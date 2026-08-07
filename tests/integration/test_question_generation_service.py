"""QuestionGeneration 服务纯函数测试 — JSON解析/Prompt构建/陷阱提示/RAG标记。

LLM 依赖的管线方法（generate_questions）需要 mock，不在本文件覆盖。
"""

import pytest

from app.services.question_generation_service import (
    _parse_llm_response,
    _describe_types,
    _build_user_prompt,
    _generate_trap_hints,
    _build_rag_mark,
    _format_rag_results,
    SYSTEM_PROMPT,
)
from app.models.question_bank import HistoricalExam


# ═══════════════════════════════════════════════════════════════
# _parse_llm_response — LLM 返回 JSON 解析
# ═══════════════════════════════════════════════════════════════

class TestParseLLMResponse:
    """_parse_llm_response 单元测试。"""

    def test_valid_json_direct(self):
        """直接 JSON 对象解析。"""
        raw = '{"questions": [{"content": "题目1", "question_type": "choice"}]}'
        result = _parse_llm_response(raw)
        assert len(result) == 1
        assert result[0]["content"] == "题目1"

    def test_json_with_markdown_fence(self):
        """```json ... ``` 代码块提取。"""
        raw = '''```json
{"questions": [{"content": "题目A"}]}
```'''
        result = _parse_llm_response(raw)
        assert len(result) == 1
        assert result[0]["content"] == "题目A"

    def test_json_with_generic_fence(self):
        """``` ... ``` 无语言标记的代码块。"""
        raw = '''```
{"questions": [{"content": "题目B"}]}
```'''
        result = _parse_llm_response(raw)
        assert len(result) == 1
        assert result[0]["content"] == "题目B"

    def test_json_regex_fallback(self):
        """从混合文本中正则提取 JSON 对象。"""
        raw = '一些说明文字 {"questions": [{"content": "提取的题目"}]} 更多文字'
        result = _parse_llm_response(raw)
        assert len(result) == 1
        assert result[0]["content"] == "提取的题目"

    def test_empty_response(self):
        """空字符串返回空列表。"""
        result = _parse_llm_response("")
        assert result == []

    def test_invalid_json(self):
        """无效 JSON 返回空列表。"""
        result = _parse_llm_response("这不是 JSON")
        assert result == []

    def test_json_without_questions_key(self):
        """JSON 无 questions 键返回空列表。"""
        raw = '{"other": "data"}'
        result = _parse_llm_response(raw)
        assert result == []

    def test_multiple_questions(self):
        """解析多道题目。"""
        raw = '{"questions": [{"content": "Q1"}, {"content": "Q2"}, {"content": "Q3"}]}'
        result = _parse_llm_response(raw)
        assert len(result) == 3

    def test_questions_empty_array(self):
        """questions 为空数组。"""
        raw = '{"questions": []}'
        result = _parse_llm_response(raw)
        assert result == []


# ═══════════════════════════════════════════════════════════════
# _describe_types — 题型代码 → 中文描述
# ═══════════════════════════════════════════════════════════════

class TestDescribeTypes:
    """_describe_types 单元测试。"""

    def test_single_type(self):
        """单题型描述。"""
        result = _describe_types(["choice"])
        assert "选择题" in result

    def test_multiple_types(self):
        """多题型描述用顿号连接。"""
        result = _describe_types(["choice", "fill_blank"])
        assert "选择题" in result
        assert "填空题" in result
        assert "、" in result

    def test_all_types(self):
        """全部题型。"""
        result = _describe_types([
            "choice", "fill_blank", "calculation",
            "experiment_inquiry", "equation_balancing",
        ])
        assert "选择题" in result
        assert "填空题" in result
        assert "计算题" in result
        assert "实验探究题" in result
        assert "推断题" in result

    def test_unknown_type_fallback(self):
        """未知题型返回原始代码。"""
        result = _describe_types(["unknown_type"])
        assert "unknown_type" in result


# ═══════════════════════════════════════════════════════════════
# _build_user_prompt — 构造第三层 User Prompt
# ═══════════════════════════════════════════════════════════════

class TestBuildUserPrompt:
    """_build_user_prompt 单元测试。"""

    def test_basic_prompt_without_rag(self):
        """无 RAG 上下文的基础 Prompt。"""
        result = _build_user_prompt(
            knowledge_points=["氧化还原反应"],
            difficulty="medium",
            quantity=3,
            type_desc="选择题",
            rag_context="",
        )

        assert "氧化还原反应" in result
        assert "3" in result
        assert "中等" in result
        assert "选择题" in result

    def test_prompt_with_rag_context(self):
        """含 RAG 上下文的变种题 Prompt。"""
        rag = "## 参考真题\n1. [全国卷 2023] 真题内容..."
        result = _build_user_prompt(
            knowledge_points=["电化学"],
            difficulty="hard",
            quantity=2,
            type_desc="计算题",
            rag_context=rag,
        )

        assert "变种题" in result
        assert "电化学" in result
        assert "困难" in result

    def test_difficulty_mapping(self):
        """难度映射正确。"""
        result_easy = _build_user_prompt(["测试"], "easy", 1, "选择题", "")
        result_hard = _build_user_prompt(["测试"], "hard", 1, "选择题", "")

        assert "基础" in result_easy
        assert "困难" in result_hard


# ═══════════════════════════════════════════════════════════════
# _generate_trap_hints — 知识点 → 陷阱提示
# ═══════════════════════════════════════════════════════════════

