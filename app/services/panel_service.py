"""PanelService — 班级学情按需实时聚合引擎。

设计决策（CONTEXT.md §十二）：
- 按需聚合，不建预计算快照表
- 班级加权均分使用指数衰减公式 w_i = exp(-λ × (t_now - t_i) / T_week)，λ = ln(2)
- score_drop 指标只取 ExamRecord，知识点错误率和障碍分布同时取 ExamRecord + PracticeSession
- 进步/退步 Top 3 使用最近两次考试个人正确率差值
"""

import logging
import math
from collections import defaultdict
from datetime import datetime, timezone

from sqlalchemy import select, func, Integer
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.org import Class
from ..models.user import Student, Teacher, TeacherClassSubject
from ..models.teaching import ExamRecord, StudentAnswer, Question, PracticeSession
from ..models.diagnosis import WarningLog
from ..core.enums import ExamRecordStatus

logger = logging.getLogger(__name__)

# 指数衰减常量：λ = ln(2)，半衰期 = 1 周
_DECAY_LAMBDA = math.log(2)
_T_WEEK_SECONDS = 7 * 24 * 3600


class PanelService:
    """班级学情按需实时聚合服务。

    所有方法均为 staticmethod，通过 db session 注入。
    """

    # ═══════════════════════════════════════════════════════════
    # 2.1 Teacher Dashboard 班级列表
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    async def get_teacher_classes(
        db: AsyncSession,
        teacher_id: int,
    ) -> list[dict]:
        """获取教师所教班级列表 + 每班简要指标。

        Args:
            db: 数据库会话
            teacher_id: Teacher.id（非 Account.id）

        Returns:
            [{class_id, class_name, student_count, recent_avg_score,
              concern_count, last_exam_date}, ...]
        """
        # 教师任课关系
        tcs_result = await db.execute(
            select(TeacherClassSubject).where(
                TeacherClassSubject.teacher_id == teacher_id
            )
        )
        tcs_list = tcs_result.scalars().all()
        if not tcs_list:
            return []

        class_ids = list({tcs.class_id for tcs in tcs_list})

        # 班级信息
        classes_result = await db.execute(
            select(Class).where(Class.id.in_(class_ids))
        )
        classes = {c.id: c for c in classes_result.scalars().all()}

        # 每班学生数
        student_counts = {}
        st_result = await db.execute(
            select(Student.class_id, func.count(Student.id))
            .where(Student.class_id.in_(class_ids))
            .group_by(Student.class_id)
        )
        for class_id, count in st_result.all():
            student_counts[class_id] = count

        # 每班最近一次考试（一次查询获取所有班级最近考试）
        from sqlalchemy import and_

        exam_subq = (
            select(
                ExamRecord.class_id,
                func.max(ExamRecord.exam_date).label("last_date"),
            )
            .where(
                ExamRecord.class_id.in_(class_ids),
                ExamRecord.status == ExamRecordStatus.completed.value,
            )
            .group_by(ExamRecord.class_id)
            .subquery()
        )

        latest_exam_result = await db.execute(
            select(ExamRecord)
            .join(
                exam_subq,
                and_(
                    ExamRecord.class_id == exam_subq.c.class_id,
                    ExamRecord.exam_date == exam_subq.c.last_date,
                ),
            )
            .where(ExamRecord.status == ExamRecordStatus.completed.value)
        )
        latest_exams = list(latest_exam_result.scalars().all())

        # 批量计算所有最近考试均分（消除 per-class N+1）
        exam_ids = [e.id for e in latest_exams]
        avg_scores = await PanelService._batch_exam_avg_scores(db, exam_ids)

        recent_scores = {}
        last_dates = {}
        for exam in latest_exams:
            last_dates[exam.class_id] = exam.exam_date
            recent_scores[exam.class_id] = avg_scores.get(exam.id)

        # 每班未处理预警学生数
        concern_counts = {}
        w_result = await db.execute(
            select(Student.class_id, func.count(func.distinct(WarningLog.student_id)))
            .join(WarningLog, WarningLog.student_id == Student.id)
            .where(
                Student.class_id.in_(class_ids),
                WarningLog.status.in_(["pending", "processing"]),
            )
            .group_by(Student.class_id)
        )
        for class_id, count in w_result.all():
            concern_counts[class_id] = count

        result = []
        for class_id in class_ids:
            cls = classes.get(class_id)
            if cls is None:
                continue
            result.append({
                "class_id": class_id,
                "class_name": cls.name,
                "student_count": student_counts.get(class_id, 0),
                "recent_avg_score": recent_scores.get(class_id),
                "concern_count": concern_counts.get(class_id, 0),
                "last_exam_date": last_dates.get(class_id),
            })

        return result

    # ═══════════════════════════════════════════════════════════
    # 2.2 班级聚合视图
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    async def get_class_overview(
        db: AsyncSession,
        class_id: int,
    ) -> dict:
        """班级聚合视图：加权均分 + 知识点 Top 5 + 障碍分布 + 进步/退步 + 关注学生。

        Returns:
            符合 ClassOverview schema 的 dict
        """
        # 班级基本信息
        cls_result = await db.execute(select(Class).where(Class.id == class_id))
        cls = cls_result.scalar_one_or_none()
        if cls is None:
            return None

        # 学生数
        st_result = await db.execute(
            select(func.count(Student.id)).where(Student.class_id == class_id)
        )
        student_count = st_result.scalar() or 0

        # 考试列表
        exam_result = await db.execute(
            select(ExamRecord)
            .where(
                ExamRecord.class_id == class_id,
                ExamRecord.status == ExamRecordStatus.completed.value,
            )
            .order_by(ExamRecord.exam_date.desc())
        )
        exams = exam_result.scalars().all()

        # 加权均分
        avg_score = await PanelService._weighted_avg_score(db, exams)

        # 知识点错误率 Top 5
        knowledge_points = await PanelService._knowledge_point_error_rates(
            db, class_id, limit=5
        )

        # 障碍类型分布
        barriers = await PanelService._barrier_distribution(db, class_id)

        # 进步/退步 Top 3
        improvers, declining = await PanelService._top_improvers_declining(
            db, class_id
        )

        # 关注学生
        concerns = await PanelService._concern_students(db, class_id)

        return {
            "class_id": class_id,
            "class_name": cls.name,
            "student_count": student_count,
            "avg_score": avg_score,
            "knowledge_points": knowledge_points,
            "barrier_distribution": barriers,
            "top_improvers": improvers,
            "top_declining": declining,
            "concern_students": concerns,
            "exam_count": len(exams),
        }

    # ═══════════════════════════════════════════════════════════
    # 2.3 学生详情
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    async def get_student_detail(
        db: AsyncSession,
        class_id: int,
        student_id: int,
    ) -> dict | None:
        """学生详情：正确率趋势 + 薄弱知识点（含 trend）+ 障碍画像历史。"""
        st_result = await db.execute(
            select(Student).where(
                Student.id == student_id,
                Student.class_id == class_id,
            )
        )
        student = st_result.scalar_one_or_none()
        if student is None:
            return None

        # 正确率趋势（考试 + 练习混合）
        accuracy_trend = await PanelService._student_accuracy_trend(db, student_id)

        # 薄弱知识点（含 trend 方向）
        weak_kps = await PanelService._student_weak_kps_with_trend(db, student_id)

        # 障碍画像历史
        barrier_history = await PanelService._student_barrier_history(db, student_id)

        # 班级名
        cls_result = await db.execute(select(Class).where(Class.id == class_id))
        cls = cls_result.scalar_one_or_none()

        return {
            "student_info": {
                "id": student.id,
                "name": student.name,
                "class_name": cls.name if cls else "",
            },
            "accuracy_trend": accuracy_trend,
            "weak_knowledge_points": weak_kps,
            "barrier_profile_history": barrier_history,
        }

    # ═══════════════════════════════════════════════════════════
    # 2.4 知识点维度展开（全量分页）
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    async def get_knowledge_points(
        db: AsyncSession,
        class_id: int,
        limit: int = 20,
        offset: int = 0,
    ) -> dict:
        """全量知识点错误率排行（分页）。"""
        all_kps = await PanelService._knowledge_point_error_rates(
            db, class_id, limit=None
        )
        total = len(all_kps)
        return {
            "data": all_kps[offset:offset + limit],
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    # ═══════════════════════════════════════════════════════════
    # 2.5 障碍类型维度展开
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    async def get_barriers(db: AsyncSession, class_id: int) -> list[dict]:
        """障碍类型分布统计。"""
        return await PanelService._barrier_distribution(db, class_id)

    # ═══════════════════════════════════════════════════════════
    # 2.6 重点关注学生列表
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    async def get_concern_students(db: AsyncSession, class_id: int) -> list[dict]:
        """预警未处理的学生列表。"""
        return await PanelService._concern_students(db, class_id)

    # ═══════════════════════════════════════════════════════════
    # 2.7 考试趋势
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    async def get_exam_trend(db: AsyncSession, class_id: int) -> list[dict]:
        """班级历次考试均分序列（按日期升序）。"""
        exam_result = await db.execute(
            select(ExamRecord)
            .where(
                ExamRecord.class_id == class_id,
                ExamRecord.status == ExamRecordStatus.completed.value,
            )
            .order_by(ExamRecord.exam_date.asc())
        )
        exams = exam_result.scalars().all()

        if not exams:
            return []

        exam_ids = [e.id for e in exams]

        # 批量计算均分（消除 per-exam N+1）
        avg_scores = await PanelService._batch_exam_avg_scores(db, exam_ids)

        # 批量统计每场考试参考人数（消除 per-exam N+1）
        participant_result = await db.execute(
            select(
                StudentAnswer.exam_record_id,
                func.count(func.distinct(StudentAnswer.student_id)),
            )
            .where(StudentAnswer.exam_record_id.in_(exam_ids))
            .group_by(StudentAnswer.exam_record_id)
        )
        participants = {row[0]: row[1] for row in participant_result.all()}

        trend = []
        for exam in exams:
            trend.append({
                "exam_id": exam.id,
                "exam_name": exam.name,
                "exam_date": exam.exam_date,
                "avg_score": avg_scores.get(exam.id),
                "participant_count": participants.get(exam.id, 0),
            })

        return trend

    # ═══════════════════════════════════════════════════════════
    # 内部 Helper 方法（2.8）
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    async def _weighted_avg_score(
        db: AsyncSession,
        exams: list[ExamRecord],
    ) -> float | None:
        """加权指数衰减均分：w_i = exp(-λ × (t_now - t_i) / T_week)。"""
        if not exams:
            return None

        now = datetime.now(timezone.utc)
        total_weight = 0.0
        weighted_sum = 0.0

        for exam in exams:
            avg = await PanelService._exam_avg_score(db, exam.id)
            if avg is None:
                continue
            if exam.exam_date:
                exam_date = exam.exam_date.replace(tzinfo=timezone.utc) if exam.exam_date.tzinfo is None else exam.exam_date
                delta_seconds = (now - exam_date).total_seconds()
            else:
                delta_seconds = _T_WEEK_SECONDS  # 无日期时视为一周前
            weight = math.exp(-_DECAY_LAMBDA * delta_seconds / _T_WEEK_SECONDS)
            weighted_sum += avg * weight
            total_weight += weight

        if total_weight == 0:
            return None
        return round(weighted_sum / total_weight, 2)

    @staticmethod
    async def _exam_avg_score(db: AsyncSession, exam_id: int) -> float | None:
        """计算单场考试的班级均分（所有学生正确率均值 × 100）。"""
        # 按学生聚合正确率（直接过滤 exam_record_id，避免跨考试题目交叉污染）
        ans_result = await db.execute(
            select(
                StudentAnswer.student_id,
                func.count(StudentAnswer.id).label("total"),
                func.sum(
                    func.cast(StudentAnswer.is_correct, Integer)
                ).label("correct"),
            )
            .where(StudentAnswer.exam_record_id == exam_id)
            .group_by(StudentAnswer.student_id)
        )
        rows = ans_result.all()
        if not rows:
            return None

        accuracies = []
        for row in rows:
            _, total, correct = row[0], row[1], row[2]
            correct = correct or 0
            total = total or 0
            if total > 0:
                accuracies.append(correct / total)

        if not accuracies:
            return None
        return round(sum(accuracies) / len(accuracies) * 100, 2)

    @staticmethod
    async def _batch_exam_avg_scores(
        db: AsyncSession,
        exam_ids: list[int],
    ) -> dict[int, float | None]:
        """批量计算多场考试的班级均分（消除 per-exam N+1）。"""
        if not exam_ids:
            return {}

        ans_result = await db.execute(
            select(
                StudentAnswer.exam_record_id,
                StudentAnswer.student_id,
                func.count(StudentAnswer.id).label("total"),
                func.sum(
                    func.cast(StudentAnswer.is_correct, Integer)
                ).label("correct"),
            )
            .where(StudentAnswer.exam_record_id.in_(exam_ids))
            .group_by(StudentAnswer.exam_record_id, StudentAnswer.student_id)
        )

        exam_accs: dict[int, list[float]] = defaultdict(list)
        for row in ans_result.all():
            eid, _, total, correct = row[0], row[1], row[2], row[3]
            correct = correct or 0
            total = total or 0
            if total > 0:
                exam_accs[eid].append(correct / total)

        return {
            eid: round(sum(accs) / len(accs) * 100, 2) if accs else None
            for eid, accs in exam_accs.items()
        }

    @staticmethod
    async def _knowledge_point_error_rates(
        db: AsyncSession,
        class_id: int,
        limit: int | None = 5,
    ) -> list[dict]:
        """知识点错误率排行。数据来源：ExamRecord + PracticeSession。

        优化：SQL GROUP BY 预聚合到题目级（而非逐行拉到 Python），
        大幅减少数据传输量（200 行 vs 30,000 行）。
        """
        # 获取班级所有学生 ID
        st_result = await db.execute(
            select(Student.id).where(Student.class_id == class_id)
        )
        student_ids = [row[0] for row in st_result.all()]
        if not student_ids:
            return []

        kp_stats: dict[str, dict] = defaultdict(lambda: {"errors": 0, "total": 0})

        # Query 1: SQL 按题目聚合正确/错误数，Python 仅展开知识点标签
        from sqlalchemy import case
        q_agg_result = await db.execute(
            select(
                Question.knowledge_point_tags,
                func.count(StudentAnswer.id),
                func.sum(
                    case((StudentAnswer.is_correct == False, 1), else_=0)
                ),
            )
            .join(Question, Question.id == StudentAnswer.question_id)
            .where(StudentAnswer.student_id.in_(student_ids))
            .group_by(Question.id)
        )
        for tags, total, errors in q_agg_result.all():
            if not tags or not total:
                continue
            for tag in tags:
                kp_stats[tag]["total"] += total
                kp_stats[tag]["errors"] += (errors or 0)

        # Query 2: PracticeSession 数据量小（每会话一行），保留 Python 聚合
        ps_result = await db.execute(
            select(PracticeSession)
            .where(
                PracticeSession.student_id.in_(student_ids),
                PracticeSession.status == "completed",
            )
        )
        for ps in ps_result.scalars().all():
            kps = ps.knowledge_point_tags or []
            correct_count = ps.questions_correct or 0
            total = ps.question_count or 0
            errors = total - correct_count
            if total == 0:
                continue
            for kp in kps:
                kp_stats[kp]["total"] += total // len(kps) if len(kps) > 0 else total
                kp_stats[kp]["errors"] += errors // len(kps) if len(kps) > 0 else errors

        # 计算错误率并排序
        result = []
        for name, stats in kp_stats.items():
            if stats["total"] > 0:
                result.append({
                    "name": name,
                    "error_rate": round(stats["errors"] / stats["total"], 4),
                })

        result.sort(key=lambda x: x["error_rate"], reverse=True)
        if limit is not None:
            result = result[:limit]
        return result

    @staticmethod
    async def _barrier_distribution(
        db: AsyncSession,
        class_id: int,
    ) -> list[dict]:
        """障碍类型分布统计：{barrier_type, count, percentage}。"""
        st_result = await db.execute(
            select(Student.barrier_profile)
            .where(
                Student.class_id == class_id,
                Student.barrier_profile.isnot(None),
            )
        )
        profiles = [row[0] for row in st_result.all() if row[0]]
        total = len(profiles)
        if total == 0:
            return []

        counts: dict[str, int] = defaultdict(int)
        for profile in profiles:
            # 找到主导障碍类型
            if isinstance(profile, dict):
                dominant = max(profile, key=profile.get)
                counts[dominant] += 1

        return [
            {
                "barrier_type": bt,
                "count": cnt,
                "percentage": round(cnt / total * 100, 1),
            }
            for bt, cnt in sorted(counts.items(), key=lambda x: x[1], reverse=True)
        ]

    @staticmethod
    async def _top_improvers_declining(
        db: AsyncSession,
        class_id: int,
    ) -> tuple[list[dict], list[dict]]:
        """进步/退步 Top 3：最近两次考试个人正确率差值。

        批量查询优化：2 次查询替代原有的 3N+1 次（N=学生数）。
        """
        # Query 1: 全班学生 ID → 姓名映射
        st_result = await db.execute(
            select(Student.id, Student.name).where(Student.class_id == class_id)
        )
        student_map = {row[0]: row[1] for row in st_result.all()}
        student_ids = list(student_map.keys())
        if not student_ids:
            return [], []

        # Query 2: 批量获取每学生×每考试的正确率（按考试日期降序）
        from sqlalchemy import desc
        agg_result = await db.execute(
            select(
                StudentAnswer.student_id,
                ExamRecord.id,
                ExamRecord.exam_date,
                func.count(StudentAnswer.id).label("total"),
                func.sum(func.cast(StudentAnswer.is_correct, Integer)).label("correct"),
            )
            .join(ExamRecord, ExamRecord.id == StudentAnswer.exam_record_id)
            .where(
                StudentAnswer.student_id.in_(student_ids),
                ExamRecord.class_id == class_id,
                ExamRecord.status == ExamRecordStatus.completed.value,
            )
            .group_by(StudentAnswer.student_id, ExamRecord.id)
            .order_by(StudentAnswer.student_id, desc(ExamRecord.exam_date))
        )
        rows = agg_result.all()

        # 按学生分组，取最近 2 次考试
        student_exams: dict[int, list[dict]] = defaultdict(list)
        for row in rows:
            sid, eid, edate, total, correct = row
            total = total or 0
            correct = correct or 0
            if total > 0:
                student_exams[sid].append({
                    "exam_id": eid,
                    "exam_date": edate,
                    "accuracy": correct / total,
                })

        # 计算变化（已按日期降序，前两条即最近两次）
        changes = []
        for sid, exams in student_exams.items():
            if len(exams) < 2:
                continue
            # exams[0] = 最新, exams[1] = 次新
            change = round(exams[0]["accuracy"] - exams[1]["accuracy"], 4)
            changes.append({
                "student_id": sid,
                "student_name": student_map.get(sid, ""),
                "change": change,
            })

        changes.sort(key=lambda x: x["change"], reverse=True)
        improvers = [c for c in changes if c["change"] > 0][:3]
        declining = [c for c in changes if c["change"] < 0][:3]
        declining.sort(key=lambda x: x["change"])
        return improvers, declining

    @staticmethod
    async def _student_exam_accuracy(
        db: AsyncSession,
        student_id: int,
        exam_id: int,
    ) -> float | None:
        """计算单个学生在单场考试中的正确率。"""
        ans_result = await db.execute(
            select(
                func.count(StudentAnswer.id),
                func.sum(
                    func.cast(StudentAnswer.is_correct, type_=Integer)
                ),
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

    @staticmethod
    async def _concern_students(
        db: AsyncSession,
        class_id: int,
    ) -> list[dict]:
        """预警未处理的学生列表。"""
        w_result = await db.execute(
            select(
                WarningLog.student_id,
                Student.name,
                Student.last_practice_time,
                func.count(WarningLog.id).label("warning_count"),
                func.max(WarningLog.warning_type).label("latest_type"),
                func.max(WarningLog.severity).label("latest_severity"),
                func.max(WarningLog.created_at).label("latest_created"),
            )
            .join(Student, Student.id == WarningLog.student_id)
            .where(
                Student.class_id == class_id,
                WarningLog.status.in_(["pending", "processing"]),
            )
            .group_by(
                WarningLog.student_id,
                Student.name,
                Student.last_practice_time,
            )
            .order_by(func.count(WarningLog.id).desc())
        )
        rows = w_result.all()

        result = []
        for row in rows:
            sid, st_name, st_last_practice, wc, lt, ls, lc = row
            result.append({
                "student_id": sid,
                "name": st_name,
                "warning_count": wc,
                "latest_warning_type": lt,
                "latest_warning_severity": ls,
                "last_practice_time": st_last_practice,
            })

        return result

    @staticmethod
    async def _student_accuracy_trend(
        db: AsyncSession,
        student_id: int,
    ) -> list[dict]:
        """个人正确率趋势（考试 + 练习混合，按日期升序）。"""
        trend = []

        # 考试数据
        exam_result = await db.execute(
            select(ExamRecord)
            .join(StudentAnswer, StudentAnswer.exam_record_id == ExamRecord.id)
            .where(StudentAnswer.student_id == student_id)
            .order_by(ExamRecord.exam_date.asc())
            .distinct()
        )
        for exam in exam_result.scalars().all():
            acc = await PanelService._student_exam_accuracy(db, student_id, exam.id)
            if acc is not None:
                q_result = await db.execute(
                    select(func.count(func.distinct(StudentAnswer.question_id)))
                    .where(StudentAnswer.exam_record_id == exam.id)
                )
                total = q_result.scalar() or 0
                trend.append({
                    "date": exam.exam_date,
                    "source_type": "exam",
                    "accuracy": round(acc, 4),
                    "total_questions": total,
                })

        # 练习数据
        ps_result = await db.execute(
            select(PracticeSession)
            .where(
                PracticeSession.student_id == student_id,
                PracticeSession.status == "completed",
            )
            .order_by(PracticeSession.created_at.asc())
        )
        for ps in ps_result.scalars().all():
            total = ps.question_count or 0
            correct = ps.questions_correct or 0
            if total > 0:
                trend.append({
                    "date": ps.created_at,
                    "source_type": "practice",
                    "accuracy": round(correct / total, 4),
                    "total_questions": total,
                })

        trend.sort(key=lambda x: x["date"] or datetime.min.replace(tzinfo=timezone.utc))
        return trend

    @staticmethod
    async def _student_weak_kps_with_trend(
        db: AsyncSession,
        student_id: int,
    ) -> list[dict]:
        """学生薄弱知识点（含 trend 方向标记）。

        trend:
        - "up": 最近一次正确率 > 前一次正确率
        - "down": 最近一次正确率 < 前一次正确率
        - "stable": 无变化或数据不足
        """
        # 取学生所有作答，按知识点聚合
        ans_result = await db.execute(
            select(
                Question.knowledge_point_tags,
                StudentAnswer.is_correct,
                StudentAnswer.created_at,
            )
            .join(Question, Question.id == StudentAnswer.question_id)
            .where(StudentAnswer.student_id == student_id)
            .order_by(StudentAnswer.created_at.asc())
        )
        rows = ans_result.all()
        if not rows:
            return []

        # 按知识点分组，按时序排列
        kp_records: dict[str, list[dict]] = defaultdict(list)
        for tags, is_correct, created_at in rows:
            if not tags:
                continue
            for tag in tags:
                kp_records[tag].append({
                    "is_correct": is_correct,
                    "created_at": created_at,
                })

        result = []
        for name, records in kp_records.items():
            total = len(records)
            errors = sum(1 for r in records if not r["is_correct"])
            error_rate = round(errors / total, 4) if total > 0 else 0.0

            # 计算 trend：比较前后半段的正确率
            trend = "stable"
            if total >= 4:
                mid = total // 2
                first_half = sum(1 for r in records[:mid] if r["is_correct"]) / mid
                second_half = sum(1 for r in records[mid:] if r["is_correct"]) / (total - mid)
                if second_half > first_half + 0.05:
                    trend = "up"
                elif second_half < first_half - 0.05:
                    trend = "down"

            result.append({
                "name": name,
                "error_rate": error_rate,
                "trend": trend,
            })

        result.sort(key=lambda x: x["error_rate"], reverse=True)
        return result[:10]

    @staticmethod
    async def _student_barrier_history(
        db: AsyncSession,
        student_id: int,
    ) -> list[dict]:
        """学生障碍画像历史快照（按时间倒序）。"""
        from ..models.barrier_profile_history import BarrierProfileHistory

        bh_result = await db.execute(
            select(BarrierProfileHistory)
            .where(BarrierProfileHistory.student_id == student_id)
            .order_by(BarrierProfileHistory.snapshot_at.desc())
            .limit(20)
        )
        return [
            {
                "snapshot_at": bh.snapshot_at,
                "profile": bh.profile,
                "dominant_barrier": bh.dominant_barrier,
            }
            for bh in bh_result.scalars().all()
        ]
