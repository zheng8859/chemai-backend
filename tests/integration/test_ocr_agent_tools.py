"""OCR Agent 工具集成测试 — query_ocr_progress / grade_answer_sheets / save_grading_results。

覆盖 tasks 4.1–4.3：
- query_ocr_progress 批次查询 / 教师全量 / 全部完成态
- grade_answer_sheets 批改已完成任务、答案来源优先级、空批次不抛异常
- save_grading_results 保存 + 触发诊断、未注册学号跳过计入 skipped_count
"""

from types import SimpleNamespace

import pytest

# ── 触发所有 @register_tool 装饰器 ──
import agent.tools  # noqa: F401
import agent.tools.ocr_progress as ocr_progress
import agent.tools.grading_trigger as grading_trigger
import agent.tools.grading_save as grading_save

from app.models.ocr import OCRTask
from app.core.enums import OCRTaskStatus
from app.services.grading_service import GradingService


@pytest.fixture
def fake_session(db_session, monkeypatch, fake_main_session_cls):
    """让 OCR 三个工具走测试 db_session，而非生产 main_engine。"""
    for mod in (ocr_progress, grading_trigger, grading_save):
        monkeypatch.setattr(mod, "MainSession", fake_main_session_cls(db_session))
    return db_session


async def _make_task(
    db_session, *, teacher_id=1, session_id=1,
    status=OCRTaskStatus.done, **kwargs,
) -> OCRTask:
    """创建测试 OCRTask 并提交。"""
    task = OCRTask(
        upload_session_id=session_id,
        teacher_id=teacher_id,
        image_path="/path/img.jpg",
        title="测试答题卡",
        status=status,
        **kwargs,
    )
    db_session.add(task)
    await db_session.commit()
    await db_session.refresh(task)
    return task


# ═══════════════════════════════════════════════════════════════
# query_ocr_progress — 进度查询
# ═══════════════════════════════════════════════════════════════

class TestQueryOcrProgress:

    @pytest.mark.anyio
    async def test_batch_progress(self, fake_session):
        """批次查询返回各状态数量、百分比与聚合状态。"""
        await _make_task(fake_session, session_id=10, status=OCRTaskStatus.done)
        await _make_task(fake_session, session_id=10, status=OCRTaskStatus.done)
        await _make_task(fake_session, session_id=10, status=OCRTaskStatus.processing)

        result = await ocr_progress.query_ocr_progress(teacher_id=1, session_id=10)
        assert result["total"] == 3
        assert result["done"] == 2
        assert result["processing"] == 1
        assert result["progress_pct"] == 66.7
        assert result["status"] == "processing"

    @pytest.mark.anyio
    async def test_teacher_all_sessions(self, fake_session):
        """不传 session_id → 返回教师全部任务。"""
        await _make_task(fake_session, session_id=10, status=OCRTaskStatus.done)
        await _make_task(fake_session, session_id=20, status=OCRTaskStatus.failed)

        result = await ocr_progress.query_ocr_progress(teacher_id=1)
        assert result["total"] == 2
        assert result["done"] == 1
        assert result["failed"] == 1

    @pytest.mark.anyio
    async def test_all_completed(self, fake_session):
        """全部完成 → progress_pct=100 且 status=completed。"""
        await _make_task(fake_session, session_id=10, status=OCRTaskStatus.done)
        await _make_task(fake_session, session_id=10, status=OCRTaskStatus.done)

        result = await ocr_progress.query_ocr_progress(teacher_id=1, session_id=10)
        assert result["progress_pct"] == 100.0
        assert result["status"] == "completed"


# ═══════════════════════════════════════════════════════════════
# grade_answer_sheets — 批量批改
# ═══════════════════════════════════════════════════════════════

