"""LLM Diagnoser 引擎单元测试。

Mock LLM callback 验证 JSON 鲁棒性管道、字段校验、并发和重试逻辑。
"""

import asyncio
import pytest
from chem_skills.chemistry_diagnosis.engine.llm_diagnoser import (
    _strip_markdown_fence,
    _extract_json,
    _repair_json,
    _parse_diagnosis_json,
    _validate_and_build,
    diagnose_single,
    diagnose_batch,
    SYSTEM_PROMPT,
)
from chem_skills.chemistry_diagnosis.engine.models import DiagnosisResult


# ═══════════════════════════════════════════════════════════════
# JSON 鲁棒性管道测试（P0 加固验证）
# ═══════════════════════════════════════════════════════════════

class TestStripMarkdownFence:
    def test_strip_json_fence(self):
        text = '```json\n{"barrier_type": "concept"}\n```'
        assert _strip_markdown_fence(text) == '{"barrier_type": "concept"}'

    def test_strip_plain_fence(self):
        text = '```\n{"barrier_type": "concept"}\n```'
        assert _strip_markdown_fence(text) == '{"barrier_type": "concept"}'

    def test_no_fence(self):
        text = '{"barrier_type": "concept"}'
        assert _strip_markdown_fence(text) == '{"barrier_type": "concept"}'

    def test_extra_whitespace(self):
        text = '  \n```json\n{"barrier_type": "concept"}\n```\n  '
        # Leading/trailing whitespace is stripped
        result = _strip_markdown_fence(text)
        assert result == '{"barrier_type": "concept"}'

    def test_text_before_json(self):
        """LLM 在 JSON 前后加了说明文字。"""
        text = '分析如下：\n```json\n{"barrier_type": "concept"}\n```\n以上是诊断结果。'
        # fence 剥离只在文本整体被 fence 包裹时生效，否则返回原文本
        result = _strip_markdown_fence(text)
        assert '分析如下' in result  # 非纯粹 fence 包裹，保持原样


class TestExtractJson:
    def test_simple_object(self):
        text = '{"barrier_type": "concept"}'
        assert _extract_json(text) == '{"barrier_type": "concept"}'

    def test_nested_braces(self):
        text = '{"data": {"barrier_type": "concept"}, "reasoning": "测试{内容}"}'
        expected = '{"data": {"barrier_type": "concept"}, "reasoning": "测试{内容}"}'
        assert _extract_json(text) == expected

    def test_escaped_quotes(self):
        text = '{"reasoning": "学生说\\"不会做\\"", "barrier_type": "concept"}'
        result = _extract_json(text)
        assert result is not None
        assert "concept" in result

    def test_multiple_json_objects_returns_first(self):
        text = '{"a": 1} extra text {"b": 2}'
        assert _extract_json(text) == '{"a": 1}'

    def test_no_json(self):
        assert _extract_json("这是一段纯文本") is None

    def test_unmatched_braces(self):
        assert _extract_json('{"a": 1') is None

    def test_json_with_text_prefix(self):
        """正则取第一个 { 开始的配对 JSON。"""
        text = '分析：学生存在概念理解障碍。结果：{"barrier_type": "concept", "reasoning": "测试"}'
        expected = '{"barrier_type": "concept", "reasoning": "测试"}'
        assert _extract_json(text) == expected


class TestRepairJson:
    def test_trailing_comma_in_object(self):
        assert _repair_json('{"a": 1,}') == '{"a": 1}'

    def test_trailing_comma_in_array(self):
        assert _repair_json('{"a": [1, 2,]}') == '{"a": [1, 2]}'

    def test_no_trailing_comma(self):
        text = '{"a": 1, "b": 2}'
        assert _repair_json(text) == text


class TestParseDiagnosisJson:
    def test_valid_json(self):
        data = _parse_diagnosis_json('{"barrier_type": "concept", "misconception_category": "redox", "reasoning": "测试", "suggestion": "建议"}')
        assert data is not None
        assert data["barrier_type"] == "concept"

    def test_json_in_markdown_fence(self):
        text = '```json\n{"barrier_type": "reading", "misconception_category": null, "reasoning": "审题不清", "suggestion": "强化审题训练"}\n```'
        data = _parse_diagnosis_json(text)
        assert data is not None
        assert data["barrier_type"] == "reading"
        assert data["misconception_category"] is None

    def test_json_with_text_prefix(self):
        text = '以下是诊断结果：\n{"barrier_type": "expression", "misconception_category": "chemical_notation", "reasoning": "方程式书写错误", "suggestion": "练习化学用语"}'
        data = _parse_diagnosis_json(text)
        assert data is not None
        assert data["barrier_type"] == "expression"

    def test_invalid_json_returns_none(self):
        assert _parse_diagnosis_json("这不是 JSON") is None

    def test_bare_text_returns_none(self):
        assert _parse_diagnosis_json("The student has a concept barrier.") is None


# ═══════════════════════════════════════════════════════════════
# 字段校验测试
# ═══════════════════════════════════════════════════════════════

