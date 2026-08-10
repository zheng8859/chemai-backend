"""Home-school schemas — StudentParentBinding, ParentNotification.

Aligned with 35-API §8 (parent/notification routers).
"""

from datetime import datetime
from pydantic import BaseModel, Field

from ..core.enums import ParentRelation, BindingStatus, NotificationType
from .base import ORMBase


# ── StudentParentBinding ───────────────────────────────────
class BindingCreate(BaseModel):
    student_id: int
    parent_id: int
    bind_code: str = Field(..., min_length=6, max_length=6)
    relation: ParentRelation = ParentRelation.other


class BindingRead(ORMBase):
    id: int
    student_id: int
    parent_id: int
    status: BindingStatus
    relation: ParentRelation
    created_at: datetime


# ── ParentNotification ─────────────────────────────────────
class ParentNotificationRead(ORMBase):
    id: int
    parent_id: int
    notification_type: NotificationType
    title: str
    body: str
    related_id: int | None = None
    read_at: datetime | None = None
    sent_at: datetime


class ParentNotificationListParams(BaseModel):
    parent_id: int
    limit: int = 20
    offset: int = 0


# ── WeeklyReport ─────────────────────────────────────────
class WeeklyReportRead(ORMBase):
    id: int
    student_id: int
    week_start: datetime
    week_end: datetime
    summary: str
    detail: str
    advice: str
    no_data: bool
    generated_at: datetime
    generated_by: str


class ReportSendRequest(BaseModel):
    """一键发送报告 (35号 §三: POST /api/report/send-to-students/{exam_record_id})"""
    exam_record_id: int


class ReportSendResponse(BaseModel):
    success: bool = True
    sent_count: int
    failed_count: int
    parent_notifications_sent: int

