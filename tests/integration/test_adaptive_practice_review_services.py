"""集成测试 — 自适应练习 + 间隔复习 + 每日练习服务。

使用 test DB (事务回滚隔离)，测试服务方法全路径。
"""

import pytest
from datetime import datetime, timezone, timedelta

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.user import Student
from app.models.teaching import (
    Question,
    PracticeSession,
    StudentAnswer,
)
from app.models.diagnosis import ReviewTask, ReviewHistory
from app.core.enums import (
    PracticeSessionStatus,
    ReviewTaskStatus,
    QuestionType,
    Difficulty,
    StudentStatus,
)

from app.services.adaptive_practice_service import (
    AdaptivePracticeService,
    AdaptivePracticeError,
)
from app.services.review_service import ReviewService, ReviewError
from app.services.daily_practice_service import DailyPracticeService


# ═══════════════════════════════════════════════════════════════
# AdaptivePracticeService tests
# ═══════════════════════════════════════════════════════════════


class TestAdaptivePracticeCreate:
    """create_practice — 7 步流水线集成测试。"""

    @pytest.mark.anyio
    async def test_create_practice_for_new_student(self, db_session, make_student, make_question):
        """新学生（无过往作答）：ZPD=medium，自动推导薄弱知识点。"""
        student = await make_student()

        result = await AdaptivePracticeService.create_practice(
            db_session, student.id, question_count=5
        )

        assert result["zpd_difficulty"] == "medium"  # 冷启动
        assert result["dominant_barrier"] == "concept"
        assert "practice_id" in result
        assert result["practice_id"].startswith("PR-")

        # 验证 PracticeSession 已创建
        session = (await db_session.execute(
            select(PracticeSession).where(
                PracticeSession.practice_id == result["practice_id"]
            )
        )).scalar_one_or_none()
        assert session is not None
        assert session.student_id == student.id
        assert session.status == PracticeSessionStatus.in_progress.value

    @pytest.mark.anyio
    async def test_create_practice_with_kp_override(self, db_session, make_student, make_question):
        """教师指定知识点补足：薄弱知识点优先，教师指定补足到 Top 3（28 号 §4 Step 2）。"""
        student = await make_student()

        result = await AdaptivePracticeService.create_practice(
            db_session, student.id, question_count=5,
            kp_override=["物质的量", "化学平衡"],
        )

        # 薄弱知识点（氧化还原反应、离子反应）优先，教师指定「物质的量」补足到 3 个
        assert result["target_kps"] == ["氧化还原反应", "离子反应", "物质的量"]

    @pytest.mark.anyio
    async def test_create_practice_nonexistent_student(self, db_session):
        """不存在的学生抛出异常。"""
        with pytest.raises(AdaptivePracticeError) as exc:
            await AdaptivePracticeService.create_practice(
                db_session, student_id=99999, question_count=5
            )
        assert "学生不存在" in str(exc.value)

    @pytest.mark.anyio
    async def test_create_practice_zpd_based_on_history(self, db_session, make_student, make_question):
        """有历史的学生的 ZPD 基于过往作答。"""
        student = await make_student()
        q = await make_question()

        # 创建 30 条全错历史 → ZPD = easy (< 40%)
        for _ in range(30):
            sa = StudentAnswer(
                student_id=student.id,
                question_id=q.id,
                answer_content="错误答案",
                is_correct=False,
            )
            db_session.add(sa)
        await db_session.flush()

        result = await AdaptivePracticeService.create_practice(
            db_session, student.id, question_count=5
        )

        assert result["zpd_difficulty"] == "easy"


