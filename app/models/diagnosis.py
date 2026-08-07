"""诊断与学习模型：BarrierConfig, KnowledgePoint, ReviewTask, ReviewHistory, VariantQuestion, WarningLog。

支撑功能（34号 §三）：
- 教师自定义诊断阈值 → BarrierConfig
- 知识图谱节点 → KnowledgePoint
- 艾宾浩斯间隔复习 → ReviewTask + ReviewHistory
- 变式题隔离存储 → VariantQuestion
- 四类学情预警 → WarningLog
"""

from datetime import datetime
from typing import Optional, List, TYPE_CHECKING

from sqlalchemy import String, Integer, Float, Boolean, DateTime, ForeignKey, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..core.enums import (
    BarrierType,
    ReviewTaskStatus,
    WarningType,
    WarningSeverity,
)
from .base import Base, TimestampMixin

if TYPE_CHECKING:
    from .user import Teacher, Student
    from .teaching import Question


class BarrierConfig(Base, TimestampMixin):
    """障碍诊断配置 — 每位教师一套自定义阈值（34号 §三.1）。

    默认值来自文档：
    - concept_threshold=3, reading_threshold=2, expression_threshold=3, mastery_threshold=3
    - auto_sync_enabled=False（诊断结论需教师手动推送）
    """

    __tablename__ = "barrier_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    teacher_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("teacher.id", ondelete="CASCADE"), unique=True, nullable=False,
        comment="教师（一对一）",
    )
    concept_threshold: Mapped[int] = mapped_column(
        Integer, default=3, server_default="3", nullable=False,
        comment="概念理解型障碍触发阈值：同一知识点连续答错 N 次",
    )
    reading_threshold: Mapped[int] = mapped_column(
        Integer, default=2, server_default="2", nullable=False,
        comment="审题障碍型触发阈值",
    )
    expression_threshold: Mapped[int] = mapped_column(
        Integer, default=3, server_default="3", nullable=False,
        comment="表述障碍型触发阈值",
    )
    mastery_threshold: Mapped[int] = mapped_column(
        Integer, default=3, server_default="3", nullable=False,
        comment="掌握标准：同一知识点连续答对 N 次",
    )
    auto_sync_enabled: Mapped[bool] = mapped_column(
        default=False, server_default="0", nullable=False,
        comment="诊断结论是否自动推送给学生端",
    )

    # ── 关系 ──
    teacher: Mapped["Teacher"] = relationship(back_populates="barrier_config")

    def __repr__(self) -> str:
        return f"<BarrierConfig teacher_id={self.teacher_id}>"


class KnowledgePoint(Base, TimestampMixin):
    """知识图谱节点 — 每个化学知识点的统计信息（34号 §三.2）。

    dynamic_error_rate = 所有学生的答错次数 ÷ 作答次数，实时更新。
    """

    __tablename__ = "knowledge_point"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False, unique=True, comment="知识点名称")
    category: Mapped[Optional[str]] = mapped_column(String(200), comment="所属分类，如 电解质溶液")
    parent_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("knowledge_point.id", ondelete="SET NULL"),
        comment="父知识点 ID（自引用，构建层级树）"
    )
    pubchem_id: Mapped[Optional[str]] = mapped_column(String(50), comment="关联 PubChem 化合物编号")
    question_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", comment="关联题目数"
    )
    dynamic_error_rate: Mapped[float] = mapped_column(
        Float, default=0.0, server_default="0.0", comment="动态错误率"
    )

    def __repr__(self) -> str:
        return f"<KnowledgePoint id={self.id} name='{self.name}'>"


class ReviewTask(Base, TimestampMixin):
    """间隔复习任务 — 每道错题自动创建，6 级螺旋递进。

    艾宾浩斯复习节奏（0-5 级）：
    Level 0: 初次学习 → 当天（趁热打铁）
    Level 1: 第 1 次复习 → 1 天后
    Level 2: 第 2 次复习 → 3 天后
    Level 3: 第 3 次复习 → 7 天后
    Level 4: 第 4 次复习 → 14 天后
    Level 5: 已掌握 → 不再安排复习
    status: pending → overdue（到期未完成）→ completed（已掌握）。
    """

    __tablename__ = "review_task"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    student_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("student.id", ondelete="CASCADE"), nullable=False, comment="学生"
    )
    question_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("question.id", ondelete="CASCADE"), nullable=False, comment="错题"
    )
    level: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False,
        comment="当前复习级别：0~4 递进，5=已掌握",
    )
    consecutive_correct: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False,
        comment="连续答对次数",
    )
    consecutive_wrong: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False,
        comment="连续答错次数",
    )
    status: Mapped[ReviewTaskStatus] = mapped_column(
        String(20), default=ReviewTaskStatus.pending,
        server_default="'pending'", nullable=False,
        comment="状态：pending / overdue / completed",
    )
    next_review_date: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), comment="下次复习日期"
    )

    # ── 关系 ──
    student: Mapped["Student"] = relationship(back_populates="review_tasks")
    question: Mapped["Question"] = relationship(back_populates="review_tasks")
    review_histories: Mapped[List["ReviewHistory"]] = relationship(back_populates="review_task")

    def __repr__(self) -> str:
        return f"<ReviewTask id={self.id} student_id={self.student_id} level={self.level}>"


