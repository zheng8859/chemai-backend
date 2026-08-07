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
    status: str = "pending"
    exam_date: datetime
    participant_count: int
    avg_score: float | None
    error_stats: dict | None
    name: str | None
    question_count: int = 0
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
    """AI 出题请求 (25号 §三: POST /api/v1/questions/generate)"""
    knowledge_points: list[str] = Field(..., min_length=1)
    difficulty: str = "medium"
    quantity: int = Field(default=3, ge=1, le=20)
    question_types: list[str] | None = None
    exam_type: str = ""
    variant_qid: str = ""


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


# ── 自适应练习（Phase 4）──────────────────────────────────────

class PracticeAnswerItem(BaseModel):
    """单条作答。"""
    question_id: int
    answer: str


class PracticeBatchSubmitRequest(BaseModel):
    """批量提交练习答案 (POST /api/v1/practice/submit)。"""
    practice_id: str
    answers: list[PracticeAnswerItem] = []


# ── 间隔复习（Phase 4）────────────────────────────────────────

class ReviewSubmitRequest(BaseModel):
    """提交复习结果 (POST /api/v1/review/submit)。"""
    review_task_id: int
    is_correct: bool


class MarkMasteredRequest(BaseModel):
    """标记题目已掌握 (POST /api/v1/review/wrong/{question_id}/master)。"""
    student_id: int


class VariantGenerateRequest(BaseModel):
    """生成变式题 (POST /api/v1/review/wrong-topic/variant/generate)。"""
    question_id: int
    count: int = 3


class TrainingCreateRequest(BaseModel):
    """创建错题强化训练 (POST /api/v1/review/wrong-topic/training/create)。"""
    student_id: int
    question_ids: list[int] = []


class TrainingSubmitRequest(BaseModel):
    """提交强化训练结果 (POST /api/v1/review/wrong-topic/training/submit)。"""
    session_id: str
    student_id: int
    answers: list[PracticeAnswerItem] = []


# ── 考试管理 ────────────────────────────────────────────────

class ExamQuestionAssociateResponse(BaseModel):
    """考试-题目关联响应 (25号 §六.2)"""
    success: bool = True
    added: int
    from_existing: int
    from_historical: int


class ExamPublishResponse(BaseModel):
    """考试发布响应 (25号 §六.3)"""
    success: bool = True
    exam_id: int
    status: str
    question_count: int
    total_students: int
    published_at: str


class ExamFinalizeResponse(BaseModel):
    """考试完成响应 (25号 §六.2)"""
    success: bool = True
    exam_id: int
    status: str
    participant_count: int


class ExamQuestionItem(BaseModel):
    """考试题目摘要"""
    id: int
    content: str
    question_type: str
    difficulty: str
    sort_order: int
    answer: str | None = None
    analysis: str | None = None
    options: list | None = None
    knowledge_point_tags: list | None = None


class ExamQuestionsResponse(BaseModel):
    """考试题目列表响应"""
    success: bool = True
    questions: list[ExamQuestionItem]


class QuestionImportResponse(BaseModel):
    """题目导入响应 (25号 §三 Mode2)"""
    success: bool = True
    imported_count: int
    questions: list["QuestionRead"]


class QuestionGenerateResponse(BaseModel):
    """AI 出题响应 (25号 §三.1.1)"""
    success: bool
    questions: list["QuestionRead"]
    generated_count: int
    total_available: int
    warning: str | None = None


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
