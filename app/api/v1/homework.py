"""Home-school API router — 亲子绑定/通知/报告。"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.database import get_db
from ...api.deps import get_current_user, UserContext, get_pagination_params
from ...services.homework_service import HomeworkService, HomeworkError
from ...schemas.homework import BindingCreate
from ...schemas.base import PaginatedResponse

router = APIRouter(prefix="", tags=["homework"])


# ── Bindings ─────────────────────────────────────────────────

@router.post("/bindings", status_code=status.HTTP_201_CREATED)
async def create_binding(
    data: BindingCreate,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(get_current_user),
):
    """创建亲子绑定（验证绑定码）。"""
    try:
        return await HomeworkService.create_binding(db, data)
    except HomeworkError as e:
        code = status.HTTP_400_BAD_REQUEST if e.error_code == "INVALID_BIND_CODE" else status.HTTP_404_NOT_FOUND
        raise HTTPException(status_code=code, detail=e.detail)


@router.get("/bindings")
async def list_bindings(
    parent_id: int | None = Query(None),
    student_id: int | None = Query(None),
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(get_current_user),
):
    """获取绑定列表（按家长或学生筛选）。"""
    if parent_id:
        items = await HomeworkService.list_bindings_by_parent(db, parent_id)
    elif student_id:
        items = await HomeworkService.list_bindings_by_student(db, student_id)
    else:
        items = []
    return {"success": True, "data": items}


@router.delete("/bindings/{binding_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_binding(
    binding_id: int,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(get_current_user),
):
    """删除亲子绑定。"""
    try:
        await HomeworkService.delete_binding(db, binding_id)
    except HomeworkError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.detail)


# ── Notifications ────────────────────────────────────────────

@router.get("/notifications")
async def list_notifications(
    parent_id: int = Query(...),
    db: AsyncSession = Depends(get_db),
    pagination: dict = Depends(get_pagination_params),
    user: UserContext = Depends(get_current_user),
):
    """获取家长通知列表。"""
    items, total = await HomeworkService.list_notifications_by_parent(
        db, parent_id,
        limit=pagination["limit"], offset=pagination["offset"],
    )
    return PaginatedResponse(items=items, total=total,
                             limit=pagination["limit"], offset=pagination["offset"])


@router.post("/notifications/{notification_id}/read")
async def mark_notification_read(
    notification_id: int,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(get_current_user),
):
    """标记通知已读。"""
    try:
        result = await HomeworkService.mark_notification_read(db, notification_id)
        return {"success": True, "data": result}
    except HomeworkError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.detail)


# ── Reports ──────────────────────────────────────────────────

@router.post("/reports/send-to-students/{exam_id}")
async def send_exam_reports(
    exam_id: int,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(get_current_user),
):
    """发送考试报告给所有绑定家长。"""
    return await HomeworkService.send_exam_reports(db, exam_id)
