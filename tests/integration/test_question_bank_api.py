"""Question Bank API 集成测试 — 题库文件夹 CRUD + 题目集管理 + 历年真题。

所有测试使用 conftest fixtures 实现完全隔离。
"""

import pytest


class TestQuestionSetCRUD:
    """题库文件夹 CRUD。"""

    @pytest.mark.anyio
    async def test_create_question_set(self, async_client, teacher_headers):
        """教师可创建题库文件夹。"""
        resp = await async_client.post(
            "/api/v1/question-sets",
            json={"name": "氧化还原专题"},
            headers=teacher_headers,
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["name"] == "氧化还原专题"

    @pytest.mark.anyio
    async def test_list_question_sets(self, async_client, teacher_headers):
        """列出题库文件夹。"""
        resp = await async_client.post(
            "/api/v1/question-sets",
            json={"name": "离子反应专题"},
            headers=teacher_headers,
        )
        assert resp.status_code == 201

        resp = await async_client.get(
            "/api/v1/question-sets", headers=teacher_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1

    @pytest.mark.anyio
    async def test_update_question_set(self, async_client, teacher_headers):
        """更新题库文件夹名称。"""
        resp = await async_client.post(
            "/api/v1/question-sets",
            json={"name": "原始名称"},
            headers=teacher_headers,
        )
        set_id = resp.json()["id"]

        resp = await async_client.patch(
            f"/api/v1/question-sets/{set_id}",
            params={"name": "更新后名称"},
            headers=teacher_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "更新后名称"

    @pytest.mark.anyio
    async def test_delete_question_set(self, async_client, teacher_headers):
        """删除题库文件夹 → 204。"""
        resp = await async_client.post(
            "/api/v1/question-sets",
            json={"name": "待删除"},
            headers=teacher_headers,
        )
        set_id = resp.json()["id"]

        resp = await async_client.delete(
            f"/api/v1/question-sets/{set_id}", headers=teacher_headers,
        )
        assert resp.status_code == 204

    @pytest.mark.anyio
    async def test_get_nonexistent_question_set(self, async_client, teacher_headers):
        """不存在的题库 → 空列表。"""
        resp = await async_client.get(
            "/api/v1/question-sets/99999/items",
            headers=teacher_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["data"] == []


class TestQuestionSetItems:
    """题库题目管理 — 添加/查看。"""

    @pytest.mark.anyio
    async def test_add_item_to_set(self, async_client, teacher_headers):
        """创建题库 → 创建题目 → 添加到题库。"""
        # 创建题库
        resp = await async_client.post(
            "/api/v1/question-sets",
            json={"name": "pH值专题"},
            headers=teacher_headers,
        )
        set_id = resp.json()["id"]

        # 创建题目
        resp = await async_client.post(
            "/api/v1/questions",
            json={
                "content": "pH=2的溶液中，[H+]浓度是多少？",
                "question_type": "calculation",
                "answer": "0.01mol/L",
                "difficulty": "easy",
            },
            headers=teacher_headers,
        )
        qid = resp.json()["id"]

        # 添加到题库
        resp = await async_client.post(
            f"/api/v1/question-sets/{set_id}/items",
            json={"question_set_id": set_id, "question_id": qid, "sort_order": 0},
            headers=teacher_headers,
        )
        assert resp.status_code == 201, resp.text

        # 列出题库题目
        resp = await async_client.get(
            f"/api/v1/question-sets/{set_id}/items",
            headers=teacher_headers,
        )
        assert resp.status_code == 200
        assert len(resp.json()["data"]) >= 1


class TestHistoricalExams:
    """历年真题 — GET /historical-exams。"""

    @pytest.mark.anyio
    async def test_list_historical_exams_empty(self, async_client, teacher_headers):
        """无真题数据时返回空。"""
        resp = await async_client.get(
            "/api/v1/historical-exams", headers=teacher_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert data["total"] >= 0

    @pytest.mark.anyio
    async def test_historical_exams_with_filters(self, async_client, teacher_headers):
        """带过滤条件的历年真题查询。"""
        resp = await async_client.get(
            "/api/v1/historical-exams",
            params={"difficulty": "easy", "knowledge_point": "化学平衡"},
            headers=teacher_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data


class TestQuestionBankRBAC:
    """题库权限测试。"""

    @pytest.mark.anyio
    async def test_student_cannot_create_question_set(self, async_client, student_headers):
        """学生无权创建题库 → 403。"""
        resp = await async_client.post(
            "/api/v1/question-sets",
            json={"name": "越权题库"},
            headers=student_headers,
        )
        assert resp.status_code == 403
