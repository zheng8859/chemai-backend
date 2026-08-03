"""教学链模型：ExamRecord → Question → StudentAnswer — 考试→诊断→练习的数据底座。

核心查询路径（34号 §一）：
- 考试 → 题目 → 学生作答：支撑错题诊断、学情分析、自适应练习
- 每条 StudentAnswer 携带障碍类型标签，由诊断引擎异步填充
"""

from datetime import datetime
from typing import Optional, List, TYPE_CHECKING

from sqlalchemy import String, Integer, Float, DateTime, ForeignKey, Boolean, JSON, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..core.enums import (
    ExamType,
    Difficulty,
    QuestionSource,
    AuditStatus,
    BarrierType,
    MisconceptionCategory,
    QuestionType,
    DiagnosisSource,
    ExamRecordStatus,
    PracticeSessionStatus,
)
from .base import Base, TimestampMixin

if TYPE_CHECKING:
    from .org import Class
    from .user import Student


class PracticeSession(Base, TimestampMixin):
    """自适应练习会话 — 一次针对特定障碍类型的练习。

    barrier_type 决定本次练习的策略（barrier→question 矩阵），
    knowledge_point_tags 记录覆盖的知识点范围。
    """

    __tablename__ = "practice_session"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    student_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("student.id", ondelete="CASCADE"), nullable=False, comment="学生"
    )
    barrier_type: Mapped[BarrierType] = mapped_column(
        String(20), nullable=False, comment="本次练习针对的障碍类型"
    )
    knowledge_point_tags: Mapped[Optional[list]] = mapped_column(
        JSON, comment="覆盖的知识点标签数组"
    )
    questions_served: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", comment="推送题目数"
    )
    questions_correct: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", comment="答对题目数"
    )
    status: Mapped[PracticeSessionStatus] = mapped_column(
        String(20), default=PracticeSessionStatus.in_progress,
        server_default="'in_progress'", nullable=False,
        comment="状态：in_progress / completed / abandoned",
    )

    # ── 关系 ──
    student: Mapped["Student"] = relationship()

    def __repr__(self) -> str:
        return f"<PracticeSession id={self.id} student_id={self.student_id}>"


class ExamRecord(Base, TimestampMixin):
    """考试记录 — 一次考试/练习/作业的完整记录。

    归属于某个班级，包含错题统计 JSON（§九.2）。
    """

    __tablename__ = "exam_record"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    class_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("class.id", ondelete="CASCADE"), nullable=False, comment="所属班级"
    )
    exam_paper_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("exam_paper.id", ondelete="SET NULL"),
        comment="关联试卷模板（可为空，手动组卷场景）"
    )
    exam_type: Mapped[ExamType] = mapped_column(
        String(20), nullable=False, comment="考试类型：monthly / practice / homework"
    )
    status: Mapped[ExamRecordStatus] = mapped_column(
        String(20), default=ExamRecordStatus.pending,
        server_default="'pending'", nullable=False,
        comment="状态：pending / in_progress / grading / completed / archived / cancelled",
    )
    exam_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, comment="考试日期"
    )
    participant_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", comment="参考人数"
    )
    avg_score: Mapped[Optional[float]] = mapped_column(Float, comment="平均分")
    error_stats: Mapped[Optional[dict]] = mapped_column(
        JSON, comment="错题统计 JSON：逐题错误率 + 知识点排行 + 班级平均分"
    )
    name: Mapped[Optional[str]] = mapped_column(String(200), comment="考试名称，如 高一期末模拟考")

    # ── 关系 ──
    class_: Mapped["Class"] = relationship(back_populates="exam_records")
    exam_paper: Mapped[Optional["ExamPaper"]] = relationship(
        "ExamPaper", foreign_keys=[exam_paper_id], back_populates="exam_records"
    )
    student_answers: Mapped[List["StudentAnswer"]] = relationship(back_populates="exam_record")
    submissions: Mapped[List["StudentSubmission"]] = relationship(back_populates="exam_record")

    def __repr__(self) -> str:
        return f"<ExamRecord id={self.id} type={self.exam_type} class_id={self.class_id}>"


