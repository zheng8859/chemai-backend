"""家长端 Schema — 请求/响应 Pydantic 模型。

对齐 33-家长端与通知系统设计。
"""

from datetime import datetime, date
from typing import Optional

from pydantic import BaseModel, Field

from ..core.enums import ParentRelation, NotificationType
from .base import ORMBase


# ── 绑定码 ──────────────────────────────────────────────

class BindCodeRequest(BaseModel):
    """学生发送绑定码请求。"""
    bind_code: str = Field(..., min_length=6, max_length=6, pattern=r"^\d{6}$",
                           description="6 位数字绑定码")


class BindRequest(BaseModel):
    """家长提交绑定请求。student_id 可选：不传则通过 bind_code 自动解析学生。"""
    student_id: int | None = None
    bind_code: str = Field(..., min_length=6, max_length=6)
    relation: ParentRelation = ParentRelation.other


class ChildInfo(BaseModel):
    """已绑定子女信息。"""
    student_id: int
    student_name: str
    class_name: str
    school_name: str
    relation: ParentRelation
    binding_id: int


# ── 子女数据查询 ─────────────────────────────────────────

class BarrierProfile(BaseModel):
    """三维障碍画像（0-1 比例值）。"""
    concept: float = Field(default=0, ge=0, le=1, description="概念理解障碍")
    reading: float = Field(default=0, ge=0, le=1, description="审题障碍")
    expression: float = Field(default=0, ge=0, le=1, description="表述障碍")


class ChildOverviewResponse(BaseModel):
    """子女学习概览。"""
    student_id: int
    student_name: str
    weekly_practice_count: int = Field(default=0, description="本周练习次数")
    accuracy_rate: float | None = Field(default=None, description="正确率（加权）")
    streak_days: int = Field(default=0, description="连续学习天数")
    total_practice_count: int = Field(default=0, description="累计练习总量")
    weak_knowledge_points: list[str] = Field(default_factory=list, description="薄弱知识点（通俗描述）")
    characteristics: str = Field(default="暂无足够数据进行分析", description="学习特点通俗描述")
    barriers: BarrierProfile | None = Field(default=None, description="三维障碍画像")
    last_practice_time: datetime | None = None


class WeeklyTimelineItem(BaseModel):
    """每周学习时间线条目。"""
    week_start: date
    week_end: date
    practice_count: int = 0
    accuracy: float | None = None
    topics_covered: list[str] = Field(default_factory=list, description="通俗主题名")


class ChildTimelineResponse(BaseModel):
    """子女学习时间线。"""
    student_id: int
    weeks: list[WeeklyTimelineItem] = Field(default_factory=list)


# ── 周报 ────────────────────────────────────────────────

class WeeklyReportResponse(ORMBase):
    """周报响应。"""
    id: int
    student_id: int
    week_start: date
    week_end: date
    summary: str = Field(max_length=200, description="周报摘要")
    detail: str = Field(max_length=600, description="周报详情")
    advice: str = Field(max_length=400, description="家长建议")
    no_data: bool = False
    generated_at: datetime
    generated_by: str


class WeeklyReportGenerateRequest(BaseModel):
    """手动生成周报请求（无额外参数，从当前数据生成）。"""
    pass


# ── 通知 ────────────────────────────────────────────────

class ParentNotificationResponse(BaseModel):
    """家长通知响应。"""
    id: int
    parent_id: int
    notification_type: NotificationType
    title: str
    body: str
    related_id: int | None = None
    is_read: bool = Field(default=False, description="是否已读（read_at != null）")
    read_at: datetime | None = Field(default=None, description="阅读时间")
    sent_at: datetime

    model_config = {"from_attributes": True}


# ── Agent ────────────────────────────────────────────────

class ParentAgentRequest(BaseModel):
    """家长 Agent 对话请求。"""
    message: str = Field(..., min_length=1, description="家长输入的问题")
    thread_id: str | None = Field(default=None, description="对话线程 ID，新对话留空")
    student_id: int = Field(..., description="当前选中的子女 ID")
