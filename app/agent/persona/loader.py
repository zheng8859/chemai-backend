"""Persona 配置加载器。

从 agent/prompts/*.yaml 加载 Persona 配置，验证必填字段，
返回 PersonaConfig 数据对象供 Agent 工厂使用。
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

logger = logging.getLogger(__name__)

# ── Agent prompts 目录（相对于项目根目录） ──
_PROMPTS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "agent" / "prompts"

# ── 必填字段 ──
_REQUIRED_TOP_FIELDS = ["persona", "system_prompt", "available_skills"]
_REQUIRED_PERSONA_FIELDS = ["name", "display_name", "description"]


@dataclass
class PersonaConfig:
    """Persona 配置数据对象。

    Attributes:
        name: 角色标识符（student / teacher / tutor / parent）
        display_name: 前端展示名称
        description: 角色描述（用于内部文档）
        system_prompt: 系统提示词模板（支持 {student_context} 占位符）
        available_skills: 工具白名单（工具名称列表）
        data_access: 数据访问权限范围（可选，仅 parent persona 需要）
    """

    name: str
    display_name: str
    description: str
    system_prompt: str
    available_skills: list[str]
    data_access: Optional[dict] = None


def _validate_config(data: dict, filepath: Path) -> None:
    """验证 Persona YAML 配置的必填字段。

    Args:
        data: 从 YAML 文件解析的字典
        filepath: YAML 文件路径（用于错误信息）

    Raises:
        ValueError: 缺少必填字段或字段类型错误
    """
    # 顶层必填字段
    for field in _REQUIRED_TOP_FIELDS:
        if field not in data:
            raise ValueError(
                f"Persona 配置缺少顶层必填字段 '{field}'：{filepath}"
            )

    # persona 子字段
    persona = data["persona"]
    for field in _REQUIRED_PERSONA_FIELDS:
        if field not in persona:
            raise ValueError(
                f"Persona 配置的 persona 段缺少必填字段 '{field}'：{filepath}"
            )

    # available_skills 非空
    skills = data["available_skills"]
    if not isinstance(skills, list) or len(skills) == 0:
        raise ValueError(
            f"Persona 配置的 available_skills 必须为非空列表：{filepath}"
        )

    # system_prompt 非空
    if not isinstance(data["system_prompt"], str) or not data["system_prompt"].strip():
        raise ValueError(
            f"Persona 配置的 system_prompt 必须为非空字符串：{filepath}"
        )


def load_persona(name: str) -> PersonaConfig:
    """加载单个 Persona 配置。

    Args:
        name: 角色名（student / teacher / tutor / parent）

    Returns:
        PersonaConfig 对象

    Raises:
        FileNotFoundError: YAML 文件不存在
        ValueError: 配置验证失败
    """
    filepath = _PROMPTS_DIR / f"{name}.yaml"
    if not filepath.exists():
        raise FileNotFoundError(f"Persona 配置文件不存在：{filepath}")

    with open(filepath, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if data is None:
        raise ValueError(f"Persona 配置文件为空：{filepath}")

    _validate_config(data, filepath)

    persona = data["persona"]
    config = PersonaConfig(
        name=persona["name"],
        display_name=persona["display_name"],
        description=persona.get("description", ""),
        system_prompt=data["system_prompt"],
        available_skills=data["available_skills"],
        data_access=data.get("data_access"),
    )

    logger.info("加载 Persona 配置: %s (%d 个工具)", name, len(config.available_skills))
    return config


def load_all_personas() -> dict[str, PersonaConfig]:
    """加载所有可用的 Persona 配置。

    Returns:
        {name: PersonaConfig} 字典
    """
    personas = {}
    for filepath in _PROMPTS_DIR.glob("*.yaml"):
        name = filepath.stem
        try:
            personas[name] = load_persona(name)
        except Exception as e:
            logger.warning("跳过无效 Persona 配置 %s: %s", filepath, e)
    return personas


def get_available_persona_names() -> list[str]:
    """获取所有可用的 Persona 名称列表。"""
    return [fp.stem for fp in _PROMPTS_DIR.glob("*.yaml") if fp.stem != "__init__"]