class ReviewHistory(Base, TimestampMixin):
    """复习历史 — 追踪每次复习的结果，支撑遗忘曲线分析（34号 §三.3）。"""

    __tablename__ = "review_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    review_task_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("review_task.id", ondelete="CASCADE"), nullable=False, comment="所属复习任务"
    )
    level: Mapped[int] = mapped_column(Integer, nullable=False, comment="本次复习时的级别")
    review_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, comment="复习日期"
    )
    result: Mapped[bool] = mapped_column(nullable=False, comment="结果：True=答对，False=答错")

    # ── 关系 ──
    review_task: Mapped["ReviewTask"] = relationship(back_populates="review_histories")

    def __repr__(self) -> str:
        return f"<ReviewHistory id={self.id} task_id={self.review_task_id} result={self.result}>"


class VariantQuestion(Base, TimestampMixin):
    """变式题 — LLM 生成的错题变体，隔离存储不污染 Question 主表。

    设计要点：
    - 与原题同知识点、同难度，不同题面/数据/情境
    - 90 天过期后不再复用，需重新生成
    - 跨学生共享：同一原题的变式题可被不同学生复用
    - 不参与任何统计分析（错误率、难度校准、学情报表）
    """

    __tablename__ = "variant_question"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    original_question_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("question.id", ondelete="CASCADE"), nullable=False,
        comment="原题 ID",
    )
    content: Mapped[str] = mapped_column(Text, nullable=False, comment="题目正文")
    question_type: Mapped[str] = mapped_column(
        String(30), default="choice", server_default="'choice'", nullable=False,
        comment="题型",
    )
    options: Mapped[Optional[list]] = mapped_column(
        JSON, comment="选项列表 JSON，非选择题为 null"
    )
    answer: Mapped[str] = mapped_column(Text, nullable=False, comment="正确答案")
    analysis: Mapped[Optional[str]] = mapped_column(Text, comment="题目解析")
    knowledge_point_tags: Mapped[Optional[list]] = mapped_column(
        JSON, comment="知识点标签数组"
    )
    difficulty: Mapped[str] = mapped_column(
        String(20), default="medium", server_default="'medium'", nullable=False,
        comment="难度等级",
    )
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=datetime.utcnow, comment="生成时间",
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        comment="过期时间（默认 90 天后）",
    )

    # ── 关系 ──
    original_question: Mapped["Question"] = relationship(
        foreign_keys=[original_question_id],
    )

    def __repr__(self) -> str:
        return f"<VariantQuestion id={self.id} orig_q={self.original_question_id}>"


class WarningLog(Base, TimestampMixin):
    """学情预警 — 四类自动监控预警（34号 §三.4）。

    三端通知状态追踪，防止重复发送。
    """

    __tablename__ = "warning_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    student_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("student.id", ondelete="CASCADE"), nullable=False, comment="学生"
    )
    warning_type: Mapped[WarningType] = mapped_column(
        String(30), nullable=False, comment="预警类型"
    )
    severity: Mapped[WarningSeverity] = mapped_column(
        String(20), nullable=False, comment="严重级别：info / warning / severe"
    )
    message: Mapped[str] = mapped_column(Text, nullable=False, comment="预警消息文本")
    notified_teacher: Mapped[bool] = mapped_column(
        default=False, server_default="0", comment="是否已通知教师"
    )
    notified_parent: Mapped[bool] = mapped_column(
        default=False, server_default="0", comment="是否已通知家长"
    )
    notified_student: Mapped[bool] = mapped_column(
        default=False, server_default="0", comment="是否已通知学生本人"
    )

    # ── 关系 ──
    student: Mapped["Student"] = relationship(back_populates="warning_logs")

    def __repr__(self) -> str:
        return f"<WarningLog id={self.id} type={self.warning_type} severity={self.severity}>"
