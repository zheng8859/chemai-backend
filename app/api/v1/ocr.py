"""OCR API router — 上传会话/OCR 任务/答题卡提交/批量上传/批改。"""

import uuid
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.database import get_db
from ...api.deps import get_current_user, require_permission, UserContext, get_pagination_params
from ...services.ocr_service import OCRService, OCRError
from ...services.grading_service import GradingService, AnswerKey
from ...schemas.ocr import (
    BatchUploadRequest,
    GradingResult,
    GradingRunRequest,
    GradingRunResponse,
    GradingSaveRequest,
    GradingSaveResponse,
    RetryTaskResponse,
    ServicesStatusResponse,
    GradingResultsResponse,
    StatsResponse,
)
from ...schemas.base import PaginatedResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="", tags=["ocr"])


# ── Sessions ─────────────────────────────────────────────────

@router.get("/ocr/sessions")
async def list_sessions(
    teacher_id: int | None = Query(None),
    db: AsyncSession = Depends(get_db),
    pagination: dict = Depends(get_pagination_params),
    user: UserContext = Depends(get_current_user),
):
    """获取上传会话列表。"""
    tid = teacher_id or user.user_id
    items, total = await OCRService.list_sessions_by_teacher(
        db, tid,
        limit=pagination["limit"], offset=pagination["offset"],
    )
    return PaginatedResponse(items=items, total=total,
                             limit=pagination["limit"], offset=pagination["offset"])


@router.get("/ocr/sessions/{session_id}")
async def get_session(
    session_id: int,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(get_current_user),
):
    """获取上传会话详情。"""
    try:
        return await OCRService.get_session(db, session_id)
    except OCRError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.detail)


# ── Tasks ────────────────────────────────────────────────────

@router.get("/ocr/sessions/{session_id}/tasks")
async def list_tasks_by_session(
    session_id: int,
    db: AsyncSession = Depends(get_db),
    pagination: dict = Depends(get_pagination_params),
    user: UserContext = Depends(get_current_user),
):
    """获取会话下的 OCR 任务列表。"""
    items, total = await OCRService.list_tasks_by_session(
        db, session_id,
        limit=pagination["limit"], offset=pagination["offset"],
    )
    return PaginatedResponse(items=items, total=total,
                             limit=pagination["limit"], offset=pagination["offset"])


@router.get("/ocr/tasks/{task_id}")
async def get_task(
    task_id: int,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(get_current_user),
):
    """获取 OCR 任务详情。"""
    try:
        return await OCRService.get_task(db, task_id)
    except OCRError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.detail)


# ── Submissions ──────────────────────────────────────────────

@router.get("/ocr/submissions")
async def list_submissions(
    exam_id: int = Query(...),
    db: AsyncSession = Depends(get_db),
    pagination: dict = Depends(get_pagination_params),
    user: UserContext = Depends(get_current_user),
):
    """获取考试下的答题卡提交记录。"""
    items, total = await OCRService.list_submissions_by_exam(
        db, exam_id,
        limit=pagination["limit"], offset=pagination["offset"],
    )
    return PaginatedResponse(items=items, total=total,
                             limit=pagination["limit"], offset=pagination["offset"])


@router.get("/ocr/submissions/{submission_id}")
async def get_submission(
    submission_id: int,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(get_current_user),
):
    """获取提交记录详情。"""
    try:
        return await OCRService.get_submission(db, submission_id)
    except OCRError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.detail)


# ── Batch Upload ─────────────────────────────────────────────

@router.post("/ocr/tasks/batch", status_code=status.HTTP_201_CREATED)
async def batch_upload(
    files: list[UploadFile] = File(...),
    teacher_id: int = Form(...),
    class_id: int = Form(...),
    exam_name: str = Form(""),
    exam_paper_id: int = Form(0),
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_permission("ocr", "create")),
):
    """批量上传答题卡（multipart/form-data）。"""
    try:
        return await OCRService.batch_upload(
            db, files, teacher_id, class_id, exam_name,
            exam_paper_id=exam_paper_id if exam_paper_id else None,
        )
    except OCRError as e:
        status_map = {
            "EMPTY_BATCH": status.HTTP_400_BAD_REQUEST,
            "BATCH_TOO_LARGE": status.HTTP_400_BAD_REQUEST,
            "UNSUPPORTED_TYPE": status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            "FILE_TOO_LARGE": status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
        }
        http_status = status_map.get(e.error_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
        raise HTTPException(status_code=http_status, detail=e.detail)


# ── Task Retry ────────────────────────────────────────────────

@router.post("/ocr/tasks/{task_id}/retry")
async def retry_task(
    task_id: int,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_permission("ocr", "create")),
):
    """4.5: 重试失败的 OCR 任务 — status→pending，清空 error_message 和 ocr_raw_result。"""
    from sqlalchemy import update
    from ...models.ocr import OCRTask
    from ...core.enums import OCRTaskStatus

    result = await db.execute(
        update(OCRTask)
        .where(OCRTask.id == task_id)
        .values(
            status=OCRTaskStatus.pending,
            error_message=None,
            ocr_raw_result=None,
            student_id_raw=None,
            student_name_raw=None,
            progress=0,
        )
    )
    await db.commit()

    if result.rowcount == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"OCR 任务不存在: id={task_id}")

    return RetryTaskResponse(success=True, task_id=task_id, status="pending")


