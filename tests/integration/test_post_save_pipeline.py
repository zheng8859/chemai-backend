"""8.7: 后保存管线集成测试 — 诊断→统计→报告 三步 Pipeline。

覆盖：
- _run_diagnosis: LLM 批量诊断错误作答 + 更新 StudentAnswer + 聚合学生画像
- compute_exam_statistics: 班级统计（参与人数/平均分/分数分布/逐题正确率/障碍分布）
- generate_class_report: LLM 生成分析报告
- _post_save_pipeline: 三步全流程（各步独立 try/catch）
"""

import pytest
from unittest.mock import AsyncMock, patch


MOCK_DIAGNOSIS_JSON = (
    '{"barrier_type":"concept","misconception_category":"redox",'
    '"reasoning":"学生混淆了氧化剂和还原剂的判断，属于概念理解偏差",'
    '"suggestion":"建议通过对比练习强化氧化还原基本概念"}'
)

MOCK_REPORT = "本次考试整体表现一般，平均分72.5。主要薄弱点在氧化还原反应和化学平衡。" \
              "建议加强概念辨析训练和化学方程式书写规范。"


# ═══════════════════════════════════════════════════════════════
# Step 1: _run_diagnosis 测试
# ═══════════════════════════════════════════════════════════════

class TestRunDiagnosis:

    @pytest.mark.anyio
    async def test_no_error_answers_returns_zero(self, db_session):
        """无错误作答 → 返回 0。"""
        from app.services.grading_service import GradingService

        diagnosed = await GradingService._run_diagnosis(db_session, exam_record_id=99999)
        assert diagnosed == 0

    @pytest.mark.anyio
    async def test_diagnoses_error_answers_with_mock_llm(self, db_session, make_student, make_question):
        """Mock LLM 返回 → StudentAnswer 被正确更新。"""
        from app.services.grading_service import GradingService
        from app.models.teaching import StudentAnswer, ExamRecord
        from app.core.enums import BarrierType, DiagnosisSource
        from datetime import datetime, timezone

        # 创建测试数据
        student = await make_student(name="诊断测试学生")
        question = await make_question(
            content="下列哪种物质是氧化剂？",
            answer="A",
            knowledge_point_tags=["氧化还原反应"],
        )

        exam = ExamRecord(
            class_id=student.class_id,
            exam_type="practice",
            exam_date=datetime.now(timezone.utc),
            status="grading",
        )
        db_session.add(exam)
        await db_session.flush()

        # 创建两个错误作答
        ans1 = StudentAnswer(
            question_id=question.id,
            student_id=student.id,
            exam_record_id=exam.id,
            answer_content="B",
            is_correct=False,
            barrier_type=BarrierType.concept,
        )
        ans2 = StudentAnswer(
            question_id=question.id,
            student_id=student.id,
            exam_record_id=exam.id,
            answer_content="D",
            is_correct=False,
            barrier_type=BarrierType.concept,
        )
        db_session.add_all([ans1, ans2])
        await db_session.commit()

        # Mock LLM 调用
        with patch(
            "app.llm.router.llm_chat",
            new_callable=AsyncMock,
        ) as mock_llm:
            mock_llm.return_value = MOCK_DIAGNOSIS_JSON

            diagnosed = await GradingService._run_diagnosis(db_session, exam_record_id=exam.id)

            # 验证 LLM 被调用
            assert mock_llm.call_count >= 2, f"Expected >=2 LLM calls, got {mock_llm.call_count}"
            assert diagnosed >= 2

        # 验证 StudentAnswer 已更新
        from sqlalchemy import select
        result = await db_session.execute(
            select(StudentAnswer).where(StudentAnswer.exam_record_id == exam.id)
        )
        updated_answers = result.scalars().all()
        for ans in updated_answers:
            assert ans.diagnosed_by == DiagnosisSource.ai_llm, \
                f"Expected ai_llm, got {ans.diagnosed_by}"
            assert ans.barrier_type is not None
            bt = ans.barrier_type.value if hasattr(ans.barrier_type, 'value') else str(ans.barrier_type)
            assert bt == "concept", f"Expected concept, got {bt}"
            assert ans.misconception_category is not None

    @pytest.mark.anyio
    async def test_skips_already_diagnosed_answers(self, db_session, make_student, make_question):
        """已诊断的答案 → 不重复诊断。"""
        from app.services.grading_service import GradingService
        from app.models.teaching import StudentAnswer, ExamRecord
        from app.core.enums import BarrierType, DiagnosisSource
        from datetime import datetime, timezone

        student = await make_student(name="已诊断学生")
        question = await make_question(content="氧化还原测试", answer="A")

        exam = ExamRecord(
            class_id=student.class_id,
            exam_type="practice",
            exam_date=datetime.now(timezone.utc),
            status="grading",
        )
        db_session.add(exam)
        await db_session.flush()

        # 一个已诊断、一个未诊断
        diagnosed_ans = StudentAnswer(
            question_id=question.id,
            student_id=student.id,
            exam_record_id=exam.id,
            answer_content="B",
            is_correct=False,
            barrier_type=BarrierType.concept,
            diagnosed_by=DiagnosisSource.ai_llm,
            misconception_category="redox",
        )
        undiagnosed_ans = StudentAnswer(
            question_id=question.id,
            student_id=student.id,
            exam_record_id=exam.id,
            answer_content="C",
            is_correct=False,
            barrier_type=BarrierType.concept,
            diagnosed_by=None,
        )
        db_session.add_all([diagnosed_ans, undiagnosed_ans])
        await db_session.commit()

        with patch(
            "app.llm.router.llm_chat",
            new_callable=AsyncMock,
        ) as mock_llm:
            mock_llm.return_value = MOCK_DIAGNOSIS_JSON

            diagnosed = await GradingService._run_diagnosis(db_session, exam_record_id=exam.id)

        # 只诊断了 1 条未诊断的（已诊断的跳过）
        assert diagnosed == 1

    @pytest.mark.anyio
    async def test_updates_barrier_profile(self, db_session, make_student, make_question):
        """诊断完成后 → 更新 Student.barrier_profile。"""
        from app.services.grading_service import GradingService
        from app.models.teaching import StudentAnswer, ExamRecord
        from app.models.user import Student
        from app.core.enums import BarrierType
        from datetime import datetime, timezone
        from sqlalchemy import select

        student = await make_student(name="画像测试学生")
        question = await make_question(
            content="概念测试题",
            answer="A",
            knowledge_point_tags=["化学平衡"],
        )

        exam = ExamRecord(
            class_id=student.class_id,
            exam_type="practice",
            exam_date=datetime.now(timezone.utc),
            status="grading",
        )
        db_session.add(exam)
        await db_session.flush()

        # 创建多条错误作答
        for answer_content in ["B", "C", "D"]:
            ans = StudentAnswer(
                question_id=question.id,
                student_id=student.id,
                exam_record_id=exam.id,
                answer_content=answer_content,
                is_correct=False,
                barrier_type=BarrierType.concept,
            )
            db_session.add(ans)
        await db_session.commit()

        with patch(
            "app.llm.router.llm_chat",
            new_callable=AsyncMock,
        ) as mock_llm:
            mock_llm.return_value = MOCK_DIAGNOSIS_JSON

            await GradingService._run_diagnosis(db_session, exam_record_id=exam.id)

        # 验证学生画像已更新
        s_result = await db_session.execute(
            select(Student).where(Student.id == student.id)
        )
        updated_student = s_result.scalar_one()
        assert updated_student.barrier_profile is not None
        bp = updated_student.barrier_profile
        # 三条 concept → concept_ratio = 1.0
        assert bp["concept"] == 1.0
        assert bp["reading"] == 0.0
        assert bp["expression"] == 0.0