class TestValidateAndBuild:
    def test_valid_concept(self):
        data = {
            "barrier_type": "concept",
            "misconception_category": "redox",
            "reasoning": "概念混淆",
            "suggestion": "强化概念教学",
        }
        result = _validate_and_build(data)
        assert result is not None
        assert result.barrier_type == "concept"
        assert result.misconception_category == "redox"

    def test_valid_reading_with_null_category(self):
        data = {
            "barrier_type": "reading",
            "misconception_category": None,
            "reasoning": "审题不清",
            "suggestion": "强化审题",
        }
        result = _validate_and_build(data)
        assert result is not None
        assert result.misconception_category is None

    def test_invalid_barrier_type_rejected(self):
        data = {
            "barrier_type": "unknown",
            "misconception_category": None,
            "reasoning": "",
            "suggestion": "",
        }
        assert _validate_and_build(data) is None

    def test_invalid_misconception_category_rejected(self):
        data = {
            "barrier_type": "concept",
            "misconception_category": "invalid_category",
            "reasoning": "",
            "suggestion": "",
        }
        assert _validate_and_build(data) is None

    def test_empty_string_barrier_type_rejected(self):
        data = {
            "barrier_type": "",
            "misconception_category": None,
            "reasoning": "",
            "suggestion": "",
        }
        assert _validate_and_build(data) is None

    def test_missing_barrier_type_rejected(self):
        data = {
            "misconception_category": None,
            "reasoning": "",
            "suggestion": "",
        }
        assert _validate_and_build(data) is None


# ═══════════════════════════════════════════════════════════════
# diagnose_single 端到端测试（Mock LLM）
# ═══════════════════════════════════════════════════════════════

VALID_LLM_RESPONSE = (
    '{"barrier_type": "concept", "misconception_category": "redox", '
    '"reasoning": "学生混淆了氧化剂和还原剂的概念", '
    '"suggestion": "建议通过半反应方程式对比教学强化概念区分"}'
)

RETRY_RESPONSE = (
    '{"barrier_type": "reading", "misconception_category": null, '
    '"reasoning": "学生未注意到题目中过量条件", '
    '"suggestion": "训练审题画关键词习惯"}'
)

INVALID_JSON_RESPONSE = "The barrier type is concept."

MARKDOWN_FENCE_RESPONSE = (
    '```json\n'
    '{"barrier_type": "expression", "misconception_category": "chemical_notation", '
    '"reasoning": "方程式缺少反应条件", "suggestion": "强调反应条件书写规范"}\n'
    '```'
)

TRAILING_COMMA_RESPONSE = (
    '{"barrier_type": "concept", "misconception_category": "mole_calculation", '
    '"reasoning": "摩尔计算错误", "suggestion": "从物质的量基本概念入手",}'
)


@pytest.mark.asyncio
async def test_diagnose_single_success():
    """正常 LLM 返回 → 成功解析。"""
    async def mock_llm(prompt: str) -> str:
        return VALID_LLM_RESPONSE

    result = await diagnose_single(
        mock_llm,
        question_content="2Fe + 3Cl2 = 2FeCl3，该反应中氧化剂是什么？",
        student_answer="Fe",
        correct_answer="Cl2",
    )
    assert result is not None
    assert result.barrier_type == "concept"
    assert result.misconception_category == "redox"


@pytest.mark.asyncio
async def test_diagnose_single_retry_on_bad_json():
    """首次返回非法 JSON → 自动重试成功。"""
    call_count = 0

    async def mock_llm(prompt: str) -> str:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return INVALID_JSON_RESPONSE  # 非 JSON
        return VALID_LLM_RESPONSE  # 重试成功

    result = await diagnose_single(
        mock_llm,
        question_content="测试题目",
        student_answer="错误答案",
        correct_answer="正确答案",
    )
    assert result is not None
    assert call_count == 2  # 确认触发了重试


@pytest.mark.asyncio
async def test_diagnose_single_retry_exhausted():
    """两次都返回非法 JSON → 返回 None。"""
    async def mock_llm(prompt: str) -> str:
        return INVALID_JSON_RESPONSE

    result = await diagnose_single(
        mock_llm,
        question_content="测试",
        student_answer="错误",
        correct_answer="正确",
    )
    assert result is None


@pytest.mark.asyncio
async def test_diagnose_single_markdown_fence():
    """LLM 返回 markdown 包裹的 JSON → 剥离后成功解析。"""
    async def mock_llm(prompt: str) -> str:
        return MARKDOWN_FENCE_RESPONSE

    result = await diagnose_single(
        mock_llm,
        question_content="测试",
        student_answer="错误",
        correct_answer="正确",
    )
    assert result is not None
    assert result.barrier_type == "expression"
    assert result.misconception_category == "chemical_notation"


@pytest.mark.asyncio
async def test_diagnose_single_trailing_comma():
    """LLM JSON 含尾部逗号 → repair 后成功解析。"""
    async def mock_llm(prompt: str) -> str:
        return TRAILING_COMMA_RESPONSE

    result = await diagnose_single(
        mock_llm,
        question_content="测试",
        student_answer="错误",
        correct_answer="正确",
    )
    assert result is not None
    assert result.barrier_type == "concept"
    assert result.misconception_category == "mole_calculation"


