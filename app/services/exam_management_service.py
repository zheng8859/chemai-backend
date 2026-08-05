"""考试管理服务 — 题目关联/发布/导出/结果（25号文档 §六）。

核心功能：
- 题目关联：双渠道（Question 表 + HistoricalExam 复制）
- 考试发布：验证 → 状态转移 → 统计
- 手动导入：批量创建题目
"""

from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from ..models.exam_paper import ExamPaper, ExamPaperQuestion
from ..models.teaching import ExamRecord, Question
from ..models.question_bank import HistoricalExam
from ..models.user import Student
from ..schemas.teaching import QuestionCreate, QuestionRead


class ExamManagementError(Exception):
    def __init__(self, detail: str, error_code: str = "RESOURCE_NOT_FOUND"):
        self.detail = detail
        self.error_code = error_code
        super().__init__(detail)


class ExamManagementService:

    # ═══════════════════════════════════════════════════════════
    # 6.2: 题目关联 — 双渠道支持（§6.4）
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    async def add_questions_to_exam(
        db: AsyncSession,
        exam_record_id: int,
        question_ids: list[int],
    ) -> dict:
        """将题目关联到考试（双渠道）。

        渠道一：Question 表中已有 → 直接创建 ExamPaperQuestion 关联
        渠道二：仅存在于 HistoricalExam → 先复制到 Question，再关联

        Args:
            db: 数据库会话
            exam_record_id: 考试记录 ID
            question_ids: 题目 ID 列表

        Returns:
            {"added": N, "from_historical": N, "from_existing": N}
        """
        # 获取考试记录
        result = await db.execute(
            select(ExamRecord).where(ExamRecord.id == exam_record_id)
        )
        exam = result.scalar_one_or_none()
        if exam is None:
            raise ExamManagementError(f"考试不存在: id={exam_record_id}")

        # 确保有 ExamPaper（如无则创建）
        if exam.exam_paper_id is None:
            paper = ExamPaper(
                name=exam.name or f"考试-{exam.id}",
                teacher_id=1,  # TODO: 从 user context 获取
                status="draft",
            )
            db.add(paper)
            await db.flush()
            exam.exam_paper_id = paper.id
            await db.flush()

        paper_id = exam.exam_paper_id

        from_existing = 0
        from_historical = 0

        for qid in question_ids:
            # 渠道一：查 Question 表
            result = await db.execute(
                select(Question).where(Question.id == qid)
            )
            question = result.scalar_one_or_none()

            if question is None:
                # 渠道二：从 HistoricalExam 复制
                result = await db.execute(
                    select(HistoricalExam).where(HistoricalExam.id == qid)
                )
                hist = result.scalar_one_or_none()
                if hist is None:
                    continue  # 两处都找不到，跳过

                question = Question(
                    content=hist.content,
                    question_type="choice" if hist.options else "fill_blank",
                    options=hist.options,
                    answer=hist.answer,
                    analysis=hist.analysis,
                    knowledge_point_tags=hist.knowledge_point_tags,
                    difficulty=hist.difficulty,
                    source="historical",
                )
                db.add(question)
                await db.flush()
                from_historical += 1
            else:
                from_existing += 1

            # 创建 ExamPaperQuestion 关联（防重复）
            result = await db.execute(
                select(ExamPaperQuestion).where(
                    ExamPaperQuestion.exam_paper_id == paper_id,
                    ExamPaperQuestion.question_id == question.id,
                )
            )
            if result.scalar_one_or_none() is None:
                sort = from_existing + from_historical
                epq = ExamPaperQuestion(
                    exam_paper_id=paper_id,
                    question_id=question.id,
                    sort_order=sort,
                )
                db.add(epq)

        await db.commit()

        return {
            "added": from_existing + from_historical,
            "from_existing": from_existing,
            "from_historical": from_historical,
        }

    @staticmethod
    async def get_exam_questions(
        db: AsyncSession, exam_record_id: int,
    ) -> list[dict]:
        """获取考试当前题目列表。"""
        result = await db.execute(
            select(ExamRecord).where(ExamRecord.id == exam_record_id)
        )
        exam = result.scalar_one_or_none()
        if exam is None or exam.exam_paper_id is None:
            return []

        result = await db.execute(
            select(ExamPaperQuestion, Question)
            .join(Question, ExamPaperQuestion.question_id == Question.id)
            .where(ExamPaperQuestion.exam_paper_id == exam.exam_paper_id)
            .order_by(ExamPaperQuestion.sort_order)
        )
        questions = []
        for epq, q in result:
            questions.append({
                "id": q.id,
                "content": q.content,
                "question_type": q.question_type,
                "difficulty": q.difficulty,
                "sort_order": epq.sort_order,
                "answer": q.answer,
                "analysis": q.analysis,
                "options": q.options,
                "knowledge_point_tags": q.knowledge_point_tags,
            })
        return questions

    @staticmethod
    async def remove_question_from_exam(
        db: AsyncSession,
        exam_record_id: int,
        question_id: int,
    ) -> None:
        """从考试中移除题目。"""
        result = await db.execute(
            select(ExamRecord).where(ExamRecord.id == exam_record_id)
        )
        exam = result.scalar_one_or_none()
        if exam is None or exam.exam_paper_id is None:
            raise ExamManagementError(f"考试不存在: id={exam_record_id}")

        result = await db.execute(
            select(ExamPaperQuestion).where(
                ExamPaperQuestion.exam_paper_id == exam.exam_paper_id,
                ExamPaperQuestion.question_id == question_id,
            )
        )
        epq = result.scalar_one_or_none()
        if epq:
            await db.delete(epq)
            await db.commit()

    # ═══════════════════════════════════════════════════════════
    # 6.2 / 6.3: 考试发布
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    async def publish_exam(db: AsyncSession, exam_record_id: int) -> dict:
        """发布考试（§6.3）。

        1. 验证考试至少有 1 道题
        2. 设置状态为 published / in_progress
        3. 统计参考学生数
        """
        result = await db.execute(
            select(ExamRecord).where(ExamRecord.id == exam_record_id)
        )
        exam = result.scalar_one_or_none()
        if exam is None:
            raise ExamManagementError(f"考试不存在: id={exam_record_id}")

        # 验证至少有题目
        question_count = 0
        if exam.exam_paper_id:
            result = await db.execute(
                select(func.count(ExamPaperQuestion.id)).where(
                    ExamPaperQuestion.exam_paper_id == exam.exam_paper_id
                )
            )
            question_count = result.scalar() or 0

        if question_count == 0:
            raise ExamManagementError("考试至少需要1道题才能发布", "VALIDATION_ERROR")

        # 统计学生数
        result = await db.execute(
            select(func.count(Student.id)).where(
                Student.class_id == exam.class_id
            )
        )
        total_students = result.scalar() or 0

        # 更新考试状态
        exam.status = "in_progress"
        exam.participant_count = total_students
        await db.commit()

        return {
            "success": True,
            "exam_id": exam.id,
            "status": "in_progress",
            "question_count": question_count,
            "total_students": total_students,
            "published_at": datetime.now(timezone.utc).isoformat(),
        }

    @staticmethod
    async def finalize_exam(db: AsyncSession, exam_record_id: int) -> dict:
        """完成考试（统计分数等）。"""
        result = await db.execute(
            select(ExamRecord).where(ExamRecord.id == exam_record_id)
        )
        exam = result.scalar_one_or_none()
        if exam is None:
            raise ExamManagementError(f"考试不存在: id={exam_record_id}")

        exam.status = "completed"
        await db.commit()

        return {
            "success": True,
            "exam_id": exam.id,
            "status": "completed",
            "participant_count": exam.participant_count,
        }

    # ═══════════════════════════════════════════════════════════
    # Mode 2: 手动录入（§3 Mode2）
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    async def import_questions(
        db: AsyncSession,
        questions_data: list[dict],
        source_name: str = "",
    ) -> list[QuestionRead]:
        """批量导入题目（手动录入 / OCR 确认后）。

        Args:
            db: 数据库会话
            questions_data: 题目字典列表
            source_name: 来源名称

        Returns:
            创建的 Question 对象列表
        """
        created: list[QuestionRead] = []
        for q_data in questions_data:
            question = Question(
                content=q_data.get("content", ""),
                question_type=q_data.get("question_type", "choice"),
                options=q_data.get("options", []),
                answer=q_data.get("answer", ""),
                analysis=q_data.get("analysis", ""),
                knowledge_point_tags=q_data.get("knowledge_point_tags", []),
                difficulty=q_data.get("difficulty", "medium"),
                source="manual",
            )
            db.add(question)
            await db.flush()
            created.append(QuestionRead.model_validate(question))

        await db.commit()
        return created
