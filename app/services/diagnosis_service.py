"""Diagnosis service — 障碍配置/知识点/班级诊断/复习/预警/练习分配。

v2: 引擎优先架构 — LLM 诊断和聚合逻辑委托给 chem_skills 纯函数库，
    API 层薄封装，仅负责 DB 读写和事务管理。
"""

import logging
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from ..models.diagnosis import (
    BarrierConfig, KnowledgePoint, WarningLog,
)
from ..models.teaching import StudentAnswer, Question, ExamRecord
from ..models.user import Student
from ..schemas.diagnosis import (
    BarrierConfigRead, BarrierConfigUpdate,
    KnowledgePointRead, WarningLogRead,
)
from ..core.enums import BarrierType, MisconceptionCategory, DiagnosisSource
from ..llm.router import llm_chat, LLMError

from chem_skills.chemistry_diagnosis.engine.llm_diagnoser import SYSTEM_PROMPT
from chem_skills.chemistry_diagnosis.engine import (
    diagnose_batch,
    aggregate_student,
    aggregate_class,
)

logger = logging.getLogger(__name__)


class DiagnosisError(Exception):
    def __init__(self, detail: str, error_code: str = "RESOURCE_NOT_FOUND"):
        self.detail = detail
        self.error_code = error_code
        super().__init__(detail)


