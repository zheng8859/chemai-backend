"""自适应练习服务 — ZPD 驱动出题 + 作答提交 + 效果跟踪。

设计文档 28 号 + tasks.md §3.1-3.5。
"""

import logging
import time
import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from ..models.teaching import (
    PracticeSession,
    PracticeSessionQuestion,
    StudentAnswer,
    Question,
)
from ..models.user import Student
from ..core.enums import PracticeSessionStatus, QuestionSource, QuestionType

from chem_skills.chemistry_memory.zpd_engine import (
    compute_zpd_difficulty,
    extract_weak_knowledge_points,
    identify_dominant_barrier,
)
from chem_skills.chemistry_memory.strategy_matrix import apply_strategy

logger = logging.getLogger(__name__)


class AdaptivePracticeError(Exception):
    """自适应练习服务异常。"""
    def __init__(self, detail: str, error_code: str = "PRACTICE_ERROR"):
        self.detail = detail
        self.error_code = error_code
        super().__init__(detail)


class AdaptivePracticeService:
    """自适应练习服务。

    所有方法均为 static method，db 会话由调用方传入。
    依赖 LLM service 作为外部注入参数。
    """

    # ═══════════════════════════════════════════════════════════
    # 3.2 create_practice — 7 步流水线
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    async def create_practice(
        db: AsyncSession,
        student_id: int,
        question_count: int = 10,
        kp_override: list[str] | None = None,
    ) -> dict:
        """为学生创建一份自适应练习。

        7 步流水线：
        1. 读取学生画像（barrier_profile, weak_knowledge_points）
        2. ZPD 难度计算（最近 30 条作答）
        3. 薄弱知识点提取
        4. 确定目标知识点
        5. 题库检索（RAG）
        6. LLM 生成不足题目（若题库不足）
        7. 创建 PracticeSession + PracticeSessionQuestion 记录

        Args:
            db: 数据库会话
            student_id: 学生 ID
            question_count: 题目数量（默认 10）
            kp_override: 手动覆盖的知识点列表（可选，用于教师分配）

        Returns:
            {
                "practice_id": str,
                "title": str,
                "question_count": int,
                "questions": list[dict],
                "zpd_difficulty": str,
                "dominant_barrier": str,
                "target_kps": list[str],
            }

        Raises:
            AdaptivePracticeError: 学生不存在
        """
        # Step 1: 读取学生画像
        student = (await db.execute(
            select(Student).where(Student.id == student_id)
        )).scalar_one_or_none()
        if student is None:
            raise AdaptivePracticeError(f"学生不存在: id={student_id}")

        barrier_profile = student.barrier_profile
        weak_kps = student.weak_knowledge_points or []

        # Step 2: ZPD 难度计算
        zpd_difficulty = await AdaptivePracticeService._calc_zpd(db, student_id)

        # Step 3: 薄弱知识点
        if not weak_kps:
            weak_kps = await AdaptivePracticeService._derive_weak_kps(db, student_id)

        # Step 4: 确定目标知识点
        if kp_override:
            target_kps = kp_override
        else:
            target_kps = weak_kps[:3]  # Top 3 薄弱点

        # Step 5: 主导障碍 + 策略
        dominant_barrier = identify_dominant_barrier(barrier_profile)
        strategy = apply_strategy(dominant_barrier, zpd_difficulty)
        final_difficulty = strategy["difficulty"]

        # Step 6: 题库检索 + LLM 补足
        questions = await AdaptivePracticeService._fetch_questions_from_bank(
            db, target_kps, final_difficulty, question_count, strategy,
        )

        # Step 7: 创建 PracticeSession
        practice_id = f"PR-{int(time.time())}-{uuid.uuid4().hex[:8].upper()}"
        session = PracticeSession(
            practice_id=practice_id,
            student_id=student_id,
            title=f"自适应练习 - {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')}",
            barrier_type=dominant_barrier,
            status=PracticeSessionStatus.in_progress.value,
            question_count=len(questions),
            knowledge_point_tags=target_kps,
        )
        db.add(session)
        await db.flush()

        # 创建关联记录
        for idx, q in enumerate(questions):
            psq = PracticeSessionQuestion(
                practice_session_id=session.id,
                question_id=q["id"],
                sort_order=idx + 1,
            )
            db.add(psq)

        await db.commit()
        await db.refresh(session)

        return {
            "practice_id": practice_id,
            "title": session.title,
            "question_count": len(questions),
            "questions": questions,
            "zpd_difficulty": zpd_difficulty,
            "dominant_barrier": dominant_barrier,
            "target_kps": target_kps,
        }

    # ═══════════════════════════════════════════════════════════
    # 3.3 get_student_tasks
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    async def get_student_tasks(
        db: AsyncSession,
        student_id: int,
    ) -> dict:
        """获取学生的练习任务列表。

        Returns:
            {
                "pending": [...],
                "completed": [...],
            }
        """
        # 待完成
        pending_result = await db.execute(
            select(PracticeSession)
            .where(
                PracticeSession.student_id == student_id,
                PracticeSession.status == PracticeSessionStatus.in_progress.value,
            )
            .order_by(PracticeSession.created_at.desc())
        )
        pending = pending_result.scalars().all()

        # 已完成
        completed_result = await db.execute(
            select(PracticeSession)
            .where(
                PracticeSession.student_id == student_id,
                PracticeSession.status == PracticeSessionStatus.completed.value,
            )
            .order_by(PracticeSession.created_at.desc())
        )
        completed = completed_result.scalars().all()

        def _format_session(s: PracticeSession) -> dict:
            return {
                "practice_id": s.practice_id,
                "title": s.title,
                "question_count": s.question_count,
                "status": s.status,
                "created_at": s.created_at.isoformat() if s.created_at else None,
                "deadline": s.deadline.isoformat() if s.deadline else None,
            }

        return {
            "pending": [_format_session(s) for s in pending],
            "completed": [_format_session(s) for s in completed],
        }

    # ═══════════════════════════════════════════════════════════
    # 3.4 submit_practice
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    async def submit_practice(
        db: AsyncSession,
        practice_id: str,
        answers: list[dict],
        current_user_id: int | None = None,
    ) -> dict:
        """提交练习答案。

        Args:
            db: 数据库会话
            practice_id: 练习业务 ID
            answers: [
                {"question_id": int, "answer": str},
                ...
            ]
            current_user_id: 当前认证用户的 Account.id，用于校验练习归属

        Returns:
            {
                "score": int,
                "total": int,
                "accuracy": float,
                "results": [{"question_id": int, "is_correct": bool, "correct_answer": str}, ...],
            }

        Raises:
            AdaptivePracticeError: 练习不存在、已提交、或不属于该学生
        """
        session = (await db.execute(
            select(PracticeSession).where(
                PracticeSession.practice_id == practice_id
            )
        )).scalar_one_or_none()
        if session is None:
            raise AdaptivePracticeError(f"练习不存在: {practice_id}")
        if session.status == PracticeSessionStatus.completed.value:
            raise AdaptivePracticeError("该练习已提交，不能重复提交", "DUPLICATE_SUBMIT")

        # 校验练习归属：session.student_id 必须匹配当前认证用户
        if current_user_id is not None:
            from ..models.user import Student
            student_result = await db.execute(
                select(Student).where(Student.account_id == current_user_id)
            )
            student = student_result.scalar_one_or_none()
            if student is None or student.id != session.student_id:
                raise AdaptivePracticeError(
                    "该练习不属于当前用户", "PRACTICE_NOT_OWNED"
                )

        # 取关联题目
        psq_result = await db.execute(
            select(PracticeSessionQuestion)
            .where(PracticeSessionQuestion.practice_session_id == session.id)
            .order_by(PracticeSessionQuestion.sort_order)
        )
        psq_list = psq_result.scalars().all()

        question_map = {}
        for psq in psq_list:
            q = (await db.execute(select(Question).where(Question.id == psq.question_id))).scalar_one_or_none()
            if q:
                question_map[q.id] = q

        # 判定并创建作答记录
        results = []
        correct_count = 0
        for a in answers:
            qid = a.get("question_id")
            answer_content = a.get("answer", "")
            question = question_map.get(qid)

            is_correct = False
            correct_answer = ""
            if question:
                correct_answer = question.answer or ""
                is_correct = answer_content.strip() == correct_answer.strip()

            if is_correct:
                correct_count += 1

            # 写入 StudentAnswer
            if question:
                sa = StudentAnswer(
                    student_id=session.student_id,
                    question_id=qid,
                    answer_content=answer_content,
                    is_correct=is_correct,
                )
                db.add(sa)

            results.append({
                "question_id": qid,
                "is_correct": is_correct,
                "correct_answer": correct_answer,
            })

        # 更新练习状态
        session.status = PracticeSessionStatus.completed.value

        # auto-sync：答错题目自动创建/更新 ReviewTask（间隔复习）
        from .review_service import ReviewService
        wrong_qids = [r["question_id"] for r in results if not r["is_correct"]]
        if wrong_qids:
            await ReviewService.sync_review_tasks(
                db, session.student_id, wrong_qids,
            )

        await db.commit()

        return {
            "score": correct_count,
            "total": len(answers),
            "accuracy": correct_count / len(answers) if answers else 0.0,
            "results": results,
        }

    # ═══════════════════════════════════════════════════════════
    # 3.5 get_practice_effect
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    async def get_practice_effect(
        db: AsyncSession,
        student_id: int,
    ) -> dict:
        """对比最近 2 次练习的正确率变化。

        Returns:
            {
                "latest_accuracy": float | None,
                "previous_accuracy": float | None,
                "improvement_rate": float | None,  # 正数=进步，负数=退步
                "latest_practice_id": str | None,
                "latest_completed_at": str | None,
            }
        """
        # 已完成的练习，按提交时间倒序
        result = await db.execute(
            select(PracticeSession)
            .where(
                PracticeSession.student_id == student_id,
                PracticeSession.status == PracticeSessionStatus.completed.value,
            )
            .order_by(PracticeSession.created_at.desc())
            .limit(2)
        )
        sessions = result.scalars().all()

        if len(sessions) < 2:
            return {
                "latest_accuracy": None,
                "previous_accuracy": None,
                "improvement_rate": None,
                "latest_practice_id": sessions[0].practice_id if sessions else None,
                "latest_completed_at": (
                    sessions[0].updated_at.isoformat()
                    if sessions and sessions[0].updated_at else None
                ),
            }

        latest = sessions[0]
        previous = sessions[1]

        # 计算正确率（通过 PracticeSessionQuestion 关联的题目 ID）
        async def _get_accuracy(session: PracticeSession) -> float:
            psq_ids_result = await db.execute(
                select(PracticeSessionQuestion.question_id)
                .where(PracticeSessionQuestion.practice_session_id == session.id)
            )
            qids = [row[0] for row in psq_ids_result.all()]
            if not qids:
                return 0.0
            total = await db.execute(
                select(func.count(StudentAnswer.id)).where(
                    StudentAnswer.student_id == session.student_id,
                    StudentAnswer.question_id.in_(qids),
                )
            )
            correct = await db.execute(
                select(func.count(StudentAnswer.id)).where(
                    StudentAnswer.student_id == session.student_id,
                    StudentAnswer.question_id.in_(qids),
                    StudentAnswer.is_correct == True,
                )
            )
            t = total.scalar() or 0
            c = correct.scalar() or 0
            return c / t if t > 0 else 0.0

        latest_acc = await _get_accuracy(latest)
        prev_acc = await _get_accuracy(previous)

        improvement = latest_acc - prev_acc if prev_acc is not None else None

        return {
            "latest_accuracy": round(latest_acc, 4),
            "previous_accuracy": round(prev_acc, 4),
            "improvement_rate": round(improvement, 4) if improvement is not None else None,
            "latest_practice_id": latest.practice_id,
            "latest_completed_at": (
                latest.updated_at.isoformat() if latest.updated_at else None
            ),
        }

    # ═══════════════════════════════════════════════════════════
    # 内部辅助方法
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    async def _calc_zpd(db: AsyncSession, student_id: int) -> str:
        """计算学生 ZPD 难度（基于最近 30 条作答）。"""
        result = await db.execute(
            select(StudentAnswer.is_correct)
            .where(StudentAnswer.student_id == student_id)
            .order_by(StudentAnswer.created_at.desc())
            .limit(30)
        )
        answers = [row[0] for row in result.all()]
        return compute_zpd_difficulty(answers)

    @staticmethod
    async def _derive_weak_kps(db: AsyncSession, student_id: int) -> list[str]:
        """从错题记录中推导薄弱知识点。"""
        result = await db.execute(
            select(StudentAnswer)
            .join(Question, Question.id == StudentAnswer.question_id)
            .where(
                StudentAnswer.student_id == student_id,
                StudentAnswer.is_correct == False,
            )
            .order_by(StudentAnswer.created_at.desc())
            .limit(100)
        )
        wrong_list = []
        for sa in result.scalars().all():
            wrong_list.append({
                "knowledge_points": sa.question.knowledge_point_tags if sa.question else [],
            })
        return extract_weak_knowledge_points(wrong_list)

    @staticmethod
    async def _fetch_questions_from_bank(
        db: AsyncSession,
        kps: list[str],
        difficulty: str,
        count: int,
        strategy: dict | None = None,
    ) -> list[dict]:
        """从题库中按知识点和难度检索题目，不足时由 LLM 补足。

        1. 题库检索（排除 variant 来源）
        2. 若数量不足 → 调 LLM 生成差额
        3. LLM 生成的题目写入 Question 表（source=ai_generated）
        4. 返回合并后的题目列表
        """
        # ── 1. 题库检索 ──────────────────────────────────────────
        if not kps:
            result = await db.execute(
                select(Question)
                .where(
                    Question.difficulty == difficulty,
                )
                .order_by(func.random())
                .limit(count)
            )
        else:
            conditions = [Question.difficulty == difficulty]
            kp_conditions = []
            for kp in kps:
                kp_conditions.append(Question.knowledge_point_tags.contains(kp))
            if kp_conditions:
                from sqlalchemy import or_
                conditions.append(or_(*kp_conditions))

            result = await db.execute(
                select(Question)
                .where(*conditions)
                .order_by(func.random())
                .limit(count)
            )

        bank_questions = result.scalars().all()
        bank_dicts = [
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
            for q in bank_questions
        ]

        shortfall = count - len(bank_dicts)
        if shortfall <= 0:
            return bank_dicts

        # ── 2. LLM 补足 ─────────────────────────────────────────
        logger.info(
            f"题库不足：需要 {count} 题，命中 {len(bank_dicts)}，LLM 补足 {shortfall}"
        )
        try:
            llm_questions = await AdaptivePracticeService._generate_questions_via_llm(
                db, kps, difficulty, shortfall, strategy,
            )
            return bank_dicts + llm_questions
        except Exception as e:
            logger.warning(f"LLM 补题失败，仅返回题库命中: {e}")
            return bank_dicts

    @staticmethod
    async def _generate_questions_via_llm(
        db: AsyncSession,
        kps: list[str],
        difficulty: str,
        count: int,
        strategy: dict | None = None,
    ) -> list[dict]:
        """调用 LLM 生成化学题目并写入 Question 表。

        Args:
            db: 数据库会话
            kps: 目标知识点列表
            difficulty: 难度等级
            count: 需要生成的数量
            strategy: 策略矩阵输出（含 question_type_weights）

        Returns:
            生成的题目 dict 列表（已持久化，含 id）
        """
        import json
        from ..llm.router import llm_chat

        kp_str = "、".join(kps) if kps else "中学化学"
        difficulty_cn = {"easy": "简单", "medium": "中等", "hard": "困难"}.get(
            difficulty, "中等"
        )

        # v1.0 仅选择题型，后续版本按策略矩阵启用多题型
        prompt = f"""你是一位经验丰富的中学化学教师，请生成 {count} 道化学选择题。

**要求：**
- 知识点：{kp_str}
- 难度：{difficulty_cn}（{difficulty}）
- 题型：选择题（4 个选项 A/B/C/D）
- 每道题必须包含完整题面、4 个选项（A/B/C/D）、正确答案、简要解析（1-2 句）
- 题面使用 LaTeX（$...$）书写化学式和方程式
- 确保题目科学准确，知识点明确

**输出格式（必须是合法的 JSON 数组）：**
```json
[
  {{
    "content": "题面内容",
    "options": ["A. ...", "B. ...", "C. ...", "D. ..."],
    "answer": "A",
    "analysis": "解析",
    "question_type": "choice",
    "difficulty": "{difficulty}",
    "knowledge_point_tags": ["{kp_str}"]
  }}
]
```

请直接返回 JSON 数组，不要包含其他文字。"""

        messages = [
            {"role": "system", "content": "你是一位经验丰富的中学化学教师，擅长编写高质量的化学试题。请始终以 JSON 格式返回结果。"},
            {"role": "user", "content": prompt},
        ]

        response = await llm_chat(messages, temperature=0.7, max_tokens=4096, json_mode=True)

        # 解析 JSON 响应
        try:
            parsed = json.loads(response)
        except json.JSONDecodeError:
            # 尝试提取 JSON 数组
            start = response.find("[")
            end = response.rfind("]") + 1
            if start >= 0 and end > start:
                parsed = json.loads(response[start:end])
            else:
                raise ValueError(f"无法解析 LLM 响应为 JSON: {response[:200]}")

        if not isinstance(parsed, list):
            parsed = [parsed]

        # 四维审核引擎校验（科学性 / 方程式配平 / 物质稳定性 / 反应条件）
        from chem_skills.chemistry_parser.engine import audit_equation, extract_equations

        # 写入 Question 表（跳过审核不通过的题目）
        generated = []
        skipped = 0
        for item in parsed[:count]:
            content = item.get("content", "")

            # 提取并审核化学方程式
            equations = extract_equations(content)
            audit_failed = False
            for eq in equations:
                report = audit_equation(eq)
                if report.has_errors:
                    logger.warning(
                        "LLM 生成题目审核不通过，跳过: equation=%s, errors=%s",
                        eq, [e.message for e in report.errors],
                    )
                    audit_failed = True
                    break

            if audit_failed:
                skipped += 1
                continue

            q = Question(
                content=content,
                question_type=item.get("question_type", "choice"),
                options=item.get("options", []),
                answer=item.get("answer", ""),
                analysis=item.get("analysis", ""),
                difficulty=difficulty,
                knowledge_point_tags=item.get("knowledge_point_tags", kps),
                source=QuestionSource.ai_generated,
            )
            db.add(q)
            await db.flush()
            generated.append({
                "id": q.id,
                "content": q.content,
                "question_type": q.question_type,
                "options": q.options,
                "answer": q.answer,
                "analysis": q.analysis,
                "difficulty": q.difficulty,
                "knowledge_point_tags": q.knowledge_point_tags,
            })

        if skipped > 0:
            logger.info(f"LLM 生成题目：{len(generated)} 道通过审核，{skipped} 道被跳过")
        else:
            logger.info(f"LLM 成功生成 {len(generated)} 道题目")
        return generated
