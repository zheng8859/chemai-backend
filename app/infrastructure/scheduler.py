"""APScheduler 集成 — 每日练习调度器 + 复习逾期通知。

设计文档 tasks.md §5.1-5.3。
"""

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)

# ── 全局调度器实例 ────────────────────────────────────────────

scheduler = AsyncIOScheduler(
    timezone="Asia/Shanghai",
    job_defaults={"misfire_grace_time": 300, "coalesce": True},
)


# ── Job 包装函数（延迟导入避免循环依赖）─────────────────────────

async def _run_daily_scheduler():
    """Cron job: 为所有已审批学生生成每日练习。"""
    from ..services.daily_practice_service import DailyPracticeService
    from ..infrastructure.database import MainSession

    logger.info("[scheduler] run_daily_scheduler 开始执行")
    try:
        async with MainSession() as db:
            result = await DailyPracticeService.run_daily_scheduler(db)
        logger.info(
            f"[scheduler] run_daily_scheduler 完成: "
            f"total={result.get('total_students', 0)} "
            f"assigned={result.get('assigned_count', 0)}"
        )
    except Exception:
        logger.exception("[scheduler] run_daily_scheduler 执行失败")


async def _run_notify_parents():
    """Cron job: 通知逾期复习的学生家长。"""
    from ..services.daily_practice_service import DailyPracticeService
    from ..infrastructure.database import MainSession

    logger.info("[scheduler] notify_parents_of_overdue_reviews 开始执行")
    try:
        async with MainSession() as db:
            result = await DailyPracticeService.notify_parents_of_overdue_reviews(db)
        logger.info(
            f"[scheduler] notify_parents 完成: "
            f"overdue={result.get('overdue_count', 0)} "
            f"notifications={result.get('notifications_created', 0)}"
        )
    except Exception:
        logger.exception("[scheduler] notify_parents_of_overdue_reviews 执行失败")


# ── 注册 Cron Jobs ────────────────────────────────────────────

def register_jobs():
    """注册所有定时任务（在 startup 时调用）。"""
    # 5.2: 每日练习调度 — 北京时间 08:00 (UTC 00:00)
    scheduler.add_job(
        _run_daily_scheduler,
        trigger=CronTrigger(hour=8, minute=0),
        id="daily_practice_scheduler",
        name="每日练习调度器",
        replace_existing=True,
    )
    # 逾期复习通知 — 北京时间 20:00
    scheduler.add_job(
        _run_notify_parents,
        trigger=CronTrigger(hour=20, minute=0),
        id="notify_parents_overdue",
        name="逾期复习家长通知",
        replace_existing=True,
    )
    logger.info("[scheduler] 已注册 2 个 cron job")


def start_scheduler():
    """启动调度器（在 lifespan startup 中调用）。"""
    register_jobs()
    scheduler.start()
    logger.info("[scheduler] 已启动")


def shutdown_scheduler():
    """关闭调度器（在 lifespan shutdown 中调用）。"""
    scheduler.shutdown(wait=False)
    logger.info("[scheduler] 已关闭")