class TestGradeAnswerSheets:

    @pytest.mark.anyio
    async def test_empty_batch_no_exception(self, fake_session):
        """无已完成任务 → 结构化空结果，不抛异常。"""
        result = await grading_trigger.grade_answer_sheets(teacher_id=1, session_id=999)
        assert result["total"] == 0
        assert result["graded"] == 0
        assert result["failed"] == 0

    @pytest.mark.anyio
    async def test_answer_source_teacher_over_paper(self, fake_session):
        """答案来源优先级：教师录入 > 题库匹配。"""
        key = await GradingService.resolve_answer_source(
            fake_session, exam_paper_id=1, teacher_answers={"1": "A"},
        )
        assert key.source_mode == "teacher_input"

    @pytest.mark.anyio
    async def test_answer_source_propagated(self, fake_session):
        """工具透传 answer_source。"""
        result = await grading_trigger.grade_answer_sheets(
            teacher_id=1, session_id=999,
            exam_paper_id=1, teacher_answers={"1": "A"},
        )
        assert result["answer_source"] == "teacher_input"

    @pytest.mark.anyio
    async def test_grades_done_tasks(self, fake_session, monkeypatch):
        """批改 status=done 的任务，返回得分与需复核标记。"""
        task = await _make_task(
            fake_session, session_id=10, status=OCRTaskStatus.done,
            ocr_raw_result={"raw_text": "1. C", "confidence": 0.9},
        )

        async def fake_grade_task(db, task_id, answer_key):
            return SimpleNamespace(error=None, total_score=85.0, needs_review=False)

        monkeypatch.setattr(GradingService, "grade_task", fake_grade_task)

        result = await grading_trigger.grade_answer_sheets(teacher_id=1, session_id=10)
        assert result["total"] == 1
        assert result["graded"] == 1
        assert result["failed"] == 0
        assert result["results"][0]["task_id"] == task.id
        assert result["results"][0]["total_score"] == 85.0


# ═══════════════════════════════════════════════════════════════
# save_grading_results — 保存 + 诊断触发
# ═══════════════════════════════════════════════════════════════

class TestSaveGradingResults:

    @pytest.mark.anyio
    async def test_empty_task_ids(self, fake_session):
        """空 task_ids → saved=0，不抛异常。"""
        result = await grading_save.save_grading_results(teacher_id=1, task_ids=[])
        assert result["saved_count"] == 0
        assert result["skipped_count"] == 0

    @pytest.mark.anyio
    async def test_unregistered_student_skipped(self, fake_session):
        """学号不在学生表中 → 跳过并计入 skipped_count。"""
        task = await _make_task(
            fake_session, session_id=10, status=OCRTaskStatus.done,
            ocr_raw_result={"raw_text": "1. C"},
            grading_result={
                "engine": "llm_semantic", "total_score": 80.0,
                "questions": [{"q_number": 1, "is_correct": True}],
                "needs_review": False,
            },
            student_id_raw="99999999",
            student_name_raw="无名",
        )

        result = await grading_save.save_grading_results(teacher_id=1, task_ids=[task.id])
        assert result["saved_count"] == 0
        assert result["skipped_count"] == 1
        assert result["diagnosis_triggered"] is False

    @pytest.mark.anyio
    async def test_diagnosis_triggered_mapping(self, fake_session, monkeypatch):
        """保存成功 → diagnosis_triggered 透传，且不触发真实管线。"""
        async def fake_save_results(db, task_ids):
            return {"saved_count": 2, "skipped_count": 0, "diagnosis_triggered": True}

        async def fake_pipeline(*args, **kwargs):
            return {"diagnosis": 0, "stats": None, "report": None}

        monkeypatch.setattr(GradingService, "save_results", fake_save_results)
        monkeypatch.setattr(GradingService, "_post_save_pipeline", fake_pipeline)

        result = await grading_save.save_grading_results(teacher_id=1, task_ids=[1, 2])
        assert result["saved_count"] == 2
        assert result["skipped_count"] == 0
        assert result["diagnosis_triggered"] is True
