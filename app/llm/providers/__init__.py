"""LLM Provider 层 — OpenAI 兼容接口抽象。"""

from .openai_compat import OpenAICompatProvider, LLMError

__all__ = ["OpenAICompatProvider", "LLMError"]
