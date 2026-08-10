"""OCR schemas — UploadSession, StudentSubmission, OCRTask.

Aligned with 35-API §3 (ocr/ocr_sheets routers).
"""

from datetime import datetime
from pydantic import BaseModel, Field

from ..core.enums import UploadSessionStatus, OCRTaskStatus
from .base import ORMBase


# ── UploadSession ──────────────────────────────────────────
class UploadSessionCreate(BaseModel):
    """创建上传会话（内部使用）"""
    teacher_id: int
    original_filename: str = ""
    mime_type: str = ""
    file_path: str = ""
    detected_type: str = ""


class UploadSessionUpdate(BaseModel):
    """更新上传会话（内部使用）"""
    status: UploadSessionStatus | None = None
    ocr_result_json: dict | None = None
    grading_result_json: dict | None = None
    total_pages: int | None = None
    completed_pages: int | None = None
    fallback_used: bool | None = None
    error_message: str | None = None
    completed_at: datetime | None = None


class UploadSessionRead(ORMBase):
    id: int
    teacher_id: int
    status: UploadSessionStatus
    original_filename: str
    mime_type: str
    file_path: str
    detected_type: str
    ocr_result_json: dict | None = None
    grading_result_json: dict | None = None
    total_pages: int
    completed_pages: int
    fallback_used: bool
    version: int
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None


class BatchUploadRequest(BaseModel):
    """批量答题卡上传 (35号 §三: POST /api/ocr/tasks/batch)"""
    teacher_id: int
    class_id: int
    exam_name: str = Field(..., max_length=200)


class BatchUploadResponse(BaseModel):
    success: bool = True
    batch_id: str
    session_id: int | None = None
    total: int
    tasks: list[dict]  # [{task_id, student_name, status}]


# ── StudentSubmission ──────────────────────────────────────
class StudentSubmissionRead(ORMBase):
    id: int
    exam_record_id: int
    student_id: int
    class_id: int
    original_image: str
    graded_image: str | None
    answer_list: list | None
    total_score: float | None
    submitted_at: datetime
    graded_at: datetime | None


# ── OCRTask ────────────────────────────────────────────────
class OCRTaskCreate(BaseModel):
    """创建 OCR 任务"""
    upload_session_id: int
    teacher_id: int
    image_path: str = ""
    title: str = ""


class OCRTaskUpdate(BaseModel):
    """更新 OCR 任务"""
    status: OCRTaskStatus | None = None
    ocr_raw_result: dict | None = None
    grading_result: dict | None = None
    student_id_raw: str | None = None
    student_name_raw: str | None = None
    progress: int | None = None
    confirmed: bool | None = None
    error_message: str | None = None
    completed_at: datetime | None = None


class OCRTaskRead(ORMBase):
    id: int
    upload_session_id: int
    teacher_id: int
    status: OCRTaskStatus
    image_path: str
    title: str
    ocr_raw_result: dict | None = None
    grading_result: dict | None = None
    student_id_raw: str | None = None
    student_name_raw: str | None = None
    progress: int
    confirmed: bool
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None


# ── Grading ────────────────────────────────────────────────

class QuestionGrading(BaseModel):
    """逐题批改结果（6.7）"""
    q_number: int
    student_answer: str
    correct_answer: str
    is_correct: bool
    reason: str = ""
    score: float = 0.0
    max_score: float = 0.0
    confidence: float = 1.0
    needs_review: bool = False


class GradingResult(BaseModel):
    """单次批改结果"""
    task_id: int
    student_id_raw: str | None = None
    student_name_raw: str | None = None
    total_score: float | None = None
    max_score: float | None = None
    engine: str = ""
    degraded: bool = False
    questions: list[QuestionGrading] = []
    needs_review: bool = False
    error: str | None = None


class GradingSummary(BaseModel):
    """批次批改汇总"""
    batch_id: str
    total_tasks: int
    graded_count: int
    failed_count: int
    average_score: float | None = None
    results: list[GradingResult] = []


class GradingRunRequest(BaseModel):
    """触发批改请求（6.8）"""
    task_ids: list[int]
    exam_paper_id: int | None = None
    teacher_answers: dict[str, str] | None = None  # {"q_number": "correct_answer"}


class GradingRunResponse(BaseModel):
    """批改执行结果"""
    batch_id: str
    success: bool = True
    total: int
    graded: int
    failed: int
    results: list[GradingResult] = []


class GradingSaveRequest(BaseModel):
    """保存批改结果请求（8.5）"""
    task_ids: list[int]


class GradingSaveResponse(BaseModel):
    """保存结果响应"""
    success: bool = True
    saved_count: int = 0
    skipped_count: int = 0
    diagnosis_triggered: bool = False


# ── 通用 API 响应模型 ──────────────────────────────────────

class RetryTaskResponse(BaseModel):
    """OCR 任务重试响应"""
    success: bool = True
    task_id: int
    status: str


class ServicesStatusResponse(BaseModel):
    """引擎可用性状态响应"""
    ocr: dict
    mineru: dict
    vision: dict
    queue_pending: int = 0


class GradingResultsResponse(BaseModel):
    """批次批改结果查询响应"""
    batch_id: str
    message: str


class StatsResponse(BaseModel):
    """统计与报告响应"""
    success: bool = True
    exam_record_id: int
    statistics: dict
    report: str
