"""9.3: 批改保存工具 — 确认保存批改结果并触发诊断。"""

import asyncio
import logging

from app.services.grading_service import GradingService
from app.infrastructure.database import MainSession

logger = logging.getLogger(__name__)


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
        # 如果未指定 task_ids，从 session 查询
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

        # 触发后保存管线
        if result["diagnosis_triggered"]:
            asyncio.create_task(
                GradingService._post_save_pipeline(result["saved_count"])
            )

        return {
            "success": True,
            "saved_count": result["saved_count"],
            "skipped_count": result["skipped_count"],
            "diagnosis_triggered": result["diagnosis_triggered"],
            "message": f"已保存 {result['saved_count']} 条，"
                       f"跳过 {result['skipped_count']} 条",
        }
