"""AI 出题服务纯函数测试 — Prompt 构造、JSON 解析、陷阱提示、RAG 标记。

不涉及 LLM 调用和数据库，仅测纯逻辑函数。
"""

import pytest
from unittest.mock import Mock

from app.services.question_generation_service import (
    _describe_types,
    _build_user_prompt,
    _parse_llm_response,
    _generate_trap_hints,
    _build_rag_mark,
    _format_rag_results,
    SYSTEM_PROMPT,
)


class TestDescribeTypes:
    def test_single_known_type(self):
        assert "选择题" in _describe_types(["choice"])

    def test_fill_blank(self):
        assert "填空题" in _describe_types(["fill_blank"])

    def test_calculation(self):
        assert "计算题" in _describe_types(["calculation"])

    def test_experiment(self):
        assert "实验探究题" in _describe_types(["experiment_inquiry"])

    def test_equation_balancing(self):
        assert "推断题" in _describe_types(["equation_balancing"])

    def test_mixed_types(self):
        result = _describe_types(["choice", "calculation"])
        assert "选择题" in result
        assert "计算题" in result
        assert "、" in result  # separator

    def test_unknown_type_raw(self):
        """未知题型原样返回。"""
        result = _describe_types(["unknown_type"])
        assert "unknown_type" in result


class TestBuildUserPrompt:
    def test_with_rag_context(self):
        rag = "## 参考真题\n1. [全国卷 2023] ..."
        prompt = _build_user_prompt(
            ["氧化还原反应"], "medium", 3,
            "选择题（4选项）", rag,
        )
        assert "氧化还原反应" in prompt
        assert "3" in prompt
        assert "中等" in prompt
        assert rag in prompt
        assert "JSON" in prompt

    def test_without_rag_context(self):
        prompt = _build_user_prompt(
            ["化学平衡", "盐类水解"], "hard", 5,
            "计算题（分步计算）", "",
        )
        assert "化学平衡" in prompt
        assert "盐类水解" in prompt
        assert "困难" in prompt
        assert "5" in prompt
        assert "JSON" in prompt
        assert "计算题" in prompt

    def test_easy_difficulty(self):
        prompt = _build_user_prompt(["摩尔计算"], "easy", 1, "选择题", "")
        assert "基础" in prompt

    def test_default_difficulty(self):
        """未知难度值 → 默认"中等"。"""
        prompt = _build_user_prompt(["氧化还原"], "unknown", 1, "选择", "")
        assert "中等" in prompt


class TestParseLLMResponse:
    def test_direct_json(self):
        raw = '{"questions": [{"content": "题目", "answer": "A"}]}'
        result = _parse_llm_response(raw)
        assert len(result) == 1
        assert result[0]["content"] == "题目"

    def test_empty_list(self):
        raw = '{"questions": []}'
        result = _parse_llm_response(raw)
        assert result == []

    def test_json_code_block(self):
        raw = '```json\n{"questions": [{"content": "题目"}]}\n```'
        result = _parse_llm_response(raw)
        assert len(result) == 1

    def test_code_block_no_lang(self):
        raw = '```\n{"questions": [{"content": "题目"}]}\n```'
        result = _parse_llm_response(raw)
        assert len(result) == 1

    def test_json_in_text(self):
        """JSON 嵌在自然语言中，自动提取。"""
        raw = '好的，以下是题目：\n{"questions": [{"content": "题目", "answer": "B"}]}\n希望对你有帮助。'
        result = _parse_llm_response(raw)
        assert len(result) == 1
        assert result[0]["answer"] == "B"

    def test_invalid_json(self):
        result = _parse_llm_response("这不是 JSON")
        assert result == []

    def test_empty_string(self):
        assert _parse_llm_response("") == []

    def test_malformed_json(self):
        assert _parse_llm_response("{broken json") == []

    def test_multiple_questions(self):
        raw = '{"questions": [{"content": "Q1"}, {"content": "Q2"}, {"content": "Q3"}]}'
        result = _parse_llm_response(raw)
        assert len(result) == 3


