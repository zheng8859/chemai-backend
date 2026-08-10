"""APScheduler 集成 — 每日练习调度器 + 复习逾期通知。

设计文档 tasks.md §5.1-5.3。
"""

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

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

async def _run_ocr_processor():
    """Interval job: 每 5 秒拾取 pending OCR 任务并处理。"""
    from ..services.ocr_service import OCRService
    from ..infrastructure.database import MainSession

    try:
        async with MainSession() as db:
            await OCRService.process_pending_tasks(db)
    except Exception:
        logger.exception("[scheduler] ocr_processor 执行失败")


async def _run_warning_check():
    """Cron job: 每天 00:00 运行学情预警检测。"""
    from ..services.early_warning_service import EarlyWarningService
    from ..infrastructure.database import MainSession

    logger.info("[scheduler] warning_check 开始执行")
    try:
        async with MainSession() as db:
            result = await EarlyWarningService.run_all_checks(db)
        logger.info(
            f"[scheduler] warning_check 完成: "
            f"total={result.get('total_students', 0)} "
            f"new_warnings={result.get('new_warnings', 0)}"
        )
    except Exception:
        logger.exception("[scheduler] warning_check 执行失败")


async def _run_weekly_report():
    """Cron job: 周一 08:00 为所有绑定学生生成周报并通知家长。"""
    from ..services.weekly_report_service import WeeklyReportService
    from ..infrastructure.database import MainSession

    logger.info("[scheduler] weekly_report 开始执行")
    try:
        async with MainSession() as db:
            result = await WeeklyReportService.run_weekly_cron(db)
        logger.info(
            f"[scheduler] weekly_report 完成: "
            f"generated={result.get('generated', 0)} "
            f"failed={result.get('failed', 0)} "
            f"notifications={result.get('notifications', 0)}"
        )
    except Exception:
        logger.exception("[scheduler] weekly_report 执行失败")


def register_jobs():
    """注册所有定时任务（在 startup 时调用）。"""
    # 5.2: 每日练习调度 — 北京时间 08:00
    scheduler.add_job(
        _run_daily_scheduler,
        trigger=CronTrigger(hour=8, minute=0),
        id="daily_practice_scheduler",
        name="每日练习调度器",
        replace_existing=True,
    )
    # 学情预警检测 — 每天 00:00
    scheduler.add_job(
        _run_warning_check,
        trigger=CronTrigger(hour=0, minute=0),
        id="warning_check",
        name="学情预警检测",
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
    # 家长周报 — 周一 08:00
    scheduler.add_job(
        _run_weekly_report,
        trigger=CronTrigger(day_of_week="mon", hour=8, minute=0),
        id="weekly_report",
        name="家长周报生成器",
        replace_existing=True,
    )
    # OCR 处理器 — 每 5 秒
    scheduler.add_job(
        _run_ocr_processor,
        trigger=IntervalTrigger(seconds=5),
        id="ocr_processor",
        name="OCR 任务处理器",
        replace_existing=True,
    )
    logger.info("[scheduler] 已注册 5 个 job")


def start_scheduler():
    """启动调度器（在 lifespan startup 中调用）。"""
    register_jobs()
    scheduler.start()
    logger.info("[scheduler] 已启动")


def shutdown_scheduler():
    """关闭调度器（在 lifespan shutdown 中调用）。"""
    scheduler.shutdown(wait=False)
    logger.info("[scheduler] 已关闭")
