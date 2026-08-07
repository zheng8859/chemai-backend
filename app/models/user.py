"""身份链模型：Account → Teacher / Student / Parent — 统一凭证 + 三类 Profile。

设计决策（从 34号 + 23号 调和）：
- Account 是统一凭证表，Teacher/Student/Parent 各自持有 account_id FK（翻转方向）
- 凭证统一，认证通道分离：Parent 走独立登录端点，JWT 不携带 school_id
- Teacher.role 是子角色枚举（admin/教务管理员/学科组长/teacher），区别于 Account.role
"""

from datetime import datetime
from typing import Optional, List, TYPE_CHECKING

from sqlalchemy import String, Integer, Float, DateTime, ForeignKey, UniqueConstraint, JSON, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..core.enums import (
    AccountRole,
    TeacherRole,
    TeacherAccountStatus,
    StudentStatus,
    ParentRelation,
    ApplicationStatus,
)
from .base import Base, TimestampMixin

if TYPE_CHECKING:
    from .org import School, Class
    from .teaching import StudentAnswer
    from .diagnosis import ReviewTask, WarningLog, BarrierConfig, KnowledgePoint
    from .homework import StudentParentBinding
    from .ocr import StudentSubmission, UploadSession
    from .question_bank import QuestionSet
    from .agent_memory import LongTermMemory


class Account(Base, TimestampMixin):
    """统一账户 — 所有用户的登录凭证。

    关系方向说明：
    - 文档 34 原设计：Account 持有 role_id → 多态 FK
    - 实现选择：Teacher/Student/Parent 各自持有 account_id → Account (翻转)
    - 原因：SQLAlchemy 原生支持，无需多态 FK 魔法
    """

    __tablename__ = "account"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    phone: Mapped[str] = mapped_column(
        String(20), unique=True, nullable=False, index=True, comment="全局唯一手机号（登录凭据）"
    )
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False, comment="加密密码")
    role: Mapped[AccountRole] = mapped_column(
        SAEnum(AccountRole, native_enum=False, length=20),
        nullable=False,
        comment="账户角色：teacher / student / parent",
    )

    # ── 关系（one-to-one，子表持有 FK） ──
    teacher_profile: Mapped[Optional["Teacher"]] = relationship(back_populates="account", uselist=False)
    student_profile: Mapped[Optional["Student"]] = relationship(back_populates="account", uselist=False)
    parent_profile: Mapped[Optional["Parent"]] = relationship(back_populates="account", uselist=False)

    def __repr__(self) -> str:
        return f"<Account id={self.id} phone='{self.phone}' role={self.role}>"


class Teacher(Base, TimestampMixin):
    """教师 Profile — 归属学校，含子角色和账号状态。

    Account.role = "teacher" → Teacher.role = 子角色（admin/教务管理员/学科组长/teacher）
    """

    __tablename__ = "teacher"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("account.id", ondelete="CASCADE"), unique=True, nullable=False, comment="关联账户"
    )
    school_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("school.id", ondelete="CASCADE"), nullable=False, comment="所属学校"
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False, comment="教师姓名")
    status: Mapped[TeacherAccountStatus] = mapped_column(
        String(20), default=TeacherAccountStatus.pending,
        server_default="'pending'", nullable=False,
        comment="账号状态：pending / approved / rejected",
    )
    role: Mapped[TeacherRole] = mapped_column(
        String(30), default=TeacherRole.teacher,
        server_default="'teacher'", nullable=False,
        comment="教师子角色：system_admin / academic_admin / subject_lead / teacher",
    )

    # ── 关系 ──
    account: Mapped["Account"] = relationship(back_populates="teacher_profile")
    school: Mapped["School"] = relationship(back_populates="teachers")
    teacher_class_subjects: Mapped[List["TeacherClassSubject"]] = relationship(back_populates="teacher")
    barrier_config: Mapped[Optional["BarrierConfig"]] = relationship(back_populates="teacher", uselist=False)
    question_sets: Mapped[List["QuestionSet"]] = relationship(back_populates="teacher")
    upload_sessions: Mapped[List["UploadSession"]] = relationship(back_populates="teacher")

    def __repr__(self) -> str:
        return f"<Teacher id={self.id} name='{self.name}' role={self.role}>"


