"""学情面板 / 预警 / 学习计划 / 练习统计 四组 schema 单测。"""

from datetime import datetime

import pytest
from pydantic import ValidationError

from app.schemas.learning_plan import (
    LearningPlanCreate,
    LearningPlanEmptyResponse,
    LearningPlanResponse,
    LearningPlanTaskCreate,
    LearningPlanTaskResponse,
    LearningPlanUpdate,
)
from app.schemas.panel import (
    AccuracyTrendItem,
    BarrierDistribution,
    BarrierHistoryItem,
    ClassListItem,
    ClassOverview,
    ConcernStudent,
    ExamTrendItem,
    ImproverStudent,
    KnowledgePointErrorRate,
    StudentDetail,
    StudentKnowledgePoint,
)
from app.schemas.stats import StudentStatsResponse
from app.schemas.warning import (
    WarningCheckResponse,
    WarningDetail,
    WarningListItem,
    WarningStats,
    WarningStatusUpdate,
)


class TestStudentStats:
    def test_defaults(self):
        r = StudentStatsResponse()
        assert r.total_practices == 0
        assert r.overall_accuracy is None
        assert r.streak_days == 0
        assert r.total_wrong_questions == 0
        assert r.review_due_today == 0

    def test_full(self):
        r = StudentStatsResponse(
            total_practices=12, overall_accuracy=0.85,
            streak_days=3, total_wrong_questions=5, review_due_today=2,
        )
        assert r.total_practices == 12
        assert r.overall_accuracy == 0.85


class TestWarningSchemas:
    def test_list_item(self):
        item = WarningListItem(
            id=1, student_id=10, student_name="张三", class_id=100, class_name="高一(1)班",
            warning_type="streak_break", severity="high", title="连续缺勤",
            created_at=datetime(2026, 8, 16),
        )
        assert item.status == "pending"
        assert item.student_name == "张三"

    def test_detail(self):
        d = WarningDetail(
            id=1, student_id=10, student_name="张三", class_id=100, class_name="高一(1)班",
            warning_type="score_drop", severity="high", title="成绩下滑", message="...",
            status="pending", created_at=datetime(2026, 8, 16),
        )
        assert d.data is None
        assert d.processed_by is None

    def test_status_update(self):
        u = WarningStatusUpdate(status="resolved", note="已沟通")
        assert u.status == "resolved"
        assert u.note == "已沟通"

    def test_stats_defaults(self):
        s = WarningStats()
        assert s.total == 0
        assert s.by_type == {}
        assert s.by_severity == {}

    def test_check_response(self):
        r = WarningCheckResponse(task_id="t-1")
        assert r.task_id == "t-1"
        assert r.status == "scheduled"


class TestLearningPlanSchemas:
    def test_task_create(self):
        t = LearningPlanTaskCreate(
            day_number=1, task_description="复习氧化还原",
            knowledge_points=["氧化还原", "电子守恒"],
        )
        assert t.estimated_minutes == 30
        assert t.knowledge_points == ["氧化还原", "电子守恒"]

    def test_task_response(self):
        t = LearningPlanTaskResponse(
            id=1, plan_id=10, day_number=1, task_description="复习",
            estimated_minutes=20, status="pending",
        )
        assert t.knowledge_points is None
        assert t.completed_at is None

    def test_plan_create(self):
        p = LearningPlanCreate(
            student_id=10, title="暑期计划",
            tasks=[{"day_number": 1, "task_description": "复习"}],
        )
        assert p.created_by == "teacher"
        assert len(p.tasks) == 1

    def test_plan_create_requires_tasks(self):
        with pytest.raises(ValidationError):
            LearningPlanCreate(student_id=10, title="空计划", tasks=[])

    def test_plan_update(self):
        u = LearningPlanUpdate(title="新标题")
        assert u.title == "新标题"
        assert u.tasks is None

    def test_plan_response(self):
        p = LearningPlanResponse(
            id=1, student_id=10, title="计划", is_active=True,
            created_at=datetime(2026, 8, 1), updated_at=datetime(2026, 8, 2),
        )
        assert p.tasks == []
        assert p.is_active is True

    def test_empty_response(self):
        r = LearningPlanEmptyResponse()
        assert r.plan is None
        assert r.message == "暂无学习计划"


class TestPanelSchemas:
    def test_knowledge_point_error_rate(self):
        k = KnowledgePointErrorRate(name="氧化还原", error_rate=0.2)
        assert k.name == "氧化还原"
        assert k.error_rate == 0.2

    def test_student_knowledge_point(self):
        k = StudentKnowledgePoint(name="化学平衡", error_rate=0.3)
        assert k.trend == "stable"

    def test_barrier_distribution(self):
        b = BarrierDistribution(barrier_type="concept", count=3, percentage=30.0)
        assert b.count == 3

    def test_improver_student(self):
        s = ImproverStudent(student_id=1, student_name="李四", change=0.15)
        assert s.change == 0.15

    def test_concern_student(self):
        c = ConcernStudent(student_id=2, name="王五")
        assert c.warning_count == 0
        assert c.latest_warning_type is None

    def test_exam_trend_item(self):
        e = ExamTrendItem(exam_id=1, exam_name="期中")
        assert e.exam_date is None
        assert e.avg_score is None
        assert e.participant_count == 0

    def test_barrier_history_item(self):
        b = BarrierHistoryItem(
            snapshot_at=datetime(2026, 8, 1), profile={"concept": 0.5},
        )
        assert b.dominant_barrier is None

    def test_accuracy_trend_item(self):
        a = AccuracyTrendItem(source_type="exam", accuracy=0.9)
        assert a.date is None
        assert a.total_questions == 0

    def test_student_detail(self):
        d = StudentDetail(student_info={"id": 1, "name": "赵六", "class_name": "高一(1)班"})
        assert d.accuracy_trend == []
        assert d.weak_knowledge_points == []

    def test_class_overview(self):
        o = ClassOverview(class_id=100, class_name="高一(1)班", student_count=40)
        assert o.avg_score is None
        assert o.knowledge_points == []
        assert o.barrier_distribution == []
        assert o.top_improvers == []
        assert o.top_declining == []
        assert o.concern_students == []
        assert o.exam_count == 0

    def test_class_list_item(self):
        c = ClassListItem(class_id=100, class_name="高一(1)班", student_count=40)
        assert c.recent_avg_score is None
        assert c.concern_count == 0
        assert c.last_exam_date is None
