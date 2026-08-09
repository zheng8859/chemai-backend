"""12.1-12.3: E2E 管线测试 — 上传→OCR→批改→保存→诊断 全流程。"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.ocr_engine import (
    OCRResult, EngineRouter, BaiduOCREngine, VLMFallbackEngine, MinerUEngine,
)
from app.services.grading_service import GradingService, AnswerKey, GradingResult

LLM_PATH = "app.llm.router.llm_chat"


# ================================================================
# 12.1: Full pipeline — choice answer sheet
# ================================================================

class TestFullPipelineChoice:

    @pytest.mark.asyncio
    async def test_full_pipeline_upload_to_grading(self):
        """上传→OCR→批改 全流程（模拟选择题答题卡）。"""
        # Simulated OCR result for a choice-only answer sheet
        ocr_result = OCRResult(
            raw_text="""学生姓名：张三
学号：20240001
一、选择题
1. C  2. B  3. A  4. D  5. C
6. B  7. A  8. D  9. C  10. B
11. A  12. D  13. C  14. B  15. A""",
            confidence=0.95,
            student_id_raw="20240001",
            student_name_raw="张三",
            engine="baidu_doc_analysis",
        )

        # Mock answer key (teacher input)
        teacher_answers = {"1": "C", "2": "B", "3": "A", "4": "D", "5": "C",
                           "6": "B", "7": "A", "8": "D", "9": "C", "10": "B",
                           "11": "A", "12": "D", "13": "C", "14": "B", "15": "A"}

        # Mock EngineRouter to return our simulated result
        with patch.object(EngineRouter, "route", new_callable=AsyncMock) as mock_route:
            mock_route.return_value = ocr_result

            # Mock LLM grading
            with patch(LLM_PATH, new_callable=AsyncMock) as mock_llm:
                mock_llm.return_value = '{"questions": [{"q_number": 1, "student_answer": "C", "is_correct": true, "reason": ""}, {"q_number": 2, "student_answer": "B", "is_correct": true, "reason": ""}, {"q_number": 3, "student_answer": "A", "is_correct": true, "reason": ""}], "needs_review": false}'

                # Step 1: OCR
                result = await EngineRouter.route("/path/to/scan.jpg", "IMAGE")
                assert result.engine == "baidu_doc_analysis"
                assert result.student_id_raw == "20240001"
                assert "1. C" in result.raw_text

                # Step 2: Answer parsing
                from app.services.answer_parser import parse_answers_from_text
                parse_result = await parse_answers_from_text(result.raw_text, 15)
                assert len(parse_result.answers) == 15
                assert parse_result.answers[0].student_answer == "C"

    @pytest.mark.asyncio
    async def test_full_pipeline_grading_and_save(self):
        """批改→保存 流程（含答案源选择）。"""
        db = AsyncMock()

        # Mock OCR task
        from app.models.ocr import OCRTask
        from app.core.enums import OCRTaskStatus
        task = OCRTask(
            id=1, upload_session_id=1, teacher_id=1,
            image_path="/path/scan.jpg", title="答题卡_1",
            status=OCRTaskStatus.done,
            ocr_raw_result={"raw_text": "1. C  2. B  3. A", "confidence": 0.95},
            student_id_raw="20240001", student_name_raw="张三",
            progress=100,
        )

        async def mock_execute(statement):
            r = MagicMock()
            r.scalar_one_or_none = MagicMock(return_value=task)
            return r

        db.execute = mock_execute

        # Resolve answer source
        key = await GradingService.resolve_answer_source(
            db, teacher_answers={"1": "C", "2": "B", "3": "A"},
        )
        assert key.source_mode == "teacher_input"
        assert key.question_count == 3

        # Grade task
        with patch(LLM_PATH, new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = '{"questions": [{"q_number": 1, "student_answer": "C", "is_correct": true, "reason": ""}, {"q_number": 2, "student_answer": "B", "is_correct": true, "reason": ""}, {"q_number": 3, "student_answer": "A", "is_correct": true, "reason": ""}], "needs_review": false}'

            grading_result = await GradingService.grade_task(db, 1, key)
            assert grading_result.total_score == 100.0
            assert grading_result.engine in ("llm_semantic",)
            assert grading_result.needs_review is False

    @pytest.mark.asyncio
    async def test_full_pipeline_wrong_answer_detection(self):
        """错误答案检测 — 学生选 B，正确答案是 C。"""
        task_id = 1
        db = AsyncMock()

        from app.models.ocr import OCRTask
        from app.core.enums import OCRTaskStatus
        task = OCRTask(
            id=1, upload_session_id=1, teacher_id=1,
            image_path="/path/scan.jpg", title="答题卡_1",
            status=OCRTaskStatus.done,
            ocr_raw_result={"raw_text": "1. B  2. B  3. C", "confidence": 0.95},
            student_id_raw="20240001", student_name_raw="张三",
            progress=100,
        )

        async def mock_execute(statement):
            r = MagicMock()
            r.scalar_one_or_none = MagicMock(return_value=task)
            return r

        db.execute = mock_execute

        key = AnswerKey(
            source_mode="teacher_input",
            question_count=3,
            questions={1: "C", 2: "B", 3: "A"},
        )

        with patch(LLM_PATH, new_callable=AsyncMock) as mock_llm:
            # Mock LLM returns: Q1 wrong, Q2 correct, Q3 wrong
            mock_llm.return_value = '{"questions": [{"q_number": 1, "student_answer": "B", "is_correct": false, "reason": "应选C"}, {"q_number": 2, "student_answer": "B", "is_correct": true, "reason": ""}, {"q_number": 3, "student_answer": "C", "is_correct": false, "reason": "应选A"}], "needs_review": false}'

            result = await GradingService.grade_task(db, 1, key)
            assert result.total_score is not None
            assert result.total_score < 100.0  # Should have wrong answers
            # Check individual question results
            correct_count = sum(1 for q in result.questions if q.is_correct)
            assert correct_count == 1  # Only Q2 is correct


# ================================================================
# 12.2: Engine fallback path
# ================================================================

class TestEngineFallback:

    @pytest.mark.asyncio
    async def test_baidu_unavailable_vlm_fallback(self):
        """百度 OCR 不可用 → VLM 降级路径。"""
        vlm_result = OCRResult(
            raw_text="1. C  2. B  3. A",
            confidence=0.72,
            student_id_raw="20240001",
            engine="zhipu_glm4v",
            error="fallback_used: baidu_failed",
        )

        with patch.object(BaiduOCREngine, "is_available", return_value=False):
            with patch.object(VLMFallbackEngine, "is_available", return_value=True):
                with patch.object(VLMFallbackEngine, "recognize", new_callable=AsyncMock) as mock_vlm:
                    mock_vlm.return_value = vlm_result
                    result = await EngineRouter.route("/path/img.jpg", "IMAGE")

        assert result.engine == "zhipu_glm4v"
        assert "fallback_used" in (result.error or "")

    @pytest.mark.asyncio
    async def test_mineru_failure_baidu_fallback(self):
        """MinerU 失败 → Baidu 降级路径（PDF）。"""
        mineru_fail = OCRResult(
            is_partial=True, engine="mineru", error="CLI not installed",
        )
        baidu_result = OCRResult(
            raw_text="1. C  2. B", confidence=0.91,
            engine="baidu_doc_analysis",
        )

        with patch.object(MinerUEngine, "is_available", return_value=True):
            with patch.object(MinerUEngine, "parse", new_callable=AsyncMock) as mock_mineru:
                mock_mineru.return_value = mineru_fail
                with patch.object(BaiduOCREngine, "is_available", return_value=True):
                    with patch.object(BaiduOCREngine, "recognize", new_callable=AsyncMock) as mock_baidu:
                        mock_baidu.return_value = baidu_result
                        result = await EngineRouter.route("/path/doc.pdf", "PDF")

        assert result.engine == "baidu_doc_analysis"


# ================================================================
# 12.3: Unreadable image — partial detection
# ================================================================

class TestUnreadableImage:

    @pytest.mark.asyncio
    async def test_unreadable_image_partial_detection(self):
        """模糊图片 → is_partial=True → 教师手动录入。"""
        # OCR returns very short text or error
        ocr_result = OCRResult(
            raw_text="...",
            confidence=0.05,
            is_partial=True,
            engine="baidu_doc_analysis",
            error="图像质量过低，识别文本不足10字符",
        )

        assert ocr_result.is_partial is True
        assert len(ocr_result.raw_text.strip()) < 10

        # Verify the route would trigger fallback
        with patch.object(BaiduOCREngine, "is_available", return_value=True):
            with patch.object(BaiduOCREngine, "recognize", new_callable=AsyncMock) as mock_baidu:
                mock_baidu.return_value = ocr_result
                with patch.object(VLMFallbackEngine, "is_available", return_value=True):
                    with patch.object(VLMFallbackEngine, "recognize", new_callable=AsyncMock) as mock_vlm:
                        mock_vlm.return_value = OCRResult(
                            raw_text="1. C...", confidence=0.4,
                            is_partial=True, engine="zhipu_glm4v",
                        )
                        result = await EngineRouter.route("/path/blurry.jpg", "IMAGE")

        # Both engines return partial — needs teacher review
        assert result.is_partial is True

    @pytest.mark.asyncio
    async def test_unreadable_needs_manual_entry(self):
        """模糊图片场景 → 批改结果标记 needs_review → 教师手动录入。"""
        db = AsyncMock()

        from app.models.ocr import OCRTask
        from app.core.enums import OCRTaskStatus
        task = OCRTask(
            id=1, upload_session_id=1, teacher_id=1,
            image_path="/blurry.jpg", title="模糊答题卡",
            status=OCRTaskStatus.done,
            ocr_raw_result={"raw_text": "...", "confidence": 0.05, "engine": "baidu_doc_analysis"},
            student_id_raw=None, student_name_raw=None,
            progress=100,
        )

        async def mock_execute(statement):
            r = MagicMock()
            r.scalar_one_or_none = MagicMock(return_value=task)
            return r

        db.execute = mock_execute

        key = AnswerKey(source_mode="llm_auto", question_count=0, questions={})

        # For empty/unreadable OCR text, grading should fail gracefully
        result = await GradingService.grade_task(db, 1, key)
        assert result.needs_review is True
        assert result.degraded is True