# ── OCR Services Status ───────────────────────────────────────

@router.get("/ocr/services/status")
async def get_services_status(
    user: UserContext = Depends(get_current_user),
):
    """获取 OCR 引擎可用性状态。"""
    from ...services.ocr_engine import get_engine_status
    eng = get_engine_status()
    return ServicesStatusResponse(
        ocr=eng.ocr,
        mineru=eng.mineru,
        vision=eng.vision,
        queue_pending=0,
    )


# ── Grading ──────────────────────────────────────────────────


@router.post("/ocr/grading/run", status_code=status.HTTP_200_OK)
async def grading_run(
    body: GradingRunRequest,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_permission("ocr", "create")),
):
    """6.8: 执行批改 — 接收 task_ids + 可选 exam_paper_id/teacher_answers → 逐个执行批改。"""
    # 更新会话状态 uploaded → grading
    from sqlalchemy import update as _update
    from ...models.ocr import UploadSession, OCRTask
    from ...core.enums import UploadSessionStatus
    from sqlalchemy import select as _select

    task_check = await db.execute(
        _select(OCRTask.upload_session_id).where(
            OCRTask.id.in_(body.task_ids)
        ).distinct()
    )
    sids = [row[0] for row in task_check.fetchall() if row[0]]
    if sids:
        await db.execute(
            _update(UploadSession)
            .where(UploadSession.id.in_(sids))
            .values(status=UploadSessionStatus.grading)
        )
        await db.commit()

    # 解析答案源
    answer_key = await GradingService.resolve_answer_source(
        db,
        exam_paper_id=body.exam_paper_id,
        teacher_answers=body.teacher_answers,
    )

    batch_id = str(uuid.uuid4())
    results = []
    graded = 0
    failed = 0

    for task_id in body.task_ids:
        try:
            result = await GradingService.grade_task(db, task_id, answer_key)
            if result.error:
                failed += 1
            else:
                graded += 1
            results.append(result)
        except Exception as e:
            logger.warning("[grading] 任务 %d 批改异常: %s", task_id, e)
            failed += 1
            results.append(GradingResult(
                task_id=task_id,
                error=str(e)[:200],
                needs_review=True,
            ))

    return GradingRunResponse(
        batch_id=batch_id,
        success=True,
        total=len(body.task_ids),
        graded=graded,
        failed=failed,
        results=results,
    )


@router.get("/ocr/grading/results/{batch_id}")
async def grading_results(
    batch_id: str,
    user: UserContext = Depends(get_current_user),
):
    """6.9: 查询批次批改结果。"""
    # 当前 P2: 批改结果存储在 OCRTask.grading_result 字段中，按 task 查询
    # P3 将引入独立的 GradingBatch 表
    return GradingResultsResponse(
        batch_id=batch_id,
        message="请通过 GET /ocr/tasks/{task_id} 查看各任务 grading_result 字段",
    )


@router.post("/ocr/grading/save", status_code=status.HTTP_200_OK)
async def grading_save(
    body: GradingSaveRequest,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_permission("ocr", "create")),
):
    """8.5: 保存批改结果 — task_ids → save_results() → saved_count + skipped_count + diagnosis。

    双写 StudentSubmission + StudentAnswer，触发后保存管线。
    """
    import asyncio as _asyncio
    from ...services.grading_service import GradingService

    result = await GradingService.save_results(db, body.task_ids)

    # 8.3: 异步触发诊断→统计→报告管线
    if result["diagnosis_triggered"]:
        _asyncio.create_task(
            GradingService._post_save_pipeline(
                saved_count=result["saved_count"],
                exam_record_id=result.get("exam_record_id", 1),
                saved_task_ids=result.get("saved_task_ids", []),
            )
        )

    return GradingSaveResponse(
        success=True,
        saved_count=result["saved_count"],
        skipped_count=result["skipped_count"],
        diagnosis_triggered=result["diagnosis_triggered"],
    )


# ── Statistics & Report ──────────────────────────────────────


@router.post("/ocr/stats", status_code=status.HTTP_200_OK)
async def compute_stats_and_report(
    exam_record_id: int = Query(...),
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_permission("ocr", "create")),
):
    """10.3: 计算班级统计 + 生成 LLM 分析报告。

    接收 exam_record_id → compute_exam_statistics + generate_class_report。
    """
    from ...services.grading_service import compute_exam_statistics, generate_class_report

    stats = await compute_exam_statistics(db, exam_record_id)

    if "error" in stats:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=stats["error"])

    report = await generate_class_report(exam_record_id, stats)

    return StatsResponse(
        success=True,
        exam_record_id=exam_record_id,
        statistics=stats,
        report=report,
    )
