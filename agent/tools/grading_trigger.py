"""grade_answer_sheets — 批改触发工具。

触发批次批改（逐题判定），对比 OCR 识别结果与标准答案。
注册给 Teacher persona。
"""

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ocr import OCRTask
from app.core.enums import OCRTaskStatus
from app.services.grading_service import GradingService, AnswerKey
from app.infrastructure.database import MainSession

from .tool_meta import register_tool

logger = logging.getLogger(__name__)


@register_tool(
    name="grade_answer_sheets",
    persona=["teacher"],
    call_limit=10,
    description="批改答题卡。传入 session_id 对已 OCR 完成的答题卡进行逐题批改，返回每道题的得分和需人工复核的题目。",
)
async def grade_answer_sheets(
    teacher_id: int,
    session_id: int | None = None,
    exam_paper_id: int | None = None,
    teacher_answers: dict | None = None,
) -> dict:
    """触发批次批改。

    Args:
        teacher_id: 教师 ID
        session_id: 上传会话 ID
        exam_paper_id: 试卷 ID（可选，用于题库匹配）
        teacher_answers: 教师录入的答案（可选，最高优先级）

    Returns:
        批改结果摘要
    """
    async with MainSession() as db:
        answer_key = await GradingService.resolve_answer_source(
            db,
            exam_paper_id=exam_paper_id,
            teacher_answers=teacher_answers,
        )

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
                continue

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
