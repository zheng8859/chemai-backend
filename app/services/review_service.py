"""间隔复习与错题训练服务 — ReviewTask 管理 + 变式题生成 + 强化训练。

设计文档 29 号 + tasks.md §3.6-3.12。
从 DiagnosisService 迁出 list_pending_reviews() 和 complete_review()，
升级为使用 spaced_repetition engine。
"""

import json
import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc, and_

from ..models.diagnosis import (
    ReviewTask,
    ReviewHistory,
    VariantQuestion,
)
from ..models.teaching import StudentAnswer, Question
from ..models.user import Student
from ..core.enums import ReviewTaskStatus
from ..llm.router import llm_chat

from chem_skills.chemistry_memory.spaced_repetition import (
    compute_next_review,
    evaluate_level_change,
    MAX_LEVEL,
)
from chem_skills.chemistry_memory.variant_generator import build_variant_prompt

logger = logging.getLogger(__name__)


class ReviewError(Exception):
    """复习服务异常。"""
    def __init__(self, detail: str, error_code: str = "REVIEW_ERROR"):
        self.detail = detail
        self.error_code = error_code
        super().__init__(detail)


class ReviewService:
    """间隔复习与错题训练服务。

    所有方法均为 static method，db 由调用方传入。
    """

    # ═══════════════════════════════════════════════════════════
    # 3.6 list_pending_reviews（从 DiagnosisService 迁入并升级）
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    async def list_pending_reviews(
        db: AsyncSession,
        student_id: int,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[dict], int]:
        """列出待复习/已逾期的 ReviewTask，附带题目内容。

        Returns:
            (tasks: list[dict], total_count: int)
        """
        total = (await db.execute(
            select(func.count(ReviewTask.id)).where(
                ReviewTask.student_id == student_id,
                ReviewTask.status.in_(["pending", "overdue"]),
            )
        )).scalar() or 0

        result = await db.execute(
            select(ReviewTask)
            .where(
                ReviewTask.student_id == student_id,
                ReviewTask.status.in_(["pending", "overdue"]),
            )
            .order_by(ReviewTask.next_review_date.asc().nulls_last())
            .offset(offset)
            .limit(limit)
        )
        tasks = result.scalars().all()

        items = []
        for t in tasks:
            question = (await db.execute(
                select(Question).where(Question.id == t.question_id)
            )).scalar_one_or_none()

            items.append({
                "id": t.id,
                "student_id": t.student_id,
                "question_id": t.question_id,
                "level": t.level,
                "status": t.status,
                "consecutive_correct": t.consecutive_correct,
                "consecutive_wrong": t.consecutive_wrong,
                "next_review_date": t.next_review_date.isoformat() if t.next_review_date else None,
                "question": {
                    "id": question.id,
                    "content": question.content,
                    "question_type": question.question_type,
                    "options": question.options,
                    "answer": question.answer,
                    "analysis": question.analysis,
                    "difficulty": question.difficulty,
                    "knowledge_point_tags": question.knowledge_point_tags,
                } if question else None,
            })

        return items, total

    # ═══════════════════════════════════════════════════════════
    # 3.6 complete_review（从 DiagnosisService 迁入并升级）
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    async def complete_review(
        db: AsyncSession,
        review_task_id: int,
        is_correct: bool,
    ) -> dict:
        """完成一次复习，使用 spaced_repetition engine 计算升降级。

        Args:
            db: 数据库会话
            review_task_id: 复习任务 ID
            is_correct: 本次作答是否正确

        Returns:
            更新后的任务信息 + 升降级详情

        Raises:
            ReviewError: 任务不存在
        """
        r = await db.execute(select(ReviewTask).where(ReviewTask.id == review_task_id))
        task = r.scalar_one_or_none()
        if task is None:
            raise ReviewError(f"复习任务不存在: id={review_task_id}")

        # 记录复习历史
        history = ReviewHistory(
            review_task_id=task.id,
            level=task.level,
            review_date=datetime.now(timezone.utc),
            result=is_correct,
        )
        db.add(history)

        # 使用 engine 计算升降级
        change = evaluate_level_change(
            level=task.level,
            consecutive_correct=task.consecutive_correct,
            consecutive_wrong=task.consecutive_wrong,
            is_correct=is_correct,
        )

        # 应用结果
        task.level = change["new_level"]
        task.consecutive_correct = change["new_consecutive_correct"]
        task.consecutive_wrong = change["new_consecutive_wrong"]

        if task.level >= MAX_LEVEL:
            task.status = ReviewTaskStatus.completed.value
            task.next_review_date = None
        else:
            task.status = ReviewTaskStatus.pending.value
            interval = compute_next_review(task.level)
            task.next_review_date = datetime.now(timezone.utc) + interval

        await db.commit()
        await db.refresh(task)

        return {
            "id": task.id,
            "level": task.level,
            "status": task.status,
            "consecutive_correct": task.consecutive_correct,
            "consecutive_wrong": task.consecutive_wrong,
            "next_review_date": task.next_review_date.isoformat() if task.next_review_date else None,
            "upgraded": change["upgraded"],
            "downgraded": change["downgraded"],
            "level_changed": change["level_changed"],
        }

    # ═══════════════════════════════════════════════════════════
    # 3.7 sync_review_tasks
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    async def sync_review_tasks(
        db: AsyncSession,
        student_id: int,
        wrong_question_ids: list[int],
    ) -> dict:
        """将错题同步为 ReviewTask。

        去重逻辑：同一 (student_id, question_id) 只保留一条。
        拉回逻辑：已完成的 ReviewTask 再次答错 → 拉回到 Level 0。
        新错题创建 ReviewTask（Level 0）。

        Returns:
            {"created": int, "pulled_back": int, "skipped": int}
        """
        created = 0
        pulled_back = 0
        skipped = 0

        for qid in set(wrong_question_ids):
            # 检查是否已存在
            existing = (await db.execute(
                select(ReviewTask).where(
                    ReviewTask.student_id == student_id,
                    ReviewTask.question_id == qid,
                )
            )).scalar_one_or_none()

            if existing is None:
                # 新建
                task = ReviewTask(
                    student_id=student_id,
                    question_id=qid,
                    level=0,
                    status=ReviewTaskStatus.pending.value,
                    consecutive_correct=0,
                    consecutive_wrong=0,
                    next_review_date=datetime.now(timezone.utc),
                )
                db.add(task)
                created += 1
            elif existing.status == ReviewTaskStatus.completed.value:
                # 已完成但再次答错 → 拉回到 Level 0
                existing.level = 0
                existing.status = ReviewTaskStatus.pending.value
                existing.consecutive_correct = 0
                existing.consecutive_wrong = 0
                existing.next_review_date = datetime.now(timezone.utc)
                pulled_back += 1
            else:
                # 已存在且未完成 → 跳过
                skipped += 1

        await db.commit()
        return {"created": created, "pulled_back": pulled_back, "skipped": skipped}

    # ═══════════════════════════════════════════════════════════
    # 3.8 get_wrong_questions
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    async def get_wrong_questions(
        db: AsyncSession,
        student_id: int,
        limit: int = 20,
        offset: int = 0,
        kp_filter: str | None = None,
    ) -> tuple[list[dict], int]:
        """获取学生的错题列表（按错误次数降序）。

        从 StudentAnswer JOIN Question 聚合，按 question_id 分组
        统计错误次数，按 wrong_count DESC 排序。

        Args:
            student_id: 学生 ID
            limit: 分页大小
            offset: 分页偏移
            kp_filter: 知识点过滤（可选，模糊匹配 JSON 列）

        Returns:
            (wrong_questions: list[dict], total: int)
        """
        # 子查询：每道错题的统计
        sa_alias = (
            select(
                StudentAnswer.question_id,
                func.count(StudentAnswer.id).label("wrong_count"),
            )
            .where(
                StudentAnswer.student_id == student_id,
                StudentAnswer.is_correct == False,
            )
            .group_by(StudentAnswer.question_id)
        ).subquery("wrong_stats")

        base_query = (
            select(Question, sa_alias.c.wrong_count)
            .join(sa_alias, Question.id == sa_alias.c.question_id)
        )

        count_query = (
            select(func.count())
            .select_from(Question)
            .join(sa_alias, Question.id == sa_alias.c.question_id)
        )

        if kp_filter:
            base_query = base_query.where(Question.knowledge_point_tags.contains(kp_filter))
            count_query = count_query.where(Question.knowledge_point_tags.contains(kp_filter))

        total = (await db.execute(count_query)).scalar() or 0

        result = await db.execute(
            base_query
            .order_by(desc(sa_alias.c.wrong_count))
            .offset(offset)
            .limit(limit)
        )

        items = []
        for q, wrong_count in result.all():
            items.append({
                "question_id": q.id,
                "content": q.content,
                "question_type": q.question_type,
                "options": q.options,
                "answer": q.answer,
                "analysis": q.analysis,
                "difficulty": q.difficulty,
                "knowledge_point_tags": q.knowledge_point_tags,
                "wrong_count": wrong_count,
            })

        return items, total

    # ═══════════════════════════════════════════════════════════
    # 3.9 generate_variants
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    async def generate_variants(
        db: AsyncSession,
        question_id: int,
        count: int = 3,
    ) -> dict:
        """为指定题目生成变式题。

        策略（设计文档 29 号 §7.5）：
        1. 先查 VariantQuestion 缓存（90 天有效期内）
        2. 不足时调用 LLM 生成
        3. 写入 VariantQuestion 表
        4. 返回变式题列表

        Args:
            db: 数据库会话
            question_id: 原题 ID
            count: 需要的变式题数量

        Returns:
            {
                "original_question_id": int,
                "variants": list[dict],
                "source": "cache" | "llm" | "mixed",
            }
        """
        # Step 1: 查缓存
        now = datetime.now(timezone.utc)
        cached_result = await db.execute(
            select(VariantQuestion)
            .where(
                VariantQuestion.original_question_id == question_id,
                VariantQuestion.expires_at > now,
            )
            .limit(count)
        )
        cached_variants = cached_result.scalars().all()

        if len(cached_variants) >= count:
            return {
                "original_question_id": question_id,
                "variants": [
                    {
                        "id": v.id,
                        "content": v.content,
                        "question_type": v.question_type,
                        "options": v.options,
                        "answer": v.answer,
                        "analysis": v.analysis,
                        "difficulty": v.difficulty,
                        "knowledge_point_tags": v.knowledge_point_tags,
                    }
                    for v in cached_variants[:count]
                ],
                "source": "cache",
            }

        # Step 2: LLM 生成
        original = (await db.execute(
            select(Question).where(Question.id == question_id)
        )).scalar_one_or_none()

        if original is None:
            raise ReviewError(f"题目不存在: id={question_id}")

        question_dict = {
            "question_type": original.question_type,
            "difficulty": original.difficulty,
            "knowledge_points": original.knowledge_point_tags or [],
            "content": original.content,
            "answer": original.answer,
            "options": original.options,
        }

        prompt = build_variant_prompt(question_dict, count)
        llm_response = await llm_chat(
            messages=[
                {"role": "system", "content": "你是一位经验丰富的中学化学教师。请严格按照 JSON 格式返回结果。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.7,
            max_tokens=3000,
        )

        # Step 3: 解析 LLM 响应并写入 VariantQuestion
        variants = ReviewService._parse_variant_response(llm_response, count)
        new_variant_ids = []
        for v in variants:
            variant = VariantQuestion(
                original_question_id=question_id,
                content=v.get("content", ""),
                question_type=original.question_type,
                options=v.get("options"),
                answer=v.get("answer", ""),
                analysis=v.get("analysis"),
                knowledge_point_tags=original.knowledge_point_tags,
                difficulty=original.difficulty,
                generated_at=now,
                expires_at=datetime(
                    now.year, now.month, now.day
                ) + timedelta(days=90),  # 90 天后过期
            )
            db.add(variant)
            await db.flush()
            new_variant_ids.append(variant.id)
            # 附加 db id 到变式题数据
            v["id"] = variant.id

        await db.commit()

        source = "mixed" if cached_variants else "llm"

        return {
            "original_question_id": question_id,
            "variants": variants,
            "source": source,
        }

    # ═══════════════════════════════════════════════════════════
    # 3.10 create_training_session
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    async def create_training_session(
        db: AsyncSession,
        student_id: int,
        question_ids: list[int],
    ) -> dict:
        """创建一次错题强化训练（临时会话，不持久化到 PracticeSession）。

        Args:
            db: 数据库会话
            student_id: 学生 ID
            question_ids: 题目 ID 列表

        Returns:
            {
                "session_id": str,  # UUID v4
                "student_id": int,
                "questions": list[dict],
            }
        """
        # 验证学生存在
        student = (await db.execute(
            select(Student).where(Student.id == student_id)
        )).scalar_one_or_none()
        if student is None:
            raise ReviewError(f"学生不存在: id={student_id}")

        # 查询题目
        questions = []
        for qid in question_ids:
            q = (await db.execute(select(Question).where(Question.id == qid))).scalar_one_or_none()
            if q:
                questions.append({
                    "id": q.id,
                    "content": q.content,
                    "question_type": q.question_type,
                    "options": q.options,
                    "answer": q.answer,
                    "analysis": q.analysis,
                    "difficulty": q.difficulty,
                    "knowledge_point_tags": q.knowledge_point_tags,
                })

        session_id = f"TR-{uuid.uuid4().hex[:12].upper()}"

        return {
            "session_id": session_id,
            "student_id": student_id,
            "questions": questions,
        }

    # ═══════════════════════════════════════════════════════════
    # 3.11 submit_training
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    async def submit_training(
        db: AsyncSession,
        session_id: str,
        student_id: int,
        answers: list[dict],
    ) -> dict:
        """提交错题强化训练结果（立即判分，不持久化训练会话）。

        Args:
            db: 数据库会话
            session_id: 训练会话 ID（UUID）
            student_id: 学生 ID
            answers: [{"question_id": int, "answer": str}, ...]

        Returns:
            {
                "session_id": str,
                "score": int,
                "total": int,
                "accuracy": float,
                "results": [...],
                "suggestion": str,  # 分档学习建议
            }
        """
        correct_count = 0
        wrong_kps: set[str] = set()
        results = []

        for a in answers:
            qid = a.get("question_id")
            answer_content = a.get("answer", "")

            q = (await db.execute(select(Question).where(Question.id == qid))).scalar_one_or_none()
            is_correct = False
            correct_answer = ""
            if q:
                correct_answer = q.answer or ""
                is_correct = answer_content.strip() == correct_answer.strip()
                if not is_correct and q.knowledge_point_tags:
                    for kp in q.knowledge_point_tags:
                        wrong_kps.add(kp)

            if is_correct:
                correct_count += 1

            results.append({
                "question_id": qid,
                "is_correct": is_correct,
                "correct_answer": correct_answer,
            })

        accuracy = correct_count / len(answers) if answers else 0.0

        # 分档学习建议
        if accuracy >= 0.9:
            suggestion = "掌握良好，建议挑战更高难度的同类题目。"
        elif accuracy >= 0.7:
            suggestion = f"仍有提升空间，重点复习：{'、'.join(list(wrong_kps)[:3])}。"
        elif accuracy >= 0.5:
            suggestion = f"基础有待巩固，建议重新学习：{'、'.join(list(wrong_kps)[:3])}，再行练习。"
        else:
            suggestion = f"概念理解存在较大困难，建议回归教材，系统梳理：{'、'.join(list(wrong_kps)[:3])}。"

        return {
            "session_id": session_id,
            "score": correct_count,
            "total": len(answers),
            "accuracy": round(accuracy, 4),
            "results": results,
            "suggestion": suggestion,
        }

    # ═══════════════════════════════════════════════════════════
    # 3.12 mark_mastered
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    async def mark_mastered(
        db: AsyncSession,
        student_id: int,
        question_id: int,
    ) -> dict:
        """标记题目为已掌握（手动标记）。

        创建或更新 ReviewTask 至 Level 5（已掌握）。

        Args:
            db: 数据库会话
            student_id: 学生 ID
            question_id: 题目 ID

        Returns:
            更新后的 ReviewTask 信息
        """
        # 查已有
        existing = (await db.execute(
            select(ReviewTask).where(
                ReviewTask.student_id == student_id,
                ReviewTask.question_id == question_id,
            )
        )).scalar_one_or_none()

        if existing is None:
            # 验证题目存在
            q = (await db.execute(select(Question).where(Question.id == question_id))).scalar_one_or_none()
            if q is None:
                raise ReviewError(f"题目不存在: id={question_id}")

            task = ReviewTask(
                student_id=student_id,
                question_id=question_id,
                level=MAX_LEVEL,
                status=ReviewTaskStatus.completed.value,
                consecutive_correct=0,
                consecutive_wrong=0,
                next_review_date=None,
            )
            db.add(task)
            await db.commit()
            await db.refresh(task)
        else:
            existing.level = MAX_LEVEL
            existing.status = ReviewTaskStatus.completed.value
            existing.consecutive_correct = 0
            existing.consecutive_wrong = 0
            existing.next_review_date = None
            await db.commit()
            await db.refresh(existing)
            task = existing

        return {
            "id": task.id,
            "student_id": task.student_id,
            "question_id": task.question_id,
            "level": task.level,
            "status": task.status,
        }

    # ═══════════════════════════════════════════════════════════
    # 内部辅助
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    def _parse_variant_response(llm_response: str, expected_count: int) -> list[dict]:
        """解析 LLM 返回的变式题 JSON 数组。"""
        # 尝试提取 JSON 数组
        text = llm_response.strip()
        # 移除可能的 markdown 代码块包装
        if text.startswith("```"):
            lines = text.split("\n")
            # 移除首行 ```json 或 ``` 和末行 ```
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines)

        try:
            variants = json.loads(text)
            if isinstance(variants, list):
                return variants[:expected_count]
            elif isinstance(variants, dict) and "variants" in variants:
                return variants["variants"][:expected_count]
            else:
                logger.warning("LLM 返回了非预期的格式: %s", text[:200])
                return []
        except json.JSONDecodeError:
            logger.warning("LLM 返回的 JSON 解析失败: %s", text[:200])
            return []
