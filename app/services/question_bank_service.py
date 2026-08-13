"""Question bank service — 题库文件夹 CRUD + 题目集管理 + 历年真题查询。"""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from ..core.enums import QuestionType, Difficulty, QuestionSource, AuditStatus
from ..models.question_bank import QuestionSet, QuestionSetItem, HistoricalExam
from ..models.teaching import Question
from ..schemas.question_bank import (
    QuestionSetCreate,
    QuestionSetRead,
    QuestionSetItemRead,
    QuestionSetItemAdd,
    HistoricalExamRead,
)


class QuestionBankError(Exception):
    def __init__(self, detail: str, error_code: str = "RESOURCE_NOT_FOUND"):
        self.detail = detail
        self.error_code = error_code
        super().__init__(detail)


class QuestionBankService:

    @staticmethod
    async def create_question_set(db: AsyncSession, data: QuestionSetCreate) -> QuestionSetRead:
        qs = QuestionSet(**data.model_dump())
        db.add(qs)
        await db.commit()
        await db.refresh(qs)
        return QuestionSetRead.model_validate(qs)

    @staticmethod
    async def list_question_sets(
        db: AsyncSession, teacher_id: int | None = None,
        limit: int = 20, offset: int = 0,
    ) -> tuple[list[QuestionSetRead], int]:
        query = select(QuestionSet)
        count_query = select(func.count(QuestionSet.id))
        if teacher_id:
            query = query.where(QuestionSet.teacher_id == teacher_id)
            count_query = count_query.where(QuestionSet.teacher_id == teacher_id)
        total = (await db.execute(count_query)).scalar() or 0
        result = await db.execute(
            query.order_by(QuestionSet.created_at.desc()).offset(offset).limit(limit)
        )
        sets = result.scalars().all()

        # Count items for each set
        set_ids = [s.id for s in sets]
        counts = {}
        if set_ids:
            count_result = await db.execute(
                select(QuestionSetItem.question_set_id, func.count(QuestionSetItem.id))
                .where(QuestionSetItem.question_set_id.in_(set_ids))
                .group_by(QuestionSetItem.question_set_id)
            )
            counts = {row[0]: row[1] for row in count_result.all()}

        reads = []
        for s in sets:
            r = QuestionSetRead.model_validate(s)
            r.question_count = counts.get(s.id, 0)
            reads.append(r)
        return reads, total

    @staticmethod
    async def update_question_set(
        db: AsyncSession, set_id: int, name: str | None = None, description: str | None = None,
    ) -> QuestionSetRead:
        result = await db.execute(select(QuestionSet).where(QuestionSet.id == set_id))
        qs = result.scalar_one_or_none()
        if qs is None:
            raise QuestionBankError(f"题库不存在: id={set_id}")
        if name is not None:
            qs.name = name
        if description is not None:
            qs.description = description
        await db.commit()
        await db.refresh(qs)
        return QuestionSetRead.model_validate(qs)

    @staticmethod
    async def delete_question_set(db: AsyncSession, set_id: int) -> None:
        result = await db.execute(select(QuestionSet).where(QuestionSet.id == set_id))
        qs = result.scalar_one_or_none()
        if qs is None:
            raise QuestionBankError(f"题库不存在: id={set_id}")
        if qs.is_system:
            raise QuestionBankError(
                "系统预设文件夹不可删除", error_code="FORBIDDEN"
            )
        await db.delete(qs)
        await db.commit()

    @staticmethod
    async def add_item(db: AsyncSession, data: QuestionSetItemAdd) -> QuestionSetItemRead:
        item = QuestionSetItem(**data.model_dump())
        db.add(item)
        await db.commit()
        await db.refresh(item)
        return QuestionSetItemRead.model_validate(item)

    @staticmethod
    async def save_questions_batch(
        db: AsyncSession,
        name: str,
        questions: list[dict],
        teacher_id: int | None = None,
    ) -> dict:
        """原子批量保存题目：建文件夹 + 逐题入库 + 建关联，单事务提交。

        任一步失败则整体回滚，不残留半套数据。
        question dict 字段：content / answer / question_type / difficulty /
        knowledge_points（或 knowledge_point_tags）/ options / analysis。

        Args:
            db: 数据库会话
            name: 题库文件夹名称
            questions: 题目 dict 列表
            teacher_id: 教师 ID

        Returns:
            {"bank_id", "bank_name", "saved_count", "question_ids"}
        """
        qs = QuestionSet(name=name, teacher_id=teacher_id or 0)
        db.add(qs)
        await db.flush()

        saved: list[int] = []
        for i, q in enumerate(questions, start=1):
            qobj = Question(
                content=q.get("content", ""),
                question_type=q.get("question_type", QuestionType.choice),
                options=q.get("options") or [],
                answer=q.get("answer", ""),
                analysis=q.get("analysis"),
                knowledge_point_tags=q.get("knowledge_points") or q.get("knowledge_point_tags") or [],
                difficulty=q.get("difficulty", Difficulty.medium),
                source=QuestionSource.ai_generated,
                audit_status=AuditStatus.passed,
            )
            db.add(qobj)
            await db.flush()
            db.add(QuestionSetItem(question_set_id=qs.id, question_id=qobj.id, sort_order=i))
            saved.append(qobj.id)

        await db.commit()
        await db.refresh(qs)
        return {
            "bank_id": qs.id,
            "bank_name": qs.name,
            "saved_count": len(saved),
            "question_ids": saved,
        }

    @staticmethod
    async def list_items(
        db: AsyncSession, set_id: int,
    ) -> list[QuestionSetItemRead]:
        result = await db.execute(
            select(QuestionSetItem, Question)
            .outerjoin(Question, QuestionSetItem.question_id == Question.id)
            .where(QuestionSetItem.question_set_id == set_id)
            .order_by(QuestionSetItem.sort_order)
        )
        items = []
        for row in result.all():
            item = row[0]  # QuestionSetItem
            question = row[1]  # Question (may be None)
            read = QuestionSetItemRead.model_validate(item)
            if question:
                read.content = question.content
                read.question_type = question.question_type
                read.difficulty = question.difficulty
                read.options = question.options
                read.answer = question.answer
                read.knowledge_point_tags = question.knowledge_point_tags
            items.append(read)
        return items

    @staticmethod
    async def reorder_item(db: AsyncSession, item_id: int, new_order: int) -> QuestionSetItemRead:
        result = await db.execute(select(QuestionSetItem).where(QuestionSetItem.id == item_id))
        item = result.scalar_one_or_none()
        if item is None:
            raise QuestionBankError(f"题目集项不存在: id={item_id}")
        item.sort_order = new_order
        await db.commit()
        await db.refresh(item)
        return QuestionSetItemRead.model_validate(item)

    @staticmethod
    async def remove_item(db: AsyncSession, item_id: int) -> None:
        result = await db.execute(select(QuestionSetItem).where(QuestionSetItem.id == item_id))
        item = result.scalar_one_or_none()
        if item is None:
            raise QuestionBankError(f"题目集项不存在: id={item_id}")
        await db.delete(item)
        await db.commit()

    @staticmethod
    async def list_historical_exams(
        db: AsyncSession,
        source: str | None = None,
        year: int | None = None,
        difficulty: str | None = None,
        knowledge_point: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[HistoricalExamRead], int]:
        query = select(HistoricalExam)
        count_query = select(func.count(HistoricalExam.id))

        if source:
            query = query.where(HistoricalExam.source == source)
            count_query = count_query.where(HistoricalExam.source == source)
        if year:
            query = query.where(HistoricalExam.year == year)
            count_query = count_query.where(HistoricalExam.year == year)
        if difficulty:
            query = query.where(HistoricalExam.difficulty == difficulty)
            count_query = count_query.where(HistoricalExam.difficulty == difficulty)

        total = (await db.execute(count_query)).scalar() or 0
        result = await db.execute(
            query.order_by(HistoricalExam.year.desc()).offset(offset).limit(limit)
        )
        return [HistoricalExamRead.model_validate(e) for e in result.scalars().all()], total
