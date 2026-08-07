"""OCR API 集成测试 — 会话/任务/提交记录查询 + 批量上传 stub。

所有测试使用 conftest fixtures 实现完全隔离。
"""

import pytest


class TestOCRSessions:
    """上传会话 — GET /ocr/sessions。"""

    @pytest.mark.anyio
    async def test_list_sessions_empty(self, async_client, admin_headers):
        """无会话数据时返回空分页。"""
        resp = await async_client.get(
            "/api/v1/ocr/sessions", headers=admin_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert data["total"] >= 0

    @pytest.mark.anyio
    async def test_get_nonexistent_session(self, async_client, admin_headers):
        """获取不存在会话 → 404。"""
        resp = await async_client.get(
            "/api/v1/ocr/sessions/99999", headers=admin_headers,
        )
        assert resp.status_code == 404

    @pytest.mark.anyio
    async def test_list_tasks_by_session_nonexistent(self, async_client, admin_headers):
        """不存在的会话任务列表 → 空。"""
        resp = await async_client.get(
            "/api/v1/ocr/sessions/99999/tasks",
            headers=admin_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 0


class TestOCRTasks:
    """OCR 任务 — GET /ocr/tasks/{id}。"""

    @pytest.mark.anyio
    async def test_get_nonexistent_task(self, async_client, admin_headers):
        """获取不存在任务 → 404。"""
        resp = await async_client.get(
            "/api/v1/ocr/tasks/99999", headers=admin_headers,
        )
        assert resp.status_code == 404


class TestOCRSubmissions:
    """答题卡提交 — GET /ocr/submissions。"""

    @pytest.mark.anyio
    async def test_list_submissions_empty(self, async_client, admin_headers):
        """无提交数据时返回空分页。"""
        resp = await async_client.get(
            "/api/v1/ocr/submissions",
            params={"exam_id": 1},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data

    @pytest.mark.anyio
    async def test_get_nonexistent_submission(self, async_client, admin_headers):
        """获取不存在提交 → 404。"""
        resp = await async_client.get(
            "/api/v1/ocr/submissions/99999", headers=admin_headers,
        )
        assert resp.status_code == 404


class TestOCRBatchUpload:
    """批量上传 — POST /ocr/tasks/batch。"""

    @pytest.mark.anyio
    async def test_batch_upload_stub(self, async_client, admin_headers, class_):
        """批量上传 stub → 201。"""
        resp = await async_client.post(
            "/api/v1/ocr/tasks/batch",
            json={
                "teacher_id": 999,
                "class_id": class_["id"],
                "exam_name": "月考上传",
            },
            headers=admin_headers,
        )
        assert resp.status_code == 201, resp.text

    @pytest.mark.anyio
    async def test_student_cannot_batch_upload(self, async_client, student_headers, class_):
        """学生无权批量上传 → 403。"""
        resp = await async_client.post(
            "/api/v1/ocr/tasks/batch",
            json={
                "teacher_id": 997,
                "class_id": class_["id"],
                "exam_name": "越权上传",
            },
            headers=student_headers,
        )
        assert resp.status_code == 403
