"""批改引擎 — 答案来源选择 + 双路径批改。

P2: 三模式答案源 + correct_edu / LLM 批改（tasks 6.1-6.6）
P3: 保存结果 + 诊断联动（tasks 8.1-8.5）
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..core.enums import OCRTaskStatus
from ..models.ocr import OCRTask
from ..models.exam_paper import ExamPaper, ExamPaperQuestion
from ..models.teaching import Question
from ..schemas.ocr import QuestionGrading, GradingResult, GradingSummary

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# 6.2: AnswerKey 数据类（内部使用，无对应 API schema）
# ═══════════════════════════════════════════════════════════════

@dataclass
class AnswerKey:
    """正确答案集。"""
    source_mode: str = "llm_auto"  # exam_paper | teacher_input | llm_auto
    question_count: int = 0
    questions: dict[int, str] = field(default_factory=dict)  # {q_number: correct_answer}


# ═══════════════════════════════════════════════════════════════
# 6.1: 答案来源选择
# ═══════════════════════════════════════════════════════════════

class GradingService:

    @staticmethod
    async def resolve_answer_source(
        db: AsyncSession,
        exam_paper_id: Optional[int] = None,
        teacher_answers: Optional[dict[str, str]] = None,
    ) -> AnswerKey:
        """三模式答案来源解析。

        优先级：教师录入 > 题库匹配 > LLM 自判
        """
        # 模式 2: 教师录入（最高优先级）
        if teacher_answers:
            # Convert string keys to int
            questions = {int(k): v for k, v in teacher_answers.items()}
            return AnswerKey(
                source_mode="teacher_input",
                question_count=len(questions),
                questions=questions,
            )

        # 模式 1: 题库匹配
        if exam_paper_id:
            try:
                # 查询试卷的所有题目
                result = await db.execute(
                    select(ExamPaperQuestion)
                    .where(ExamPaperQuestion.exam_paper_id == exam_paper_id)
                    .order_by(ExamPaperQuestion.sort_order.asc())
                )
                ep_questions = result.scalars().all()

                if ep_questions:
                    questions = {}
                    for eq in ep_questions:
                        # 查询题目的正确答案
                        q_result = await db.execute(
                            select(Question).where(Question.id == eq.question_id)
                        )
                        question = q_result.scalar_one_or_none()
                        if question and question.answer:
                            questions[eq.sort_order] = question.answer

                    if questions:
                        return AnswerKey(
                            source_mode="exam_paper",
                            question_count=len(questions),
                            questions=questions,
                        )
            except Exception as e:
                logger.warning("[grading] 题库匹配失败: %s", e)

        # 模式 3: LLM 自判（fallback）
        return AnswerKey(
            source_mode="llm_auto",
            question_count=0,
            questions={},
        )

    # ═══════════════════════════════════════════════════════════
    # 6.3-6.4: 双路径批改（correct_edu → LLM 降级）
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    async def _grade_with_fallback(
        ocr_text: str,
        answer_key: AnswerKey,
        task_id: int,
        student_id_raw: Optional[str] = None,
        student_name_raw: Optional[str] = None,
        image_path: str = "",
    ) -> GradingResult:
        """6.3: correct_edu 优先 → LLM 降级。

        仅选择题答题卡使用 correct_edu；非选择题/LLM 自判模式直接走 LLM。
        """
        from .ocr_engine import BaiduOCREngine

        # 仅选择题场景且答案源非 llm_auto 时尝试 correct_edu
        if answer_key.source_mode != "llm_auto" and image_path:
            try:
                edu_result = await BaiduOCREngine.grade_via_correct_edu(
                    image_path,
                    answer_key=answer_key.questions,
                )
                if edu_result.get("success") and edu_result.get("results"):
                    # 转换 correct_edu 结果为 GradingResult
                    questions = []
                    correct_count = 0
                    for q in edu_result["results"]:
                        is_correct = q.get("is_correct", False)
                        if is_correct:
                            correct_count += 1
                        questions.append(QuestionGrading(
                            q_number=q.get("q_number", 0),
                            student_answer=q.get("student_answer", ""),
                            correct_answer=q.get("correct_answer", ""),
                            is_correct=is_correct,
                            reason=q.get("status_text", ""),
                            confidence=0.95,
                        ))
                    total = len(questions)
                    score = (correct_count / total * 100) if total > 0 else 0
                    return GradingResult(
                        task_id=task_id,
                        student_id_raw=student_id_raw,
                        student_name_raw=student_name_raw,
                        total_score=round(score, 1),
                        max_score=100.0,
                        engine="correct_edu",
                        questions=questions,
                    )
            except Exception as e:
                logger.info("[grading] correct_edu 失败，降级到 LLM: %s", e)

        # 降级到 LLM 批改
        return await GradingService._grade_via_llm(
            ocr_text, answer_key, task_id,
            student_id_raw, student_name_raw,
        )

    # ═══════════════════════════════════════════════════════════
    # 6.4: LLM 语义批改
    # ═══════════════════════════════════════════════════════════

    GRADING_PROMPT = """你是化学老师批改助手。基于以下信息批改学生答案。

