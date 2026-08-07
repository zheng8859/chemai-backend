"""OCR schemas — UploadSession, StudentSubmission, OCRTask."""

import pytest
from datetime import datetime
from pydantic import ValidationError

from app.core.enums import UploadSessionStatus, OCRTaskStatus
from app.schemas.ocr import (
    UploadSessionRead, BatchUploadRequest, BatchUploadResponse,
    StudentSubmissionRead, OCRTaskRead,
)

NOW = datetime(2026, 8, 1, 12, 0, 0)


class TestUploadSessionRead:
    def test_valid(self):
        r = UploadSessionRead(
            id=1, teacher_id=10,
            status=UploadSessionStatus.uploaded,
            created_at=NOW, completed_at=None,
        )
        assert r.status == UploadSessionStatus.uploaded
        assert r.completed_at is None

    def test_completed(self):
        r = UploadSessionRead(
            id=1, teacher_id=10,
            status=UploadSessionStatus.done,
            created_at=NOW, completed_at=NOW,
        )
        assert r.status == UploadSessionStatus.done


class TestBatchUploadRequest:
    def test_valid(self):
        r = BatchUploadRequest(teacher_id=10, class_id=1, exam_name="期中考试")
        assert r.exam_name == "期中考试"

    def test_exam_name_required(self):
        with pytest.raises(ValidationError):
            BatchUploadRequest(teacher_id=10, class_id=1)


class TestBatchUploadResponse:
    def test_valid(self):
        r = BatchUploadResponse(
            batch_id="batch-001", total=30,
            tasks=[{"task_id": "1", "student_name": "小明", "status": "pending"}],
        )
        assert r.success is True
        assert r.batch_id == "batch-001"
        assert r.total == 30


class TestStudentSubmissionRead:
    def test_valid(self):
        r = StudentSubmissionRead(
            id=1, exam_record_id=1, student_id=10, class_id=1,
            original_image="/img/001.jpg", graded_image=None,
            answer_list=None, total_score=None,
            submitted_at=NOW, graded_at=None,
        )
        assert r.original_image == "/img/001.jpg"


class TestOCRTaskRead:
    def test_valid(self):
        r = OCRTaskRead(
            id=1, upload_session_id=1,
            status=OCRTaskStatus.pending,
            ocr_raw_result=None, grading_result=None,
            created_at=NOW,
        )
        assert r.status == OCRTaskStatus.pending

    def test_with_results(self):
        r = OCRTaskRead(
            id=1, upload_session_id=1,
            status=OCRTaskStatus.done,
            ocr_raw_result={"text": "..."},
            grading_result={"score": 85},
            created_at=NOW,
        )
        assert r.ocr_raw_result == {"text": "..."}
