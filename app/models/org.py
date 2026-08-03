"""组织链模型：School → Grade → Class — 多租户隔离的骨骼。

数据隔离规则（34号 §十）：
- 班级是隔离的核心边界
- 同校教师只能看到本校数据
- 所有查询沿 School → Grade → Class 链向下展开
"""

from typing import Optional, List, TYPE_CHECKING

from sqlalchemy import String, Integer, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin

if TYPE_CHECKING:
    from .user import Teacher


class School(Base, TimestampMixin):
    """学校 — 顶层组织容器，多租户根节点。"""

    __tablename__ = "school"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False, comment="学校全称")
    region: Mapped[Optional[str]] = mapped_column(String(100), comment="所在地区")
    address: Mapped[Optional[str]] = mapped_column(String(500), comment="详细地址")
    phone: Mapped[Optional[str]] = mapped_column(String(30), comment="联系电话")
    current_semester: Mapped[Optional[str]] = mapped_column(String(50), comment="当前学期，如 2026春")

    # ── 关系 ──
    grades: Mapped[List["Grade"]] = relationship(back_populates="school")
    teachers: Mapped[List["Teacher"]] = relationship(back_populates="school")

    def __repr__(self) -> str:
        return f"<School id={self.id} name='{self.name}'>"


class Grade(Base, TimestampMixin):
    """年级 — 学校下的第二层组织。"""

    __tablename__ = "grade"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    school_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("school.id", ondelete="CASCADE"), nullable=False, comment="所属学校"
    )
    name: Mapped[str] = mapped_column(String(50), nullable=False, comment="年级名称，如 高一/高二/高三")
    academic_year: Mapped[Optional[str]] = mapped_column(String(20), comment="学年，如 2025-2026")

    # ── 关系 ──
    school: Mapped["School"] = relationship(back_populates="grades")
    classes: Mapped[List["Class"]] = relationship(back_populates="grade")

    __table_args__ = (
        UniqueConstraint("school_id", "name", name="uq_grade_school_name"),
    )

    def __repr__(self) -> str:
        return f"<Grade id={self.id} name='{self.name}' school_id={self.school_id}>"


class Class(Base, TimestampMixin):
    """班级 — 最小组织单元，数据隔离的核心边界。"""

    __tablename__ = "class"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    grade_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("grade.id", ondelete="CASCADE"), nullable=False, comment="所属年级"
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False, comment="班级名称，如 高一(3)班")
    student_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0", comment="当前学生人数")
    stage: Mapped[Optional[str]] = mapped_column(String(20), comment="学段：高中/初中")
    subject: Mapped[str] = mapped_column(
        String(50), default="化学", server_default="'化学'", comment="学科（本平台聚焦化学）"
    )

    # ── 关系 ──
    grade: Mapped["Grade"] = relationship(back_populates="classes")
    students: Mapped[List["Student"]] = relationship(back_populates="class_")
    exam_records: Mapped[List["ExamRecord"]] = relationship(back_populates="class_")
    teacher_class_subjects: Mapped[List["TeacherClassSubject"]] = relationship(back_populates="class_")

    __table_args__ = (
        UniqueConstraint("grade_id", "name", name="uq_class_grade_name"),
    )

    def __repr__(self) -> str:
        return f"<Class id={self.id} name='{self.name}' grade_id={self.grade_id}>"
