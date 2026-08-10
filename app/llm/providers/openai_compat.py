"""OpenAI 兼容 API Provider — 支持 DeepSeek/MiMo/通义千问等。

通过 HTTP POST 调用 /v1/chat/completions 端点。
"""

import json
import httpx
from typing import Any


class LLMError(Exception):
    """LLM 调用异常。"""
    def __init__(self, message: str, provider: str = "", status_code: int = 0):
        self.provider = provider
        self.status_code = status_code
        super().__init__(f"[{provider}] {message}")


class OpenAICompatProvider:
    """OpenAI 兼容的 LLM Provider。

    支持：
    - DeepSeek: https://api.deepseek.com/v1
    - MiMo: 自定义 base_url
    - 通义千问 DashScope: https://dashscope.aliyuncs.com/compatible-mode/v1
    - 智谱 GLM: https://open.bigmodel.cn/api/paas/v4
    """

    def __init__(
        self,
        name: str,
        api_key: str,
        base_url: str,
        model: str = "",
        timeout: float = 60.0,
    ):
        self.name = name
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    async def chat(
        self,
        messages: list[dict[str, Any]],
        temperature: float = 0.3,
        max_tokens: int = 4096,
        response_format: dict | None = None,
        tools: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """发送 chat completion 请求，返回完整 message 对象。

        Args:
            messages: [{"role": "system", "content": "..."}, ...]
            temperature: 温度参数
            max_tokens: 最大 token 数
            response_format: 可选，如 {"type": "json_object"}
            tools: 可选，工具定义列表 (OpenAI function-calling 格式)

        Returns:
            {"content": str | None, "tool_calls": list | None}

        Raises:
            LLMError: API 调用失败
        """
        url = f"{self.base_url}/chat/completions"

        payload: dict[str, Any] = {
            "model": self.model or "default",
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        if response_format:
            payload["response_format"] = response_format
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(url, json=payload, headers=headers)
                if resp.status_code != 200:
                    raise LLMError(
                        f"API 返回 {resp.status_code}: {resp.text[:500]}",
                        provider=self.name,
                        status_code=resp.status_code,
                    )
                data = resp.json()
                msg = data["choices"][0]["message"]
                return {
                    "content": msg.get("content"),
                    "tool_calls": msg.get("tool_calls"),
                }

        except httpx.TimeoutException:
            raise LLMError("请求超时", provider=self.name)
        except LLMError:
            raise
        except Exception as e:
            raise LLMError(str(e), provider=self.name)