class TestAdaptivePracticeSubmit:
    """submit_practice — 提交答案并计算正确率。"""

    @pytest.mark.anyio
    async def test_submit_all_correct(self, db_session, make_student, make_question):
        """全部答对 → score = total, accuracy = 1.0。"""
        student = await make_student()
        q = await make_question( content="氧化铜与盐酸反应？", answer="B")

        result = await AdaptivePracticeService.create_practice(
            db_session, student.id, question_count=1
        )

        # 通过 ORM 更新问题列表（create_practice 如无匹配题则 questions 为空）
        # 手动关联题目到 session
        session = (await db_session.execute(
            select(PracticeSession).where(
                PracticeSession.practice_id == result["practice_id"]
            )
        )).scalar_one()

        from app.models.teaching import PracticeSessionQuestion
        psq = PracticeSessionQuestion(
            practice_session_id=session.id,
            question_id=q.id,
            sort_order=1,
        )
        db_session.add(psq)
        await db_session.flush()

        submit_result = await AdaptivePracticeService.submit_practice(
            db_session,
            result["practice_id"],
            [{"question_id": q.id, "answer": "B"}],
        )

        assert submit_result["score"] == 1
        assert submit_result["total"] == 1
        assert submit_result["accuracy"] == 1.0
        assert all(r["is_correct"] for r in submit_result["results"])

        # 验证 StudentAnswer 已创建
        sa = (await db_session.execute(
            select(StudentAnswer).where(
                StudentAnswer.student_id == student.id,
                StudentAnswer.question_id == q.id,
            )
        )).scalar_one_or_none()
        assert sa is not None

    @pytest.mark.anyio
    async def test_submit_duplicate_raises_error(self, db_session, make_student, make_question):
        """重复提交抛出异常。"""
        student = await make_student()
        q = await make_question()

        result = await AdaptivePracticeService.create_practice(
            db_session, student.id, question_count=1
        )

        # 第一次提交
        await AdaptivePracticeService.submit_practice(
            db_session, result["practice_id"], []
        )

        # 第二次提交 → 错误
        with pytest.raises(AdaptivePracticeError) as exc:
            await AdaptivePracticeService.submit_practice(
                db_session, result["practice_id"], []
            )
        assert "重复提交" in str(exc.value)


class TestAdaptivePracticeTasks:
    """get_student_tasks — 获取待完成/已完成任务。"""

    @pytest.mark.anyio
    async def test_returns_empty_for_new_student(self, db_session, make_student, make_question):
        """新学生无任务。"""
        student = await make_student()
        tasks = await AdaptivePracticeService.get_student_tasks(db_session, student.id)
        assert tasks["pending"] == []
        assert tasks["completed"] == []

    @pytest.mark.anyio
    async def test_returns_pending_after_create(self, db_session, make_student, make_question):
        """创建练习后出现在 pending 中。"""
        student = await make_student()
        await AdaptivePracticeService.create_practice(
            db_session, student.id, question_count=5
        )

        tasks = await AdaptivePracticeService.get_student_tasks(db_session, student.id)
        assert len(tasks["pending"]) == 1
        assert len(tasks["completed"]) == 0


