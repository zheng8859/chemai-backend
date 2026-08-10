"""QuestionBankService 服务层测试 — 题库文件夹/题目集/历年真题。

直接调用 QuestionBankService 静态方法，使用 db_session fixture。
"""

import pytest

from sqlalchemy import select

from app.services.question_bank_service import QuestionBankService, QuestionBankError
from app.models.question_bank import QuestionSet, QuestionSetItem, HistoricalExam
from app.models.teaching import Question
from app.schemas.question_bank import (
    QuestionSetCreate, QuestionSetItemAdd,
)


# ═══════════════════════════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════════════════════════

async def _create_question(db, **overrides):
    """创建测试题目。"""
    defaults = {
        "content": "测试题目",
        "question_type": "choice",
        "options": ["A", "B", "C", "D"],
        "answer": "B",
        "difficulty": "medium",
    }
    defaults.update(overrides)
    q = Question(**defaults)
    db.add(q)
    await db.commit()
    await db.refresh(q)
    return q


# ═══════════════════════════════════════════════════════════════
# QuestionSet CRUD
# ═══════════════════════════════════════════════════════════════

class TestQuestionSetCreate:
    """POST /question-sets → create_question_set。"""

    @pytest.mark.anyio
    async def test_create(self, db_session):
        """创建题库文件夹。"""
        result = await QuestionBankService.create_question_set(
            db_session, QuestionSetCreate(name="氧化还原专题", teacher_id=1),
        )

        assert result.name == "氧化还原专题"
        assert result.id is not None


class TestQuestionSetList:
    """GET /question-sets → list_question_sets。"""

    @pytest.mark.anyio
    async def test_empty(self, db_session):
        """无题库时返回空。"""
        items, total = await QuestionBankService.list_question_sets(db_session)
        assert total == 0
        assert items == []

    @pytest.mark.anyio
    async def test_with_data(self, db_session):
        """有题库时分页返回。"""
        for name in ["专题A", "专题B"]:
            db_session.add(QuestionSet(name=name, teacher_id=1))
        await db_session.commit()

        items, total = await QuestionBankService.list_question_sets(db_session)
        assert total == 2
        assert len(items) == 2

    @pytest.mark.anyio
    async def test_filter_by_teacher(self, db_session):
        """按教师过滤。"""
        db_session.add(QuestionSet(name="我的", teacher_id=1))
        db_session.add(QuestionSet(name="别人的", teacher_id=2))
        await db_session.commit()

        items, total = await QuestionBankService.list_question_sets(db_session, teacher_id=1)
        assert total == 1


class TestQuestionSetUpdate:
    """PATCH /question-sets/{id} → update_question_set。"""

    @pytest.mark.anyio
    async def test_nonexistent_raises(self, db_session):
        """不存在的题库 → QuestionBankError。"""
        with pytest.raises(QuestionBankError, match="题库不存在"):
            await QuestionBankService.update_question_set(db_session, 99999, name="新名称")

    @pytest.mark.anyio
    async def test_update_name(self, db_session):
        """更新题库名称。"""
        qs = QuestionSet(name="原始名称", teacher_id=1)
        db_session.add(qs)
        await db_session.commit()
        await db_session.refresh(qs)

        result = await QuestionBankService.update_question_set(
            db_session, qs.id, name="新名称",
        )
        assert result.name == "新名称"


class TestQuestionSetDelete:
    """DELETE /question-sets/{id} → delete_question_set。"""

    @pytest.mark.anyio
    async def test_nonexistent_raises(self, db_session):
        """不存在的题库 → QuestionBankError。"""
        with pytest.raises(QuestionBankError, match="题库不存在"):
            await QuestionBankService.delete_question_set(db_session, 99999)

    @pytest.mark.anyio
    async def test_system_set_cannot_delete(self, db_session):
        """系统预设文件夹不可删除。"""
        qs = QuestionSet(name="系统题库", teacher_id=1, is_system=True)
        db_session.add(qs)
        await db_session.commit()
        await db_session.refresh(qs)

        with pytest.raises(QuestionBankError, match="系统预设文件夹不可删除"):
            await QuestionBankService.delete_question_set(db_session, qs.id)

    @pytest.mark.anyio
    async def test_delete_normal_set(self, db_session):
        """删除普通题库。"""
        qs = QuestionSet(name="待删除", teacher_id=1)
        db_session.add(qs)
        await db_session.commit()
        await db_session.refresh(qs)

        await QuestionBankService.delete_question_set(db_session, qs.id)

        # 验证已删除
        result = await db_session.execute(
            select(QuestionSet).where(QuestionSet.id == qs.id)
        )
        assert result.scalar_one_or_none() is None


# ═══════════════════════════════════════════════════════════════
# QuestionSet Items
# ═══════════════════════════════════════════════════════════════

