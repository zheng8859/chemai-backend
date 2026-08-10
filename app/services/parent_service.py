"""ParentService — 家长端业务逻辑：子女数据聚合 + 绑定管理 + 通知 CRUD。

从 HomeworkService 迁移绑定/通知方法至此，HomeworkService 保留教师端报告发送。
"""

import logging
from datetime import datetime, timezone, timedelta

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.enums import BindingStatus, NotificationType, PracticeSessionStatus
from ..models.user import Student, Parent
from ..models.homework import StudentParentBinding, ParentNotification, WeeklyReport
from ..models.org import Class, School, Grade
from ..models.teaching import PracticeSession
from ..schemas.homework import BindingCreate, BindingRead
from ..schemas.parent import (
    ChildInfo,
    ChildOverviewResponse,
    WeeklyTimelineItem,
    ChildTimelineResponse,
    ParentNotificationResponse,
)
from ..utils import get_current_week_start

logger = logging.getLogger(__name__)

# 通知保留天数
_NOTIFICATION_RETENTION_DAYS = 90


class ParentError(Exception):
    def __init__(self, detail: str, error_code: str = "RESOURCE_NOT_FOUND"):
        self.detail = detail
        self.error_code = error_code
        super().__init__(detail)


class ParentService:
    """家长端服务 — 所有方法均为 static method。"""

    # ═══════════════════════════════════════════════════════════
    # 绑定管理
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    async def create_binding(db: AsyncSession, parent_db_id: int, data) -> BindingRead:
        """创建亲子绑定（验证绑定码）。

        支持两种方式定位学生：
        1. 通过 data.student_id（兼容旧调用）
        2. 通过 data.bind_code 直接查找（前端新路径）
        """
        if data.student_id:
            # 通过 student_id 查找
            result = await db.execute(select(Student).where(Student.id == data.student_id))
            student = result.scalar_one_or_none()
            if student is None:
                raise ParentError(f"学生不存在: id={data.student_id}")
            if student.bind_code != data.bind_code:
                raise ParentError("绑定码无效", "INVALID_BIND_CODE")
        else:
            # 通过 bind_code 反向查找学生
            result = await db.execute(
                select(Student).where(Student.bind_code == data.bind_code)
            )
            student = result.scalar_one_or_none()
            if student is None:
                raise ParentError("绑定码无效，未找到对应学生", "INVALID_BIND_CODE")

        # 检查是否已存在 active 绑定
        existing = await db.execute(
            select(StudentParentBinding).where(
                StudentParentBinding.student_id == data.student_id,
                StudentParentBinding.parent_id == parent_db_id,
                StudentParentBinding.status == BindingStatus.active,
            )
        )
        if existing.scalar_one_or_none() is not None:
            raise ParentError("已绑定该学生", "ALREADY_BOUND")

        binding = StudentParentBinding(
            student_id=student.id,
            parent_id=parent_db_id,
            status=BindingStatus.active,
            relation=data.relation,
        )
        db.add(binding)
        await db.commit()
        await db.refresh(binding)
        return BindingRead.model_validate(binding)

    @staticmethod
    async def list_bound_children(db: AsyncSession, parent_db_id: int) -> list[ChildInfo]:
        """查询家长已绑定的子女列表（含班级、学校信息）。"""
        result = await db.execute(
            select(StudentParentBinding, Student, Class, School)
            .join(Student, Student.id == StudentParentBinding.student_id)
            .join(Class, Class.id == Student.class_id)
            .join(Grade, Grade.id == Class.grade_id)
            .join(School, School.id == Grade.school_id)
            .where(
                StudentParentBinding.parent_id == parent_db_id,
                StudentParentBinding.status == BindingStatus.active,
            )
        )
        rows = result.all()
        children = []
        for binding, student, class_, school in rows:
            children.append(ChildInfo(
                student_id=student.id,
                student_name=student.name,
                class_name=class_.name,
                school_name=school.name,
                relation=binding.relation,
                binding_id=binding.id,
            ))
        return children

    @staticmethod
    async def delete_binding(
        db: AsyncSession, binding_id: int, parent_db_id: int | None = None
    ) -> None:
        """删除亲子绑定。parent_db_id 非 None 时校验绑定归属。"""
        clause = [StudentParentBinding.id == binding_id]
        if parent_db_id is not None:
            clause.append(StudentParentBinding.parent_id == parent_db_id)
        result = await db.execute(
            select(StudentParentBinding).where(*clause)
        )
        binding = result.scalar_one_or_none()
        if binding is None:
            raise ParentError(f"绑定关系不存在或无权操作: id={binding_id}")
        await db.delete(binding)
        await db.commit()

    @staticmethod
    async def set_student_bind_code(
        db: AsyncSession, student_db_id: int, bind_code: str
    ) -> None:
        """学生设置/更新绑定码。"""
        result = await db.execute(select(Student).where(Student.id == student_db_id))
        student = result.scalar_one_or_none()
        if student is None:
            raise ParentError(f"学生不存在: id={student_db_id}")
        student.bind_code = bind_code
        await db.commit()

    # ═══════════════════════════════════════════════════════════
    # 子女学习数据查询
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    async def get_child_overview(
        db: AsyncSession, student_db_id: int
    ) -> ChildOverviewResponse:
        """获取子女学习概览：本周练习数、正确率、连续天数、薄弱点。"""
        now = datetime.now(timezone.utc)
        week_start = get_current_week_start(now)

        # 本周练习会话
        sessions_result = await db.execute(
            select(PracticeSession).where(
                PracticeSession.student_id == student_db_id,
                PracticeSession.status == PracticeSessionStatus.completed,
                PracticeSession.created_at >= week_start,
            )
        )
        sessions = sessions_result.scalars().all()
        weekly_practice_count = len(sessions)

        # 加权正确率
        from ..services.stats_service import StatsService
        accuracy = await StatsService._weighted_accuracy(db, student_db_id, now)
        streak = await StatsService._calc_streak_days(db, student_db_id, now)
        total_count = await StatsService._count_completed_sessions(db, student_db_id)

        # 学生信息和薄弱知识点
        student_result = await db.execute(
            select(Student).where(Student.id == student_db_id)
        )
        student = student_result.scalar_one_or_none()

        weak_kps = student.weak_knowledge_points if student and student.weak_knowledge_points else []
        # 将化学术语转换为通俗表述（家长端可读）
        if weak_kps:
            from ..utils import convert_chemical_terms_list
            weak_kps = convert_chemical_terms_list(weak_kps)
        last_practice = student.last_practice_time if student else None

        # 学习特点通俗描述 + 障碍画像
        characteristics = "暂无足够数据进行分析"
        barriers = None
        if student and student.barrier_profile:
            bp = student.barrier_profile
            parts = []
            concept = bp.get("concept", 0)
            reading = bp.get("reading", 0)
            expression = bp.get("expression", 0)

            barriers = dict(concept=concept, reading=reading, expression=expression)

            if concept >= 0.5:
                parts.append("在概念理解方面需要多花一些时间")
            elif concept >= 0.3:
                parts.append("概念理解正在稳步提升")
            else:
                parts.append("对概念的理解比较扎实")

            if reading >= 0.4:
                parts.append("读题时偶尔会漏看条件，建议多关注审题习惯")
            if expression >= 0.4:
                parts.append("在书写和表述方面有进步空间")

            if parts:
                characteristics = "。".join(parts) + "。"

        return ChildOverviewResponse(
            student_id=student_db_id,
            student_name=student.name if student else "",
            weekly_practice_count=weekly_practice_count,
            accuracy_rate=accuracy,
            streak_days=streak,
            total_practice_count=total_count,
            weak_knowledge_points=weak_kps,
            characteristics=characteristics,
            barriers=barriers,
            last_practice_time=last_practice,
        )

    @staticmethod
    async def get_child_timeline(
        db: AsyncSession, student_db_id: int, weeks: int = 4
    ) -> ChildTimelineResponse:
        """获取近 N 周每周学习时间线。"""
        now = datetime.now(timezone.utc)
        items = []

        for i in range(weeks - 1, -1, -1):
            week_end = now - timedelta(days=now.weekday() + i * 7 + 1)
            week_start = week_end - timedelta(days=6)
            week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)
            week_end = week_end.replace(hour=0, minute=0, second=0, microsecond=0)

            count_result = await db.execute(
                select(func.count(PracticeSession.id)).where(
                    PracticeSession.student_id == student_db_id,
                    PracticeSession.status == PracticeSessionStatus.completed,
                    PracticeSession.created_at >= week_start,
                    PracticeSession.created_at < week_end,
                )
            )
            count = count_result.scalar() or 0

            items.append(WeeklyTimelineItem(
                week_start=week_start.date(),
                week_end=(week_end - timedelta(days=1)).date(),
                practice_count=count,
                accuracy=None,  # 聚合查询较复杂，预留
                topics_covered=[],
            ))

        return ChildTimelineResponse(student_id=student_db_id, weeks=items)

    # ═══════════════════════════════════════════════════════════
    # 通知管理
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    async def create_notification(
        db: AsyncSession,
        parent_db_id: int,
        notification_type: str,
        title: str,
        body: str,
        related_id: int | None = None,
    ) -> ParentNotificationResponse:
        """创建家长通知。"""
        notif = ParentNotification(
            parent_id=parent_db_id,
            notification_type=notification_type,
            title=title,
            body=body,
            related_id=related_id,
            sent_at=datetime.now(timezone.utc),
        )
        db.add(notif)
        await db.commit()
        await db.refresh(notif)
        return ParentNotificationResponse.model_validate(notif)

    @staticmethod
    async def list_notifications(
        db: AsyncSession, parent_db_id: int,
        limit: int = 20, offset: int = 0,
    ) -> tuple[list[ParentNotificationResponse], int]:
        """获取家长通知列表（90 天保留）。"""
        now = datetime.now(timezone.utc)
        since = now - timedelta(days=_NOTIFICATION_RETENTION_DAYS)

        total_result = await db.execute(
            select(func.count(ParentNotification.id)).where(
                ParentNotification.parent_id == parent_db_id,
                ParentNotification.sent_at >= since,
            )
        )
        total = total_result.scalar() or 0

        result = await db.execute(
            select(ParentNotification)
            .where(
                ParentNotification.parent_id == parent_db_id,
                ParentNotification.sent_at >= since,
            )
            .order_by(ParentNotification.sent_at.desc())
            .offset(offset).limit(limit)
        )
        return [
            ParentNotificationResponse.model_validate(n)
            for n in result.scalars().all()
        ], total

    @staticmethod
    async def mark_notification_read(
        db: AsyncSession, notification_id: int, parent_db_id: int,
    ) -> ParentNotificationResponse:
        """标记通知为已读（校验通知归属）。"""
        result = await db.execute(
            select(ParentNotification).where(
                ParentNotification.id == notification_id,
                ParentNotification.parent_id == parent_db_id,
            )
        )
        notif = result.scalar_one_or_none()
        if notif is None:
            raise ParentError(f"通知不存在或无权操作: id={notification_id}")
        notif.read_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(notif)
        return ParentNotificationResponse.model_validate(notif)
