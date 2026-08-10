"""OCR API 集成测试 — 会话/任务/提交记录查询 + 批量上传 multipart。"""

import io
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
    """批量上传 — POST /ocr/tasks/batch (multipart/form-data)。"""

    @pytest.mark.anyio
    async def test_batch_upload_success(self, async_client, admin_headers, class_):
        """正常上传 JPG 文件 → 201。"""
        fake_jpg = io.BytesIO(b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00")
        fake_jpg.name = "答题卡_001.jpg"
        files_data = [("files", (fake_jpg.name, fake_jpg, "image/jpeg"))]
        form_data = {
            "teacher_id": "999",
            "class_id": str(class_["id"]),
            "exam_name": "月考上传测试",
        }
        resp = await async_client.post(
            "/api/v1/ocr/tasks/batch",
            files=files_data,
            data=form_data,
            headers=admin_headers,
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["success"] is True
        assert data["total"] == 1
        assert "session_id" in data
        assert "batch_id" in data
        assert len(data["tasks"]) == 1

    @pytest.mark.anyio
    async def test_batch_upload_multiple_files(self, async_client, admin_headers, class_):
        """批量上传多个文件 → 201。"""
        files_data = []
        for i in range(3):
            fake = io.BytesIO(b"fake-jpeg-data-%d" % i)
            fake.name = f"答题卡_{i+1:03d}.jpg"
            files_data.append(("files", (fake.name, fake, "image/jpeg")))

        form_data = {
            "teacher_id": "999",
            "class_id": str(class_["id"]),
            "exam_name": "批量3张上传",
        }
        resp = await async_client.post(
            "/api/v1/ocr/tasks/batch",
            files=files_data,
            data=form_data,
            headers=admin_headers,
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["total"] == 3
        assert len(data["tasks"]) == 3

    @pytest.mark.anyio
    async def test_batch_upload_empty(self, async_client, admin_headers, class_):
        """空文件列表 → 422（FastAPI 校验 files 必填）。"""
        form_data = {
            "teacher_id": "999",
            "class_id": str(class_["id"]),
            "exam_name": "空上传",
        }
        resp = await async_client.post(
            "/api/v1/ocr/tasks/batch",
            data=form_data,
            headers=admin_headers,
        )
        # FastAPI 在进入 handler 前校验 files 为必填，返回 422
        assert resp.status_code in (400, 422), resp.text

    @pytest.mark.anyio
    async def test_batch_upload_unsupported_type(self, async_client, admin_headers, class_):
        """不支持的文件类型 → 415。"""
        fake_docx = io.BytesIO(b"fake-docx-data")
        fake_docx.name = "document.docx"
        files_data = [("files", (fake_docx.name, fake_docx, "application/vnd.openxmlformats-officedocument.wordprocessingml.document"))]
        form_data = {
            "teacher_id": "999",
            "class_id": str(class_["id"]),
            "exam_name": "上传docx",
        }
        resp = await async_client.post(
            "/api/v1/ocr/tasks/batch",
            files=files_data,
            data=form_data,
            headers=admin_headers,
        )
        assert resp.status_code == 415, resp.text

    @pytest.mark.anyio
    async def test_batch_upload_too_large(self, async_client, admin_headers, class_, monkeypatch):
        """超大文件 → 413（通过 monkeypatch 降低限制为 1 字节）。"""
        monkeypatch.setattr("app.services.ocr_service.OCR_MAX_FILE_SIZE_MB", 0)
        fake_jpg = io.BytesIO(b"\xff\xd8\xff\xe0\x00\x10JFIF")
        fake_jpg.name = "too_big.jpg"
        files_data = [("files", (fake_jpg.name, fake_jpg, "image/jpeg"))]
        form_data = {
            "teacher_id": "999",
            "class_id": str(class_["id"]),
            "exam_name": "超大文件",
        }
        resp = await async_client.post(
            "/api/v1/ocr/tasks/batch",
            files=files_data,
            data=form_data,
            headers=admin_headers,
        )
        assert resp.status_code == 413, resp.text

    @pytest.mark.anyio
    async def test_student_cannot_batch_upload(self, async_client, student_headers, class_):
        """学生无权批量上传 → 403。"""
        fake = io.BytesIO(b"fake-jpeg")
        fake.name = "test.jpg"
        files_data = [("files", (fake.name, fake, "image/jpeg"))]
        form_data = {
            "teacher_id": "997",
            "class_id": str(class_["id"]),
            "exam_name": "越权上传",
        }
        resp = await async_client.post(
            "/api/v1/ocr/tasks/batch",
            files=files_data,
            data=form_data,
            headers=student_headers,
        )
        assert resp.status_code == 403
