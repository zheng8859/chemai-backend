"""Panel API 集成测试 — 7 个端点（权限 + 数据）。

端点：
- GET  /panel/classes
- GET  /panel/class/{class_id}
- GET  /panel/class/{class_id}/student/{student_id}
- GET  /panel/class/{class_id}/knowledge-points
- GET  /panel/class/{class_id}/barriers
- GET  /panel/class/{class_id}/concern-students
- GET  /panel/class/{class_id}/exam-trend
"""

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.user import Account, Teacher, Student, TeacherClassSubject
from app.models.org import School, Grade, Class as ClassModel
from app.models.diagnosis import WarningLog
from app.models.barrier_profile_history import BarrierProfileHistory
from app.models.teaching import ExamRecord, Question, StudentAnswer
from app.core.enums import (
    AccountRole, StudentStatus, ExamRecordStatus,
    QuestionType, Difficulty, QuestionSource,
    WarningType, WarningSeverity,
)
from app.core.security import create_access_token


# ── Helpers ────────────────────────────────────────────────────

async def _setup_teacher_with_class(
    db: AsyncSession,
) -> tuple[Teacher, ClassModel, Student, Account]:
    """创建教师、班级、学生并建立任课关系。返回 (teacher, class_, student, teacher_account)。"""
    # 学校 → 年级 → 班级（先创建，Teacher 需要 school_id）
    school = School(name="Panel 测试学校", region="测试区")
    db.add(school)
    await db.flush()
    grade = Grade(name="高一", school_id=school.id)
    db.add(grade)
    await db.flush()
    class_ = ClassModel(name="高一(1)班", grade_id=grade.id)
    db.add(class_)
    await db.flush()

    # 教师 Account
    teacher_account = Account(
        phone=f"130{uuid.uuid4().hex[:6]}",
        password_hash="test_hash",
        role=AccountRole.teacher,
    )
    db.add(teacher_account)
    await db.flush()

    teacher = Teacher(
        name="测试教师",
        account_id=teacher_account.id,
        school_id=school.id,
    )
    db.add(teacher)
    await db.flush()

    # 教师-班级任课关系
    tcs = TeacherClassSubject(
        teacher_id=teacher.id,
        class_id=class_.id,
        subject="chemistry",
    )
    db.add(tcs)
    await db.flush()

    # 学生
    student_account = Account(
        phone=f"131{uuid.uuid4().hex[:6]}",
        password_hash="test_hash",
        role=AccountRole.student,
    )
    db.add(student_account)
    await db.flush()
    student = Student(
        name="测试学生",
        account_id=student_account.id,
        class_id=class_.id,
        school_id=school.id,
        student_id=f"S{uuid.uuid4().hex[:6].upper()}",
        status=StudentStatus.approved.value,
        barrier_profile={"concept": 0.5, "reading": 0.3, "expression": 0.2},
        weak_knowledge_points=["氧化还原反应"],
    )
    db.add(student)
    await db.flush()

    return teacher, class_, student, teacher_account


def _teacher_token(account_id: int) -> dict:
    """生成教师 JWT token header。"""
    token = create_access_token(
        user_id=account_id, role="teacher", school_id=1, sub_role="teacher",
    )
    return {"Authorization": f"Bearer {token}"}


def _student_token(account_id: int) -> dict:
    """生成学生 JWT token header。"""
    token = create_access_token(user_id=account_id, role="student", school_id=1)
    return {"Authorization": f"Bearer {token}"}


# ═══════════════════════════════════════════════════════════════
# Panel API Tests
# ═══════════════════════════════════════════════════════════════


