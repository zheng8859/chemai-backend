"""5.4: answers parser unit tests — choice regex + LLM mock."""

import pytest
from unittest.mock import AsyncMock, patch

from app.services.answer_parser import (
    ParsedAnswer,
    ParseResult,
    _parse_choice_answers,
    _parse_complex_answers,
    parse_answers_from_text,
)

# llm_chat is imported inside functions via `from ..llm.router import llm_chat`,
# so we must patch at the source module.
LLM_PATH = "app.llm.router.llm_chat"


# ================================================================
# 5.2: choice regex tests
# ================================================================

class TestChoiceRegex:

    def test_normal_choice_dot_format(self):
        text = "1. C  2. B  3. A"
        result = _parse_choice_answers(text)
        assert len(result) == 3
        assert result[0].q_number == 1
        assert result[0].student_answer == "C"
        assert result[0].question_type == "choice"
        assert result[0].confidence == 0.99

    def test_normal_choice_chinese_comma(self):
        text = "1、D  2、C"
        result = _parse_choice_answers(text)
        assert len(result) == 2
        assert result[0].student_answer == "D"
        assert result[1].student_answer == "C"

    def test_normal_choice_fullwidth_dot(self):
        text = "1．A  2．B"
        result = _parse_choice_answers(text)
        assert len(result) == 2
        assert result[0].student_answer == "A"

    def test_no_space_choice(self):
        text = "11.C  12.A  13.D"
        result = _parse_choice_answers(text)
        assert len(result) == 3
        assert result[0].q_number == 11
        assert result[0].student_answer == "C"

    def test_lowercase_options(self):
        text = "1. a  2. b  3. c  4. d"
        result = _parse_choice_answers(text)
        assert len(result) == 4
        assert result[0].student_answer == "A"

    def test_mixed_lines(self):
        text = "1. C  2. B\n3. D  4. A  5. C"
        result = _parse_choice_answers(text)
        assert len(result) == 5

    def test_deduplicate_same_number(self):
        text = "1. C  something  1. D"
        result = _parse_choice_answers(text)
        assert len(result) == 1
        assert result[0].student_answer == "C"

    def test_noise_ignore_non_choice_text(self):
        text = "Name: Zhang San  Student ID: 20240001\n1. C  2. B  3. A  4. D  5. C\nFill-in section:"
        result = _parse_choice_answers(text)
        assert len(result) == 5

    def test_noise_ignore_chemistry_formulas(self):
        text = "1. C  2. B  H2O is water  3. A"
        result = _parse_choice_answers(text)
        assert len(result) == 3

    def test_noise_email_and_urls(self):
        text = "1. C  2. B  email@example.com  https://foo.com  3. A"
        result = _parse_choice_answers(text)
        assert len(result) == 3

    def test_boundary_empty_text(self):
        result = _parse_choice_answers("")
        assert result == []

    def test_boundary_no_choices(self):
        text = "16. H2O  17. redox reaction  18. Fe3+"
        result = _parse_choice_answers(text)
        assert result == []

    def test_boundary_single_digit_options(self):
        text = "1. oxidation  2. reduction"
        result = _parse_choice_answers(text)
        assert result == []

    def test_boundary_max_question_number(self):
        text = "99. C  100. D"
        result = _parse_choice_answers(text)
        assert len(result) == 2
        assert result[0].q_number == 99

    def test_boundary_chinese_punctuation_only(self):
        text = "1，A  2，B"
        result = _parse_choice_answers(text)
        assert result == []

    def test_result_sorted_by_q_number(self):
        text = "5. D  3. B  1. C  4. D  2. A"
        result = _parse_choice_answers(text)
        numbers = [a.q_number for a in result]
        assert numbers == [1, 2, 3, 4, 5]


# ================================================================
# 5.3: LLM mock tests
# ================================================================

