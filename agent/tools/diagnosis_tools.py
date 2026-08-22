"""诊断工具集（7 个）— 教师端学情诊断与学习计划。

所有工具通过 @register_tool 注册，直接调用已有 Service 层的静态方法
（Service 均为无状态静态方法容器，不实例化）。

对齐设计 30 §3.3：diagnose_barrier / weekly_report 对 teacher 与 parent 可用，
其余仅 teacher；assign_adaptive_practice / send_learning_plan 需审批门控。
"""

import json
import logging

from sqlalchemy import select

from app.infrastructure.database import MainSession
from app.llm.router import llm_chat
from app.models.user import Student
from app.models.org import Class
from app.services.diagnosis_service import DiagnosisService, DiagnosisError
from app.services.panel_service import PanelService
from app.services.adaptive_practice_service import (
    AdaptivePracticeService,
    AdaptivePracticeError,
)
from app.services.notification_service import NotificationService

from .tool_meta import register_tool

logger = logging.getLogger(__name__)

# 班级自适应练习：每批学生数（设计 28 决策三「5 人/批」）
CLASS_PRACTICE_BATCH_SIZE = 5

# 周报 LLM 系统提示词
WEEKLY_REPORT_SYSTEM_PROMPT = (
    "你是 ChemAI 智辅化学的教学助手，负责用通俗语言为学生/家长撰写学习周报。"
    "要求：200 字左右；以鼓励为主，不制造焦虑；严格基于给定数据，不编造内容。"
)


def _summarize_practice(student_id: int, practice: dict) -> dict:
    """从 create_practice 返回值抽取每生参数摘要（不含题目明细）。"""
    return {
        "student_id": student_id,
        "practice_id": practice["practice_id"],
        "zpd_difficulty": practice["zpd_difficulty"],
        "dominant_barrier": practice["dominant_barrier"],
        "target_kps": practice["target_kps"],
        "question_count": practice["question_count"],
    }


@register_tool(
    name="diagnose_barrier",
    persona=["teacher", "parent"],
    call_limit=2,
    prerequisite_any_of=[["student_id", "class_id", "student_name"]],
    description="诊断指定学生的学习障碍类型（概念/审题/表述三维度），返回障碍画像。"
    "支持纯数字 ID、中文姓名（模糊匹配，多结果返回候选）或班级级统计。",
)
async def diagnose_barrier(
    student_id: int = 0,
    class_id: int = 0,
    student_name: str = "",
) -> dict:
    """诊断学生学习障碍（个体/班级两级，名称解析）。"""
    async with MainSession() as db:
        # 1. 名称解析优先（支持重名返回候选）
        if student_name.strip():
            candidates = await DiagnosisService.resolve_student_by_identity(
                db, student_name.strip()
            )
            if not candidates:
                return {"scope": "error", "message": f"未找到姓名为「{student_name}」的学生"}
            if len(candidates) > 1:
                return {
                    "scope": "ambiguous",
                    "candidates": [
                        {"student_id": s.id, "name": s.name, "class_id": s.class_id}
                        for s in candidates
                    ],
                }
            sid = candidates[0].id
        elif student_id:
            sid = student_id
        elif class_id:
            # 2. 班级级：全班障碍分布（各障碍为主导的学生人数与占比）
            barriers = await PanelService.get_barriers(db, class_id)
            return {
                "scope": "class",
                "class_id": class_id,
                "barrier_distribution": barriers,
            }
        else:
            return {"scope": "error", "message": "请提供 student_id、class_id 或 student_name 之一"}

        # 3. 个体诊断
        try:
            diagnosis = await DiagnosisService.get_student_diagnosis(db, sid)
        except DiagnosisError:
            return {"scope": "error", "message": f"学生不存在: id={sid}"}

        data = diagnosis.model_dump()
        return {
            "scope": "student",
            "student_id": sid,
            "barrier_profile": data.get("barrier_profile", {}),
            "dominant_type": data.get("dominant_type"),
            "weak_kps": data.get("weak_kps", []),
            "last_diagnosis_date": data.get("last_diagnosis_date"),
        }


@register_tool(
    name="show_diagnosis",
    persona=["teacher"],
    call_limit=1,
    description="触发前端诊断面板——展示班级整体障碍分布柱状图、Top5 薄弱知识点、需关注学生列表。",
)
async def show_diagnosis(class_id: int) -> dict:
    """打开诊断面板。"""
    async with MainSession() as db:
        overview = await PanelService.get_class_overview(db, class_id)
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
    call_limit=1,
    description="触发前端学生列表面板——展示班级学生列表，可按姓名搜索、按障碍类型筛选。",
)
async def show_students(
    class_id: int = 0,
    keyword: str = "",
    barrier: str = "",
) -> dict:
    """打开学生列表面板（barrier 透传至前端筛选）。"""
    return {
        "_component": {
            "type": "student-list",
            "action": "open",
            "class_id": class_id,
            "keyword": keyword,
            "barrier": barrier,
        },
        "message": f"学生列表已打开{'，搜索：' + keyword if keyword else ''}。",
    }


