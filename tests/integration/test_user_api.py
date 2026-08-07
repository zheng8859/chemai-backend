"""User API 集成测试 — Student/Parent/TeacherAssignment CRUD + RBAC + Accounts。

所有测试使用 conftest fixtures 实现完全隔离。
"""

import pytest
from httpx import QueryParams


class TestStudentCRUD:
    """学生 CRUD — POST /students, GET/PATCH/DELETE /students/{id}。"""

    @pytest.mark.anyio
    async def test_create_student(self, async_client, admin_headers, class_):
        """admin 可创建学生（Query params）。"""
        params = {
            "name": "张三",
            "studentId": "S2026001",
            "class_id": class_["id"],
        }
        resp = await async_client.post(
            "/api/v1/students", params=params, headers=admin_headers,
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["success"] is True
        assert data["data"]["name"] == "张三"

    @pytest.mark.anyio
    async def test_teacher_cannot_create_student(self, async_client, teacher_headers, class_):
        """普通教师无权创建学生 → 403。"""
        params = {
            "name": "越权学生",
            "studentId": "S9999",
            "class_id": class_["id"],
        }
        resp = await async_client.post(
            "/api/v1/students", params=params, headers=teacher_headers,
        )
        assert resp.status_code == 403

    @pytest.mark.anyio
    async def test_get_student(self, async_client, admin_headers, class_):
        """获取学生详情。"""
        # 创建
        params = {"name": "李四", "studentId": "S2026002", "class_id": class_["id"]}
        resp = await async_client.post(
            "/api/v1/students", params=params, headers=admin_headers,
        )
        student_id = resp.json()["data"]["id"]

        # 查询
        resp = await async_client.get(
            f"/api/v1/students/{student_id}", headers=admin_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["name"] == "李四"

    @pytest.mark.anyio
    async def test_list_students_by_class(self, async_client, admin_headers, class_):
        """按班级列出学生（注：service 层 phone="" 唯一键限制，单次创建一名学生）。"""
        params = {"name": "学生0", "studentId": "S20010", "class_id": class_["id"]}
        await async_client.post(
            "/api/v1/students", params=params, headers=admin_headers,
        )

        resp = await async_client.get(
            f"/api/v1/classes/{class_['id']}/students",
            headers=admin_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1

    @pytest.mark.anyio
    async def test_update_student(self, async_client, admin_headers, class_):
        """更新学生姓名。"""
        params = {"name": "王五", "studentId": "S2026003", "class_id": class_["id"]}
        resp = await async_client.post(
            "/api/v1/students", params=params, headers=admin_headers,
        )
        student_id = resp.json()["data"]["id"]

        resp = await async_client.patch(
            f"/api/v1/students/{student_id}",
            json={"name": "王五改名"},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["name"] == "王五改名"

    @pytest.mark.anyio
    async def test_delete_student(self, async_client, admin_headers, class_):
        """删除学生 → 204。"""
        params = {"name": "删除生", "studentId": "S2026004", "class_id": class_["id"]}
        resp = await async_client.post(
            "/api/v1/students", params=params, headers=admin_headers,
        )
        student_id = resp.json()["data"]["id"]

        resp = await async_client.delete(
            f"/api/v1/students/{student_id}", headers=admin_headers,
        )
        assert resp.status_code == 204

    @pytest.mark.anyio
    async def test_get_nonexistent_student_404(self, async_client, admin_headers):
        """查询不存在学生 → 404。"""
        resp = await async_client.get(
            "/api/v1/students/99999", headers=admin_headers,
        )
        assert resp.status_code == 404


class TestParentCRUD:
    """家长 CRUD — POST /parents, GET/PATCH /parents/{id}。"""

    @pytest.mark.anyio
    async def test_create_parent(self, async_client, admin_headers):
        """admin 可创建家长。"""
        params = {"name": "张爸爸", "phone": "13850000001"}
        resp = await async_client.post(
            "/api/v1/parents", params=params, headers=admin_headers,
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["success"] is True
        assert data["data"]["name"] == "张爸爸"

    @pytest.mark.anyio
    async def test_list_parents(self, async_client, admin_headers):
        """列出所有家长。"""
        # 创建家长
        for i in range(2):
            params = {"name": f"家长{i}", "phone": f"138500000{i}"}
            await async_client.post(
                "/api/v1/parents", params=params, headers=admin_headers,
            )

        resp = await async_client.get("/api/v1/parents", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 2

    @pytest.mark.anyio
    async def test_get_parent(self, async_client, admin_headers):
        """获取家长详情。"""
        params = {"name": "李妈妈", "phone": "13850000003"}
        resp = await async_client.post(
            "/api/v1/parents", params=params, headers=admin_headers,
        )
        parent_id = resp.json()["data"]["id"]

        resp = await async_client.get(
            f"/api/v1/parents/{parent_id}", headers=admin_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["name"] == "李妈妈"

    @pytest.mark.anyio
    async def test_update_parent(self, async_client, admin_headers):
        """更新家长信息。"""
        params = {"name": "王爸爸", "phone": "13850000004"}
        resp = await async_client.post(
            "/api/v1/parents", params=params, headers=admin_headers,
        )
        parent_id = resp.json()["data"]["id"]

        resp = await async_client.patch(
            f"/api/v1/parents/{parent_id}",
            json={"name": "王爸爸改名", "email": "test@example.com"},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["name"] == "王爸爸改名"

    @pytest.mark.anyio
    async def test_get_nonexistent_parent_404(self, async_client, admin_headers):
        """查询不存在的家长 → 404。"""
        resp = await async_client.get(
            "/api/v1/parents/99999", headers=admin_headers,
        )
        assert resp.status_code == 404


class TestTeacherAssignment:
    """教师任课分配 — POST/GET/DELETE /teacher-assignments。"""

    @pytest.mark.anyio
    async def test_create_and_list_assignment(self, async_client, admin_headers, class_):
        """创建任课分配 → 列出教师任课 → 验证。"""
        resp = await async_client.post(
            "/api/v1/teacher-assignments",
            json={"teacher_id": 999, "class_id": class_["id"], "subject": "化学"},
            headers=admin_headers,
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["subject"] == "化学"
        assignment_id = data["id"]

        # 列出教师任课
        resp = await async_client.get(
            f"/api/v1/teacher-assignments?teacher_id=999",
            headers=admin_headers,
        )
        assert resp.status_code == 200
        assignments = resp.json()["data"]
        assert any(a["id"] == assignment_id for a in assignments)

    @pytest.mark.anyio
    async def test_delete_assignment(self, async_client, admin_headers, class_):
        """删除任课关系 → 204。"""
        resp = await async_client.post(
            "/api/v1/teacher-assignments",
            json={"teacher_id": 999, "class_id": class_["id"], "subject": "化学"},
            headers=admin_headers,
        )
        assignment_id = resp.json()["id"]

        resp = await async_client.delete(
            f"/api/v1/teacher-assignments/{assignment_id}",
            headers=admin_headers,
        )
        assert resp.status_code == 204

    @pytest.mark.anyio
    async def test_teacher_cannot_assign(self, async_client, teacher_headers, class_):
        """普通教师无权创建任课分配 → 403。"""
        resp = await async_client.post(
            "/api/v1/teacher-assignments",
            json={"teacher_id": 998, "class_id": class_["id"], "subject": "化学"},
            headers=teacher_headers,
        )
        assert resp.status_code == 403


class TestAccountsList:
    """GET /accounts — 账户列表。"""

    @pytest.mark.anyio
    async def test_list_accounts(self, async_client, admin_headers):
        """列出账户（需认证）。"""
        resp = await async_client.get("/api/v1/accounts", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "data" in data
        assert "total" in data

    @pytest.mark.anyio
    async def test_list_accounts_unauthorized(self, async_client):
        """未认证 → 401。"""
        resp = await async_client.get("/api/v1/accounts")
        assert resp.status_code == 401


class TestStudentMyProfile:
    """GET /students/me — 学生查看自己的 Profile。"""

    @pytest.mark.anyio
    async def test_my_profile_wrong_role(self, async_client, admin_headers):
        """非学生角色访问 /students/me → 403。"""
        resp = await async_client.get(
            "/api/v1/students/me", headers=admin_headers,
        )
        assert resp.status_code == 403
