"""LLM Provider 纯函数测试 — LLMError、OpenAICompatProvider 构造。

不涉及实际 HTTP 调用。
"""

import pytest

from app.llm.providers.openai_compat import LLMError, OpenAICompatProvider


class TestLLMError:
    def test_is_exception(self):
        err = LLMError("请求失败")
        assert isinstance(err, Exception)

    def test_provider_preserved(self):
        err = LLMError("超时", provider="MiMo")
        assert err.provider == "MiMo"

    def test_status_code_default(self):
        err = LLMError("错误")
        assert err.status_code == 0

    def test_status_code_preserved(self):
        err = LLMError("API 错误", provider="DashScope", status_code=429)
        assert err.status_code == 429

    def test_string_repr_includes_provider(self):
        err = LLMError("请求超时", provider="MiMo")
        assert "[MiMo]" in str(err)
        assert "请求超时" in str(err)

    def test_string_repr_no_provider(self):
        err = LLMError("未知错误")
        assert "[]" in str(err)
        assert "未知错误" in str(err)


class TestOpenAICompatProviderInit:
    def test_basic_construction(self):
        p = OpenAICompatProvider(
            name="TestProvider",
            api_key="sk-test123",
            base_url="https://api.example.com/v1",
        )
        assert p.name == "TestProvider"
        assert p.api_key == "sk-test123"
        assert p.base_url == "https://api.example.com/v1"

    def test_default_model_empty(self):
        p = OpenAICompatProvider(
            name="Test", api_key="key", base_url="https://api.example.com/v1",
        )
        assert p.model == ""

    def test_custom_model(self):
        p = OpenAICompatProvider(
            name="Test", api_key="key", base_url="https://api.example.com/v1",
            model="gpt-4",
        )
        assert p.model == "gpt-4"

    def test_default_timeout(self):
        p = OpenAICompatProvider(
            name="Test", api_key="key", base_url="https://api.example.com/v1",
        )
        assert p.timeout == 60.0

    def test_custom_timeout(self):
        p = OpenAICompatProvider(
            name="Test", api_key="key", base_url="https://api.example.com/v1",
            timeout=30.0,
        )
        assert p.timeout == 30.0

    def test_base_url_strips_trailing_slash(self):
        p = OpenAICompatProvider(
            name="Test", api_key="key", base_url="https://api.example.com/v1/",
        )
        assert p.base_url == "https://api.example.com/v1"

    def test_deepseek_config(self):
        p = OpenAICompatProvider(
            name="DeepSeek",
            api_key="sk-deepseek",
            base_url="https://api.deepseek.com/v1",
            model="deepseek-chat",
        )
        assert p.name == "DeepSeek"
        assert p.model == "deepseek-chat"

    def test_dashscope_config(self):
        p = OpenAICompatProvider(
            name="DashScope",
            api_key="sk-dashscope",
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            model="qwen-plus",
        )
        assert p.name == "DashScope"
        assert p.model == "qwen-plus"
