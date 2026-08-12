"""学生练习统计 API 路由 — "我的"页面卡片数据。

端点：
- GET /api/v1/student/{student_id}/stats — 获取学生 5 项练习统计聚合
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.database import get_db
from ...api.deps import require_student_self
from ...services.stats_service import StatsService
from ...schemas.stats import StudentStatsResponse

router = APIRouter(prefix="/student", tags=["student-stats"])


@router.get("/{student_id}/stats", response_model=StudentStatsResponse)
async def get_student_stats(
    student_id: int,
    db: AsyncSession = Depends(get_db),
    student_db_id: int = Depends(require_student_self()),
):
    """获取学生练习统计聚合数据（"我的"页面卡片）。

    返回 5 项指标：
    - total_practices: 累计完成练习次数
    - overall_accuracy: 加权指数衰减正确率
    - streak_days: 连续打卡天数
    - total_wrong_questions: 错题存量
    - review_due_today: 今日待复习任务数

    权限：仅学生本人可访问自己的统计数据。
    """
    return await StatsService.get_student_stats(db, student_db_id)