OCR 识别文本：
---
{ocr_text}
---

正确答案：
{answer_key}

要求：
1. 逐题判定正确/错误
2. 选择题只需匹配字母（不区分大小写）
3. 非选择题判断化学等价性：
   - 化学式下标等效：H2O ≡ H₂O, Fe3+ ≡ Fe³⁺
   - 方程式箭头等效：→ ≡ =
   - 忽略多余空格和括号
   - 等价概念（如 氧化反应 ≈ 氧化还原反应）

返回 JSON：
```json
{{
  "questions": [
    {{"q_number": 1, "student_answer": "C", "is_correct": true, "reason": ""}},
    {{"q_number": 16, "student_answer": "H2O", "is_correct": true, "reason": "化学式等效(H2O≡H₂O)"}},
    {{"q_number": 17, "student_answer": "氧化反应", "is_correct": false, "reason": "应为氧化还原反应,缺少还原"}}
  ],
  "needs_review": false
}}
```"""

    @staticmethod
    async def _grade_via_llm(
        ocr_text: str,
        answer_key: AnswerKey,
        task_id: int,
        student_id_raw: Optional[str] = None,
        student_name_raw: Optional[str] = None,
    ) -> GradingResult:
        """LLM 语义批改。"""
        from ..llm.router import llm_chat
        from .answer_parser import parse_answers_from_text

        # 解析学生答案
        parse_result = await parse_answers_from_text(
            ocr_text, question_count=answer_key.question_count,
        )

        if not parse_result.answers:
            return GradingResult(
                task_id=task_id,
                student_id_raw=student_id_raw,
                student_name_raw=student_name_raw,
                total_score=0,
                engine="llm_semantic",
                degraded=True,
                error="无法解析学生答案",
                needs_review=True,
            )

        # 如果有正确答案（非 LLM 自判模式），用 LLM 对比
        if answer_key.source_mode != "llm_auto":
            # 构建 answer_key 文本
            key_lines = []
            for q_num, ans in sorted(answer_key.questions.items()):
                key_lines.append(f"{q_num}. {ans}")
            key_text = "\n".join(key_lines)

            prompt = GradingService.GRADING_PROMPT.format(
                ocr_text=ocr_text[:4000],
                answer_key=key_text,
            )

            try:
                response = await llm_chat(
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.1,
                    json_mode=True,
                )
                data = json.loads(response)

                questions = []
                correct_count = 0
                for q_data in data.get("questions", []):
                    q_num = q_data.get("q_number", 0)
                    is_correct = q_data.get("is_correct", False)
                    if is_correct:
                        correct_count += 1
                    questions.append(QuestionGrading(
                        q_number=q_num,
                        student_answer=q_data.get("student_answer", ""),
                        correct_answer=answer_key.questions.get(q_num, ""),
                        is_correct=is_correct,
                        reason=q_data.get("reason", ""),
                        needs_review=q_data.get("needs_review", False),
                        confidence=0.85,
                    ))

                total = len(questions)
                score = (correct_count / total * 100) if total > 0 else 0

                return GradingResult(
                    task_id=task_id,
                    student_id_raw=student_id_raw,
                    student_name_raw=student_name_raw,
                    total_score=round(score, 1),
                    max_score=100.0,
                    engine="llm_semantic",
                    questions=questions,
                    needs_review=data.get("needs_review", False),
                )

            except Exception as e:
                logger.warning("[grading] LLM 批改失败: %s", e)
                return GradingResult(
                    task_id=task_id,
                    engine="llm_semantic",
                    degraded=True,
                    error=str(e)[:200],
                    needs_review=True,
                )

        # LLM 自判模式：标记全部需要教师复核
        questions = []
        for ans in parse_result.answers:
            is_correct = False
            reason = "待教师确认"
            # 选择题用简单比较
            if ans.question_type == "choice":
                result = GradingService._compare_choice_answer(
                    ans.student_answer, "AUTO",
                )
                is_correct = result[0]
                reason = result[1]

            questions.append(QuestionGrading(
                q_number=ans.q_number,
                student_answer=ans.student_answer,
                correct_answer="AUTO",
                is_correct=is_correct,
                reason=reason,
                needs_review=True,
                confidence=0.5,
            ))

        return GradingResult(
            task_id=task_id,
            student_id_raw=student_id_raw,
            student_name_raw=student_name_raw,
            engine="llm_auto",
            degraded=True,
            questions=questions,
            needs_review=True,
        )

    # ═══════════════════════════════════════════════════════════
    # 6.5: 选择题字符串比较
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    def _compare_choice_answer(
        student_answer: str,
        correct_answer: str,
    ) -> tuple[bool, str]:
        """选择题比较：strip + upper + exact match + empty/AUTO 处理。"""
        # AUTO 模式
        if correct_answer == "AUTO":
            return False, "待教师确认"

        # 空答案
        stripped = student_answer.strip().upper()
        if not stripped:
            return False, "未作答"

        # 精确匹配
        correct = correct_answer.strip().upper()
        if stripped == correct:
            return True, ""

        return False, f"答案不匹配: 学生={stripped}, 正确答案={correct}"

    # ═══════════════════════════════════════════════════════════
    # 6.6: 化学等价判断（LLM 语义等价）
    # ═══════════════════════════════════════════════════════════

    CHEM_EQUIVALENCE_PROMPT = """判断两个化学表达式是否等价。

