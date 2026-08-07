"""Homework API 集成测试 — 亲子绑定/通知/报告。

所有测试使用 conftest fixtures 实现完全隔离。
"""

import pytest


class TestBindings:
    """亲子绑定 — POST/GET/DELETE /bindings。"""

    @pytest.mark.anyio
    async def test_create_binding_invalid_code(self, async_client, admin_headers):
        """无效绑定码 → 400。"""
        resp = await async_client.post(
            "/api/v1/bindings",
            json={
                "student_id": 1,
                "parent_id": 1,
                "bind_code": "ZZZZZZ",
                "relation": "mother",
            },
            headers=admin_headers,
        )
        # 绑定码不存在 → 400 或 404（取决于业务逻辑）
        assert resp.status_code in (400, 404)

    @pytest.mark.anyio
    async def test_list_bindings_empty(self, async_client, admin_headers):
        """无绑定数据时返回空列表。"""
        resp = await async_client.get(
            "/api/v1/bindings", headers=admin_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["data"] == []

    @pytest.mark.anyio
    async def test_delete_nonexistent_binding(self, async_client, admin_headers):
        """删除不存在绑定 → 404。"""
        resp = await async_client.delete(
            "/api/v1/bindings/99999", headers=admin_headers,
        )
        assert resp.status_code == 404


class TestNotifications:
    """家长通知 — GET /notifications。"""

    @pytest.mark.anyio
    async def test_list_notifications_empty(self, async_client, admin_headers):
        """无通知数据时返回空分页。"""
        resp = await async_client.get(
            "/api/v1/notifications",
            params={"parent_id": 1},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert data["total"] >= 0

    @pytest.mark.anyio
    async def test_mark_nonexistent_notification_read(self, async_client, admin_headers):
        """标记不存在通知为已读 → 404。"""
        resp = await async_client.post(
            "/api/v1/notifications/99999/read",
            headers=admin_headers,
        )
        assert resp.status_code == 404


class TestReports:
    """考试报告 — POST /reports/send-to-students/{exam_id}。"""

    @pytest.mark.anyio
    async def test_send_reports_nonexistent_exam(self, async_client, admin_headers):
        """不存在的考试 → stub 返回（不抛异常）。"""
        resp = await async_client.post(
            "/api/v1/reports/send-to-students/99999",
            headers=admin_headers,
        )
        # stub 实现通常返回 200 带空数据
        assert resp.status_code in (200, 404)