class DiagnosisService:

    # ═══════════════════════════════════════════════════════════
    # Barrier Config
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    async def get_barrier_config(db: AsyncSession, teacher_id: int) -> BarrierConfigRead:
        result = await db.execute(
            select(BarrierConfig).where(BarrierConfig.teacher_id == teacher_id)
        )
        config = result.scalar_one_or_none()
        if config is None:
            # Auto-create default
            config = BarrierConfig(teacher_id=teacher_id)
            db.add(config)
            await db.commit()
            await db.refresh(config)
        return BarrierConfigRead.model_validate(config)

    @staticmethod
    async def update_barrier_config(
        db: AsyncSession, teacher_id: int, data: BarrierConfigUpdate,
    ) -> BarrierConfigRead:
        result = await db.execute(
            select(BarrierConfig).where(BarrierConfig.teacher_id == teacher_id)
        )
        config = result.scalar_one_or_none()
        if config is None:
            config = BarrierConfig(teacher_id=teacher_id)
            db.add(config)

        update_data = data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(config, key, value)
        await db.commit()
        await db.refresh(config)
        return BarrierConfigRead.model_validate(config)

    # ═══════════════════════════════════════════════════════════
    # Knowledge Points
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    async def list_knowledge_points(
        db: AsyncSession, category: str | None = None,
        limit: int = 50, offset: int = 0,
    ) -> tuple[list[KnowledgePointRead], int]:
        query = select(KnowledgePoint)
        count_query = select(func.count(KnowledgePoint.id))
        if category:
            query = query.where(KnowledgePoint.category == category)
            count_query = count_query.where(KnowledgePoint.category == category)
        total = (await db.execute(count_query)).scalar() or 0
        result = await db.execute(
            query.order_by(KnowledgePoint.name).offset(offset).limit(limit)
        )
        return [KnowledgePointRead.model_validate(k) for k in result.scalars().all()], total

    @staticmethod
    async def search_knowledge_points(
        db: AsyncSession,
        keyword: str,
        limit: int = 20,
    ) -> list[KnowledgePointRead]:
        pattern = f"%{keyword}%"
        result = await db.execute(
            select(KnowledgePoint)
            .where(
                (KnowledgePoint.name.ilike(pattern))
                | (KnowledgePoint.category.ilike(pattern))
            )
            .order_by(KnowledgePoint.name)
            .limit(limit)
        )
        return [KnowledgePointRead.model_validate(k) for k in result.scalars().all()]

    # ═══════════════════════════════════════════════════════════
    # Class Diagnosis（真实聚合，替换 stub）
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    async def get_class_diagnosis(
        db: AsyncSession, class_id: int, exam_id: int,
    ) -> dict:
        """班级障碍诊断聚合 — 基于 engine 的真实聚合逻辑。

        仅覆盖已诊断作答（barrier_type IS NOT NULL），未诊断学生不参与统计。
        """
        # 查询该考试下所有已诊断的错误作答
        result = await db.execute(
            select(StudentAnswer)
            .join(Student, Student.id == StudentAnswer.student_id)
            .where(
                StudentAnswer.exam_record_id == exam_id,
                StudentAnswer.is_correct == False,
                StudentAnswer.barrier_type.is_not(None),
                Student.class_id == class_id,
            )
        )
        answers = result.scalars().all()

        # 按学生分组
        student_answers: dict[int, list[dict]] = {}
        for sa in answers:
            if sa.student_id not in student_answers:
                student_answers[sa.student_id] = []
            student_answers[sa.student_id].append({
                "barrier_type": sa.barrier_type.value if isinstance(sa.barrier_type, BarrierType) else sa.barrier_type,
                "misconception_category": (
                    sa.misconception_category.value
                    if isinstance(sa.misconception_category, MisconceptionCategory)
                    else sa.misconception_category
                ),
                "knowledge_point_tags": sa.question.knowledge_point_tags if sa.question else None,
                "is_correct": sa.is_correct,
            })

        # 班级级聚合
        distribution = aggregate_class(class_id, exam_id, student_answers)

        # 逐生画像 + 构建响应
        students_list = []
        for sid in student_answers:
            profile = aggregate_student(sid, student_answers[sid])
            # 获取学生姓名
            student = (await db.execute(select(Student).where(Student.id == sid))).scalar_one_or_none()
            student_name = student.name if student else f"学生{sid}"

            students_list.append({
                "student_id": sid,
                "student_name": student_name,
                "barrier_type": profile.dominant_barrier(),
                "confidence": None,  # 不存储 confidence
                "weak_kps": profile.weak_kps,
                "recommended_intervention": None,  # 暂时为空，v2 可接入建议引擎
            })

        return {
            "success": True,
            "class_id": class_id,
            "exam_id": exam_id,
            "class_summary": distribution.to_summary_dict(),
            "students": students_list,
        }

    # ═══════════════════════════════════════════════════════════
    # LLM Diagnosis（新增）
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    def _create_llm_adapter():
        """创建 LLM 调用适配器（依赖注入 callback）。

        将 engine 所需的 Callable[[str], Awaitable[str]] 适配到项目的 llm_chat()。
        """
        async def _adapter(user_prompt: str) -> str:
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ]
            return await llm_chat(
                messages,
                temperature=0.3,
                max_tokens=2000,
            )

        return _adapter

    @staticmethod
    async def _get_student_error_history(
        db: AsyncSession,
        student_id: int,
        limit: int = 5,
    ) -> list[dict]:
        """获取学生近期错题历史（用于 LLM 诊断上下文）。"""
        result = await db.execute(
            select(StudentAnswer)
            .join(Question, Question.id == StudentAnswer.question_id)
            .where(
                StudentAnswer.student_id == student_id,
                StudentAnswer.is_correct == False,
                StudentAnswer.barrier_type.is_not(None),  # 只取已诊断的作为参考
            )
            .order_by(StudentAnswer.created_at.desc())
            .limit(limit)
        )
        history = []
        for sa in result.scalars().all():
            history.append({
                "content": sa.question.content if sa.question else "",
                "answer": sa.answer_content,
                "correct": sa.question.answer if sa.question else "",
            })
        return history

    @staticmethod
    async def run_llm_diagnosis(
        db: AsyncSession,
        exam_record_id: int,
    ) -> dict:
        """触发 LLM 批量诊断（单次最多 10 条）。

        查询该考试中 barrier_type IS NULL 的错误作答，
        调用 engine 的 diagnose_batch()，写入结果，触发聚合。

        Args:
            db: 数据库会话
            exam_record_id: 考试记录 ID

        Returns:
            {"success": True, "analyzed_count": N, "failed_count": N,
             "remaining_count": N}

        Raises:
            DiagnosisError: 考试不存在
            LLMError: 所有 LLM Provider 不可用
        """
        # 验证考试存在
        exam = (await db.execute(
            select(ExamRecord).where(ExamRecord.id == exam_record_id)
        )).scalar_one_or_none()
        if exam is None:
            raise DiagnosisError(f"考试不存在: id={exam_record_id}")

        # 查询未诊断的错误作答（最多 10 条）
        result = await db.execute(
            select(StudentAnswer)
            .join(Question, Question.id == StudentAnswer.question_id)
            .where(
                StudentAnswer.exam_record_id == exam_record_id,
                StudentAnswer.is_correct == False,
                StudentAnswer.barrier_type.is_(None),
            )
            .limit(10)
        )
        unanswered = result.scalars().all()

        if not unanswered:
            # 计算剩余未诊断数
            remaining = await db.execute(
                select(func.count(StudentAnswer.id)).where(
                    StudentAnswer.exam_record_id == exam_record_id,
                    StudentAnswer.is_correct == False,
                    StudentAnswer.barrier_type.is_(None),
                )
            )
            return {
                "success": True,
                "analyzed_count": 0,
                "failed_count": 0,
                "remaining_count": remaining.scalar() or 0,
            }

        # 构建 engine 输入 + 获取学生历史
        error_answers = []
        for sa in unanswered:
            history = await DiagnosisService._get_student_error_history(db, sa.student_id)
            error_answers.append({
                "_sa_id": sa.id,
                "_student_id": sa.student_id,
                "question_content": sa.question.content if sa.question else "",
                "student_answer": sa.answer_content,
                "correct_answer": sa.question.answer if sa.question else "",
                "history": history,
            })

        # 调用 engine（依赖注入 LLM adapter）
        llm_adapter = DiagnosisService._create_llm_adapter()
        success_results, failed_count = await diagnose_batch(llm_adapter, error_answers)

        # 写入诊断结果到 StudentAnswer
        affected_students: set[int] = set()
        analyzed_ids: set[int] = set()

        for ea, diag_result in success_results:
            sa_id = ea["_sa_id"]
            student_id = ea["_student_id"]

            sa_record = (await db.execute(
                select(StudentAnswer).where(StudentAnswer.id == sa_id)
            )).scalar_one_or_none()

            if sa_record is None:
                continue

            sa_record.barrier_type = BarrierType(diag_result.barrier_type)
            if diag_result.misconception_category:
                sa_record.misconception_category = MisconceptionCategory(
                    diag_result.misconception_category
                )
            sa_record.diagnosed_by = DiagnosisSource.ai_llm

            analyzed_ids.add(sa_id)
            affected_students.add(student_id)

        await db.commit()

        # 更新受影响学生的 barrier_profile
        for student_id in affected_students:
            await DiagnosisService._update_barrier_profile(db, student_id)

        # 计算剩余未诊断数
        remaining = await db.execute(
            select(func.count(StudentAnswer.id)).where(
                StudentAnswer.exam_record_id == exam_record_id,
                StudentAnswer.is_correct == False,
                StudentAnswer.barrier_type.is_(None),
            )
        )

        return {
            "success": True,
            "analyzed_count": len(success_results),
            "failed_count": failed_count,
            "remaining_count": remaining.scalar() or 0,
        }

    @staticmethod
    async def _update_barrier_profile(db: AsyncSession, student_id: int):
        """更新单个学生的 barrier_profile JSON 字段。

        查询该生所有已诊断错误作答，调用 engine aggregate_student()，写回 Student。
        """
        result = await db.execute(
            select(StudentAnswer)
            .join(Question, Question.id == StudentAnswer.question_id)
            .where(
                StudentAnswer.student_id == student_id,
                StudentAnswer.is_correct == False,
                StudentAnswer.barrier_type.is_not(None),
            )
        )
        all_diagnosed = result.scalars().all()

        # 构建 engine 所需 dict 列表
        answer_dicts = []
        for sa in all_diagnosed:
            answer_dicts.append({
                "barrier_type": (
                    sa.barrier_type.value
                    if isinstance(sa.barrier_type, BarrierType)
                    else sa.barrier_type
                ),
                "misconception_category": (
                    sa.misconception_category.value
                    if isinstance(sa.misconception_category, MisconceptionCategory)
                    else sa.misconception_category
                ),
                "knowledge_point_tags": sa.question.knowledge_point_tags if sa.question else None,
                "is_correct": sa.is_correct,
            })

        profile = aggregate_student(student_id, answer_dicts)

        # 写回 Student 表
        student = (await db.execute(
            select(Student).where(Student.id == student_id)
        )).scalar_one_or_none()

        if student:
            student.barrier_profile = profile.to_dict()
            student.barrier_profile_updated_at = datetime.now(timezone.utc)
            await db.commit()

    # ═══════════════════════════════════════════════════════════
    # Teacher Override（新增）
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    async def override_diagnosis(
        db: AsyncSession,
        student_answer_id: int,
        barrier_type: str,
        misconception_category: str | None = None,
    ) -> dict:
        """教师覆盖单条作答的诊断结果。

        Args:
            db: 数据库会话
            student_answer_id: 作答记录 ID
            barrier_type: 新的障碍类型（concept/reading/expression）
            misconception_category: 新的迷思概念类别（可为 None）

        Returns:
            {"old": {...}, "new": {...}}

        Raises:
            DiagnosisError: 作答记录不存在
        """
        sa = (await db.execute(
            select(StudentAnswer).where(StudentAnswer.id == student_answer_id)
        )).scalar_one_or_none()

        if sa is None:
            raise DiagnosisError(f"作答记录不存在: id={student_answer_id}")

        # 保存旧值
        old_barrier = (
            sa.barrier_type.value
            if isinstance(sa.barrier_type, BarrierType)
            else sa.barrier_type
        )
        old_misconception = (
            sa.misconception_category.value
            if isinstance(sa.misconception_category, MisconceptionCategory)
            else sa.misconception_category
        )
        old_diagnosed_by = (
            sa.diagnosed_by.value
            if isinstance(sa.diagnosed_by, DiagnosisSource)
            else sa.diagnosed_by
        )

        old_values = {
            "barrier_type": old_barrier,
            "misconception_category": old_misconception,
            "diagnosed_by": old_diagnosed_by,
        }

        # 写入新值
        sa.barrier_type = BarrierType(barrier_type)
        if misconception_category:
            sa.misconception_category = MisconceptionCategory(misconception_category)
        else:
            sa.misconception_category = None
        sa.diagnosed_by = DiagnosisSource.teacher
        sa.diagnosis_overridden_at = datetime.now(timezone.utc)

        await db.commit()
        await db.refresh(sa)

        # 更新学生障碍画像
        await DiagnosisService._update_barrier_profile(db, sa.student_id)

        new_values = {
            "barrier_type": (
                sa.barrier_type.value
                if isinstance(sa.barrier_type, BarrierType)
                else sa.barrier_type
            ),
            "misconception_category": (
                sa.misconception_category.value
                if isinstance(sa.misconception_category, MisconceptionCategory)
                else sa.misconception_category
            ),
            "diagnosed_by": "teacher",
            "diagnosis_overridden_at": (
                sa.diagnosis_overridden_at.isoformat()
                if sa.diagnosis_overridden_at
                else None
            ),
        }

        return {"old": old_values, "new": new_values}

    # ═══════════════════════════════════════════════════════════
    # Review Tasks（已迁至 ReviewService）
    # ═══════════════════════════════════════════════════════════
    #
    # list_pending_reviews() 和 complete_review() 已迁移到
    # app/services/review_service.py::ReviewService。
    # 旧方法使用固定的 1-6 级模型，新版使用 engine 的 0-5 螺旋模型。
    #
    # 如需向后兼容，请直接调用：
    #   from .review_service import ReviewService
    #   tasks, total = await ReviewService.list_pending_reviews(db, ...)
    #   result = await ReviewService.complete_review(db, ...)

    # ═══════════════════════════════════════════════════════════
    # Warnings
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    async def list_warnings(
        db: AsyncSession,
        class_id: int | None = None,
        resolved: bool | None = None,
        severity: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[WarningLogRead], int]:
        query = select(WarningLog)
        count_query = select(func.count(WarningLog.id))
        if severity:
            query = query.where(WarningLog.severity == severity)
            count_query = count_query.where(WarningLog.severity == severity)
        total = (await db.execute(count_query)).scalar() or 0
        result = await db.execute(
            query.order_by(WarningLog.created_at.desc()).offset(offset).limit(limit)
        )
        return [WarningLogRead.model_validate(w) for w in result.scalars().all()], total

    @staticmethod
    async def resolve_warning(db: AsyncSession, warning_id: int) -> WarningLogRead:
        result = await db.execute(select(WarningLog).where(WarningLog.id == warning_id))
        warning = result.scalar_one_or_none()
        if warning is None:
            raise DiagnosisError(f"预警不存在: id={warning_id}")
        warning.notified_teacher = True
        warning.notified_parent = True
        warning.notified_student = True
        await db.commit()
        await db.refresh(warning)
        return WarningLogRead.model_validate(warning)

    # ═══════════════════════════════════════════════════════════
    # Practice Assign (stub)
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    async def assign_practice_stub(
        student_id: int, question_count: int = 10,
    ) -> dict:
        import uuid
        return {
            "success": True,
            "practice_session_id": str(uuid.uuid4()),
            "questions": [],
            "estimated_time_minutes": question_count * 3,
        }
