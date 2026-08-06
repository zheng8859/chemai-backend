"""Diagnosis schemas — BarrierConfig, KnowledgePoint, ReviewTask, WarningLog.

Aligned with 35-API §6 (diagnosis/practice/review routers), §9 (warning).
"""

from datetime import datetime
from pydantic import BaseModel, Field

from ..core.enums import (
    BarrierType,
    ReviewTaskStatus,
    WarningType,
    WarningSeverity,
)
from .base import ORMBase


# ── BarrierConfig ──────────────────────────────────────────
class BarrierConfigRead(ORMBase):
    id: int
    teacher_id: int
    concept_threshold: int
    reading_threshold: int
    expression_threshold: int
    mastery_threshold: int
    auto_sync_enabled: bool
    created_at: datetime


class BarrierConfigUpdate(BaseModel):
    concept_threshold: int | None = Field(None, ge=1, le=10)
    reading_threshold: int | None = Field(None, ge=1, le=10)
    expression_threshold: int | None = Field(None, ge=1, le=10)
    mastery_threshold: int | None = Field(None, ge=1, le=10)
    auto_sync_enabled: bool | None = None


# ── KnowledgePoint ─────────────────────────────────────────
class KnowledgePointRead(ORMBase):
    id: int
    name: str
    category: str | None
    pubchem_id: str | None
    question_count: int
    dynamic_error_rate: float


# ── Diagnosis result (35号 §三: GET /api/diagnosis/barrier/...) ─
class StudentDiagnosisItem(BaseModel):
    student_id: int
    student_name: str
    barrier_type: BarrierType | None
    confidence: float | None
    weak_kps: list[str]
    recommended_intervention: str | None


class ClassDiagnosisResponse(BaseModel):
    success: bool = True
    class_id: int
    exam_id: int
    class_summary: dict  # {concept_rate, reading_rate, expression_rate, top_weak_kps}
    students: list[StudentDiagnosisItem]


# ── ReviewTask ─────────────────────────────────────────────
class ReviewTaskRead(ORMBase):
    id: int
    student_id: int
    question_id: int
    level: int
    status: ReviewTaskStatus
    next_review_date: datetime | None
    created_at: datetime


class ReviewCompleteRequest(BaseModel):
    review_task_id: int
    result: bool  # True=答对, False=答错


# ── WarningLog ─────────────────────────────────────────────
class WarningLogRead(ORMBase):
    id: int
    student_id: int
    warning_type: WarningType
    severity: WarningSeverity
    message: str
    notified_teacher: bool
    notified_parent: bool
    notified_student: bool
    created_at: datetime


class WarningResolveRequest(BaseModel):
    warning_id: int


# ── Practice ───────────────────────────────────────────────
class PracticeAssignRequest(BaseModel):
    """自适应练习布置 (35号 §三: POST /api/practice/assign)"""
    student_id: int
    question_count: int = Field(default=10, ge=1, le=50)
    target_barrier: BarrierType | None = None
    knowledge_points: list[str] | None = None


class PracticeAssignResponse(BaseModel):
    success: bool = True
    practice_session_id: str
    questions: list[int]  # question ids
    estimated_time_minutes: int


# ── LLM Diagnosis Run ────────────────────────────────────────

class DiagnosisRunResponse(BaseModel):
    """POST /diagnosis/run-llm/{exam_id} 响应。

    remaining_count 供前端自动循环判断终止条件。
    """
    success: bool = True
    analyzed_count: int = 0
    failed_count: int = 0
    remaining_count: int = 0


# ── Teacher Override ──────────────────────────────────────────

class DiagnosisOverrideRequest(BaseModel):
    """PUT /diagnosis/override/{student_answer_id} 请求体。

    barrier_type 必填（concept/reading/expression），
    misconception_category 可选（六类 或 null）。
    """
    barrier_type: str = Field(
        ..., min_length=1,
        description="障碍类型：concept / reading / expression",
    )
    misconception_category: str | None = Field(
        None,
        description="迷思概念类别：六选一 或 null",
    )


class DiagnosisOverrideResponse(BaseModel):
    """PUT /diagnosis/override/{student_answer_id} 响应体。

    返回覆盖前后的值，供前端展示变更。
    """
    success: bool = True
    old: dict
    new: dict
