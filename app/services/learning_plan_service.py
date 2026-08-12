"""LearningPlanService — 学习计划 CRUD + 任务完成标记。

教师通过 Agent 为学生创建结构化学习计划，学生端只读 + 标记任务完成。
核心约束：一个学生同时只有一份活跃计划（is_active=true）。
"""

import logging
from datetime import datetime, timezone

from sqlalchemy import select, update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..models.learning_plan import LearningPlan, LearningPlanTask
from ..models.user import Student
from ..api.deps import resolve_student_id
from ..schemas.learning_plan import (
    LearningPlanCreate,
    LearningPlanUpdate,
    LearningPlanResponse,
    LearningPlanTaskResponse,
)

logger = logging.getLogger(__name__)


class LearningPlanError(Exception):
    def __init__(self, detail: str, error_code: str = "RESOURCE_NOT_FOUND"):
        self.detail = detail
        self.error_code = error_code
        super().__init__(detail)


class LearningPlanService:
    """学习计划服务 — 纯 DB CRUD，不含通知钩子（通知由调用方或钩子触发）。"""

    @staticmethod
    async def create_plan(
        db: AsyncSession,
        data: LearningPlanCreate,
        teacher_account_id: int,
    ) -> LearningPlanResponse:
        """教师创建学习计划（自动归档同学生旧计划）。

        Args:
            db: 异步数据库会话
            data: 创建请求（含 student_id=Account.id、title、tasks）
            teacher_account_id: 当前教师 Account.id（用于记录 created_by）

        Returns:
            新创建的 LearningPlanResponse（含任务列表）
        """
        # Account.id → Student.id 映射
        student_db_id = await resolve_student_id(db, data.student_id)
        if student_db_id is None:
            raise LearningPlanError(f"学生不存在: account_id={data.student_id}")

        # 归档旧活跃计划
        await db.execute(
            sa_update(LearningPlan)
            .where(
                LearningPlan.student_id == student_db_id,
                LearningPlan.is_active == True,  # noqa: E712
            )
            .values(is_active=False)
        )

        # 创建新计划
        plan = LearningPlan(
            student_id=student_db_id,
            title=data.title,
            is_active=True,
            created_by=data.created_by or "teacher",
        )
        db.add(plan)
        await db.flush()  # 获取 plan.id

        # 创建关联任务
        task_objs = []
        for t in data.tasks:
            task = LearningPlanTask(
                plan_id=plan.id,
                day_number=t.day_number,
                task_description=t.task_description,
                estimated_minutes=t.estimated_minutes,
                knowledge_points=t.knowledge_points,
            )
            db.add(task)
            task_objs.append(task)

        await db.commit()

        # 重新加载以获取 created_at/updated_at
        await db.refresh(plan)
        for t in task_objs:
            await db.refresh(t)

        # Best-effort 通知写入
        try:
            from .notification_service import NotificationService
            await NotificationService.create_notification_best_effort(
                db,
                student_id=student_db_id,
                type_=NotificationService.TYPE_PLAN_UPDATED,
                title="学习计划已更新",
                body=f"教师为你创建了学习计划：{plan.title}",
                related_id=plan.id,
            )
        except Exception:
            pass

        # Store 写入（best-effort）
        try:
            from ..agent.store import write_learning_plan_summary
            await write_learning_plan_summary(
                db,
                student_id=student_db_id,
                plan_id=plan.id,
                title=plan.title,
                task_count=len(task_objs),
            )
        except Exception:
            pass

        return LearningPlanResponse(
            id=plan.id,
            student_id=plan.student_id,
            title=plan.title,
            is_active=plan.is_active,
            created_by=plan.created_by,
            tasks=[LearningPlanTaskResponse.model_validate(t) for t in task_objs],
            created_at=plan.created_at,
            updated_at=plan.updated_at,
        )

    @staticmethod
    async def update_plan(
        db: AsyncSession,
        plan_id: int,
        data: LearningPlanUpdate,
    ) -> LearningPlanResponse:
        """教师更新学习计划（全量替换任务列表）。

        Args:
            db: 异步数据库会话
            plan_id: 计划 ID
            data: 更新请求（title + tasks 均可选，全量替换）

        Returns:
            更新后的 LearningPlanResponse
        """
        # 查询计划
        result = await db.execute(
            select(LearningPlan)
            .where(LearningPlan.id == plan_id)
            .options(selectinload(LearningPlan.tasks))
        )
        plan = result.scalar_one_or_none()
        if plan is None:
            raise LearningPlanError(f"学习计划不存在: id={plan_id}")

        # 更新标题
        if data.title is not None:
            plan.title = data.title

        # 全量替换任务列表
        if data.tasks is not None:
            # 删除旧任务
            for old_task in list(plan.tasks):
                await db.delete(old_task)
            await db.flush()

            # 创建新任务
            new_tasks = []
            for t in data.tasks:
                task = LearningPlanTask(
                    plan_id=plan.id,
                    day_number=t.day_number,
                    task_description=t.task_description,
                    estimated_minutes=t.estimated_minutes,
                    knowledge_points=t.knowledge_points,
                )
                db.add(task)
                new_tasks.append(task)

        await db.commit()

        # 重新加载
        await db.refresh(plan)
        # 重新加载任务列表
        tasks_result = await db.execute(
            select(LearningPlanTask)
            .where(LearningPlanTask.plan_id == plan.id)
            .order_by(LearningPlanTask.day_number, LearningPlanTask.id)
        )
        tasks = tasks_result.scalars().all()

        # Best-effort 通知写入
        try:
            from .notification_service import NotificationService
            await NotificationService.create_notification_best_effort(
                db,
                student_id=plan.student_id,
                type_=NotificationService.TYPE_PLAN_UPDATED,
                title="学习计划已更新",
                body=f"你的学习计划已更新：{plan.title}",
                related_id=plan.id,
            )
        except Exception:
            pass

        # Store 写入（best-effort）
        try:
            from ..agent.store import write_learning_plan_summary
            await write_learning_plan_summary(
                db,
                student_id=plan.student_id,
                plan_id=plan.id,
                title=plan.title,
                task_count=len(tasks),
            )
        except Exception:
            pass

        return LearningPlanResponse(
            id=plan.id,
            student_id=plan.student_id,
            title=plan.title,
            is_active=plan.is_active,
            created_by=plan.created_by,
            tasks=[LearningPlanTaskResponse.model_validate(t) for t in tasks],
            created_at=plan.created_at,
            updated_at=plan.updated_at,
        )

    @staticmethod
    async def get_active_plan(
        db: AsyncSession,
        student_db_id: int,  # 数据库 Student.id
    ) -> LearningPlanResponse | None:
        """学生获取当前活跃学习计划。

        Args:
            db: 异步数据库会话
            student_db_id: Student 主键（数据库 ID）

        Returns:
            LearningPlanResponse 或 None（无活跃计划时）
        """
        result = await db.execute(
            select(LearningPlan)
            .where(
                LearningPlan.student_id == student_db_id,
                LearningPlan.is_active == True,  # noqa: E712
            )
            .options(selectinload(LearningPlan.tasks))
        )
        plan = result.scalar_one_or_none()
        if plan is None:
            return None

        # 按 day_number + id 排序
        sorted_tasks = sorted(plan.tasks, key=lambda t: (t.day_number, t.id))

        return LearningPlanResponse(
            id=plan.id,
            student_id=plan.student_id,
            title=plan.title,
            is_active=plan.is_active,
            created_by=plan.created_by,
            tasks=[LearningPlanTaskResponse.model_validate(t) for t in sorted_tasks],
            created_at=plan.created_at,
            updated_at=plan.updated_at,
        )

    @staticmethod
    async def mark_task_complete(
        db: AsyncSession,
        task_id: int,
        student_db_id: int,  # 数据库 Student.id
    ) -> LearningPlanTaskResponse:
        """学生标记任务为已完成。

        Args:
            db: 异步数据库会话
            task_id: 任务 ID
            student_db_id: 当前学生 Student.id（用于权限校验）

        Returns:
            更新后的 LearningPlanTaskResponse

        Raises:
            LearningPlanError: 任务不存在 / 非当前学生任务 / 已完成
        """
        # 查询任务及其所属计划
        result = await db.execute(
            select(LearningPlanTask)
            .join(LearningPlan, LearningPlan.id == LearningPlanTask.plan_id)
            .where(LearningPlanTask.id == task_id)
        )
        task = result.scalar_one_or_none()
        if task is None:
            raise LearningPlanError(f"任务不存在: id={task_id}")

        # 重新查询以获取 plan 关联
        result2 = await db.execute(
            select(LearningPlanTask)
            .options(selectinload(LearningPlanTask.plan))
            .where(LearningPlanTask.id == task_id)
        )
        task = result2.scalar_one_or_none()

        # 校验 student_id
        if task.plan.student_id != student_db_id:
            raise LearningPlanError(
                "无权操作其他学生的任务", error_code="FORBIDDEN"
            )

        # 校验状态
        if task.status == "completed":
            raise LearningPlanError(
                "任务已完成", error_code="CONFLICT"
            )

        task.status = "completed"
        task.completed_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(task)

        return LearningPlanTaskResponse.model_validate(task)
