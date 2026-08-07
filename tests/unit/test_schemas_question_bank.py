"""Question bank schemas — QuestionSet, QuestionSetItem, HistoricalExam."""

import pytest
from datetime import datetime
from pydantic import ValidationError

from app.core.enums import Difficulty
from app.schemas.question_bank import (
    QuestionSetCreate, QuestionSetRead,
    QuestionSetItemRead, QuestionSetItemAdd,
    HistoricalExamRead,
)

NOW = datetime(2026, 8, 1, 12, 0, 0)


class TestQuestionSetCreate:
    def test_valid_minimal(self):
        r = QuestionSetCreate(name="氧化还原题库")
        assert r.name == "氧化还原题库"
        assert r.teacher_id is None
        assert r.description is None

    def test_with_teacher(self):
        r = QuestionSetCreate(teacher_id=10, name="我的题库", description="收藏的题目")
        assert r.teacher_id == 10
        assert r.description == "收藏的题目"

    def test_name_required(self):
        with pytest.raises(ValidationError):
            QuestionSetCreate()


class TestQuestionSetRead:
    def test_valid_with_defaults(self):
        r = QuestionSetRead(
            id=1, teacher_id=10, name="氧化还原题库",
            description=None, created_at=NOW,
        )
        assert r.is_system is False
        assert r.question_count == 0

    def test_system_folder(self):
        r = QuestionSetRead(
            id=1, teacher_id=0, name="系统预设",
            description=None, is_system=True, question_count=100,
            created_at=NOW,
        )
        assert r.is_system is True
        assert r.question_count == 100


class TestQuestionSetItemRead:
    def test_valid_minimal(self):
        r = QuestionSetItemRead(
            id=1, question_set_id=1, question_id=100, sort_order=0,
        )
        assert r.content is None
        assert r.question_type is None

    def test_full_fields(self):
        r = QuestionSetItemRead(
            id=1, question_set_id=1, question_id=100, sort_order=1,
            content="题目内容", question_type="choice",
            difficulty="medium",
            options=["A", "B"], answer="A",
            knowledge_point_tags=["氧化还原"],
        )
        assert r.content == "题目内容"
        assert r.knowledge_point_tags == ["氧化还原"]


class TestQuestionSetItemAdd:
    def test_valid(self):
        r = QuestionSetItemAdd(question_set_id=1, question_id=100)
        assert r.sort_order == 0

    def test_with_order(self):
        r = QuestionSetItemAdd(question_set_id=1, question_id=100, sort_order=5)
        assert r.sort_order == 5


class TestHistoricalExamRead:
    def test_valid(self):
        r = HistoricalExamRead(
            id=1, source="全国卷", year=2023,
            question_number="7", knowledge_point_tags=["氧化还原"],
            difficulty=Difficulty.medium, discrimination=0.45,
            content="题目内容", answer="A", analysis="解析",
        )
        assert r.source == "全国卷"
        assert r.year == 2023

    def test_optional_fields(self):
        r = HistoricalExamRead(
            id=1, source="湖南卷", year=2024,
            question_number=None, knowledge_point_tags=None,
            difficulty=Difficulty.hard, discrimination=None,
            content="题目", answer="B", analysis=None,
        )
        assert r.question_number is None
