"""ExamManagementService 服务层测试 — 考试题目关联/发布/导入。

直接调用 ExamManagementService 静态方法，使用 db_session fixture。
"""

import pytest
from datetime import datetime, timezone

from sqlalchemy import select

from app.services.exam_management_service import (
    ExamManagementService, ExamManagementError,
)
from app.models.exam_paper import ExamPaper, ExamPaperQuestion
from app.models.teaching import ExamRecord, Question
from app.models.question_bank import HistoricalExam


# ═══════════════════════════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════════════════════════

async def _create_exam(db, **overrides):
    """创建测试考试记录。"""
    defaults = {
        "class_id": 1,
        "exam_type": "monthly",
        "status": "pending",
        "exam_date": datetime.now(timezone.utc),
    }
    defaults.update(overrides)
    exam = ExamRecord(**defaults)
    db.add(exam)
    await db.commit()
    await db.refresh(exam)
    return exam


async def _create_question(db, **overrides):
    """创建测试题目。"""
    defaults = {
        "content": "测试题目内容",
        "question_type": "choice",
        "options": ["A. 选项1", "B. 选项2", "C. 选项3", "D. 选项4"],
        "answer": "B",
        "analysis": "测试解析",
        "knowledge_point_tags": ["氧化还原"],
        "difficulty": "medium",
    }
    defaults.update(overrides)
    q = Question(**defaults)
    db.add(q)
    await db.commit()
    await db.refresh(q)
    return q


async def _create_historical_exam(db, **overrides):
    """创建测试历年真题。"""
    defaults = {
        "source": "全国卷",
        "year": 2024,
        "difficulty": "medium",
        "content": "历年真题题目内容",
        "answer": "C",
        "analysis": "历年真题解析",
        "knowledge_point_tags": ["电化学"],
    }
    defaults.update(overrides)
    he = HistoricalExam(**defaults)
    db.add(he)
    await db.commit()
    await db.refresh(he)
    return he


# ═══════════════════════════════════════════════════════════════
# add_questions_to_exam — 题目关联（双渠道）
# ═══════════════════════════════════════════════════════════════

class TestAddQuestionsToExam:
    """POST 题目关联 → add_questions_to_exam。"""

    @pytest.mark.anyio
    async def test_nonexistent_exam_raises(self, db_session):
        """考试不存在 → ExamManagementError。"""
        with pytest.raises(ExamManagementError, match="考试不存在"):
            await ExamManagementService.add_questions_to_exam(
                db_session, exam_record_id=99999, question_ids=[1],
            )

    @pytest.mark.anyio
    async def test_add_from_question_table(self, db_session):
        """渠道一：从 Question 表添加已有题目。"""
        exam = await _create_exam(db_session)
        q = await _create_question(db_session)

        result = await ExamManagementService.add_questions_to_exam(
            db_session, exam.id, question_ids=[q.id],
        )

        assert result["added"] == 1
        assert result["from_existing"] == 1
        assert result["from_historical"] == 0

    @pytest.mark.anyio
    async def test_add_from_historical_exam(self, db_session):
        """渠道二：从 HistoricalExam 复制到 Question 再关联。"""
        exam = await _create_exam(db_session)
        he = await _create_historical_exam(db_session)

        # historical exam ID may overlap with Question IDs, so use source_hint
        result = await ExamManagementService.add_questions_to_exam(
            db_session, exam.id, question_ids=[he.id],
            source_hint="historical",
        )

        assert result["added"] == 1
        assert result["from_historical"] == 1
        assert result["from_existing"] == 0

    @pytest.mark.anyio
    async def test_auto_creates_exam_paper(self, db_session):
        """考试无 ExamPaper 时自动创建。"""
        exam = await _create_exam(db_session)  # no exam_paper_id
        q = await _create_question(db_session)

        await ExamManagementService.add_questions_to_exam(
            db_session, exam.id, question_ids=[q.id],
        )

        await db_session.refresh(exam)
        assert exam.exam_paper_id is not None

    @pytest.mark.anyio
    async def test_reuses_existing_exam_paper(self, db_session):
        """已有 ExamPaper 时复用，不重复创建。"""
        paper = ExamPaper(name="已有试卷", teacher_id=1, status="draft")
        db_session.add(paper)
        await db_session.flush()
        exam = await _create_exam(db_session, exam_paper_id=paper.id)
        q = await _create_question(db_session)

        await ExamManagementService.add_questions_to_exam(
            db_session, exam.id, question_ids=[q.id],
        )

        await db_session.refresh(exam)
        assert exam.exam_paper_id == paper.id

    @pytest.mark.anyio
    async def test_deduplicate_questions(self, db_session):
        """重复添加同一题目 → 不创建重复 ExamPaperQuestion 关联。"""
        exam = await _create_exam(db_session)
        q = await _create_question(db_session)

        # 第一次添加
        await ExamManagementService.add_questions_to_exam(
            db_session, exam.id, question_ids=[q.id],
        )
        # 第二次添加同一题目
        await ExamManagementService.add_questions_to_exam(
            db_session, exam.id, question_ids=[q.id],
        )

        # 验证 ExamPaperQuestion 只有一条（不重复）
        result = await db_session.execute(
            select(ExamPaperQuestion).where(
                ExamPaperQuestion.exam_paper_id == exam.exam_paper_id,
                ExamPaperQuestion.question_id == q.id,
            )
        )
        epqs = result.scalars().all()
        assert len(epqs) == 1

    @pytest.mark.anyio
    async def test_skip_nonexistent_ids(self, db_session):
        """不存在的题目 ID → 跳过，不报错。"""
        exam = await _create_exam(db_session)
        # 使用不存在的 ID（既不来自 Question 也不来自 HistoricalExam）
        result = await ExamManagementService.add_questions_to_exam(
            db_session, exam.id, question_ids=[99999],
        )

        assert result["added"] == 0

    @pytest.mark.anyio
    async def test_fallback_to_historical_when_not_in_question(self, db_session):
        """Question 表查不到时 fallback 到 HistoricalExam。"""
        exam = await _create_exam(db_session)
        he = await _create_historical_exam(db_session)

        # source_hint 为空 → 先查 Question（找不到），再 fallback 到 HistoricalExam
        result = await ExamManagementService.add_questions_to_exam(
            db_session, exam.id, question_ids=[he.id],
        )

        assert result["added"] == 1
        assert result["from_historical"] == 1