# ═══════════════════════════════════════════════════════════════
# Step 2: compute_exam_statistics 测试
# ═══════════════════════════════════════════════════════════════

class TestComputeExamStatistics:

    @pytest.mark.anyio
    async def test_empty_exam_returns_error(self, db_session):
        """无作答数据 → 返回 error。"""
        from app.services.grading_service import compute_exam_statistics

        stats = await compute_exam_statistics(db_session, exam_record_id=99999)
        assert "error" in stats

    @pytest.mark.anyio
    async def test_computes_basic_stats(self, db_session, make_student, make_question):
        """有作答数据 → 正确计算统计。"""
        from app.services.grading_service import compute_exam_statistics
        from app.models.teaching import StudentAnswer, ExamRecord
        from app.core.enums import BarrierType
        from datetime import datetime, timezone

        student = await make_student(name="统计测试学生")
        question = await make_question(content="统计测试题", answer="A")

        exam = ExamRecord(
            class_id=student.class_id,
            exam_type="practice",
            exam_date=datetime.now(timezone.utc),
            status="grading",
        )
        db_session.add(exam)
        await db_session.flush()

        # 一个正确、一个错误
        ans1 = StudentAnswer(
            question_id=question.id,
            student_id=student.id,
            exam_record_id=exam.id,
            answer_content="A",
            is_correct=True,
        )
        ans2 = StudentAnswer(
            question_id=question.id,
            student_id=student.id,
            exam_record_id=exam.id,
            answer_content="B",
            is_correct=False,
            barrier_type=BarrierType.concept,
        )
        db_session.add_all([ans1, ans2])
        await db_session.commit()

        stats = await compute_exam_statistics(db_session, exam_record_id=exam.id)

        assert "error" not in stats
        assert stats["participants"] == 1
        assert stats["avg_score"] == 50.0  # 2 题中 1 正确 = 50%
        assert stats["max_score"] == 50.0
        assert stats["min_score"] == 50.0
        assert "score_distribution" in stats
        assert "question_accuracy" in stats
        assert "barrier_distribution" in stats
        # 1 条 concept 障碍
        assert stats["barrier_distribution"].get("concept", 0) == 1

    @pytest.mark.anyio
    async def test_computes_multi_student_stats(self, db_session, make_student, make_question):
        """多学生 → 分开计算。"""
        from app.services.grading_service import compute_exam_statistics
        from app.models.teaching import StudentAnswer, ExamRecord
        from datetime import datetime, timezone

        s1 = await make_student(name="学生甲", student_id="S000001")
        s2 = await make_student(name="学生乙", student_id="S000002")
        # 确保两个学生在同一班级
        q1 = await make_question(content="题1", answer="A")
        q2 = await make_question(content="题2", answer="B")

        exam = ExamRecord(
            class_id=s1.class_id,
            exam_type="practice",
            exam_date=datetime.now(timezone.utc),
            status="grading",
        )
        db_session.add(exam)
        await db_session.flush()

        # 学生甲：全对
        db_session.add(StudentAnswer(question_id=q1.id, student_id=s1.id, exam_record_id=exam.id, answer_content="A", is_correct=True))
        db_session.add(StudentAnswer(question_id=q2.id, student_id=s1.id, exam_record_id=exam.id, answer_content="B", is_correct=True))
        # 学生乙：全错
        db_session.add(StudentAnswer(question_id=q1.id, student_id=s2.id, exam_record_id=exam.id, answer_content="C", is_correct=False))
        db_session.add(StudentAnswer(question_id=q2.id, student_id=s2.id, exam_record_id=exam.id, answer_content="D", is_correct=False))
        await db_session.commit()

        stats = await compute_exam_statistics(db_session, exam_record_id=exam.id)

        assert stats["participants"] == 2
        assert stats["avg_score"] == 50.0  # (100+0)/2
        assert stats["max_score"] == 100.0
        assert stats["min_score"] == 0.0


