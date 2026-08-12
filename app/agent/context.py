"""Agent 学生上下文注入 — System Message 构建器。

当 persona="student" 时：
1. 从数据库查询学生障碍画像、学习计划、练习统计
2. 将查询结果格式化为结构化 System Message 块
3. 注入到 Agent system prompt 前面

非 student persona 不受影响。
"""

import logging
import math
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..models.user import Student
from ..models.org import Class
from ..models.learning_plan import LearningPlan, LearningPlanTask
from ..models.teaching import PracticeSession

logger = logging.getLogger(__name__)


async def build_student_context(
    db: AsyncSession,
    student_id: int,  # 数据库 Student.id
) -> Optional[str]:
    """构建学生上下文 System Message 块。

    返回 None 表示学生不存在（调用方应处理）。
    返回的文本可直接拼接到 Agent system prompt 前面。

    Args:
        db: 数据库会话
        student_id: Student 主键

    Returns:
        格式化的上下文文本，或 None（学生不存在）
    """
    # 查询学生
    result = await db.execute(
        select(Student)
        .where(Student.id == student_id)
        .options(selectinload(Student.class_))
    )
    student = result.scalar_one_or_none()
    if student is None:
        logger.warning("build_student_context: 学生不存在 id=%d", student_id)
        return None

    # 解析班级名称
    class_name = student.class_.name if student.class_ else f"班级 #{student.class_id}"

    lines = [
        "<!-- STUDENT_CONTEXT_START -->",
        "以下是当前学生的个人信息，请在对话中参考：",
        "",
        f"## 学生基本信息",
        f"- 姓名：{student.name}",
        f"- 班级：{class_name}",
    ]

    # ── 障碍画像 ──
    if student.barrier_profile:
        profile = student.barrier_profile
        lines.append("")
        lines.append("## 障碍画像")
        lines.append(f"- 概念障碍：{profile.get('concept', 'N/A')}")
        lines.append(f"- 审题障碍：{profile.get('reading', 'N/A')}")
        lines.append(f"- 表述障碍：{profile.get('expression', 'N/A')}")
        if student.barrier_profile_updated_at:
            lines.append(f"- 最后更新：{student.barrier_profile_updated_at.isoformat()}")

    # ── 薄弱知识点 ──
    if student.weak_knowledge_points:
        lines.append("")
        lines.append("## 薄弱知识点")
        for kp in student.weak_knowledge_points[:5]:
            lines.append(f"- {kp}")

    # ── 活跃学习计划 ──
    plan_result = await db.execute(
        select(LearningPlan)
        .where(
            LearningPlan.student_id == student_id,
            LearningPlan.is_active == True,  # noqa: E712
        )
    )
    active_plan = plan_result.scalar_one_or_none()
    if active_plan:
        # 统计任务进度
        task_result = await db.execute(
            select(LearningPlanTask)
            .where(LearningPlanTask.plan_id == active_plan.id)
        )
        tasks = task_result.scalars().all()
        completed = sum(1 for t in tasks if t.status == "completed")
        total = len(tasks)

        lines.append("")
        lines.append("## 当前学习计划")
        lines.append(f"- 标题：{active_plan.title}")
        lines.append(f"- 进度：{completed}/{total} 已完成")
        if total > 0:
            pct = int(completed / total * 100)
            lines.append(f"- 完成率：{pct}%")

    # ── 练习统计 ──
    stats_result = await db.execute(
        select(PracticeSession).where(
            PracticeSession.student_id == student_id,
            PracticeSession.status == "completed",
            PracticeSession.questions_served > 0,
        )
    )
    sessions = stats_result.scalars().all()
    total_practices = len(sessions)

    # 指数衰减加权正确率（与 StatsService / Panel API 一致）
    _DECAY_LAMBDA = math.log(2)
    _T_WEEK_SECONDS = 7 * 24 * 3600
    now = datetime.now(timezone.utc)

    if sessions:
        total_weight = 0.0
        weighted_sum = 0.0
        for s in sessions:
            accuracy = s.questions_correct / s.questions_served
            session_time = s.updated_at.replace(tzinfo=timezone.utc) if s.updated_at and s.updated_at.tzinfo is None else (s.updated_at or now)
            if session_time is None:
                session_time = now
            delta_seconds = (now - session_time).total_seconds()
            weight = math.exp(-_DECAY_LAMBDA * delta_seconds / _T_WEEK_SECONDS)
            weighted_sum += accuracy * weight
            total_weight += weight
        overall_accuracy = round(weighted_sum / total_weight, 4) if total_weight > 0 else None
    else:
        overall_accuracy = None

    lines.append("")
    lines.append("## 练习统计")
    lines.append(f"- 累计练习：{total_practices} 次")
    if overall_accuracy is not None:
        lines.append(f"- 加权正确率：{round(overall_accuracy * 100, 1)}%")
    lines.append(f"- 累计练习数：{student.practice_count}")

    lines.append("")
    lines.append("<!-- STUDENT_CONTEXT_END -->")

    return "\n".join(lines)


def inject_student_context(
    system_prompt: str,
    student_context: str,
) -> str:
    """将学生上下文注入到 Agent system prompt 前面。

    Args:
        system_prompt: 原始 system prompt（来自 Persona 配置）
        student_context: build_student_context() 返回的文本

    Returns:
        注入后的完整 system prompt
    """
    return f"{student_context}\n\n---\n\n{system_prompt}"


def should_inject_context(persona: str) -> bool:
    """判断是否应该为学生上下文注入。

    仅 student persona 需要。teacher/tutor/parent 不受影响。

    Args:
        persona: 角色名

    Returns:
        True 当 persona == "student"
    """
    return persona == "student"
