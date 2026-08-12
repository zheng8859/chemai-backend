"""消息通知 — 请求/响应 Pydantic 模型。"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class NotificationResponse(BaseModel):
    """通知响应体（学生消息列表项）。"""
    id: int
    student_id: int
    type: str = Field(..., description="通知类型：practice_assigned / plan_updated / report_ready")
    title: str
    body: str
    related_id: Optional[int] = None
    read_at: Optional[datetime] = None
    created_at: datetime

    model_config = {"from_attributes": True}
