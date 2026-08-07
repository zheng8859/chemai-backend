"""间隔复习 API 路由 — 待复习列表 / 提交复习结果。

设计文档 tasks.md §4.5-4.7。
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.database import get_db
from ...api.deps import get_current_user, UserContext, resolve_student_id
from ...services.review_service import ReviewService, ReviewError
from ...schemas.teaching import ReviewSubmitRequest

router = APIRouter(prefix="/review", tags=["review"])


# ── 4.6 GET /api/review/student/{id}/due ───────────────────────────────

@router.get("/student/{id}/due")
async def get_due_reviews(
    id: int,  # student_id
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(get_current_user),
):
    """获取学生的待复习/逾期 ReviewTask 列表（附带题目内容）。"""
    try:
        student_id = await resolve_student_id(db, id)
        if student_id is None:
            return {"success": True, "data": [], "total": 0}
        tasks, total = await ReviewService.list_pending_reviews(
            db, student_id, limit=limit, offset=offset,
        )
        return {"success": True, "data": tasks, "total": total}
    except ReviewError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error_code": e.error_code, "message": e.detail},
        )


# ── 4.7 POST /api/review/submit ───────────────────────────────────────

@router.post("/submit")
async def submit_review(
    data: ReviewSubmitRequest,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(get_current_user),
):
    """提交一次复习结果，返回更新后的级别和下次复习日期。"""
    try:
        result = await ReviewService.complete_review(
            db, data.review_task_id, data.is_correct,
        )
        return {"success": True, "data": result}
    except ReviewError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error_code": e.error_code, "message": e.detail},
        )
