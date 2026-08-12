"""学习计划模型：LearningPlan + LearningPlanTask。

教师通过 Agent 为学生创建结构化学习计划，学生端只读 + 标记任务完成。
一个学生同时只有一份活跃计划（is_active=true），新计划创建时旧计划自动归档。
"""

from datetime import datetime
from typing import Optional, List, TYPE_CHECKING

from sqlalchemy import String, Integer, Boolean, DateTime, ForeignKey, JSON, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin

if TYPE_CHECKING:
    from .user import Student


class LearningPlan(Base, TimestampMixin):
    """学习计划 — 教师通过 Agent 生成，一份计划含多天的任务列表。

    创建新计划时，该学生旧的 is_active=true 计划自动设为 false。
    计划标题（title）由教师或 Agent 设定。
    """

    __tablename__ = "learning_plan"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    student_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("student.id", ondelete="CASCADE"), nullable=False, comment="学生"
    )
    title: Mapped[str] = mapped_column(
        String(200), nullable=False, comment="计划标题"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="1", comment="是否为当前活跃计划"
    )
    created_by: Mapped[Optional[str]] = mapped_column(
        String(50), default="teacher", comment="创建来源：teacher / agent"
    )

    # ── 关联关系 ──
    student: Mapped["Student"] = relationship(back_populates="learning_plans")
    tasks: Mapped[List["LearningPlanTask"]] = relationship(
        back_populates="plan", cascade="all, delete-orphan",
        order_by="LearningPlanTask.day_number, LearningPlanTask.id",
    )

    def __repr__(self) -> str:
        return f"<LearningPlan id={self.id} student_id={self.student_id} active={self.is_active}>"


class LearningPlanTask(Base, TimestampMixin):
    """学习计划任务 — 某一天的一项具体学习任务。

    status 枚举：pending（待做）、completed（已完成）、skipped（已跳过）。
    """

    __tablename__ = "learning_plan_task"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plan_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("learning_plan.id", ondelete="CASCADE"), nullable=False, comment="所属计划"
    )
    day_number: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="第几天（从 1 开始）"
    )
    task_description: Mapped[str] = mapped_column(
        Text, nullable=False, comment="任务描述"
    )
    estimated_minutes: Mapped[int] = mapped_column(
        Integer, default=30, comment="预估完成时间（分钟）"
    )
    knowledge_points: Mapped[Optional[list]] = mapped_column(
        JSON, comment="关联知识点标签数组"
    )
    status: Mapped[str] = mapped_column(
        String(20), default="pending", server_default="'pending'",
        comment="任务状态：pending / completed / skipped"
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), comment="完成时间"
    )

    # ── 关联关系 ──
    plan: Mapped["LearningPlan"] = relationship(back_populates="tasks")

    def __repr__(self) -> str:
        return f"<LearningPlanTask id={self.id} day={self.day_number} status={self.status}>"
