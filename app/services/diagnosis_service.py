"""Diagnosis service — 障碍配置/知识点/班级诊断/复习/预警/练习分配。"""

from datetime import datetime, timezone, timedelta

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from ..models.diagnosis import (
    BarrierConfig, KnowledgePoint, ReviewTask, ReviewHistory, WarningLog,
)
from ..schemas.diagnosis import (
    BarrierConfigRead, BarrierConfigUpdate,
    KnowledgePointRead, ReviewTaskRead, WarningLogRead,
)


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
        """按关键字模糊搜索知识点（§9.2 search_knowledge_points）。

        支持按名称和类别模糊匹配。
        """
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
    # Class Diagnosis (aggregation stub)
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    async def get_class_diagnosis(
        db: AsyncSession, class_id: int, exam_id: int,
    ) -> dict:
        """班级障碍诊断聚合 — 返回占位数据（实际诊断引擎在后续阶段实现）。"""
        return {
            "success": True,
            "class_id": class_id,
            "exam_id": exam_id,
            "class_summary": {
                "concept_rate": 0.0,
                "reading_rate": 0.0,
                "expression_rate": 0.0,
                "top_weak_kps": [],
            },
            "students": [],
        }

    # ═══════════════════════════════════════════════════════════
    # Review Tasks
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    async def list_pending_reviews(
        db: AsyncSession, student_id: int,
        limit: int = 20, offset: int = 0,
    ) -> tuple[list[ReviewTaskRead], int]:
        total = (await db.execute(
            select(func.count(ReviewTask.id)).where(
                ReviewTask.student_id == student_id,
                ReviewTask.status.in_(["pending", "overdue"]),
            )
        )).scalar() or 0
        result = await db.execute(
            select(ReviewTask)
            .where(ReviewTask.student_id == student_id,
                   ReviewTask.status.in_(["pending", "overdue"]))
            .order_by(ReviewTask.next_review_date.asc().nulls_last())
            .offset(offset).limit(limit)
        )
        return [ReviewTaskRead.model_validate(t) for t in result.scalars().all()], total

    @staticmethod
    async def complete_review(
        db: AsyncSession, review_task_id: int, result: bool,
    ) -> ReviewTaskRead:
        r = await db.execute(select(ReviewTask).where(ReviewTask.id == review_task_id))
        task = r.scalar_one_or_none()
        if task is None:
            raise DiagnosisError(f"复习任务不存在: id={review_task_id}")

        # Record history
        history = ReviewHistory(
            review_task_id=task.id,
            level=task.level,
            review_date=datetime.now(timezone.utc),
            result=result,
        )
        db.add(history)

        if result:
            # Correct: level up
            task.level = min(task.level + 1, 6)
            if task.level >= 6:
                task.status = "completed"
            else:
                intervals = {1: 1, 2: 3, 3: 7, 4: 14, 5: 30}
                days = intervals.get(task.level, 30)
                task.next_review_date = datetime.now(timezone.utc) + timedelta(days=days)
        else:
            # Wrong: level down
            task.level = max(task.level - 1, 1)
            task.next_review_date = datetime.now(timezone.utc) + timedelta(days=1)

        await db.commit()
        await db.refresh(task)
        return ReviewTaskRead.model_validate(task)

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
