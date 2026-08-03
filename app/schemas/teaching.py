"""Teaching schemas — ExamRecord, Question, StudentAnswer.

Aligned with 35-API §4 (exam/grading), §5 (question/exam_bank/knowledge).
"""

from datetime import datetime
from pydantic import BaseModel, Field

from ..core.enums import (
    ExamType,
    Difficulty,
    QuestionSource,
    AuditStatus,
    BarrierType,
)
from .base import ORMBase


# ── ExamRecord ─────────────────────────────────────────────
class ExamCreate(BaseModel):
    class_id: int
    exam_type: ExamType
    exam_date: datetime
    name: str | None = Field(None, max_length=200)


class ExamRead(ORMBase):
    id: int
    class_id: int
    exam_type: ExamType
    exam_date: datetime
    participant_count: int
    avg_score: float | None
    error_stats: dict | None
    name: str | None
    created_at: datetime


class ExamListParams(BaseModel):
    class_id: int | None = None
    limit: int = 20
    offset: int = 0
    sort_by: str = "exam_date"
    order: str = "desc"


# ── Question ───────────────────────────────────────────────
class QuestionCreate(BaseModel):
    content: str
    question_type: str = "choice"
    options: list | None = None
    answer: str
    analysis: str | None = None
    knowledge_point_tags: list | None = None
    difficulty: Difficulty = Difficulty.medium
    source: QuestionSource = QuestionSource.manual


class QuestionRead(ORMBase):
    id: int
    content: str
    question_type: str
    options: list | None
    answer: str
    analysis: str | None
    knowledge_point_tags: list | None
    difficulty: Difficulty
    source: QuestionSource
    audit_status: AuditStatus
    audit_report: dict | None
    created_at: datetime


class QuestionGenerateRequest(BaseModel):
    """AI 出题请求 (35号 §三: POST /api/question/generate)"""
    knowledge_points: list[str] = Field(..., min_length=1)
    difficulty: Difficulty = Difficulty.medium
    count: int = Field(default=3, ge=1, le=20)
    question_type: str = "选择题"
    teacher_id: int


class QuestionGenerateResponse(BaseModel):
    success: bool = True
    questions: list["QuestionRead"]
    generated_count: int
    total_available: int


class QuestionHistoricalParams(BaseModel):
    source: str | None = None
    year: int | None = None
    difficulty: Difficulty | None = None
    limit: int = 20
    offset: int = 0


# ── StudentAnswer ──────────────────────────────────────────
class StudentAnswerRead(ORMBase):
    id: int
    student_id: int
    question_id: int
    exam_record_id: int
    answer_content: str
    is_correct: bool
    barrier_type: BarrierType | None
    consecutive_wrong_count: int
    consecutive_correct_count: int
    created_at: datetime


class PracticeSubmitRequest(BaseModel):
    """练习提交 (35号 §三: POST /api/practice/submit)"""
    student_id: int
    question_id: int
    practice_session_id: str | None = None
    answer_content: str


# ── Grading ────────────────────────────────────────────────
class GradingRunRequest(BaseModel):
    """触发 LLM 批改 (35号 §三: POST /api/grading/run)"""
    exam_id: int
    class_id: int


class GradingRunResponse(BaseModel):
    success: bool = True
    grading_job_id: str
    total_submissions: int
    status: str
