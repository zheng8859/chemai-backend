"""OCRService 服务层测试 — 上传会话/任务/提交记录 + 批量上传。

直接调用 OCRService 静态方法，使用 db_session fixture。
"""

import pytest

from sqlalchemy import select

from app.services.ocr_service import OCRService, OCRError
from app.models.ocr import UploadSession, OCRTask, StudentSubmission


# ═══════════════════════════════════════════════════════════════
# Upload Sessions
# ═══════════════════════════════════════════════════════════════

class TestCreateSession:
    """POST /ocr/sessions → create_upload_session。"""

    @pytest.mark.anyio
    async def test_create_session(self, db_session):
        """创建上传会话。"""
        result = await OCRService.create_upload_session(db_session, teacher_id=1)

        assert result.teacher_id == 1
        assert result.id is not None


class TestGetSession:
    """GET /ocr/sessions/{id} → get_session。"""

    @pytest.mark.anyio
    async def test_nonexistent_raises(self, db_session):
        """会话不存在 → OCRError。"""
        with pytest.raises(OCRError, match="上传会话不存在"):
            await OCRService.get_session(db_session, 99999)

    @pytest.mark.anyio
    async def test_get_existing(self, db_session):
        """获取已创建的会话。"""
        s = UploadSession(teacher_id=1)
        db_session.add(s)
        await db_session.commit()
        await db_session.refresh(s)

        result = await OCRService.get_session(db_session, s.id)
        assert result.id == s.id
        assert result.teacher_id == 1


class TestListSessions:
    """GET /ocr/sessions → list_sessions_by_teacher。"""

    @pytest.mark.anyio
    async def test_empty(self, db_session):
        """无会话数据时返回空。"""
        items, total = await OCRService.list_sessions_by_teacher(db_session, teacher_id=1)
        assert total == 0
        assert items == []

    @pytest.mark.anyio
    async def test_with_data(self, db_session):
        """有会话数据时分页返回。"""
        for i in range(2):
            db_session.add(UploadSession(teacher_id=1))
        db_session.add(UploadSession(teacher_id=2))  # 其他教师
        await db_session.commit()

        items, total = await OCRService.list_sessions_by_teacher(db_session, teacher_id=1)
        assert total == 2
        assert len(items) == 2


# ═══════════════════════════════════════════════════════════════
# OCR Tasks
# ═══════════════════════════════════════════════════════════════

class TestListTasks:
    """GET /ocr/tasks → list_tasks_by_session。"""

    @pytest.mark.anyio
    async def test_empty(self, db_session):
        """无任务时返回空。"""
        items, total = await OCRService.list_tasks_by_session(db_session, session_id=1)
        assert total == 0
        assert items == []

    @pytest.mark.anyio
    async def test_with_data(self, db_session):
        """有任务时返回。"""
        s = UploadSession(teacher_id=1)
        db_session.add(s)
        await db_session.flush()
        db_session.add(OCRTask(upload_session_id=s.id, teacher_id=1, image_path="", title="task1"))
        db_session.add(OCRTask(upload_session_id=s.id, teacher_id=1, image_path="", title="task2"))
        await db_session.commit()

        items, total = await OCRService.list_tasks_by_session(db_session, session_id=s.id)
        assert total == 2
        assert len(items) == 2


class TestGetTask:
    """GET /ocr/tasks/{id} → get_task。"""

    @pytest.mark.anyio
    async def test_nonexistent_raises(self, db_session):
        """任务不存在 → OCRError。"""
        with pytest.raises(OCRError, match="OCR 任务不存在"):
            await OCRService.get_task(db_session, 99999)

    @pytest.mark.anyio
    async def test_get_existing(self, db_session):
        """获取已创建任务。"""
        s = UploadSession(teacher_id=1)
        db_session.add(s)
        await db_session.flush()
        t = OCRTask(upload_session_id=s.id, teacher_id=1, image_path="", title="test_task")
        db_session.add(t)
        await db_session.commit()
        await db_session.refresh(t)

        result = await OCRService.get_task(db_session, t.id)
        assert result.id == t.id


# ═══════════════════════════════════════════════════════════════
# Student Submissions
# ═══════════════════════════════════════════════════════════════

class TestListSubmissions:
    """GET /ocr/submissions → list_submissions_by_exam。"""

    @pytest.mark.anyio
    async def test_empty(self, db_session):
        """无提交记录时返回空。"""
        items, total = await OCRService.list_submissions_by_exam(db_session, exam_id=1)
        assert total == 0
        assert items == []

    @pytest.mark.anyio
    async def test_with_data(self, db_session):
        """有提交记录时返回。"""
        db_session.add(StudentSubmission(
            exam_record_id=1, student_id=1,
            class_id=1, original_image="test1.png",
        ))
        db_session.add(StudentSubmission(
            exam_record_id=1, student_id=2,
            class_id=1, original_image="test2.png",
        ))
        await db_session.commit()

        items, total = await OCRService.list_submissions_by_exam(db_session, exam_id=1)
        assert total == 2
        assert len(items) == 2


class TestGetSubmission:
    """GET /ocr/submissions/{id} → get_submission。"""

    @pytest.mark.anyio
    async def test_nonexistent_raises(self, db_session):
        """提交记录不存在 → OCRError。"""
        with pytest.raises(OCRError, match="提交记录不存在"):
            await OCRService.get_submission(db_session, 99999)

    @pytest.mark.anyio
    async def test_get_existing(self, db_session):
        """获取已创建的提交记录。"""
        sub = StudentSubmission(
            exam_record_id=1, student_id=1,
            class_id=1, original_image="test.png",
        )
        db_session.add(sub)
        await db_session.commit()
        await db_session.refresh(sub)

        result = await OCRService.get_submission(db_session, sub.id)
        assert result.id == sub.id


# ═══════════════════════════════════════════════════════════════
# Batch Upload
# ═══════════════════════════════════════════════════════════════

class TestBatchUpload:
    """POST /ocr/tasks/batch → batch_upload_stub。"""

    @pytest.mark.anyio
    async def test_batch_upload(self, db_session):
        """Stub 批量上传创建会话+占位任务。"""
        result = await OCRService.batch_upload_stub(
            db_session, teacher_id=1, class_id=1, exam_name="月考",
        )

        assert result["success"] is True
        assert result["total"] == 3
        assert len(result["tasks"]) == 3
        assert "batch_id" in result
