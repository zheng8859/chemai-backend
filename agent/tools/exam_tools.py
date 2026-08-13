"""出题工具集（7 个）— 教师端题库管理与题目生成。

所有工具通过 @register_tool 注册，调用已有 Service 层。
"""

import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import MIMO_API_KEY, MIMO_BASE_URL, MIMO_MODEL
from app.infrastructure.database import MainSession
from app.llm.providers.openai_compat import OpenAICompatProvider
from app.llm.router import llm_chat
from app.models.question_bank import HistoricalExam
from app.models.teaching import Question
from app.services import question_generation_service
from app.services.question_bank_service import QuestionBankService, QuestionBankError
from app.services.vector_search_service import (
    VectorSearchService,
    index_questions,
    search_questions_vector,
)

from .tool_meta import register_tool

logger = logging.getLogger(__name__)

WEB_SUMMARY_MAX_CHARS = 400


# ═══════════════════════════════════════════════════════════════
# 搜索结果格式化
# ═══════════════════════════════════════════════════════════════

def _format_bank_question(q: Question) -> dict:
    """题库题目 → 结果 dict。"""
    return {
        "id": q.id,
        "source": "bank",
        "content": q.content,
        "question_type": q.question_type,
        "difficulty": q.difficulty,
        "knowledge_point_tags": q.knowledge_point_tags or [],
        "answer": q.answer,
    }


def _format_historical(e: HistoricalExam) -> dict:
    """历年真题 → 结果 dict。"""
    return {
        "id": e.id,
        "source": "historical",
        "content": e.content,
        "difficulty": e.difficulty,
        "knowledge_point_tags": e.knowledge_point_tags or [],
        "answer": e.answer,
        "year": e.year,
        "exam_source": e.source,
    }


async def _keyword_match_questions(
    db: AsyncSession,
    keyword: str,
    kps: list[str],
    question_type: str,
    difficulty: str,
    limit: int,
) -> list[Question]:
    """第一层：关键词匹配题库题目（content / knowledge_point_tags / 难度 / 题型）。"""
    query = select(Question)
    if difficulty:
        query = query.where(Question.difficulty == difficulty)
    if question_type:
        query = query.where(Question.question_type == question_type)
    query = query.order_by(Question.created_at.desc()).limit(max(limit * 5, 20))
    result = await db.execute(query)
    questions = result.scalars().all()

    if not keyword and not kps:
        return list(questions[:limit])

    matched = []
    for q in questions:
        haystack = (q.content or "") + " " + " ".join(q.knowledge_point_tags or [])
        kw_hit = bool(keyword) and keyword.lower() in haystack.lower()
        kp_hit = any(kp in (q.knowledge_point_tags or []) for kp in kps)
        if kw_hit or kp_hit:
            matched.append(q)
    return matched[:limit]


async def _all_questions(db: AsyncSession, question_type: str, difficulty: str) -> list[Question]:
    """第二层向量补充的候选池：按难度/题型过滤的全部题目（上限 50）。"""
    query = select(Question)
    if difficulty:
        query = query.where(Question.difficulty == difficulty)
    if question_type:
        query = query.where(Question.question_type == question_type)
    query = query.order_by(Question.created_at.desc()).limit(50)
    result = await db.execute(query)
    return result.scalars().all()


# ═══════════════════════════════════════════════════════════════
# 工具 1: search_exam_bank — 三级搜索
# ═══════════════════════════════════════════════════════════════

