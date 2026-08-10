"""答案解析器 — 从 OCR 文本中提取结构化学生答案。

P2: 正则 + LLM 混合策略（tasks 5.1-5.3）
- 选择题：纯正则提取，零 LLM 调用
- 非选择题：单次 LLM 批量提取
"""

import json
import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ParsedAnswer:
    """单题答案。"""
    q_number: int
    student_answer: str
    question_type: str = "choice"  # choice | fill | calculation | experiment
    confidence: float = 1.0


@dataclass
class ParseResult:
    """答案解析结果。"""
    answers: list[ParsedAnswer] = field(default_factory=list)
    total_found: int = 0
    total_expected: int = 0
    is_partial: bool = False
    raw_text: str = ""


# ═══════════════════════════════════════════════════════════════
# 5.2: 选择题正则提取
# ═══════════════════════════════════════════════════════════════

CHOICE_PATTERN = re.compile(r"(\d{1,3})\s*[.、．]\s*([A-Da-d])", re.MULTILINE)


def _parse_choice_answers(raw_text: str) -> list[ParsedAnswer]:
    """纯正则提取选择题答案。

    匹配格式：题号. 选项字母
    - "1. C  2. B  3. A"
    - "1、D  2、C"
    - "11.B  12.A 13.D"
    """
    answers = []
    seen_numbers = set()

    for m in CHOICE_PATTERN.finditer(raw_text):
        q_num = int(m.group(1))
        option = m.group(2).upper()

        # 去重（同一题号只保留第一次出现）
        if q_num not in seen_numbers:
            seen_numbers.add(q_num)
            answers.append(ParsedAnswer(
                q_number=q_num,
                student_answer=option,
                question_type="choice",
                confidence=0.99,
            ))

    return sorted(answers, key=lambda a: a.q_number)


# ═══════════════════════════════════════════════════════════════
# 5.3: 非选择题 LLM 辅助提取
# ═══════════════════════════════════════════════════════════════

NON_CHOICE_EXTRACTION_PROMPT = """你是一个化学答题卡解析器。从以下 OCR 识别文本中提取所有非选择题（填空题、计算题、实验题）的答案。

OCR 文本：
---
{ocr_text}
---

要求：
1. 找出所有题号（数字后跟 . 或 、或 ））
2. 提取每个题号后面的答案内容
3. 答案可能包含：化学式（H₂O, Fe³⁺）、方程式（2H₂ + O₂ → 2H₂O）、数字、文字说明
4. 跳过已经提取过的选择题答案

请返回 JSON 格式：
```json
{{
  "answers": [
    {{"q_number": 16, "student_answer": "H₂O", "question_type": "fill"}},
    {{"q_number": 17, "student_answer": "氧化还原反应", "question_type": "fill"}}
  ]
}}
```

如果找不到非选择题答案，返回空数组 []."""


async def _parse_complex_answers(raw_text: str, choice_count: int = 0) -> list[ParsedAnswer]:
    """LLM 辅助提取非选择题答案。

    在选择题正则提取后，用一次 LLM 调用提取剩余的非选择题答案。
    """
    from ..llm.router import llm_chat

    prompt = NON_CHOICE_EXTRACTION_PROMPT.format(ocr_text=raw_text[:4000])  # 截断保护

    try:
        response = await llm_chat(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            json_mode=True,
        )

        # 解析 JSON 响应
        # 尝试提取 JSON 块
        json_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", response)
        if json_match:
            response = json_match.group(1)

        data = json.loads(response)
        answers_data = data.get("answers", [])

        answers = []
        seen_numbers = set(range(1, choice_count + 1))  # 跳过选择题号
        for item in answers_data:
            q_num = item.get("q_number", 0)
            if q_num and q_num not in seen_numbers:
                seen_numbers.add(q_num)
                answers.append(ParsedAnswer(
                    q_number=q_num,
                    student_answer=str(item.get("student_answer", "")).strip(),
                    question_type=item.get("question_type", "fill"),
                    confidence=0.85,  # LLM 提取的置信度
                ))

        return sorted(answers, key=lambda a: a.q_number)

    except Exception as e:
        logger.warning("[answer_parser] LLM 非选择题提取失败: %s", e)
        return []


# ═══════════════════════════════════════════════════════════════
# 5.1: 主解析入口
# ═══════════════════════════════════════════════════════════════

async def parse_answers_from_text(
    raw_text: str,
    question_count: int = 0,
) -> ParseResult:
    """从 OCR 文本中提取结构化答案。

    流程：预处理 → 选择题正则提取 → 非选择题 LLM 辅助提取 → 合并校验。

    Args:
        raw_text: OCR 原始文本
        question_count: 预期题目总数（0=不校验）

    Returns:
        ParseResult: 包含所有提取到的答案
    """
    # 预处理：去多余空白、统一标点
    cleaned = raw_text.strip()

    # 5.2: 选择题正则提取
    choice_answers = _parse_choice_answers(cleaned)
    logger.info("[answer_parser] 正则提取到 %d 道选择题", len(choice_answers))

    # 5.3: 非选择题 LLM 提取
    remaining = question_count - len(choice_answers) if question_count > 0 else 0
    complex_answers = []
    if remaining > 0 or question_count == 0:
        complex_answers = await _parse_complex_answers(cleaned, len(choice_answers))
        logger.info("[answer_parser] LLM 提取到 %d 道非选择题", len(complex_answers))

    # 合并 + 校验
    all_answers = choice_answers + complex_answers
    all_answers.sort(key=lambda a: a.q_number)

    is_partial = False
    if question_count > 0 and len(all_answers) < question_count:
        is_partial = True
        logger.warning(
            "[answer_parser] 部分提取: 预期 %d 题, 实际 %d 题",
            question_count, len(all_answers),
        )

    return ParseResult(
        answers=all_answers,
        total_found=len(all_answers),
        total_expected=question_count,
        is_partial=is_partial,
        raw_text=cleaned,
    )
