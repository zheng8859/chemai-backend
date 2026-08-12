"""消息通知 API 路由 — 学生拉取通知列表 / 标记已读。

端点：
- GET  /api/v1/notifications/student/{student_id} — 获取学生通知列表（30 天内分页）
- POST /api/v1/notifications/{id}/student-read    — 标记学生通知为已读
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.database import get_db
from ...api.deps import require_student_self, get_current_user, UserContext, resolve_student_id, get_pagination_params
from ...services.notification_service import NotificationService
from ...schemas.notification import NotificationResponse
from ...schemas.base import PaginatedResponse

router = APIRouter(prefix="/notifications", tags=["notifications"])


# ── GET: 学生通知列表 ──

@router.get("/student/{student_id}")
async def get_student_notifications(
    student_id: int,
    db: AsyncSession = Depends(get_db),
    student_db_id: int = Depends(require_student_self()),
    pagination: dict = Depends(get_pagination_params),
):
    """获取学生通知列表（分页，仅 30 天内）。

    按创建时间倒序排列。
    """
    items, total = await NotificationService.get_student_notifications(
        db,
        student_id=student_db_id,
        limit=pagination["limit"],
        offset=pagination["offset"],
    )
    return PaginatedResponse(
        items=items, total=total,
        limit=pagination["limit"], offset=pagination["offset"],
    )


# ── POST: 标记已读 ──

@router.post("/{notification_id}/student-read", response_model=NotificationResponse)
async def mark_notification_read(
    notification_id: int,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(get_current_user),
):
    """将指定通知标记为已读。

    校验：仅通知的接收学生本人可标记。
    """
    if user.role != "student":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="仅学生角色可操作",
        )
    student_db_id = await resolve_student_id(db, user.user_id)
    if student_db_id is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="学生档案不存在",
        )
    result = await NotificationService.mark_as_read(
        db, notification_id, student_db_id,
    )
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="通知不存在或无权操作",
        )
    return result
