"""User profile schemas — Account, Teacher, Student, Parent, TeacherApplication.

Aligned with 35-API §1 (auth/user/teacher_application routers).
"""

from datetime import datetime
from pydantic import BaseModel, Field

from ..core.enums import (
    AccountRole,
    TeacherRole,
    TeacherAccountStatus,
    StudentStatus,
    ParentRelation,
    ApplicationStatus,
)
from .base import ORMBase


# ── Account ────────────────────────────────────────────────
class AccountRead(ORMBase):
    id: int
    username: str
    role: AccountRole
    created_at: datetime | None = None


# ── Teacher ────────────────────────────────────────────────
class TeacherRead(ORMBase):
    id: int
    account_id: int
    school_id: int
    name: str
    phone: str | None = None
    status: TeacherAccountStatus
    role: TeacherRole
    created_at: datetime | None = None


class TeacherUpdate(BaseModel):
    name: str | None = None
    phone: str | None = None
    role: TeacherRole | None = None


# ── Student ────────────────────────────────────────────────
class StudentRead(ORMBase):
    id: int
    account_id: int
    class_id: int
    name: str
    phone: str | None = None
    status: StudentStatus
    barrier_profile: dict | None = None
    barrier_profile_updated_at: datetime | None = None
    practice_count: int = 0
    last_practice_time: datetime | None = None
    bind_code: str | None = None
    created_at: datetime | None = None


class StudentUpdate(BaseModel):
    name: str | None = None
    phone: str | None = None
    class_id: int | None = None


# ── Parent ─────────────────────────────────────────────────
class ParentRead(ORMBase):
    id: int
    account_id: int
    name: str
    phone: str | None = None
    email: str | None = None
    created_at: datetime | None = None


class ParentUpdate(BaseModel):
    name: str | None = None
    phone: str | None = None
    email: str | None = None


# ── TeacherClassSubject ────────────────────────────────────
class TeacherClassSubjectRead(ORMBase):
    id: int
    teacher_id: int
    class_id: int
    subject: str
    is_head_teacher: bool


class TeacherClassSubjectCreate(BaseModel):
    teacher_id: int
    class_id: int
    subject: str = "化学"
    is_head_teacher: bool = False


# ── TeacherApplication ─────────────────────────────────────
class TeacherApplicationCreate(BaseModel):
    name: str = Field(..., max_length=100)
    phone: str = Field(..., max_length=30)
    school_name: str = Field(..., max_length=200)
    subject: str = "化学"


class TeacherApplicationRead(ORMBase):
    id: int
    name: str
    phone: str
    school_name: str
    subject: str
    status: ApplicationStatus
    reviewer_id: int | None = None
    reviewed_at: datetime | None = None
    created_at: datetime | None = None


class TeacherApplicationApprove(BaseModel):
    approved: bool
    reviewer_id: int
