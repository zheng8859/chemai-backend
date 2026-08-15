"""Agent Store — 基于 LongTermMemory 表的记忆读写抽象。

提供 student diagnosis history 和 learning plan 的写入/读取接口。
写入策略：best-effort，失败不阻塞父操作。
底层存储：app.models.agent_memory.LongTermMemory（memory_type 区分不同记忆）。
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.agent_memory import LongTermMemory
from ..core.enums import MemoryType

logger = logging.getLogger(__name__)

# Store namespace 前缀
NS_DIAGNOSIS = "student_diagnosis_history"
NS_LEARNING_PLAN = "student_learning_plan"


async def write_diagnosis_snapshot(
    db: AsyncSession,
    student_id: int,
    profile: dict,
    dominant_barrier: Optional[str] = None,
) -> None:
    """写入学生诊断快照到 Store（best-effort）。

    Args:
        db: 数据库会话
        student_id: Student 主键
        profile: 障碍画像 JSON
        dominant_barrier: 主导障碍类型
    """
    try:
        memory = LongTermMemory(
            student_id=student_id,
            memory_type=MemoryType.student_diagnosis_history,
            content={
                "namespace": NS_DIAGNOSIS,
                "profile": profile,
                "dominant_barrier": dominant_barrier,
                "recorded_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        db.add(memory)
        await db.commit()
        logger.debug("Store 写入成功: student_id=%d type=diagnosis", student_id)
    except Exception:
        logger.warning(
            "Store 写入失败（best-effort）: student_id=%d type=diagnosis",
            student_id, exc_info=True,
        )


async def write_learning_plan_summary(
    db: AsyncSession,
    student_id: int,
    plan_id: int,
    title: str,
    task_count: int,
) -> None:
    """写入学习计划摘要到 Store（best-effort）。

    Args:
        db: 数据库会话
        student_id: Student 主键
        plan_id: 计划 ID
        title: 计划标题
        task_count: 任务数量
    """
    try:
        memory = LongTermMemory(
            student_id=student_id,
            memory_type=MemoryType.student_learning_plan,
            content={
                "namespace": NS_LEARNING_PLAN,
                "plan_id": plan_id,
                "title": title,
                "task_count": task_count,
                "recorded_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        db.add(memory)
        await db.commit()
        logger.debug("Store 写入成功: student_id=%d type=learning_plan", student_id)
    except Exception:
        logger.warning(
            "Store 写入失败（best-effort）: student_id=%d type=learning_plan",
            student_id, exc_info=True,
        )


async def read_diagnosis_history(
    db: AsyncSession,
    student_id: int,
    limit: int = 5,
) -> list[dict]:
    """读取学生诊断历史（最近 N 条）。

    Args:
        db: 数据库会话
        student_id: Student 主键
        limit: 返回条数

    Returns:
        [{"profile": {...}, "dominant_barrier": "...", "recorded_at": "..."}, ...]
    """
    try:
        result = await db.execute(
            select(LongTermMemory)
            .where(
                LongTermMemory.student_id == student_id,
                LongTermMemory.memory_type == MemoryType.student_diagnosis_history,
            )
            .order_by(LongTermMemory.created_at.desc(), LongTermMemory.id.desc())
            .limit(limit)
        )
        memories = result.scalars().all()
        return [m.content for m in memories]
    except Exception:
        logger.warning(
            "Store 读取失败: student_id=%d type=diagnosis",
            student_id, exc_info=True,
        )
        return []


async def count_diagnosis_history(db: AsyncSession, student_id: int) -> int:
    """统计学生诊断历史总数（不受 read_diagnosis_history 的 limit 截断）。

    Args:
        db: 数据库会话
        student_id: Student 主键

    Returns:
        诊断记录总数；读取失败时返回 0
    """
    try:
        result = await db.execute(
            select(func.count(LongTermMemory.id)).where(
                LongTermMemory.student_id == student_id,
                LongTermMemory.memory_type == MemoryType.student_diagnosis_history,
            )
        )
        return result.scalar() or 0
    except Exception:
        logger.warning(
            "Store 计数失败: student_id=%d type=diagnosis",
            student_id, exc_info=True,
        )
        return 0


async def read_learning_plan_summary(
    db: AsyncSession,
    student_id: int,
) -> Optional[dict]:
    """读取学生最新学习计划摘要。

    Args:
        db: 数据库会话
        student_id: Student 主键

    Returns:
        content dict 或 None
    """
    try:
        result = await db.execute(
            select(LongTermMemory)
            .where(
                LongTermMemory.student_id == student_id,
                LongTermMemory.memory_type == MemoryType.student_learning_plan,
            )
            .order_by(LongTermMemory.created_at.desc(), LongTermMemory.id.desc())
            .limit(1)
        )
        memory = result.scalar_one_or_none()
        return memory.content if memory else None
    except Exception:
        logger.warning(
            "Store 读取失败: student_id=%d type=learning_plan",
            student_id, exc_info=True,
        )
        return None


async def read_teacher_preference(
    db: AsyncSession,
    teacher_id: int,
) -> Optional[dict]:
    """读取教师最新偏好设置。

    Args:
        db: 数据库会话
        teacher_id: Teacher 主键

    Returns:
        content dict 或 None
    """
    try:
        result = await db.execute(
            select(LongTermMemory)
            .where(
                LongTermMemory.teacher_id == teacher_id,
                LongTermMemory.memory_type == MemoryType.teacher_preference,
            )
            .order_by(LongTermMemory.created_at.desc(), LongTermMemory.id.desc())
            .limit(1)
        )
        memory = result.scalar_one_or_none()
        return memory.content if memory else None
    except Exception:
        logger.warning(
            "Store 读取失败: teacher_id=%d type=teacher_preference",
            teacher_id, exc_info=True,
        )
        return None
