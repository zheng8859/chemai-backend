"""API 集成测试 — 自适应练习 + 间隔复习 + 错题训练端点。

测试所有 Phase 4 API 端点：
- /api/v1/practice/*
- /api/v1/review/*

使用 conftest.py fixtures (async_client, teacher_headers, student_headers, db_session, school, grade, class_)。
"""

import pytest
import uuid
from datetime import datetime, timezone, timedelta

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.user import Student, Account
from app.models.org import School, Grade, Class as ClassModel
from app.models.teaching import Question, PracticeSession, PracticeSessionQuestion, StudentAnswer
from app.models.diagnosis import ReviewTask, ReviewHistory
from app.core.enums import (
    AccountRole, StudentStatus, PracticeSessionStatus, ReviewTaskStatus,
    QuestionType, Difficulty, QuestionSource,
)


# ═══════════════════════════════════════════════════════════════
# Helper factories (direct DB, not via API)
# ═══════════════════════════════════════════════════════════════

async def _create_account(db: AsyncSession, role=AccountRole.student) -> Account:
    account = Account(
        phone=f"1380013{uuid.uuid4().hex[:4]}",
        password_hash="test_hash",
        role=role,
    )
    db.add(account)
    await db.flush()
    return account


async def _create_student(db: AsyncSession, **kwargs) -> Student:
    """通过 DB 直接创建学生（绕过 API，用于准备测试数据）。"""
    account = await _create_account(db)
    school = School(name="API测试学校", region="测试区")
    db.add(school)
    await db.flush()
    grade = Grade(name="高一", school_id=school.id)
    db.add(grade)
    await db.flush()
    class_ = ClassModel(name="API测试班", grade_id=grade.id)
    db.add(class_)
    await db.flush()

    defaults = dict(
        name="API测试学生",
        account_id=account.id,
        class_id=class_.id,
        school_id=school.id,
        student_id=f"S{uuid.uuid4().hex[:6].upper()}",
        status=StudentStatus.approved.value,
        barrier_profile={"concept": 0.5, "reading": 0.3, "expression": 0.2},
        weak_knowledge_points=["氧化还原反应", "离子反应"],
    )
    defaults.update(kwargs)
    student = Student(**defaults)
    db.add(student)
    await db.flush()
    return student


async def _create_question(
    db: AsyncSession,
    content: str = "API测试题目",
    answer: str = "A",
    difficulty: str = "medium",
    knowledge_point_tags: list | None = None,
    **kwargs,
) -> Question:
    defaults = dict(
        content=content,
        question_type=QuestionType.choice,
        options=["A. 选项A", "B. 选项B", "C. 选项C", "D. 选项D"],
        answer=answer,
        difficulty=Difficulty(difficulty),
        knowledge_point_tags=knowledge_point_tags or ["化学"],
        source=QuestionSource.ai_generated,
    )
    defaults.update(kwargs)
    q = Question(**defaults)
    db.add(q)
    await db.flush()
    return q


# ═══════════════════════════════════════════════════════════════
# Practice API tests
# ═══════════════════════════════════════════════════════════════


