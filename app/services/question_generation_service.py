"""AI 出题生成服务 — 完整管线（25号文档 §三）。

管线步骤（Mode 1: AI 生成）:
  0. RAG 检索 — 从历史真题库向量/关键词检索相似题目
  1. LLM 生成 — 构造 3 层 Prompt，调用 LLM fallback 路由
  2. JSON 解析 — 解析 LLM 返回的题目数组
  3. 方程式审核 — 每道题经四维安全审核引擎校验
  4. 持久化 — 审核通过的题目写入数据库
"""

import json
import logging
import re

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..llm.router import llm_chat
from ..models.question_bank import HistoricalExam
from ..models.teaching import Question
from ..schemas.teaching import QuestionRead

from chem_skills.chemistry_parser.engine import (
    audit_equation,
    extract_equations,
    AuditReport,
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# System Prompt (25号 §三.1.2 第一层 + 第二层)
# ═══════════════════════════════════════════════════════════════

SYSTEM_PROMPT = """你是一位资深高中化学教师，专门为高中学生设计高质量的化学试题。

## 格式规范（必须严格遵守）

1. 所有化学式、离子式和方程式必须用 $...$ LaTeX 行内公式包裹。例如：$H_2O$、$Fe^{3+}$
2. 下标用 _ 表示，上标用 ^ 表示，元素符号首字母大写。例如：$Fe_2O_3$、$SO_4^{2-}$
3. 方程式箭头用 \\rightarrow，可逆反应用 \\rightleftharpoons。例如：$2H_2 + O_2 \\rightarrow 2H_2O$
4. 反应条件用 \\xrightarrow{条件}，加热用 \\xrightarrow{\\triangle}
5. 中文正文中嵌入的化学式也必须用 $ 包裹

## 题型要求

- choice（选择题）：提供4个选项（A/B/C/D），标注正确答案，设置1-2个陷阱选项
- fill_blank（填空题）：用下划线标记填空位置，答案仅包含填空内容，每道题可有1-3个空
- calculation（计算题）：给出具体数值条件，答案须含分步计算过程
- experiment_inquiry（实验题）：描述化学实验情境并包含2-3个子问题
- equation_balancing（方程式配平）：推断题形式给出物质转化线索

## 输出格式

必须返回严格的 JSON 对象，格式如下：
{
  "questions": [
    {
      "content": "题目正文（$...$LaTeX格式）",
      "question_type": "choice",
      "options": ["A. 选项1", "B. 选项2", "C. 选项3", "D. 选项4"],
      "answer": "D",
      "analysis": "解析内容",
      "knowledge_point_tags": ["知识点1", "知识点2"],
      "difficulty": "medium"
    }
  ]
}

options 字段仅选择题需要。其他题型的 options 设为空数组 []。
"""


# ═══════════════════════════════════════════════════════════════
# Public API
# ═══════════════════════════════════════════════════════════════

async def generate_questions(
    db: AsyncSession,
    knowledge_points: list[str],
    difficulty: str = "medium",
    quantity: int = 3,
    question_types: list[str] | None = None,
    exam_type: str = "",
    variant_qid: str = "",
) -> dict:
    """执行完整的 AI 出题管线。

    Args:
        db: 数据库会话
        knowledge_points: 目标知识点列表
        difficulty: 难度等级
        quantity: 生成数量
        question_types: 题型列表
        exam_type: 考试类型描述
        variant_qid: 变体蓝本题 ID

    Returns:
        {
            "success": true,
            "questions": [QuestionRead, ...],
            "generated_count": N,
            "audit_reports": [dict, ...],
            "total_available": N
        }
    """
    types = question_types or ["choice"]
    type_desc = _describe_types(types)

    # ── Step 0: RAG 检索 ──
    rag_context = await _rag_search(db, knowledge_points, difficulty, variant_qid)

    # ── Step 1: LLM 生成 ──
    user_prompt = _build_user_prompt(
        knowledge_points, difficulty, quantity, type_desc, rag_context
    )
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    try:
        raw_response = await llm_chat(messages, json_mode=True, temperature=0.4)
    except Exception as e:
        logger.error(f"LLM 调用失败: {e}")
        return {
            "success": False,
            "warning": f"LLM 调用失败: {e}",
            "questions": [],
            "generated_count": 0,
        }

    # ── Step 2: JSON 解析 ──
    questions_data = _parse_llm_response(raw_response)
    if not questions_data:
        return {
            "success": False,
            "warning": "LLM 返回的 JSON 无法解析",
            "questions": [],
            "generated_count": 0,
            "raw_response": raw_response[:500],
        }

    # ── Step 3-5: 审核 + 重试循环（HARD BLOCK 红线）──
    MAX_RETRIES = 3
    passed_questions: list[dict] = []
    blocked_count = 0

    for q_data in questions_data:
        # 四维审核
        eqs = extract_equations(q_data.get("content", ""))
        is_blocked = False
        for eq in eqs:
            report = audit_equation(eq)
            if report.overall_status == "blocked":
                is_blocked = True
                break

        if is_blocked:
            blocked_count += 1
            # 尝试重新生成（最多 MAX_RETRIES 次）
            for retry in range(MAX_RETRIES):
                try:
                    retry_prompt = (
                        f"之前生成的题目中化学方程式审核不通过，请重新生成一道。\n"
                        f"知识点：{'、'.join(knowledge_points)}\n"
                        f"难度：{difficulty}\n"
                        f"注意：化学方程式必须配平，且符合 LaTeX 格式规范。"
                    )
                    retry_response = await llm_chat(
                        [{"role": "system", "content": SYSTEM_PROMPT},
                         {"role": "user", "content": retry_prompt}],
                        json_mode=True, temperature=0.5,
                    )
                    retry_data = _parse_llm_response(retry_response)
                    if retry_data:
                        q_data = retry_data[0]
                        # 再次审核
                        eqs2 = extract_equations(q_data.get("content", ""))
                        blocked_again = any(
                            audit_equation(e).overall_status == "blocked"
                            for e in eqs2
                        )
                        if not blocked_again:
                            is_blocked = False
                            break
                except Exception:
                    continue

        if not is_blocked:
            # 陷阱提示
            kps = q_data.get("knowledge_point_tags", [])
            analysis = q_data.get("analysis", "") or ""
            hints = _generate_trap_hints(kps)
            if hints:
                analysis += "\n\n【教学提示】\n" + "\n".join(f"- {h}" for h in hints)

            # 持久化（只有审核通过的题目才入库）
            question = Question(
                content=q_data.get("content", ""),
                question_type=q_data.get("question_type", "choice"),
                options=q_data.get("options", []),
                answer=q_data.get("answer", ""),
                analysis=analysis,
                knowledge_point_tags=q_data.get("knowledge_point_tags", []),
                difficulty=q_data.get("difficulty", difficulty),
                source="ai_generated",
                audit_status="passed",
            )
            db.add(question)
            await db.flush()
            passed_questions.append(QuestionRead.model_validate(question))

    await db.commit()

    rag_mark = _build_rag_mark(rag_context, variant_qid)

    return {
        "success": True,
        "questions": passed_questions,
        "generated_count": len(passed_questions),
        "total_available": await _count_available(db, knowledge_points),
        "rag_mark": rag_mark,
        "audit_summary": {
            "total_equations_checked": len(questions_data),
            "blocked": blocked_count,
            "retry_success": blocked_count - sum(
                1 for q in questions_data
                if not any(
                    audit_equation(e).overall_status == "blocked"
                    for e in extract_equations(q.get("content", ""))
                )
            ) if blocked_count > 0 else 0,
        },
    }


# ═══════════════════════════════════════════════════════════════
# Internal: RAG
# ═══════════════════════════════════════════════════════════════

async def _rag_search(
    db: AsyncSession,
    knowledge_points: list[str],
    difficulty: str,
    variant_qid: str = "",
) -> str:
    """从历史真题库检索相似题目作为 RAG 上下文。

    Returns:
        格式化的真题参考文本，若无结果则返回空字符串
    """
    if variant_qid:
        # 直接取蓝本题
        result = await db.execute(
            select(HistoricalExam).where(HistoricalExam.id == variant_qid)
        )
        exam = result.scalar_one_or_none()
        if exam:
            return _format_rag_results([exam])

    # 按知识点 + 难度检索
    conditions = []
    if difficulty:
        conditions.append(HistoricalExam.difficulty == difficulty)

    query = select(HistoricalExam)
    if conditions:
        for c in conditions:
            query = query.where(c)
    query = query.order_by(HistoricalExam.year.desc()).limit(5)

    result = await db.execute(query)
    exams = result.scalars().all()
    return _format_rag_results(exams)


def _format_rag_results(exams: list[HistoricalExam]) -> str:
    """格式化真题检索结果为 Prompt 文本。"""
    if not exams:
        return ""
    lines = ["## 参考真题\n"]
    for i, exam in enumerate(exams, 1):
        lines.append(f"{i}. [{exam.source} {exam.year}] {exam.content[:200]}")
        lines.append(f"   答案: {exam.answer}")
        if exam.analysis:
            lines.append(f"   解析: {exam.analysis[:100]}")
        lines.append("")
    return "\n".join(lines)


async def _count_available(db: AsyncSession, knowledge_points: list[str]) -> int:
    """统计可用题目数。"""
    result = await db.execute(select(HistoricalExam))
    return len(result.scalars().all())


# ═══════════════════════════════════════════════════════════════
# Internal: Prompt
# ═══════════════════════════════════════════════════════════════

def _describe_types(types: list[str]) -> str:
    """将题型代码转为中文描述。"""
    mapping = {
        "choice": "选择题（4选项）",
        "fill_blank": "填空题（1-3个空）",
        "calculation": "计算题（分步计算）",
        "experiment_inquiry": "实验探究题（2-3个子问题）",
        "equation_balancing": "方程式配平/推断题",
    }
    return "、".join(mapping.get(t, t) for t in types)


def _build_user_prompt(
    knowledge_points: list[str],
    difficulty: str,
    quantity: int,
    type_desc: str,
    rag_context: str,
) -> str:
    """构造 User Prompt（25号 §三.1.2 第三层）。"""
    diff_map = {"easy": "基础", "medium": "中等", "hard": "困难"}

    if rag_context:
        prompt = (
            f"基于以下真题生成 {quantity} 道变种题。\n\n"
            f"{rag_context}\n"
            f"要求：难度为{diff_map.get(difficulty, '中等')}，题型为{type_desc}。"
            f"知识点覆盖：{'、'.join(knowledge_points)}。\n"
            f"直接返回 JSON 格式。"
        )
    else:
        prompt = (
            f"为以下知识点生成 {quantity} 道{diff_map.get(difficulty, '中等')}难度的{type_desc}。\n\n"
            f"知识点：{'、'.join(knowledge_points)}\n"
            f"直接返回 JSON 格式。"
        )

    return prompt


# ═══════════════════════════════════════════════════════════════
# Internal: Parsing
# ═══════════════════════════════════════════════════════════════

def _parse_llm_response(raw: str) -> list[dict]:
    """解析 LLM 返回的 JSON，提取 questions 数组。"""
    # 尝试直接解析
    try:
        data = json.loads(raw)
        return data.get("questions", [])
    except json.JSONDecodeError:
        pass

    # 尝试提取 ```json ... ``` 代码块
    match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', raw)
    if match:
        try:
            data = json.loads(match.group(1))
            return data.get("questions", [])
        except json.JSONDecodeError:
            pass

    # 尝试查找 JSON 对象
    match = re.search(r'\{[\s\S]*"questions"[\s\S]*\}', raw)
    if match:
        try:
            data = json.loads(match.group(0))
            return data.get("questions", [])
        except json.JSONDecodeError:
            pass

    return []


# ═══════════════════════════════════════════════════════════════
# Internal: Trap Hints（§3.1.3 Step 5）
# ═══════════════════════════════════════════════════════════════

_TRAP_HINTS: dict[str, str] = {
    "盐类水解": "注意区分'水解'与'电离'的概念——水解是盐的离子与水的反应，电离是电解质解离为离子",
    "电离": "强电解质完全电离（如NaCl、H2SO4），弱电解质部分电离（如CH3COOH、NH3·H2O）",
    "氧化还原反应": "注意电子转移的方向和数目——氧化剂得电子被还原，还原剂失电子被氧化",
    "原电池": "负极发生氧化反应（失电子），正极发生还原反应（得电子），电子由负极流向正极",
    "电解池": "阳极发生氧化反应，阴极发生还原反应；阳离子向阴极移动，阴离子向阳极移动",
    "化学平衡": "勒夏特列原理：改变条件时平衡向减弱该改变的方向移动",
    "物质的量": "n=m/M，注意单位换算——摩尔质量单位是g/mol",
    "元素周期律": "同周期从左到右金属性减弱非金属性增强，同族从上到下金属性增强",
    "有机化学": "注意官能团的性质——羟基(-OH)亲水，酯基(-COO-)可水解",
    "酯化反应": "酯化反应是酸和醇生成酯和水，需浓硫酸催化并加热，反应可逆",
    "共价键": "非金属元素之间通常形成共价键，注意极性键与非极性键的区别",
    "离子键": "活泼金属与活泼非金属之间形成离子键，注意电子转移的方向",
    "电解质溶液": "电解质溶液导电靠自由移动的离子，离子浓度越大导电性越强",
}


def _generate_trap_hints(knowledge_points: list[str]) -> list[str]:
    """根据知识点自动生成教学提示。"""
    hints = []
    for kp in knowledge_points:
        for key, hint in _TRAP_HINTS.items():
            if key in kp or kp in key:
                if hint not in hints:
                    hints.append(hint)
    return hints[:3]  # 最多 3 条


# ═══════════════════════════════════════════════════════════════
# Internal: RAG Mark（§4.4）
# ═══════════════════════════════════════════════════════════════

def _build_rag_mark(rag_context: str, variant_qid: str) -> dict | None:
    """构建变体题的 RAG 标记信息。"""
    if not rag_context and not variant_qid:
        return None

    mark = {
        "is_from_rag": bool(rag_context or variant_qid),
    }

    if variant_qid:
        mark["source_question_id"] = variant_qid
        mark["match_method"] = "blueprint"
    elif rag_context:
        mark["match_method"] = "simple"
        # 尝试从 RAG 上下文中提取来源信息
        import re
        source_match = re.search(r'\[([^\]]+)\]', rag_context)
        if source_match:
            mark["source_question_preview"] = source_match.group(0)[:100]

    return mark
