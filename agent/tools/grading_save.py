"""save_grading_results — 批改结果保存工具。

确认保存批改结果并触发诊断管线。
注册给 Teacher persona。
"""

import asyncio
import logging

from app.services.grading_service import GradingService
from app.infrastructure.database import MainSession

from .tool_meta import register_tool

logger = logging.getLogger(__name__)


@register_tool(
    name="save_grading_results",
    persona=["teacher"],
    call_limit=10,
    requires_approval=True,
    prerequisites=["session_id"],
    description="保存批改结果到数据库并触发诊断管线。需教师确认后执行。",
)
async def save_grading_results(
    teacher_id: int,
    session_id: int | None = None,
    task_ids: list[int] | None = None,
) -> dict:
    """保存批改结果到数据库并触发诊断管线。

    Args:
        teacher_id: 教师 ID
        session_id: 上传会话 ID
        task_ids: 指定 task ID 列表

    Returns:
        saved_count, skipped_count, diagnosis_triggered
    """
    async with MainSession() as db:
        if not task_ids and session_id:
            from sqlalchemy import select
            from app.models.ocr import OCRTask
            from app.core.enums import OCRTaskStatus

            result = await db.execute(
                select(OCRTask.id)
                .where(
                    OCRTask.upload_session_id == session_id,
                    OCRTask.status == OCRTaskStatus.done,
                )
            )
            task_ids = [row[0] for row in result.fetchall()]

        if not task_ids:
            return {
                "success": True,
                "saved_count": 0,
                "skipped_count": 0,
                "diagnosis_triggered": False,
                "message": "无待保存任务",
            }

        result = await GradingService.save_results(db, task_ids)

        if result["diagnosis_triggered"]:
            asyncio.create_task(
                GradingService._post_save_pipeline(result["saved_count"])
            )

        return {
            "success": True,
            "saved_count": result["saved_count"],
            "skipped_count": result["skipped_count"],
            "diagnosis_triggered": result["diagnosis_triggered"],
            "message": f"已保存 {result['saved_count']} 条，跳过 {result['skipped_count']} 条",
        }
