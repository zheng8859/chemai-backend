"""Org API 集成测试 — School/Grade/Class CRUD + 组织树 + RBAC 权限。

使用 conftest fixtures（async_client + admin_headers/teacher_headers）实现隔离。
"""

import pytest


class TestSchoolCRUD:
    """学校 CRUD 操作。"""

    @pytest.mark.anyio
    async def test_create_and_get_school(self, async_client, admin_headers):
        """创建学校 → 获取学校详情 → 验证字段。"""
        resp = await async_client.post(
            "/api/v1/schools",
            json={"name": "测试中学", "region": "北京"},
            headers=admin_headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "测试中学"
        school_id = data["id"]

        resp = await async_client.get(
            f"/api/v1/schools/{school_id}", headers=admin_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "测试中学"

    @pytest.mark.anyio
    async def test_list_schools(self, async_client, admin_headers):
        """学校列表分页。"""
        resp = await async_client.get(
            "/api/v1/schools?limit=10&offset=0", headers=admin_headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "items" in body
        assert "total" in body
        assert isinstance(body["items"], list)

    @pytest.mark.anyio
    async def test_update_school(self, async_client, admin_headers):
        """更新学校名称。"""
        resp = await async_client.post(
            "/api/v1/schools",
            json={"name": "更新前"},
            headers=admin_headers,
        )
        assert resp.status_code == 201
        school_id = resp.json()["id"]

        resp = await async_client.patch(
            f"/api/v1/schools/{school_id}",
            json={"name": "更新后"},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "更新后"

    @pytest.mark.anyio
    async def test_delete_school(self, async_client, admin_headers):
        """删除学校返回 204。"""
        resp = await async_client.post(
            "/api/v1/schools",
            json={"name": "待删除"},
            headers=admin_headers,
        )
        school_id = resp.json()["id"]

        resp = await async_client.delete(
            f"/api/v1/schools/{school_id}", headers=admin_headers,
        )
        assert resp.status_code == 204


class TestGradeCRUD:
    """年级 CRUD 操作。"""

    @pytest.mark.anyio
    async def test_create_and_list_grades(self, async_client, admin_headers):
        """创建年级 → 在学校下列出年级。"""
        # 先创建学校
        resp = await async_client.post(
            "/api/v1/schools",
            json={"name": "年级测试校"},
            headers=admin_headers,
        )
        school_id = resp.json()["id"]

        # 创建年级
        resp = await async_client.post(
            "/api/v1/grades",
            json={"school_id": school_id, "name": "高一"},
            headers=admin_headers,
        )
        assert resp.status_code == 201
        assert resp.json()["name"] == "高一"

        # 列出学校下年级
        resp = await async_client.get(
            f"/api/v1/schools/{school_id}/grades",
            headers=admin_headers,
        )
        assert resp.status_code == 200
        assert len(resp.json()["items"]) >= 1


class TestClassCRUD:
    """班级 CRUD 操作。"""

    @pytest.mark.anyio
    async def test_create_and_get_class(self, async_client, admin_headers):
        """创建班级 → 获取班级详情。"""
        # 创建学校和年级
        resp = await async_client.post(
            "/api/v1/schools",
            json={"name": "班级测试校"},
            headers=admin_headers,
        )
        school_id = resp.json()["id"]

        resp = await async_client.post(
            "/api/v1/grades",
            json={"school_id": school_id, "name": "高二"},
            headers=admin_headers,
        )
        grade_id = resp.json()["id"]

        # 创建班级
        resp = await async_client.post(
            "/api/v1/classes",
            json={"grade_id": grade_id, "name": "高二(3)班"},
            headers=admin_headers,
        )
        assert resp.status_code == 201
        class_id = resp.json()["id"]
        assert resp.json()["name"] == "高二(3)班"

        # 获取班级详情
        resp = await async_client.get(
            f"/api/v1/classes/{class_id}", headers=admin_headers,
        )
        assert resp.status_code == 200


class TestOrgTree:
    """组织树查询。"""

    @pytest.mark.anyio
    async def test_org_tree(self, async_client, admin_headers):
        """组织树返回嵌套结构。"""
        resp = await async_client.get("/api/v1/org/tree", headers=admin_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert "data" in body


class TestRBAC:
    """RBAC 权限测试。"""

    @pytest.mark.anyio
    async def test_teacher_cannot_create_school(self, async_client, teacher_headers):
        """普通教师无权创建学校（403）。"""
        resp = await async_client.post(
            "/api/v1/schools",
            json={"name": "教师越权"},
            headers=teacher_headers,
        )
        assert resp.status_code == 403

    @pytest.mark.anyio
    async def test_unauthenticated_blocked(self, async_client):
        """未认证请求被阻断（401）。"""
        resp = await async_client.get("/api/v1/schools")
        assert resp.status_code == 401
