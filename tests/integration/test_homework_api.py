"""Homework API 集成测试 — 教师端报告发送。

绑定/通知路由已迁移至 test_parent_api.py。
"""

import pytest


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