class TestGenerateTrapHints:
    def test_exact_match(self):
        hints = _generate_trap_hints(["氧化还原反应"])
        assert len(hints) > 0
        assert any("电子转移" in h for h in hints)

    def test_multiple_kps(self):
        hints = _generate_trap_hints(["盐类水解", "电离"])
        assert len(hints) >= 2

    def test_empty_kps(self):
        hints = _generate_trap_hints([])
        assert hints == []

    def test_unknown_kp(self):
        hints = _generate_trap_hints(["未知知识点"])
        assert hints == []

    def test_max_three_hints(self):
        """最多返回 3 条提示。"""
        hints = _generate_trap_hints([
            "盐类水解", "电离", "氧化还原反应",
            "原电池", "电解池", "化学平衡",
        ])
        assert len(hints) <= 3

    def test_substring_match(self):
        """key in kp or kp in key 双向匹配。"""
        hints = _generate_trap_hints(["有机"])
        assert len(hints) > 0  # "有机化学" matches

    def test_deduplication(self):
        """相同提示不重复。"""
        hints = _generate_trap_hints(["盐类水解", "盐类水解"])
        unique = set(hints)
        assert len(hints) == len(unique)


class TestBuildRagMark:
    def test_no_context_no_variant(self):
        assert _build_rag_mark("", "") is None

    def test_variant_mode(self):
        mark = _build_rag_mark("", "q_001")
        assert mark is not None
        assert mark["is_from_rag"] is True
        assert mark["source_question_id"] == "q_001"
        assert mark["match_method"] == "blueprint"

    def test_rag_context_mode(self):
        mark = _build_rag_mark("[全国卷 2023] 题目内容", "")
        assert mark is not None
        assert mark["is_from_rag"] is True
        assert mark["match_method"] == "simple"
        assert "source_question_preview" in mark

    def test_rag_context_extracts_source(self):
        mark = _build_rag_mark("[全国卷 2023 Q7] 题目...", "")
        assert mark["source_question_preview"] is not None
        assert "[全国卷 2023 Q7]" in mark["source_question_preview"]


class TestFormatRagResults:
    def test_empty_list(self):
        assert _format_rag_results([]) == ""

    def test_single_result(self):
        exam = Mock()
        exam.source = "全国卷"
        exam.year = 2023
        exam.content = "题目内容"
        exam.answer = "A"
        exam.analysis = "解析"

        result = _format_rag_results([exam])
        assert "全国卷" in result
        assert "2023" in result
        assert "题目内容" in result
        assert "答案: A" in result
        assert "解析" in result

    def test_result_no_analysis(self):
        exam = Mock()
        exam.source = "湖南卷"
        exam.year = 2024
        exam.content = "题目"
        exam.answer = "B"
        exam.analysis = None

        result = _format_rag_results([exam])
        assert "湖南卷" in result
        assert "解析" not in result

    def test_content_truncated(self):
        """题目内容截断到 200 字符。"""
        exam = Mock()
        exam.source = "全国卷"
        exam.year = 2023
        exam.content = "A" * 300
        exam.answer = "X"
        exam.analysis = ""

        result = _format_rag_results([exam])
        # content should be truncated to 200 — "A" * 201 would exceed truncation
        assert "A" * 201 not in result


class TestSystemPrompt:
    def test_contains_latex_rules(self):
        assert "LaTeX" in SYSTEM_PROMPT
        assert "\\rightarrow" in SYSTEM_PROMPT

    def test_contains_output_format(self):
        assert '"questions"' in SYSTEM_PROMPT
        assert '"content"' in SYSTEM_PROMPT

    def test_mentions_question_types(self):
        assert "choice" in SYSTEM_PROMPT
        assert "fill_blank" in SYSTEM_PROMPT
        assert "calculation" in SYSTEM_PROMPT