# ═══════════════════════════════════════════════════════════════
# Step 3: generate_class_report 测试
# ═══════════════════════════════════════════════════════════════

class TestGenerateClassReport:

    @pytest.mark.anyio
    async def test_generates_report_with_mock_llm(self):
        """Mock LLM → 返回报告文本。"""
        from app.services.grading_service import generate_class_report

        stats = {
            "participants": 30,
            "avg_score": 72.5,
            "max_score": 98.0,
            "min_score": 35.0,
            "score_distribution": {"0-59": 5, "60-69": 8, "70-79": 10, "80-89": 5, "90-100": 2},
            "question_accuracy": {"1": 80.0, "2": 65.0, "3": 45.0},
            "barrier_distribution": {"concept": 12, "reading": 8, "expression": 5},
        }

        with patch(
            "app.llm.router.llm_chat",
            new_callable=AsyncMock,
        ) as mock_llm:
            mock_llm.return_value = MOCK_REPORT

            report = await generate_class_report(1, stats)

            assert mock_llm.call_count == 1
            assert isinstance(report, str)
            assert len(report) > 20
            assert "氧化" in report


# ═══════════════════════════════════════════════════════════════
# Full Pipeline: _post_save_pipeline 测试
# ═══════════════════════════════════════════════════════════════

