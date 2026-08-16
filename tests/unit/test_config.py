"""Config 模块测试 — 验证所有环境变量默认值和常量的类型、取值。"""

import os
from pathlib import Path

import pytest


class TestConfigDefaults:
    """测试 config 模块中所有常量的默认值和类型。"""

    def test_project_root_is_valid_path(self):
        from app.config import PROJECT_ROOT
        assert isinstance(PROJECT_ROOT, Path)
        # PROJECT_ROOT 应该包含 "chemai-backend"
        assert "chemai-backend" in str(PROJECT_ROOT).lower().replace("\\", "/").split("/")[-1]

    def test_data_dir_under_project_root(self):
        from app.config import PROJECT_ROOT, DATA_DIR
        assert DATA_DIR.parent == PROJECT_ROOT

    def test_chemai_data_dir_default(self):
        from app.config import CHEMAI_DATA_DIR, DATA_DIR
        # 默认值使用 DATA_DIR
        assert CHEMAI_DATA_DIR == str(DATA_DIR)

    def test_database_url_is_sqlite(self):
        from app.config import DATABASE_URL
        assert "sqlite" in DATABASE_URL
        assert "chemai.db" in DATABASE_URL

    def test_checkpoint_db_url_is_separate(self):
        from app.config import CHECKPOINT_DB_URL, DATABASE_URL
        assert CHECKPOINT_DB_URL != DATABASE_URL
        assert "checkpoint.db" in CHECKPOINT_DB_URL

    def test_memory_db_url_is_separate(self):
        from app.config import MEMORY_DB_URL
        assert "memory.db" in MEMORY_DB_URL

    def test_chroma_db_path(self):
        from app.config import CHROMA_DB_PATH
        assert "chroma_db" in CHROMA_DB_PATH

    def test_chroma_collection(self):
        from app.config import CHROMA_COLLECTION
        assert CHROMA_COLLECTION == "exam_questions"

    def test_llm_api_keys_are_strings(self):
        from app.config import (
            MIMO_API_KEY, DASHSCOPE_API_KEY, DEEPSEEK_API_KEY, ZHIPU_API_KEY,
        )
        assert isinstance(MIMO_API_KEY, str)
        assert isinstance(DASHSCOPE_API_KEY, str)
        assert isinstance(DEEPSEEK_API_KEY, str)
        assert isinstance(ZHIPU_API_KEY, str)

    def test_llm_base_urls_default_empty(self):
        from app.config import MIMO_BASE_URL, DEEPSEEK_BASE_URL
        assert MIMO_BASE_URL == ""
        assert DEEPSEEK_BASE_URL == ""

    def test_llm_provider_default(self):
        from app.config import LLM_PROVIDER
        assert LLM_PROVIDER == "auto"

    def test_llm_temperature_default(self):
        from app.config import LLM_TEMPERATURE
        assert isinstance(LLM_TEMPERATURE, float)
        assert LLM_TEMPERATURE == 0.3

    def test_llm_max_tokens_default(self):
        from app.config import LLM_MAX_TOKENS
        assert isinstance(LLM_MAX_TOKENS, int)
        assert LLM_MAX_TOKENS == 4096

    def test_llm_max_retries_default(self):
        from app.config import LLM_MAX_RETRIES
        assert LLM_MAX_RETRIES == 3

    def test_ocr_api_keys_default_empty(self):
        from app.config import BAIDU_OCR_API_KEY, BAIDU_OCR_SECRET_KEY
        assert BAIDU_OCR_API_KEY == ""
        assert BAIDU_OCR_SECRET_KEY == ""

    def test_ocr_sheet_provider_default(self):
        from app.config import OCR_SHEET_PROVIDER
        assert OCR_SHEET_PROVIDER == "mineru"

    def test_ocr_poll_interval_default(self):
        from app.config import OCR_POLL_INTERVAL
        assert isinstance(OCR_POLL_INTERVAL, int)
        assert OCR_POLL_INTERVAL == 5

    def test_agent_version_default(self):
        from app.config import AGENT_VERSION
        assert AGENT_VERSION == "v2"

    def test_agent_recursion_limit_default(self):
        from app.config import AGENT_RECURSION_LIMIT
        assert isinstance(AGENT_RECURSION_LIMIT, int)
        assert AGENT_RECURSION_LIMIT == 12

    def test_agent_context_max_messages_default(self):
        from app.config import AGENT_CONTEXT_MAX_MESSAGES
        assert AGENT_CONTEXT_MAX_MESSAGES == 30

    def test_knowledge_graph_path(self):
        from app.config import KNOWLEDGE_GRAPH_PATH
        assert "knowledge_points.json" in KNOWLEDGE_GRAPH_PATH

    def test_exam_bank_path(self):
        from app.config import EXAM_BANK_PATH
        assert "exam_bank" in EXAM_BANK_PATH

    def test_jwt_secret_not_weak_default(self):
        from app.config import JWT_SECRET, DEFAULT_JWT_SECRET
        # 安全要求：不得回退到弱默认值（测试环境由 conftest 注入测试密钥）
        assert JWT_SECRET not in ("", DEFAULT_JWT_SECRET)

    def test_jwt_algorithm(self):
        from app.config import JWT_ALGORITHM
        assert JWT_ALGORITHM == "HS256"

    def test_jwt_expire_minutes_default(self):
        from app.config import JWT_EXPIRE_MINUTES
        assert JWT_EXPIRE_MINUTES == 480

    def test_scheduler_timezone(self):
        from app.config import SCHEDULER_TIMEZONE
        assert SCHEDULER_TIMEZONE == "Asia/Shanghai"


