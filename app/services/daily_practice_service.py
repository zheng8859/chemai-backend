"""每日练习调度器 — 08:00 UTC Cron 触发，银行优先 + LLM 补足。

设计文档 tasks.md §3.13-3.15。
"""

import logging
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..models.user import Student
from ..models.homework import StudentParentBinding, ParentNotification
from ..models.teaching import Question, PracticeSession, PracticeSessionQuestion
from ..models.diagnosis import ReviewTask
from ..core.enums import (
    StudentStatus,
    PracticeSessionStatus,
    QuestionSource,
    NotificationType,
)

from chem_skills.chemistry_memory.zpd_engine import identify_dominant_barrier
from chem_skills.chemistry_memory.strategy_matrix import apply_strategy

logger = logging.getLogger(__name__)


class DailyPracticeError(Exception):
    """每日练习调度器异常。"""
    def __init__(self, detail: str, error_code: str = "DAILY_PRACTICE_ERROR"):
        self.detail = detail
        self.error_code = error_code
        super().__init__(detail)


class DailyPracticeService:
    """每日练习调度器。

    所有方法均为 static method，db 由调用方传入。
    """

    # ═══════════════════════════════════════════════════════════
    # 3.14 run_daily_scheduler
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    @staticmethod
    async def run_daily_scheduler(
        db: AsyncSession,
        question_count: int = 5,
        batch_size: int = 5,
    ) -> dict:
        """执行每日练习调度（08:00 / 20:00 CST Cron 触发）。

        流程：
        1. 查询所有已审批（approved）学生
        2. 按 batch_size（默认 5）分批处理
        3. 逐生计算：障碍 → 策略 → 目标知识点 → 题库检索
        4. 每批完成后 commit，避免长事务锁库
        5. 创建 PracticeSession + PracticeSessionQuestion 记录

        Args:
            db: 数据库会话
            question_count: 每生日练习题数（默认 5）
            batch_size: 每批处理学生数（默认 5）

        Returns:
            {
                "success": True,
                "total_students": int,
                "assigned_count": int,
                "batches": int,
                "details": [...],
            }
        """
        # Step 1: 查询所有已审批学生
        result = await db.execute(
            select(Student).where(Student.status == StudentStatus.approved.value)
        )
        students = result.scalars().all()

        if not students:
            logger.info("run_daily_scheduler: 无已审批学生，跳过")
            return {
                "success": True,
                "total_students": 0,
                "assigned_count": 0,
                "batches": 0,
                "details": [],
            }

        assigned_count = 0
        details = []
        batch_count = 0

        # 分批处理，每批最多 batch_size 人
        for i in range(0, len(students), batch_size):
            batch = students[i:i + batch_size]
            batch_count += 1

            for student in batch:
                try:
                    practice_info = await DailyPracticeService._assign_daily_practice(
                        db, student, question_count
                    )
                    if practice_info:
                        details.append(practice_info)
                        assigned_count += 1
                except Exception as e:
                    logger.error(
                        "为学生 %d 分配每日练习失败: %s", student.id, str(e)
                    )

            # 每批完成后立即 commit
            await db.commit()
            logger.info(
                "run_daily_scheduler 批次 %d: %d 名学生已处理",
                batch_count, len(batch),
            )

        logger.info(
            "run_daily_scheduler 完成: %d/%d 名学生已分配，共 %d 批",
            assigned_count, len(students), batch_count,
        )

        return {
            "success": True,
            "total_students": len(students),
            "assigned_count": assigned_count,
            "batches": batch_count,
            "details": details,
        }

    @staticmethod
    async def _assign_daily_practice(
        db: AsyncSession,
        student: Student,
        count: int,
    ) -> dict | None:
        """为单个学生分配每日练习。

        Returns:
            分配信息 dict，若无可分配题目则返回 None。
        """
        # 障碍 → 策略 → 目标知识点
        barrier_profile = student.barrier_profile
        weak_kps = student.weak_knowledge_points or []

        if not weak_kps:
            # 从错题记录推导（复用 AdaptivePracticeService 的共享逻辑）
            from .adaptive_practice_service import AdaptivePracticeService
            weak_kps = await AdaptivePracticeService._derive_weak_kps(db, student.id)

        dominant_barrier = identify_dominant_barrier(barrier_profile)
        strategy = apply_strategy(dominant_barrier, "medium")  # 每日练习默认 medium
        target_difficulty = strategy["difficulty"]

        # 题库检索（银行优先）
        questions = await DailyPracticeService._fetch_from_bank(
            db, weak_kps, target_difficulty, count
        )

        if not questions:
            logger.info("学生 %d 无匹配题目，跳过", student.id)
            return None

        # 创建 PracticeSession（每日练习）
        import uuid as _uuid
        practice_id = f"PR-{_uuid.uuid4().hex[:12].upper()}"
        session = PracticeSession(
            practice_id=practice_id,
            student_id=student.id,
            title=f"每日练习 - {datetime.now(timezone.utc).strftime('%Y-%m-%d')}",
            barrier_type=dominant_barrier,
            status=PracticeSessionStatus.in_progress.value,
            question_count=len(questions),
            knowledge_point_tags=weak_kps[:5],
        )
        db.add(session)
        await db.flush()

        # 关联题目到 PracticeSession
        for idx, q in enumerate(questions):
            psq = PracticeSessionQuestion(
                practice_session_id=session.id,
                question_id=q["id"],
                sort_order=idx + 1,
            )
            db.add(psq)

        return {
            "student_id": student.id,
            "student_name": student.name,
            "practice_id": practice_id,
            "question_count": len(questions),
            "target_kps": weak_kps[:3],
            "difficulty": target_difficulty,
        }

    # ═══════════════════════════════════════════════════════════
    # 3.15 notify_parents_of_overdue_reviews
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    async def notify_parents_of_overdue_reviews(
        db: AsyncSession,
    ) -> dict:
        """检查逾期复习任务，通知绑定家长。

        流程：
        1. 查询所有逾期 ReviewTask（status=pending, next_review_date < now）
        2. 按学生分组计数
        3. 查找每个学生的绑定家长
        4. 创建 ParentNotification 记录
           （当前版本：记录日志，等通知引擎就绪后替换）

        Returns:
            {
                "success": True,
                "overdue_count": int,
                "affected_students": int,
                "notifications_created": int,
            }
        """
        now = datetime.now(timezone.utc)

        # 查询逾期任务
        overdue_result = await db.execute(
            select(ReviewTask).where(
                ReviewTask.status == "pending",
                ReviewTask.next_review_date < now,
            )
        )
        overdue_tasks = overdue_result.scalars().all()

        if not overdue_tasks:
            return {
                "success": True,
                "overdue_count": 0,
                "affected_students": 0,
                "notifications_created": 0,
            }

        # 按学生分组计数
        student_overdue: dict[int, int] = {}
        for task in overdue_tasks:
            student_overdue[task.student_id] = (
                student_overdue.get(task.student_id, 0) + 1
            )

        # 更新 ReviewTask status 为 overdue
        for task in overdue_tasks:
            task.status = "overdue"

        # 查找绑定家长并创建通知
        notifications_created = 0
        for student_id, count in student_overdue.items():
            # 查询学生姓名
            student = (await db.execute(
                select(Student).where(Student.id == student_id)
            )).scalar_one_or_none()
            student_name = student.name if student else f"学生#{student_id}"

            # 查询绑定家长
            relations = await db.execute(
                select(StudentParentBinding).where(
                    StudentParentBinding.student_id == student_id,
                    StudentParentBinding.status == "active",
                )
            )
            for rel in relations.scalars().all():
                notification = ParentNotification(
                    parent_id=rel.parent_id,
                    notification_type=NotificationType.warning_alert,
                    title="复习任务逾期提醒",
                    body=(
                        f"您的孩子 {student_name} 有 {count} 道题目"
                        f"已超过复习时间，请督促孩子登录系统完成复习。"
                    ),
                )
                db.add(notification)
                notifications_created += 1

        await db.commit()

        return {
            "success": True,
            "overdue_count": len(overdue_tasks),
            "affected_students": len(student_overdue),
            "notifications_created": notifications_created,
        }

    # ═══════════════════════════════════════════════════════════
    # 内部辅助
    @staticmethod
    async def _fetch_from_bank(
        db: AsyncSession,
        kps: list[str],
        difficulty: str,
        count: int,
    ) -> list[dict]:
        """从题库检索题目（向量优先 + SQL 回退）。

        三层检索策略：
        1. SQL 难度筛选 → 候选集
        2. ChromaDB 向量语义重排序（可用时）
        3. 无向量时随机采样
        """
        # Step 1: SQL 难度筛选（候选集）
        result = await db.execute(
            select(Question)
            .where(Question.difficulty == difficulty)
            .limit(count * 10)  # 取更多候选供向量精排
        )
        candidates = result.scalars().all()

        if not candidates:
            return []

        # Step 2: 向量语义重排序（ChromaDB 可用时）
        if kps:
            from .vector_search_service import search_questions_vector
            try:
                candidates = await search_questions_vector(
                    list(candidates), kps, limit=count,
                )
            except Exception:
                # 向量搜索失败 → 随机采样
                import random
                random.shuffle(candidates)
                candidates = candidates[:count]
        else:
            # 无知识点 → 随机采样
            import random
            random.shuffle(candidates)
            candidates = candidates[:count]

        return [
            {
                "id": q.id,
                "content": q.content,
                "question_type": q.question_type,
                "options": q.options,
                "answer": q.answer,
                "analysis": q.analysis,
                "difficulty": q.difficulty,
                "knowledge_point_tags": q.knowledge_point_tags,
            }
            for q in candidates[:count]
        ]
