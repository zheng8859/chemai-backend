"""EarlyWarningService — 四类预警自动检测引擎。

设计决策（CONTEXT.md §八）：
- score_drop 仅取 ExamRecord（考试成绩），不纳入 PracticeSession
- 去重逻辑：同一学生同类型未处理预警存在时不重复生成
- new_barrier 检测需要 BarrierProfileHistory 历史快照作为基线
- 归一化：S_normalized = S_raw / max(S_raw_barriers_in_class)
- 各规则异常隔离：单条规则失败不影响其他规则

定时调度：每天 00:00（Asia/Shanghai）由 APScheduler 触发。
手动触发：POST /api/v1/warning/check 异步执行。
"""

import asyncio
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta

from sqlalchemy import select, func, Integer
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.user import Student
from ..models.teaching import ExamRecord, StudentAnswer, Question
from ..models.diagnosis import WarningLog
from ..models.barrier_profile_history import BarrierProfileHistory
from ..core.enums import (
    WarningType,
    WarningSeverity,
    ExamRecordStatus,
    BarrierType,
)

logger = logging.getLogger(__name__)

# ── 阈值常量 ──────────────────────────────────────────────────
ABSENCE_DAYS = 3            # 连续未登录天数阈值
SCORE_DROP_RATE = 0.10      # 成绩下滑比例阈值（10%）
HIGH_ERROR_RATE_WARNING = 0.50  # 高错误率 warning 阈值
HIGH_ERROR_RATE_SEVERE = 0.70   # 高错误率 severe 阈值
NEW_BARRIER_SHIFT = 0.30    # 新障碍归一化得分变化阈值（30%）


@dataclass
class WarningResult:
    """预警检测结果。"""
    student_id: int
    warning_type: str
    severity: str
    title: str
    message: str
    data: dict = field(default_factory=dict)