class TestConfigEnvOverride:
    """测试环境变量覆盖默认值。"""

    def test_env_overrides_database_url(self, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "mysql+asyncmy://user:pass@host/db")
        # 重新导入以获取新值
        import importlib
        import app.config
        importlib.reload(app.config)
        from app.config import DATABASE_URL
        assert "mysql" in DATABASE_URL
        # 恢复
        monkeypatch.delenv("DATABASE_URL", raising=False)
        importlib.reload(app.config)

    def test_env_overrides_llm_temperature(self, monkeypatch):
        monkeypatch.setenv("LLM_TEMPERATURE", "0.7")
        import importlib
        import app.config
        importlib.reload(app.config)
        from app.config import LLM_TEMPERATURE
        assert LLM_TEMPERATURE == 0.7
        monkeypatch.delenv("LLM_TEMPERATURE", raising=False)
        importlib.reload(app.config)

    def test_env_overrides_llm_max_retries(self, monkeypatch):
        monkeypatch.setenv("LLM_MAX_RETRIES", "5")
        import importlib
        import app.config
        importlib.reload(app.config)
        from app.config import LLM_MAX_RETRIES
        assert LLM_MAX_RETRIES == 5
        monkeypatch.delenv("LLM_MAX_RETRIES", raising=False)
        importlib.reload(app.config)

    def test_env_overrides_agent_version(self, monkeypatch):
        monkeypatch.setenv("AGENT_VERSION", "v1")
        import importlib
        import app.config
        importlib.reload(app.config)
        from app.config import AGENT_VERSION
        assert AGENT_VERSION == "v1"
        monkeypatch.delenv("AGENT_VERSION", raising=False)
        importlib.reload(app.config)

    def test_env_overrides_jwt_expire(self, monkeypatch):
        monkeypatch.setenv("JWT_EXPIRE_MINUTES", "60")
        import importlib
        import app.config
        importlib.reload(app.config)
        from app.config import JWT_EXPIRE_MINUTES
        assert JWT_EXPIRE_MINUTES == 60
        monkeypatch.delenv("JWT_EXPIRE_MINUTES", raising=False)
        importlib.reload(app.config)
