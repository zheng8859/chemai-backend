"""Teaching service — 考试/题目/作答 CRUD + 出题/批改 stub。"""

from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from ..models.teaching import ExamRecord, Question, StudentAnswer
from ..models.org import Class
from ..schemas.teaching import (
    ExamCreate, ExamRead, QuestionCreate, QuestionRead, StudentAnswerRead,
)


class TeachingError(Exception):
    def __init__(self, detail: str, error_code: str = "RESOURCE_NOT_FOUND"):
        self.detail = detail
        self.error_code = error_code
        super().__init__(detail)


class TeachingService:

    # ═══════════════════════════════════════════════════════════
    # Exams
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    async def create_exam(db: AsyncSession, data: ExamCreate) -> ExamRead:
        exam = ExamRecord(
            class_id=data.class_id,
            exam_type=data.exam_type,
            exam_date=data.exam_date,
            name=data.name,
            status="pending",
        )
        db.add(exam)
        await db.commit()
        await db.refresh(exam)
        return ExamRead.model_validate(exam)

    @staticmethod
    async def get_exam(db: AsyncSession, exam_id: int) -> ExamRead:
        result = await db.execute(select(ExamRecord).where(ExamRecord.id == exam_id))
        exam = result.scalar_one_or_none()
        if exam is None:
            raise TeachingError(f"考试不存在: id={exam_id}")
        return ExamRead.model_validate(exam)

    @staticmethod
    async def list_exams_by_class(
        db: AsyncSession, class_id: int | None = None,
        limit: int = 20, offset: int = 0,
    ) -> tuple[list[ExamRead], int]:
        query = select(ExamRecord)
        count_query = select(func.count(ExamRecord.id))
        if class_id:
            query = query.where(ExamRecord.class_id == class_id)
            count_query = count_query.where(ExamRecord.class_id == class_id)
        total = (await db.execute(count_query)).scalar() or 0
        result = await db.execute(
            query.order_by(ExamRecord.exam_date.desc()).offset(offset).limit(limit)
        )
        exams = [ExamRead.model_validate(e) for e in result.scalars().all()]
        return exams, total

    @staticmethod
    async def update_exam(
        db: AsyncSession, exam_id: int, name: str | None = None,
    ) -> ExamRead:
        result = await db.execute(select(ExamRecord).where(ExamRecord.id == exam_id))
        exam = result.scalar_one_or_none()
        if exam is None:
            raise TeachingError(f"考试不存在: id={exam_id}")
        if name is not None:
            exam.name = name
        await db.commit()
        await db.refresh(exam)
        return ExamRead.model_validate(exam)

    @staticmethod
    async def delete_exam(db: AsyncSession, exam_id: int) -> None:
        result = await db.execute(select(ExamRecord).where(ExamRecord.id == exam_id))
        exam = result.scalar_one_or_none()
        if exam is None:
            raise TeachingError(f"考试不存在: id={exam_id}")
        await db.delete(exam)
        await db.commit()

    # ═══════════════════════════════════════════════════════════
    # Questions
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    async def create_question(db: AsyncSession, data: QuestionCreate) -> QuestionRead:
        q = Question(**data.model_dump())
        db.add(q)
        await db.commit()
        await db.refresh(q)
        return QuestionRead.model_validate(q)

    @staticmethod
    async def get_question(db: AsyncSession, question_id: int) -> QuestionRead:
        result = await db.execute(select(Question).where(Question.id == question_id))
        q = result.scalar_one_or_none()
        if q is None:
            raise TeachingError(f"题目不存在: id={question_id}")
        return QuestionRead.model_validate(q)

    @staticmethod
    async def list_questions(
        db: AsyncSession,
        difficulty: str | None = None,
        question_type: str | None = None,
        knowledge_point: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[QuestionRead], int]:
        query = select(Question)
        count_query = select(func.count(Question.id))
        if difficulty:
            query = query.where(Question.difficulty == difficulty)
            count_query = count_query.where(Question.difficulty == difficulty)
        if question_type:
            query = query.where(Question.question_type == question_type)
            count_query = count_query.where(Question.question_type == question_type)
        total = (await db.execute(count_query)).scalar() or 0
        result = await db.execute(
            query.order_by(Question.created_at.desc()).offset(offset).limit(limit)
        )
        return [QuestionRead.model_validate(q) for q in result.scalars().all()], total

    @staticmethod
    async def update_question(
        db: AsyncSession, question_id: int, **kwargs,
    ) -> QuestionRead:
        result = await db.execute(select(Question).where(Question.id == question_id))
        q = result.scalar_one_or_none()
        if q is None:
            raise TeachingError(f"题目不存在: id={question_id}")
        for key, value in kwargs.items():
            if value is not None:
                setattr(q, key, value)
        await db.commit()
        await db.refresh(q)
        return QuestionRead.model_validate(q)

    @staticmethod
    async def delete_question(db: AsyncSession, question_id: int) -> None:
        result = await db.execute(select(Question).where(Question.id == question_id))
        q = result.scalar_one_or_none()
        if q is None:
            raise TeachingError(f"题目不存在: id={question_id}")
        await db.delete(q)
        await db.commit()

    # ═══════════════════════════════════════════════════════════
    # Stubs
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    async def generate_questions_stub(**kwargs) -> dict:
        """AI 出题 stub — LLM 管线尚未实现。"""
        return {
            "warning": "LLM pipeline not implemented",
            "questions": [],
            "generated_count": 0,
            "total_available": 0,
        }

    # ═══════════════════════════════════════════════════════════
    # Answers
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    async def submit_answer(
        db: AsyncSession,
        student_id: int,
        question_id: int,
        answer_content: str,
        exam_record_id: int | None = None,
    ) -> StudentAnswerRead:
        # Auto-grade: compare against question.answer
        result = await db.execute(select(Question).where(Question.id == question_id))
        question = result.scalar_one_or_none()
        if question is None:
            raise TeachingError(f"题目不存在: id={question_id}")
        is_correct = (answer_content.strip() == question.answer.strip())

        answer = StudentAnswer(
            student_id=student_id,
            question_id=question_id,
            exam_record_id=exam_record_id,
            answer_content=answer_content,
            is_correct=is_correct,
        )
        db.add(answer)
        await db.commit()
        await db.refresh(answer)
        return StudentAnswerRead.model_validate(answer)

    @staticmethod
    async def list_answers_by_exam(
        db: AsyncSession, exam_id: int,
        limit: int = 20, offset: int = 0,
    ) -> tuple[list[StudentAnswerRead], int]:
        total = (await db.execute(
            select(func.count(StudentAnswer.id)).where(StudentAnswer.exam_record_id == exam_id)
        )).scalar() or 0
        result = await db.execute(
            select(StudentAnswer)
            .where(StudentAnswer.exam_record_id == exam_id)
            .order_by(StudentAnswer.created_at.desc())
            .offset(offset).limit(limit)
        )
        return [StudentAnswerRead.model_validate(a) for a in result.scalars().all()], total

    @staticmethod
    async def list_answers_by_student(
        db: AsyncSession, student_id: int,
        limit: int = 20, offset: int = 0,
    ) -> tuple[list[StudentAnswerRead], int]:
        total = (await db.execute(
            select(func.count(StudentAnswer.id)).where(StudentAnswer.student_id == student_id)
        )).scalar() or 0
        result = await db.execute(
            select(StudentAnswer)
            .where(StudentAnswer.student_id == student_id)
            .order_by(StudentAnswer.created_at.desc())
            .offset(offset).limit(limit)
        )
        return [StudentAnswerRead.model_validate(a) for a in result.scalars().all()], total

    @staticmethod
    async def trigger_grading_stub(exam_id: int, class_id: int) -> dict:
        """LLM 批改 stub — 返回占位 grading_job_id。"""
        import uuid
        return {
            "success": True,
            "grading_job_id": str(uuid.uuid4()),
            "total_submissions": 0,
            "status": "pending",
        }
