"""Test core enums — all enums importable and values match spec."""

import pytest

from app.core.enums import (
    AccountRole,
    BarrierType,
    ExamType,
    QuestionSource,
    AuditStatus,
    Difficulty,
    TeacherRole,
    TeacherAccountStatus,
    ReviewTaskStatus,
    StudentStatus,
    ParentRelation,
    BindingStatus,
    WarningType,
    WarningSeverity,
    NotificationType,
    ApplicationStatus,
    OCRTaskStatus,
    MemoryType,
    UploadSessionStatus,
    # New enums (45-数据模型与认证体系)
    MisconceptionCategory,
    QuestionType,
    ExamPaperStatus,
    ExamRecordStatus,
    PracticeSessionStatus,
    ApprovalStatus,
    DiagnosisSource,
)


class TestMisconceptionCategory:
    def test_all_six_values_exist(self):
        values = list(MisconceptionCategory)
        assert len(values) == 6
        names = {v.value for v in values}
        assert names == {
            "chemical_equilibrium",
            "redox",
            "mole_calculation",
            "organic_chemistry",
            "chemical_notation",
            "structure_of_matter",
        }


class TestQuestionType:
    def test_all_five_values_exist(self):
        values = list(QuestionType)
        assert len(values) == 5
        names = {v.value for v in values}
        assert names == {
            "choice",
            "fill_blank",
            "calculation",
            "equation_balancing",
            "experiment_inquiry",
        }


class TestExamPaperStatus:
    def test_draft_published_archived(self):
        assert ExamPaperStatus.draft.value == "draft"
        assert ExamPaperStatus.published.value == "published"
        assert ExamPaperStatus.archived.value == "archived"


class TestExamRecordStatus:
    def test_all_six_states(self):
        values = {v.value for v in ExamRecordStatus}
        assert values == {
            "pending", "in_progress", "grading",
            "completed", "archived", "cancelled",
        }


class TestPracticeSessionStatus:
    def test_three_states(self):
        values = {v.value for v in PracticeSessionStatus}
        assert values == {"in_progress", "completed", "abandoned"}


class TestApprovalStatus:
    def test_four_states(self):
        values = {v.value for v in ApprovalStatus}
        assert values == {"pending", "approved", "rejected", "expired"}


class TestDiagnosisSource:
    def test_three_sources(self):
        values = {v.value for v in DiagnosisSource}
        assert values == {"ai_rule", "ai_llm", "teacher"}


class TestDifficulty:
    def test_three_tiers_plus_competition(self):
        values = {v.value for v in Difficulty}
        assert values == {"easy", "medium", "hard", "competition"}
