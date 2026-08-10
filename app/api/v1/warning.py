"""Warning API — 教师端预警引擎（5 端点 + 权限校验）。

端点：
- GET /warning/list — 预警列表（筛选 + 分页）
- GET /warning/{id} — 预警详情
- PATCH /warning/{id}/status — 更新预警状态（含状态机校验）
- GET /warning/stats — 预警统计摘要
- POST /warning/check — 手动触发检测

状态机：pending → processing → resolved
        pending → dismissed
非法转换（resolved/dismissed → pending）返回 422。
"""

import asyncio
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.database import get_db
from ...api.deps import get_current_user, UserContext, verify_teacher
from ...services.early_warning_service import EarlyWarningService
from ...models.diagnosis import WarningLog
from ...schemas.warning import WarningStatusUpdate

router = APIRouter(prefix="/warning", tags=["warning"])

# ── 状态机合法转换 ────────────────────────────────────────────
_VALID_TRANSITIONS = {
    "pending": {"processing", "dismissed"},
    "processing": {"resolved"},
    "resolved": set(),
    "dismissed": set(),
}


# ── 5.2 GET /warning/list ──────────────────────────────────────

@router.get("/list")
async def get_warning_list(
    class_id: int | None = Query(None, description="按班级筛选"),
    severity: str | None = Query(None, description="按严重度筛选"),
    warning_type: str | None = Query(None, description="按类型筛选"),
    status_filter: str | None = Query(None, alias="status", description="按状态筛选"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(get_current_user),
):
    """预警列表（按班级/严重度/类型/状态筛选 + 分页）。

    默认按严重度降序（severe > warning > info），同严重度按创建时间倒序。
    """
    await verify_teacher(db, user)

    # 构建查询条件
    from ...models.user import Student
    from ...models.org import Class

    conditions = []
    if class_id is not None:
        conditions.append(Student.class_id == class_id)
    if severity is not None:
        conditions.append(WarningLog.severity == severity)
    if warning_type is not None:
        conditions.append(WarningLog.warning_type == warning_type)
    if status_filter is not None:
        conditions.append(WarningLog.status == status_filter)

    query = (
        select(WarningLog, Student.name, Student.class_id, Class.name)
        .join(Student, Student.id == WarningLog.student_id)
        .join(Class, Class.id == Student.class_id)
    )
    if conditions:
        from sqlalchemy import and_
        query = query.where(and_(*conditions))

    # 严重度排序：severe=0, warning=1, info=2
    from sqlalchemy import case
    severity_order = case(
        (WarningLog.severity == "severe", 0),
        (WarningLog.severity == "warning", 1),
        else_=2,
    )
    query = query.order_by(severity_order, WarningLog.created_at.desc())

    # 总数
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # 分页
    query = query.offset(offset).limit(limit)
    result = await db.execute(query)
    rows = result.all()

    data = []
    for row in rows:
        wl, st_name, st_class_id, cls_name = row
        data.append({
            "id": wl.id,
            "student_id": wl.student_id,
            "student_name": st_name,
            "class_id": st_class_id,
            "class_name": cls_name,
            "warning_type": wl.warning_type.value if hasattr(wl.warning_type, "value") else str(wl.warning_type),
            "severity": wl.severity.value if hasattr(wl.severity, "value") else str(wl.severity),
            "title": wl.title or "",
            "status": wl.status,
            "created_at": wl.created_at.isoformat(),
        })

    return {"success": True, "data": data, "total": total, "limit": limit, "offset": offset}


# ── 5.5 GET /warning/stats ──────────────────────────────────────
# 注意：必须在 /{warning_id} 之前注册，避免 "stats" 被当作 int 解析导致 422

@router.get("/stats")
async def get_warning_stats(
    class_id: int | None = Query(None, description="按班级筛选（可选）"),
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(get_current_user),
):
    """预警统计摘要：by_type + by_severity + total。"""
    await verify_teacher(db, user)

    from ...models.user import Student

    # 按类型计数
    type_query = select(
        WarningLog.warning_type, func.count(WarningLog.id)
    ).join(Student, Student.id == WarningLog.student_id)
    if class_id is not None:
        type_query = type_query.where(Student.class_id == class_id)
    type_query = type_query.where(WarningLog.status.in_(["pending", "processing"]))
    type_query = type_query.group_by(WarningLog.warning_type)
    type_result = await db.execute(type_query)

    by_type = {}
    for wt, cnt in type_result.all():
        key = wt.value if hasattr(wt, "value") else str(wt)
        by_type[key] = cnt

    # 按严重度计数
    sev_query = select(
        WarningLog.severity, func.count(WarningLog.id)
    ).join(Student, Student.id == WarningLog.student_id)
    if class_id is not None:
        sev_query = sev_query.where(Student.class_id == class_id)
    sev_query = sev_query.where(WarningLog.status.in_(["pending", "processing"]))
    sev_query = sev_query.group_by(WarningLog.severity)
    sev_result = await db.execute(sev_query)

    by_severity = {}
    for sv, cnt in sev_result.all():
        key = sv.value if hasattr(sv, "value") else str(sv)
        by_severity[key] = cnt

    total = sum(by_type.values())

    return {"success": True, "data": {"total": total, "by_type": by_type, "by_severity": by_severity}}


# ── 5.3 GET /warning/{id} ──────────────────────────────────────

@router.get("/{warning_id}")
async def get_warning_detail(
    warning_id: int,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(get_current_user),
):
    """预警详情（含 JSON 数据快照）。"""
    await verify_teacher(db, user)

    from ...models.user import Student
    from ...models.org import Class

    result = await db.execute(
        select(WarningLog, Student.name, Student.class_id, Class.name)
        .join(Student, Student.id == WarningLog.student_id)
        .join(Class, Class.id == Student.class_id)
        .where(WarningLog.id == warning_id)
    )
    row = result.one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="预警不存在")

    wl, st_name, st_class_id, cls_name = row
    return {
        "success": True,
        "data": {
            "id": wl.id,
            "student_id": wl.student_id,
            "student_name": st_name,
            "class_id": st_class_id,
            "class_name": cls_name,
            "warning_type": wl.warning_type.value if hasattr(wl.warning_type, "value") else str(wl.warning_type),
            "severity": wl.severity.value if hasattr(wl.severity, "value") else str(wl.severity),
            "title": wl.title or "",
            "message": wl.message,
            "data": wl.data,
            "status": wl.status,
            "processed_by": wl.processed_by,
            "processed_at": wl.processed_at.isoformat() if wl.processed_at else None,
            "note": wl.note,
            "created_at": wl.created_at.isoformat(),
        },
    }


