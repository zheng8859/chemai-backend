"""LLM Provider 工厂 — 模型创建 + 熔断器 + 三级回退。

Provider 配置（38号实测数据）：
- MiMo-V2.5: 视觉+联网搜索, P50 5.0s / P99 15.2s
- 通义千问 qwen-turbo: 最低延迟, P50 1.5s / P99 5.1s
- DeepSeek-V4-Flash: 化学满分, 成本最低

熔断器状态机：
CLOSED（正常）──连续失败 3 次──→ OPEN（熔断，30s 内直接跳过）
OPEN ──30s 后──→ HALF_OPEN（放行 1 次试探）
HALF_OPEN ──成功──→ CLOSED（恢复）
HALF_OPEN ──失败──→ OPEN（重新计时 30s）
"""

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from langchain_openai import ChatOpenAI

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════════
# Provider 配置
# ═══════════════════════════════════════════════════════════════════════════════

PROVIDER_CONFIG = {
    "mimo": {
        "name": "MiMo-V2.5",
        "base_url": os.getenv("MIMO_BASE_URL") or "https://api.mimo.com/v1",
        "api_key": os.getenv("MIMO_API_KEY", ""),
        "model": os.getenv("MIMO_MODEL", "mimo-v2.5"),
        "priority": 1,
        "capabilities": ["vision", "search"],
    },
    "qwen": {
        "name": "通义千问 Turbo",
        "base_url": os.getenv("QWEN_BASE_URL") or "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "api_key": os.getenv("DASHSCOPE_API_KEY", ""),
        "model": os.getenv("QWEN_MODEL", "qwen-turbo"),
        "priority": 2,
        "capabilities": ["text"],
    },
    "deepseek": {
        "name": "DeepSeek-V4-Flash",
        "base_url": os.getenv("DEEPSEEK_BASE_URL") or "https://api.deepseek.com/v1",
        "api_key": os.getenv("DEEPSEEK_API_KEY", ""),
        "model": os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash"),
        "priority": 3,
        "capabilities": ["text"],
    },
}

# 默认 Provider 优先级列表
FALLBACK_ORDER = ["mimo", "qwen", "deepseek"]

# 重试配置
MAX_RETRIES_PER_PROVIDER = 3
RETRY_DELAYS = [1.0, 2.0, 4.0]  # 指数退避（秒）


# ═══════════════════════════════════════════════════════════════════════════════
# 熔断器状态机
# ═══════════════════════════════════════════════════════════════════════════════

class CircuitState(str, Enum):
    CLOSED = "closed"        # 正常
    OPEN = "open"            # 熔断
    HALF_OPEN = "half_open"  # 半开（试探）


@dataclass
class CircuitBreaker:
    """每个 Provider 独立的熔断器。"""

    provider: str
    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    failure_threshold: int = 3
    recovery_timeout: float = 30.0  # OPEN 状态持续时间（秒）
    last_failure_time: float = 0.0
    open_time: float = 0.0
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def record_success(self) -> None:
        """记录成功调用。"""
        async with self._lock:
            if self.state == CircuitState.HALF_OPEN:
                logger.info("熔断器 %s: HALF_OPEN → CLOSED（试探成功）", self.provider)
            self.state = CircuitState.CLOSED
            self.failure_count = 0

    async def record_failure(self) -> None:
        """记录失败调用。"""
        async with self._lock:
            self.failure_count += 1
            self.last_failure_time = time.monotonic()

            if self.state == CircuitState.HALF_OPEN:
                logger.warning("熔断器 %s: HALF_OPEN → OPEN（试探失败）", self.provider)
                self.state = CircuitState.OPEN
                self.open_time = time.monotonic()
            elif self.failure_count >= self.failure_threshold:
                logger.warning("熔断器 %s: CLOSED → OPEN（连续失败 %d 次）",
                               self.provider, self.failure_count)
                self.state = CircuitState.OPEN
                self.open_time = time.monotonic()

    async def allow_request(self) -> bool:
        """判断是否允许通过请求。

        Returns:
            True = 允许调用, False = 跳过此 Provider
        """
        async with self._lock:
            if self.state == CircuitState.CLOSED:
                return True

            if self.state == CircuitState.OPEN:
                elapsed = time.monotonic() - self.open_time
                if elapsed >= self.recovery_timeout:
                    logger.info("熔断器 %s: OPEN → HALF_OPEN（%d 秒已过）",
                                self.provider, int(elapsed))
                    self.state = CircuitState.HALF_OPEN
                    return True
                return False

            # HALF_OPEN: 允许 1 次试探
            return True


