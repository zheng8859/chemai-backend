"""NotificationService — 学生消息通知 CRUD + best-effort 写入。

通知由教师操作自动触发（布置练习、发送学习计划），非手动发送。
写入策略：best-effort，失败不阻塞父操作。
保留策略：30 天。
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.notification import Notification
from ..schemas.notification import NotificationResponse

logger = logging.getLogger(__name__)


class NotificationService:
    """消息通知服务 — 纯 DB CRUD。"""

    # 通知类型常量
    TYPE_PRACTICE_ASSIGNED = "practice_assigned"
    TYPE_PLAN_UPDATED = "plan_updated"
    TYPE_REPORT_READY = "report_ready"

    # ── 写入 ──

    @staticmethod
    async def create_notification(
        db: AsyncSession,
        student_id: int,  # 数据库 Student.id
        type_: str,
        title: str,
        body: str,
        related_id: Optional[int] = None,
    ) -> Optional[NotificationResponse]:
        """创建通知（best-effort：失败时仅 log 不抛异常）。

        Args:
            db: 异步数据库会话
            student_id: Student 主键
            type_: 通知类型
            title: 通知标题
            body: 通知正文
            related_id: 关联资源 ID

        Returns:
            NotificationResponse 或 None（写入失败时）
        """
        try:
            notification = Notification(
                student_id=student_id,
                type=type_,
                title=title,
                body=body,
                related_id=related_id,
            )
            db.add(notification)
            await db.commit()
            await db.refresh(notification)
            return NotificationResponse.model_validate(notification)
        except Exception:
            logger.warning(
                "通知写入失败（best-effort）: student_id=%d type=%s",
                student_id, type_, exc_info=True,
            )
            return None

    @staticmethod
    async def create_notification_best_effort(
        db: AsyncSession,
        student_id: int,
        type_: str,
        title: str,
        body: str,
        related_id: Optional[int] = None,
    ) -> None:
        """创建通知的 fire-and-forget 版本 — 调用方无需关心结果。"""
        try:
            notification = Notification(
                student_id=student_id,
                type=type_,
                title=title,
                body=body,
                related_id=related_id,
            )
            db.add(notification)
            await db.commit()
        except Exception:
            logger.warning(
                "通知写入失败（best-effort）: student_id=%d type=%s",
                student_id, type_, exc_info=True,
            )

    # ── 读取 ──

    @staticmethod
    async def get_student_notifications(
        db: AsyncSession,
        student_id: int,  # 数据库 Student.id
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[NotificationResponse], int]:
        """获取学生通知列表（分页，仅 30 天内）。

        Args:
            db: 异步数据库会话
            student_id: Student 主键
            limit: 每页条数
            offset: 偏移量

        Returns:
            (通知列表, 总数)
        """
        now = datetime.now(timezone.utc)
        since = now - timedelta(days=30)

        # 总数
        count_result = await db.execute(
            select(func.count(Notification.id)).where(
                Notification.student_id == student_id,
                Notification.created_at >= since,
            )
        )
        total = count_result.scalar() or 0

        # 列表
        result = await db.execute(
            select(Notification)
            .where(
                Notification.student_id == student_id,
                Notification.created_at >= since,
            )
            .order_by(Notification.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        notifications = result.scalars().all()
        return [
            NotificationResponse.model_validate(n) for n in notifications
        ], total

    # ── 标记已读 ──

    @staticmethod
    async def mark_as_read(
        db: AsyncSession,
        notification_id: int,
        student_id: int,  # 数据库 Student.id（权限校验）
    ) -> Optional[NotificationResponse]:
        """标记通知为已读。

        Args:
            db: 异步数据库会话
            notification_id: 通知 ID
            student_id: 当前学生 Student.id

        Returns:
            NotificationResponse 或 None（通知不存在/不属于该学生）
        """
        result = await db.execute(
            select(Notification).where(Notification.id == notification_id)
        )
        notification = result.scalar_one_or_none()
        if notification is None:
            return None
        if notification.student_id != student_id:
            return None  # 不属于当前学生

        notification.read_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(notification)
        return NotificationResponse.model_validate(notification)