class EarlyWarningService:
    """四类预警自动检测服务。"""

    # ── 互斥锁：防 cron + 手动 API 并发重复检测 ─────────────────
    _check_lock = asyncio.Lock()

    # ═══════════════════════════════════════════════════════════
    # 3.6 run_all_checks orchestrator
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    async def run_all_checks(
        db: AsyncSession,
        skip_if_locked: bool = False,
    ) -> dict:
        """遍历所有活跃学生，运行四类检测规则，去重后批量写入。

        通过模块级 asyncio.Lock 防 cron + 手动 API 并发重复检测。

        Args:
            skip_if_locked: True 时若锁已被持有则静默跳过（cron 使用）；
                            False 时阻塞等待（手动 API 使用，调用方应先检查锁状态返回 429）。

        Returns:
            {"total_students": N, "new_warnings": N,
             "by_type": {...}, "errors": N}
        """
        if skip_if_locked and EarlyWarningService._check_lock.locked():
            logger.info("预警检测已在运行中，跳过本次 cron 触发")
            return {
                "total_students": 0, "new_warnings": 0,
                "by_type": {}, "errors": 0, "skipped": True,
            }

        async with EarlyWarningService._check_lock:
            return await EarlyWarningService._run_all_checks_impl(db)

    @staticmethod
    async def _run_all_checks_impl(db: AsyncSession) -> dict:
        """run_all_checks 的实际实现（调用方已持有 _check_lock）。"""
        # 获取所有已审批学生
        st_result = await db.execute(
            select(Student).where(Student.status == "approved")
        )
        students = st_result.scalars().all()

        all_warnings: list[WarningResult] = []
        error_count = 0

        for student in students:
            try:
                warnings = await EarlyWarningService._check_student(db, student)
                all_warnings.extend(warnings)
            except Exception:
                logger.exception(
                    "学生 %d 预警检测异常，跳过", student.id
                )
                error_count += 1

        # 去重：同一学生同类型未处理预警存在时不重复生成
        new_warnings = await EarlyWarningService._deduplicate(db, all_warnings)

        # 批量写入 WarningLog
        for w in new_warnings:
            warning_log = WarningLog(
                student_id=w.student_id,
                warning_type=WarningType(w.warning_type),
                severity=WarningSeverity(w.severity),
                title=w.title,
                message=w.message,
                data=w.data,
                status="pending",
            )
            db.add(warning_log)

        # 更新 BarrierProfileHistory 快照（为下次 new_barrier 检测准备基线）
        await EarlyWarningService._snapshot_barrier_profiles(db, students)

        await db.commit()

        by_type = defaultdict(int)
        for w in new_warnings:
            by_type[w.warning_type] += 1

        logger.info(
            "预警检测完成: %d 名学生, %d 条新预警, %d 次异常",
            len(students), len(new_warnings), error_count,
        )

        return {
            "total_students": len(students),
            "new_warnings": len(new_warnings),
            "by_type": dict(by_type),
            "errors": error_count,
        }

    # ═══════════════════════════════════════════════════════════
    # 3.7 异步后台任务包装器
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    async def run_async_check():
        """异步后台执行预警检测（供手动触发 API 使用）。

        通过 MainSession 创建独立数据库会话，不依赖请求上下文。
        """
        from ..infrastructure.database import MainSession

        logger.info("[warning] 手动触发预警检测开始")
        try:
            async with MainSession() as db:
                result = await EarlyWarningService.run_all_checks(db)
            logger.info(
                "[warning] 手动触发完成: students=%d, warnings=%d",
                result["total_students"], result["new_warnings"],
            )
            return result
        except Exception:
            logger.exception("[warning] 手动触发预警检测失败")
            return {
                "total_students": 0,
                "new_warnings": 0,
                "by_type": {},
                "errors": 1,
            }

    # ═══════════════════════════════════════════════════════════
    # 单个学生检测入口
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    async def _check_student(
        db: AsyncSession,
        student: Student,
    ) -> list[WarningResult]:
        """对单个学生运行全部四类检测规则。"""
        results: list[WarningResult] = []

        # 3.2 连续未登录
        r = EarlyWarningService._check_consecutive_absence(student)
        if r:
            results.append(r)

        # 3.3 成绩下滑
        r = await EarlyWarningService._check_score_drop(db, student)
        if r:
            results.append(r)

        # 3.4 高错误率
        warnings = await EarlyWarningService._check_high_error_rate(db, student)
        results.extend(warnings)

        # 3.5 新障碍出现
        r = await EarlyWarningService._check_new_barrier(db, student)
        if r:
            results.append(r)

        return results

    # ═══════════════════════════════════════════════════════════
    # 3.2 连续未登录检测
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    def _check_consecutive_absence(student: Student) -> WarningResult | None:
        """连续未登录 ≥ 3 天 → info 预警。"""
        if student.last_practice_time is None:
            return None  # 新学生无练习记录，不预警

        now = datetime.now(timezone.utc)
        delta = now - student.last_practice_time.replace(tzinfo=timezone.utc)
        if delta.days >= ABSENCE_DAYS:
            return WarningResult(
                student_id=student.id,
                warning_type=WarningType.consecutive_absence.value,
                severity=WarningSeverity.info.value,
                title="连续未登录",
                message=(
                    f"学生 {student.name} 已连续 {delta.days} 天未登录练习，"
                    f"最近练习时间：{student.last_practice_time.strftime('%Y-%m-%d %H:%M')}"
                ),
                data={
                    "last_practice_time": student.last_practice_time.isoformat(),
                    "absent_days": delta.days,
                },
            )
        return None

    # ═══════════════════════════════════════════════════════════
    # 3.3 成绩下滑检测（仅 ExamRecord）
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    async def _check_score_drop(
        db: AsyncSession,
        student: Student,
    ) -> WarningResult | None:
        """最近两次考试正确率降幅 ≥ 10% → warning 预警。

        数据源：仅 ExamRecord，不纳入 PracticeSession。
        """
        # 获取该学生最近两次已完成考试
        exam_result = await db.execute(
            select(ExamRecord)
            .join(StudentAnswer, StudentAnswer.exam_record_id == ExamRecord.id)
            .where(
                StudentAnswer.student_id == student.id,
                ExamRecord.status == ExamRecordStatus.completed.value,
            )
            .order_by(ExamRecord.exam_date.desc())
            .limit(2)
            .distinct()
        )
        exams = exam_result.scalars().all()

        if len(exams) < 2:
            return None

        # 计算最近两次各自的正确率
        latest_exam, previous_exam = exams[0], exams[1]
        latest_acc = await EarlyWarningService._exam_accuracy(
            db, student.id, latest_exam.id
        )
        previous_acc = await EarlyWarningService._exam_accuracy(
            db, student.id, previous_exam.id
        )

        if latest_acc is None or previous_acc is None:
            return None

        drop = previous_acc - latest_acc
        if drop >= SCORE_DROP_RATE:
            return WarningResult(
                student_id=student.id,
                warning_type=WarningType.score_drop.value,
                severity=WarningSeverity.warning.value,
                title="成绩下滑",
                message=(
                    f"学生 {student.name} 最近一次考试正确率"
                    f"（{latest_acc:.1%}）较前一次（{previous_acc:.1%}）"
                    f"下降 {drop:.1%}，超过 {SCORE_DROP_RATE:.0%} 阈值"
                ),
                data={
                    "latest_exam_id": latest_exam.id,
                    "latest_exam_name": latest_exam.name,
                    "latest_accuracy": round(latest_acc, 4),
                    "previous_exam_id": previous_exam.id,
                    "previous_exam_name": previous_exam.name,
                    "previous_accuracy": round(previous_acc, 4),
                    "drop": round(drop, 4),
                },
            )
        return None

    # ═══════════════════════════════════════════════════════════
    # 3.4 高错误率检测（知识点级）
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    async def _check_high_error_rate(
        db: AsyncSession,
        student: Student,
    ) -> list[WarningResult]:
        """知识点错误率检测：≥50% warning，≥70% severe。

        按知识点聚合学生所有作答，对达到阈值的每个知识点生成一条预警。
        SQL GROUP BY 预聚合到题目级，Python 仅展开标签。
        """
        from sqlalchemy import case
        ans_result = await db.execute(
            select(
                Question.knowledge_point_tags,
                func.count(StudentAnswer.id),
                func.sum(
                    case((StudentAnswer.is_correct == False, 1), else_=0)
                ),
            )
            .join(Question, Question.id == StudentAnswer.question_id)
            .where(StudentAnswer.student_id == student.id)
            .group_by(Question.id)
        )

        # 按知识点聚合（逐题展开标签，而非逐作答行）
        kp_stats: dict[str, dict] = defaultdict(lambda: {"errors": 0, "total": 0})
        for tags, total, errors in ans_result.all():
            if not tags or not total:
                continue
            for tag in tags:
                kp_stats[tag]["total"] += total
                kp_stats[tag]["errors"] += (errors or 0)

        results = []
        for name, stats in kp_stats.items():
            if stats["total"] < 3:  # 样本太少不预警
                continue
            error_rate = stats["errors"] / stats["total"]

            if error_rate >= HIGH_ERROR_RATE_SEVERE:
                severity = WarningSeverity.severe.value
            elif error_rate >= HIGH_ERROR_RATE_WARNING:
                severity = WarningSeverity.warning.value
            else:
                continue

            results.append(WarningResult(
                student_id=student.id,
                warning_type=WarningType.high_error_rate.value,
                severity=severity,
                title=f"知识点高错误率：{name}",
                message=(
                    f"学生 {student.name} 在知识点「{name}」上错误率"
                    f"为 {error_rate:.1%}（{stats['errors']}/{stats['total']}），"
                    f"超过 {severity} 阈值"
                ),
                data={
                    "knowledge_point": name,
                    "error_rate": round(error_rate, 4),
                    "errors": stats["errors"],
                    "total": stats["total"],
                },
            ))

        return results

    # ═══════════════════════════════════════════════════════════
    # 3.5 新障碍出现检测
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    async def _check_new_barrier(
        db: AsyncSession,
        student: Student,
    ) -> WarningResult | None:
        """主导障碍归一化得分变化 ≥ 30% → severe 预警。

        归一化：S_normalized = S_raw / max(S_raw_barriers_in_class)。
        与 BarrierProfileHistory 中最近一次快照对比。
        """
        profile = student.barrier_profile
        if not profile or not isinstance(profile, dict):
            return None

        # 获取班级中所有学生的障碍画像，计算各障碍类型最大原始值
        st_result = await db.execute(
            select(Student.barrier_profile)
            .where(
                Student.class_id == student.class_id,
                Student.barrier_profile.isnot(None),
            )
        )
        all_profiles = [row[0] for row in st_result.all() if row[0]]

        if not all_profiles:
            return None

        max_raw = {}
        for p in all_profiles:
            if isinstance(p, dict):
                for bt, val in p.items():
                    max_raw[bt] = max(max_raw.get(bt, 0.0), val)

        # 当前归一化得分
        current_dominant = max(profile, key=profile.get)
        current_normalized = (
            profile[current_dominant] / max_raw.get(current_dominant, 1.0)
            if max_raw.get(current_dominant, 0) > 0
            else 0.0
        )

        # 获取最近一次历史快照
        bh_result = await db.execute(
            select(BarrierProfileHistory)
            .where(BarrierProfileHistory.student_id == student.id)
            .order_by(BarrierProfileHistory.snapshot_at.desc())
            .limit(1)
        )
        last_snapshot = bh_result.scalar_one_or_none()

        if last_snapshot is None:
            # 无历史快照，跳过检测（后续 run_all_checks 会写入快照作为基线）
            return None

        last_profile = last_snapshot.profile
        if not last_profile or not isinstance(last_profile, dict):
            return None

        # 找到历史快照中的主导障碍类型
        last_dominant = last_snapshot.dominant_barrier or max(
            last_profile, key=last_profile.get
        )

        # 主导障碍类型不变 → 不预警（仅检测"新类型出现"）
        if current_dominant == last_dominant:
            return None

        # 使用快照中的 max_raw 归一化历史值（兼容无 max_raw 的旧快照）
        snapshot_max_raw = (
            last_snapshot.max_raw
            if last_snapshot.max_raw and isinstance(last_snapshot.max_raw, dict)
            else max_raw
        )

        # 当前主导障碍类型在历史快照中的原始值
        last_raw = last_profile.get(current_dominant, 0.0)
        last_normalized = (
            last_raw / snapshot_max_raw.get(current_dominant, 1.0)
            if snapshot_max_raw.get(current_dominant, 0) > 0
            else 0.0
        )

        shift = current_normalized - last_normalized
        if shift >= NEW_BARRIER_SHIFT:
            return WarningResult(
                student_id=student.id,
                warning_type=WarningType.new_barrier.value,
                severity=WarningSeverity.severe.value,
                title="新障碍类型出现",
                message=(
                    f"学生 {student.name} 的主导障碍类型从"
                    f"「{last_dominant}」转变为「{current_dominant}」，"
                    f"归一化得分变化 {shift:.1%}，超过 30% 阈值"
                ),
                data={
                    "previous_dominant": last_dominant,
                    "current_dominant": current_dominant,
                    "previous_normalized": round(last_normalized, 4),
                    "current_normalized": round(current_normalized, 4),
                    "shift": round(shift, 4),
                    "snapshot_at": last_snapshot.snapshot_at.isoformat(),
                },
            )

        return None

    # ═══════════════════════════════════════════════════════════
    # Helper: 去重 & 快照
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    async def _deduplicate(
        db: AsyncSession,
        warnings: list[WarningResult],
    ) -> list[WarningResult]:
        """过滤：同一学生同类型未处理预警已存在时不重复生成。"""
        if not warnings:
            return []

        # 批量查询已有未处理预警
        student_ids = list({w.student_id for w in warnings})
        existing_result = await db.execute(
            select(WarningLog.student_id, WarningLog.warning_type)
            .where(
                WarningLog.student_id.in_(student_ids),
                WarningLog.status.in_(["pending", "processing"]),
            )
        )
        existing = set(
            (row[0], row[1]) for row in existing_result.all()
        )

        return [
            w for w in warnings
            if (w.student_id, w.warning_type) not in existing
        ]

    @staticmethod
    async def _snapshot_barrier_profiles(
        db: AsyncSession,
        students: list[Student],
    ) -> None:
        """为所有学生写入当前障碍画像快照（供下次 new_barrier 检测基线）。

        同时计算并存储班级级 max_raw 归一化基线，
        确保下次检测时历史值与当前值使用一致的归一化参考。
        """
        now = datetime.now(timezone.utc)

        # 按班级分组，计算各班 max_raw（各障碍类型最大原始值）
        class_profiles: dict[int, list[dict]] = defaultdict(list)
        for student in students:
            profile = student.barrier_profile
            if profile and isinstance(profile, dict) and student.class_id:
                class_profiles[student.class_id].append(profile)

        class_max_raw: dict[int, dict] = {}
        for cid, profiles in class_profiles.items():
            max_raw: dict[str, float] = {}
            for p in profiles:
                for bt, val in p.items():
                    max_raw[bt] = max(max_raw.get(bt, 0.0), float(val))
            class_max_raw[cid] = max_raw

        for student in students:
            profile = student.barrier_profile
            if not profile or not isinstance(profile, dict):
                continue

            dominant = max(profile, key=profile.get) if profile else None
            snapshot = BarrierProfileHistory(
                student_id=student.id,
                snapshot_at=now,
                profile=profile,
                dominant_barrier=dominant,
                max_raw=class_max_raw.get(student.class_id),
            )
            db.add(snapshot)

    @staticmethod
    async def _exam_accuracy(
        db: AsyncSession,
        student_id: int,
        exam_id: int,
    ) -> float | None:
        """计算单个学生在单场考试中的正确率。"""
        ans_result = await db.execute(
            select(
                func.count(StudentAnswer.id),
                func.sum(func.cast(StudentAnswer.is_correct, Integer)),
            )
            .where(
                StudentAnswer.student_id == student_id,
                StudentAnswer.exam_record_id == exam_id,
            )
        )
        total, correct = ans_result.one()
        if not total:
            return None
        return (correct or 0) / total
