"""Org API 集成测试 — School/Grade/Class CRUD + 组织树 + RBAC 权限。

需要运行中的数据库（Phase 2 migration 已执行）。
"""

import pytest
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.core.security import create_access_token


# ── Helpers ──────────────────────────────────────────────────

def _auth_header(role="teacher", sub_role="teacher", school_id=1):
    """生成测试用 JWT Bearer header。"""
    token = create_access_token(user_id=1, role=role, school_id=school_id, sub_role=sub_role)
    return {"Authorization": f"Bearer {token}"}


def _admin_header(school_id=1):
    return _auth_header(role="teacher", sub_role="system_admin", school_id=school_id)


# ── School 测试 ──────────────────────────────────────────────

@pytest.mark.anyio
async def test_create_and_get_school():
    """创建学校 → 获取学校详情 → 验证字段。"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 创建学校
        resp = await client.post(
            "/api/v1/schools",
            json={"name": "测试中学", "region": "北京"},
            headers=_admin_header(),
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "测试中学"
        school_id = data["id"]

        # 获取学校详情
        resp = await client.get(f"/api/v1/schools/{school_id}", headers=_admin_header())
        assert resp.status_code == 200
        assert resp.json()["name"] == "测试中学"


@pytest.mark.anyio
async def test_list_schools():
    """学校列表分页。"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v1/schools?limit=10&offset=0", headers=_admin_header())
        assert resp.status_code == 200
        body = resp.json()
        assert "items" in body
        assert "total" in body
        assert isinstance(body["items"], list)


@pytest.mark.anyio
async def test_update_school():
    """更新学校名称。"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 先创建
        resp = await client.post(
            "/api/v1/schools",
            json={"name": "更新前"},
            headers=_admin_header(),
        )
        assert resp.status_code == 201
        school_id = resp.json()["id"]

        # 更新
        resp = await client.patch(
            f"/api/v1/schools/{school_id}",
            json={"name": "更新后"},
            headers=_admin_header(),
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "更新后"


@pytest.mark.anyio
async def test_delete_school():
    """删除学校返回 204。"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/schools",
            json={"name": "待删除"},
            headers=_admin_header(),
        )
        school_id = resp.json()["id"]

        resp = await client.delete(f"/api/v1/schools/{school_id}", headers=_admin_header())
        assert resp.status_code == 204


# ── Grade 测试 ───────────────────────────────────────────────

@pytest.mark.anyio
async def test_create_and_list_grades():
    """创建年级 → 在学校下列出年级。"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 先创建学校
        resp = await client.post(
            "/api/v1/schools",
            json={"name": "年级测试校"},
            headers=_admin_header(),
        )
        school_id = resp.json()["id"]

        # 创建年级
        resp = await client.post(
            "/api/v1/grades",
            json={"school_id": school_id, "name": "高一"},
            headers=_admin_header(),
        )
        assert resp.status_code == 201
        assert resp.json()["name"] == "高一"

        # 列出学校下年级
        resp = await client.get(
            f"/api/v1/schools/{school_id}/grades",
            headers=_admin_header(),
        )
        assert resp.status_code == 200
        assert len(resp.json()["items"]) >= 1


# ── Class 测试 ───────────────────────────────────────────────

@pytest.mark.anyio
async def test_create_and_get_class():
    """创建班级 → 获取班级详情。"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 创建学校和年级
        resp = await client.post(
            "/api/v1/schools",
            json={"name": "班级测试校"},
            headers=_admin_header(),
        )
        school_id = resp.json()["id"]

        resp = await client.post(
            "/api/v1/grades",
            json={"school_id": school_id, "name": "高二"},
            headers=_admin_header(),
        )
        grade_id = resp.json()["id"]

        # 创建班级
        resp = await client.post(
            "/api/v1/classes",
            json={"grade_id": grade_id, "name": "高二(3)班"},
            headers=_admin_header(),
        )
        assert resp.status_code == 201
        class_id = resp.json()["id"]
        assert resp.json()["name"] == "高二(3)班"

        # 获取班级详情
        resp = await client.get(f"/api/v1/classes/{class_id}", headers=_admin_header())
        assert resp.status_code == 200


# ── Org Tree 测试 ────────────────────────────────────────────

@pytest.mark.anyio
async def test_org_tree():
    """组织树返回嵌套结构。"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v1/org/tree", headers=_admin_header())
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert "data" in body


# ── RBAC 权限测试 ────────────────────────────────────────────

@pytest.mark.anyio
async def test_teacher_cannot_create_school():
    """普通教师无权创建学校（403）。"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/schools",
            json={"name": "教师越权"},
            headers=_auth_header(role="teacher", sub_role="teacher"),
        )
        assert resp.status_code == 403


@pytest.mark.anyio
async def test_unauthenticated_blocked():
    """未认证请求被阻断（401）。"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v1/schools")
        assert resp.status_code == 401
