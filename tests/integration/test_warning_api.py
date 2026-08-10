"""Warning API 集成测试 — 5 个端点 + 状态机 + 权限。

端点：
- GET    /warning/list
- GET    /warning/{id}
- PATCH  /warning/{id}/status  (含状态机校验)
- GET    /warning/stats
- POST   /warning/check
"""

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.user import Account, Teacher, Student, TeacherClassSubject
from app.models.org import School, Grade, Class as ClassModel
from app.models.diagnosis import WarningLog
from app.core.enums import (
    AccountRole, StudentStatus,
    WarningType, WarningSeverity,
)
from app.core.security import create_access_token


# ── Helpers ────────────────────────────────────────────────────

async def _setup_teacher_with_warning(
    db: AsyncSession,
) -> tuple[Teacher, ClassModel, Student, Account, WarningLog]:
    """创建教师 + 班级 + 学生 + 任课关系 + 一条预警。"""
    # 学校 → 年级 → 班级（先创建，Teacher 需要 school_id）
    school = School(name="Warning 测试学校", region="测试区")
    db.add(school)
    await db.flush()
    grade = Grade(name="高一", school_id=school.id)
    db.add(grade)
    await db.flush()
    class_ = ClassModel(name="高一(2)班", grade_id=grade.id)
    db.add(class_)
    await db.flush()

    # 教师 Account
    teacher_account = Account(
        phone=f"140{uuid.uuid4().hex[:6]}",
        password_hash="test_hash",
        role=AccountRole.teacher,
    )
    db.add(teacher_account)
    await db.flush()

    teacher = Teacher(
        name="预警测试教师",
        account_id=teacher_account.id,
        school_id=school.id,
    )
    db.add(teacher)
    await db.flush()

    # 教师-班级任课关系
    tcs = TeacherClassSubject(
        teacher_id=teacher.id, class_id=class_.id, subject="chemistry",
    )
    db.add(tcs)
    await db.flush()

    # 学生
    student_account = Account(
        phone=f"141{uuid.uuid4().hex[:6]}",
        password_hash="test_hash",
        role=AccountRole.student,
    )
    db.add(student_account)
    await db.flush()
    student = Student(
        name="预警测试学生",
        account_id=student_account.id,
        class_id=class_.id,
        school_id=school.id,
        student_id=f"S{uuid.uuid4().hex[:6].upper()}",
        status=StudentStatus.approved.value,
    )
    db.add(student)
    await db.flush()

    # 一条 pending 预警
    warning = WarningLog(
        student_id=student.id,
        warning_type=WarningType.score_drop,
        severity=WarningSeverity.warning,
        title="成绩下滑预警",
        message="最近一次考试正确率下降 15%",
        data={"drop": 0.15, "latest_exam_name": "期中考试"},
        status="pending",
    )
    db.add(warning)
    await db.flush()

    return teacher, class_, student, teacher_account, warning


def _teacher_token(account_id: int) -> dict:
    token = create_access_token(
        user_id=account_id, role="teacher", school_id=1, sub_role="teacher",
    )
    return {"Authorization": f"Bearer {token}"}


# ═══════════════════════════════════════════════════════════════
# Warning API Tests
# ═══════════════════════════════════════════════════════════════


