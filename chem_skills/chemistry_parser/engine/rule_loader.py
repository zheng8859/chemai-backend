"""规则 JSON 加载器 — 统一的路径解析 + 回退逻辑。

所有需要加载 data/*.json 规则的模块共用此函数。
"""

import json
from pathlib import Path
from typing import Any


def load_json_rules(filename: str, fallback: dict[str, Any] | None = None) -> dict[str, Any]:
    """加载 data/ 目录下的 JSON 规则文件。

    查找优先级：
    1. 环境变量 CHEMAI_DATA_DIR（通过 app.config）
    2. 引擎同级 data/ 目录（__file__ 回退）

    Args:
        filename: JSON 文件名（如 "audit_conditions.json"）
        fallback: 文件不可用时的最小内置规则

    Returns:
        解析后的规则 dict
    """
    from app.config import CHEMAI_DATA_DIR

    candidates = [
        CHEMAI_DATA_DIR,
        str(Path(__file__).resolve().parent.parent.parent.parent / "data"),
    ]
    for base in candidates:
        if not base:
            continue
        path = Path(base) / filename
        if path.exists():
            with open(path, encoding="utf-8") as f:
                return json.load(f)

    return fallback or {}