学生答案: {student_answer}
正确答案: {correct_answer}

判断规则：
- 化学式下标等效：H2O ≡ H₂O, Fe3+ ≡ Fe³⁺
- 方程式箭头等效：→ ≡ =, ⇌ ≡ ↔
- 忽略多余空格、括号顺序
- 化学概念等价判断（如 燃烧 ≈ 剧烈氧化，但 氧化反应 ≠ 氧化还原反应）

返回 JSON: {{"is_equivalent": true/false, "reason": ""}}"""

    @staticmethod
    async def _compare_chemical_answer(
        student_answer: str,
        correct_answer: str,
    ) -> tuple[bool, str]:
        """非选择题化学等价判断（LLM 语义等价）。"""
        from ..llm.router import llm_chat

        # 空答案
        if not student_answer.strip():
            return False, "未作答"

        # 简单字符串匹配（快速路径）
        sa = student_answer.strip().lower().replace(" ", "")
        ca = correct_answer.strip().lower().replace(" ", "")
        if sa == ca:
            return True, ""

        # LLM 化学等价判断
        prompt = GradingService.CHEM_EQUIVALENCE_PROMPT.format(
            student_answer=student_answer,
            correct_answer=correct_answer,
        )

        try:
            response = await llm_chat(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
                json_mode=True,
            )
            data = json.loads(response)
            is_equiv = data.get("is_equivalent", False)
            reason = data.get("reason", "")
            return is_equiv, reason
        except Exception as e:
            logger.warning("[grading] 化学等价判断失败: %s", e)
            # 失败时保守处理：标记为需要复核
            return False, f"化学等价判断失败: {str(e)[:100]}"

    # ═══════════════════════════════════════════════════════════
    # 6.1/6.4: 批改主入口
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    async def grade_task(
        db: AsyncSession,
        task_id: int,
        answer_key: AnswerKey,
    ) -> GradingResult:
        """对单个 OCR 任务执行批改。"""
        # 获取 OCR 任务
        result = await db.execute(
            select(OCRTask).where(OCRTask.id == task_id)
        )
        task = result.scalar_one_or_none()

        if not task:
            return GradingResult(
                task_id=task_id,
                error="OCR 任务不存在",
                needs_review=True,
            )

        if task.status != OCRTaskStatus.done:
            return GradingResult(
                task_id=task_id,
                error=f"任务状态不正确: {task.status}",
                needs_review=True,
            )

        # 获取 OCR 文本
        ocr_result = task.ocr_raw_result or {}
        raw_text = ocr_result.get("raw_text", "")

        if not raw_text:
            return GradingResult(
                task_id=task_id,
                student_id_raw=task.student_id_raw,
                student_name_raw=task.student_name_raw,
                error="OCR 文本为空",
                needs_review=True,
            )

        # 双路径批改：correct_edu 优先 → LLM 降级
        grading_result = await GradingService._grade_with_fallback(
            raw_text, answer_key, task_id,
            task.student_id_raw, task.student_name_raw,
            task.image_path,
        )

        # 存储批改结果到 task
        task.grading_result = {
            "engine": grading_result.engine,
            "total_score": grading_result.total_score,
            "questions": [
                {
                    "q_number": q.q_number,
                    "student_answer": q.student_answer,
                    "correct_answer": q.correct_answer,
                    "is_correct": q.is_correct,
                    "reason": q.reason,
                }
                for q in grading_result.questions
            ],
            "needs_review": grading_result.needs_review,
        }
        await db.commit()

        return grading_result

    # ═══════════════════════════════════════════════════════════
    # 8.1-8.4: 保存结果 + 诊断联动
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    async def save_results(
        db: AsyncSession,
        task_ids: list[int],
    ) -> dict:
        """8.1: 查询已完成批改的 task → 校验 → 双写 StudentSubmission + StudentAnswer。

        Returns:
            {"saved_count": int, "skipped_count": int, "diagnosis_triggered": bool}
        """
        from ..models.user import Student
        from ..models.teaching import StudentAnswer
        from ..models.ocr import StudentSubmission, UploadSession
        from ..core.enums import BarrierType, UploadSessionStatus

        saved_count = 0
        skipped = []

        for task_id in task_ids:
            # 查询已批改的 task
            result = await db.execute(
                select(OCRTask).where(OCRTask.id == task_id)
            )
            task = result.scalar_one_or_none()

            if not task:
                skipped.append({"task_id": task_id, "reason": "任务不存在"})
                continue

            if not task.grading_result:
                skipped.append({"task_id": task_id, "reason": "尚未批改"})
                continue

            if task.confirmed:
                skipped.append({"task_id": task_id, "reason": "已确认保存（幂等）"})
                continue

            # 8.2: 脏数据保护 — 学号匹配
            student = None
            if task.student_id_raw:
                s_result = await db.execute(
                    select(Student).where(
                        Student.student_id == task.student_id_raw,
                    )
                )
                student = s_result.scalar_one_or_none()

            if not student and task.student_id_raw:
                skipped.append({
                    "task_id": task_id,
                    "reason": f"学号 {task.student_id_raw} 不在学生表中",
                })
                continue

            # 双写 StudentSubmission + StudentAnswer
            grading = task.grading_result

            # StudentSubmission
            submission = StudentSubmission(
                exam_record_id=1,  # P4 将从 UploadSession 关联
                student_id=student.id if student else 0,
                class_id=student.class_id if student else 0,
                original_image=task.image_path,
                answer_list=grading.get("questions", []),
                total_score=grading.get("total_score"),
            )
            db.add(submission)
            await db.flush()

            # StudentAnswer — 逐题写入
            for q in grading.get("questions", []):
                answer = StudentAnswer(
                    question_id=0,  # P4 将从 ExamPaper 关联
                    student_id=student.id if student else 0,
                    exam_record_id=1,
                    answer_content=q.get("student_answer", ""),
                    is_correct=q.get("is_correct", False),
                    barrier_type=BarrierType.concept if not q.get("is_correct") else None,
                )
                db.add(answer)

            # 标记为已确认
            task.confirmed = True

            saved_count += 1

        # 诊断触发标记
        diagnosis_triggered = saved_count > 0

        await db.commit()

        # 更新已保存任务的会话状态：grading → graded
        if saved_count > 0:
            saved_task_ids = [
                tid for tid in task_ids
                if not any(s["task_id"] == tid for s in skipped)
            ]
            if saved_task_ids:
                from sqlalchemy import update as _update, select as _select
                # 获取涉及到的 session ids
                tasks_result = await db.execute(
                    _select(OCRTask.upload_session_id).where(
                        OCRTask.id.in_(saved_task_ids)
                    ).distinct()
                )
                session_ids = [row[0] for row in tasks_result.fetchall()]
                if session_ids:
                    await db.execute(
                        _update(UploadSession)
                        .where(UploadSession.id.in_(session_ids))
                        .values(status=UploadSessionStatus.graded)
                    )
                    await db.commit()
                    logger.info("[grading] 会话状态更新为 graded: %s", session_ids)

        logger.info(
            "[grading] 保存结果: saved=%d, skipped=%d, diagnosis=%s",
            saved_count, len(skipped), diagnosis_triggered,
        )

        return {
            "saved_count": saved_count,
            "skipped_count": len(skipped),
            "skipped_details": skipped,
            "diagnosis_triggered": diagnosis_triggered,
        }

    @staticmethod
    async def _post_save_pipeline(saved_count: int) -> None:
        """8.3: 异步执行诊断→统计→报告链。

        8.4: 各步独立 try/catch，前一步失败不阻塞后续。
        """
        if saved_count == 0:
            return

        logger.info("[grading] 启动后保存管线: %d 条记录", saved_count)

        from ..infrastructure.database import MainSession

        # Step 1: 障碍诊断
        try:
            async with MainSession() as db:
                logger.info("[grading] 诊断步骤: 待 P4 诊断引擎接入")
        except Exception as e:
            logger.warning("[grading] 诊断失败: %s", e)

        # Step 2: 班级统计
        try:
            async with MainSession() as db:
                logger.info("[grading] 统计步骤: 待 exam_record_id 关联后自动触发")
        except Exception as e:
            logger.warning("[grading] 统计失败: %s", e)

        # Step 3: LLM 分析报告
        try:
            logger.info("[grading] 报告步骤: 待通过 /ocr/stats 端点手动触发")
        except Exception as e:
            logger.warning("[grading] 报告失败: %s", e)


# ═══════════════════════════════════════════════════════════════
# 10.1-10.2: 班级统计 + LLM 报告
# ═══════════════════════════════════════════════════════════════

STATS_PROMPT = """你是化学教学分析专家。基于以下班级考试数据，生成一份 300-500 字的分析报告。

