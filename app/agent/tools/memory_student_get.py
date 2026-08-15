"""fetch_student_memory — Agent 学生记忆检索辅助函数。

委托 app.agent.store 读取 LongTermMemory：
- 最近 5 条诊断历史（障碍画像 + 主导类型）
- 最新学习计划摘要

与注册工具 `agent.tools.memory_tools.memory_student_get` 区分：该函数接受显式
`db` 会话供上下文注入调用，且复用 store.py 的读写抽象，不重复查询 LongTermMemory。
"""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.store import read_diagnosis_history, read_learning_plan_summary

logger = logging.getLogger(__name__)


async def fetch_student_memory(
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
    diagnosis_history = await read_diagnosis_history(db, student_id, limit=limit)
    learning_plan = await read_learning_plan_summary(db, student_id)

    return {
        "diagnosis_history": diagnosis_history,
        "learning_plan": learning_plan,
    }
