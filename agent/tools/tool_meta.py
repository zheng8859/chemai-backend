"""Agent 工具元数据注册中心。

每个工具通过 @register_tool 装饰器注册元数据：
- name: 工具名称（必须唯一）
- persona: 可用角色列表，如 ["student"]、["teacher", "tutor"]
- call_limit: 每会话最大调用次数（0 = 无限制）
- requires_approval: 是否需要教师审批后才能执行（默认 False）
- prerequisites: 前置条件参数列表（Guard L1 检查）
- description: 工具功能描述（供 Agent 使用）
"""

from typing import Callable, Optional

# ── 全局元数据存储 ──

_tool_meta: dict[str, dict] = {}

# 已注册的函数名集合（用于完整性验证）
_registered_func_names: set[str] = set()


def register_tool(
    name: str,
    persona: list[str],
    call_limit: int = 0,
    requires_approval: bool = False,
    prerequisites: Optional[list[str]] = None,
    description: str = "",
):
    """装饰器：注册 Agent 工具元数据。

    Usage:
        @register_tool(
            name="periodic_law_tutor",
            persona=["student"],
            call_limit=5,
            description="Socratic tutoring for periodic law problems",
        )
        async def periodic_law_tutor(...):
            ...

        @register_tool(
            name="delete_bank",
            persona=["teacher"],
            call_limit=3,
            requires_approval=True,
            prerequisites=["bank_id"],
            description="删除题库（危险操作，需审批）",
        )
        async def delete_bank(...):
            ...
    """

    def decorator(func: Callable) -> Callable:
        func_name = func.__name__

        # 冲突检测：同一名称重复注册
        if name in _tool_meta:
            raise ValueError(
                f"工具名称冲突：'{name}' 已被 {_tool_meta[name]['func'].__name__} 注册，"
                f"新注册 func={func_name}"
            )

        _tool_meta[name] = {
            "name": name,
            "persona": persona,
            "call_limit": call_limit,
            "requires_approval": requires_approval,
            "prerequisites": prerequisites or [],
            "description": description,
            "func": func,
        }
        _registered_func_names.add(func_name)
        return func

    return decorator


def get_tools_for_persona(persona: str) -> list[dict]:
    """获取指定角色的可用工具列表（含函数引用）。

    Args:
        persona: 角色名（student / teacher / tutor / parent）

    Returns:
        按注册顺序排列的工具元数据列表
    """
    return [
        meta for meta in _tool_meta.values()
        if persona in meta["persona"]
    ]


def get_tool_names_for_persona(persona: str) -> list[str]:
    """获取指定角色的可用工具名称列表。"""
    return [meta["name"] for meta in get_tools_for_persona(persona)]


def get_all_tools() -> dict[str, dict]:
    """获取所有已注册工具。"""
    return dict(_tool_meta)


def get_tool_meta(name: str) -> Optional[dict]:
    """获取单个工具的完整元数据。

    Args:
        name: 工具名称

    Returns:
        工具元数据字典，不存在返回 None
    """
    return _tool_meta.get(name)


def validate_tool_integrity() -> list[str]:
    """编译时完整性验证。

    检查：
    1. TOOL_META 中每个 func 字段指向的函数确实存在
    2. 被 @register_tool 装饰的函数都有元数据条目

    Returns:
        错误信息列表（空列表表示验证通过）
    """
    errors = []

    for name, meta in _tool_meta.items():
        func = meta.get("func")
        if func is None:
            errors.append(f"工具 '{name}' 缺少 func 引用")
        elif not callable(func):
            errors.append(f"工具 '{name}' 的 func 不可调用: {func}")

        # 校验 call_limit >= 0
        if meta.get("call_limit", 0) < 0:
            errors.append(f"工具 '{name}' 的 call_limit 不能为负数: {meta['call_limit']}")

        # 校验 persona 非空
        if not meta.get("persona"):
            errors.append(f"工具 '{name}' 的 persona 列表为空")

    return errors
