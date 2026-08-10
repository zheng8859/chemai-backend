"""障碍画像历史快照 — 追踪学生障碍画像变化，用于 new_barrier 预警检测基线对比。"""

from datetime import datetime
from typing import Optional

from sqlalchemy import Integer, String, DateTime, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class BarrierProfileHistory(Base):
    """学生障碍画像的历史快照。

    每次预警检测后写入当前障碍画像快照，用于下次检测时计算主导障碍
    归一化得分变化幅度（≥ 30% 触发 new_barrier 预警）。

    字段：
    - student_id: 学生 ID
    - snapshot_at: 快照时间
    - profile: 三维分布 JSON，如 {"concept": 0.40, "reading": 0.30, "expression": 0.30}
    - dominant_barrier: 主导障碍类型字符串（concept / reading / expression）
    """

    __tablename__ = "barrier_profile_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    student_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("student.id", ondelete="CASCADE"), nullable=False,
        comment="学生 ID",
    )
    snapshot_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow,
        comment="快照时间",
    )
    profile: Mapped[dict] = mapped_column(
        JSON, nullable=False, comment="三维障碍分布 JSON"
    )
    dominant_barrier: Mapped[Optional[str]] = mapped_column(
        String(20), comment="主导障碍类型：concept / reading / expression"
    )
    max_raw: Mapped[Optional[dict]] = mapped_column(
        JSON, nullable=True,
        comment="快照时班级各障碍类型最大原始值，用于归一化基线对比",
    )

    def __repr__(self) -> str:
        return (
            f"<BarrierProfileHistory id={self.id} student_id={self.student_id}"
            f" dominant={self.dominant_barrier}>"
        )
