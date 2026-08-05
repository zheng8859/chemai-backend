"""Diagnosis API router — 障碍配置/知识点/班级诊断/复习/预警/练习分配。"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.database import get_db
from ...api.deps import get_current_user, require_permission, UserContext, get_pagination_params
from ...services.diagnosis_service import DiagnosisService, DiagnosisError
from ...schemas.diagnosis import (
    BarrierConfigUpdate,
    ReviewCompleteRequest,
    PracticeAssignRequest,
)
from ...schemas.base import PaginatedResponse

router = APIRouter(prefix="", tags=["diagnosis"])


# ── Barrier Config ──────────────────────────────────────────

@router.get("/diagnosis/barrier-config")
async def get_barrier_config(
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(get_current_user),
):
    config = await DiagnosisService.get_barrier_config(db, user.user_id)
    return {"success": True, "data": config}


@router.patch("/diagnosis/barrier-config")
async def update_barrier_config(
    data: BarrierConfigUpdate,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(get_current_user),
):
    config = await DiagnosisService.update_barrier_config(db, user.user_id, data)
    return {"success": True, "data": config}


# ── Knowledge Points ─────────────────────────────────────────

@router.get("/knowledge-points/search")
async def search_knowledge_points(
    keyword: str = Query(..., min_length=1, description="搜索关键词"),
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(get_current_user),
):
    """按关键字模糊搜索知识点（出题工作台知识点选择器）。

    用于出题工作台 Mode 1 的知识点 chip 输入框自动补全。
    """
    results = await DiagnosisService.search_knowledge_points(db, keyword)
    return {"success": True, "data": results, "count": len(results)}


@router.get("/knowledge-points")
async def list_knowledge_points(
    category: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    pagination: dict = Depends(get_pagination_params),
    user: UserContext = Depends(get_current_user),
):
    items, total = await DiagnosisService.list_knowledge_points(
        db, category=category,
        limit=pagination["limit"], offset=pagination["offset"],
    )
    return PaginatedResponse(items=items, total=total,
                             limit=pagination["limit"], offset=pagination["offset"])


# ── Class Diagnosis ──────────────────────────────────────────

@router.get("/diagnosis/class/{class_id}/exam/{exam_id}")
async def get_class_diagnosis(
    class_id: int,
    exam_id: int,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(get_current_user),
):
    return await DiagnosisService.get_class_diagnosis(db, class_id, exam_id)


# ── Reviews ──────────────────────────────────────────────────

@router.get("/reviews/pending")
async def list_pending_reviews(
    student_id: int = Query(...),
    db: AsyncSession = Depends(get_db),
    pagination: dict = Depends(get_pagination_params),
    user: UserContext = Depends(get_current_user),
):
    items, total = await DiagnosisService.list_pending_reviews(
        db, student_id,
        limit=pagination["limit"], offset=pagination["offset"],
    )
    return PaginatedResponse(items=items, total=total,
                             limit=pagination["limit"], offset=pagination["offset"])


@router.post("/reviews/complete")
async def complete_review(
    request: ReviewCompleteRequest,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(get_current_user),
):
    try:
        result = await DiagnosisService.complete_review(
            db, request.review_task_id, request.result,
        )
        return {"success": True, "data": result}
    except DiagnosisError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.detail)


# ── Warnings ─────────────────────────────────────────────────

@router.get("/warnings")
async def list_warnings(
    class_id: int | None = Query(None),
    resolved: bool | None = Query(None),
    severity: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    pagination: dict = Depends(get_pagination_params),
    user: UserContext = Depends(get_current_user),
):
    items, total = await DiagnosisService.list_warnings(
        db, class_id=class_id, resolved=resolved, severity=severity,
        limit=pagination["limit"], offset=pagination["offset"],
    )
    return PaginatedResponse(items=items, total=total,
                             limit=pagination["limit"], offset=pagination["offset"])


@router.post("/warnings/{warning_id}/resolve")
async def resolve_warning(
    warning_id: int,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_permission("student", "update")),
):
    try:
        result = await DiagnosisService.resolve_warning(db, warning_id)
        return {"success": True, "data": result}
    except DiagnosisError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.detail)


# ── Practice Assign (stub) ───────────────────────────────────

@router.post("/practice/assign")
async def assign_practice(
    request: PracticeAssignRequest,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_permission("student", "update")),
):
    return await DiagnosisService.assign_practice_stub(
        request.student_id, request.question_count,
    )
