"""Org API router — 学校/年级/班级 CRUD + 组织树。

端点:
  GET    /schools              — 学校列表
  POST   /schools              — 创建学校
  GET    /schools/{id}         — 学校详情
  PATCH  /schools/{id}         — 更新学校
  DELETE /schools/{id}         — 删除学校
  GET    /schools/{id}/grades  — 学校下的年级列表
  POST   /grades               — 创建年级
  GET    /grades/{id}          — 年级详情
  PATCH  /grades/{id}          — 更新年级
  DELETE /grades/{id}          — 删除年级
  GET    /grades/{id}/classes  — 年级下的班级列表
  POST   /classes              — 创建班级
  GET    /classes/{id}         — 班级详情
  PATCH  /classes/{id}         — 更新班级
  DELETE /classes/{id}         — 删除班级
  GET    /org/tree             — 组织树
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.database import get_db
from ...api.deps import get_current_user, require_permission, UserContext, get_pagination_params
from ...services.org_service import OrgService, OrgError
from ...schemas.org import (
    SchoolCreate,
    SchoolRead,
    SchoolUpdate,
    GradeCreate,
    GradeRead,
    GradeUpdate,
    ClassCreate,
    ClassRead,
    ClassUpdate,
)
from ...schemas.base import PaginatedResponse

router = APIRouter(prefix="", tags=["org"])


# ═══════════════════════════════════════════════════════════
# School endpoints
# ═══════════════════════════════════════════════════════════

@router.get("/schools", response_model=PaginatedResponse[SchoolRead])
async def list_schools(
    db: AsyncSession = Depends(get_db),
    pagination: dict = Depends(get_pagination_params),
    user: UserContext = Depends(get_current_user),
):
    """获取学校列表（分页）。"""
    items, total = await OrgService.list_schools(
        db, limit=pagination["limit"], offset=pagination["offset"]
    )
    return PaginatedResponse(
        items=items, total=total,
        limit=pagination["limit"], offset=pagination["offset"],
    )


@router.post("/schools", response_model=SchoolRead, status_code=status.HTTP_201_CREATED)
async def create_school(
    data: SchoolCreate,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_permission("school", "create")),
):
    """创建学校。"""
    try:
        return await OrgService.create_school(db, data)
    except OrgError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.detail)


@router.get("/schools/{school_id}", response_model=SchoolRead)
async def get_school(
    school_id: int,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(get_current_user),
):
    """获取学校详情。"""
    try:
        return await OrgService.get_school(db, school_id)
    except OrgError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.detail)


@router.patch("/schools/{school_id}", response_model=SchoolRead)
async def update_school(
    school_id: int,
    data: SchoolUpdate,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_permission("school", "update")),
):
    """更新学校信息。"""
    try:
        return await OrgService.update_school(db, school_id, data)
    except OrgError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.detail)


@router.delete("/schools/{school_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_school(
    school_id: int,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_permission("school", "delete")),
):
    """删除学校。"""
    try:
        await OrgService.delete_school(db, school_id)
    except OrgError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.detail)


# ═══════════════════════════════════════════════════════════
# Grade endpoints
# ═══════════════════════════════════════════════════════════

@router.get("/schools/{school_id}/grades", response_model=PaginatedResponse[GradeRead])
async def list_grades(
    school_id: int,
    db: AsyncSession = Depends(get_db),
    pagination: dict = Depends(get_pagination_params),
    user: UserContext = Depends(get_current_user),
):
    """获取某学校下的年级列表（分页）。"""
    try:
        items, total = await OrgService.list_grades_by_school(
            db, school_id, limit=pagination["limit"], offset=pagination["offset"]
        )
    except OrgError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.detail)
    return PaginatedResponse(
        items=items, total=total,
        limit=pagination["limit"], offset=pagination["offset"],
    )


@router.post("/grades", response_model=GradeRead, status_code=status.HTTP_201_CREATED)
async def create_grade(
    data: GradeCreate,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_permission("grade", "create")),
):
    """创建年级。"""
    try:
        return await OrgService.create_grade(db, data)
    except OrgError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.detail)


@router.get("/grades/{grade_id}", response_model=GradeRead)
async def get_grade(
    grade_id: int,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(get_current_user),
):
    """获取年级详情。"""
    try:
        return await OrgService.get_grade(db, grade_id)
    except OrgError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.detail)


@router.patch("/grades/{grade_id}", response_model=GradeRead)
async def update_grade(
    grade_id: int,
    data: GradeUpdate,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_permission("grade", "update")),
):
    """更新年级信息。"""
    try:
        return await OrgService.update_grade(db, grade_id, data)
    except OrgError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.detail)


@router.delete("/grades/{grade_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_grade(
    grade_id: int,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_permission("grade", "delete")),
):
    """删除年级。"""
    try:
        await OrgService.delete_grade(db, grade_id)
    except OrgError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.detail)


# ═══════════════════════════════════════════════════════════
# Class endpoints
# ═══════════════════════════════════════════════════════════

@router.get("/grades/{grade_id}/classes", response_model=PaginatedResponse[ClassRead])
async def list_classes(
    grade_id: int,
    db: AsyncSession = Depends(get_db),
    pagination: dict = Depends(get_pagination_params),
    user: UserContext = Depends(get_current_user),
):
    """获取某年级下的班级列表（分页）。"""
    try:
        items, total = await OrgService.list_classes_by_grade(
            db, grade_id, limit=pagination["limit"], offset=pagination["offset"]
        )
    except OrgError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.detail)
    return PaginatedResponse(
        items=items, total=total,
        limit=pagination["limit"], offset=pagination["offset"],
    )


@router.post("/classes", response_model=ClassRead, status_code=status.HTTP_201_CREATED)
async def create_class(
    data: ClassCreate,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_permission("class", "create")),
):
    """创建班级。"""
    try:
        return await OrgService.create_class(db, data)
    except OrgError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.detail)


@router.get("/classes/{class_id}", response_model=ClassRead)
async def get_class(
    class_id: int,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(get_current_user),
):
    """获取班级详情。"""
    try:
        return await OrgService.get_class(db, class_id)
    except OrgError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.detail)


@router.patch("/classes/{class_id}", response_model=ClassRead)
async def update_class(
    class_id: int,
    data: ClassUpdate,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_permission("class", "update")),
):
    """更新班级信息。"""
    try:
        return await OrgService.update_class(db, class_id, data)
    except OrgError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.detail)


@router.delete("/classes/{class_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_class(
    class_id: int,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_permission("class", "delete")),
):
    """删除班级。"""
    try:
        await OrgService.delete_class(db, class_id)
    except OrgError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.detail)


# ═══════════════════════════════════════════════════════════
# Org Tree
# ═══════════════════════════════════════════════════════════

@router.get("/org/tree")
async def get_org_tree(
    school_id: int | None = Query(None, description="可选：只返回指定学校的树"),
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(get_current_user),
):
    """获取组织树（school → grades → classes 嵌套结构）。"""
    tree = await OrgService.get_org_tree(db, school_id=school_id)
    return {"success": True, "data": tree}