@pytest.mark.asyncio
async def test_diagnose_single_with_history():
    """传入历史错题上下文 → 正常诊断。"""
    async def mock_llm(prompt: str) -> str:
        # 验证 prompt 包含历史错题信息
        assert "历史错题" in prompt
        return VALID_LLM_RESPONSE

    history = [
        {"content": "题目1", "answer": "A", "correct": "B"},
        {"content": "题目2", "answer": "C", "correct": "D"},
    ]
    result = await diagnose_single(
        mock_llm,
        question_content="测试题目",
        student_answer="错误答案",
        correct_answer="正确答案",
        history=history,
    )
    assert result is not None


@pytest.mark.asyncio
async def test_diagnose_single_llm_exception():
    """LLM 调用抛出异常 → 重试后仍失败 → 返回 None。"""
    async def mock_llm(prompt: str) -> str:
        raise RuntimeError("网络错误")

    result = await diagnose_single(
        mock_llm,
        question_content="测试",
        student_answer="错误",
        correct_answer="正确",
    )
    assert result is None


# ═══════════════════════════════════════════════════════════════
# diagnose_batch 批量测试
# ═══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_diagnose_batch_all_success():
    """10 条全成功 → analyzed_count=10, failed_count=0。"""
    async def mock_llm(prompt: str) -> str:
        return VALID_LLM_RESPONSE

    batch = [
        {
            "question_content": f"题目{i}",
            "student_answer": f"答案{i}",
            "correct_answer": f"正确{i}",
            "history": [],
        }
        for i in range(10)
    ]

    results, failed = await diagnose_batch(mock_llm, batch)
    assert len(results) == 10
    assert failed == 0


@pytest.mark.asyncio
async def test_diagnose_batch_partial_failure():
    """部分失败 → 部分成功写入。

    用 question_content 中的 marker 控制失败：
    "FAIL" marker 的项返回非法 JSON（两次都非法，避免重试救回）。
    """
    async def mock_llm(prompt: str) -> str:
        if "FAIL" in prompt:
            return "not json at all"
        return VALID_LLM_RESPONSE

    batch = []
    for i in range(6):
        marker = "FAIL" if i < 2 else "OK"
        batch.append({
            "question_content": f"{marker}题目{i}",
            "student_answer": f"答案{i}",
            "correct_answer": f"正确{i}",
            "history": [],
        })

    results, failed = await diagnose_batch(mock_llm, batch)
    assert len(results) == 4  # 4 OK items succeed
    assert failed == 2         # 2 FAIL items fail + retries fail


@pytest.mark.asyncio
async def test_diagnose_batch_exceeds_limit():
    """超过 10 条 → 只处理前 10 条。"""
    async def mock_llm(prompt: str) -> str:
        return VALID_LLM_RESPONSE

    batch = [
        {
            "question_content": f"题目{i}",
            "student_answer": f"答案{i}",
            "correct_answer": f"正确{i}",
            "history": [],
        }
        for i in range(15)
    ]

    results, failed = await diagnose_batch(mock_llm, batch)
    assert len(results) == 10  # 只处理 10 条


@pytest.mark.asyncio
async def test_diagnose_batch_empty():
    """空列表 → 返回空。"""
    async def mock_llm(prompt: str) -> str:
        return VALID_LLM_RESPONSE

    results, failed = await diagnose_batch(mock_llm, [])
    assert results == []
    assert failed == 0


@pytest.mark.asyncio
async def test_diagnose_batch_concurrency_order():
    """验证并发执行：Semaphore 控制并发数，结果按 task 顺序收集。"""
    running = [0]
    max_running = [0]

    async def mock_llm(prompt: str) -> str:
        running[0] += 1
        max_running[0] = max(max_running[0], running[0])
        await asyncio.sleep(0.01)
        running[0] -= 1
        return VALID_LLM_RESPONSE

    batch = [{"question_content": f"Q{i}", "student_answer": "A", "correct_answer": "C", "history": []} for i in range(10)]

    results, _ = await diagnose_batch(mock_llm, batch)
    assert len(results) == 10
    assert max_running[0] <= 5  # Semaphore 限制


# ═══════════════════════════════════════════════════════════════
# Prompt 构建测试
# ═══════════════════════════════════════════════════════════════

class TestPrompt:
    def test_system_prompt_contains_all_barrier_types(self):
        assert "concept" in SYSTEM_PROMPT
        assert "reading" in SYSTEM_PROMPT
        assert "expression" in SYSTEM_PROMPT

    def test_system_prompt_contains_all_misconception_categories(self):
        assert "chemical_equilibrium" in SYSTEM_PROMPT
        assert "redox" in SYSTEM_PROMPT
        assert "mole_calculation" in SYSTEM_PROMPT
        assert "organic_chemistry" in SYSTEM_PROMPT
        assert "chemical_notation" in SYSTEM_PROMPT
        assert "structure_of_matter" in SYSTEM_PROMPT
