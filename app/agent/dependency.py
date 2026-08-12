"""依赖注入容器 — AgentContext。

AgentContext 作为请求级上下文，在 Agent 创建时注入到工具函数中。
工具函数可通过 get_current_context() 访问 student_id、persona、provider。

用法：
    from app.agent.dependency import AgentContext, set_current_context

    ctx = AgentContext(
        student_id=123,
        student_profile=profile_dict,
        persona="teacher",
        provider_name="qwen",
    )
    set_current_context(ctx)

    # 工具函数中
    ctx = get_current_context()
    if ctx and ctx.student_id:
        ...
"""

import contextvars
from dataclasses import dataclass, field
from typing import Optional

# ── ContextVar（线程安全 + 协程安全） ──
_current_context: contextvars.ContextVar[Optional["AgentContext"]] = \
    contextvars.ContextVar("agent_context", default=None)


@dataclass
class AgentContext:
    """Agent 请求级上下文。

    Attributes:
        student_id: 当前学生 ID（Student/Parent persona 时有效）
        student_profile: 学生障碍画像 + 学习计划
        persona: 当前角色
        episodic: 情景记忆（请求内临时存储，如诊断结果）
        provider_name: 当前使用的 LLM Provider
        teacher_id: 教师 ID（Teacher persona 时有效）
    """

    student_id: Optional[int] = None
    student_profile: Optional[dict] = None
    persona: str = "student"
    episodic: dict = field(default_factory=dict)
    provider_name: str = "qwen"
    teacher_id: Optional[int] = None


def set_current_context(ctx: AgentContext) -> None:
    """设置当前请求的 AgentContext。"""
    _current_context.set(ctx)


def get_current_context() -> Optional[AgentContext]:
    """获取当前请求的 AgentContext。"""
    return _current_context.get(None)


def clear_current_context() -> None:
    """清除当前请求的 AgentContext。"""
    _current_context.set(None)
