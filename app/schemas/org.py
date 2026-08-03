"""Organization schemas — School, Grade, Class.

Aligned with 35-API §2 (school/grade/class_api routers).
"""

from datetime import datetime
from pydantic import BaseModel, Field

from .base import ORMBase


# ── School ─────────────────────────────────────────────────
class SchoolCreate(BaseModel):
    name: str = Field(..., max_length=200)
    region: str | None = None
    address: str | None = None
    phone: str | None = None
    current_semester: str | None = None


class SchoolRead(ORMBase):
    id: int
    name: str
    region: str | None
    address: str | None
    phone: str | None
    current_semester: str | None
    created_at: datetime


class SchoolUpdate(BaseModel):
    name: str | None = None
    region: str | None = None
    address: str | None = None
    phone: str | None = None
    current_semester: str | None = None


# ── Grade ──────────────────────────────────────────────────
class GradeCreate(BaseModel):
    school_id: int
    name: str = Field(..., max_length=50)
    academic_year: str | None = None


class GradeRead(ORMBase):
    id: int
    school_id: int
    name: str
    academic_year: str | None
    created_at: datetime


class GradeUpdate(BaseModel):
    name: str | None = None
    academic_year: str | None = None


# ── Class ──────────────────────────────────────────────────
class ClassCreate(BaseModel):
    grade_id: int
    name: str = Field(..., max_length=100)
    stage: str | None = None
    subject: str = "化学"


class ClassRead(ORMBase):
    id: int
    grade_id: int
    name: str
    student_count: int
    stage: str | None
    subject: str
    created_at: datetime


class ClassUpdate(BaseModel):
    name: str | None = None
    stage: str | None = None
