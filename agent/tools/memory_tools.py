"""记忆工具集（2 个）— 学生记忆检索、教师偏好读取。

通过 LangGraph AsyncSqliteStore 读写长期记忆。
注册给 Teacher/Student persona。
"""

import logging

from app.agent.store import (
    read_diagnosis_history,
    count_diagnosis_history,
    read_learning_plan_summary,
    read_teacher_preference,
)
from app.infrastructure.database import MainSession

from .tool_meta import register_tool

logger = logging.getLogger(__name__)


@register_tool(
    name="memory_student_get",
    persona=["teacher", "student"],
    call_limit=10,
    description="读取学生诊断历史和学习档案。传入 student_id 返回障碍画像、薄弱知识点、学习计划和练习统计。",
)
async def memory_student_get(student_id: int) -> dict:
    """读取学生长期记忆。

    Args:
        student_id: 学生 ID

    Returns:
        {"diagnosis_history": [...], "learning_plan": dict | None, "diagnosis_count": int}
    """
    try:
        async with MainSession() as db:
            diagnoses = await read_diagnosis_history(db, student_id)
            diagnosis_count = await count_diagnosis_history(db, student_id)
            plan = await read_learning_plan_summary(db, student_id)
    except Exception as e:
        logger.warning("memory_student_get 失败: %s", e)
        diagnoses, diagnosis_count, plan = [], 0, None

    return {
        "student_id": student_id,
        "diagnosis_history": [
            {
                "barrier_type": d.get("dominant_barrier"),
                "distribution": d.get("profile"),
                "timestamp": d.get("recorded_at"),
            }
            for d in diagnoses
        ],
        "active_learning_plan": plan,
        "diagnosis_count": diagnosis_count,
    }


@register_tool(
    name="memory_teacher_get",
    persona=["teacher"],
    call_limit=10,
    description="读取教师偏好设置：教学风格、难度偏好、班级配置。用于个性化 Agent 行为。",
)
async def memory_teacher_get(teacher_id: int) -> dict:
    """读取教师偏好设置。

    Args:
        teacher_id: 教师 ID

    Returns:
        {"teaching_style": str, "difficulty_preference": str, "class_config": dict}
    """
    defaults = {
        "teaching_style": "balanced",
        "difficulty_preference": "auto",
        "class_configuration": {},
    }

    try:
        async with MainSession() as db:
            pref = await read_teacher_preference(db, teacher_id)
        pref = pref or {}
    except Exception as e:
        logger.warning("memory_teacher_get 失败: %s", e)
        pref = {}

    return {
        "teacher_id": teacher_id,
        "teaching_style": pref.get("teaching_style", defaults["teaching_style"]),
        "difficulty_preference": pref.get(
            "difficulty_preference", defaults["difficulty_preference"]
        ),
        "class_configuration": pref.get(
            "class_configuration", defaults["class_configuration"]
        ),
    }
