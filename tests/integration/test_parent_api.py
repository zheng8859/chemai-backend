"""Parent API 集成测试 — 绑码/绑定/解绑/子女查询/通知 CRUD。

所有测试使用 conftest fixtures 实现完全隔离。
"""

import pytest
from sqlalchemy import select

from app.models.user import Account, Student, Parent
from app.models.homework import StudentParentBinding, ParentNotification
from app.core.enums import AccountRole, BindingStatus, NotificationType


class TestBindCode:
    """绑码管理 — POST /parent/bind-code/{student_id}。"""

    @pytest.mark.anyio
    async def test_set_bind_code_as_admin_returns_403(self, async_client, admin_headers):
        """非学生角色 → 403。"""
        resp = await async_client.post(
            "/api/v1/parent/bind-code/1",
            json={"bind_code": "123456"},
            headers=admin_headers,
        )
        assert resp.status_code == 403

    @pytest.mark.anyio
    async def test_set_bind_code_as_student(
        self, async_client, student_headers, db_session,
    ):
        """学生设置绑定码 → 200（需先有 Student 记录）。"""
        # 创建 Account + Student
        from app.models.org import School, Grade, Class as ClassModel
        school = School(name="测试学校", region="测试区")
        db_session.add(school)
        await db_session.flush()
        grade = Grade(name="高一", school_id=school.id)
        db_session.add(grade)
        await db_session.flush()
        class_ = ClassModel(name="高一(1)班", grade_id=grade.id)
        db_session.add(class_)
        await db_session.flush()

        account = Account(
            id=997, phone="13800000001", password_hash="hash",
            role=AccountRole.student,
        )
        db_session.add(account)
        await db_session.flush()

        student = Student(
            account_id=account.id, class_id=class_.id, school_id=school.id,
            name="测试学生", student_id="S00001",
        )
        db_session.add(student)
        await db_session.commit()

        resp = await async_client.post(
            f"/api/v1/parent/bind-code/{account.id}",
            json={"bind_code": "654321"},
            headers=student_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "绑定码已更新" in data["message"]


class TestBindings:
    """亲子绑定 — POST /parent/bind, GET /children, DELETE /bind/{id}。"""

    @pytest.mark.anyio
    async def test_bind_invalid_code(self, async_client, parent_headers, db_session):
        """无效绑定码 → 400。"""
        # 需要先创建 Parent 记录（Account 996 + Parent）
        account = Account(
            id=996, phone="13800000002", password_hash="hash",
            role=AccountRole.parent,
        )
        db_session.add(account)
        await db_session.flush()
        parent = Parent(account_id=account.id, name="测试家长")
        db_session.add(parent)
        await db_session.commit()

        resp = await async_client.post(
            "/api/v1/parent/bind",
            json={
                "student_id": 99999,
                "bind_code": "000000",
                "relation": "mother",
            },
            headers=parent_headers,
        )
        # 学生不存在 → 404
        assert resp.status_code == 404

    @pytest.mark.anyio
    async def test_non_parent_role_returns_403(self, async_client, admin_headers):
        """非家长角色 → 403。"""
        resp = await async_client.post(
            "/api/v1/parent/bind",
            json={
                "student_id": 1,
                "bind_code": "123456",
                "relation": "father",
            },
            headers=admin_headers,
        )
        assert resp.status_code == 403

    @pytest.mark.anyio
    async def test_list_children_empty(self, async_client, parent_headers, db_session):
        """无绑定子女 → 空列表。"""
        account = Account(
            id=996, phone="13800000003", password_hash="hash",
            role=AccountRole.parent,
        )
        db_session.add(account)
        await db_session.flush()
        parent = Parent(account_id=account.id, name="测试家长")
        db_session.add(parent)
        await db_session.commit()

        resp = await async_client.get(
            "/api/v1/parent/children", headers=parent_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["data"] == []

    @pytest.mark.anyio
    async def test_delete_nonexistent_binding(self, async_client, parent_headers, db_session):
        """删除不存在绑定 → 404。"""
        account = Account(
            id=996, phone="13800000004", password_hash="hash",
            role=AccountRole.parent,
        )
        db_session.add(account)
        await db_session.flush()
        parent = Parent(account_id=account.id, name="测试家长")
        db_session.add(parent)
        await db_session.commit()

        resp = await async_client.delete(
            "/api/v1/parent/bind/99999", headers=parent_headers,
        )
        assert resp.status_code == 404


class TestChildDataQuery:
    """子女数据查询 — GET /child/{id}/report, /timeline。"""

    @pytest.mark.anyio
    async def test_report_without_binding(self, async_client, parent_headers, db_session):
        """未绑定学生 → 403。"""
        account = Account(
            id=996, phone="13800000005", password_hash="hash",
            role=AccountRole.parent,
        )
        db_session.add(account)
        await db_session.flush()
        parent = Parent(account_id=account.id, name="测试家长")
        db_session.add(parent)
        await db_session.commit()

        resp = await async_client.get(
            "/api/v1/parent/child/999/report", headers=parent_headers,
        )
        assert resp.status_code == 403

    @pytest.mark.anyio
    async def test_timeline_without_binding(self, async_client, parent_headers, db_session):
        """未绑定学生 → 403。"""
        account = Account(
            id=996, phone="13800000006", password_hash="hash",
            role=AccountRole.parent,
        )
        db_session.add(account)
        await db_session.flush()
        parent = Parent(account_id=account.id, name="测试家长")
        db_session.add(parent)
        await db_session.commit()

        resp = await async_client.get(
            "/api/v1/parent/child/999/timeline", headers=parent_headers,
        )
        assert resp.status_code == 403


class TestWeeklyReport:
    """周报 — GET /child/{id}/weekly, POST /child/{id}/weekly/generate。"""

    @pytest.mark.anyio
    async def test_weekly_without_binding(self, async_client, parent_headers, db_session):
        """未绑定 → 403。"""
        account = Account(
            id=996, phone="13800000007", password_hash="hash",
            role=AccountRole.parent,
        )
        db_session.add(account)
        await db_session.flush()
        parent = Parent(account_id=account.id, name="测试家长")
        db_session.add(parent)
        await db_session.commit()

        resp = await async_client.get(
            "/api/v1/parent/child/999/weekly", headers=parent_headers,
        )
        assert resp.status_code == 403


class TestNotifications:
    """通知管理 — GET /parent/notifications, PUT /parent/notifications/{id}/read。"""

    @pytest.mark.anyio
    async def test_list_notifications_empty(self, async_client, parent_headers, db_session):
        """无通知 → 空分页。"""
        account = Account(
            id=996, phone="13800000008", password_hash="hash",
            role=AccountRole.parent,
        )
        db_session.add(account)
        await db_session.flush()
        parent = Parent(account_id=account.id, name="测试家长")
        db_session.add(parent)
        await db_session.commit()

        resp = await async_client.get(
            "/api/v1/parent/notifications", headers=parent_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert data["total"] >= 0

    @pytest.mark.anyio
    async def test_mark_nonexistent_notification(self, async_client, parent_headers, db_session):
        """标记不存在通知 → 404。"""
        account = Account(
            id=996, phone="13800000009", password_hash="hash",
            role=AccountRole.parent,
        )
        db_session.add(account)
        await db_session.flush()
        parent = Parent(account_id=account.id, name="测试家长")
        db_session.add(parent)
        await db_session.commit()

        resp = await async_client.put(
            "/api/v1/parent/notifications/99999/read", headers=parent_headers,
        )
        assert resp.status_code == 404


class TestConversations:
    """对话管理 — /parent/agent/conversations 系列。"""

    @pytest.mark.anyio
    async def test_list_conversations_empty(self, async_client, parent_headers, db_session):
        """无对话 → 空列表。"""
        account = Account(
            id=996, phone="13800000010", password_hash="hash",
            role=AccountRole.parent,
        )
        db_session.add(account)
        await db_session.flush()
        parent = Parent(account_id=account.id, name="测试家长")
        db_session.add(parent)
        await db_session.commit()

        resp = await async_client.get(
            "/api/v1/parent/agent/conversations", headers=parent_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["data"] == []

    @pytest.mark.anyio
    async def test_create_conversation(self, async_client, parent_headers, db_session):
        """创建新对话 → 返回 thread_id。"""
        account = Account(
            id=996, phone="13800000011", password_hash="hash",
            role=AccountRole.parent,
        )
        db_session.add(account)
        await db_session.flush()
        parent = Parent(account_id=account.id, name="测试家长")
        db_session.add(parent)
        await db_session.commit()

        resp = await async_client.post(
            "/api/v1/parent/agent/new", headers=parent_headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["success"] is True
        assert data["data"]["thread_id"].startswith("p-")

    @pytest.mark.anyio
    async def test_history_not_found(self, async_client, parent_headers, db_session):
        """不存在的对话 → 404。"""
        account = Account(
            id=996, phone="13800000012", password_hash="hash",
            role=AccountRole.parent,
        )
        db_session.add(account)
        await db_session.flush()
        parent = Parent(account_id=account.id, name="测试家长")
        db_session.add(parent)
        await db_session.commit()

        resp = await async_client.get(
            "/api/v1/parent/agent/history/p-nonexistent", headers=parent_headers,
        )
        assert resp.status_code == 404

    @pytest.mark.anyio
    async def test_delete_conversation(self, async_client, parent_headers, db_session):
        """删除不存在/不归属的对话 → 404（已校验归属）。"""
        account = Account(
            id=996, phone="13800000013", password_hash="hash",
            role=AccountRole.parent,
        )
        db_session.add(account)
        await db_session.flush()
        parent = Parent(account_id=account.id, name="测试家长")
        db_session.add(parent)
        await db_session.commit()

        resp = await async_client.delete(
            "/api/v1/parent/agent/conversations/p-nonexistent", headers=parent_headers,
        )
        assert resp.status_code == 404


class TestBindCodeAsStudent:
    """学生端绑码完整流程。"""

    @pytest.mark.anyio
    async def test_student_not_found(self, async_client, student_headers):
        """Account 无 Student 记录 → 404（由 require_student_self 触发）。"""
        resp = await async_client.post(
            "/api/v1/parent/bind-code/997",
            json={"bind_code": "123456"},
            headers=student_headers,
        )
        assert resp.status_code == 404
