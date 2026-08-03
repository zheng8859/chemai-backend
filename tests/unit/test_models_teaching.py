"""Test Teaching & Diagnosis model changes."""

import pytest

from app.models.teaching import StudentAnswer, Question
from app.models.diagnosis import KnowledgePoint


class TestStudentAnswerDiagnosis:
    def test_misconception_category_field(self):
        assert hasattr(StudentAnswer, "misconception_category"), (
            "StudentAnswer should have 'misconception_category'"
        )

    def test_diagnosed_by_field(self):
        assert hasattr(StudentAnswer, "diagnosed_by"), (
            "StudentAnswer should have 'diagnosed_by'"
        )

    def test_diagnosis_overridden_at_field(self):
        assert hasattr(StudentAnswer, "diagnosis_overridden_at"), (
            "StudentAnswer should have 'diagnosis_overridden_at'"
        )

    def test_exam_record_id_nullable(self):
        col = StudentAnswer.__table__.c.exam_record_id
        assert col.nullable, "StudentAnswer.exam_record_id must be nullable"


class TestQuestionVariant:
    def test_variant_of_question_id_field(self):
        assert hasattr(Question, "variant_of_question_id"), (
            "Question should have 'variant_of_question_id'"
        )

    def test_variant_dimensions_field(self):
        assert hasattr(Question, "variant_dimensions"), (
            "Question should have 'variant_dimensions'"
        )


class TestKnowledgePointHierarchy:
    def test_parent_id_field(self):
        assert hasattr(KnowledgePoint, "parent_id"), (
            "KnowledgePoint should have 'parent_id'"
        )