class Question(Base, TimestampMixin):
    """题目 — 一道完整的化学试题。

    核心字段：
    - options JSON：选择题为 [A, B, C, D]，非选择题为空数组
    - knowledge_point_tags JSON：知识点标签数组，如 ["氧化还原反应", "电化学"]
    - audit_report JSON：四维安全审核报告（§九.4）
    """

    __tablename__ = "question"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    content: Mapped[str] = mapped_column(Text, nullable=False, comment="题目正文")
    question_type: Mapped[QuestionType] = mapped_column(
        String(30), default=QuestionType.choice,
        server_default="'choice'", nullable=False,
        comment="题型：choice/fill_blank/calculation/equation_balancing/experiment_inquiry"
    )
    options: Mapped[Optional[list]] = mapped_column(
        JSON, comment="选项列表 JSON，非选择题为 null"
    )
    answer: Mapped[str] = mapped_column(Text, nullable=False, comment="正确答案")
    analysis: Mapped[Optional[str]] = mapped_column(Text, comment="题目解析")
    knowledge_point_tags: Mapped[Optional[list]] = mapped_column(
        JSON, comment="知识点标签数组"
    )
    difficulty: Mapped[Difficulty] = mapped_column(
        String(20), default=Difficulty.medium,
        server_default="'medium'", nullable=False,
        comment="难度：easy / medium / hard / competition"
    )
    source: Mapped[QuestionSource] = mapped_column(
        String(30), default=QuestionSource.manual,
        server_default="'manual'", nullable=False,
        comment="题目来源：ai_generated / manual / daily_practice / ocr_import"
    )
    audit_status: Mapped[AuditStatus] = mapped_column(
        String(20), default=AuditStatus.passed,
        server_default="'passed'", nullable=False,
        comment="审核状态：passed / warning / blocked"
    )
    audit_report: Mapped[Optional[dict]] = mapped_column(
        JSON, comment="审核报告 JSON：四维度 + 综合判定 + 审核耗时"
    )
    variant_of_question_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("question.id", ondelete="SET NULL"),
        comment="变体蓝本题 ID（自引用）"
    )
    variant_dimensions: Mapped[Optional[dict]] = mapped_column(
        JSON, comment="变体维度：{value, substance, stem, options, difficulty}"
    )

    # ── 关系 ──
    student_answers: Mapped[List["StudentAnswer"]] = relationship(back_populates="question")
    review_tasks: Mapped[List["ReviewTask"]] = relationship(back_populates="question")
    question_set_items: Mapped[List["QuestionSetItem"]] = relationship(back_populates="question")

    def __repr__(self) -> str:
        return f"<Question id={self.id} type={self.question_type} diff={self.difficulty}>"


class StudentAnswer(Base, TimestampMixin):
    """学生作答 — 学生对一道题的单次作答记录。

    诊断相关字段：
    - barrier_type：诊断引擎异步填充的障碍类型标签
    - consecutive_wrong_count / consecutive_correct_count：用于阈值判断
    """

    __tablename__ = "student_answer"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    student_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("student.id", ondelete="CASCADE"), nullable=False, comment="学生"
    )
    question_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("question.id", ondelete="CASCADE"), nullable=False, comment="题目"
    )
    exam_record_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("exam_record.id", ondelete="SET NULL"), nullable=True, comment="所属考试（练习作答时为 NULL）"
    )
    answer_content: Mapped[str] = mapped_column(Text, nullable=False, comment="学生作答内容")
    is_correct: Mapped[bool] = mapped_column(nullable=False, comment="是否正确")
    barrier_type: Mapped[Optional[BarrierType]] = mapped_column(
        String(20), comment="诊断引擎判定的障碍类型"
    )
    misconception_category: Mapped[Optional[MisconceptionCategory]] = mapped_column(
        String(30), comment="迷思概念类别（3×6 诊断矩阵第二维）"
    )
    diagnosed_by: Mapped[Optional[DiagnosisSource]] = mapped_column(
        String(20), comment="诊断来源：ai_rule / ai_llm / teacher"
    )
    diagnosis_overridden_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), comment="教师覆盖诊断的时间"
    )
    consecutive_wrong_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", comment="同一知识点连续错误次数"
    )
    consecutive_correct_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", comment="同一知识点连续正确次数"
    )

    # ── 关系 ──
    student: Mapped["Student"] = relationship(back_populates="answers")
    question: Mapped["Question"] = relationship(back_populates="student_answers")
    exam_record: Mapped["ExamRecord"] = relationship(back_populates="student_answers")

    def __repr__(self) -> str:
        return f"<StudentAnswer id={self.id} student_id={self.student_id} correct={self.is_correct}>"