# ── 5.4 PATCH /warning/{id}/status ─────────────────────────────

@router.patch("/{warning_id}/status")
async def update_warning_status(
    warning_id: int,
    body: WarningStatusUpdate,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(get_current_user),
):
    """更新预警状态（含状态机校验）。"""
    teacher_id = await verify_teacher(db, user)

    wl = await db.get(WarningLog, warning_id)
    if wl is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="预警不存在")

    # 状态机校验
    allowed = _VALID_TRANSITIONS.get(wl.status, set())
    if body.status not in allowed:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"非法状态转换：{wl.status} → {body.status}。"
                f"允许：{'、'.join(sorted(allowed)) if allowed else '无'}"
            ),
        )

    wl.status = body.status
    if body.note is not None:
        wl.note = body.note

    # 若转为 resolved 或 dismissed，记录处理人和处理时间
    if body.status in ("resolved", "dismissed"):
        wl.processed_by = teacher_id
        wl.processed_at = datetime.now(timezone.utc)

    await db.commit()

    return {
        "success": True,
        "data": {
            "id": wl.id,
            "status": wl.status,
            "processed_by": wl.processed_by,
            "processed_at": wl.processed_at.isoformat() if wl.processed_at else None,
        },
    }


# ── 5.6 POST /warning/check ────────────────────────────────────

@router.post("/check")
async def trigger_warning_check(
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(get_current_user),
):
    """手动触发预警检测（异步执行 + 互斥锁防重）。"""
    await verify_teacher(db, user)

    if EarlyWarningService._check_lock.locked():
        raise HTTPException(
            status_code=429,
            detail="已有预警检测任务运行中，请稍后再试",
        )

    task_id = f"wc-{uuid.uuid4().hex[:12]}"

    async def _run_in_background():
        await EarlyWarningService.run_async_check()

    asyncio.create_task(_run_in_background())

    return {
        "success": True,
        "data": {"task_id": task_id, "status": "scheduled"},
    }
