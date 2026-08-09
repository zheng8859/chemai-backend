"""9.2: 批改触发工具 — 触发批次批改（逐题判定）。"""

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ocr import OCRTask
from app.core.enums import OCRTaskStatus
from app.services.grading_service import GradingService, AnswerKey
from app.infrastructure.database import MainSession

logger = logging.getLogger(__name__)


async def trigger_grading(
    teacher_id: int,
    batch_id: str | None = None,
    session_id: int | None = None,
    exam_paper_id: int | None = None,
    teacher_answers: dict | None = None,
) -> dict:
    """触发批次批改。

    Args:
        teacher_id: 教师 ID
        batch_id: 批次 ID（预留）
        session_id: 上传会话 ID
        exam_paper_id: 试卷 ID（可选，用于题库匹配）
        teacher_answers: 教师录入的答案（可选，最高优先级）

    Returns:
        批改结果摘要
    """
    async with MainSession() as db:
        # 解析答案源
        answer_key = await GradingService.resolve_answer_source(
            db,
            exam_paper_id=exam_paper_id,
            teacher_answers=teacher_answers,
        )

        # 查询已完成 OCR 但未批改的 task
        if session_id:
            result = await db.execute(
                select(OCRTask)
                .where(
                    OCRTask.upload_session_id == session_id,
                    OCRTask.status == OCRTaskStatus.done,
                )
            )
        else:
            result = await db.execute(
                select(OCRTask)
                .where(
                    OCRTask.teacher_id == teacher_id,
                    OCRTask.status == OCRTaskStatus.done,
                )
            )

        tasks = result.scalars().all()

        graded = 0
        failed = 0
        results = []

        for task in tasks:
            if task.grading_result:
                graded += 1
                continue  # 已批改，跳过

            try:
                grad_result = await GradingService.grade_task(db, task.id, answer_key)
                if grad_result.error:
                    failed += 1
                else:
                    graded += 1
                results.append({
                    "task_id": task.id,
                    "total_score": grad_result.total_score,
                    "needs_review": grad_result.needs_review,
                })
            except Exception as e:
                logger.warning("[agent] 批改 task %d 失败: %s", task.id, e)
                failed += 1

        return {
            "total": len(tasks),
            "graded": graded,
            "failed": failed,
            "answer_source": answer_key.source_mode,
            "results": results,
        }
