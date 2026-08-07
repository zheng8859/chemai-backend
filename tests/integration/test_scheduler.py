"""APScheduler 集成测试 — 每日练习调度 + 逾期通知。

设计文档 tasks.md §5.4。
"""

import pytest
from datetime import datetime, timezone, timedelta

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.services.daily_practice_service import DailyPracticeService
from app.models.user import Student, Account
from app.models.org import School, Grade, Class as ClassModel
from app.models.diagnosis import ReviewTask
from app.models.homework import StudentParentBinding, ParentNotification
from app.core.enums import (
    AccountRole, StudentStatus, ReviewTaskStatus, NotificationType,
)


# ── Helpers ────────────────────────────────────────────────────

async def _create_approved_student(db: AsyncSession) -> Student:
    """创建已审批学生。"""
    import uuid
    account = Account(
        phone=f"138{uuid.uuid4().hex[:6]}",
        password_hash="test_hash",
        role=AccountRole.student,
    )
    db.add(account)
    await db.flush()
    school = School(name="调度器测试学校", region="测试区")
    db.add(school)
    await db.flush()
    grade = Grade(name="高一", school_id=school.id)
    db.add(grade)
    await db.flush()
    class_ = ClassModel(name="调度器测试班", grade_id=grade.id)
    db.add(class_)
    await db.flush()
    student = Student(
        name="调度器测试学生",
        account_id=account.id,
        class_id=class_.id,
        school_id=school.id,
        student_id=f"S{uuid.uuid4().hex[:6].upper()}",
        status=StudentStatus.approved.value,
    )
    db.add(student)
    await db.flush()
    return student


# ── Tests ──────────────────────────────────────────────────────


class TestDailySchedulerIntegration:
    """5.2 / 5.4 每日练习调度器。"""

    @pytest.mark.anyio
    async def test_no_approved_students(self, db_session):
        """无已审批学生 → 返回 0。"""
        result = await DailyPracticeService.run_daily_scheduler(db_session)
        assert result["success"] is True
        assert result["total_students"] == 0
        assert result["assigned_count"] == 0

    @pytest.mark.anyio
    async def test_scheduler_creates_exam_record(self, db_session):
        """已审批学生 → 创建 ExamRecord(type=daily_practice)。"""
        from app.models.teaching import ExamRecord

        from app.models.teaching import Question
        from app.core.enums import QuestionType, Difficulty, QuestionSource

        student = await _create_approved_student(db_session)
        # 种子题目，确保题库非空
        db_session.add(Question(
            content="每日练习测试题",
            question_type=QuestionType.choice,
            options=["A", "B", "C", "D"],
            answer="A",
            difficulty=Difficulty.easy,
            knowledge_point_tags=["化学"],
            source=QuestionSource.ai_generated,
        ))
        await db_session.commit()

        result = await DailyPracticeService.run_daily_scheduler(db_session)
        await db_session.commit()

        assert result["success"] is True
        assert result["total_students"] >= 1
        assert result["assigned_count"] >= 1

        # 验证 ExamRecord 已创建（ExamRecord.class_id，非 student_id）
        exam_records = (await db_session.execute(
            select(ExamRecord).where(
                ExamRecord.class_id == student.class_id,
            )
        )).scalars().all()
        assert len(exam_records) >= 1

    @pytest.mark.anyio
    async def test_scheduler_skips_non_approved(self, db_session):
        """未审批学生 → 跳过。"""
        import uuid
        account = Account(
            phone=f"139{uuid.uuid4().hex[:6]}",
            password_hash="test_hash",
            role=AccountRole.student,
        )
        db_session.add(account)
        await db_session.flush()
        school = School(name="未审批测试学校", region="测试区")
        db_session.add(school)
        await db_session.flush()
        grade = Grade(name="高一", school_id=school.id)
        db_session.add(grade)
        await db_session.flush()
        class_ = ClassModel(name="未审批测试班", grade_id=grade.id)
        db_session.add(class_)
        await db_session.flush()
        student = Student(
            name="未审批学生",
            account_id=account.id,
            class_id=class_.id,
            school_id=school.id,
            student_id=f"S{uuid.uuid4().hex[:6].upper()}",
            status=StudentStatus.pending.value,
        )
        db_session.add(student)
        await db_session.commit()

        result = await DailyPracticeService.run_daily_scheduler(db_session)
        assert result["assigned_count"] == 0


class TestSchedulerNotifyIntegration:
    """5.4 逾期通知。"""

    @pytest.mark.anyio
    async def test_notify_creates_notifications(self, db_session):
        """逾期 ReviewTask + 绑定家长 → 创建 ParentNotification。"""
        import uuid
        from app.models.user import Parent
        from app.models.teaching import Question
        from app.core.enums import QuestionType, Difficulty, QuestionSource
        from app.core.enums import BindingStatus, ParentRelation

        student = await _create_approved_student(db_session)

        # 创建家长
        parent_account = Account(
            phone=f"137{uuid.uuid4().hex[:6]}",
            password_hash="test_hash",
            role=AccountRole.parent,
        )
        db_session.add(parent_account)
        await db_session.flush()
        parent = Parent(
            name="测试家长",
            account_id=parent_account.id,
        )
        db_session.add(parent)
        await db_session.flush()

        # 创建绑定
        binding = StudentParentBinding(
            student_id=student.id,
            parent_id=parent.id,
            status=BindingStatus.active,
            relation=ParentRelation.other,
        )
        db_session.add(binding)

        # 创建题目 + 逾期 ReviewTask
        q = Question(
            content="调度器错题",
            question_type=QuestionType.choice,
            options=["A", "B", "C", "D"],
            answer="A",
            difficulty=Difficulty.medium,
            knowledge_point_tags=["化学"],
            source=QuestionSource.ai_generated,
        )
        db_session.add(q)
        await db_session.flush()

        yesterday = datetime.now(timezone.utc) - timedelta(days=2)
        task = ReviewTask(
            student_id=student.id,
            question_id=q.id,
            level=1,
            status=ReviewTaskStatus.pending,
            next_review_date=yesterday,
        )
        db_session.add(task)
        await db_session.commit()

        result = await DailyPracticeService.notify_parents_of_overdue_reviews(
            db_session,
        )
        await db_session.commit()

        assert result["success"] is True
        assert result["notifications_created"] >= 1
        assert result["overdue_count"] >= 1

        # 验证 ParentNotification 已创建
        notifications = (await db_session.execute(
            select(ParentNotification).where(
                ParentNotification.parent_id == parent.id,
            )
        )).scalars().all()
        assert len(notifications) >= 1
        assert notifications[0].notification_type == NotificationType.warning_alert
        assert "逾期" in notifications[0].title
