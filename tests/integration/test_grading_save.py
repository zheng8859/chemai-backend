"""8.6: grading save integration tests — 正常保存/学号不存在跳过/重复保存幂等/诊断触发。"""

import pytest

from app.services.grading_service import GradingService
from app.infrastructure.database import get_db


class TestGradingSaveAPI:

    @pytest.mark.anyio
    async def test_save_requires_auth(self, async_client):
        """未认证返回 401/403。"""
        response = await async_client.post("/api/v1/ocr/grading/save", json={
            "task_ids": [1],
        })
        assert response.status_code in (401, 403)

    @pytest.mark.anyio
    async def test_save_student_forbidden(self, async_client, student_headers):
        """学生角色无 ocr:create 权限。"""
        response = await async_client.post(
            "/api/v1/ocr/grading/save",
            json={"task_ids": [1]},
            headers=student_headers,
        )
        assert response.status_code in (401, 403, 422)

    @pytest.mark.anyio
    async def test_save_teacher_success_200(self, async_client, teacher_headers):
        """教师调用返回 200（通过权限检查，内部无已完成 task 则 saved=0）。"""
        response = await async_client.post(
            "/api/v1/ocr/grading/save",
            json={"task_ids": [99999]},  # 不存在的 task
            headers=teacher_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["saved_count"] == 0
        assert "skipped_count" in data

    @pytest.mark.anyio
    async def test_save_empty_task_ids(self, async_client, teacher_headers):
        """空 task_ids 返回 200，saved=0。"""
        response = await async_client.post(
            "/api/v1/ocr/grading/save",
            json={"task_ids": []},
            headers=teacher_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["saved_count"] == 0

    @pytest.mark.anyio
    async def test_save_missing_fields_422(self, async_client, teacher_headers):
        """缺少 task_ids 返回 422。"""
        response = await async_client.post(
            "/api/v1/ocr/grading/save",
            json={},
            headers=teacher_headers,
        )
        assert response.status_code == 422


class TestGradingSaveService:
    """直接测试 GradingService.save_results() 业务逻辑。"""

    @pytest.mark.anyio
    async def test_save_nonexistent_task_skipped(self, db_session):
        """不存在的 task → 跳过并记录原因。"""
        result = await GradingService.save_results(db_session, [99999])
        assert result["saved_count"] == 0
        assert result["skipped_count"] == 1
        assert any("不存在" in s["reason"] for s in result.get("skipped_details", []))

    @pytest.mark.anyio
    async def test_save_task_without_grading_result_skipped(self, db_session):
        """task 存在但无 grading_result → 跳过。"""
        from app.models.ocr import OCRTask
        from app.core.enums import OCRTaskStatus

        task = OCRTask(
            upload_session_id=1,
            teacher_id=1,
            image_path="/path/img.jpg",
            title="未批改任务",
            status=OCRTaskStatus.done,
        )
        db_session.add(task)
        await db_session.commit()
        await db_session.refresh(task)

        result = await GradingService.save_results(db_session, [task.id])
        assert result["saved_count"] == 0
        assert result["skipped_count"] == 1
        assert any("尚未批改" in s["reason"] for s in result.get("skipped_details", []))

    @pytest.mark.anyio
    async def test_save_student_not_found_skipped(self, db_session):
        """学号不在学生表中 → 脏数据保护，跳过。"""
        from app.models.ocr import OCRTask
        from app.core.enums import OCRTaskStatus

        task = OCRTask(
            upload_session_id=1,
            teacher_id=1,
            image_path="/path/img.jpg",
            title="学号不存在任务",
            status=OCRTaskStatus.done,
            ocr_raw_result={"raw_text": "1. C", "confidence": 0.9},
            grading_result={
                "engine": "llm_semantic",
                "total_score": 85.0,
                "questions": [{"q_number": 1, "student_answer": "C", "correct_answer": "C", "is_correct": True, "reason": ""}],
                "needs_review": False,
            },
            student_id_raw="99999999",  # 不在学生表中
            student_name_raw="无名",
        )
        db_session.add(task)
        await db_session.commit()
        await db_session.refresh(task)

        result = await GradingService.save_results(db_session, [task.id])
        assert result["saved_count"] == 0
        assert result["skipped_count"] == 1
        assert any("不在学生表中" in s["reason"] for s in result.get("skipped_details", []))

    @pytest.mark.anyio
    async def test_save_duplicate_idempotent(self, db_session):
        """重复保存 → 幂等，第二次跳过。"""
        from app.models.ocr import OCRTask
        from app.core.enums import OCRTaskStatus

        task = OCRTask(
            upload_session_id=1,
            teacher_id=1,
            image_path="/path/img.jpg",
            title="已确认任务",
            status=OCRTaskStatus.done,
            ocr_raw_result={"raw_text": "1. C", "confidence": 0.9},
            grading_result={
                "engine": "llm_semantic",
                "total_score": 100.0,
                "questions": [{"q_number": 1, "student_answer": "C", "correct_answer": "C", "is_correct": True, "reason": ""}],
                "needs_review": False,
            },
            student_id_raw=None,  # 无学号 = 跳过脏数据检查，仍可保存
            student_name_raw="测试",
            confirmed=False,
        )
        db_session.add(task)
        await db_session.commit()
        await db_session.refresh(task)

        # 第一次保存
        result1 = await GradingService.save_results(db_session, [task.id])
        assert result1["saved_count"] == 1
        await db_session.refresh(task)
        assert task.confirmed is True

        # 第二次保存（幂等）
        result2 = await GradingService.save_results(db_session, [task.id])
        assert result2["saved_count"] == 0
        assert result2["skipped_count"] == 1
        assert any("已确认保存" in s["reason"] for s in result2.get("skipped_details", []))

    @pytest.mark.anyio
    async def test_save_marks_diagnosis_triggered(self, db_session):
        """保存成功 → diagnosis_triggered=True。"""
        from app.models.ocr import OCRTask
        from app.core.enums import OCRTaskStatus

        task = OCRTask(
            upload_session_id=1,
            teacher_id=1,
            image_path="/path/img.jpg",
            title="触发诊断任务",
            status=OCRTaskStatus.done,
            ocr_raw_result={"raw_text": "1. C", "confidence": 0.9},
            grading_result={
                "engine": "llm_semantic",
                "total_score": 90.0,
                "questions": [{"q_number": 1, "student_answer": "C", "correct_answer": "C", "is_correct": True, "reason": ""}],
                "needs_review": False,
            },
            student_id_raw=None,
            student_name_raw="诊断测试",
            confirmed=False,
        )
        db_session.add(task)
        await db_session.commit()
        await db_session.refresh(task)

        result = await GradingService.save_results(db_session, [task.id])
        assert result["saved_count"] == 1
        assert result["diagnosis_triggered"] is True
