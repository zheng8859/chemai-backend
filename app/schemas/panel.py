"""Panel API — 请求/响应 Pydantic 模型（学情面板聚合 API）。"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# ── 知识点错误率 ──

class KnowledgePointErrorRate(BaseModel):
    """知识点错误率项（班级级精简版）。"""
    name: str = Field(..., description="知识点名称")
    error_rate: float = Field(..., ge=0, le=1, description="错误率")


class StudentKnowledgePoint(BaseModel):
    """学生维度知识点项（含 trend 方向标记）。"""
    name: str = Field(..., description="知识点名称")
    error_rate: float = Field(..., ge=0, le=1, description="错误率")
    trend: str = Field("stable", description="变化方向：up / down / stable")


# ── 障碍类型分布 ──

class BarrierDistribution(BaseModel):
    """障碍类型分布项。"""
    barrier_type: str = Field(..., description="障碍类型：concept / reading / expression")
    count: int = Field(..., ge=0, description="该类型学生人数")
    percentage: float = Field(..., ge=0, le=100, description="占班级总人数百分比")


# ── 进步/退步学生 ──

class ImproverStudent(BaseModel):
    """进步/退步学生信息。"""
    student_id: int
    student_name: str
    change: float = Field(..., description="最近两次考试个人正确率差值（正=进步，负=退步）")


# ── 重点关注学生 ──

class ConcernStudent(BaseModel):
    """重点关注学生项。"""
    student_id: int
    name: str
    warning_count: int = Field(0, description="未处理预警数")
    latest_warning_type: Optional[str] = Field(None, description="最近一次预警类型")
    latest_warning_severity: Optional[str] = Field(None, description="最近一次预警严重度")
    last_practice_time: Optional[datetime] = Field(None, description="最近练习时间")


# ── 考试趋势 ──

class ExamTrendItem(BaseModel):
    """考试趋势数据点。"""
    exam_id: int
    exam_name: str
    exam_date: Optional[datetime] = None
    avg_score: Optional[float] = Field(None, description="班级均分（百分制）")
    participant_count: int = Field(0, description="参考人数")


# ── 障碍画像历史 ──

class BarrierHistoryItem(BaseModel):
    """障碍画像历史快照。"""
    snapshot_at: datetime
    profile: dict = Field(..., description="三维分布 JSON")
    dominant_barrier: Optional[str] = None


# ── 学生详情 ──

class AccuracyTrendItem(BaseModel):
    """正确率趋势数据点。"""
    date: Optional[datetime] = None
    source_type: str = Field(..., description="数据来源：exam / practice")
    accuracy: float = Field(..., ge=0, le=1, description="正确率")
    total_questions: int = Field(0, description="题目总数")


class StudentDetail(BaseModel):
    """学生详情。"""
    student_info: dict = Field(..., description="{id, name, class_name}")
    accuracy_trend: list[AccuracyTrendItem] = Field(default_factory=list)
    weak_knowledge_points: list[StudentKnowledgePoint] = Field(default_factory=list)
    barrier_profile_history: list[BarrierHistoryItem] = Field(default_factory=list)


# ── 班级聚合视图 ──

class ClassOverview(BaseModel):
    """班级聚合视图（GET /panel/class/{class_id}）。"""
    class_id: int
    class_name: str
    student_count: int
    avg_score: Optional[float] = Field(None, description="加权指数衰减均分")
    knowledge_points: list[KnowledgePointErrorRate] = Field(default_factory=list, description="错误率 Top 5")
    barrier_distribution: list[BarrierDistribution] = Field(default_factory=list)
    top_improvers: list[ImproverStudent] = Field(default_factory=list, description="进步 Top 3")
    top_declining: list[ImproverStudent] = Field(default_factory=list, description="退步 Top 3")
    concern_students: list[ConcernStudent] = Field(default_factory=list)
    exam_count: int = Field(0, description="考试次数")


# ── 班级列表项（Dashboard 首页） ──

class ClassListItem(BaseModel):
    """教师 Dashboard 班级列表项。"""
    class_id: int
    class_name: str
    student_count: int
    recent_avg_score: Optional[float] = Field(None, description="最近一次考试班级均分")
    concern_count: int = Field(0, description="预警未处理学生数")
    last_exam_date: Optional[datetime] = Field(None, description="最近一次考试日期")