# ── 全局熔断器实例（进程内存） ──

_circuit_breakers: dict[str, CircuitBreaker] = {}


def _get_circuit_breaker(provider: str) -> CircuitBreaker:
    """获取或创建指定 Provider 的熔断器。"""
    if provider not in _circuit_breakers:
        _circuit_breakers[provider] = CircuitBreaker(provider=provider)
    return _circuit_breakers[provider]


# ═══════════════════════════════════════════════════════════════════════════════
# 模型工厂
# ═══════════════════════════════════════════════════════════════════════════════

def get_model(
    provider: str,
    tools: Optional[list] = None,
    temperature: float = 0.3,
    max_tokens: int = 4096,
    timeout: float = 60.0,
) -> ChatOpenAI:
    """创建 ChatOpenAI 兼容的 LLM 实例。

    Args:
        provider: Provider 标识（mimo / qwen / deepseek）
        tools: 工具列表（用于 tool calling）
        temperature: 温度参数
        max_tokens: 最大输出 token 数
        timeout: 请求超时（秒）

    Returns:
        ChatOpenAI 实例

    Raises:
        ValueError: 未知的 Provider
    """
    config = PROVIDER_CONFIG.get(provider)
    if config is None:
        raise ValueError(f"未知的 LLM Provider: {provider}，可用: {list(PROVIDER_CONFIG.keys())}")

    if not config["api_key"]:
        logger.warning("Provider %s 未配置 API Key，将使用环境变量默认值", provider)

    kwargs = {
        "model": config["model"],
        "base_url": config["base_url"],
        "api_key": config["api_key"],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "timeout": timeout,
    }

    if tools:
        kwargs["tools"] = tools

    model = ChatOpenAI(**kwargs)
    logger.debug("创建模型: %s (%s)", config["name"], config["model"])
    return model


def get_agent_model(provider: str, tools: Optional[list] = None) -> ChatOpenAI:
    """创建 Agent 推理模型（带工具绑定）。

    Args:
        provider: Provider 标识
        tools: 工具列表

    Returns:
        ChatOpenAI 实例
    """
    return get_model(provider, tools=tools, temperature=0.3, max_tokens=4096)


def get_tool_model(provider: str) -> ChatOpenAI:
    """创建工具系统模型（不带工具绑定，用于 Planner、摘要等）。

    Args:
        provider: Provider 标识

    Returns:
        ChatOpenAI 实例
    """
    return get_model(provider, tools=None, temperature=0.1, max_tokens=2048)


# ═══════════════════════════════════════════════════════════════════════════════
# 回退逻辑（含熔断器 + 重试）
# ═══════════════════════════════════════════════════════════════════════════════

