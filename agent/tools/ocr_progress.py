"""query_ocr_progress — OCR 进度查询工具。

查询批次 OCR 处理进度，返回各状态任务数量和完成百分比。
注册给 Teacher persona。
"""

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ocr import OCRTask
from app.core.enums import OCRTaskStatus
from app.infrastructure.database import MainSession

from .tool_meta import register_tool

logger = logging.getLogger(__name__)


@register_tool(
    name="query_ocr_progress",
    persona=["teacher"],
    call_limit=10,
    description="查询 OCR 识别进度。传入 session_id 查看特定批次，不传则查看教师所有 OCR 任务。返回各状态（pending/processing/done/failed）的任务数量。",
)
async def query_ocr_progress(
    teacher_id: int,
    session_id: int | None = None,
) -> dict:
    """查询 OCR 批次处理进度。

    Args:
        teacher_id: 教师 ID
        session_id: 上传会话 ID

    Returns:
        批次进度摘要
    """
    async with MainSession() as db:
        if session_id:
            result = await db.execute(
                select(OCRTask)
                .where(OCRTask.upload_session_id == session_id)
            )
        else:
            result = await db.execute(
                select(OCRTask)
                .where(OCRTask.teacher_id == teacher_id)
            )

        tasks = result.scalars().all()

        total = len(tasks)
        pending = sum(1 for t in tasks if t.status == OCRTaskStatus.pending)
        processing = sum(1 for t in tasks if t.status == OCRTaskStatus.processing)
        done = sum(1 for t in tasks if t.status == OCRTaskStatus.done)
        failed = sum(1 for t in tasks if t.status == OCRTaskStatus.failed)

        return {
            "total": total,
            "pending": pending,
            "processing": processing,
            "done": done,
            "failed": failed,
            "progress_pct": round((done / total * 100) if total > 0 else 0, 1),
            "status": (
                "completed" if done == total
                else "processing" if processing > 0 or pending > 0
                else "failed" if failed == total
                else "idle"
            ),
        }
