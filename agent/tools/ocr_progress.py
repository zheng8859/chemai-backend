"""9.1: OCR 进度查询工具 — 查询批次 OCR 处理进度。"""

import logging

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ocr import UploadSession, OCRTask
from app.core.enums import OCRTaskStatus
from app.infrastructure.database import MainSession

logger = logging.getLogger(__name__)


async def query_ocr_progress(
    teacher_id: int,
    batch_id: str | None = None,
    session_id: int | None = None,
) -> dict:
    """查询 OCR 批次处理进度。

    Args:
        teacher_id: 教师 ID
        batch_id: 批次 ID（预留，当前使用 session_id）
        session_id: 上传会话 ID

    Returns:
        批次进度摘要
    """
    async with MainSession() as db:
        # 按 session_id 或 teacher_id 查询
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