async def invoke_with_fallback(
    messages: list,
    provider_order: Optional[list[str]] = None,
    tools: Optional[list] = None,
) -> dict:
    """使用回退链调用 LLM。

    流程：
    1. 按 provider_order 依次尝试
    2. 每个 Provider 先检查熔断器状态 → 熔断中则跳过
    3. 每个 Provider 最多重试 MAX_RETRIES_PER_PROVIDER 次（指数退避）
    4. 成功则返回结果，失败则尝试下一个 Provider
    5. 所有 Provider 都失败则抛出 RuntimeError

    Args:
        messages: 消息列表
        provider_order: Provider 优先级列表（默认 ["mimo", "qwen", "deepseek"]）
        tools: 工具列表
        streaming: 是否流式调用

    Returns:
        {"content": str, "provider": str, "retry_count": int}

    Raises:
        RuntimeError: 所有 Provider 都失败
    """
    order = provider_order or FALLBACK_ORDER
    last_error = None

    for provider in order:
        cb = _get_circuit_breaker(provider)

        # 检查熔断器
        if not await cb.allow_request():
            logger.info("Provider %s 已熔断，跳过", provider)
            continue

        # 重试循环
        for attempt in range(MAX_RETRIES_PER_PROVIDER):
            try:
                model = get_agent_model(provider)
                if tools:
                    model = model.bind_tools(tools)

                response = await model.ainvoke(messages)

                # 成功 → 熔断器记录
                await cb.record_success()
                return {
                    "content": response.content if hasattr(response, 'content') else str(response),
                    "provider": provider,
                    "retry_count": attempt,
                    "response": response,
                }

            except Exception as e:
                logger.warning(
                    "Provider %s 第 %d/%d 次尝试失败: %s",
                    provider, attempt + 1, MAX_RETRIES_PER_PROVIDER, e,
                )
                last_error = e
                await cb.record_failure()

                if attempt < MAX_RETRIES_PER_PROVIDER - 1:
                    delay = RETRY_DELAYS[min(attempt, len(RETRY_DELAYS) - 1)]
                    await asyncio.sleep(delay)

        logger.error("Provider %s 所有重试均失败", provider)

    raise RuntimeError(
        f"所有 LLM Provider 调用均失败（尝试了 {len(order)} 个 Provider）。"
        f"最后一个错误: {last_error}"
    )


async def invoke_with_fallback_streaming(
    messages: list,
    provider_order: Optional[list[str]] = None,
    tools: Optional[list] = None,
):
    """流式调用 LLM（回退链 + 熔断器）。

    与 invoke_with_fallback 逻辑相同，但使用 astream_events 返回异步生成器。
    """
    order = provider_order or FALLBACK_ORDER
    last_error = None

    for provider in order:
        cb = _get_circuit_breaker(provider)

        if not await cb.allow_request():
            logger.info("Provider %s 已熔断，跳过", provider)
            continue

        for attempt in range(MAX_RETRIES_PER_PROVIDER):
            try:
                model = get_agent_model(provider)
                if tools:
                    model = model.bind_tools(tools)

                # 返回异步生成器（熔断器在流成功完成后才记录成功）
                async def safe_stream(model=model):
                    try:
                        async for event in model.astream_events(messages, version="v2"):
                            yield event
                        await cb.record_success()
                    except Exception:
                        await cb.record_failure()
                        raise

                return safe_stream(), provider

            except Exception as e:
                logger.warning(
                    "Provider %s 第 %d/%d 次流式尝试失败: %s",
                    provider, attempt + 1, MAX_RETRIES_PER_PROVIDER, e,
                )
                last_error = e
                await cb.record_failure()

                if attempt < MAX_RETRIES_PER_PROVIDER - 1:
                    delay = RETRY_DELAYS[min(attempt, len(RETRY_DELAYS) - 1)]
                    await asyncio.sleep(delay)

        logger.error("Provider %s 所有流式重试均失败", provider)

    raise RuntimeError(
        f"所有 LLM Provider 流式调用均失败。最后一个错误: {last_error}"
    )


def get_circuit_breaker_status() -> dict[str, dict]:
    """获取所有 Provider 的熔断器状态（用于监控）。"""
    return {
        provider: {
            "state": cb.state.value,
            "failure_count": cb.failure_count,
            "last_failure_time": cb.last_failure_time,
        }
        for provider, cb in _circuit_breakers.items()
    }
