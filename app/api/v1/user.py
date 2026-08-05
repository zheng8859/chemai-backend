"""User API router — 账户管理/教师审批/学生管理/家长管理/任课分配。

端点:
  GET    /accounts               — 账户列表
  GET    /teacher-applications   — 教师申请列表
  POST   /teacher-applications/{id}/approve — 审批通过
  POST   /teacher-applications/{id}/reject  — 审批拒绝
  POST   /students               — 创建学生
  GET    /students/me            — 学生查看自己的 Profile
  GET    /classes/{id}/students  — 班级学生列表
  GET    /students/{id}          — 学生详情
  PATCH  /students/{id}          — 更新学生
  DELETE /students/{id}          — 删除学生
  POST   /parents                — 创建家长
  GET    /parents                — 家长列表
  GET    /parents/{id}           — 家长详情
  PATCH  /parents/{id}           — 更新家长
  POST   /teacher-assignments    — 创建任课分配
  GET    /teacher-assignments    — 教师任课列表
  DELETE /teacher-assignments/{id} — 删除任课关系
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.database import get_db
from ...api.deps import get_current_user, require_permission, UserContext, get_pagination_params
from ...services.user_service import UserService, UserError
from ...schemas.user import (
    StudentUpdate,
    ParentUpdate,
    TeacherClassSubjectCreate,
    TeacherClassSubjectRead,
)
from ...schemas.base import PaginatedResponse

router = APIRouter(prefix="", tags=["user"])


# ═══════════════════════════════════════════════════════════
# Accounts
# ═══════════════════════════════════════════════════════════

@router.get("/accounts")
async def list_accounts(
    role: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    pagination: dict = Depends(get_pagination_params),
    user: UserContext = Depends(get_current_user),
):
    """获取账户列表。"""
    items, total = await UserService.list_accounts(
        db, limit=pagination["limit"], offset=pagination["offset"], role=role,
    )
    return {"success": True, "data": items, "total": total}


# ═══════════════════════════════════════════════════════════
# Teacher Applications
# ═══════════════════════════════════════════════════════════

@router.get("/teacher-applications")
async def list_teacher_applications(
    status_filter: str | None = Query(None, alias="status"),
    db: AsyncSession = Depends(get_db),
    pagination: dict = Depends(get_pagination_params),
    user: UserContext = Depends(require_permission("teacher", "read")),
):
    """获取教师入驻申请列表。"""
    items, total = await UserService.get_teacher_applications(
        db, status=status_filter,
        limit=pagination["limit"], offset=pagination["offset"],
    )
    return {"success": True, "data": items, "total": total}


@router.post("/teacher-applications/{application_id}/approve")
async def approve_teacher_application(
    application_id: int,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_permission("teacher", "update")),
):
    """审批通过教师申请。"""
    try:
        result = await UserService.approve_teacher_application(
            db, application_id, user.user_id, approved=True,
        )
        return {"success": True, "data": result}
    except UserError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.detail)


@router.post("/teacher-applications/{application_id}/reject")
async def reject_teacher_application(
    application_id: int,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_permission("teacher", "update")),
):
    """审批拒绝教师申请。"""
    try:
        result = await UserService.reject_teacher_application(
            db, application_id, user.user_id,
        )
        return {"success": True, "data": result}
    except UserError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.detail)


# ═══════════════════════════════════════════════════════════
# Students
# ═══════════════════════════════════════════════════════════

@router.post("/students", status_code=status.HTTP_201_CREATED)
async def create_student(
    name: str = Query(...),
    student_id: str = Query(..., alias="studentId"),
    class_id: int = Query(...),
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_permission("student", "create")),
):
    """创建学生。"""
    try:
        result = await UserService.create_student(db, class_id, name, student_id)
        return {"success": True, "data": result}
    except UserError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.detail)


@router.get("/students/me")
async def get_my_profile(
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(get_current_user),
):
    """学生查看自己的 Profile。"""
    if user.role != "student":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="仅学生可查看")
    try:
        result = await UserService.get_student_profile(db, user.user_id)
        return {"success": True, "data": result}
    except UserError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.detail)


@router.get("/classes/{class_id}/students")
async def list_students_by_class(
    class_id: int,
    db: AsyncSession = Depends(get_db),
    pagination: dict = Depends(get_pagination_params),
    user: UserContext = Depends(get_current_user),
):
    """获取班级学生列表。"""
    try:
        items, total = await UserService.list_students_by_class(
            db, class_id, limit=pagination["limit"], offset=pagination["offset"],
        )
    except UserError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.detail)
    return PaginatedResponse(
        items=items, total=total,
        limit=pagination["limit"], offset=pagination["offset"],
    )


@router.get("/students/{student_id}")
async def get_student(
    student_id: int,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(get_current_user),
):
    """获取学生详情。"""
    try:
        result = await UserService.get_student(db, student_id)
        return {"success": True, "data": result}
    except UserError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.detail)


@router.patch("/students/{student_id}")
async def update_student(
    student_id: int,
    data: StudentUpdate,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_permission("student", "update")),
):
    """更新学生信息。"""
    try:
        result = await UserService.update_student(db, student_id, data)
        return {"success": True, "data": result}
    except UserError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.detail)


@router.delete("/students/{student_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_student(
    student_id: int,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_permission("student", "delete")),
):
    """删除学生。"""
    try:
        await UserService.delete_student(db, student_id)
    except UserError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.detail)


# ═══════════════════════════════════════════════════════════
# Parents
# ═══════════════════════════════════════════════════════════

@router.post("/parents", status_code=status.HTTP_201_CREATED)
async def create_parent(
    name: str = Query(...),
    phone: str = Query(...),
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_permission("student", "create")),
):
    """创建家长账户。"""
    try:
        result = await UserService.create_parent(db, name, phone)
        return {"success": True, "data": result}
    except UserError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.detail)


@router.get("/parents")
async def list_parents(
    db: AsyncSession = Depends(get_db),
    pagination: dict = Depends(get_pagination_params),
    user: UserContext = Depends(get_current_user),
):
    """获取家长列表。"""
    items, total = await UserService.list_parents(
        db, limit=pagination["limit"], offset=pagination["offset"],
    )
    return PaginatedResponse(
        items=items, total=total,
        limit=pagination["limit"], offset=pagination["offset"],
    )


@router.get("/parents/{parent_id}")
async def get_parent(
    parent_id: int,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(get_current_user),
):
    """获取家长详情。"""
    try:
        result = await UserService.get_parent(db, parent_id)
        return {"success": True, "data": result}
    except UserError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.detail)


@router.patch("/parents/{parent_id}")
async def update_parent(
    parent_id: int,
    data: ParentUpdate,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(get_current_user),
):
    """更新家长信息。"""
    try:
        result = await UserService.update_parent(db, parent_id, data)
        return {"success": True, "data": result}
    except UserError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.detail)


# ═══════════════════════════════════════════════════════════
# Teacher Assignments
# ═══════════════════════════════════════════════════════════

@router.post("/teacher-assignments", response_model=TeacherClassSubjectRead,
             status_code=status.HTTP_201_CREATED)
async def create_assignment(
    data: TeacherClassSubjectCreate,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_permission("teacher", "update")),
):
    """创建教师任课分配。"""
    try:
        return await UserService.create_assignment(db, data)
    except UserError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.detail)


@router.get("/teacher-assignments")
async def list_teacher_assignments(
    teacher_id: int = Query(None),
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(get_current_user),
):
    """获取教师任课列表。"""
    tid = teacher_id or user.user_id
    result = await UserService.list_teacher_assignments(db, tid)
    return {"success": True, "data": result}


@router.delete("/teacher-assignments/{assignment_id}",
               status_code=status.HTTP_204_NO_CONTENT)
async def delete_assignment(
    assignment_id: int,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_permission("teacher", "update")),
):
    """删除任课关系。"""
    try:
        await UserService.delete_assignment(db, assignment_id)
    except UserError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.detail)
