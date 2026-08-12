"""学习计划 API — 请求/响应 Pydantic 模型。"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# ── Task ──

class LearningPlanTaskCreate(BaseModel):
    """创建/更新计划时的单个任务项。"""
    day_number: int = Field(..., ge=1, description="第几天（从 1 开始）")
    task_description: str = Field(..., min_length=1, description="任务描述")
    estimated_minutes: int = Field(30, ge=1, description="预估完成时间（分钟）")
    knowledge_points: Optional[list[str]] = Field(None, description="关联知识点标签数组")


class LearningPlanTaskResponse(BaseModel):
    """学习计划任务项的响应体。"""
    id: int
    plan_id: int
    day_number: int
    task_description: str
    estimated_minutes: int
    knowledge_points: Optional[list[str]] = None
    status: str
    completed_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ── Plan ──

class LearningPlanCreate(BaseModel):
    """教师创建学习计划请求。"""
    student_id: int = Field(..., description="目标学生 Account.id（由教师指定）")
    title: str = Field(..., min_length=1, max_length=200, description="计划标题")
    created_by: Optional[str] = Field("teacher", description="创建来源：teacher / agent")
    tasks: list[LearningPlanTaskCreate] = Field(
        ..., min_length=1, description="任务列表（至少 1 项）"
    )


class LearningPlanUpdate(BaseModel):
    """教师更新学习计划请求 — 全量替换任务列表。"""
    title: Optional[str] = Field(None, min_length=1, max_length=200, description="计划标题")
    tasks: Optional[list[LearningPlanTaskCreate]] = Field(
        None, min_length=1, description="新的任务列表（替换原有全部任务）"
    )


class LearningPlanResponse(BaseModel):
    """学习计划响应体 — 含任务列表。"""
    id: int
    student_id: int
    title: str
    is_active: bool
    created_by: Optional[str] = None
    tasks: list[LearningPlanTaskResponse] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class LearningPlanEmptyResponse(BaseModel):
    """学生无活跃计划时的响应。"""
    plan: None = None
    message: str = "暂无学习计划"