@register_tool(
    name="search_exam_bank",
    persona=["teacher", "tutor"],
    call_limit=3,
    description="三级搜索题库：关键词 → 向量 → 联网兜底。传入 keyword 和可选的 knowledge_point、question_type、difficulty。",
)
async def search_exam_bank(
    keyword: str = "",
    knowledge_point: str = "",
    question_type: str = "",
    difficulty: str = "",
    limit: int = 5,
) -> dict:
    """三级搜索题库。"""
    async with MainSession() as db:
        kps = [kp.strip() for kp in (knowledge_point or "").split(",") if kp.strip()]
        query_kps = kps or ([keyword] if keyword else [])
        items: list[dict] = []

        # ── Tier 1: 关键词匹配题库题目 ──
        bank_qs = await _keyword_match_questions(db, keyword, kps, question_type, difficulty, limit)

        # ── Tier 2: 向量补充（题库题目语义精筛 + 历年真题） ──
        if len(bank_qs) < limit:
            existing_ids = {q.id for q in bank_qs}
            pool = [q for q in await _all_questions(db, question_type, difficulty)
                    if q.id not in existing_ids]
            ranked = await search_questions_vector(pool, query_kps, limit - len(bank_qs))
            for q in ranked:
                bank_qs.append(q)
                if len(bank_qs) >= limit:
                    break

        for q in bank_qs[:limit]:
            items.append(_format_bank_question(q))

        # 历年真题补充
        if len(items) < limit:
            hist = await VectorSearchService.search_similar(
                db, query_kps, difficulty, limit=limit - len(items),
            )
            for e in hist:
                items.append(_format_historical(e))

        # ── Tier 3: 联网兜底 ──
        if len(items) < 3 and keyword:
            web = await web_search(keyword)
            items.append({
                "source": "web",
                "label": "AI辅助搜索",
                "summary": web.get("summary", ""),
            })

        return {"items": items, "total": len(items)}


# ═══════════════════════════════════════════════════════════════
# 工具 2: web_search — 联网搜索
# ═══════════════════════════════════════════════════════════════

@register_tool(
    name="web_search",
    persona=["teacher", "tutor", "student", "parent"],
    call_limit=2,
    description="联网搜索化学资料并返回摘要。用于查找化学概念解释、实验方案、题目背景等。",
)
async def web_search(query: str) -> dict:
    """联网搜索化学资料（MiMo search + LLM 摘要）。"""
    logger.info("web_search: %s", query)
    if not MIMO_API_KEY or not MIMO_BASE_URL:
        return {
            "query": query,
            "results": [],
            "summary": f"关于「{query}」的搜索结果（未配置联网搜索服务）",
        }

    try:
        provider = OpenAICompatProvider(
            name="MiMo",
            api_key=MIMO_API_KEY,
            base_url=MIMO_BASE_URL,
            model=MIMO_MODEL,
        )
        raw = await provider.chat(
            [{"role": "user", "content": f"联网搜索：{query}"}],
            temperature=0.2,
            max_tokens=2048,
            enable_search=True,
        )
        raw_text = (raw.get("content") or "").strip()
        if not raw_text:
            return {"query": query, "results": [], "summary": f"关于「{query}」的搜索结果（无结果）"}

        summary = raw_text
        try:
            summary = await llm_chat(
                [
                    {"role": "system", "content": "你是化学资料摘要助手，把下面的联网搜索结果总结成不超过 400 字的摘要，只输出摘要正文。"},
                    {"role": "user", "content": raw_text[:4000]},
                ],
                temperature=0.2,
                max_tokens=600,
            )
        except Exception as e:  # 摘要失败回退原文
            logger.warning("web_search 摘要失败，回退原文: %s", e)

        return {
            "query": query,
            "results": [raw_text[:4000]],
            "summary": (summary or raw_text)[:WEB_SUMMARY_MAX_CHARS],
        }
    except Exception as e:
        logger.warning("web_search 失败，降级: %s", e)
        return {
            "query": query,
            "results": [],
            "summary": f"关于「{query}」的搜索结果（联网搜索暂不可用）",
        }


# ═══════════════════════════════════════════════════════════════
# 工具 3: show_exam_workbench — 内联出题面板
# ═══════════════════════════════════════════════════════════════

@register_tool(
    name="show_exam_workbench",
    persona=["teacher", "tutor"],
    call_limit=3,
    description="触发前端出题工作台面板（4 Tab：出题/题库/考试/OCR）。不执行业务逻辑，只返回 _component 标记。",
)
async def show_exam_workbench() -> dict:
    """打开出题工作台面板。"""
    return {
        "_component": {
            "type": "exam-workbench",
            "props": {},
        },
        "message": "出题工作台已打开，您可以在面板中进行操作。",
    }


# ═══════════════════════════════════════════════════════════════
# 工具 4: save_to_bank — 三实体入库
# ═══════════════════════════════════════════════════════════════

def _auto_bank_name(questions: list[dict]) -> str:
    """根据题目知识点 + 时间自动命名题库文件夹。"""
    kps = sorted({
        kp
        for q in questions
        for kp in (q.get("knowledge_points") or q.get("knowledge_point_tags") or [])
    })
    suffix = ("-" + "、".join(kps[:3])) if kps else ""
    return f"AI出题{suffix} {datetime.now():%m-%d %H:%M}"


