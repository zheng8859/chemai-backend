"""学生消息通知模型：Notification。

教师操作（布置练习、发送学习计划）时自动触发通知写入。
学生端拉取通知列表，30 天后自动清理。
"""

from datetime import datetime
from typing import Optional, TYPE_CHECKING

from sqlalchemy import String, Integer, DateTime, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin

if TYPE_CHECKING:
    from .user import Student


class Notification(Base, TimestampMixin):
    """学生消息通知 — 教师操作时自动触发，非手动发送。

    通知类型（type）：
    - practice_assigned: 教师布置新练习
    - plan_updated: 教师更新学习计划
    - report_ready: 学习报告已生成（保留扩展）

    写入策略：best-effort，失败不阻塞父操作。
    保留策略：30 天，过期可清理。
    """

    __tablename__ = "notification"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    student_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("student.id", ondelete="CASCADE"), nullable=False, comment="接收学生"
    )
    type: Mapped[str] = mapped_column(
        String(30), nullable=False, comment="通知类型：practice_assigned / plan_updated / report_ready"
    )
    title: Mapped[str] = mapped_column(
        String(200), nullable=False, comment="通知标题"
    )
    body: Mapped[str] = mapped_column(
        Text, nullable=False, comment="通知正文"
    )
    related_id: Mapped[Optional[int]] = mapped_column(
        Integer, comment="关联资源 ID（如 practice_id / plan_id）"
    )
    read_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), comment="已读时间"
    )

    # ── 关联关系 ──
    student: Mapped["Student"] = relationship(back_populates="notifications")

    def __repr__(self) -> str:
        return f"<Notification id={self.id} student_id={self.student_id} type={self.type}>"