考试数据：
- 参与人数：{participants}
- 平均分：{avg_score:.1f}
- 最高分：{max_score:.0f}
- 最低分：{min_score:.0f}
- 分数分布：{score_distribution}
- 逐题正确率：{question_accuracy}
- 薄弱知识点：{weak_points}

报告要求：
1. 整体表现分析（1-2 句）
2. 薄弱知识点诊断（2-3 个最关键问题）
3. 障碍类型分析（概念理解/审题偏差/表述不清）
4. 改进建议（2-3 条可操作建议）
5. 使用中文，面向教师，简洁专业"""


async def compute_exam_statistics(
    db: AsyncSession,
    exam_record_id: int,
) -> dict:
    """10.1: 计算班级考试统计。

    参与人数/平均分/分数分布/逐题错误率/障碍分布 → 写入 ExamRecord.error_stats + status→completed。
    """
    from sqlalchemy import select, func
    from ..models.teaching import ExamRecord, StudentAnswer
    from ..core.enums import BarrierType

    # 查询该考试下所有学生答案
    result = await db.execute(
        select(StudentAnswer).where(StudentAnswer.exam_record_id == exam_record_id)
    )
    answers = result.scalars().all()

    if not answers:
        return {"error": "该考试无学生作答数据"}

    # 按学生分组
    student_scores: dict[int, list] = {}
    for a in answers:
        student_scores.setdefault(a.student_id, []).append(a)

    participants = len(student_scores)

    # 分数统计
    scores = []
    for sid, ans_list in student_scores.items():
        correct = sum(1 for a in ans_list if a.is_correct)
        total = len(ans_list)
        score = (correct / total * 100) if total > 0 else 0
        scores.append(score)

    avg_score = sum(scores) / len(scores) if scores else 0
    max_score = max(scores) if scores else 0
    min_score = min(scores) if scores else 0

    # 分数分布（0-59, 60-69, 70-79, 80-89, 90-100）
    distribution = {"0-59": 0, "60-69": 0, "70-79": 0, "80-89": 0, "90-100": 0}
    for s in scores:
        if s < 60:
            distribution["0-59"] += 1
        elif s < 70:
            distribution["60-69"] += 1
        elif s < 80:
            distribution["70-79"] += 1
        elif s < 90:
            distribution["80-89"] += 1
        else:
            distribution["90-100"] += 1

    # 逐题错误率（按 question_id 聚合）
    question_stats: dict[int, dict] = {}
    for a in answers:
        if a.question_id not in question_stats:
            question_stats[a.question_id] = {"total": 0, "correct": 0, "errors": {}}
        qs = question_stats[a.question_id]
        qs["total"] += 1
        if a.is_correct:
            qs["correct"] += 1

    question_accuracy = {}
    for qid, qs in sorted(question_stats.items()):
        rate = (qs["correct"] / qs["total"] * 100) if qs["total"] > 0 else 0
        question_accuracy[str(qid)] = round(rate, 1)

    # 障碍分布
    barrier_dist: dict[str, int] = {}
    for a in answers:
        if a.barrier_type:
            key = a.barrier_type.value if hasattr(a.barrier_type, 'value') else str(a.barrier_type)
            barrier_dist[key] = barrier_dist.get(key, 0) + 1

    # 写入 ExamRecord
    exam_result = await db.execute(
        select(ExamRecord).where(ExamRecord.id == exam_record_id)
    )
    exam = exam_result.scalar_one_or_none()
    if exam:
        exam.error_stats = {
            "participants": participants,
            "avg_score": round(avg_score, 1),
            "max_score": round(max_score, 1),
            "min_score": round(min_score, 1),
            "score_distribution": distribution,
            "question_accuracy": question_accuracy,
            "barrier_distribution": barrier_dist,
        }
        exam.status = "completed" if hasattr(exam, 'status') else exam.status
        await db.commit()

    return {
        "participants": participants,
        "avg_score": round(avg_score, 1),
        "max_score": round(max_score, 1),
        "min_score": round(min_score, 1),
        "score_distribution": distribution,
        "question_accuracy": question_accuracy,
        "barrier_distribution": barrier_dist,
    }


async def generate_class_report(
    exam_record_id: int,
    stats: dict,
) -> str:
    """10.2: LLM 注入考试数据 → 生成 300-500 字中文分析报告。"""
    from ..llm.router import llm_chat

    weak_points = ", ".join(
        f"题{q}: {rate}%正确率"
        for q, rate in sorted(stats.get("question_accuracy", {}).items(), key=lambda x: x[1])
        if rate < 70
    ) or "无明显薄弱点"

    prompt = STATS_PROMPT.format(
        participants=stats.get("participants", 0),
        avg_score=stats.get("avg_score", 0),
        max_score=stats.get("max_score", 0),
        min_score=stats.get("min_score", 0),
        score_distribution=stats.get("score_distribution", {}),
        question_accuracy=stats.get("question_accuracy", {}),
        weak_points=weak_points,
    )

    try:
        report = await llm_chat(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.5,
            max_tokens=1000,
        )
        return report
    except Exception as e:
        logger.warning("[stats] LLM 报告生成失败: %s", e)
        # 生成 fallback 基本报告
        return (
            f"班级考试分析报告\n\n"
            f"参与人数：{stats.get('participants', 0)}\n"
            f"平均分：{stats.get('avg_score', 0)}\n"
            f"最高分：{stats.get('max_score', 0)}\n"
            f"最低分：{stats.get('min_score', 0)}\n"
            f"薄弱知识点：{weak_points}\n"
        )