@register_tool(
    name="save_to_bank",
    persona=["teacher", "tutor"],
    call_limit=1,
    description="将题目批量写入题库。questions 为题目列表（含 content/answer/question_type/difficulty/knowledge_points），bank_name 可选，不传则自动命名。",
)
async def save_to_bank(
    questions: list[dict],
    teacher_id: int = 0,
    bank_name: str = "",
) -> dict:
    """将题目批量保存到题库。"""
    if not questions:
        return {"status": "skipped", "reason": "questions 为空"}

    name = bank_name or _auto_bank_name(questions)
    async with MainSession() as db:
        try:
            result = await QuestionBankService.save_questions_batch(
                db, name=name, questions=questions, teacher_id=teacher_id,
            )
        except Exception as e:
            logger.exception("save_to_bank 失败")
            return {"status": "error", "reason": str(e)}

        # 增量同步 ChromaDB（提交后）；向量索引失败不影响主流程
        try:
            await index_questions(db, mode="append")
        except Exception as e:
            logger.warning("save_to_bank 向量同步失败，不影响主流程: %s", e)

        return {
            "status": "saved",
            "bank_id": result["bank_id"],
            "bank_name": result["bank_name"],
            "saved_count": result["saved_count"],
            "question_ids": result["question_ids"],
            "_route": {"page": "exam-v2", "params": {"bank_id": result["bank_id"]}},
        }


# ═══════════════════════════════════════════════════════════════
# 工具 5: generate_questions — LLM 出题 + 四维审核
# ═══════════════════════════════════════════════════════════════

@register_tool(
    name="generate_questions",
    persona=["teacher", "tutor"],
    call_limit=5,
    description="LLM 生成题目并自动过四维审核。传入 knowledge_points、quantity、difficulty，可选 question_types、variant_qid。",
)
async def generate_questions(
    knowledge_points: str,
    quantity: int = 3,
    difficulty: str = "medium",
    question_types: list[str] | None = None,
    variant_qid: str = "",
) -> dict:
    """LLM 生成题目并自动审核。"""
    async with MainSession() as db:
        result = await question_generation_service.generate_questions(
            db=db,
            knowledge_points=[kp.strip() for kp in knowledge_points.split(",") if kp.strip()],
            difficulty=difficulty,
            quantity=min(quantity, 5),
            question_types=question_types,
            variant_qid=variant_qid,
        )
        questions = result.get("questions", [])
        audit = result.get("audit_summary", {})
        return {
            "questions": [q.model_dump() for q in questions],
            "generated_count": result.get("generated_count", len(questions)),
            "audit_summary": {
                "total": len(questions),
                "passed": sum(
                    1 for q in questions if str(getattr(q, "audit_status", "")) == "passed"
                ),
                "blocked": audit.get("blocked", 0),
            },
            "rag_mark": result.get("rag_mark"),
        }


# ═══════════════════════════════════════════════════════════════
# 工具 6: list_banks — 题库列表
# ═══════════════════════════════════════════════════════════════

@register_tool(
    name="list_banks",
    persona=["teacher", "tutor"],
    call_limit=1,
    description="列出当前教师的所有题库（question sets），返回 ID、名称、题目数量。",
)
async def list_banks() -> dict:
    """列出可用题库。"""
    async with MainSession() as db:
        sets, total = await QuestionBankService.list_question_sets(db)
        return {
            "banks": [{"id": s.id, "name": s.name, "item_count": s.question_count}
                      for s in sets],
            "total": total,
        }


# ═══════════════════════════════════════════════════════════════
# 工具 7: delete_bank — 删除题库（审批）
# ═══════════════════════════════════════════════════════════════

@register_tool(
    name="delete_bank",
    persona=["teacher", "tutor"],
    call_limit=1,
    requires_approval=True,
    prerequisites=["bank_id"],
    description="删除题库（危险操作，需教师审批确认）。传入 bank_id 指定要删除的题库。",
)
async def delete_bank(bank_id: int) -> dict:
    """删除题库。"""
    async with MainSession() as db:
        try:
            await QuestionBankService.delete_question_set(db, bank_id)
            return {"status": "deleted", "bank_id": bank_id}
        except QuestionBankError as e:
            return {"status": "error", "reason": e.detail, "error_code": e.error_code}