class TestAdaptivePracticeEffect:
    """get_practice_effect — 对比最近 2 次练习。"""

    @pytest.mark.anyio
    async def test_less_than_two_sessions_returns_none_improvement(self, db_session, make_student, make_question):
        """少于 2 次练习 → improvement_rate = None。"""
        student = await make_student()
        effect = await AdaptivePracticeService.get_practice_effect(
            db_session, student.id
        )
        assert effect["improvement_rate"] is None

    @pytest.mark.anyio
    async def test_two_sessions_with_improvement(self, db_session, make_student, make_question):
        """2 次练习对比 → 计算进步率（不同题目避免交叉污染）。"""
        student = await make_student()
        q1 = await make_question( content="题A", answer="A")
        q2 = await make_question( content="题B", answer="B")
        q3 = await make_question( content="题C", answer="C")
        q4 = await make_question( content="题D", answer="D")

        from app.models.teaching import PracticeSessionQuestion

        # 第一次练习：2 题对 1 题
        ps1 = PracticeSession(
            practice_id="PR-TEST-001",
            student_id=student.id,
            title="测试练习 1",
            barrier_type="concept",
            status=PracticeSessionStatus.completed.value,
            question_count=2,
        )
        db_session.add(ps1)
        await db_session.flush()
        db_session.add(StudentAnswer(
            student_id=student.id, question_id=q1.id,
            answer_content="A", is_correct=True,
        ))
        db_session.add(StudentAnswer(
            student_id=student.id, question_id=q2.id,
            answer_content="错", is_correct=False,
        ))
        db_session.add(PracticeSessionQuestion(
            practice_session_id=ps1.id, question_id=q1.id, sort_order=1,
        ))
        db_session.add(PracticeSessionQuestion(
            practice_session_id=ps1.id, question_id=q2.id, sort_order=2,
        ))
        await db_session.flush()

        # 第二次练习：2 题全对（使用不同题目）
        ps2 = PracticeSession(
            practice_id="PR-TEST-002",
            student_id=student.id,
            title="测试练习 2",
            barrier_type="concept",
            status=PracticeSessionStatus.completed.value,
            question_count=2,
        )
        db_session.add(ps2)
        await db_session.flush()
        db_session.add(StudentAnswer(
            student_id=student.id, question_id=q3.id,
            answer_content="C", is_correct=True,
        ))
        db_session.add(StudentAnswer(
            student_id=student.id, question_id=q4.id,
            answer_content="D", is_correct=True,
        ))
        db_session.add(PracticeSessionQuestion(
            practice_session_id=ps2.id, question_id=q3.id, sort_order=1,
        ))
        db_session.add(PracticeSessionQuestion(
            practice_session_id=ps2.id, question_id=q4.id, sort_order=2,
        ))
        await db_session.flush()

        effect = await AdaptivePracticeService.get_practice_effect(
            db_session, student.id
        )

        # 至少有一次练习的正确率为 1.0（ps2 全对），一次为 0.5（ps1 半对）
        assert effect["latest_accuracy"] is not None
        assert effect["previous_accuracy"] is not None
        assert effect["improvement_rate"] is not None
        # 验证准确率值在合理范围
        assert 0.0 <= effect["latest_accuracy"] <= 1.0
        assert 0.0 <= effect["previous_accuracy"] <= 1.0
        # 两次练习的准确率中有一个是全对、一个是半对
        accuracies = {effect["latest_accuracy"], effect["previous_accuracy"]}
        assert 1.0 in accuracies
        assert 0.5 in accuracies


# ═══════════════════════════════════════════════════════════════
# ReviewService tests
# ═══════════════════════════════════════════════════════════════


class TestReviewListPending:
    """list_pending_reviews — 列出待复习任务。"""

    @pytest.mark.anyio
    async def test_empty_for_new_student(self, db_session, make_student, make_question):
        """新学生无待复习任务。"""
        student = await make_student()
        tasks, total = await ReviewService.list_pending_reviews(
            db_session, student.id
        )
        assert tasks == []
        assert total == 0

    @pytest.mark.anyio
    async def test_returns_pending_task_with_question(self, db_session, make_student, make_question):
        """待复习任务附带题目内容。"""
        student = await make_student()
        q = await make_question()

        # 创建待复习任务
        task = ReviewTask(
            student_id=student.id,
            question_id=q.id,
            level=0,
            status=ReviewTaskStatus.pending.value,
            consecutive_correct=0,
            consecutive_wrong=0,
            next_review_date=datetime.now(timezone.utc),
        )
        db_session.add(task)
        await db_session.flush()

        tasks, total = await ReviewService.list_pending_reviews(
            db_session, student.id
        )
        assert total == 1
        assert tasks[0]["question"] is not None
        assert tasks[0]["question"]["content"] == "测试题目"


