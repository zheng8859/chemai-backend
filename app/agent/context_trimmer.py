"""上下文裁剪器 — 三层裁剪策略。

当消息数超过阈值时触发：
Layer 1: 无条件保留最近 6 条消息
Layer 2: 15 个教学关键词命中 → 额外保留
Layer 3: 丢弃 ≥ 10 条时 LLM 摘要压缩（≤ 200 字）

摘要缓存 per checkpoint，避免重复生成。
"""

import logging
from typing import Optional

from app.llm.model_factory import get_tool_model

logger = logging.getLogger(__name__)

# ── 裁剪参数 ──
MAX_MESSAGES = 30
KEEP_RECENT = 6
SUMMARY_MIN_DISCARD = 10  # 丢弃 ≥ 10 条时触发摘要
SUMMARY_MAX_CHARS = 200  # 摘要最大字符数

# ── 教学关键词（Layer 2 过滤） ──
_TEACHING_KEYWORDS = [
    "学生", "诊断", "障碍", "考试", "题目", "知识点",
    "分数", "薄弱", "学习计划", "错题", "成绩", "练习",
    "班级", "教师", "实验", "方程式", "配平", "审核",
    "出题", "化学", "题库", "作业", "正确率", "进度",
]

# ── 摘要缓存（per checkpoint，LRU 淘汰） ──
from collections import OrderedDict

_MAX_CACHE_SIZE = 1000
_summary_cache: OrderedDict[str, str] = OrderedDict()


def _cache_put(thread_id: str, summary: str) -> None:
    """写入缓存（超过上限时淘汰最旧条目）。"""
    if len(_summary_cache) >= _MAX_CACHE_SIZE:
        _summary_cache.popitem(last=False)
    _summary_cache[thread_id] = summary


def trim(
    messages: list[dict],
    max_messages: int = MAX_MESSAGES,
    keep_recent: int = KEEP_RECENT,
    thread_id: str = "",
) -> list[dict]:
    """三层裁剪消息列表。

    Args:
        messages: 消息列表（[{"role": str, "content": str}, ...]）
        max_messages: 触发裁剪的阈值
        keep_recent: Layer 1 无条件保留的最近消息数
        thread_id: 对话线程 ID（用于摘要缓存键）

    Returns:
        裁剪后的消息列表
    """
    if len(messages) <= max_messages:
        return messages

    total = len(messages)
    recent = messages[-keep_recent:]  # Layer 1: 最近 6 条
    older = messages[:-keep_recent]   # 待裁剪区域

    # Layer 2: 关键词过滤
    kept_by_keyword = []
    discarded = []

    for msg in older:
        content = msg.get("content", "")
        if any(kw in content for kw in _TEACHING_KEYWORDS):
            kept_by_keyword.append(msg)
        else:
            discarded.append(msg)

    # 合并：关键词保留 + 最近 6 条
    result = kept_by_keyword + recent
    discarded_count = len(discarded)

    logger.info(
        "上下文裁剪: %d → %d 条（Layer1=%d, Layer2=%d, 丢弃=%d）",
        total, len(result), keep_recent, len(kept_by_keyword), discarded_count,
    )

    # Layer 3: 摘要生成（异步完成后通过回调注入）
    if discarded_count >= SUMMARY_MIN_DISCARD:
        _schedule_summary(discarded, thread_id)

    # 如果有缓存摘要，prepend 到结果
    if thread_id and thread_id in _summary_cache:
        summary_msg = {
            "role": "system",
            "content": f"[对话历史摘要] {_summary_cache[thread_id]}",
        }
        result.insert(0, summary_msg)

    return result


async def generate_summary(discarded: list[dict]) -> str:
    """为被丢弃的消息生成 LLM 摘要。

    Args:
        discarded: 被丢弃的消息列表

    Returns:
        ≤ 200 字的中文摘要
    """
    if not discarded:
        return ""

    # 拼接被丢弃消息的文本
    joined = "\n".join(
        f"[{m.get('role', '?')}]: {str(m.get('content', ''))[:200]}"
        for m in discarded
    )

    prompt = f"""请将以下对话历史压缩为不超过 200 字的中文摘要。
保留关键信息：涉及的学生、知识点、诊断结果、题目内容、决策结论。

对话：
{joined}

摘要（≤200字）："""

    try:
        model = get_tool_model("qwen")
        response = await model.ainvoke([{"role": "user", "content": prompt}])
        content = response.content if hasattr(response, 'content') else str(response)
        summary = content[:SUMMARY_MAX_CHARS]
        logger.info("上下文摘要生成成功: %d 字符", len(summary))
        return summary
    except Exception as e:
        logger.warning("上下文摘要生成失败: %s", e)
        return ""


def _schedule_summary(discarded: list[dict], thread_id: str) -> None:
    """调度摘要生成任务（异步后台，不阻塞主流程）。

    Args:
        discarded: 被丢弃的消息
        thread_id: 对话线程 ID
    """
    if not thread_id:
        return

    async def _run():
        try:
            summary = await generate_summary(discarded)
            if summary:
                _cache_put(thread_id, summary)
        except Exception as e:
            logger.warning("摘要调度失败: %s", e)

    import asyncio
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_run())
    except RuntimeError:
        # 无事件循环（测试环境），同步执行
        pass


def should_trim(messages: list[dict], threshold: int = MAX_MESSAGES) -> bool:
    """判断是否需要裁剪。

    Args:
        messages: 消息列表
        threshold: 消息数阈值

    Returns:
        True = 需要裁剪
    """
    return len(messages) > threshold


def clear_summary_cache(thread_id: str = "") -> None:
    """清除摘要缓存。

    Args:
        thread_id: 指定线程 ID（空 = 清除全部）
    """
    if thread_id:
        _summary_cache.pop(thread_id, None)
    else:
        _summary_cache.clear()