class TestComplexAnswerLLM:

    @pytest.mark.asyncio
    async def test_parse_complex_with_llm_mock(self):
        mock_response = '{"answers": [{"q_number": 16, "student_answer": "H2O", "question_type": "fill"}, {"q_number": 17, "student_answer": "redox", "question_type": "fill"}]}'
        with patch(LLM_PATH, new_callable=AsyncMock) as mock_chat:
            mock_chat.return_value = mock_response
            result = await _parse_complex_answers("16. H2O  17. redox", choice_count=15)
        assert len(result) == 2
        assert result[0].q_number == 16
        assert result[0].student_answer == "H2O"
        assert result[0].question_type == "fill"
        assert result[0].confidence == 0.85

    @pytest.mark.asyncio
    async def test_parse_complex_skip_choice_numbers(self):
        mock_response = '{"answers": [{"q_number": 1, "student_answer": "C", "question_type": "choice"}, {"q_number": 16, "student_answer": "H2O", "question_type": "fill"}]}'
        with patch(LLM_PATH, new_callable=AsyncMock) as mock_chat:
            mock_chat.return_value = mock_response
            result = await _parse_complex_answers("1. C  16. H2O", choice_count=15)
        assert len(result) == 1
        assert result[0].q_number == 16

    @pytest.mark.asyncio
    async def test_parse_complex_empty_response(self):
        mock_response = '{"answers": []}'
        with patch(LLM_PATH, new_callable=AsyncMock) as mock_chat:
            mock_chat.return_value = mock_response
            result = await _parse_complex_answers("only choices", choice_count=15)
        assert result == []

    @pytest.mark.asyncio
    async def test_parse_complex_llm_error(self):
        with patch(LLM_PATH, new_callable=AsyncMock) as mock_chat:
            mock_chat.side_effect = Exception("API timeout")
            result = await _parse_complex_answers("16. H2O", choice_count=15)
        assert result == []

    @pytest.mark.asyncio
    async def test_parse_complex_deduplicate_in_llm(self):
        mock_response = '{"answers": [{"q_number": 16, "student_answer": "H2O", "question_type": "fill"}, {"q_number": 16, "student_answer": "H2O2", "question_type": "fill"}]}'
        with patch(LLM_PATH, new_callable=AsyncMock) as mock_chat:
            mock_chat.return_value = mock_response
            result = await _parse_complex_answers("16. H2O", choice_count=15)
        assert len(result) == 1
        assert result[0].student_answer == "H2O"


# ================================================================
# 5.1: main entry hybrid tests
# ================================================================

class TestParseAnswersFromText:

    @pytest.mark.asyncio
    async def test_hybrid_choice_only(self):
        text = "1. C  2. B  3. A  4. D  5. C"
        result = await parse_answers_from_text(text, question_count=5)
        assert result.total_found == 5
        assert result.is_partial is False
        assert all(a.question_type == "choice" for a in result.answers)

    @pytest.mark.asyncio
    async def test_hybrid_mixed_with_llm(self):
        text = "1. C  2. B  3. A  4. D  5. C\n16. H2O  17. redox"
        mock_response = '{"answers": [{"q_number": 16, "student_answer": "H2O", "question_type": "fill"}, {"q_number": 17, "student_answer": "redox", "question_type": "fill"}]}'
        with patch(LLM_PATH, new_callable=AsyncMock) as mock_chat:
            mock_chat.return_value = mock_response
            result = await parse_answers_from_text(text, question_count=17)
        assert result.total_found == 7
        assert result.is_partial is True

    @pytest.mark.asyncio
    async def test_hybrid_complete_match(self):
        text = "1. C  2. B  3. A"
        result = await parse_answers_from_text(text, question_count=3)
        assert result.total_found == 3
        assert result.is_partial is False

    @pytest.mark.asyncio
    async def test_hybrid_question_count_zero(self):
        text = "1. C  2. B"
        with patch(LLM_PATH, new_callable=AsyncMock) as mock_chat:
            mock_chat.return_value = '{"answers": []}'
            result = await parse_answers_from_text(text, question_count=0)
        assert result.total_found == 2
        assert result.is_partial is False

    @pytest.mark.asyncio
    async def test_hybrid_result_sorted(self):
        text = "5. D  3. B  1. C"
        result = await parse_answers_from_text(text, question_count=3)
        numbers = [a.q_number for a in result.answers]
        assert numbers == [1, 3, 5]

    @pytest.mark.asyncio
    async def test_hybrid_empty_text(self):
        with patch(LLM_PATH, new_callable=AsyncMock) as mock_chat:
            mock_chat.return_value = '{"answers": []}'
            result = await parse_answers_from_text("", question_count=10)
        assert result.total_found == 0
        assert result.is_partial is True

    @pytest.mark.asyncio
    async def test_hybrid_raw_text_preserved(self):
        text = "  1. C  2. B  "
        with patch(LLM_PATH, new_callable=AsyncMock) as mock_chat:
            mock_chat.return_value = '{"answers": []}'
            result = await parse_answers_from_text(text, question_count=2)
        assert result.raw_text == "1. C  2. B"