# ═══════════════════════════════════════════════════════════════
# get_exam_questions — 获取考试题目列表
# ═══════════════════════════════════════════════════════════════

class TestGetExamQuestions:
    """GET 考试题目列表 → get_exam_questions。"""

    @pytest.mark.anyio
    async def test_nonexistent_exam_returns_empty(self, db_session):
        """考试不存在 → 返回空列表。"""
        result = await ExamManagementService.get_exam_questions(db_session, 99999)
        assert result == []

    @pytest.mark.anyio
    async def test_exam_without_paper_returns_empty(self, db_session):
        """考试无试卷关联 → 返回空列表。"""
        exam = await _create_exam(db_session)
        result = await ExamManagementService.get_exam_questions(db_session, exam.id)
        assert result == []

    @pytest.mark.anyio
    async def test_returns_questions_with_details(self, db_session):
        """有题目时返回完整题目信息。"""
        exam = await _create_exam(db_session)
        q = await _create_question(db_session)
        await ExamManagementService.add_questions_to_exam(
            db_session, exam.id, question_ids=[q.id],
        )

        result = await ExamManagementService.get_exam_questions(db_session, exam.id)
        assert len(result) == 1
        assert result[0]["content"] == "测试题目内容"
        assert result[0]["answer"] == "B"
        assert result[0]["question_type"] == "choice"
        assert "sort_order" in result[0]

    @pytest.mark.anyio
    async def test_questions_sorted_by_sort_order(self, db_session):
        """在同一次调用中添加多道题目，sort_order 递增。"""
        exam = await _create_exam(db_session)
        q1 = await _create_question(db_session, content="题目1")
        q2 = await _create_question(db_session, content="题目2")

        # 同一次调用添加多道题 → sort_order 递增
        await ExamManagementService.add_questions_to_exam(
            db_session, exam.id, question_ids=[q1.id, q2.id],
        )

        result = await ExamManagementService.get_exam_questions(db_session, exam.id)
        assert len(result) == 2
        assert result[0]["sort_order"] < result[1]["sort_order"]


# ═══════════════════════════════════════════════════════════════
# remove_question_from_exam — 移除题目
# ═══════════════════════════════════════════════════════════════

class TestRemoveQuestionFromExam:
    """DELETE 题目移除 → remove_question_from_exam。"""

    @pytest.mark.anyio
    async def test_nonexistent_exam_raises(self, db_session):
        """考试不存在 → ExamManagementError。"""
        with pytest.raises(ExamManagementError, match="考试不存在"):
            await ExamManagementService.remove_question_from_exam(
                db_session, 99999, question_id=1,
            )

    @pytest.mark.anyio
    async def test_exam_without_paper_raises(self, db_session):
        """考试无试卷 → ExamManagementError。"""
        exam = await _create_exam(db_session)
        with pytest.raises(ExamManagementError, match="考试不存在"):
            await ExamManagementService.remove_question_from_exam(
                db_session, exam.id, question_id=1,
            )

    @pytest.mark.anyio
    async def test_remove_existing_question(self, db_session):
        """移除已关联的题目。"""
        exam = await _create_exam(db_session)
        q = await _create_question(db_session)
        await ExamManagementService.add_questions_to_exam(
            db_session, exam.id, question_ids=[q.id],
        )

        await ExamManagementService.remove_question_from_exam(
            db_session, exam.id, question_id=q.id,
        )

        # 验证已移除
        result = await ExamManagementService.get_exam_questions(db_session, exam.id)
        assert len(result) == 0

    @pytest.mark.anyio
    async def test_remove_nonexistent_question_no_error(self, db_session):
        """移除不存在的题目 → 不报错（幂等）。"""
        exam = await _create_exam(db_session)
        q = await _create_question(db_session)
        await ExamManagementService.add_questions_to_exam(
            db_session, exam.id, question_ids=[q.id],
        )

        # 移除不相关的题目 ID → 不报错
        await ExamManagementService.remove_question_from_exam(
            db_session, exam.id, question_id=99999,
        )
        # 原有题目仍在
        result = await ExamManagementService.get_exam_questions(db_session, exam.id)
        assert len(result) == 1


