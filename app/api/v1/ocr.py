"""OCR API router — 上传会话/OCR 任务/答题卡提交/批量上传。"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.database import get_db
from ...api.deps import get_current_user, require_permission, UserContext, get_pagination_params
from ...services.ocr_service import OCRService, OCRError
from ...schemas.ocr import BatchUploadRequest
from ...schemas.base import PaginatedResponse

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


# ── Batch Upload (stub) ──────────────────────────────────────

@router.post("/ocr/tasks/batch", status_code=status.HTTP_201_CREATED)
async def batch_upload(
    request: BatchUploadRequest,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_permission("ocr", "create")),
):
    """批量上传答题卡（stub — 实际文件处理在后续阶段实现）。"""
    return await OCRService.batch_upload_stub(
        db, request.teacher_id, request.class_id, request.exam_name,
    )
