"""WeeklyReportService — LLM 驱动的周报生成 + 缓存 + Cron 入口。

对齐 33-家长端与通知系统设计 §八（周报生成）。
"""

import json
import logging
from datetime import datetime, timezone, timedelta

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..core.enums import BindingStatus, NotificationType, PracticeSessionStatus
from ..models.homework import StudentParentBinding, ParentNotification, WeeklyReport
from ..models.user import Student, Parent
from ..models.teaching import PracticeSession, StudentAnswer
from ..llm.router import llm_chat
from ..llm.providers.openai_compat import LLMError
from ..schemas.parent import WeeklyReportResponse
from ..utils import get_current_week_start, get_current_week_range
from .parent_service import ParentService

logger = logging.getLogger(__name__)

# ── 化学术语 → 通俗表述映射（33号 §八 — 家长端术语转换）──────────

def _convert_terms(raw: str) -> str:
    """将化学专业术语替换为通俗表述（家长可阅读）。"""
    from ..utils import convert_chemical_terms
    return convert_chemical_terms(raw)


def _convert_term_list(terms: list[str]) -> str:
    """将术语列表转为通俗表述字符串。"""
    if not terms:
        return "暂无"
    from ..utils import convert_chemical_terms_list
    converted = convert_chemical_terms_list(terms)
    return "、".join(converted) if converted else "暂无"

# ── 周报生成 System Prompt（33号 §八） ──────────────────────

_WEEKLY_REPORT_SYSTEM = """你是一位专业的教育顾问，专门为中学生家长撰写每周学习报告。

## 核心原则
1. **通俗易懂**：不使用化学专业术语，将概念转换为家长能理解的日常语言
2. **正向引导**：先肯定进步，再指出提升空间，避免制造焦虑
3. **不排名不比较**：只描述孩子自身的学习变化，不做横向对比
4. **具体可操作**：建议部分要具体，家长知道可以怎么做来帮助孩子
5. **适度使用 emoji**：让报告更亲切，但不过度

## 输出格式
严格输出 JSON，不要包含 markdown 代码块标记：
```json
{
  "summary": "一句话总结（≤60字），让家长一眼了解本周概况",
  "detail": "2-3 段正文（每段 ≤150字），分块描述：练习情况、掌握程度变化、学习习惯观察",
  "advice": "1-2 条给家长的具体建议（每条 ≤80字），可操作、不教条",
  "no_data": false
}
```

## 化学术语转换表（供参考）
- 氧化还原反应 → "与电子转移相关的反应"
- 离子反应 → "溶液中离子的反应"
- 物质的量/摩尔 → "化学中计量物质多少的单位"
- 化学平衡 → "化学反应进行到一定程度会达到的动态平衡"
- 元素周期律 → "元素性质随原子序数变化的规律"
- 电解质 → "能导电的化合物"
- 共价键/离子键 → "原子之间的连接方式"
- 配平 → "让方程式左右两边原子数一致"
- 沉淀 → "溶液中析出的固体"
- 中和反应 → "酸和碱生成盐和水的反应"
"""

_WEEKLY_REPORT_USER = """请为以下学生生成本周（{week_start} 至 {week_end}）的学习报告。

## 学生信息
- 姓名：{student_name}
- 年级：{grade}

## 本周学习数据
- 完成练习次数：{practice_count}
- 加权正确率：{accuracy_str}
- 连续学习天数：{streak_days}
- 练习涉及知识点：{topics_plain}

## 薄弱知识点（请务必转换为通俗表述）
{weak_points_plain}

## 学习障碍画像（三维）
- 概念理解障碍：{barrier_concept}
- 审题能力障碍：{barrier_reading}
- 表述能力障碍：{barrier_expression}

## 重要：输出要求
1. 所有化学术语必须按 system prompt 中的术语转换表替换为通俗表述
2. 不得出现任何排名、百分位、对比性语句（如"超过X%同学"）
3. 如果本周无练习数据或数据量太少（<2次），设 no_data=true 并给出鼓励性内容"""


