"""Home-school API router — 教师端报告发送（绑定/通知已迁移至 parent.py）。"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.database import get_db
from ...api.deps import get_current_user, UserContext
from ...services.homework_service import HomeworkService

router = APIRouter(prefix="", tags=["homework"])


# ── Reports ──────────────────────────────────────────────────

@router.post("/reports/send-to-students/{exam_id}")
async def send_exam_reports(
    exam_id: int,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(get_current_user),
):
    """发送考试报告给所有绑定家长。"""
    return await HomeworkService.send_exam_reports(db, exam_id)
