"""Question bank schemas — QuestionSet, QuestionSetItem, HistoricalExam.

Aligned with 35-API §5 (exam_bank/knowledge routers).
"""

from datetime import datetime
from pydantic import BaseModel, Field

from ..core.enums import Difficulty
from .base import ORMBase


# ── QuestionSet ────────────────────────────────────────────
class QuestionSetCreate(BaseModel):
    teacher_id: int
    name: str = Field(..., max_length=200)
    description: str | None = None


class QuestionSetRead(ORMBase):
    id: int
    teacher_id: int
    name: str
    description: str | None
    created_at: datetime


# ── QuestionSetItem ────────────────────────────────────────
class QuestionSetItemRead(ORMBase):
    id: int
    question_set_id: int
    question_id: int
    sort_order: int


class QuestionSetItemAdd(BaseModel):
    question_set_id: int
    question_id: int
    sort_order: int = 0


# ── HistoricalExam ─────────────────────────────────────────
class HistoricalExamRead(ORMBase):
    id: int
    source: str
    year: int
    question_number: str | None
    knowledge_point_tags: list | None
    difficulty: Difficulty
    discrimination: float | None
    content: str
    answer: str
    analysis: str | None
