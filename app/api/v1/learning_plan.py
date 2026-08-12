"""学习计划 API 路由 — 教师创建/更新，学生查看/执行。

端点：
- POST   /api/v1/learning-plan                  — 教师创建学习计划
- PUT    /api/v1/learning-plan/{plan_id}         — 教师更新学习计划
- GET    /api/v1/learning-plan/{student_id}      — 学生获取活跃计划
- PATCH  /api/v1/learning-plan/tasks/{task_id}/complete — 学生标记任务完成
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.database import get_db
from ...api.deps import get_current_user, UserContext, require_student_self
from ...services.learning_plan_service import LearningPlanService, LearningPlanError
from ...schemas.learning_plan import (
    LearningPlanCreate,
    LearningPlanUpdate,
    LearningPlanResponse,
    LearningPlanTaskResponse,
)

router = APIRouter(prefix="/learning-plan", tags=["learning-plan"])


# ── POST: 教师创建学习计划 ──

@router.post(
    "",
    response_model=LearningPlanResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_learning_plan(
    data: LearningPlanCreate,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(get_current_user),
):
    """教师为学生创建学习计划。

    自动归档该学生旧的活跃计划（is_active=false）。
    """
    if user.role != "teacher":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="仅教师角色可创建学习计划",
        )
    try:
        return await LearningPlanService.create_plan(db, data, user.user_id)
    except LearningPlanError as e:
        status_code_map = {
            "FORBIDDEN": status.HTTP_403_FORBIDDEN,
            "CONFLICT": status.HTTP_409_CONFLICT,
        }
        code = status_code_map.get(e.error_code, status.HTTP_404_NOT_FOUND)
        raise HTTPException(status_code=code, detail=e.detail)


# ── PUT: 教师更新学习计划 ──

@router.put("/{plan_id}", response_model=LearningPlanResponse)
async def update_learning_plan(
    plan_id: int,
    data: LearningPlanUpdate,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(get_current_user),
):
    """教师更新学习计划（全量替换任务列表）。"""
    if user.role != "teacher":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="仅教师角色可更新学习计划",
        )
    try:
        return await LearningPlanService.update_plan(db, plan_id, data)
    except LearningPlanError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.detail)


# ── GET: 学生获取活跃计划 ──

@router.get("/{student_id}")
async def get_active_learning_plan(
    student_id: int,
    db: AsyncSession = Depends(get_db),
    student_db_id: int = Depends(require_student_self()),
):
    """学生获取自己当前活跃的学习计划（含所有任务，按 day_number 排序）。

    无活跃计划时返回 plan=null。
    """
    result = await LearningPlanService.get_active_plan(db, student_db_id)
    if result is None:
        return {"plan": None, "message": "暂无学习计划"}
    return {"plan": result, "message": "ok"}


# ── PATCH: 学生标记任务完成 ──

@router.patch("/tasks/{task_id}/complete", response_model=LearningPlanTaskResponse)
async def mark_task_complete(
    task_id: int,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(get_current_user),
):
    """学生将学习计划中的任务标记为已完成。

    校验：
    - 该任务属于当前学生的活跃计划
    - 任务状态为 pending（未完成）
    """
    if user.role != "student":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="仅学生角色可标记任务完成",
        )

    # 解析 student_db_id
    from ...api.deps import resolve_student_id
    student_db_id = await resolve_student_id(db, user.user_id)
    if student_db_id is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="学生档案不存在"
        )

    try:
        return await LearningPlanService.mark_task_complete(db, task_id, student_db_id)
    except LearningPlanError as e:
        status_code_map = {
            "FORBIDDEN": status.HTTP_403_FORBIDDEN,
            "CONFLICT": status.HTTP_409_CONFLICT,
        }
        code = status_code_map.get(e.error_code, status.HTTP_404_NOT_FOUND)
        raise HTTPException(status_code=code, detail=e.detail)
