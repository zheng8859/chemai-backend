"""试卷模型：ExamPaper → ExamPaperQuestion → Question — 试卷模板与考试执行的双层模型。

考试生命周期（45-数据模型与认证体系 §四）：
- ExamPaper（模板）：draft → published → archived — 可复用、可版本化的试卷定义
- ExamRecord（实例）：pending → in_progress → grading → completed → archived (+cancelled)
"""

from typing import Optional, List, TYPE_CHECKING

from sqlalchemy import String, Integer, Float, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..core.enums import ExamPaperStatus, ExamRecordStatus
from .base import Base, TimestampMixin

if TYPE_CHECKING:
    from .user import Teacher
    from .teaching import Question, ExamRecord
    from .org import Class


class ExamPaper(Base, TimestampMixin):
    """试卷模板 — 一套完整考试题目的可复用定义。

    status: draft（编辑中）→ published（可被布置）→ archived（不再使用）
    """

    __tablename__ = "exam_paper"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False, comment="试卷名称")
    total_score: Mapped[int] = mapped_column(
        Integer, default=100, server_default="100", comment="试卷总分"
    )
    duration_minutes: Mapped[int] = mapped_column(
        Integer, default=60, server_default="60", comment="考试时限（分钟）"
    )
    status: Mapped[ExamPaperStatus] = mapped_column(
        String(20), default=ExamPaperStatus.draft,
        server_default="'draft'", nullable=False,
        comment="状态：draft / published / archived",
    )
    teacher_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("teacher.id", ondelete="CASCADE"), nullable=False, comment="创建教师"
    )

    # ── 关系 ──
    teacher: Mapped["Teacher"] = relationship()
    questions: Mapped[List["ExamPaperQuestion"]] = relationship(back_populates="exam_paper")
    exam_records: Mapped[List["ExamRecord"]] = relationship(back_populates="exam_paper")

    def __repr__(self) -> str:
        return f"<ExamPaper id={self.id} name='{self.name}' status={self.status}>"


class ExamPaperQuestion(Base, TimestampMixin):
    """试卷↔题目多对多关联 — 含排序和该题在此试卷中的分值。

    同一道题在不同试卷中可设置不同分值（如计算题在期中卷值5分，在期末卷值10分）。
    """

    __tablename__ = "exam_paper_question"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    exam_paper_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("exam_paper.id", ondelete="CASCADE"), nullable=False, comment="试卷"
    )
    question_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("question.id", ondelete="CASCADE"), nullable=False, comment="题目"
    )
    sort_order: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", comment="排序序号"
    )
    score: Mapped[float] = mapped_column(
        Float, default=0.0, server_default="0.0", nullable=False,
        comment="该题在此试卷中的分值"
    )

    # ── 关系 ──
    exam_paper: Mapped["ExamPaper"] = relationship(back_populates="questions")
    question: Mapped["Question"] = relationship()

    __table_args__ = (
        UniqueConstraint("exam_paper_id", "question_id", name="uq_epq_paper_question"),
    )

    def __repr__(self) -> str:
        return f"<ExamPaperQuestion paper_id={self.exam_paper_id} q_id={self.question_id}>"
