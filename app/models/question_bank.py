"""题库模型：QuestionSet, QuestionSetItem, HistoricalExam。

支撑功能（34号 §六）：
- QuestionSet：教师创建的题库文件夹（按知识点/考试分类）
- QuestionSetItem：题库↔题目多对多中间实体（含排序）
- HistoricalExam：历年高考真题库（RAG 知识底座）
"""

from typing import Optional, List, TYPE_CHECKING

from sqlalchemy import String, Integer, Float, ForeignKey, JSON, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..core.enums import Difficulty
from .base import Base, TimestampMixin

if TYPE_CHECKING:
    from .user import Teacher
    from .teaching import Question


class QuestionSet(Base, TimestampMixin):
    """题库文件夹 — 教师创建的自定义题目集合（34号 §六.1）。"""

    __tablename__ = "question_set"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    teacher_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("teacher.id", ondelete="CASCADE"), nullable=False, comment="创建教师"
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False, comment="文件夹名称")
    description: Mapped[Optional[str]] = mapped_column(Text, comment="描述")

    # ── 关系 ──
    teacher: Mapped["Teacher"] = relationship(back_populates="question_sets")
    items: Mapped[List["QuestionSetItem"]] = relationship(back_populates="question_set")

    def __repr__(self) -> str:
        return f"<QuestionSet id={self.id} name='{self.name}'>"


class QuestionSetItem(Base, TimestampMixin):
    """题库文件夹与题目的多对多关联 — 含排序字段（34号 §六.2）。"""

    __tablename__ = "question_set_item"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    question_set_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("question_set.id", ondelete="CASCADE"), nullable=False, comment="题库文件夹"
    )
    question_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("question.id", ondelete="CASCADE"), nullable=False, comment="题目"
    )
    sort_order: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", comment="排序序号"
    )

    # ── 关系 ──
    question_set: Mapped["QuestionSet"] = relationship(back_populates="items")
    question: Mapped["Question"] = relationship(back_populates="question_set_items")

    __table_args__ = (
        UniqueConstraint("question_set_id", "question_id", name="uq_qsi_set_question"),
    )

    def __repr__(self) -> str:
        return f"<QuestionSetItem set_id={self.question_set_id} q_id={self.question_id}>"


class HistoricalExam(Base, TimestampMixin):
    """历年真题 — 系统预置的高考真题库，RAG 检索增强生成的知识底座（34号 §六.3）。

    数据范围：全国卷(2008-2020, ~143题) + 湖南卷(2021-2025, ~107题)。
    discrimination（区分度）：衡量题目区分优生和差生能力的统计指标。
    """

    __tablename__ = "historical_exam"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="试卷来源，如 全国卷/湖南卷"
    )
    year: Mapped[int] = mapped_column(Integer, nullable=False, comment="年份")
    question_number: Mapped[Optional[str]] = mapped_column(String(20), comment="题号")
    knowledge_point_tags: Mapped[Optional[list]] = mapped_column(
        JSON, comment="知识点标签数组"
    )
    difficulty: Mapped[Difficulty] = mapped_column(
        String(20), default=Difficulty.medium,
        server_default="'medium'", nullable=False, comment="难度"
    )
    discrimination: Mapped[Optional[float]] = mapped_column(
        Float, comment="区分度（统计指标）"
    )
    content: Mapped[str] = mapped_column(Text, nullable=False, comment="题目正文")
    answer: Mapped[str] = mapped_column(Text, nullable=False, comment="答案")
    analysis: Mapped[Optional[str]] = mapped_column(Text, comment="解析")

    def __repr__(self) -> str:
        return f"<HistoricalExam id={self.id} source='{self.source}' year={self.year}>"
