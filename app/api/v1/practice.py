"""自适应练习 API 路由 — 练习任务 / 作答提交 / 效果追踪。

设计文档 tasks.md §4.1-4.4。
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.database import get_db
from ...api.deps import get_current_user, UserContext
from ...services.adaptive_practice_service import (
    AdaptivePracticeService,
    AdaptivePracticeError,
)
from ...schemas.teaching import PracticeBatchSubmitRequest

router = APIRouter(prefix="/practice", tags=["practice"])


# ── 4.2 GET /api/practice/student/{uid}/tasks ──────────────────────────

@router.get("/student/{uid}/tasks")
async def get_student_tasks(
    uid: int,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(get_current_user),
):
    """获取学生的练习任务列表（待完成 + 已完成）。"""
    try:
        tasks = await AdaptivePracticeService.get_student_tasks(db, uid)
        return {"success": True, "data": tasks}
    except AdaptivePracticeError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error_code": e.error_code, "message": e.detail},
        )


# ── 4.3 POST /api/practice/submit ─────────────────────────────────────

@router.post("/submit")
async def submit_practice(
    data: PracticeBatchSubmitRequest,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(get_current_user),
):
    """提交练习答案，触发自动判分 + auto-sync（错题进入复习队列）。"""
    try:
        answers = [a.model_dump() for a in data.answers]
        result = await AdaptivePracticeService.submit_practice(
            db, data.practice_id, answers
        )
        return {"success": True, "data": result}
    except AdaptivePracticeError as e:
        status_code_map = {
            "DUPLICATE_SUBMIT": status.HTTP_409_CONFLICT,
        }
        raise HTTPException(
            status_code=status_code_map.get(e.error_code, status.HTTP_404_NOT_FOUND),
            detail={"error_code": e.error_code, "message": e.detail},
        )


# ── 4.4 GET /api/practice/effect/{student_id} ─────────────────────────

@router.get("/effect/{student_id}")
async def get_practice_effect(
    student_id: int,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(get_current_user),
):
    """获取练习效果追踪（最近 2 次对比）。"""
    try:
        effect = await AdaptivePracticeService.get_practice_effect(db, student_id)
        return {"success": True, "data": effect}
    except AdaptivePracticeError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error_code": e.error_code, "message": e.detail},
        )