class TestReviewComplete:
    """complete_review — 完成复习并更新级别。"""

    @pytest.mark.anyio
    async def test_complete_review_correct_advances(self, db_session, make_student, make_question):
        """答对 2 次连续触发升级。"""
        student = await make_student()
        q = await make_question()

        task = ReviewTask(
            student_id=student.id,
            question_id=q.id,
            level=1,
            status=ReviewTaskStatus.pending.value,
            consecutive_correct=1,
            consecutive_wrong=0,
            next_review_date=datetime.now(timezone.utc),
        )
        db_session.add(task)
        await db_session.flush()

        r1 = await ReviewService.complete_review(db_session, task.id, is_correct=True)
        assert r1["upgraded"] is True
        assert r1["level"] == 2
        assert r1["consecutive_correct"] == 0

    @pytest.mark.anyio
    async def test_complete_review_wrong_downgrades(self, db_session, make_student, make_question):
        """答错下降级。"""
        student = await make_student()
        q = await make_question()

        task = ReviewTask(
            student_id=student.id,
            question_id=q.id,
            level=2,
            status=ReviewTaskStatus.pending.value,
            consecutive_correct=0,
            consecutive_wrong=0,
            next_review_date=datetime.now(timezone.utc),
        )
        db_session.add(task)
        await db_session.flush()

        r1 = await ReviewService.complete_review(db_session, task.id, is_correct=False)
        assert r1["downgraded"] is True
        assert r1["level"] == 1

    @pytest.mark.anyio
    async def test_complete_review_nonexistent(self, db_session):
        """不存在的任务抛出异常。"""
        with pytest.raises(ReviewError) as exc:
            await ReviewService.complete_review(db_session, 99999, is_correct=True)
        assert "复习任务不存在" in str(exc.value)


class TestReviewSync:
    """sync_review_tasks — 错题同步为 ReviewTask。"""

    @pytest.mark.anyio
    async def test_sync_creates_new_tasks(self, db_session, make_student, make_question):
        """新错题创建 ReviewTask。"""
        student = await make_student()
        q = await make_question()

        result = await ReviewService.sync_review_tasks(
            db_session, student.id, [q.id]
        )

        assert result["created"] == 1
        assert result["pulled_back"] == 0

        # 验证 ReviewTask 已创建
        task = (await db_session.execute(
            select(ReviewTask).where(
                ReviewTask.student_id == student.id,
                ReviewTask.question_id == q.id,
            )
        )).scalar_one()
        assert task.level == 0

    @pytest.mark.anyio
    async def test_sync_skips_existing_pending(self, db_session, make_student, make_question):
        """已存在且未完成的 ReviewTask 跳过。"""
        student = await make_student()
        q = await make_question()

        task = ReviewTask(
            student_id=student.id,
            question_id=q.id,
            level=1,
            status=ReviewTaskStatus.pending.value,
            consecutive_correct=0,
            consecutive_wrong=0,
            next_review_date=datetime.now(timezone.utc),
        )
        db_session.add(task)
        await db_session.flush()

        result = await ReviewService.sync_review_tasks(
            db_session, student.id, [q.id]
        )
        assert result["skipped"] == 1

    @pytest.mark.anyio
    async def test_sync_pulls_back_completed(self, db_session, make_student, make_question):
        """已完成的 ReviewTask 再次答错 → 拉回到 Level 0。"""
        student = await make_student()
        q = await make_question()

        task = ReviewTask(
            student_id=student.id,
            question_id=q.id,
            level=5,
            status=ReviewTaskStatus.completed.value,
            consecutive_correct=0,
            consecutive_wrong=0,
            next_review_date=None,
        )
        db_session.add(task)
        await db_session.flush()

        result = await ReviewService.sync_review_tasks(
            db_session, student.id, [q.id]
        )
        assert result["pulled_back"] == 1

        await db_session.refresh(task)
        assert task.level == 0
        assert task.status == ReviewTaskStatus.pending.value


class TestReviewWrongQuestions:
    """get_wrong_questions — 错题列表。"""

    @pytest.mark.anyio
    async def test_empty_for_new_student(self, db_session, make_student, make_question):
        """无错题 → 空列表。"""
        student = await make_student()
        items, total = await ReviewService.get_wrong_questions(
            db_session, student.id
        )
        assert items == []
        assert total == 0

    @pytest.mark.anyio
    async def test_returns_wrong_questions_sorted_by_count(self, db_session, make_student, make_question):
        """错题按错误次数降序排列。"""
        student = await make_student()
        q = await make_question()

        # 同一题错 3 次
        for _ in range(3):
            db_session.add(StudentAnswer(
                student_id=student.id,
                question_id=q.id,
                answer_content="错",
                is_correct=False,
            ))
        await db_session.flush()

        items, total = await ReviewService.get_wrong_questions(db_session, student.id)
        assert total == 1
        assert items[0]["wrong_count"] == 3


