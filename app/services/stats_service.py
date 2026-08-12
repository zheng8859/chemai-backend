"""StatsService — 学生练习统计聚合查询。

为"我的"页面提供 5 项核心指标：
- 累计练习数（total_practices）
- 加权正确率（overall_accuracy，指数衰减，与 Panel API 一致）
- 连续打卡天数（streak_days）
- 错题存量（total_wrong_questions）
- 今日待复习数（review_due_today）
"""

import logging
import math
from datetime import datetime, timezone, timedelta

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.teaching import PracticeSession, StudentAnswer
from ..models.diagnosis import ReviewTask
from ..schemas.stats import StudentStatsResponse

logger = logging.getLogger(__name__)

# 指数衰减常量（与 panel_service 一致）
_DECAY_LAMBDA = math.log(2)
_T_WEEK_SECONDS = 7 * 24 * 3600


class StatsService:
    """学生练习统计服务 — 按需聚合，纯查询无副作用。"""

    @staticmethod
    async def get_student_stats(
        db: AsyncSession,
        student_id: int,  # 数据库 Student.id
    ) -> StudentStatsResponse:
        """获取学生练习统计聚合数据。

        Args:
            db: 异步数据库会话
            student_id: Student 主键（数据库 ID，非 Account.id）

        Returns:
            StudentStatsResponse 包含 5 项聚合指标
        """
        now = datetime.now(timezone.utc)

        # ── 1. 累计完成练习数 ──
        total_practices = await StatsService._count_completed_sessions(db, student_id)

        # ── 2. 加权正确率 ──
        overall_accuracy = await StatsService._weighted_accuracy(db, student_id, now)

        # ── 3. 连续打卡天数 ──
        streak_days = await StatsService._calc_streak_days(db, student_id, now)

        # ── 4. 错题存量 ──
        total_wrong_questions = await StatsService._count_wrong_answers(db, student_id)

        # ── 5. 今日待复习数 ──
        review_due_today = await StatsService._count_due_reviews(db, student_id, now)

        return StudentStatsResponse(
            total_practices=total_practices,
            overall_accuracy=overall_accuracy,
            streak_days=streak_days,
            total_wrong_questions=total_wrong_questions,
            review_due_today=review_due_today,
        )

    # ── 内部方法 ──

    @staticmethod
    async def _count_completed_sessions(db: AsyncSession, student_id: int) -> int:
        """累计完成练习数。"""
        result = await db.execute(
            select(func.count(PracticeSession.id)).where(
                PracticeSession.student_id == student_id,
                PracticeSession.status == "completed",
            )
        )
        return result.scalar() or 0

    @staticmethod
    async def _weighted_accuracy(
        db: AsyncSession, student_id: int, now: datetime
    ) -> float | None:
        """加权指数衰减正确率。

        对每场已完成练习计算 accuracy = questions_correct / questions_served，
        按时间衰减加权：w_i = exp(-λ × (now - t_i) / T_week)。
        仅统计 questions_served > 0 的会话。
        """
        result = await db.execute(
            select(PracticeSession).where(
                PracticeSession.student_id == student_id,
                PracticeSession.status == "completed",
                PracticeSession.questions_served > 0,
            ).order_by(PracticeSession.updated_at.desc())
        )
        sessions = result.scalars().all()

        if not sessions:
            return None

        total_weight = 0.0
        weighted_sum = 0.0

        for session in sessions:
            accuracy = session.questions_correct / session.questions_served
            session_time = session.updated_at.replace(tzinfo=timezone.utc) if session.updated_at and session.updated_at.tzinfo is None else (session.updated_at or now)
            if session_time is None:
                session_time = now
            delta_seconds = (now - session_time).total_seconds()
            weight = math.exp(-_DECAY_LAMBDA * delta_seconds / _T_WEEK_SECONDS)
            weighted_sum += accuracy * weight
            total_weight += weight

        if total_weight == 0:
            return None
        return round(weighted_sum / total_weight, 4)

    @staticmethod
    async def _calc_streak_days(
        db: AsyncSession, student_id: int, now: datetime
    ) -> int:
        """连续打卡天数。

        从今天往回数，找到最长的连续有练习记录的天数链。
        将完成时间按日历日聚合，然后从今天开始向前计数。
        """
        result = await db.execute(
            select(PracticeSession.updated_at).where(
                PracticeSession.student_id == student_id,
                PracticeSession.status == "completed",
            ).order_by(PracticeSession.updated_at.desc())
        )
        sessions = result.scalars().all()

        if not sessions:
            return 0

        # 提取不重复的日期（按本地日期聚合，使用 UTC 近似的日期边界）
        seen_dates: set[str] = set()
        for s in sessions:
            if s:
                session_time = s.replace(tzinfo=timezone.utc) if s.tzinfo is None else s
                date_str = session_time.strftime("%Y-%m-%d")
                seen_dates.add(date_str)

        if not seen_dates:
            return 0

        # 从今天开始往前数连续天数
        today_str = now.strftime("%Y-%m-%d")
        streak = 0
        check_date = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

        # 如果今天有练习，从今天开始算；否则从昨天开始
        if today_str not in seen_dates:
            # 今天没练习但昨天有 → 连续到昨天
            check_date = check_date - timedelta(days=1)

        while True:
            check_str = check_date.strftime("%Y-%m-%d")
            if check_str in seen_dates:
                streak += 1
                check_date = check_date - timedelta(days=1)
            else:
                break

        return streak

    @staticmethod
    async def _count_wrong_answers(db: AsyncSession, student_id: int) -> int:
        """错题存量 — 统计该学生所有答错的作答记录数。"""
        result = await db.execute(
            select(func.count(StudentAnswer.id)).where(
                StudentAnswer.student_id == student_id,
                StudentAnswer.is_correct == False,  # noqa: E712
            )
        )
        return result.scalar() or 0

    @staticmethod
    async def _count_due_reviews(
        db: AsyncSession, student_id: int, now: datetime
    ) -> int:
        """今日待复习任务数。

        统计 next_review_date <= 今天 且状态为 pending/overdue 的 ReviewTask。
        """
        # 待复习：next_review_date 已到期（≤ 当前时间）且状态为 pending/overdue
        result = await db.execute(
            select(func.count(ReviewTask.id)).where(
                ReviewTask.student_id == student_id,
                ReviewTask.status.in_(["pending", "overdue"]),
                ReviewTask.next_review_date <= now,
            )
        )
        return result.scalar() or 0
