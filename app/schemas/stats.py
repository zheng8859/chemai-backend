"""学生练习统计 — 响应 Pydantic 模型。"""

from typing import Optional

from pydantic import BaseModel, Field


class StudentStatsResponse(BaseModel):
    """学生练习统计聚合视图（"我的"页面卡片数据）。

    包含 5 个指标：
    - total_practices: 累计完成练习次数
    - overall_accuracy: 加权指数衰减正确率（None 表示无数据）
    - streak_days: 连续打卡天数（从今天往回算的连续有练习的天数）
    - total_wrong_questions: 错题存量
    - review_due_today: 今日待复习任务数
    """

    total_practices: int = Field(0, description="累计完成练习次数")
    overall_accuracy: Optional[float] = Field(None, description="加权指数衰减正确率")
    streak_days: int = Field(0, description="连续打卡天数")
    total_wrong_questions: int = Field(0, description="错题存量")
    review_due_today: int = Field(0, description="今日待复习任务数")

    model_config = {"from_attributes": True}