class TestWarningList:
    """GET /warning/list — 预警列表。"""

    @pytest.mark.anyio
    async def test_unauthorized_no_token(self, async_client):
        """无 token → 401。"""
        resp = await async_client.get("/api/v1/warning/list")
        assert resp.status_code == 401

    @pytest.mark.anyio
    async def test_forbidden_student_role(self, async_client, student_headers):
        """学生角色 → 403。"""
        resp = await async_client.get(
            "/api/v1/warning/list", headers=student_headers,
        )
        assert resp.status_code == 403

    @pytest.mark.anyio
    async def test_list_success(self, async_client, db_session):
        """教师有权 → 200 + 返回预警列表。"""
        _, _, _, teacher_acct, warning = await _setup_teacher_with_warning(db_session)
        await db_session.commit()

        resp = await async_client.get(
            "/api/v1/warning/list",
            headers=_teacher_token(teacher_acct.id),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["total"] >= 1
        assert len(data["data"]) >= 1
        item = data["data"][0]
        assert item["id"] == warning.id
        assert "student_name" in item
        assert "class_name" in item

    @pytest.mark.anyio
    async def test_list_filter_by_severity(self, async_client, db_session):
        """按严重度筛选。"""
        _, _, _, teacher_acct, warning = await _setup_teacher_with_warning(db_session)
        await db_session.commit()

        # 筛选 severity=severe，应返回空
        resp = await async_client.get(
            "/api/v1/warning/list?severity=severe",
            headers=_teacher_token(teacher_acct.id),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0

        # 筛选 severity=warning，应返回数据
        resp = await async_client.get(
            "/api/v1/warning/list?severity=warning",
            headers=_teacher_token(teacher_acct.id),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1

    @pytest.mark.anyio
    async def test_list_filter_by_class(self, async_client, db_session):
        """按班级筛选。"""
        _, class_, _, teacher_acct, warning = await _setup_teacher_with_warning(
            db_session
        )
        await db_session.commit()

        resp = await async_client.get(
            f"/api/v1/warning/list?class_id={class_.id}",
            headers=_teacher_token(teacher_acct.id),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1

    @pytest.mark.anyio
    async def test_list_filter_by_status(self, async_client, db_session):
        """按状态筛选。"""
        _, _, _, teacher_acct, warning = await _setup_teacher_with_warning(db_session)
        await db_session.commit()

        resp = await async_client.get(
            "/api/v1/warning/list?status=pending",
            headers=_teacher_token(teacher_acct.id),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1

    @pytest.mark.anyio
    async def test_list_pagination(self, async_client, db_session):
        """分页参数正常。"""
        _, _, _, teacher_acct, _ = await _setup_teacher_with_warning(db_session)
        await db_session.commit()

        resp = await async_client.get(
            "/api/v1/warning/list?limit=5&offset=0",
            headers=_teacher_token(teacher_acct.id),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["limit"] == 5
        assert data["offset"] == 0


class TestWarningDetail:
    """GET /warning/{id} — 预警详情。"""

    @pytest.mark.anyio
    async def test_not_found(self, async_client, db_session):
        """不存在的预警 → 404。"""
        _, _, _, teacher_acct, _ = await _setup_teacher_with_warning(db_session)
        await db_session.commit()

        resp = await async_client.get(
            "/api/v1/warning/99999",
            headers=_teacher_token(teacher_acct.id),
        )
        assert resp.status_code == 404

    @pytest.mark.anyio
    async def test_detail_success(self, async_client, db_session):
        """有权访问 → 200 + 返回详情（含 data 快照）。"""
        _, _, _, teacher_acct, warning = await _setup_teacher_with_warning(db_session)
        await db_session.commit()

        resp = await async_client.get(
            f"/api/v1/warning/{warning.id}",
            headers=_teacher_token(teacher_acct.id),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        detail = data["data"]
        assert detail["id"] == warning.id
        assert detail["warning_type"] == "score_drop"
        assert detail["severity"] == "warning"
        assert detail["status"] == "pending"
        assert detail["data"] is not None
        assert detail["data"]["drop"] == 0.15


# ═══════════════════════════════════════════════════════════════
# Warning State Machine Tests (8.4)
# ═══════════════════════════════════════════════════════════════


class TestWarningStateMachine:
    """PATCH /warning/{id}/status — 状态机转换。"""

    @pytest.mark.anyio
    async def test_valid_transition_pending_to_processing(self, async_client, db_session):
        """pending → processing（合法）。"""
        _, _, _, teacher_acct, warning = await _setup_teacher_with_warning(db_session)
        await db_session.commit()

        resp = await async_client.patch(
            f"/api/v1/warning/{warning.id}/status",
            json={"status": "processing"},
            headers=_teacher_token(teacher_acct.id),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["data"]["status"] == "processing"

    @pytest.mark.anyio
    async def test_valid_transition_pending_to_dismissed(self, async_client, db_session):
        """pending → dismissed（合法）。"""
        _, _, _, teacher_acct, warning = await _setup_teacher_with_warning(db_session)
        await db_session.commit()

        resp = await async_client.patch(
            f"/api/v1/warning/{warning.id}/status",
            json={"status": "dismissed"},
            headers=_teacher_token(teacher_acct.id),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["data"]["status"] == "dismissed"

    @pytest.mark.anyio
    async def test_valid_transition_processing_to_resolved(self, async_client, db_session):
        """processing → resolved（合法）。"""
        _, _, _, teacher_acct, warning = await _setup_teacher_with_warning(db_session)
        # 先设成 processing
        warning.status = "processing"
        await db_session.commit()

        resp = await async_client.patch(
            f"/api/v1/warning/{warning.id}/status",
            json={"status": "resolved"},
            headers=_teacher_token(teacher_acct.id),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["data"]["status"] == "resolved"

    @pytest.mark.anyio
    async def test_invalid_transition_resolved_to_pending(self, async_client, db_session):
        """resolved → pending（非法）→ 422。"""
        _, _, _, teacher_acct, warning = await _setup_teacher_with_warning(db_session)
        # 先设成 resolved
        warning.status = "resolved"
        await db_session.commit()

        resp = await async_client.patch(
            f"/api/v1/warning/{warning.id}/status",
            json={"status": "pending"},
            headers=_teacher_token(teacher_acct.id),
        )
        assert resp.status_code == 422
        assert "非法状态转换" in resp.json()["detail"]

    @pytest.mark.anyio
    async def test_invalid_transition_dismissed_to_pending(self, async_client, db_session):
        """dismissed → pending（非法）→ 422。"""
        _, _, _, teacher_acct, warning = await _setup_teacher_with_warning(db_session)
        warning.status = "dismissed"
        await db_session.commit()

        resp = await async_client.patch(
            f"/api/v1/warning/{warning.id}/status",
            json={"status": "pending"},
            headers=_teacher_token(teacher_acct.id),
        )
        assert resp.status_code == 422

    @pytest.mark.anyio
    async def test_invalid_transition_dismissed_to_processing(self, async_client, db_session):
        """dismissed → processing（非法）→ 422。"""
        _, _, _, teacher_acct, warning = await _setup_teacher_with_warning(db_session)
        warning.status = "dismissed"
        await db_session.commit()

        resp = await async_client.patch(
            f"/api/v1/warning/{warning.id}/status",
            json={"status": "processing"},
            headers=_teacher_token(teacher_acct.id),
        )
        assert resp.status_code == 422

    @pytest.mark.anyio
    async def test_invalid_transition_pending_to_resolved(self, async_client, db_session):
        """pending → resolved（跳过 processing，非法）→ 422。"""
        _, _, _, teacher_acct, warning = await _setup_teacher_with_warning(db_session)
        await db_session.commit()

        resp = await async_client.patch(
            f"/api/v1/warning/{warning.id}/status",
            json={"status": "resolved"},
            headers=_teacher_token(teacher_acct.id),
        )
        assert resp.status_code == 422

    @pytest.mark.anyio
    async def test_transition_records_processed_info(self, async_client, db_session):
        """resolved/dismissed 时记录 processed_by 和 processed_at。"""
        _, _, _, teacher_acct, warning = await _setup_teacher_with_warning(db_session)
        await db_session.commit()

        resp = await async_client.patch(
            f"/api/v1/warning/{warning.id}/status",
            json={"status": "dismissed", "note": "该学生已补课提升"},
            headers=_teacher_token(teacher_acct.id),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["data"]["processed_by"] is not None
        assert data["data"]["processed_at"] is not None

    @pytest.mark.anyio
    async def test_invalid_status_value_rejected(self, async_client, db_session):
        """非法状态值 → 422（Pydantic 校验）。"""
        _, _, _, teacher_acct, warning = await _setup_teacher_with_warning(db_session)
        await db_session.commit()

        resp = await async_client.patch(
            f"/api/v1/warning/{warning.id}/status",
            json={"status": "invalid_status"},
            headers=_teacher_token(teacher_acct.id),
        )
        assert resp.status_code == 422


class TestWarningStats:
    """GET /warning/stats — 预警统计摘要。"""

    @pytest.mark.anyio
    async def test_stats_success(self, async_client, db_session):
        """教师有权 → 200 + 返回统计。"""
        _, _, _, teacher_acct, warning = await _setup_teacher_with_warning(db_session)
        await db_session.commit()

        resp = await async_client.get(
            "/api/v1/warning/stats",
            headers=_teacher_token(teacher_acct.id),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        stats = data["data"]
        assert "total" in stats
        assert "by_type" in stats
        assert "by_severity" in stats
        assert stats["total"] >= 1

    @pytest.mark.anyio
    async def test_stats_filter_by_class(self, async_client, db_session):
        """按班级筛选统计。"""
        _, class_, _, teacher_acct, warning = await _setup_teacher_with_warning(
            db_session
        )
        await db_session.commit()

        resp = await async_client.get(
            f"/api/v1/warning/stats?class_id={class_.id}",
            headers=_teacher_token(teacher_acct.id),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["data"]["total"] >= 1

    @pytest.mark.anyio
    async def test_stats_only_counts_pending_processing(self, async_client, db_session):
        """统计仅计数 pending/processing 状态。"""
        _, _, _, teacher_acct, warning = await _setup_teacher_with_warning(db_session)
        # 再创建一个 resolved 的预警（不应计入总数）
        resolved_warning = WarningLog(
            student_id=warning.student_id,
            warning_type=WarningType.consecutive_absence,
            severity=WarningSeverity.info,
            title="已解决预警",
            message="已处理",
            status="resolved",
        )
        db_session.add(resolved_warning)
        await db_session.commit()

        resp = await async_client.get(
            "/api/v1/warning/stats",
            headers=_teacher_token(teacher_acct.id),
        )
        assert resp.status_code == 200
        data = resp.json()
        # total 只计 pending/processing，不包括 resolved
        by_type = data["data"]["by_type"]
        assert "consecutive_absence" not in by_type  # resolved 不计入


class TestWarningCheck:
    """POST /warning/check — 手动触发检测。"""

    @pytest.mark.anyio
    async def test_check_success(self, async_client, db_session):
        """教师有权 → 200 + 返回 task_id。"""
        _, _, _, teacher_acct, _ = await _setup_teacher_with_warning(db_session)
        await db_session.commit()

        resp = await async_client.post(
            "/api/v1/warning/check",
            headers=_teacher_token(teacher_acct.id),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "task_id" in data["data"]
        assert data["data"]["status"] == "scheduled"
        assert data["data"]["task_id"].startswith("wc-")

    @pytest.mark.anyio
    async def test_check_concurrent_rejected(self, async_client, db_session):
        """并发调用 → 锁被持有时第二个请求应返回 429。"""
        from app.services.early_warning_service import EarlyWarningService

        _, _, _, teacher_acct, _ = await _setup_teacher_with_warning(db_session)
        await db_session.commit()

        # 模拟检测任务运行中：获取互斥锁
        await EarlyWarningService._check_lock.acquire()
        try:
            resp = await async_client.post(
                "/api/v1/warning/check",
                headers=_teacher_token(teacher_acct.id),
            )
            assert resp.status_code == 429
            assert "已有预警检测任务运行中" in resp.json()["detail"]
        finally:
            EarlyWarningService._check_lock.release()