class TestItemAdd:
    """POST /question-sets/{id}/items → add_item。"""

    @pytest.mark.anyio
    async def test_add_item(self, db_session):
        """添加题目到题库。"""
        qs = QuestionSet(name="专题", teacher_id=1)
        db_session.add(qs)
        q = await _create_question(db_session)
        await db_session.commit()

        result = await QuestionBankService.add_item(
            db_session,
            QuestionSetItemAdd(
                question_set_id=qs.id, question_id=q.id, sort_order=1,
            ),
        )

        assert result.question_set_id == qs.id
        assert result.question_id == q.id
        assert result.sort_order == 1


class TestItemList:
    """GET /question-sets/{id}/items → list_items。"""

    @pytest.mark.anyio
    async def test_empty_set(self, db_session):
        """空题库返回空列表。"""
        items = await QuestionBankService.list_items(db_session, set_id=1)
        assert items == []

    @pytest.mark.anyio
    async def test_with_items(self, db_session):
        """列出题库中的题目。"""
        qs = QuestionSet(name="专题", teacher_id=1)
        db_session.add(qs)
        q = await _create_question(db_session, content="pH计算题")
        await db_session.commit()

        item = QuestionSetItem(question_set_id=qs.id, question_id=q.id, sort_order=1)
        db_session.add(item)
        await db_session.commit()

        items = await QuestionBankService.list_items(db_session, set_id=qs.id)
        assert len(items) == 1
        assert items[0].content == "pH计算题"


class TestItemReorder:
    """PATCH /question-sets/items/{id} → reorder_item。"""

    @pytest.mark.anyio
    async def test_nonexistent_raises(self, db_session):
        """不存在的项 → QuestionBankError。"""
        with pytest.raises(QuestionBankError, match="题目集项不存在"):
            await QuestionBankService.reorder_item(db_session, 99999, new_order=5)

    @pytest.mark.anyio
    async def test_reorder(self, db_session):
        """调整排序成功。"""
        qs = QuestionSet(name="专题", teacher_id=1)
        db_session.add(qs)
        await db_session.commit()
        item = QuestionSetItem(question_set_id=qs.id, question_id=1, sort_order=1)
        db_session.add(item)
        await db_session.commit()
        await db_session.refresh(item)

        result = await QuestionBankService.reorder_item(db_session, item.id, new_order=5)
        assert result.sort_order == 5


class TestItemRemove:
    """DELETE /question-sets/items/{id} → remove_item。"""

    @pytest.mark.anyio
    async def test_nonexistent_raises(self, db_session):
        """不存在的项 → QuestionBankError。"""
        with pytest.raises(QuestionBankError, match="题目集项不存在"):
            await QuestionBankService.remove_item(db_session, 99999)

    @pytest.mark.anyio
    async def test_remove(self, db_session):
        """删除项成功。"""
        qs = QuestionSet(name="专题", teacher_id=1)
        db_session.add(qs)
        await db_session.commit()
        item = QuestionSetItem(question_set_id=qs.id, question_id=1, sort_order=1)
        db_session.add(item)
        await db_session.commit()
        item_id = item.id

        await QuestionBankService.remove_item(db_session, item_id)
        result = await db_session.execute(
            select(QuestionSetItem).where(QuestionSetItem.id == item_id)
        )
        assert result.scalar_one_or_none() is None


# ═══════════════════════════════════════════════════════════════
# Historical Exams
# ═══════════════════════════════════════════════════════════════

class TestHistoricalExams:
    """GET /historical-exams → list_historical_exams。"""

    @pytest.mark.anyio
    async def test_empty(self, db_session):
        """无历年真题时返回空。"""
        items, total = await QuestionBankService.list_historical_exams(db_session)
        assert total == 0
        assert items == []

    @pytest.mark.anyio
    async def test_with_data(self, db_session):
        """有历年真题时返回。"""
        db_session.add(HistoricalExam(
            source="长沙一模", year=2024,
            difficulty="medium", content="长沙市2024年一模考试化学试题",
            answer="B", analysis="解析",
        ))
        db_session.add(HistoricalExam(
            source="全国卷", year=2024,
            difficulty="hard", content="2024年全国统一高考化学试题",
            answer="C", analysis="解析",
        ))
        await db_session.commit()

        items, total = await QuestionBankService.list_historical_exams(db_session)
        assert total == 2

    @pytest.mark.anyio
    async def test_filter_by_difficulty(self, db_session):
        """按难度过滤。"""
        db_session.add(HistoricalExam(
            source="来源A", year=2023, difficulty="easy",
            content="2023年来源A化学试题（简单）",
            answer="A", analysis="解析",
        ))
        db_session.add(HistoricalExam(
            source="来源A", year=2023, difficulty="hard",
            content="2023年来源A化学试题（困难）",
            answer="D", analysis="解析",
        ))
        await db_session.commit()

        items, total = await QuestionBankService.list_historical_exams(
            db_session, difficulty="hard",
        )
        assert total == 1
        assert items[0].difficulty == "hard"
