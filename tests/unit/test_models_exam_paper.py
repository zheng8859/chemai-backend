"""Test ExamPaper model — state machines and field constraints."""

import pytest

from app.models.exam_paper import ExamPaper, ExamPaperQuestion
from app.models.teaching import ExamRecord
from app.core.enums import ExamPaperStatus, ExamRecordStatus


class TestExamPaperModel:
    def test_fields_exist(self):
        assert ExamPaper.__tablename__ == "exam_paper"
        assert hasattr(ExamPaper, "name")
        assert hasattr(ExamPaper, "total_score")
        assert hasattr(ExamPaper, "duration_minutes")
        assert hasattr(ExamPaper, "status")
        assert hasattr(ExamPaper, "teacher_id")

    def test_status_defaults_draft(self):
        col = ExamPaper.__table__.c.status
        assert col.server_default.arg == "'draft'"

    def test_status_values(self):
        assert ExamPaperStatus.draft.value == "draft"
        assert ExamPaperStatus.published.value == "published"
        assert ExamPaperStatus.archived.value == "archived"


class TestExamPaperQuestionModel:
    def test_fields_exist(self):
        assert ExamPaperQuestion.__tablename__ == "exam_paper_question"
        assert hasattr(ExamPaperQuestion, "exam_paper_id")
        assert hasattr(ExamPaperQuestion, "question_id")
        assert hasattr(ExamPaperQuestion, "sort_order")
        assert hasattr(ExamPaperQuestion, "score")


class TestExamRecordModel:
    def test_exam_paper_id_exists(self):
        assert hasattr(ExamRecord, "exam_paper_id"), (
            "ExamRecord should have 'exam_paper_id' FK"
        )

    def test_status_exists(self):
        assert hasattr(ExamRecord, "status"), (
            "ExamRecord should have 'status' field"
        )

    def test_status_values(self):
        values = {v.value for v in ExamRecordStatus}
        assert values == {
            "pending", "in_progress", "grading",
            "completed", "archived", "cancelled",
        }
