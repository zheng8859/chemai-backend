"""诊断工具集（7 个）— 教师端学情诊断与学习计划。

所有工具通过 @register_tool 注册，调用已有 Service 层。
"""

import logging

from app.infrastructure.database import MainSession
from app.services.diagnosis_service import DiagnosisService
from app.services.panel_service import PanelService
from app.services.learning_plan_service import LearningPlanService
from app.services.adaptive_practice_service import AdaptivePracticeService
from app.services.notification_service import NotificationService

from .tool_meta import register_tool

logger = logging.getLogger(__name__)


@register_tool(
    name="diagnose_barrier",
    persona=["teacher", "parent"],
    call_limit=10,
    prerequisites=["student_id"],
    description="诊断指定学生的学习障碍类型（概念/审题/表述三维度），返回障碍画像。",
)
async def diagnose_barrier(student_id: int) -> dict:
    """诊断学生学习障碍。"""
    async with MainSession() as db:
        svc = DiagnosisService(db)
        diagnosis = await svc.get_student_diagnosis(db, student_id)
        return {
            "student_id": student_id,
            "barrier_profile": diagnosis.get("barrier_profile", {}),
            "weak_points": diagnosis.get("weak_knowledge_points", []),
            "updated_at": diagnosis.get("updated_at"),
        }


@register_tool(
    name="show_diagnosis",
    persona=["teacher"],
    call_limit=5,
    description="触发前端诊断面板——展示班级整体障碍分布柱状图、Top5 薄弱知识点、需关注学生列表。",
)
async def show_diagnosis(class_id: int) -> dict:
    """打开诊断面板。"""
    async with MainSession() as db:
        svc = PanelService(db)
        overview = await svc.get_class_overview(db, class_id)
        return {
            "_component": {
                "type": "diagnosis",
                "action": "open",
                "data": overview,
            },
            "message": "诊断面板已打开。",
        }


@register_tool(
    name="show_students",
    persona=["teacher"],
    call_limit=5,
    description="触发前端学生列表面板——展示班级学生列表，可按姓名搜索、按障碍类型筛选。",
)
async def show_students(class_id: int = 0, keyword: str = "") -> dict:
    """打开学生列表面板。"""
    return {
        "_component": {
            "type": "student-list",
            "action": "open",
            "class_id": class_id,
            "keyword": keyword,
        },
        "message": f"学生列表已打开{'，搜索：' + keyword if keyword else ''}。",
    }


@register_tool(
    name="weekly_report",
    persona=["teacher", "parent"],
    call_limit=5,
    description="生成班级/学生周报。包含练习次数、正确率趋势、薄弱知识点变化。",
)
async def weekly_report(student_id: int = 0, class_id: int = 0) -> dict:
    """生成周报。"""
    async with MainSession() as db:
        svc = PanelService(db)
        if student_id:
            detail = await svc.get_student_detail(db, class_id or 0, student_id)
            return {"report": detail, "scope": "student", "student_id": student_id}
        else:
            overview = await svc.get_class_overview(db, class_id)
            return {"report": overview, "scope": "class", "class_id": class_id}


@register_tool(
    name="assign_adaptive_practice",
    persona=["teacher"],
    call_limit=10,
    requires_approval=True,
    prerequisites=["student_id", "knowledge_point"],
    description="为学生分配自适应练习题（需教师确认）。基于 ZPD 和间隔复习算法选题。",
)
async def assign_adaptive_practice(
    student_id: int,
    knowledge_point: str,
    count: int = 5,
) -> dict:
    """分配自适应练习。"""
    async with MainSession() as db:
        svc = AdaptivePracticeService(db)
        practice = await svc.create_practice(
            db, student_id, question_count=count, kp_override=knowledge_point
        )
        return {
            "practice_id": practice.id,
            "status": practice.status.value if hasattr(practice.status, 'value') else str(practice.status),
        }


@register_tool(
    name="generate_learning_plan",
    persona=["teacher"],
    call_limit=10,
    prerequisites=["student_id"],
    description="为指定学生生成个性化学习计划。基于障碍画像和薄弱知识点。",
)
async def generate_learning_plan(student_id: int, teacher_id: int) -> dict:
    """生成学习计划。"""
    async with MainSession() as db:
        svc = LearningPlanService(db)
        data = {"student_id": student_id, "title": "个性化学习计划"}
        plan = await svc.create_plan(db, data, teacher_id)
        return {
            "plan_id": plan.id,
            "title": getattr(plan, 'title', ''),
            "status": str(plan.status) if hasattr(plan, 'status') else 'created',
        }


@register_tool(
    name="send_learning_plan",
    persona=["teacher"],
    call_limit=10,
    requires_approval=True,
    prerequisites=["plan_id", "student_id"],
    description="将学习计划发送给学生（需教师确认）。",
)
async def send_learning_plan(plan_id: int, student_id: int) -> dict:
    """发送学习计划给学生。"""
    async with MainSession() as db:
        svc = NotificationService(db)
        await svc.create_notification(
            db, student_id,
            type_="plan_updated",
            title="新的学习计划",
            body=f"教师为你制定了新的学习计划（ID: {plan_id}），请查看。",
            related_id=plan_id,
        )
        return {"status": "sent", "plan_id": plan_id, "student_id": student_id}
