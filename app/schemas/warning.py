"""Warning API — 请求/响应 Pydantic 模型（预警引擎 API）。"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# ── 预警列表项 ──

class WarningListItem(BaseModel):
    """预警列表项（GET /warning/list）。"""
    id: int
    student_id: int
    student_name: str
    class_id: int
    class_name: str
    warning_type: str = Field(..., description="预警类型枚举值")
    severity: str = Field(..., description="严重度枚举值")
    title: str
    status: str = Field("pending", description="预警状态")
    created_at: datetime


# ── 预警详情 ──

class WarningDetail(BaseModel):
    """预警详情（GET /warning/{id}）。"""
    id: int
    student_id: int
    student_name: str
    class_id: int
    class_name: str
    warning_type: str
    severity: str
    title: str
    message: str
    data: Optional[dict] = Field(None, description="JSON 数据快照")
    status: str
    processed_by: Optional[int] = None
    processed_at: Optional[datetime] = None
    note: Optional[str] = None
    created_at: datetime


# ── 更新预警状态 ──

class WarningStatusUpdate(BaseModel):
    """更新预警状态（PATCH /warning/{id}/status）。"""
    status: str = Field(..., description="目标状态：processing / resolved / dismissed")
    note: Optional[str] = Field(None, description="教师备注")


# ── 预警统计摘要 ──

class WarningStats(BaseModel):
    """预警统计摘要（GET /warning/stats）。"""
    total: int = 0
    by_type: dict = Field(default_factory=dict, description="按类型计数")
    by_severity: dict = Field(default_factory=dict, description="按严重度计数")


# ── 手动触发检测响应 ──

class WarningCheckResponse(BaseModel):
    """手动触发预警检测响应（POST /warning/check）。"""
    task_id: str
    status: str = "scheduled"