@register_tool(
    name="weekly_report",
    persona=["teacher", "parent"],
    call_limit=2,
    description="生成班级/学生周报。基于面板数据调用 LLM 生成 200 字自然语言周报（鼓励为主）。",
)
async def weekly_report(student_id: int = 0, class_id: int = 0) -> dict:
    """生成自然语言周报（LLM 失败降级结构化数据）。"""
    async with MainSession() as db:
        scope = "student" if student_id else "class"
        if student_id:
            data = await PanelService.get_student_detail(db, class_id, student_id)
        else:
            data = await PanelService.get_class_overview(db, class_id)

        if data is None:
            return {
                "scope": scope,
                "no_data": True,
                "message": "暂无足够数据，无法生成周报",
            }

        messages = [
            {"role": "system", "content": WEEKLY_REPORT_SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(data, ensure_ascii=False, default=str)},
        ]
        try:
            report = (await llm_chat(messages, temperature=0.3, max_tokens=500)).strip()
        except Exception as exc:  # noqa: BLE001 — LLM 降级不阻断对话
            logger.warning("周报 LLM 调用失败，降级结构化数据: %s", exc)
            return {"scope": scope, "report": data, "degraded": True}

        result: dict = {"scope": scope, "report": report}
        if student_id:
            result["student_id"] = student_id
        else:
            result["class_id"] = class_id
        return result


def _normalize_class_name(name: str) -> str:
    """归一化班级名：全角括号→半角、去首尾空白，用于跨格式匹配。"""
    return name.strip().replace("（", "(").replace("）", ")")


async def _resolve_class_id(db, class_name: str) -> int | None:
    """按班级名解析 class_id（精确→子串，归一化括号后匹配）。

    Args:
        db: AsyncSession
        class_name: 班级名称（如「高一（1）班」，支持全角/半角括号）

    Returns:
        唯一命中的 Class.id；多候选或无命中返回 None（不猜测）。
    """
    name = _normalize_class_name(class_name)
    if not name:
        return None

    result = await db.execute(select(Class).where(Class.name == name))
    exact = result.scalars().all()
    if len(exact) == 1:
        return exact[0].id
    if len(exact) > 1:
        return None  # 重名班级，不猜测

    result = await db.execute(select(Class).where(Class.name.contains(name)))
    sub = result.scalars().all()
    if len(sub) == 1:
        return sub[0].id
    return None


@register_tool(
    name="assign_adaptive_practice",
    persona=["teacher"],
    call_limit=1,
    requires_approval=True,
    description="为班级学生批量分配自适应练习题（需教师确认）。基于 ZPD 和间隔复习算法选题，内部每批 5 人。"
    "支持按班级名（class_name，如「高一（1）班」，全角/半角括号均可）或班级 ID 指定班级。",
)
async def assign_adaptive_practice(
    class_id: int = 0,
    student_id: int = 0,
    knowledge_point: str = "",
    count: int = 5,
    class_name: str = "",
) -> dict:
    """分配自适应练习（班级级为主，单生兜底；支持班级名解析）。

    class_name 用于把班级名（如「高一（1）班」，全角/半角括号均可）解析为 class_id；
    与 class_id 同时提供时优先 class_id。
    """
    async with MainSession() as db:
        kp_override = [knowledge_point] if knowledge_point else None

        # 班级名解析（"高一（1）班" → class_id），class_id 已提供时跳过
        if not class_id and class_name.strip():
            class_id = await _resolve_class_id(db, class_name)
            if class_id is None:
                return {
                    "scope": "error",
                    "message": f"未找到班级「{class_name}」，请确认班级名称（如「高一(1)班」）或改用班级 ID",
                }

        # 单生快捷路径
        if student_id:
            practice = await AdaptivePracticeService.create_practice(
                db, student_id, question_count=count, kp_override=kp_override,
            )
            return {
                "scope": "single",
                "total_students": 1,
                "practices": [_summarize_practice(student_id, practice)],
            }

        if not class_id:
            return {"scope": "error", "message": "请提供 student_id、class_id 或 class_name"}

        # 班级级：查学生，每批 5 名顺序生成
        result = await db.execute(
            select(Student)
            .where(Student.class_id == class_id)
            .order_by(Student.id)
        )
        students = result.scalars().all()

        practices = []
        for i in range(0, len(students), CLASS_PRACTICE_BATCH_SIZE):
            for s in students[i:i + CLASS_PRACTICE_BATCH_SIZE]:
                try:
                    p = await AdaptivePracticeService.create_practice(
                        db, s.id, question_count=count, kp_override=kp_override,
                    )
                    practices.append(_summarize_practice(s.id, p))
                except AdaptivePracticeError as exc:
                    practices.append({"student_id": s.id, "error": str(exc)})

        return {
            "scope": "class",
            "class_id": class_id,
            "total_students": len(students),
            "practices": practices,
        }


@register_tool(
    name="generate_learning_plan",
    persona=["teacher"],
    call_limit=5,
    description="为指定学生生成个性化学习计划（预览）。返回跳转指令，持久化由前端抽屉确认后走 REST API。",
)
async def generate_learning_plan(student_id: int) -> dict:
    """生成学习计划预览（返回 _route，不写库）。"""
    return {
        "_route": {
            "page": "students",
            "params": {"student_id": student_id, "action": "open_learning_plan"},
        },
        "message": "已跳转至学生管理页，学习计划抽屉即将打开。",
    }


@register_tool(
    name="send_learning_plan",
    persona=["teacher"],
    call_limit=2,
    requires_approval=True,
    prerequisites=["plan_id", "student_id"],
    description="将学习计划发送给学生（需教师确认）。",
)
async def send_learning_plan(plan_id: int, student_id: int) -> dict:
    """发送学习计划给学生。"""
    async with MainSession() as db:
        await NotificationService.create_notification(
            db, student_id,
            type_="plan_updated",
            title="新的学习计划",
            body=f"教师为你制定了新的学习计划（ID: {plan_id}），请查看。",
            related_id=plan_id,
        )
        return {"status": "sent", "plan_id": plan_id, "student_id": student_id}
