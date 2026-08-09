"""OCR schemas — UploadSession, StudentSubmission, OCRTask (覆盖新字段)."""

import pytest
from datetime import datetime
from pydantic import ValidationError

from app.core.enums import UploadSessionStatus, OCRTaskStatus
from app.schemas.ocr import (
    UploadSessionRead, UploadSessionCreate, UploadSessionUpdate,
    BatchUploadRequest, BatchUploadResponse,
    StudentSubmissionRead, OCRTaskRead, OCRTaskCreate,
    GradingResult, GradingSummary, QuestionGrading,
)

NOW = datetime(2026, 8, 1, 12, 0, 0)


class TestUploadSessionRead:
    def test_valid(self):
        r = UploadSessionRead(
            id=1, teacher_id=10,
            status=UploadSessionStatus.uploaded,
            original_filename="答题卡_001.jpg", mime_type="image/jpeg",
            file_path="ocr_uploads/1/2026-08-01/a1b2c3d4.jpg",
            detected_type="IMAGE",
            total_pages=1, completed_pages=0,
            fallback_used=False, version=1,
            created_at=NOW, updated_at=NOW, completed_at=None,
        )
        assert r.status == UploadSessionStatus.uploaded
        assert r.completed_at is None
        assert r.original_filename == "答题卡_001.jpg"
        assert r.detected_type == "IMAGE"

    def test_completed(self):
        r = UploadSessionRead(
            id=1, teacher_id=10,
            status=UploadSessionStatus.done,
            original_filename="答题卡_002.pdf", mime_type="application/pdf",
            file_path="ocr_uploads/1/2026-08-01/b2c3d4e5.pdf",
            detected_type="PDF",
            total_pages=3, completed_pages=3,
            fallback_used=True, version=2,
            created_at=NOW, updated_at=NOW, completed_at=NOW,
        )
        assert r.status == UploadSessionStatus.done
        assert r.fallback_used is True
        assert r.total_pages == 3

    def test_with_ocr_result(self):
        r = UploadSessionRead(
            id=2, teacher_id=10,
            status=UploadSessionStatus.ready,
            original_filename="test.jpg", mime_type="image/jpeg",
            file_path="ocr_uploads/1/2026-08-01/test.jpg",
            detected_type="IMAGE",
            total_pages=1, completed_pages=1,
            fallback_used=False, version=1,
            ocr_result_json={"text": "识别内容..."},
            grading_result_json={"score": 85},
            created_at=NOW, updated_at=NOW, completed_at=None,
        )
        assert r.ocr_result_json == {"text": "识别内容..."}
        assert r.grading_result_json == {"score": 85}


class TestUploadSessionCreate:
    def test_minimal(self):
        r = UploadSessionCreate(teacher_id=10)
        assert r.teacher_id == 10
        assert r.original_filename == ""
        assert r.mime_type == ""

    def test_full(self):
        r = UploadSessionCreate(
            teacher_id=10, original_filename="test.jpg",
            mime_type="image/jpeg", file_path="path/to/file",
            detected_type="IMAGE",
        )
        assert r.detected_type == "IMAGE"


class TestUploadSessionUpdate:
    def test_partial_update(self):
        r = UploadSessionUpdate(status=UploadSessionStatus.ready)
        assert r.status == UploadSessionStatus.ready

    def test_progress_update(self):
        r = UploadSessionUpdate(total_pages=3, completed_pages=1)
        assert r.total_pages == 3
        assert r.completed_pages == 1


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
            id=1, upload_session_id=1, teacher_id=10,
            status=OCRTaskStatus.pending,
            image_path="", title="答题卡_01",
            student_id_raw=None, student_name_raw=None,
            progress=0, confirmed=False,
            error_message=None, completed_at=None,
            ocr_raw_result=None, grading_result=None,
            created_at=NOW, updated_at=NOW,
        )
        assert r.status == OCRTaskStatus.pending
        assert r.teacher_id == 10
        assert r.progress == 0

    def test_with_results(self):
        r = OCRTaskRead(
            id=1, upload_session_id=1, teacher_id=10,
            status=OCRTaskStatus.done,
            image_path="ocr_uploads/1/card.jpg", title="答题卡_01",
            student_id_raw="202401001", student_name_raw="张三",
            progress=100, confirmed=True,
            error_message=None, completed_at=NOW,
            ocr_raw_result={"text": "..."},
            grading_result={"score": 85},
            created_at=NOW, updated_at=NOW,
        )
        assert r.ocr_raw_result == {"text": "..."}
        assert r.student_id_raw == "202401001"
        assert r.student_name_raw == "张三"

    def test_failed_task(self):
        r = OCRTaskRead(
            id=2, upload_session_id=1, teacher_id=10,
            status=OCRTaskStatus.failed,
            image_path="", title="答题卡_02",
            student_id_raw=None, student_name_raw=None,
            progress=20, confirmed=False,
            error_message="百度 OCR API 超时", completed_at=None,
            ocr_raw_result=None, grading_result=None,
            created_at=NOW, updated_at=NOW,
        )
        assert r.status == OCRTaskStatus.failed
        assert r.error_message == "百度 OCR API 超时"


class TestOCRTaskCreate:
    def test_minimal(self):
        r = OCRTaskCreate(upload_session_id=1, teacher_id=10)
        assert r.image_path == ""
        assert r.title == ""

    def test_full(self):
        r = OCRTaskCreate(
            upload_session_id=1, teacher_id=10,
            image_path="path/to/image.jpg", title="答题卡_化学月考",
        )
        assert r.title == "答题卡_化学月考"


class TestGradingResult:
    def test_valid(self):
        r = GradingResult(
            task_id=1, total_score=85.0, max_score=100.0,
            questions=[
                QuestionGrading(q_number=1, student_answer="C", correct_answer="C",
                                is_correct=True, score=5.0, max_score=5.0),
            ],
            needs_review=False,
        )
        assert r.total_score == 85.0
        assert len(r.questions) == 1

    def test_needs_review(self):
        r = GradingResult(
            task_id=2, total_score=None, max_score=None,
            questions=[], needs_review=True, error="LLM 无法判定",
        )
        assert r.needs_review is True


class TestGradingSummary:
    def test_valid(self):
        r = GradingSummary(
            batch_id="batch-001", total_tasks=30,
            graded_count=28, failed_count=2,
            average_score=72.4,
            results=[
                GradingResult(task_id=1, total_score=85.0, max_score=100.0,
                              questions=[], needs_review=False),
            ],
        )
        assert r.average_score == 72.4
        assert r.graded_count == 28
