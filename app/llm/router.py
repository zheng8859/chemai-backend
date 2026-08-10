"""LLM 三层 Fallback 路由 — MiMo → 通义千问 → DeepSeek。

调用顺序：
1. MiMo（主力）
2. 通义千问 DashScope（回退）
3. DeepSeek（最终回退）
"""

import logging
from typing import Any

from ..config import (
    MIMO_API_KEY,
    MIMO_BASE_URL,
    DASHSCOPE_API_KEY,
    DEEPSEEK_API_KEY,
    DEEPSEEK_BASE_URL,
    LLM_TEMPERATURE,
    LLM_MAX_TOKENS,
    LLM_MAX_RETRIES,
)
from .providers import OpenAICompatProvider, LLMError

logger = logging.getLogger(__name__)

# ── Provider 实例（懒加载） ──────────────────────────────────

_providers: list[OpenAICompatProvider] | None = None


def _get_providers() -> list[OpenAICompatProvider]:
    """获取已配置的 provider 列表（按优先级）。"""
    global _providers
    if _providers is not None:
        return _providers

    _providers = []
    if MIMO_API_KEY and MIMO_BASE_URL:
        _providers.append(OpenAICompatProvider(
            name="MiMo",
            api_key=MIMO_API_KEY,
            base_url=MIMO_BASE_URL,
            timeout=60.0,
        ))
    if DASHSCOPE_API_KEY:
        _providers.append(OpenAICompatProvider(
            name="DashScope",
            api_key=DASHSCOPE_API_KEY,
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            model="qwen-plus",
            timeout=60.0,
        ))
    if DEEPSEEK_API_KEY:
        _providers.append(OpenAICompatProvider(
            name="DeepSeek",
            api_key=DEEPSEEK_API_KEY,
            base_url=DEEPSEEK_BASE_URL or "https://api.deepseek.com/v1",
            model="deepseek-chat",
            timeout=60.0,
        ))

    return _providers


# ── Public API ───────────────────────────────────────────────

async def llm_chat(
    messages: list[dict[str, str]],
    temperature: float | None = None,
    max_tokens: int | None = None,
    json_mode: bool = False,
) -> str:
    """通过 fallback 路由调用 LLM（纯文本模式）。

    依次尝试已配置的 provider，第一个成功即返回。
    全部失败则抛出 LLMError。

    Args:
        messages: 消息列表
        temperature: 温度（默认从 config 读取）
        max_tokens: 最大 token（默认从 config 读取）
        json_mode: 是否启用 JSON 输出模式

    Returns:
        LLM 响应文本

    Raises:
        LLMError: 所有 provider 均失败
    """
    temp = temperature if temperature is not None else LLM_TEMPERATURE
    tokens = max_tokens if max_tokens is not None else LLM_MAX_TOKENS

    response_format = {"type": "json_object"} if json_mode else None

    providers = _get_providers()
    if not providers:
        raise LLMError("没有配置任何 LLM Provider", provider="none")

    last_error: LLMError | None = None

    for provider in providers:
        try:
            logger.info(f"LLM call: {provider.name}")
            result = await provider.chat(
                messages,
                temperature=temp,
                max_tokens=tokens,
                response_format=response_format,
            )
            logger.info(f"LLM success: {provider.name}")
            return result["content"] or ""
        except LLMError as e:
            logger.warning(f"LLM fallback from {provider.name}: {e}")
            last_error = e
            continue

    raise LLMError(
        f"所有 LLM Provider 均调用失败 (共{len(providers)}个)",
        provider="all",
    )


async def llm_chat_with_tools(
    messages: list[dict[str, str]],
    tools: list[dict[str, Any]],
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> dict[str, Any]:
    """通过 fallback 路由调用 LLM（工具调用模式）。

    Args:
        messages: 消息列表
        tools: 工具定义列表 (OpenAI function-calling 格式)
        temperature: 温度
        max_tokens: 最大 token

    Returns:
        {"content": str | None, "tool_calls": list | None}

    Raises:
        LLMError: 所有 provider 均失败
    """
    temp = temperature if temperature is not None else LLM_TEMPERATURE
    tokens = max_tokens if max_tokens is not None else LLM_MAX_TOKENS

    providers = _get_providers()
    if not providers:
        raise LLMError("没有配置任何 LLM Provider", provider="none")

    last_error: LLMError | None = None

    for provider in providers:
        try:
            logger.info(f"LLM tool call: {provider.name}")
            result = await provider.chat(
                messages,
                temperature=temp,
                max_tokens=tokens,
                tools=tools,
            )
            logger.info(f"LLM tool success: {provider.name}")
            return result
        except LLMError as e:
            logger.warning(f"LLM tool fallback from {provider.name}: {e}")
            last_error = e
            continue

    raise LLMError(
        f"所有 LLM Provider 均调用失败 (共{len(providers)}个)",
        provider="all",
    )
