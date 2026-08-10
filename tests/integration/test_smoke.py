"""冒烟测试 — 验证 conftest.py 基础设施：engine、session、client、headers、factories。"""

import pytest
from httpx import AsyncClient, ASGITransport


class TestSmoke:
    """验证所有顶层 fixture 可用且正确隔离。"""

    @pytest.mark.anyio
    async def test_admin_headers_work(self, async_client, admin_headers):
        """admin 可访问学校列表。"""
        resp = await async_client.get("/api/v1/schools", headers=admin_headers)
        assert resp.status_code == 200
        assert "items" in resp.json()

    @pytest.mark.anyio
    async def test_teacher_cannot_create_school(self, async_client, teacher_headers):
        """普通教师无权创建学校。"""
        resp = await async_client.post(
            "/api/v1/schools",
            json={"name": "越权学校"},
            headers=teacher_headers,
        )
        assert resp.status_code == 403

    @pytest.mark.anyio
    async def test_unauthenticated_blocked(self, async_client):
        """无 token 被拦截。"""
        resp = await async_client.get("/api/v1/schools")
        assert resp.status_code == 401

    @pytest.mark.anyio
    async def test_school_factory(self, async_client, admin_headers, school):
        """factory 创建的学校可查询。"""
        resp = await async_client.get(
            f"/api/v1/schools/{school['id']}", headers=admin_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == school["name"]

    @pytest.mark.anyio
    async def test_full_org_chain(self, async_client, admin_headers, school, grade, class_):
        """school → grade → class 工厂链正确连接。"""
        assert grade["school_id"] == school["id"]
        assert class_["grade_id"] == grade["id"]

        # 验证年级属于学校
        resp = await async_client.get(
            f"/api/v1/schools/{school['id']}/grades", headers=admin_headers,
        )
        assert resp.status_code == 200
        assert any(g["id"] == grade["id"] for g in resp.json()["items"])

    @pytest.mark.anyio
    async def test_schools_api_paginated(self, async_client, admin_headers):
        """学校列表 API 返回分页结果。"""
        resp = await async_client.get(
            "/api/v1/schools?limit=100", headers=admin_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert isinstance(data["items"], list)