class WeeklyReportService:
    """家长周报服务 — LLM 生成 + 缓存查询 + Cron 入口。"""

    # ═══════════════════════════════════════════════════════════
    # 核心生成
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    async def generate_report(
        db: AsyncSession,
        student_db_id: int,
        generated_by: str = "auto",
    ) -> WeeklyReportResponse:
        """为指定学生生成当周周报。

        1. 聚合本周练习数据
        2. 构造 prompt 调用 LLM
        3. 解析 JSON 响应
        4. 存储 WeeklyReport
        5. 返回响应
        """
        now = datetime.now(timezone.utc)
        week_start, week_end = get_current_week_range(now)

        # ── 聚合数据 ──
        from ..models.org import Class, Grade

        student_result = await db.execute(
            select(Student)
            .options(
                selectinload(Student.class_)
                .selectinload(Class.grade)
            )
            .where(Student.id == student_db_id)
        )
        student = student_result.scalar_one_or_none()
        if student is None:
            raise ValueError(f"学生不存在: id={student_db_id}")

        # 本周完成练习数
        count_result = await db.execute(
            select(func.count(PracticeSession.id)).where(
                PracticeSession.student_id == student_db_id,
                PracticeSession.status == PracticeSessionStatus.completed,
                PracticeSession.created_at >= week_start,
                PracticeSession.created_at < week_end,
            )
        )
        practice_count = count_result.scalar() or 0

        # 加权正确率
        from ..services.stats_service import StatsService
        accuracy = await StatsService._weighted_accuracy(db, student_db_id, now)
        streak = await StatsService._calc_streak_days(db, student_db_id, now)

        # 本周涉及知识点
        sessions_result = await db.execute(
            select(PracticeSession).where(
                PracticeSession.student_id == student_db_id,
                PracticeSession.status == PracticeSessionStatus.completed,
                PracticeSession.created_at >= week_start,
                PracticeSession.created_at < week_end,
            )
        )
        sessions = sessions_result.scalars().all()
        topics_set: set[str] = set()
        for s in sessions:
            if s.topics:
                topics_set.update(s.topics)
        topics = list(topics_set)[:10]  # 最多 10 个

        # 薄弱知识点
        weak_kps = student.weak_knowledge_points or []

        # 障碍画像
        bp = student.barrier_profile or {}
        barrier_concept = bp.get("concept", 0)
        barrier_reading = bp.get("reading", 0)
        barrier_expression = bp.get("expression", 0)

        # 年级（从班级获取）
        grade_name = "未知"
        if student.class_:
            grade_name = student.class_.grade.name if student.class_.grade else "未知"

        # ── 构造 Prompt ──
        accuracy_str = "暂无数据" if accuracy is None else f"{accuracy:.1%}"
        topics_str = _convert_term_list(topics)
        weak_str = _convert_term_list(weak_kps)

        def _barrier_label(val: float) -> str:
            if val >= 0.5:
                return "需要重点关注"
            elif val >= 0.3:
                return "有一定提升空间"
            return "表现良好"

        user_prompt = _WEEKLY_REPORT_USER.format(
            week_start=week_start.strftime("%Y-%m-%d"),
            week_end=(week_end - timedelta(days=1)).strftime("%Y-%m-%d"),
            student_name=student.name,
            grade=grade_name,
            practice_count=practice_count,
            accuracy_str=accuracy_str,
            streak_days=streak,
            topics_plain=topics_str,
            weak_points_plain=weak_str,
            barrier_concept=_barrier_label(barrier_concept),
            barrier_reading=_barrier_label(barrier_reading),
            barrier_expression=_barrier_label(barrier_expression),
        )

        messages = [
            {"role": "system", "content": _WEEKLY_REPORT_SYSTEM},
            {"role": "user", "content": user_prompt},
        ]

        # ── LLM 调用 ──
        try:
            raw = await llm_chat(messages, temperature=0.7, json_mode=True)
            data = json.loads(raw)
            # 归一化：LLM 可能将文本字段返回为字符串或字符串列表
            for field in ("summary", "detail", "advice"):
                val = data.get(field, "")
                if isinstance(val, list):
                    data[field] = "\n".join(val)
        except (LLMError, json.JSONDecodeError) as e:
            logger.error(f"WeeklyReport LLM 调用失败: {e}")
            # 降级：生成基础报告
            data = WeeklyReportService._fallback_report(
                student_name=student.name,
                practice_count=practice_count,
                accuracy=accuracy,
                streak=streak,
                weak_kps=weak_kps,
            )

        # ── 存储（upsert：同一学生同一周只保留最新一份）──
        report = await db.execute(
            select(WeeklyReport).where(
                WeeklyReport.student_id == student_db_id,
                WeeklyReport.week_start == week_start,
            )
        )
        existing = report.scalar_one_or_none()

        if existing:
            existing.summary = data.get("summary", existing.summary)
            existing.detail = data.get("detail", existing.detail)
            existing.advice = data.get("advice", existing.advice)
            existing.no_data = data.get("no_data", existing.no_data)
            existing.generated_at = datetime.now(timezone.utc)
            existing.generated_by = generated_by
            report_obj = existing
        else:
            report_obj = WeeklyReport(
                student_id=student_db_id,
                week_start=week_start,
                week_end=week_end - timedelta(days=1),
                summary=data.get("summary", "本周学习报告已生成"),
                detail=data.get("detail", "暂无详细数据"),
                advice=data.get("advice", "请持续关注孩子的学习情况"),
                no_data=data.get("no_data", practice_count < 2),
                generated_at=datetime.now(timezone.utc),
                generated_by=generated_by,
            )
            db.add(report_obj)

        await db.commit()
        await db.refresh(report_obj)

        return WeeklyReportResponse.model_validate(report_obj)

    @staticmethod
    def _fallback_report(
        student_name: str,
        practice_count: int,
        accuracy: float | None,
        streak: int,
        weak_kps: list[str],
    ) -> dict:
        """LLM 不可用时生成降级周报（不含 AI 建议）。"""
        if practice_count == 0:
            return {
                "summary": f"{student_name}本周暂无练习记录",
                "detail": "本周没有完成化学练习。建议每天花15-20分钟做一些练习题，保持学习节奏。",
                "advice": "可以和孩子一起制定一个简单的学习计划，每天固定时间完成几道化学题。",
                "no_data": True,
            }

        acc_str = f"，正确率 {accuracy:.0%}" if accuracy is not None else ""
        weak_str = f"薄弱知识点：{_convert_term_list(weak_kps)}。" if weak_kps else ""

        return {
            "summary": f"{student_name}本周完成{practice_count}次练习{acc_str}，连续学习{streak}天",
            "detail": (
                f"本周共完成 {practice_count} 次化学练习{acc_str}。"
                f"{weak_str}"
                f"已连续学习 {streak} 天，{'请继续保持！' if streak >= 5 else '可以尝试每天坚持练习，养成良好习惯。'}"
            ),
            "advice": (
                "建议关注错题，定期回顾做错的题目，理解错误原因比做新题更重要。"
                if weak_kps
                else "孩子表现不错，继续保持每天练习的习惯即可。"
            ),
            "no_data": practice_count < 2,
        }

    # ═══════════════════════════════════════════════════════════
    # 缓存查询
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    async def get_report(
        db: AsyncSession,
        student_db_id: int,
        week_start: datetime | None = None,
    ) -> WeeklyReportResponse | None:
        """查询已缓存的周报。

        Args:
            db: 异步会话
            student_db_id: 学生数据库 ID
            week_start: 周一日期，默认为本周一
        """
        if week_start is None:
            week_start = get_current_week_start()

        result = await db.execute(
            select(WeeklyReport).where(
                WeeklyReport.student_id == student_db_id,
                WeeklyReport.week_start == week_start,
            ).order_by(WeeklyReport.generated_at.desc()).limit(1)
        )
        report = result.scalar_one_or_none()
        if report is None:
            return None
        return WeeklyReportResponse.model_validate(report)

    # ═══════════════════════════════════════════════════════════
    # 生成 + 通知
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    async def generate_and_notify(
        db: AsyncSession,
        student_db_id: int,
        generated_by: str = "auto",
    ) -> WeeklyReportResponse:
        """生成周报 → 查询绑定家长 → 创建通知。"""
        report = await WeeklyReportService.generate_report(
            db, student_db_id, generated_by
        )

        # 查询该学生的所有活跃绑定家长
        bindings_result = await db.execute(
            select(StudentParentBinding).where(
                StudentParentBinding.student_id == student_db_id,
                StudentParentBinding.status == BindingStatus.active,
            )
        )
        bindings = bindings_result.scalars().all()

        for binding in bindings:
            await ParentService.create_notification(
                db,
                parent_db_id=binding.parent_id,
                notification_type=NotificationType.weekly_report.value,
                title=f"📊 本周学习报告已生成",
                body=report.summary,
                related_id=report.id,
            )

        return report

    # ═══════════════════════════════════════════════════════════
    # Cron 入口（周一 08:00 触发）
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    async def run_weekly_cron(db: AsyncSession) -> dict:
        """批量生成周报并通知所有活跃绑定家长。

        周一 08:00 Cron 触发。遍历所有有活跃绑定的学生 →
        逐个生成周报 → 通知对应家长。

        Returns:
            {'generated': int, 'failed': int, 'notifications': int}
        """
        # 查找所有有活跃绑定的学生
        bindings_result = await db.execute(
            select(StudentParentBinding.student_id).where(
                StudentParentBinding.status == BindingStatus.active,
            ).distinct()
        )
        student_ids = [row[0] for row in bindings_result.all()]

        generated = 0
        failed = 0
        notifications_sent = 0

        for sid in student_ids:
            try:
                report = await WeeklyReportService.generate_and_notify(
                    db, sid, generated_by="auto"
                )
                generated += 1
                # count notifications from generate_and_notify
                bindings_count = await db.execute(
                    select(func.count(StudentParentBinding.id)).where(
                        StudentParentBinding.student_id == sid,
                        StudentParentBinding.status == BindingStatus.active,
                    )
                )
                notifications_sent += bindings_count.scalar() or 0
            except Exception as e:
                logger.error(f"WeeklyReport Cron 失败 student_id={sid}: {e}")
                failed += 1
                continue

        logger.info(
            f"WeeklyReport Cron 完成: generated={generated}, failed={failed}, "
            f"notifications={notifications_sent}"
        )
        return {
            "generated": generated,
            "failed": failed,
            "notifications": notifications_sent,
        }
