"""Teaching schemas — ExamRecord, Question, StudentAnswer, Grading."""

import pytest
from datetime import datetime
from pydantic import ValidationError

from app.core.enums import ExamType, Difficulty, QuestionSource, AuditStatus, BarrierType
from app.schemas.teaching import (
    ExamCreate, ExamRead, ExamListParams,
    QuestionCreate, QuestionRead,
    QuestionGenerateRequest, QuestionGenerateResponse,
    QuestionHistoricalParams,
    StudentAnswerRead, PracticeSubmitRequest,
    GradingRunRequest, GradingRunResponse,
    ExamQuestionAssociateResponse,
    ExamPublishResponse, ExamFinalizeResponse,
    ExamQuestionItem, ExamQuestionsResponse,
    QuestionImportResponse,
)

NOW = datetime(2026, 8, 1, 12, 0, 0)


class TestExamCreate:
    def test_valid(self):
        r = ExamCreate(class_id=1, exam_type=ExamType.monthly, exam_date=NOW)
        assert r.exam_type == ExamType.monthly

    def test_with_name(self):
        r = ExamCreate(class_id=1, exam_type=ExamType.practice, exam_date=NOW, name="期中练习")
        assert r.name == "期中练习"

    def test_class_id_required(self):
        with pytest.raises(ValidationError):
            ExamCreate(exam_type=ExamType.monthly, exam_date=NOW)


class TestExamRead:
    def test_valid_with_defaults(self):
        r = ExamRead(
            id=1, class_id=1, exam_type=ExamType.monthly,
            exam_date=NOW, participant_count=0,
            avg_score=None, error_stats=None,
            name=None, created_at=NOW,
        )
        assert r.status == "pending"
        assert r.question_count == 0


class TestExamListParams:
    def test_defaults(self):
        r = ExamListParams()
        assert r.limit == 20
        assert r.order == "desc"


class TestQuestionCreate:
    def test_defaults(self):
        r = QuestionCreate(content="水的化学式是什么？", answer="H2O")
        assert r.question_type == "choice"
        assert r.difficulty == Difficulty.medium
        assert r.source == QuestionSource.manual

    def test_full_fields(self):
        r = QuestionCreate(
            content="题目", question_type="fill_blank",
            options=["A", "B"], answer="A",
            analysis="解析", knowledge_point_tags=["氧化还原"],
            difficulty=Difficulty.hard, source=QuestionSource.ai_generated,
        )
        assert r.difficulty == Difficulty.hard
        assert r.knowledge_point_tags == ["氧化还原"]


class TestQuestionRead:
    def test_valid(self):
        r = QuestionRead(
            id=1, content="题目内容", question_type="choice",
            options=["A", "B", "C", "D"], answer="A",
            analysis=None, knowledge_point_tags=["氧化还原"],
            difficulty=Difficulty.medium, source=QuestionSource.ai_generated,
            audit_status=AuditStatus.passed, audit_report=None,
            created_at=NOW,
        )
        assert r.audit_status == AuditStatus.passed


class TestQuestionGenerateRequest:
    def test_valid_minimal(self):
        r = QuestionGenerateRequest(knowledge_points=["氧化还原反应"])
        assert r.quantity == 3

    def test_knowledge_points_required(self):
        with pytest.raises(ValidationError):
            QuestionGenerateRequest(knowledge_points=[])

    def test_quantity_bounds(self):
        r = QuestionGenerateRequest(knowledge_points=["氧化还原"], quantity=1)
        assert r.quantity == 1
        r2 = QuestionGenerateRequest(knowledge_points=["氧化还原"], quantity=20)
        assert r2.quantity == 20

    def test_quantity_too_high(self):
        with pytest.raises(ValidationError):
            QuestionGenerateRequest(knowledge_points=["氧化还原"], quantity=21)

    def test_quantity_too_low(self):
        with pytest.raises(ValidationError):
            QuestionGenerateRequest(knowledge_points=["氧化还原"], quantity=0)


class TestQuestionHistoricalParams:
    def test_defaults(self):
        r = QuestionHistoricalParams()
        assert r.limit == 20
        assert r.year is None

    def test_filter_by_year(self):
        r = QuestionHistoricalParams(year=2024, difficulty=Difficulty.hard)
        assert r.year == 2024
        assert r.difficulty == Difficulty.hard


class TestStudentAnswerRead:
    def test_valid(self):
        r = StudentAnswerRead(
            id=1, student_id=10, question_id=100,
            exam_record_id=1, answer_content="A",
            is_correct=True, barrier_type=None,
            consecutive_wrong_count=0, consecutive_correct_count=1,
            created_at=NOW,
        )
        assert r.is_correct is True


class TestPracticeSubmitRequest:
    def test_valid(self):
        r = PracticeSubmitRequest(
            student_id=10, question_id=100,
            answer_content="2H2 + O2 → 2H2O",
        )
        assert r.practice_session_id is None

    def test_with_session(self):
        r = PracticeSubmitRequest(
            student_id=10, question_id=100,
            practice_session_id="sess-001", answer_content="A",
        )
        assert r.practice_session_id == "sess-001"


class TestGradingRunRequest:
    def test_valid(self):
        r = GradingRunRequest(exam_id=1, class_id=1)
        assert r.exam_id == 1


class TestGradingRunResponse:
    def test_valid(self):
        r = GradingRunResponse(
            grading_job_id="job-001",
            total_submissions=45, status="processing",
        )
        assert r.success is True


class TestExamQuestionAssociateResponse:
    def test_valid(self):
        r = ExamQuestionAssociateResponse(added=5, from_existing=3, from_historical=2)
        assert r.added == 5


class TestExamPublishResponse:
    def test_valid(self):
        r = ExamPublishResponse(
            exam_id=1, status="in_progress",
            question_count=10, total_students=45,
            published_at="2026-08-01T12:00:00",
        )
        assert r.status == "in_progress"


class TestExamFinalizeResponse:
    def test_valid(self):
        r = ExamFinalizeResponse(exam_id=1, status="completed", participant_count=45)
        assert r.status == "completed"


class TestExamQuestionItem:
    def test_valid(self):
        r = ExamQuestionItem(
            id=1, content="题目", question_type="choice",
            difficulty="medium", sort_order=1,
        )
        assert r.answer is None
        assert r.analysis is None
        assert r.options is None

    def test_with_full_fields(self):
        r = ExamQuestionItem(
            id=1, content="题目", question_type="choice",
            difficulty="medium", sort_order=1,
            answer="A", analysis="解析",
            options=["A", "B"], knowledge_point_tags=["kp1"],
        )
        assert r.answer == "A"


class TestExamQuestionsResponse:
    def test_valid(self):
        r = ExamQuestionsResponse(questions=[])
        assert r.success is True
        assert r.questions == []


class TestQuestionImportResponse:
    def test_valid(self):
        r = QuestionImportResponse(imported_count=5, questions=[])
        assert r.imported_count == 5
        assert r.success is True
