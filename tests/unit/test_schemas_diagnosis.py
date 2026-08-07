"""Diagnosis schemas — BarrierConfig, StudentDiagnosis, ReviewTask, Warning, Practice, Override."""

import pytest
from datetime import datetime
from pydantic import ValidationError

from app.core.enums import BarrierType, ReviewTaskStatus, WarningType, WarningSeverity
from app.schemas.diagnosis import (
    BarrierConfigRead, BarrierConfigUpdate,
    KnowledgePointRead,
    StudentDiagnosisItem, ClassDiagnosisResponse,
    ReviewTaskRead, ReviewCompleteRequest,
    WarningLogRead, WarningResolveRequest,
    PracticeAssignRequest, PracticeAssignResponse,
    DiagnosisRunResponse,
    DiagnosisOverrideRequest, DiagnosisOverrideResponse,
)

NOW = datetime(2026, 8, 1, 12, 0, 0)


class TestBarrierConfigRead:
    def test_valid(self):
        r = BarrierConfigRead(
            id=1, teacher_id=10,
            concept_threshold=3, reading_threshold=3,
            expression_threshold=3, mastery_threshold=5,
            auto_sync_enabled=True, created_at=NOW,
        )
        assert r.concept_threshold == 3


class TestBarrierConfigUpdate:
    def test_partial(self):
        r = BarrierConfigUpdate(concept_threshold=5, auto_sync_enabled=False)
        assert r.concept_threshold == 5
        assert r.auto_sync_enabled is False

    def test_threshold_bounds(self):
        """阈值必须在 1-10 范围内。"""
        r = BarrierConfigUpdate(concept_threshold=1)
        assert r.concept_threshold == 1
        r = BarrierConfigUpdate(concept_threshold=10)
        assert r.concept_threshold == 10

    def test_threshold_too_low(self):
        with pytest.raises(ValidationError):
            BarrierConfigUpdate(concept_threshold=0)

    def test_threshold_too_high(self):
        with pytest.raises(ValidationError):
            BarrierConfigUpdate(concept_threshold=11)


class TestKnowledgePointRead:
    def test_valid(self):
        r = KnowledgePointRead(
            id=1, name="氧化还原反应", category="化学原理",
            pubchem_id=None, question_count=45, dynamic_error_rate=0.23,
        )
        assert r.name == "氧化还原反应"


class TestStudentDiagnosisItem:
    def test_valid(self):
        r = StudentDiagnosisItem(
            student_id=10, student_name="小明",
            barrier_type=BarrierType.concept, confidence=0.85,
            weak_kps=["氧化还原", "摩尔计算"],
            recommended_intervention="针对氧化还原概念进行专题训练",
        )
        assert r.barrier_type == BarrierType.concept


class TestClassDiagnosisResponse:
    def test_valid(self):
        r = ClassDiagnosisResponse(
            class_id=1, exam_id=1,
            class_summary={
                "concept_rate": 0.4, "reading_rate": 0.3,
                "expression_rate": 0.3, "top_weak_kps": ["氧化还原"],
            },
            students=[],
        )
        assert r.class_id == 1


class TestReviewTaskRead:
    def test_valid(self):
        r = ReviewTaskRead(
            id=1, student_id=10, question_id=100,
            level=2, status=ReviewTaskStatus.pending,
            next_review_date=NOW, created_at=NOW,
        )
        assert r.level == 2


class TestReviewCompleteRequest:
    def test_correct(self):
        r = ReviewCompleteRequest(review_task_id=1, result=True)
        assert r.result is True

    def test_incorrect(self):
        r = ReviewCompleteRequest(review_task_id=1, result=False)
        assert r.result is False


class TestWarningLogRead:
    def test_valid(self):
        r = WarningLogRead(
            id=1, student_id=10,
            warning_type=WarningType.score_drop,
            severity=WarningSeverity.warning,
            message="成绩下滑 15%",
            notified_teacher=True, notified_parent=False,
            notified_student=False, created_at=NOW,
        )
        assert r.warning_type == WarningType.score_drop


class TestWarningResolveRequest:
    def test_valid(self):
        r = WarningResolveRequest(warning_id=1)
        assert r.warning_id == 1


class TestPracticeAssignRequest:
    def test_defaults(self):
        r = PracticeAssignRequest(student_id=10)
        assert r.question_count == 10
        assert r.target_barrier is None
        assert r.knowledge_points is None

    def test_with_target_barrier(self):
        r = PracticeAssignRequest(
            student_id=10, question_count=20,
            target_barrier=BarrierType.reading,
            knowledge_points=["氧化还原"],
        )
        assert r.target_barrier == BarrierType.reading
        assert r.knowledge_points == ["氧化还原"]

    def test_count_bounds(self):
        r = PracticeAssignRequest(student_id=10, question_count=1)
        assert r.question_count == 1
        r = PracticeAssignRequest(student_id=10, question_count=50)
        assert r.question_count == 50

    def test_count_too_low(self):
        with pytest.raises(ValidationError):
            PracticeAssignRequest(student_id=10, question_count=0)

    def test_count_too_high(self):
        with pytest.raises(ValidationError):
            PracticeAssignRequest(student_id=10, question_count=51)


class TestPracticeAssignResponse:
    def test_valid(self):
        r = PracticeAssignResponse(
            practice_session_id="sess-001",
            questions=[1, 2, 3], estimated_time_minutes=15,
        )
        assert r.success is True
        assert len(r.questions) == 3


class TestDiagnosisRunResponse:
    def test_defaults(self):
        r = DiagnosisRunResponse()
        assert r.success is True
        assert r.analyzed_count == 0
        assert r.failed_count == 0
        assert r.remaining_count == 0

    def test_after_run(self):
        r = DiagnosisRunResponse(
            analyzed_count=10, failed_count=1, remaining_count=5,
        )
        assert r.analyzed_count == 10


class TestDiagnosisOverrideRequest:
    def test_valid(self):
        r = DiagnosisOverrideRequest(
            barrier_type="concept",
            misconception_category="chemical_equilibrium",
        )
        assert r.barrier_type == "concept"

    def test_category_optional(self):
        r = DiagnosisOverrideRequest(barrier_type="reading")
        assert r.misconception_category is None

    def test_barrier_type_empty_rejected(self):
        with pytest.raises(ValidationError):
            DiagnosisOverrideRequest(barrier_type="")


class TestDiagnosisOverrideResponse:
    def test_valid(self):
        r = DiagnosisOverrideResponse(
            old={"barrier_type": "reading"},
            new={"barrier_type": "concept"},
        )
        assert r.success is True
        assert r.old == {"barrier_type": "reading"}
