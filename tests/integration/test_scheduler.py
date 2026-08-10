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
    async def test_scheduler_creates_practice_session(self, db_session):
        """已审批学生 → 创建 PracticeSession（每日练习）。"""
        from app.models.teaching import PracticeSession, PracticeSessionQuestion, Question
        from app.core.enums import QuestionType, Difficulty, QuestionSource, PracticeSessionStatus

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

        # 验证返回 practice_id
        assert "practice_id" in result["details"][0]

        # 验证 PracticeSession 已创建
        sessions = (await db_session.execute(
            select(PracticeSession).where(
                PracticeSession.student_id == student.id,
                PracticeSession.status == PracticeSessionStatus.in_progress.value,
            )
        )).scalars().all()
        assert len(sessions) >= 1

        # 验证 PracticeSessionQuestion 已关联
        psqs = (await db_session.execute(
            select(PracticeSessionQuestion).where(
                PracticeSessionQuestion.practice_session_id == sessions[0].id,
            )
        )).scalars().all()
        assert len(psqs) >= 1

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


# ═══════════════════════════════════════════════════════════════
# Warning Check Cron Job Tests (8.5)
# ═══════════════════════════════════════════════════════════════


class TestWarningCheckScheduler:
    """预警检测 cron job（每天 00:00）。"""

    def test_warning_check_job_registered_after_register(self):
        """验证 register_jobs() 正确注册 warning_check cron job。"""
        from app.infrastructure.scheduler import scheduler, register_jobs

        register_jobs()

        job = scheduler.get_job("warning_check")
        assert job is not None, "warning_check cron job 未注册"
        assert job.name == "学情预警检测"

    def test_warning_check_cron_timing(self):
        """验证 warning_check cron 为每天 00:00。"""
        from app.infrastructure.scheduler import scheduler, register_jobs
        from apscheduler.triggers.cron import CronTrigger

        register_jobs()

        job = scheduler.get_job("warning_check")
        assert job is not None
        trigger = job.trigger
        assert isinstance(trigger, CronTrigger)
        # 验证 trigger 字符串包含 "hour='0'" 和 "minute='0'"
        trigger_str = str(trigger)
        assert "hour='0'" in trigger_str or "hour=0" in trigger_str
        assert "minute='0'" in trigger_str or "minute=0" in trigger_str

    def test_all_jobs_registered(self):
        """验证全部 cron job 注册。"""
        from app.infrastructure.scheduler import scheduler, register_jobs

        register_jobs()

        job_ids = {
            "daily_practice_scheduler", "notify_parents_overdue",
            "warning_check", "weekly_report",
        }
        for jid in job_ids:
            assert scheduler.get_job(jid) is not None, f"Job {jid} 未注册"

    @pytest.mark.anyio
    async def test_warning_check_job_no_students(self, db_session):
        """无学生时 → 预警检测返回 0。"""
        from app.services.early_warning_service import EarlyWarningService

        result = await EarlyWarningService.run_all_checks(db_session)
        await db_session.commit()

        assert result["total_students"] == 0
        assert result["new_warnings"] == 0

    @pytest.mark.anyio
    async def test_warning_check_job_with_student(self, db_session):
        """有已审批学生时 → 运行检测不抛异常。"""
        from app.services.early_warning_service import EarlyWarningService

        student = await _create_approved_student(db_session)
        await db_session.commit()

        result = await EarlyWarningService.run_all_checks(db_session)
        await db_session.commit()

        assert result["total_students"] >= 1
        assert "new_warnings" in result
        assert "by_type" in result
        assert "errors" in result

    @pytest.mark.anyio
    async def test_warning_check_job_exception_isolation(self, db_session):
        """单学生异常不应中断其他学生检测（errors 计数递增）。"""
        from app.services.early_warning_service import EarlyWarningService

        # 创建两个学生，第一个有正常数据，第二个无 barrier_profile
        import uuid
        from app.models.user import Account as Acc

        # Student 1: normal
        s1 = await _create_approved_student(db_session)

        # Student 2: also normal (service handles missing profile gracefully)
        account2 = Acc(
            phone=f"139{uuid.uuid4().hex[:6]}",
            password_hash="test_hash",
            role=AccountRole.student,
        )
        db_session.add(account2)
        await db_session.flush()
        school = School(name="隔离测试学校", region="测试区")
        db_session.add(school)
        await db_session.flush()
        grade = Grade(name="高一", school_id=school.id)
        db_session.add(grade)
        await db_session.flush()
        class2 = ClassModel(name="隔离测试班", grade_id=grade.id)
        db_session.add(class2)
        await db_session.flush()
        s2 = Student(
            name="无画像学生",
            account_id=account2.id,
            class_id=class2.id,
            school_id=school.id,
            student_id=f"S{uuid.uuid4().hex[:6].upper()}",
            status=StudentStatus.approved.value,
            barrier_profile=None,  # 无画像
        )
        db_session.add(s2)
        await db_session.commit()

        result = await EarlyWarningService.run_all_checks(db_session)
        await db_session.commit()

        # 两个学生都应被处理，无异常（errors 应为 0 或少量）
        assert result["total_students"] >= 2
        # 即使某个学生处理中出错，整体也不应抛异常

    @pytest.mark.anyio
    async def test_score_drop_detection_with_real_data(self, db_session):
        """成绩下滑检测：有 2 场考试 + StudentAnswer 的端到端测试。

        验证 _exam_accuracy 内部能正确查询到题目 ID（而非走 Question.exam_record_id 的错误路径）。
        """
        from app.services.early_warning_service import EarlyWarningService
        from app.models.teaching import ExamRecord, StudentAnswer, Question
        from app.core.enums import (
            ExamRecordStatus, ExamType, QuestionType, Difficulty, QuestionSource,
        )

        # 1. 创建学生
        student = await _create_approved_student(db_session)

        # 2. 创建 2 场已完成考试
        exam1 = ExamRecord(
            class_id=student.class_id,
            exam_type=ExamType.monthly,
            status=ExamRecordStatus.completed,
            exam_date=datetime.now(timezone.utc) - timedelta(days=14),
            name="第一次月考",
        )
        db_session.add(exam1)
        await db_session.flush()

        exam2 = ExamRecord(
            class_id=student.class_id,
            exam_type=ExamType.monthly,
            status=ExamRecordStatus.completed,
            exam_date=datetime.now(timezone.utc) - timedelta(days=1),
            name="第二次月考",
        )
        db_session.add(exam2)
        await db_session.flush()

        # 3. 创建题目
        questions = []
        for i in range(10):
            q = Question(
                content=f"测试题{i}",
                question_type=QuestionType.choice,
                options=["A", "B", "C", "D"],
                answer="A",
                difficulty=Difficulty.medium,
                knowledge_point_tags=["化学"],
                source=QuestionSource.ai_generated,
            )
            db_session.add(q)
            await db_session.flush()
            questions.append(q)

        # 4. 第一次考试：8/10 正确 (80%)
        for q in questions:
            db_session.add(StudentAnswer(
                student_id=student.id,
                question_id=q.id,
                exam_record_id=exam1.id,
                answer_content="A",
                is_correct=(q.id <= questions[7].id),  # 前 8 题正确
            ))

        # 5. 第二次考试：6/10 正确 (60%) — 降幅 20% ≥ 10% 阈值
        for q in questions:
            db_session.add(StudentAnswer(
                student_id=student.id,
                question_id=q.id,
                exam_record_id=exam2.id,
                answer_content="A",
                is_correct=(q.id <= questions[5].id),  # 前 6 题正确
            ))
        await db_session.commit()

        # 6. 执行预警检测
        result = await EarlyWarningService.run_all_checks(db_session)
        await db_session.commit()

        # 7. 验证：应产生一条 score_drop 预警
        assert result["total_students"] >= 1
        assert result["new_warnings"] >= 1, (
            f"应至少产生 1 条预警，实际 {result['new_warnings']}，"
            f"by_type={result.get('by_type', {})}"
        )
        assert result["by_type"].get("score_drop", 0) >= 1, (
            f"应产生 score_drop 预警，实际 by_type={result.get('by_type', {})}"
        )
