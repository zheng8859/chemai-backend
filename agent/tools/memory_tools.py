"""记忆工具集（2 个）— 学生记忆检索、教师偏好读取。

通过 LangGraph AsyncSqliteStore 读写长期记忆。
注册给 Teacher/Student persona。
"""

import logging

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
        {"diagnosis_history": [...], "learning_plan": dict | None, "practice_stats": dict}
    """
    from app.agent.store import read_diagnosis_snapshots, read_learning_plan

    try:
        diagnoses = await read_diagnosis_snapshots(student_id)
        plan = await read_learning_plan(student_id)

        return {
            "student_id": student_id,
            "diagnosis_history": [
                {"barrier_type": d.get("barrier_type"),
                 "distribution": d.get("distribution"),
                 "timestamp": d.get("timestamp")}
                for d in diagnoses
            ],
            "active_learning_plan": plan,
            "diagnosis_count": len(diagnoses),
        }
    except Exception as e:
        logger.warning("memory_student_get 失败: %s", e)
        return {
            "student_id": student_id,
            "diagnosis_history": [],
            "active_learning_plan": None,
            "diagnosis_count": 0,
            "error": str(e),
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
    # TODO: 从 teacher_preferences 表或 Store 读取
    return {
        "teacher_id": teacher_id,
        "teaching_style": "balanced",
        "difficulty_preference": "auto",
        "class_configuration": {},
    }
