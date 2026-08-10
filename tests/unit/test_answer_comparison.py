"""6.10: answer comparison unit tests — choice string compare + chemical equivalence."""

import pytest
from unittest.mock import AsyncMock, patch

from app.services.grading_service import GradingService

LLM_PATH = "app.llm.router.llm_chat"


# ================================================================
# 6.5: choice answer comparison tests
# ================================================================

class TestChoiceAnswerComparison:

    def test_exact_match_uppercase(self):
        is_correct, reason = GradingService._compare_choice_answer("C", "C")
        assert is_correct is True
        assert reason == ""

    def test_lowercase_match(self):
        is_correct, reason = GradingService._compare_choice_answer("a", "A")
        assert is_correct is True

    def test_whitespace_tolerance(self):
        is_correct, reason = GradingService._compare_choice_answer("  B  ", "B")
        assert is_correct is True

    def test_mismatch(self):
        is_correct, reason = GradingService._compare_choice_answer("C", "D")
        assert is_correct is False
        assert "C" in reason
        assert "D" in reason

    def test_empty_student_answer(self):
        is_correct, reason = GradingService._compare_choice_answer("", "C")
        assert is_correct is False
        assert "未作答" in reason

    def test_whitespace_only_answer(self):
        is_correct, reason = GradingService._compare_choice_answer("   ", "C")
        assert is_correct is False
        assert "未作答" in reason

    def test_auto_mode(self):
        is_correct, reason = GradingService._compare_choice_answer("C", "AUTO")
        assert is_correct is False
        assert "待教师确认" in reason

    def test_same_letter_different_case(self):
        is_correct, reason = GradingService._compare_choice_answer("d", "D")
        assert is_correct is True


# ================================================================
# 6.6: chemical equivalence tests (LLM mock)
# ================================================================

class TestChemicalEquivalence:

    @pytest.mark.asyncio
    async def test_subscript_equivalent_h2o(self):
        """H2O and H2O (same text) — fast path exact match."""
        is_equiv, reason = await GradingService._compare_chemical_answer("H2O", "H2O")
        assert is_equiv is True
        assert reason == ""

    @pytest.mark.asyncio
    async def test_empty_answer(self):
        is_equiv, reason = await GradingService._compare_chemical_answer("", "H2O")
        assert is_equiv is False
        assert "未作答" in reason

    @pytest.mark.asyncio
    async def test_whitespace_insensitive(self):
        is_equiv, reason = await GradingService._compare_chemical_answer("  H2O  ", "H2O")
        assert is_equiv is True

    @pytest.mark.asyncio
    async def test_llm_equiv_fe3plus(self):
        """Fe(OH)3 vs Fe(OH)3 — LLM says equivalent (after fast path check for different input)."""
        with patch(LLM_PATH, new_callable=AsyncMock) as mock_chat:
            mock_chat.return_value = '{"is_equivalent": true, "reason": "chemical equivalence"}'
            is_equiv, reason = await GradingService._compare_chemical_answer("Fe(OH)3", "Fe(OH)3?")
        assert is_equiv is True

    @pytest.mark.asyncio
    async def test_llm_not_equiv(self):
        """oxidation vs redox — LLM says not equivalent."""
        with patch(LLM_PATH, new_callable=AsyncMock) as mock_chat:
            mock_chat.return_value = '{"is_equivalent": false, "reason": "different concepts"}'
            is_equiv, reason = await GradingService._compare_chemical_answer("oxidation", "redox reaction")
        assert is_equiv is False
        assert reason != ""

    @pytest.mark.asyncio
    async def test_llm_error_fallback(self):
        """LLM failure → conservative: not equivalent."""
        with patch(LLM_PATH, new_callable=AsyncMock) as mock_chat:
            mock_chat.side_effect = Exception("timeout")
            is_equiv, reason = await GradingService._compare_chemical_answer("Fe3+", "Fe2+")
        assert is_equiv is False
        assert "失败" in reason

    @pytest.mark.asyncio
    async def test_simple_string_match_fast_path(self):
        """Identical after normalization — no LLM call needed."""
        # The _compare_chemical_answer normalizes (strip + lower + remove spaces)
        # So "h2o" matches "H2O" without LLM
        is_equiv, reason = await GradingService._compare_chemical_answer("h2o", "H2O")
        assert is_equiv is True
        assert reason == ""


# ================================================================
# 6.1: answer source resolution tests
# ================================================================

class TestResolveAnswerSource:

    @pytest.mark.asyncio
    async def test_teacher_input_priority(self):
        """教师录入最高优先级。"""
        from unittest.mock import AsyncMock
        db = AsyncMock()
        key = await GradingService.resolve_answer_source(
            db,
            exam_paper_id=1,
            teacher_answers={"1": "C", "2": "B"},
        )
        assert key.source_mode == "teacher_input"
        assert key.question_count == 2
        assert key.questions[1] == "C"

    @pytest.mark.asyncio
    async def test_llm_auto_fallback(self):
        """无教师录入、无题库匹配 → LLM 自判。"""
        db = AsyncMock()
        key = await GradingService.resolve_answer_source(db)
        assert key.source_mode == "llm_auto"
        assert key.question_count == 0
        assert key.questions == {}
