"""Evals 共享 fixtures — Golden 数据集、API client、认证 token。

用法:
    pytest tests/evals/ -v           # 跑 L1+L2（跳 L3 slow）
    pytest tests/evals/ -v --run-slow # 启用 L3 slow
"""

import json
import os
import sqlite3
from pathlib import Path

import pytest

# ── 路径常量 ──────────────────────────────────
EVALS_DIR = Path(__file__).resolve().parent
GOLDEN_DIR = EVALS_DIR / "golden_dataset"
DB_PATH = GOLDEN_DIR / "golden_dataset.db"


# ═══════════════════════════════════════════════════════════
# --run-slow 命令行选项
# ═══════════════════════════════════════════════════════════

def pytest_addoption(parser):
    parser.addoption(
        "--run-slow",
        action="store_true",
        default=False,
        help="启用 L3 @slow 标记的测试（需真实 LLM 调用）",
    )


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "slow: L3 慢速测试，需真实 LLM 调用，默认跳过",
    )


def pytest_collection_modifyitems(config, items):
    """无 --run-slow 时自动跳过 @slow 标记的测试。"""
    if not config.getoption("--run-slow"):
        skip_slow = pytest.mark.skip(reason="需 --run-slow 选项启用 L3 slow 测试")
        for item in items:
            if "slow" in item.keywords:
                item.add_marker(skip_slow)


# ═══════════════════════════════════════════════════════════
# Golden 数据集 fixtures
# ═══════════════════════════════════════════════════════════

@pytest.fixture(scope="session")
def golden_db() -> sqlite3.Connection:
    """Golden 数据集 SQLite 连接（session 级，所有测试共享）。"""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()


@pytest.fixture(scope="session")
def golden_samples() -> list[dict]:
    """加载全部 100 条 Golden 样本（从 JSON 文件）。"""
    all_samples = []
    for json_path in sorted(GOLDEN_DIR.glob("*.json")):
        if json_path.name == "schema.json":
            continue
        data = json.loads(json_path.read_text(encoding="utf-8"))
        all_samples.extend(data.get("samples", []))
    return all_samples


@pytest.fixture(scope="session")
def golden_by_module(golden_samples) -> dict[str, list[dict]]:
    """按化学模块分组的 Golden 样本（category 字段）。"""
    groups = {}
    for s in golden_samples:
        groups.setdefault(s["category"], []).append(s)
    return groups


@pytest.fixture(scope="session")
def golden_by_category(golden_by_module) -> dict[str, list[dict]]:
    """按化学模块分组的 Golden 样本（category 字段，golden_by_module 别名）。"""
    return golden_by_module


@pytest.fixture(scope="session")
def golden_by_type(golden_samples) -> dict[str, list[dict]]:
    """按样本类型（出题/诊断/辅导）分组的 Golden 样本（module 字段）。"""
    groups = {}
    for s in golden_samples:
        groups.setdefault(s["module"], []).append(s)
    return groups


# ═══════════════════════════════════════════════════════════
# API 相关 fixtures（需要后端运行时使用）
# ═══════════════════════════════════════════════════════════

@pytest.fixture(scope="session")
def api_base_url() -> str:
    """API 基础 URL，默认 http://localhost:8000。"""
    return os.getenv("CHEMAI_API_URL", "http://localhost:8000")


@pytest.fixture(scope="session")
def has_api_key() -> bool:
    """检查是否存在 LLM API Key（用于跳过 L3 slow 测试）。"""
    return bool(
        os.getenv("DASHSCOPE_API_KEY")
        or os.getenv("MIMO_API_KEY")
        or os.getenv("OPENAI_API_KEY")
    )


@pytest.fixture
def api_key_missing(request, has_api_key):
    """当无 API Key 时跳过 L3 测试的 fixture。

    用法:
        def test_l3_something(api_key_missing): ...
    """
    if request.node.get_closest_marker("l3") and not has_api_key:
        pytest.skip("无 LLM API Key（设置 DASHSCOPE_API_KEY 或 MIMO_API_KEY）")


# ═══════════════════════════════════════════════════════════
# 回归基线样本 fixtures
# ═══════════════════════════════════════════════════════════

REGRESSION_IDS = {"golden_027", "golden_031", "golden_056", "golden_089"}


@pytest.fixture(scope="session")
def regression_samples(golden_samples) -> list[dict]:
    """4 条回归基线样本（Doc 54 指定，不可修改预期值）。"""
    return [s for s in golden_samples if s["id"] in REGRESSION_IDS]