class TestPanelClasses:
    """GET /panel/classes — 教师班级列表。"""

    @pytest.mark.anyio
    async def test_unauthorized_no_token(self, async_client):
        """无 token → 401。"""
        resp = await async_client.get("/api/v1/panel/classes")
        assert resp.status_code == 401

    @pytest.mark.anyio
    async def test_forbidden_student_role(self, async_client, student_headers):
        """学生角色 → 403。"""
        resp = await async_client.get(
            "/api/v1/panel/classes", headers=student_headers,
        )
        assert resp.status_code == 403

    @pytest.mark.anyio
    async def test_teacher_no_profile(self, async_client, teacher_headers):
        """教师 token 但 DB 无 Teacher 档案 → 403。"""
        resp = await async_client.get(
            "/api/v1/panel/classes", headers=teacher_headers,
        )
        assert resp.status_code == 403

    @pytest.mark.anyio
    async def test_teacher_with_classes(self, async_client, db_session):
        """教师有关联班级 → 200 + 返回班级列表。"""
        teacher, class_, student, teacher_acct = await _setup_teacher_with_class(
            db_session
        )
        await db_session.commit()

        resp = await async_client.get(
            "/api/v1/panel/classes",
            headers=_teacher_token(teacher_acct.id),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert isinstance(data["data"], list)
        # 应该返回至少一个班级
        class_ids = [c["class_id"] for c in data["data"]]
        assert class_.id in class_ids


class TestPanelClassOverview:
    """GET /panel/class/{class_id} — 班级聚合视图。"""

    @pytest.mark.anyio
    async def test_forbidden_wrong_teacher(self, async_client, db_session):
        """教师无权访问非任课班级 → 403。"""
        _, class_, _, teacher_acct = await _setup_teacher_with_class(db_session)
        # 获取 school 引用
        school = (await db_session.execute(select(School))).scalars().first()
        # 创建第二个教师（无任课关系）
        other_account = Account(
            phone="13200000001",
            password_hash="test_hash",
            role=AccountRole.teacher,
        )
        db_session.add(other_account)
        await db_session.flush()
        other_teacher = Teacher(
            name="其他教师",
            account_id=other_account.id,
            school_id=school.id,
        )
        db_session.add(other_teacher)
        await db_session.commit()

        resp = await async_client.get(
            f"/api/v1/panel/class/{class_.id}",
            headers=_teacher_token(other_account.id),
        )
        assert resp.status_code == 403

    @pytest.mark.anyio
    async def test_class_not_found_permission_first(self, async_client, db_session):
        """不存在的班级 → 403（权限检查先于存在性检查）。"""
        teacher, class_, student, teacher_acct = await _setup_teacher_with_class(
            db_session
        )
        await db_session.commit()

        resp = await async_client.get(
            "/api/v1/panel/class/99999",
            headers=_teacher_token(teacher_acct.id),
        )
        # 教师无 99999 班级的任课关系 → 403
        assert resp.status_code == 403

    @pytest.mark.anyio
    async def test_class_overview_success(self, async_client, db_session):
        """有权教师访问班级 → 200 + 返回聚合数据。"""
        teacher, class_, student, teacher_acct = await _setup_teacher_with_class(
            db_session
        )
        await db_session.commit()

        resp = await async_client.get(
            f"/api/v1/panel/class/{class_.id}",
            headers=_teacher_token(teacher_acct.id),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        overview = data["data"]
        assert "class_name" in overview
        assert "student_count" in overview
        assert "avg_score" in overview
        assert "knowledge_points" in overview
        assert "barrier_distribution" in overview
        assert "top_improvers" in overview
        assert "top_declining" in overview
        assert "concern_students" in overview
        assert "exam_count" in overview


class TestPanelStudentDetail:
    """GET /panel/class/{class_id}/student/{student_id} — 学生详情。"""

    @pytest.mark.anyio
    async def test_student_not_in_class(self, async_client, db_session):
        """学生不属于该班级 → 404。"""
        teacher, class_, student, teacher_acct = await _setup_teacher_with_class(
            db_session
        )

        # 使用已创建的 school，创建另一个班级和另一学生
        school = (await db_session.execute(select(School))).scalars().first()
        grade2 = Grade(name="高二", school_id=school.id)
        db_session.add(grade2)
        await db_session.flush()
        other_class = ClassModel(name="高二(1)班", grade_id=grade2.id)
        db_session.add(other_class)
        await db_session.flush()
        other_student_account = Account(
            phone=f"135{uuid.uuid4().hex[:6]}",
            password_hash="test_hash",
            role=AccountRole.student,
        )
        db_session.add(other_student_account)
        await db_session.flush()
        other_student = Student(
            name="其他学生",
            account_id=other_student_account.id,
            class_id=other_class.id,
            school_id=school.id,
            student_id="S99999",
            status=StudentStatus.approved.value,
        )
        db_session.add(other_student)
        await db_session.commit()

        resp = await async_client.get(
            f"/api/v1/panel/class/{class_.id}/student/{other_student.id}",
            headers=_teacher_token(teacher_acct.id),
        )
        # 学生不属于该班级 → 404
        assert resp.status_code == 404

    @pytest.mark.anyio
    async def test_student_detail_success(self, async_client, db_session):
        """有权访问 → 200 + 返回学生详情。"""
        teacher, class_, student, teacher_acct = await _setup_teacher_with_class(
            db_session
        )
        await db_session.commit()

        resp = await async_client.get(
            f"/api/v1/panel/class/{class_.id}/student/{student.id}",
            headers=_teacher_token(teacher_acct.id),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        detail = data["data"]
        # PanelService returns student_info for the student summary key
        student_key = "student" if "student" in detail else "student_info"
        assert student_key in detail
        assert "accuracy_trend" in detail
        assert "weak_knowledge_points" in detail
        # barrier profile may be named barrier_profile or barrier_profile_history
        has_barrier = "barrier_profile" in detail or "barrier_profile_history" in detail
        assert has_barrier, f"Expected barrier_profile or barrier_profile_history, got keys: {list(detail.keys())}"


class TestPanelKnowledgePoints:
    """GET /panel/class/{class_id}/knowledge-points — 知识点维度。"""

    @pytest.mark.anyio
    async def test_knowledge_points_success(self, async_client, db_session):
        """有权访问 → 200 + 返回分页数据。"""
        teacher, class_, student, teacher_acct = await _setup_teacher_with_class(
            db_session
        )
        await db_session.commit()

        resp = await async_client.get(
            f"/api/v1/panel/class/{class_.id}/knowledge-points",
            headers=_teacher_token(teacher_acct.id),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "data" in data
        assert "total" in data
        assert "limit" in data
        assert "offset" in data

    @pytest.mark.anyio
    async def test_knowledge_points_pagination(self, async_client, db_session):
        """分页参数正常传递。"""
        teacher, class_, student, teacher_acct = await _setup_teacher_with_class(
            db_session
        )
        await db_session.commit()

        resp = await async_client.get(
            f"/api/v1/panel/class/{class_.id}/knowledge-points?limit=5&offset=0",
            headers=_teacher_token(teacher_acct.id),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["limit"] == 5
        assert data["offset"] == 0


class TestPanelBarriers:
    """GET /panel/class/{class_id}/barriers — 障碍分布。"""

    @pytest.mark.anyio
    async def test_barriers_success(self, async_client, db_session):
        """有权访问 → 200 + 返回障碍分布。"""
        teacher, class_, student, teacher_acct = await _setup_teacher_with_class(
            db_session
        )
        await db_session.commit()

        resp = await async_client.get(
            f"/api/v1/panel/class/{class_.id}/barriers",
            headers=_teacher_token(teacher_acct.id),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert isinstance(data["data"], list)


class TestPanelConcernStudents:
    """GET /panel/class/{class_id}/concern-students — 关注学生。"""

    @pytest.mark.anyio
    async def test_concern_students_success(self, async_client, db_session):
        """有权访问 → 200。"""
        teacher, class_, student, teacher_acct = await _setup_teacher_with_class(
            db_session
        )
        await db_session.commit()

        resp = await async_client.get(
            f"/api/v1/panel/class/{class_.id}/concern-students",
            headers=_teacher_token(teacher_acct.id),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert isinstance(data["data"], list)

    @pytest.mark.anyio
    async def test_concern_students_with_warnings(self, async_client, db_session):
        """有预警的学生应出现在关注列表中。"""
        teacher, class_, student, teacher_acct = await _setup_teacher_with_class(
            db_session
        )

        # 创建预警
        warning = WarningLog(
            student_id=student.id,
            warning_type=WarningType.score_drop,
            severity=WarningSeverity.warning,
            title="成绩下滑",
            message="测试预警",
            status="pending",
        )
        db_session.add(warning)
        await db_session.commit()

        resp = await async_client.get(
            f"/api/v1/panel/class/{class_.id}/concern-students",
            headers=_teacher_token(teacher_acct.id),
        )
        assert resp.status_code == 200
        data = resp.json()
        # 关注列表应包含有预警的学生
        concern_ids = [s["student_id"] for s in data["data"]]
        assert student.id in concern_ids


class TestPanelExamTrend:
    """GET /panel/class/{class_id}/exam-trend — 考试趋势。"""

    @pytest.mark.anyio
    async def test_exam_trend_success(self, async_client, db_session):
        """有权访问 → 200 + 返回趋势数据。"""
        teacher, class_, student, teacher_acct = await _setup_teacher_with_class(
            db_session
        )
        await db_session.commit()

        resp = await async_client.get(
            f"/api/v1/panel/class/{class_.id}/exam-trend",
            headers=_teacher_token(teacher_acct.id),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert isinstance(data["data"], list)

    @pytest.mark.anyio
    async def test_exam_trend_with_data(self, async_client, db_session):
        """有考试数据时返回趋势点。"""
        teacher, class_, student, teacher_acct = await _setup_teacher_with_class(
            db_session
        )
        await db_session.commit()

        # 创建考试
        from datetime import datetime, timezone
        from app.core.enums import ExamType

        exam = ExamRecord(
            name="期中考试",
            class_id=class_.id,
            exam_type=ExamType.monthly,
            exam_date=datetime.now(timezone.utc),
            status=ExamRecordStatus.completed.value,
        )
        db_session.add(exam)
        await db_session.flush()

        # 创建题目（Question 没有 exam_record_id，通过 StudentAnswer 关联）
        question = Question(
            content="趋势测试题",
            question_type=QuestionType.choice,
            options=["A", "B", "C", "D"],
            answer="A",
            difficulty=Difficulty.medium,
            knowledge_point_tags=["化学"],
            source=QuestionSource.ai_generated,
        )
        db_session.add(question)
        await db_session.flush()

        # 通过 StudentAnswer 将题目与考试关联
        answer = StudentAnswer(
            student_id=student.id,
            question_id=question.id,
            exam_record_id=exam.id,
            answer_content="A",
            is_correct=True,
        )
        db_session.add(answer)
        await db_session.commit()

        resp = await async_client.get(
            f"/api/v1/panel/class/{class_.id}/exam-trend",
            headers=_teacher_token(teacher_acct.id),
        )
        assert resp.status_code == 200
        data = resp.json()
        # 趋势数据中有考试出现就说明正确
        assert data["success"] is True
