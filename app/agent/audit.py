"""审计日志 — JSONL 格式，环形缓冲区 + 异步磁盘写入。

设计：
- 内存环形缓冲区（deque maxlen=100），热路径不阻塞
- asyncio.Queue + 后台 drain 协程异步写入磁盘
- JSONL 文件路径: data/audit/{YYYY-MM-DD}.jsonl
- 自动脱敏：password/phone/token/api_key/secret → "***"
"""

import asyncio
import json
import logging
import time
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ── 审计日志目录 ──
_AUDIT_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "audit"

# ── 脱敏模式 ──
_REDACT_PATTERNS = [
    "password", "phone", "parent_phone", "token",
    "api_key", "secret", "access_key", "private_key",
]
_REDACT_PLACEHOLDER = "***"

# ── 缓冲区上限 ──
_BUFFER_MAXLEN = 100
_QUEUE_MAXSIZE = 500  # 写入队列上限


class AuditLogger:
    """审计日志记录器（单例）。

    用法：
        logger = AuditLogger.get_instance()
        await logger.audit_log(
            timestamp=time.time(),
            persona="teacher",
            skill_name="generate_questions",
            args={"knowledge_points": ["氧化还原"]},
            result={"questions": 3},
            duration_ms=1234.5,
        )
    """

    _instance: Optional["AuditLogger"] = None

    def __init__(self):
        self._buffer: deque[dict] = deque(maxlen=_BUFFER_MAXLEN)
        self._write_queue: asyncio.Queue = asyncio.Queue(maxsize=_QUEUE_MAXSIZE)
        self._drain_task: Optional[asyncio.Task] = None

    @classmethod
    def get_instance(cls) -> "AuditLogger":
        """获取单例实例。"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def _ensure_drain(self) -> None:
        """确保后台 drain 协程在运行。"""
        if self._drain_task is None or self._drain_task.done():
            self._drain_task = asyncio.create_task(self._drain())

    async def _drain(self) -> None:
        """后台协程：批量写入 JSONL 文件。"""
        batch = []
        while True:
            try:
                entry = await asyncio.wait_for(self._write_queue.get(), timeout=0.1)
                batch.append(entry)
                # 累积 10 条或等待超时 → 批量写入
                if len(batch) >= 10:
                    await self._flush_batch(batch)
                    batch.clear()
            except asyncio.TimeoutError:
                if batch:
                    await self._flush_batch(batch)
                    batch.clear()

    async def _flush_batch(self, batch: list[dict]) -> None:
        """将一批日志条目写入 JSONL 文件（异步，不阻塞事件循环）。"""
        try:
            date_str = datetime.now().strftime("%Y-%m-%d")
            filepath = _AUDIT_DIR / f"{date_str}.jsonl"
            filepath.parent.mkdir(parents=True, exist_ok=True)

            loop = asyncio.get_running_loop()

            def _sync_write():
                with open(filepath, "a", encoding="utf-8") as f:
                    for entry in batch:
                        f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")

            await loop.run_in_executor(None, _sync_write)
        except Exception as e:
            logger.error("审计日志写入失败: %s", e)

    async def audit_log(
        self,
        timestamp: float,
        persona: str,
        skill_name: str,
        args: dict,
        result: Optional[dict] = None,
        duration_ms: float = 0,
        error: Optional[str] = None,
    ) -> None:
        """记录一条审计日志。

        Args:
            timestamp: Unix 时间戳
            persona: 当前角色
            skill_name: 工具名称
            args: 工具参数（会自动脱敏）
            result: 工具返回结果（会自动截断 ≤ 200 字）
            duration_ms: 执行耗时（毫秒）
            error: 错误信息
        """
        entry = {
            "timestamp": datetime.fromtimestamp(timestamp).isoformat(),
            "persona": persona,
            "skill_name": skill_name,
            "args": _redact_dict(args),
            "result_summary": _truncate_result(result),
            "duration_ms": round(duration_ms, 2),
            "error": error,
        }

        # 写入环形缓冲区
        self._buffer.append(entry)

        # 异步写入磁盘
        await self._ensure_drain()
        try:
            self._write_queue.put_nowait(entry)
        except asyncio.QueueFull:
            logger.warning("审计日志写入队列已满，丢弃条目: %s", skill_name)

    def get_recent_logs(self, n: int = 20) -> list[dict]:
        """获取最近 n 条审计日志（从缓冲区）。"""
        items = list(self._buffer)
        return items[-n:]


def _redact_dict(d: dict) -> dict:
    """递归脱敏字典中的敏感字段（支持 dict/list/tuple/set 嵌套）。"""
    if not isinstance(d, dict):
        return d

    redacted = {}
    for key, value in d.items():
        if any(pattern in key.lower() for pattern in _REDACT_PATTERNS):
            redacted[key] = _REDACT_PLACEHOLDER
        elif isinstance(value, dict):
            redacted[key] = _redact_dict(value)
        elif isinstance(value, list):
            redacted[key] = [
                _redact_dict(item) if isinstance(item, dict) else item
                for item in value
            ]
        elif isinstance(value, (tuple, set)):
            # tuple/set 转换为 list 处理（保持 JSON 可序列化）
            redacted[key] = list(value)
        else:
            redacted[key] = value
    return redacted


def _truncate_result(result: Optional[dict], max_chars: int = 200) -> str:
    """截断结果摘要。"""
    if result is None:
        return ""
    try:
        text = json.dumps(result, ensure_ascii=False, default=str)
        if len(text) <= max_chars:
            return text
        return text[:max_chars] + "..."
    except (TypeError, ValueError):
        return str(result)[:max_chars]
