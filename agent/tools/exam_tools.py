"""出题工具集（7 个）— 教师端题库管理与题目生成。

所有工具通过 @register_tool 注册，调用已有 Service 层。
"""

import logging

from app.infrastructure.database import MainSession
from app.services.question_bank_service import QuestionBankService
from app.services import question_generation_service

from .tool_meta import register_tool

logger = logging.getLogger(__name__)


@register_tool(
    name="search_exam_bank",
    persona=["teacher", "tutor"],
    call_limit=20,
    description="三级搜索题库：知识点→章节→题型。传入 keyword 和可选的 knowledge_point、section、question_type 进行搜索。",
)
async def search_exam_bank(
    keyword: str = "",
    knowledge_point: str = "",
    question_type: str = "",
    limit: int = 20,
) -> dict:
    """搜索题库。"""
    async with MainSession() as db:
        svc = QuestionBankService(db)
        # list_items 按 question_set 查询，此处做关键词全文搜索
        # 实际生产环境应使用向量检索或全文索引
        items = await svc.list_items(db, set_id=None)
        # 客户端过滤
        filtered = []
        for item in items:
            if keyword and keyword.lower() not in (item.stem or "").lower():
                continue
            if knowledge_point and knowledge_point != item.knowledge_point:
                continue
            if question_type and question_type != item.question_type:
                continue
            filtered.append({
                "id": item.id if hasattr(item, 'id') else 0,
                "stem": (item.stem or "")[:200],
                "type": item.question_type if hasattr(item, 'question_type') else "",
                "difficulty": item.difficulty if hasattr(item, 'difficulty') else "",
                "knowledge_point": item.knowledge_point if hasattr(item, 'knowledge_point') else "",
            })
            if len(filtered) >= limit:
                break
        return {"items": filtered, "total": len(filtered)}


@register_tool(
    name="web_search",
    persona=["teacher", "tutor", "student"],
    call_limit=10,
    description="联网搜索化学资料并返回摘要。用于查找化学概念解释、实验方案、题目背景等。",
)
async def web_search(query: str) -> dict:
    """联网搜索化学资料。"""
    logger.info("web_search: %s", query)
    return {
        "results": [],
        "summary": f"关于「{query}」的搜索结果（联网搜索功能即将上线）",
    }


@register_tool(
    name="show_exam_workbench",
    persona=["teacher", "tutor"],
    call_limit=5,
    description="触发前端出题工作台面板（4 Tab：出题/题库/考试/OCR）。不执行业务逻辑，只返回 _component 标记。",
)
async def show_exam_workbench() -> dict:
    """打开出题工作台面板。"""
    return {
        "_component": {
            "type": "exam-workbench",
            "action": "open",
            "tabs": ["generate", "bank", "exam", "ocr"],
        },
        "message": "出题工作台已打开，您可以在面板中进行操作。",
    }


@register_tool(
    name="save_to_bank",
    persona=["teacher"],
    call_limit=30,
    description="将题目写入题库。必须提供 stem（题干）、answer（答案）、question_type（题型）。",
)
async def save_to_bank(
    stem: str,
    answer: str,
    question_type: str,
    difficulty: str = "medium",
    knowledge_point: str = "",
    section: str = "",
    options: str = "",
    analysis: str = "",
) -> dict:
    """将题目保存到题库。"""
    async with MainSession() as db:
        svc = QuestionBankService(db)
        data = {
            "stem": stem,
            "answer": answer,
            "question_type": question_type,
            "difficulty": difficulty,
            "knowledge_point": knowledge_point,
            "section": section,
            "options": options,
            "analysis": analysis,
        }
        item = await svc.add_item(db, data)
        return {"item_id": item.id if hasattr(item, 'id') else 0, "status": "saved"}


@register_tool(
    name="generate_questions",
    persona=["teacher"],
    call_limit=10,
    description="LLM 生成题目并自动过四维审核。传入 knowledge_points 和 quantity，返回带审核结果的题目列表。",
)
async def generate_questions(
    knowledge_points: str,
    quantity: int = 3,
    difficulty: str = "medium",
) -> dict:
    """LLM 生成题目并自动审核。"""
    async with MainSession() as db:
        result = await question_generation_service.generate_questions(
            db=db,
            knowledge_points=[kp.strip() for kp in knowledge_points.split(",")],
            difficulty=difficulty,
            quantity=min(quantity, 5),
        )
        questions = result.get("questions", [])
        return {
            "questions": questions,
            "audit_summary": {
                "total": len(questions),
                "passed": sum(1 for q in questions if q.get("audit_passed", False)),
            },
        }


@register_tool(
    name="list_banks",
    persona=["teacher"],
    call_limit=10,
    description="列出当前教师的所有题库（question sets），返回 ID、名称、题目数量。",
)
async def list_banks() -> dict:
    """列出可用题库。"""
    async with MainSession() as db:
        svc = QuestionBankService(db)
        sets = await svc.list_question_sets(db)
        return {
            "banks": [{"id": s.id, "name": s.name, "item_count": getattr(s, 'item_count', 0)}
                      for s in sets],
            "total": len(sets),
        }


@register_tool(
    name="delete_bank",
    persona=["teacher"],
    call_limit=3,
    requires_approval=True,
    prerequisites=["bank_id"],
    description="删除题库（危险操作，需教师审批确认）。传入 bank_id 指定要删除的题库。",
)
async def delete_bank(bank_id: int) -> dict:
    """删除题库。"""
    async with MainSession() as db:
        svc = QuestionBankService(db)
        await svc.delete_question_set(db, bank_id)
        return {"status": "deleted", "bank_id": bank_id}