# ═══════════════════════════════════════════════════════════════
# publish_exam — 发布考试
# ═══════════════════════════════════════════════════════════════

class TestPublishExam:
    """POST 发布考试 → publish_exam。"""

    @pytest.mark.anyio
    async def test_nonexistent_exam_raises(self, db_session):
        """考试不存在 → ExamManagementError。"""
        with pytest.raises(ExamManagementError, match="考试不存在"):
            await ExamManagementService.publish_exam(db_session, 99999)

    @pytest.mark.anyio
    async def test_publish_without_questions_raises(self, db_session):
        """考试无题目 → ExamManagementError (VALIDATION_ERROR)。"""
        exam = await _create_exam(db_session)
        with pytest.raises(ExamManagementError, match="至少需要1道题"):
            await ExamManagementService.publish_exam(db_session, exam.id)

    @pytest.mark.anyio
    async def test_publish_success(self, db_session):
        """有题目时发布成功。"""
        exam = await _create_exam(db_session)
        q = await _create_question(db_session)
        await ExamManagementService.add_questions_to_exam(
            db_session, exam.id, question_ids=[q.id],
        )

        result = await ExamManagementService.publish_exam(db_session, exam.id)

        assert result["success"] is True
        assert result["status"] == "in_progress"
        assert result["question_count"] == 1
        assert "published_at" in result

        await db_session.refresh(exam)
        assert exam.status == "in_progress"


# ═══════════════════════════════════════════════════════════════
# finalize_exam — 完成考试
# ═══════════════════════════════════════════════════════════════

class TestFinalizeExam:
    """POST 完成考试 → finalize_exam。"""

    @pytest.mark.anyio
    async def test_nonexistent_exam_raises(self, db_session):
        """考试不存在 → ExamManagementError。"""
        with pytest.raises(ExamManagementError, match="考试不存在"):
            await ExamManagementService.finalize_exam(db_session, 99999)

    @pytest.mark.anyio
    async def test_finalize_success(self, db_session):
        """完成考试成功。"""
        exam = await _create_exam(db_session, participant_count=30)
        result = await ExamManagementService.finalize_exam(db_session, exam.id)

        assert result["success"] is True
        assert result["status"] == "completed"
        assert result["participant_count"] == 30

        await db_session.refresh(exam)
        assert exam.status == "completed"


# ═══════════════════════════════════════════════════════════════
# import_questions — 批量导入题目
# ═══════════════════════════════════════════════════════════════

class TestImportQuestions:
    """POST 批量导入 → import_questions。"""

    @pytest.mark.anyio
    async def test_import_empty_list(self, db_session):
        """空列表导入 → 返回空。"""
        result = await ExamManagementService.import_questions(db_session, [])
        assert result == []

    @pytest.mark.anyio
    async def test_import_single_question(self, db_session):
        """导入单道题目。"""
        result = await ExamManagementService.import_questions(
            db_session,
            [{
                "content": "手动录入的题目",
                "question_type": "choice",
                "options": ["A", "B", "C", "D"],
                "answer": "A",
                "difficulty": "easy",
            }],
        )

        assert len(result) == 1
        assert result[0].content == "手动录入的题目"
        assert result[0].source == "manual"

    @pytest.mark.anyio
    async def test_import_multiple_questions(self, db_session):
        """批量导入多道题目。"""
        result = await ExamManagementService.import_questions(
            db_session,
            [
                {"content": "题目1", "question_type": "choice", "answer": "A"},
                {"content": "题目2", "question_type": "fill_blank", "answer": "B"},
                {"content": "题目3", "question_type": "calculation", "answer": "3.14"},
            ],
        )

        assert len(result) == 3
        assert result[0].source == "manual"

    @pytest.mark.anyio
    async def test_import_with_defaults(self, db_session):
        """缺字段时使用默认值。"""
        result = await ExamManagementService.import_questions(
            db_session,
            [{"content": "最少字段", "answer": "X"}],
        )

        assert len(result) == 1
        assert result[0].question_type == "choice"  # 默认
        assert result[0].difficulty == "medium"      # 默认
        assert result[0].source == "manual"          # 始终 manual