class TestPostSavePipeline:

    @pytest.mark.anyio
    async def test_saved_count_zero_returns_early(self):
        """saved_count=0 → 直接返回空结果。"""
        from app.services.grading_service import GradingService

        result = await GradingService._post_save_pipeline(saved_count=0)
        assert result["diagnosis"] == 0
        assert result["stats"] is None
        assert result["report"] is None

    @pytest.mark.anyio
    async def test_full_pipeline_with_mock_llm(self, db_session, make_student, make_question):
        """完整管线：诊断→统计→报告，Mock LLM。"""
        from app.services.grading_service import GradingService
        from app.models.teaching import StudentAnswer, ExamRecord
        from app.core.enums import BarrierType, DiagnosisSource
        from datetime import datetime, timezone

        student = await make_student(name="管线测试学生")
        question = await make_question(
            content="全管线测试题",
            answer="A",
            knowledge_point_tags=["氧化还原反应"],
        )

        exam = ExamRecord(
            class_id=student.class_id,
            exam_type="practice",
            exam_date=datetime.now(timezone.utc),
            status="grading",
        )
        db_session.add(exam)
        await db_session.flush()

        # 创建错误作答
        ans = StudentAnswer(
            question_id=question.id,
            student_id=student.id,
            exam_record_id=exam.id,
            answer_content="B",
            is_correct=False,
            barrier_type=BarrierType.concept,
        )
        db_session.add(ans)
        await db_session.commit()

        with patch(
            "app.llm.router.llm_chat",
            new_callable=AsyncMock,
        ) as mock_llm:
            mock_llm.return_value = MOCK_DIAGNOSIS_JSON

            result = await GradingService._post_save_pipeline(
                saved_count=1,
                exam_record_id=exam.id,
                _db=db_session,
            )

            # 验证各步骤产出
            assert result["diagnosis"] >= 1, f"Expected >=1 diagnoses, got {result['diagnosis']}"
            assert result["stats"] is not None, "Stats should not be None"
            assert "error" not in result["stats"], f"Stats error: {result['stats'].get('error')}"

        # 验证诊断结果已落地
        from sqlalchemy import select
        ans_result = await db_session.execute(
            select(StudentAnswer).where(StudentAnswer.exam_record_id == exam.id)
        )
        updated = ans_result.scalars().all()
        for a in updated:
            assert a.diagnosed_by == DiagnosisSource.ai_llm

    @pytest.mark.anyio
    async def test_pipeline_each_step_independent(self, db_session):
        """各步独立 try/catch：诊断失败不影响统计和报告。"""
        from app.services.grading_service import GradingService

        # exam_record_id 不存在 → 诊断和统计返回空/error，但不应崩溃
        with patch(
            "app.services.grading_service.GradingService._run_diagnosis",
            side_effect=RuntimeError("模拟诊断崩溃"),
        ):
            result = await GradingService._post_save_pipeline(
                saved_count=1,
                exam_record_id=99999,
                _db=db_session,
            )

        # 诊断失败 → diagnosis=0（初始值）
        assert result["diagnosis"] == 0
        # 统计应返回正常结果（有 db_session，只是没有数据）
        assert result["stats"] is not None
        # 报告应跳过（无有效统计 或 error）
        assert result["report"] is None
