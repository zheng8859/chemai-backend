"""自适应练习 API 路由 — 练习任务 / 作答提交 / 效果追踪 / 错题管理。

设计文档 tasks.md §4.1-4.4, §4.8-4.13。
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.database import get_db
from ...api.deps import get_current_user, UserContext, resolve_student_id
from ...services.adaptive_practice_service import (
    AdaptivePracticeService,
    AdaptivePracticeError,
)
from ...services.review_service import ReviewService, ReviewError
from ...schemas.teaching import (
    PracticeBatchSubmitRequest,
    MarkMasteredRequest,
    VariantGenerateRequest,
    TrainingCreateRequest,
    TrainingSubmitRequest,
)
from ...schemas.diagnosis import PracticeAssignRequest

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
        student_id = await resolve_student_id(db, uid)
        if student_id is None:
            return {"success": True, "data": {"pending": [], "completed": []}}
        tasks = await AdaptivePracticeService.get_student_tasks(db, student_id)
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
            db, data.practice_id, answers, current_user_id=user.user_id,
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
        sid = await resolve_student_id(db, student_id)
        if sid is None:
            return {"success": True, "data": {"sessions": [], "comparison": None}}
        effect = await AdaptivePracticeService.get_practice_effect(db, sid)
        return {"success": True, "data": effect}
    except AdaptivePracticeError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error_code": e.error_code, "message": e.detail},
        )


# ── 4.5 POST /api/practice/assign ────────────────────────────────────

@router.post("/assign")
async def assign_practice(
    data: PracticeAssignRequest,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(get_current_user),
):
    """教师为学生分配自适应练习（需教师权限）。"""
    if user.role not in ("teacher", "system_admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error_code": "FORBIDDEN", "message": "仅教师可分配练习"},
        )
    try:
        result = await AdaptivePracticeService.create_practice(
            db,
            student_id=data.student_id,
            question_count=data.question_count,
            kp_override=data.knowledge_points,
        )
        return {
            "success": True,
            "data": {
                "practice_id": result["practice_id"],
                "question_count": result["question_count"],
                "zpd_difficulty": result["zpd_difficulty"],
                "target_kps": result["target_kps"],
            },
        }
    except AdaptivePracticeError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error_code": e.error_code, "message": e.detail},
        )


# ── 4.8 GET /api/practice/wrong/list ──────────────────────────────────

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
        sid = await resolve_student_id(db, student_id)
        if sid is None:
            return {"success": True, "data": [], "total": 0}
        items, total = await ReviewService.get_wrong_questions(
            db, sid, limit=limit, offset=offset, kp_filter=kp_filter,
        )
        return {"success": True, "data": items, "total": total}
    except ReviewError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error_code": e.error_code, "message": e.detail},
        )


# ── 4.9 POST /api/practice/wrong/{question_id}/master ─────────────────

@router.post("/wrong/{question_id}/master")
async def mark_mastered(
    question_id: int,
    data: MarkMasteredRequest,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(get_current_user),
):
    """标记题目为已掌握。"""
    try:
        sid = await resolve_student_id(db, data.student_id)
        if sid is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error_code": "STUDENT_NOT_FOUND", "message": "学生档案不存在"},
            )
        result = await ReviewService.mark_mastered(db, sid, question_id)
        return {"success": True, "data": result}
    except ReviewError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error_code": e.error_code, "message": e.detail},
        )


# ── 4.10 POST /api/practice/wrong-topic/variant/generate ──────────────

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


# ── 4.11 POST /api/practice/wrong-topic/training/create ───────────────

@router.post("/wrong-topic/training/create")
async def create_training(
    data: TrainingCreateRequest,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(get_current_user),
):
    """创建一次错题强化训练。"""
    try:
        sid = await resolve_student_id(db, data.student_id)
        if sid is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error_code": "STUDENT_NOT_FOUND", "message": "学生档案不存在"},
            )
        result = await ReviewService.create_training_session(
            db, sid, data.question_ids,
        )
        return {"success": True, "data": result}
    except ReviewError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error_code": e.error_code, "message": e.detail},
        )


# ── 4.12 POST /api/practice/wrong-topic/training/submit ───────────────

@router.post("/wrong-topic/training/submit")
async def submit_training(
    data: TrainingSubmitRequest,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(get_current_user),
):
    """提交错题强化训练结果。"""
    try:
        sid = await resolve_student_id(db, data.student_id)
        if sid is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error_code": "STUDENT_NOT_FOUND", "message": "学生档案不存在"},
            )
        answers = [a.model_dump() for a in data.answers]
        result = await ReviewService.submit_training(
            db, data.session_id, sid, answers,
        )
        return {"success": True, "data": result}
    except ReviewError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error_code": e.error_code, "message": e.detail},
        )


# ── 4.13 GET /api/practice/wrong-topic/knowledge-points ───────────────

@router.get("/wrong-topic/knowledge-points")
async def list_wrong_knowledge_points(
    student_id: int = Query(..., description="学生 ID"),
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(get_current_user),
):
    """列出学生错题涉及的知识点列表（从错题聚合）。"""
    try:
        sid = await resolve_student_id(db, student_id)
        if sid is None:
            return {"success": True, "data": [], "total": 0}
        items, _ = await ReviewService.get_wrong_questions(
            db, sid, limit=1000, offset=0,
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
