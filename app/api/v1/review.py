"""间隔复习与错题训练 API 路由。

设计文档 tasks.md §4.5-4.13。
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.database import get_db
from ...api.deps import get_current_user, UserContext
from ...services.review_service import ReviewService, ReviewError
from ...schemas.teaching import (
    ReviewSubmitRequest,
    MarkMasteredRequest,
    VariantGenerateRequest,
    TrainingCreateRequest,
    TrainingSubmitRequest,
)

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
        tasks, total = await ReviewService.list_pending_reviews(
            db, id, limit=limit, offset=offset,
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


# ── 4.8 GET /api/review/wrong/list ────────────────────────────────────

@router.get("/wrong/list")
async def get_wrong_questions(
    student_id: int = Query(..., description="学生 ID"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    kp_filter: str | None = Query(None, description="知识点过滤"),
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(get_current_user),
):
    """获取学生的错题列表（按错误次数降序，支持知识点过滤）。"""
    try:
        items, total = await ReviewService.get_wrong_questions(
            db, student_id, limit=limit, offset=offset, kp_filter=kp_filter,
        )
        return {"success": True, "data": items, "total": total}
    except ReviewError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error_code": e.error_code, "message": e.detail},
        )


# ── 4.9 POST /api/review/wrong/{question_id}/master ───────────────────

@router.post("/wrong/{question_id}/master")
async def mark_mastered(
    question_id: int,
    data: MarkMasteredRequest,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(get_current_user),
):
    """标记题目为已掌握。"""
    try:
        result = await ReviewService.mark_mastered(db, data.student_id, question_id)
        return {"success": True, "data": result}
    except ReviewError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error_code": e.error_code, "message": e.detail},
        )


# ── 4.10 POST /api/review/wrong-topic/variant/generate ────────────────

@router.post("/wrong-topic/variant/generate")
async def generate_variants(
    data: VariantGenerateRequest,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(get_current_user),
):
    """为指定题目生成变式题。"""
    try:
        result = await ReviewService.generate_variants(db, data.question_id, data.count)
        return {"success": True, "data": result}
    except ReviewError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error_code": e.error_code, "message": e.detail},
        )


# ── 4.11 POST /api/review/wrong-topic/training/create ─────────────────

@router.post("/wrong-topic/training/create")
async def create_training(
    data: TrainingCreateRequest,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(get_current_user),
):
    """创建一次错题强化训练。"""
    try:
        result = await ReviewService.create_training_session(
            db, data.student_id, data.question_ids,
        )
        return {"success": True, "data": result}
    except ReviewError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error_code": e.error_code, "message": e.detail},
        )


# ── 4.12 POST /api/review/wrong-topic/training/submit ─────────────────

@router.post("/wrong-topic/training/submit")
async def submit_training(
    data: TrainingSubmitRequest,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(get_current_user),
):
    """提交错题强化训练结果。"""
    try:
        answers = [a.model_dump() for a in data.answers]
        result = await ReviewService.submit_training(
            db, data.session_id, data.student_id, answers,
        )
        return {"success": True, "data": result}
    except ReviewError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error_code": e.error_code, "message": e.detail},
        )


# ── 4.13 GET /api/review/wrong-topic/knowledge-points ─────────────────

@router.get("/wrong-topic/knowledge-points")
async def list_wrong_knowledge_points(
    student_id: int = Query(..., description="学生 ID"),
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(get_current_user),
):
    """列出学生错题涉及的知识点列表（从错题聚合）。"""
    try:
        items, _ = await ReviewService.get_wrong_questions(
            db, student_id, limit=1000, offset=0,
        )
        # 从错题列表提取所有知识点，去重
        kps: dict[str, int] = {}
        for item in items:
            for kp in (item.get("knowledge_point_tags") or []):
                if kp:
                    kps[kp] = kps.get(kp, 0) + 1
        result = [
            {"name": kp, "wrong_count": count}
            for kp, count in sorted(kps.items(), key=lambda x: -x[1])
        ]
        return {"success": True, "data": result, "total": len(result)}
    except ReviewError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error_code": e.error_code, "message": e.detail},
        )