class TestReviewMarkMastered:
    """mark_mastered — 手动标记已掌握。"""

    @pytest.mark.anyio
    async def test_creates_mastered_task(self, db_session, make_student, make_question):
        """创建新 ReviewTask 并直接设为 Level 5。"""
        student = await make_student()
        q = await make_question()

        result = await ReviewService.mark_mastered(
            db_session, student.id, q.id
        )
        assert result["level"] == 5
        assert result["status"] == ReviewTaskStatus.completed.value


class TestReviewTraining:
    """create_training_session + submit_training — 错题强化训练。"""

    @pytest.mark.anyio
    async def test_create_training_returns_session(self, db_session, make_student, make_question):
        """创建训练会话返回题目列表。"""
        student = await make_student()
        q = await make_question()

        result = await ReviewService.create_training_session(
            db_session, student.id, [q.id]
        )
        assert result["session_id"].startswith("TR-")
        assert len(result["questions"]) == 1

    @pytest.mark.anyio
    async def test_submit_training_all_correct(self, db_session, make_student, make_question):
        """全部答对，建议积极。"""
        student = await make_student()
        q = await make_question( answer="B")

        result = await ReviewService.submit_training(
            db_session, "TR-TEST-SESSION", student.id,
            [{"question_id": q.id, "answer": "B"}],
        )

        assert result["accuracy"] == 1.0
        assert "掌握良好" in result["suggestion"]

    @pytest.mark.anyio
    async def test_submit_training_poor_performance(self, db_session, make_student, make_question):
        """全错，建议回归教材。"""
        student = await make_student()
        q = await make_question( answer="C")

        result = await ReviewService.submit_training(
            db_session, "TR-TEST-SESSION", student.id,
            [{"question_id": q.id, "answer": "错误"}],
        )

        assert result["accuracy"] == 0.0
        assert "回归教材" in result["suggestion"]


# ═══════════════════════════════════════════════════════════════
# DailyPracticeService tests
# ═══════════════════════════════════════════════════════════════


class TestDailyPracticeScheduler:
    """run_daily_scheduler — 每日练习分配。"""

    @pytest.mark.anyio
    async def test_no_approved_students(self, db_session):
        """无已审批学生 → 成功但 0 分配。"""
        result = await DailyPracticeService.run_daily_scheduler(db_session)
        assert result["success"] is True
        assert result["assigned_count"] == 0

    @pytest.mark.anyio
    async def test_assigns_practice_to_approved_student(self, db_session, make_student, make_question):
        """已审批学生获得每日练习。"""
        student = await make_student()
        q = await make_question(
            content="测试题",
            knowledge_point_tags=["氧化还原反应"],
        )

        result = await DailyPracticeService.run_daily_scheduler(db_session)
        assert result["success"] is True
        # 注意：如果题库有匹配题目，学生会被分配
        # 取决于 _fetch_from_bank 的查询结果


class TestDailyPracticeNotify:
    """notify_parents_of_overdue_reviews — 逾期通知。"""

    @pytest.mark.anyio
    async def test_no_overdue_tasks(self, db_session):
        """无逾期任务 → 成功但 0 通知。"""
        result = await DailyPracticeService.notify_parents_of_overdue_reviews(
            db_session
        )
        assert result["success"] is True
        assert result["overdue_count"] == 0

    @pytest.mark.anyio
    async def test_overdue_tasks_updated_and_notified(self, db_session, make_student, make_question):
        """逾期任务被标记为 overdue 并通知。"""
        student = await make_student()
        q = await make_question()

        # 创建已逾期任务
        task = ReviewTask(
            student_id=student.id,
            question_id=q.id,
            level=1,
            status=ReviewTaskStatus.pending.value,
            consecutive_correct=0,
            consecutive_wrong=0,
            next_review_date=datetime.now(timezone.utc) - timedelta(days=1),
        )
        db_session.add(task)
        await db_session.flush()

        result = await DailyPracticeService.notify_parents_of_overdue_reviews(
            db_session
        )
        assert result["overdue_count"] >= 1

        await db_session.refresh(task)
        assert task.status == "overdue"
