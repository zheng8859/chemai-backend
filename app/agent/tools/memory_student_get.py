"""memory_student_get — Agent 学生记忆检索工具。

从 LongTermMemory Store 读取：
- 最近 5 条诊断历史（障碍画像 + 主导类型）
- 最新学习计划摘要

供 Agent Student persona 构建上下文时调用。
"""

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_memory import LongTermMemory
from app.core.enums import MemoryType

logger = logging.getLogger(__name__)


async def memory_student_get(
    db: AsyncSession,
    student_id: int,
    limit: int = 5,
) -> dict:
    """获取学生长期记忆摘要（诊断历史 + 学习计划）。

    Args:
        db: 数据库会话
        student_id: Student 主键
        limit: 诊断历史返回条数

    Returns:
        {
            "diagnosis_history": [...],
            "learning_plan": {...} | None,
        }
    """
    # 诊断历史
    try:
        diag_result = await db.execute(
            select(LongTermMemory)
            .where(
                LongTermMemory.student_id == student_id,
                LongTermMemory.memory_type == MemoryType.student_diagnosis_history,
            )
            .order_by(LongTermMemory.created_at.desc())
            .limit(limit)
        )
        diagnosis_history = [
            m.content for m in diag_result.scalars().all()
        ]
    except Exception:
        logger.warning("memory_student_get 诊断历史查询失败", exc_info=True)
        diagnosis_history = []

    # 学习计划
    try:
        plan_result = await db.execute(
            select(LongTermMemory)
            .where(
                LongTermMemory.student_id == student_id,
                LongTermMemory.memory_type == MemoryType.student_learning_plan,
            )
            .order_by(LongTermMemory.created_at.desc())
            .limit(1)
        )
        plan_memory = plan_result.scalar_one_or_none()
        learning_plan = plan_memory.content if plan_memory else None
    except Exception:
        logger.warning("memory_student_get 学习计划查询失败", exc_info=True)
        learning_plan = None

    return {
        "diagnosis_history": diagnosis_history,
        "learning_plan": learning_plan,
    }