class Student(Base, TimestampMixin):
    """学生 Profile — 核心实体，归属班级，携带障碍画像和练习追踪。

    默认创建即通过（StudentStatus.approved），遵循 23号 §六 轻量审批设计。
    """

    __tablename__ = "student"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("account.id", ondelete="CASCADE"), unique=True, nullable=False, comment="关联账户"
    )
    class_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("class.id", ondelete="CASCADE"), nullable=False, comment="所属班级"
    )
    school_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("school.id", ondelete="CASCADE"), nullable=False, comment="所属学校（冗余，加速数据隔离查询）"
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False, comment="学生姓名")
    student_id: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="学号，与 school_id 组合全局唯一"
    )
    is_activated: Mapped[bool] = mapped_column(
        default=False, server_default="0", nullable=False, comment="是否已激活（首次登录后置 True）"
    )
    status: Mapped[StudentStatus] = mapped_column(
        String(20), default=StudentStatus.approved,
        server_default="'approved'", nullable=False,
        comment="账号状态：pending / approved / rejected",
    )
    barrier_profile: Mapped[Optional[dict]] = mapped_column(
        JSON, comment="障碍画像 JSON：{concept, reading, expression} 占比和=1"
    )
    barrier_profile_updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), comment="障碍画像最后更新时间"
    )
    weak_knowledge_points: Mapped[Optional[list]] = mapped_column(
        JSON, comment="薄弱知识点列表，如 ['氧化还原反应', '离子反应']"
    )
    practice_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", comment="累计完成练习数"
    )
    last_practice_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), comment="最近练习时间"
    )
    bind_code: Mapped[Optional[str]] = mapped_column(
        String(6), unique=True, comment="6 位家长绑定码"
    )

    # ── 关系 ──
    account: Mapped["Account"] = relationship(back_populates="student_profile")
    class_: Mapped["Class"] = relationship(back_populates="students")
    answers: Mapped[List["StudentAnswer"]] = relationship(back_populates="student")
    review_tasks: Mapped[List["ReviewTask"]] = relationship(back_populates="student")
    warning_logs: Mapped[List["WarningLog"]] = relationship(back_populates="student")
    parent_bindings: Mapped[List["StudentParentBinding"]] = relationship(back_populates="student")
    submissions: Mapped[List["StudentSubmission"]] = relationship(back_populates="student")
    long_term_memories: Mapped[List["LongTermMemory"]] = relationship(
        "LongTermMemory", foreign_keys="LongTermMemory.student_id", back_populates="student"
    )

    def __repr__(self) -> str:
        return f"<Student id={self.id} name='{self.name}' class_id={self.class_id}>"

    __table_args__ = (
        UniqueConstraint("school_id", "student_id", name="uq_student_school_student_id"),
    )


class Parent(Base, TimestampMixin):
    """家长 Profile — 独立实体，无学校归属。

    统一认证（45-数据模型与认证体系）：
    - 所有角色统一 POST /api/auth/login（phone + password）
    - JWT payload 不携带 school_id
    """

    __tablename__ = "parent"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("account.id", ondelete="CASCADE"), unique=True, nullable=False, comment="关联账户"
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False, comment="家长姓名")
    email: Mapped[Optional[str]] = mapped_column(String(200), comment="电子邮箱")

    # ── 关系 ──
    account: Mapped["Account"] = relationship(back_populates="parent_profile")
    child_bindings: Mapped[List["StudentParentBinding"]] = relationship(back_populates="parent")
    notifications: Mapped[List["ParentNotification"]] = relationship(back_populates="parent")

    def __repr__(self) -> str:
        return f"<Parent id={self.id} name='{self.name}'>"


class TeacherClassSubject(Base, TimestampMixin):
    """教师 ↔ 班级 多对多任课关系。

    含附加字段：学科、是否为班主任。
    教师通过此表确定可访问的班级范围（数据隔离核心）。
    """

    __tablename__ = "teacher_class_subject"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    teacher_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("teacher.id", ondelete="CASCADE"), nullable=False, comment="教师"
    )
    class_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("class.id", ondelete="CASCADE"), nullable=False, comment="班级"
    )
    subject: Mapped[str] = mapped_column(
        String(50), default="化学", server_default="'化学'", comment="教授学科"
    )
    is_head_teacher: Mapped[bool] = mapped_column(
        default=False, server_default="0", comment="是否班主任"
    )

    # ── 关系 ──
    teacher: Mapped["Teacher"] = relationship(back_populates="teacher_class_subjects")
    class_: Mapped["Class"] = relationship(back_populates="teacher_class_subjects")

    __table_args__ = (
        UniqueConstraint("teacher_id", "class_id", name="uq_tcs_teacher_class"),
    )

    def __repr__(self) -> str:
        return f"<TeacherClassSubject teacher_id={self.teacher_id} class_id={self.class_id}>"


class TeacherApplication(Base, TimestampMixin):
    """教师入驻申请表 — 独立的审批流程实体（23号 §五）。"""

    __tablename__ = "teacher_application"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, comment="申请人姓名")
    phone: Mapped[str] = mapped_column(String(20), nullable=False, comment="手机号码（登录凭据）")
    password_hash: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="加密密码（审批通过后复制到 Account）"
    )
    school_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("school.id", ondelete="CASCADE"), nullable=False, comment="申请学校"
    )
    school_name: Mapped[str] = mapped_column(String(200), nullable=False, comment="学校名称（申请时保存，方便审批查看）")
    subject: Mapped[str] = mapped_column(
        String(50), default="化学", server_default="'化学'", comment="教授学科"
    )
    status: Mapped[ApplicationStatus] = mapped_column(
        String(20), default=ApplicationStatus.pending,
        server_default="'pending'", nullable=False,
        comment="审批状态：pending / approved / rejected",
    )
    reviewer_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("teacher.id", ondelete="SET NULL"), comment="审批人（admin）"
    )
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), comment="审批完成时间"
    )

    # ── 关系 ──
    reviewer: Mapped[Optional["Teacher"]] = relationship(foreign_keys=[reviewer_id])

    def __repr__(self) -> str:
        return f"<TeacherApplication id={self.id} name='{self.name}' status={self.status}>"
