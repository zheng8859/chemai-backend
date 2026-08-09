"""Home-school service — 亲子绑定/通知/报告发送。

⚠ *Deprecated* — 绑定/通知方法已迁移至 ParentService。
  教师端报告发送（send_exam_reports）继续保留。
"""

from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from ..core.enums import BindingStatus, NotificationType
from ..models.homework import StudentParentBinding, ParentNotification
from ..models.user import Student
from ..schemas.homework import (
    BindingCreate, BindingRead, ParentNotificationRead,
)


class HomeworkError(Exception):
    def __init__(self, detail: str, error_code: str = "RESOURCE_NOT_FOUND"):
        self.detail = detail
        self.error_code = error_code
        super().__init__(detail)


class HomeworkService:

    # ═══════════════════════════════════════════════════════════
    # Bindings (⚠ Deprecated → ParentService)
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    async def create_binding(db: AsyncSession, data: BindingCreate) -> BindingRead:
        """⚠ Deprecated: 请使用 ParentService.create_binding()"""
        # Validate bind_code
        result = await db.execute(select(Student).where(Student.id == data.student_id))
        student = result.scalar_one_or_none()
        if student is None:
            raise HomeworkError(f"学生不存在: id={data.student_id}")
        if student.bind_code != data.bind_code:
            raise HomeworkError("绑定码无效", "INVALID_BIND_CODE")

        binding = StudentParentBinding(
            student_id=data.student_id,
            parent_id=data.parent_id,
            status=BindingStatus.active,
            relation=data.relation,
        )
        db.add(binding)
        await db.commit()
        await db.refresh(binding)
        return BindingRead.model_validate(binding)

    @staticmethod
    async def list_bindings_by_parent(
        db: AsyncSession, parent_id: int,
    ) -> list[BindingRead]:
        """⚠ Deprecated: 请使用 ParentService.list_bound_children()"""
        result = await db.execute(
            select(StudentParentBinding).where(
                StudentParentBinding.parent_id == parent_id,
                StudentParentBinding.status == BindingStatus.active,
            )
        )
        return [BindingRead.model_validate(b) for b in result.scalars().all()]

    @staticmethod
    async def list_bindings_by_student(
        db: AsyncSession, student_id: int,
    ) -> list[BindingRead]:
        """⚠ Deprecated: 请使用 ParentService (无直接对应，学生端查询)"""
        result = await db.execute(
            select(StudentParentBinding).where(
                StudentParentBinding.student_id == student_id,
            )
        )
        return [BindingRead.model_validate(b) for b in result.scalars().all()]

    @staticmethod
    async def delete_binding(db: AsyncSession, binding_id: int) -> None:
        """⚠ Deprecated: 请使用 ParentService.delete_binding()"""
        result = await db.execute(
            select(StudentParentBinding).where(StudentParentBinding.id == binding_id)
        )
        binding = result.scalar_one_or_none()
        if binding is None:
            raise HomeworkError(f"绑定关系不存在: id={binding_id}")
        await db.delete(binding)
        await db.commit()

    # ═══════════════════════════════════════════════════════════
    # Notifications (⚠ Deprecated → ParentService)
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    async def create_notification(
        db: AsyncSession,
        parent_id: int,
        notification_type: str,
        title: str,
        body: str,
    ) -> ParentNotificationRead:
        """⚠ Deprecated: 请使用 ParentService.create_notification()"""
        notif = ParentNotification(
            parent_id=parent_id,
            notification_type=notification_type,
            title=title,
            body=body,
            sent_at=datetime.now(timezone.utc),
        )
        db.add(notif)
        await db.commit()
        await db.refresh(notif)
        return ParentNotificationRead.model_validate(notif)

    @staticmethod
    async def list_notifications_by_parent(
        db: AsyncSession, parent_id: int,
        limit: int = 20, offset: int = 0,
    ) -> tuple[list[ParentNotificationRead], int]:
        """⚠ Deprecated: 请使用 ParentService.list_notifications()"""
        total = (await db.execute(
            select(func.count(ParentNotification.id)).where(
                ParentNotification.parent_id == parent_id,
            )
        )).scalar() or 0
        result = await db.execute(
            select(ParentNotification)
            .where(ParentNotification.parent_id == parent_id)
            .order_by(ParentNotification.sent_at.desc())
            .offset(offset).limit(limit)
        )
        return [ParentNotificationRead.model_validate(n) for n in result.scalars().all()], total

    @staticmethod
    async def mark_notification_read(
        db: AsyncSession, notification_id: int,
    ) -> ParentNotificationRead:
        """⚠ Deprecated: 请使用 ParentService.mark_notification_read()"""
        result = await db.execute(
            select(ParentNotification).where(ParentNotification.id == notification_id)
        )
        notif = result.scalar_one_or_none()
        if notif is None:
            raise HomeworkError(f"通知不存在: id={notification_id}")
        notif.read_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(notif)
        return ParentNotificationRead.model_validate(notif)

    # ═══════════════════════════════════════════════════════════
    # Reports
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    async def send_exam_reports(db: AsyncSession, exam_id: int) -> dict:
        """发送考试报告给所有绑定家长（stub — 实际报告生成在后续阶段实现）。"""
        sent = 0
        failed = 0
        return {
            "success": True,
            "sent_count": sent,
            "failed_count": failed,
            "parent_notifications_sent": sent,
        }
