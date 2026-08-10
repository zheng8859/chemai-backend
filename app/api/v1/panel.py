"""Panel API — 教师端学情面板（7 端点 + 权限校验）。

端点：
- GET /panel/classes — 教师 Dashboard 班级列表
- GET /panel/class/{class_id} — 班级聚合视图
- GET /panel/class/{class_id}/student/{student_id} — 学生详情
- GET /panel/class/{class_id}/knowledge-points — 知识点维度展开
- GET /panel/class/{class_id}/barriers — 障碍类型维度展开
- GET /panel/class/{class_id}/concern-students — 重点关注学生
- GET /panel/class/{class_id}/exam-trend — 考试趋势
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ...infrastructure.database import get_db
from ...api.deps import get_current_user, UserContext, verify_teacher
from ...services.panel_service import PanelService
from ...models.user import TeacherClassSubject

router = APIRouter(prefix="/panel", tags=["panel"])


# ── 教师权限校验 helper（含班级访问权限）────────────────────────

async def _verify_teacher_access(
    db: AsyncSession,
    user: UserContext,
    class_id: int | None = None,
) -> int:
    """验证教师权限 + 可选班级访问权。

    调用 shared verify_teacher 做基础校验，再验证班级任课关系。

    Returns:
        Teacher.id（数据库主键，非 Account.id）

    Raises:
        403: 非教师角色或无权访问该班级
    """
    teacher_id = await verify_teacher(db, user)

    if class_id is not None:
        tcs_result = await db.execute(
            select(TeacherClassSubject).where(
                TeacherClassSubject.teacher_id == teacher_id,
                TeacherClassSubject.class_id == class_id,
            )
        )
        if tcs_result.scalar_one_or_none() is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="无权访问该班级数据",
            )

    return teacher_id


# ── 4.2 GET /panel/classes ─────────────────────────────────────

@router.get("/classes")
async def get_classes(
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(get_current_user),
):
    """教师 Dashboard：所教班级列表 + 每班简要指标。"""
    teacher_id = await _verify_teacher_access(db, user)
    data = await PanelService.get_teacher_classes(db, teacher_id)
    return {"success": True, "data": data}


# ── 4.3 GET /panel/class/{class_id} ────────────────────────────

@router.get("/class/{class_id}")
async def get_class_overview(
    class_id: int,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(get_current_user),
):
    """班级聚合视图。"""
    await _verify_teacher_access(db, user, class_id)
    data = await PanelService.get_class_overview(db, class_id)
    if data is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="班级不存在",
        )
    return {"success": True, "data": data}


# ── 4.4 GET /panel/class/{class_id}/student/{student_id} ───────

@router.get("/class/{class_id}/student/{student_id}")
async def get_student_detail(
    class_id: int,
    student_id: int,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(get_current_user),
):
    """学生详情抽屉。"""
    await _verify_teacher_access(db, user, class_id)
    data = await PanelService.get_student_detail(db, class_id, student_id)
    if data is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="学生不存在或不属于该班级",
        )
    return {"success": True, "data": data}


# ── 4.5 GET /panel/class/{class_id}/knowledge-points ───────────

@router.get("/class/{class_id}/knowledge-points")
async def get_knowledge_points(
    class_id: int,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(get_current_user),
):
    """知识点维度展开（分页）。"""
    await _verify_teacher_access(db, user, class_id)
    data = await PanelService.get_knowledge_points(db, class_id, limit, offset)
    return {"success": True, **data}


# ── 4.6 GET /panel/class/{class_id}/barriers ───────────────────

@router.get("/class/{class_id}/barriers")
async def get_barriers(
    class_id: int,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(get_current_user),
):
    """障碍类型维度展开。"""
    await _verify_teacher_access(db, user, class_id)
    data = await PanelService.get_barriers(db, class_id)
    return {"success": True, "data": data}


# ── 4.7 GET /panel/class/{class_id}/concern-students ───────────

@router.get("/class/{class_id}/concern-students")
async def get_concern_students(
    class_id: int,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(get_current_user),
):
    """重点关注学生列表。"""
    await _verify_teacher_access(db, user, class_id)
    data = await PanelService.get_concern_students(db, class_id)
    return {"success": True, "data": data}


# ── 4.8 GET /panel/class/{class_id}/exam-trend ─────────────────

@router.get("/class/{class_id}/exam-trend")
async def get_exam_trend(
    class_id: int,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(get_current_user),
):
    """班级历次考试均分趋势。"""
    await _verify_teacher_access(db, user, class_id)
    data = await PanelService.get_exam_trend(db, class_id)
    return {"success": True, "data": data}