class TestPracticeGetStudentTasks:
    """4.2 GET /api/v1/practice/student/{uid}/tasks"""

    @pytest.mark.anyio
    async def test_get_tasks_no_sessions(self, async_client, student_headers, db_session):
        """无练习记录的学生 → 返回空列表。"""
        student = await _create_student(db_session)
        await db_session.commit()

        resp = await async_client.get(
            f"/api/v1/practice/student/{student.id}/tasks",
            headers=student_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "pending" in data["data"]
        assert "completed" in data["data"]
        assert data["data"]["pending"] == []
        assert data["data"]["completed"] == []

    @pytest.mark.anyio
    async def test_get_tasks_nonexistent_student(self, async_client, student_headers):
        """不存在的学生 → 200（空列表，服务不抛异常）。"""
        resp = await async_client.get(
            "/api/v1/practice/student/99999/tasks",
            headers=student_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["data"]["pending"] == []
        assert data["data"]["completed"] == []


class TestPracticeSubmit:
    """4.3 POST /api/v1/practice/submit"""

    @pytest.mark.anyio
    async def test_submit_missing_practice_id(self, async_client, student_headers):
        """缺少 practice_id → 422（Pydantic 校验）。"""
        resp = await async_client.post(
            "/api/v1/practice/submit",
            json={"answers": []},
            headers=student_headers,
        )
        assert resp.status_code == 422

    @pytest.mark.anyio
    async def test_submit_nonexistent_practice(self, async_client, student_headers):
        """不存在的 practice_id → 404。"""
        resp = await async_client.post(
            "/api/v1/practice/submit",
            json={"practice_id": "PR-NONEXIST", "answers": []},
            headers=student_headers,
        )
        assert resp.status_code == 404

    @pytest.mark.anyio
    async def test_submit_duplicate(self, async_client, student_headers, db_session):
        """重复提交同一次练习 → 409。"""
        student = await _create_student(db_session)
        q = await _create_question(db_session)
        await db_session.commit()

        # 创建练习
        session = PracticeSession(
            practice_id="PR-DUP-TEST",
            student_id=student.id,
            title="重复提交测试",
            barrier_type="concept",
            status=PracticeSessionStatus.in_progress.value,
            question_count=1,
            knowledge_point_tags=["氧化还原反应"],
        )
        db_session.add(session)
        await db_session.flush()
        psq = PracticeSessionQuestion(practice_session_id=session.id, question_id=q.id, sort_order=1)
        db_session.add(psq)
        await db_session.commit()

        # 第一次提交
        resp1 = await async_client.post(
            "/api/v1/practice/submit",
            json={"practice_id": "PR-DUP-TEST", "answers": [{"question_id": q.id, "answer": "A"}]},
            headers=student_headers,
        )
        assert resp1.status_code == 200

        # 第二次提交（重复）
        resp2 = await async_client.post(
            "/api/v1/practice/submit",
            json={"practice_id": "PR-DUP-TEST", "answers": [{"question_id": q.id, "answer": "A"}]},
            headers=student_headers,
        )
        assert resp2.status_code == 409
        assert "DUPLICATE_SUBMIT" in resp2.json()["detail"]["error_code"]

    @pytest.mark.anyio
    async def test_submit_success(self, async_client, student_headers, db_session):
        """正常提交练习 → 返回成绩。"""
        student = await _create_student(db_session)
        q = await _create_question(db_session, answer="B")
        await db_session.commit()

        session = PracticeSession(
            practice_id="PR-SUBMIT-OK",
            student_id=student.id,
            title="正常提交测试",
            barrier_type="concept",
            status=PracticeSessionStatus.in_progress.value,
            question_count=1,
            knowledge_point_tags=["化学"],
        )
        db_session.add(session)
        await db_session.flush()
        psq = PracticeSessionQuestion(practice_session_id=session.id, question_id=q.id, sort_order=1)
        db_session.add(psq)
        await db_session.commit()

        resp = await async_client.post(
            "/api/v1/practice/submit",
            json={"practice_id": "PR-SUBMIT-OK", "answers": [{"question_id": q.id, "answer": "B"}]},
            headers=student_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["data"]["score"] == 1
        assert data["data"]["total"] == 1
        assert data["data"]["accuracy"] == 1.0
        assert len(data["data"]["results"]) == 1
        assert data["data"]["results"][0]["is_correct"] is True


class TestPracticeEffect:
    """4.4 GET /api/v1/practice/effect/{student_id}"""

    @pytest.mark.anyio
    async def test_get_effect_no_sessions(self, async_client, student_headers, db_session):
        """无练习记录 → 返回 null 字段。"""
        student = await _create_student(db_session)
        await db_session.commit()

        resp = await async_client.get(
            f"/api/v1/practice/effect/{student.id}",
            headers=student_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["data"]["latest_accuracy"] is None
        assert data["data"]["improvement_rate"] is None

    @pytest.mark.anyio
    async def test_get_effect_nonexistent_student(self, async_client, student_headers):
        """不存在的学生 → 200（空结果）。"""
        resp = await async_client.get(
            "/api/v1/practice/effect/99999",
            headers=student_headers,
        )
        assert resp.status_code == 200


# ═══════════════════════════════════════════════════════════════
# Review API tests
# ═══════════════════════════════════════════════════════════════


class TestReviewGetDue:
    """4.6 GET /api/v1/review/student/{id}/due"""

    @pytest.mark.anyio
    async def test_get_due_empty(self, async_client, student_headers, db_session):
        """无待复习任务 → 返回空列表。"""
        student = await _create_student(db_session)
        await db_session.commit()

        resp = await async_client.get(
            f"/api/v1/review/student/{student.id}/due",
            headers=student_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["data"] == []
        assert data["total"] == 0

    @pytest.mark.anyio
    async def test_get_due_nonexistent_student(self, async_client, student_headers):
        """不存在的学生 → 200 空列表。"""
        resp = await async_client.get(
            "/api/v1/review/student/99999/due",
            headers=student_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["data"] == []

    @pytest.mark.anyio
    async def test_get_due_pagination(self, async_client, student_headers, db_session):
        """分页参数正确传递。"""
        student = await _create_student(db_session)
        await db_session.commit()

        resp = await async_client.get(
            f"/api/v1/review/student/{student.id}/due?limit=5&offset=0",
            headers=student_headers,
        )
        assert resp.status_code == 200


class TestReviewSubmit:
    """4.7 POST /api/v1/review/submit"""

    @pytest.mark.anyio
    async def test_submit_missing_fields(self, async_client, student_headers):
        """缺少必填字段 → 422（Pydantic 校验）。"""
        resp = await async_client.post(
            "/api/v1/review/submit",
            json={},
            headers=student_headers,
        )
        assert resp.status_code == 422

    @pytest.mark.anyio
    async def test_submit_nonexistent_task(self, async_client, student_headers):
        """不存在的 task → 404。"""
        resp = await async_client.post(
            "/api/v1/review/submit",
            json={"review_task_id": 99999, "is_correct": True},
            headers=student_headers,
        )
        assert resp.status_code == 404


class TestWrongList:
    """4.8 GET /api/v1/review/wrong/list"""

    @pytest.mark.anyio
    async def test_get_wrong_list_empty(self, async_client, student_headers, db_session):
        """无错题 → 返回空列表。"""
        student = await _create_student(db_session)
        await db_session.commit()

        resp = await async_client.get(
            f"/api/v1/review/wrong/list?student_id={student.id}",
            headers=student_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["data"] == []
        assert data["total"] == 0

    @pytest.mark.anyio
    async def test_get_wrong_list_missing_student_id(self, async_client, student_headers):
        """缺少 student_id → 422。"""
        resp = await async_client.get(
            "/api/v1/review/wrong/list",
            headers=student_headers,
        )
        assert resp.status_code == 422


class TestWrongMarkMastered:
    """4.9 POST /api/v1/review/wrong/{question_id}/master"""

    @pytest.mark.anyio
    async def test_mark_mastered_missing_student_id(self, async_client, student_headers):
        """缺少 student_id → 422（Pydantic 校验）。"""
        resp = await async_client.post(
            "/api/v1/review/wrong/1/master",
            json={},
            headers=student_headers,
        )
        assert resp.status_code == 422

    @pytest.mark.anyio
    async def test_mark_mastered_success(self, async_client, student_headers, db_session):
        """正常标记已掌握 → 200。"""
        student = await _create_student(db_session)
        q = await _create_question(db_session)
        await db_session.commit()

        resp = await async_client.post(
            f"/api/v1/review/wrong/{q.id}/master",
            json={"student_id": student.id},
            headers=student_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True


class TestWrongVariantGenerate:
    """4.10 POST /api/v1/review/wrong-topic/variant/generate"""

    @pytest.mark.anyio
    async def test_generate_variants_missing_question_id(self, async_client, student_headers):
        """缺少 question_id → 422（Pydantic 校验）。"""
        resp = await async_client.post(
            "/api/v1/review/wrong-topic/variant/generate",
            json={},
            headers=student_headers,
        )
        assert resp.status_code == 422

    @pytest.mark.anyio
    async def test_generate_variants_nonexistent_question(self, async_client, student_headers):
        """不存在的题目 → 404。"""
        resp = await async_client.post(
            "/api/v1/review/wrong-topic/variant/generate",
            json={"question_id": 99999, "count": 3},
            headers=student_headers,
        )
        assert resp.status_code == 404


class TestTrainingCreate:
    """4.11 POST /api/v1/review/wrong-topic/training/create"""

    @pytest.mark.anyio
    async def test_create_training_missing_student_id(self, async_client, student_headers):
        """缺少 student_id → 422（Pydantic 校验）。"""
        resp = await async_client.post(
            "/api/v1/review/wrong-topic/training/create",
            json={},
            headers=student_headers,
        )
        assert resp.status_code == 422

    @pytest.mark.anyio
    async def test_create_training_success(self, async_client, student_headers, db_session):
        """正常创建训练 → 200。"""
        student = await _create_student(db_session)
        q1 = await _create_question(db_session, content="题1")
        q2 = await _create_question(db_session, content="题2")
        await db_session.commit()

        resp = await async_client.post(
            "/api/v1/review/wrong-topic/training/create",
            json={"student_id": student.id, "question_ids": [q1.id, q2.id]},
            headers=student_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "session_id" in data["data"]


class TestTrainingSubmit:
    """4.12 POST /api/v1/review/wrong-topic/training/submit"""

    @pytest.mark.anyio
    async def test_submit_training_missing_fields(self, async_client, student_headers):
        """缺少必填字段 → 422（Pydantic 校验）。"""
        resp = await async_client.post(
            "/api/v1/review/wrong-topic/training/submit",
            json={},
            headers=student_headers,
        )
        assert resp.status_code == 422

    @pytest.mark.anyio
    async def test_submit_training_success(self, async_client, student_headers, db_session):
        """正常提交训练 → 200。"""
        student = await _create_student(db_session)
        q1 = await _create_question(db_session, content="训练题1", answer="C")
        await db_session.commit()

        # 先创建训练
        create_resp = await async_client.post(
            "/api/v1/review/wrong-topic/training/create",
            json={"student_id": student.id, "question_ids": [q1.id]},
            headers=student_headers,
        )
        session_id = create_resp.json()["data"]["session_id"]

        # 提交训练
        resp = await async_client.post(
            "/api/v1/review/wrong-topic/training/submit",
            json={
                "session_id": session_id,
                "student_id": student.id,
                "answers": [{"question_id": q1.id, "answer": "C"}],
            },
            headers=student_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "score" in data["data"]
        assert "accuracy" in data["data"]


class TestWrongKnowledgePoints:
    """4.13 GET /api/v1/review/wrong-topic/knowledge-points"""

    @pytest.mark.anyio
    async def test_list_kps_empty(self, async_client, student_headers, db_session):
        """无错题 → 返回空知识点列表。"""
        student = await _create_student(db_session)
        await db_session.commit()

        resp = await async_client.get(
            f"/api/v1/review/wrong-topic/knowledge-points?student_id={student.id}",
            headers=student_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["data"] == []
        assert data["total"] == 0

    @pytest.mark.anyio
    async def test_list_kps_missing_student_id(self, async_client, student_headers):
        """缺少 student_id → 422。"""
        resp = await async_client.get(
            "/api/v1/review/wrong-topic/knowledge-points",
            headers=student_headers,
        )
        assert resp.status_code == 422


# ═══════════════════════════════════════════════════════════════
# Auth: 验证所有端点需要认证
# ═══════════════════════════════════════════════════════════════


class TestPracticeAuth:
    """练习端点认证检查。"""

    @pytest.mark.anyio
    async def test_tasks_requires_auth(self, async_client):
        """无 token → 401。"""
        resp = await async_client.get("/api/v1/practice/student/1/tasks")
        assert resp.status_code == 401

    @pytest.mark.anyio
    async def test_submit_requires_auth(self, async_client):
        resp = await async_client.post("/api/v1/practice/submit", json={})
        assert resp.status_code == 401

    @pytest.mark.anyio
    async def test_effect_requires_auth(self, async_client):
        resp = await async_client.get("/api/v1/practice/effect/1")
        assert resp.status_code == 401


class TestReviewAuth:
    """复习端点认证检查。"""

    @pytest.mark.anyio
    async def test_due_requires_auth(self, async_client):
        resp = await async_client.get("/api/v1/review/student/1/due")
        assert resp.status_code == 401

    @pytest.mark.anyio
    async def test_submit_requires_auth(self, async_client):
        resp = await async_client.post("/api/v1/review/submit", json={})
        assert resp.status_code == 401

    @pytest.mark.anyio
    async def test_wrong_list_requires_auth(self, async_client):
        resp = await async_client.get("/api/v1/review/wrong/list?student_id=1")
        assert resp.status_code == 401
