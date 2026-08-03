"""OCR schemas — UploadSession, StudentSubmission, OCRTask.

Aligned with 35-API §3 (ocr/ocr_sheets routers).
"""

from datetime import datetime
from pydantic import BaseModel, Field

from ..core.enums import UploadSessionStatus, OCRTaskStatus
from .base import ORMBase


# ── UploadSession ──────────────────────────────────────────
class UploadSessionRead(ORMBase):
    id: int
    teacher_id: int
    status: UploadSessionStatus
    created_at: datetime
    completed_at: datetime | None


class BatchUploadRequest(BaseModel):
    """批量答题卡上传 (35号 §三: POST /api/ocr/tasks/batch)"""
    teacher_id: int
    class_id: int
    exam_name: str = Field(..., max_length=200)


class BatchUploadResponse(BaseModel):
    success: bool = True
    batch_id: str
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
class OCRTaskRead(ORMBase):
    id: int
    upload_session_id: int
    status: OCRTaskStatus
    ocr_raw_result: dict | None
    grading_result: dict | None
    created_at: datetime
