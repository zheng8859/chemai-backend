"""家校互通模型：StudentParentBinding, ParentNotification。

支撑功能（34号 §四）：
- 家长通过 6 位绑定码与学生建立亲子关联
- 绑定后接收通知和报告
- 遵循"最小可见"隐私原则（23号 §四.2）
"""

from datetime import datetime
from typing import Optional, List, TYPE_CHECKING

from sqlalchemy import String, Integer, ForeignKey, Boolean, DateTime, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..core.enums import ParentRelation, BindingStatus, NotificationType
from .base import Base, TimestampMixin

if TYPE_CHECKING:
    from .user import Student, Parent


class StudentParentBinding(Base, TimestampMixin):
    """亲子绑定 — 通过 6 位绑定码建立学生与家长的关联（34号 §四）。

    绑定流程（23号 §四.3）：
    1. 学生在客户端生成 6 位绑定码 → Student.bind_code
    2. 家长提交 student_id + bind_code → 系统验证
    3. 验证通过 → 创建 binding 记录（status=active）
    """

    __tablename__ = "student_parent_binding"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    student_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("student.id", ondelete="CASCADE"), nullable=False, comment="学生"
    )
    parent_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("parent.id", ondelete="CASCADE"), nullable=False, comment="家长"
    )
    status: Mapped[BindingStatus] = mapped_column(
        String(20), default=BindingStatus.active,
        server_default="'active'", nullable=False,
        comment="绑定状态：active / inactive",
    )
    relation: Mapped[ParentRelation] = mapped_column(
        "relationship",
        String(20), default=ParentRelation.other,
        server_default="'other'", nullable=False,
        comment="亲子关系：father / mother / other",
    )

    # ── 关联关系 ──
    student: Mapped["Student"] = relationship(back_populates="parent_bindings")
    parent: Mapped["Parent"] = relationship(back_populates="child_bindings")

    __table_args__ = (
        UniqueConstraint("student_id", "parent_id", name="uq_binding_student_parent"),
    )

    def __repr__(self) -> str:
        return f"<StudentParentBinding student_id={self.student_id} parent_id={self.parent_id}>"


class ParentNotification(Base, TimestampMixin):
    """家长通知 — 系统推送给家长的消息（33号 §九, 34号 §四）。

    通知类型：weekly_report / score_alert / learning_plan / reminder / daily_report。
    家长端 API 前置验证绑定关系 status=active。
    保留策略：90 天。
    """

    __tablename__ = "parent_notification"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    parent_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("parent.id", ondelete="CASCADE"), nullable=False, comment="家长"
    )
    notification_type: Mapped[NotificationType] = mapped_column(
        String(30), nullable=False, comment="通知类型"
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False, comment="通知标题")
    body: Mapped[str] = mapped_column(Text, nullable=False, comment="通知正文")
    related_id: Mapped[Optional[int]] = mapped_column(
        Integer, comment="关联资源 ID（如 weekly_report_id / warning_log_id）"
    )
    read_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), comment="已读时间"
    )
    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=datetime.utcnow, comment="发送时间"
    )

    # ── 关系 ──
    parent: Mapped["Parent"] = relationship(back_populates="notifications")

    def __repr__(self) -> str:
        return f"<ParentNotification id={self.id} parent_id={self.parent_id} type={self.notification_type}>"


class WeeklyReport(Base, TimestampMixin):
    """家长周报 — LLM 生成的缓存报告（33号 §七）。

    同一学生同一周只生成一份（UniqueConstraint）。
    分为 auto（Cron 自动）和 manual（家长手动）两种生成方式。
    """

    __tablename__ = "weekly_report"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    student_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("student.id", ondelete="CASCADE"), nullable=False, comment="学生"
    )
    week_start: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, comment="本周一日期"
    )
    week_end: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, comment="本周日日期"
    )
    summary: Mapped[str] = mapped_column(
        String(200), nullable=False, comment="概述段（≤60字）"
    )
    detail: Mapped[str] = mapped_column(
        Text, nullable=False, comment="具体表现段（≤120字）"
    )
    advice: Mapped[str] = mapped_column(
        Text, nullable=False, comment="家庭建议段（≤80字）"
    )
    no_data: Mapped[bool] = mapped_column(
        default=False, server_default="0", comment="当周无数据时为 True"
    )
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=datetime.utcnow, comment="生成时间"
    )
    generated_by: Mapped[str] = mapped_column(
        String(20), nullable=False, comment="生成方式：auto / manual"
    )

    # ── 唯一约束 ──
    __table_args__ = (
        UniqueConstraint("student_id", "week_start", name="uq_weekly_report_student_week"),
    )

    def __repr__(self) -> str:
        return (
            f"<WeeklyReport id={self.id} student_id={self.student_id} "
            f"week={self.week_start} generated_by={self.generated_by}>"
        )