class TestGenerateTrapHints:
    """_generate_trap_hints 单元测试。"""

    def test_exact_kp_match(self):
        """完全匹配知识点返回提示。"""
        hints = _generate_trap_hints(["盐类水解"])
        assert len(hints) > 0
        assert any("水解" in h for h in hints)

    def test_substring_match(self):
        """部分匹配返回提示。"""
        hints = _generate_trap_hints(["盐类水解的应用"])  # 包含"盐类水解"
        assert len(hints) > 0

    def test_key_match(self):
        """知识点名称包含陷阱键时返回提示。"""
        hints = _generate_trap_hints(["原电池"])  # 精确匹配键
        assert len(hints) > 0
        assert any("负极" in h for h in hints)

    def test_no_match_returns_empty(self):
        """无匹配知识点返回空列表。"""
        hints = _generate_trap_hints(["不存在的知识点XYZ"])
        assert hints == []

    def test_max_3_hints(self):
        """最多返回 3 条提示。"""
        hints = _generate_trap_hints([
            "盐类水解", "氧化还原反应", "原电池", "化学平衡",
        ])
        assert len(hints) <= 3

    def test_deduplication(self):
        """同一陷阱不重复出现。"""
        # "氧化还原" 匹配 "氧化还原反应" 键
        hints = _generate_trap_hints(["氧化还原反应", "氧化还原"])
        # 两条 KP 匹配同一个陷阱，不应重复
        unique = set(hints)
        assert len(hints) == len(unique)

    def test_empty_input(self):
        """空知识点列表返回空。"""
        hints = _generate_trap_hints([])
        assert hints == []


# ═══════════════════════════════════════════════════════════════
# _format_rag_results — 真题列表 → 格式化文本
# ═══════════════════════════════════════════════════════════════

class TestFormatRagResults:
    """_format_rag_results 单元测试。"""

    def test_empty_list(self):
        """空列表返回空字符串。"""
        result = _format_rag_results([])
        assert result == ""

    def test_single_exam(self):
        """单个真题格式化。"""
        exam = HistoricalExam(
            source="全国卷", year=2023,
            content="真题内容" * 20,  # 超过200字符
            answer="B", analysis="解析内容" * 10,
        )
        result = _format_rag_results([exam])

        assert "参考真题" in result
        assert "全国卷" in result
        assert "2023" in result
        assert "B" in result
        # content 截断为前200字符
        assert result.count("真题内容") < 30

    def test_multiple_exams(self):
        """多个真题格式化。"""
        exams = [
            HistoricalExam(source="全国卷", year=2023, content="C1", answer="A", analysis="解析1"),
            HistoricalExam(source="湖南卷", year=2024, content="C2", answer="B", analysis=""),
        ]
        result = _format_rag_results(exams)

        assert "全国卷" in result
        assert "湖南卷" in result
        assert "2023" in result
        assert "2024" in result

    def test_exam_without_analysis(self):
        """无解析的真题不影响格式化。"""
        exam = HistoricalExam(
            source="测试", year=2020, content="内容", answer="C", analysis=None,
        )
        result = _format_rag_results([exam])
        assert "测试" in result
        # 无解析行时不应崩溃


# ═══════════════════════════════════════════════════════════════
# _build_rag_mark — RAG 标记构建
# ═══════════════════════════════════════════════════════════════

class TestBuildRagMark:
    """_build_rag_mark 单元测试。"""

    def test_no_rag_no_variant(self):
        """无 RAG 上下文且无变体 ID → None。"""
        result = _build_rag_mark("", "")
        assert result is None

    def test_variant_qid(self):
        """有变体蓝本题 ID → blueprint 标记。"""
        result = _build_rag_mark("", "123")
        assert result is not None
        assert result["is_from_rag"] is True
        assert result["source_question_id"] == "123"
        assert result["match_method"] == "blueprint"

    def test_rag_context_only(self):
        """仅有 RAG 上下文 → simple 标记。"""
        rag = "## 参考真题\n1. [全国卷 2023] 真题..."
        result = _build_rag_mark(rag, "")
        assert result is not None
        assert result["is_from_rag"] is True
        assert result["match_method"] == "simple"
        assert "source_question_preview" in result

    def test_both_rag_and_variant(self):
        """同时有 RAG 和变体 ID → blueprint 优先。"""
        rag = "## 参考真题"
        result = _build_rag_mark(rag, "456")
        assert result is not None
        assert result["match_method"] == "blueprint"
        assert result["source_question_id"] == "456"


# ═══════════════════════════════════════════════════════════════
# SYSTEM_PROMPT 常量验证
# ═══════════════════════════════════════════════════════════════

class TestSystemPrompt:
    """SYSTEM_PROMPT 常量验证。"""

    def test_contains_required_sections(self):
        """系统 Prompt 包含必需的格式/题型/输出格式章节。"""
        assert "格式规范" in SYSTEM_PROMPT
        assert "题型要求" in SYSTEM_PROMPT
        assert "输出格式" in SYSTEM_PROMPT

    def test_contains_question_types(self):
        """系统 Prompt 包含所有题型的描述。"""
        assert "choice" in SYSTEM_PROMPT
        assert "fill_blank" in SYSTEM_PROMPT
        assert "calculation" in SYSTEM_PROMPT
        assert "experiment_inquiry" in SYSTEM_PROMPT
        assert "equation_balancing" in SYSTEM_PROMPT

    def test_contains_latex_instructions(self):
        """系统 Prompt 包含 LaTeX 格式指令。"""
        assert "LaTeX" in SYSTEM_PROMPT
        assert "$...$" in SYSTEM_PROMPT
        assert "rightarrow" in SYSTEM_PROMPT
