"""DiagnosisService 服务层测试 — 障碍配置/知识点/教师覆盖/预警/stub。

直接调用 DiagnosisService 静态方法，使用 db_session fixture。
LLM 依赖的方法（run_llm_diagnosis）需要 mock，不在本文件覆盖。
"""

import pytest
from datetime import datetime, timezone

from sqlalchemy import select

from app.services.diagnosis_service import DiagnosisService, DiagnosisError
from app.models.diagnosis import BarrierConfig, KnowledgePoint, WarningLog
from app.models.teaching import Question, StudentAnswer
from app.models.user import Student
from app.core.enums import BarrierType, MisconceptionCategory, DiagnosisSource, WarningType, WarningSeverity


# ═══════════════════════════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════════════════════════

async def _create_question(db, **overrides):
    """创建测试题目。"""
    defaults = {
        "content": "测试题目",
        "question_type": "choice",
        "options": ["A", "B", "C", "D"],
        "answer": "B",
        "difficulty": "medium",
        "knowledge_point_tags": ["氧化还原"],
    }
    defaults.update(overrides)
    q = Question(**defaults)
    db.add(q)
    await db.commit()
    await db.refresh(q)
    return q


async def _create_student(db, **overrides):
    """创建测试学生。"""
    defaults = {
        "id": 1,
        "account_id": 1,
        "class_id": 1,
        "school_id": 1,
        "name": "测试学生",
        "student_id": "S20001",
        "status": "approved",
    }
    defaults.update(overrides)
    s = Student(**defaults)
    db.add(s)
    await db.commit()
    await db.refresh(s)
    return s


async def _create_student_answer(db, **overrides):
    """创建测试学生作答（含诊断信息）。"""
    defaults = {
        "student_id": 1,
        "question_id": 1,
        "answer_content": "A",
        "is_correct": False,
        "barrier_type": BarrierType.concept,
        "misconception_category": MisconceptionCategory.redox,
        "diagnosed_by": DiagnosisSource.ai_rule,
    }
    defaults.update(overrides)
    sa = StudentAnswer(**defaults)
    db.add(sa)
    await db.commit()
    await db.refresh(sa)
    return sa


# ═══════════════════════════════════════════════════════════════
# Barrier Config
# ═══════════════════════════════════════════════════════════════

class TestBarrierConfigGet:
    """GET barrier config → get_barrier_config。"""

    @pytest.mark.anyio
    async def test_auto_create_default(self, db_session):
        """无配置时自动创建默认配置。"""
        result = await DiagnosisService.get_barrier_config(db_session, teacher_id=1)

        assert result.teacher_id == 1
        assert result.concept_threshold == 3  # 默认值
        assert result.auto_sync_enabled is False

    @pytest.mark.anyio
    async def test_return_existing(self, db_session):
        """已有配置时返回已有（不重复创建）。"""
        bc = BarrierConfig(teacher_id=1, concept_threshold=5)
        db_session.add(bc)
        await db_session.commit()

        result = await DiagnosisService.get_barrier_config(db_session, teacher_id=1)
        assert result.concept_threshold == 5


class TestBarrierConfigUpdate:
    """PATCH barrier config → update_barrier_config。"""

    @pytest.mark.anyio
    async def test_update_existing(self, db_session):
        """更新已有配置。"""
        bc = BarrierConfig(teacher_id=1)
        db_session.add(bc)
        await db_session.commit()

        from app.schemas.diagnosis import BarrierConfigUpdate
        result = await DiagnosisService.update_barrier_config(
            db_session, teacher_id=1,
            data=BarrierConfigUpdate(concept_threshold=10, auto_sync_enabled=True),
        )

        assert result.concept_threshold == 10
        assert result.auto_sync_enabled is True

    @pytest.mark.anyio
    async def test_update_auto_creates_when_missing(self, db_session):
        """无配置时自动创建再更新。"""
        from app.schemas.diagnosis import BarrierConfigUpdate
        result = await DiagnosisService.update_barrier_config(
            db_session, teacher_id=1,
            data=BarrierConfigUpdate(concept_threshold=7),
        )

        assert result.concept_threshold == 7
        assert result.teacher_id == 1


# ═══════════════════════════════════════════════════════════════
# Knowledge Points
# ═══════════════════════════════════════════════════════════════

class TestListKnowledgePoints:
    """GET knowledge points → list_knowledge_points。"""

    @pytest.mark.anyio
    async def test_empty(self, db_session):
        """无知识点时返回空列表。"""
        items, total = await DiagnosisService.list_knowledge_points(db_session)
        assert total == 0
        assert items == []

    @pytest.mark.anyio
    async def test_with_data(self, db_session):
        """有知识点时分页返回。"""
        db_session.add(KnowledgePoint(name="氧化还原反应", category="电化学"))
        db_session.add(KnowledgePoint(name="离子方程式", category="电解质溶液"))
        await db_session.commit()

        items, total = await DiagnosisService.list_knowledge_points(db_session)
        assert total == 2
        assert len(items) == 2

    @pytest.mark.anyio
    async def test_filter_by_category(self, db_session):
        """按类别过滤。"""
        db_session.add(KnowledgePoint(name="氧化还原反应", category="电化学"))
        db_session.add(KnowledgePoint(name="物质的量", category="计量"))
        await db_session.commit()

        items, total = await DiagnosisService.list_knowledge_points(
            db_session, category="电化学",
        )
        assert total == 1
        assert items[0].name == "氧化还原反应"


class TestSearchKnowledgePoints:
    """GET knowledge points/search → search_knowledge_points。"""

    @pytest.mark.anyio
    async def test_no_match(self, db_session):
        """无匹配时返回空。"""
        result = await DiagnosisService.search_knowledge_points(db_session, "不存在的")
        assert result == []

    @pytest.mark.anyio
    async def test_by_name(self, db_session):
        """按名称搜索。"""
        db_session.add(KnowledgePoint(name="氧化还原反应"))
        db_session.add(KnowledgePoint(name="离子方程式"))
        await db_session.commit()

        result = await DiagnosisService.search_knowledge_points(db_session, "氧化")
        assert len(result) == 1
        assert result[0].name == "氧化还原反应"

    @pytest.mark.anyio
    async def test_by_category(self, db_session):
        """按类别搜索。"""
        db_session.add(KnowledgePoint(name="知识点A", category="电化学"))
        db_session.add(KnowledgePoint(name="知识点B", category="计量"))
        await db_session.commit()

        result = await DiagnosisService.search_knowledge_points(db_session, "电化学")
        assert len(result) == 1
        assert result[0].name == "知识点A"


# ═══════════════════════════════════════════════════════════════
# Override Diagnosis
# ═══════════════════════════════════════════════════════════════

class TestOverrideDiagnosis:
    """POST 教师覆盖诊断 → override_diagnosis。"""

    @pytest.mark.anyio
    async def test_nonexistent_answer_raises(self, db_session):
        """作答不存在 → DiagnosisError。"""
        with pytest.raises(DiagnosisError, match="作答记录不存在"):
            await DiagnosisService.override_diagnosis(
                db_session, student_answer_id=99999,
                barrier_type="reading",
            )

    @pytest.mark.anyio
    async def test_override_success(self, db_session):
        """教师覆盖诊断成功。"""
        q = await _create_question(db_session)
        sa = await _create_student_answer(db_session, question_id=q.id)

        result = await DiagnosisService.override_diagnosis(
            db_session, student_answer_id=sa.id,
            barrier_type="reading",
            misconception_category="chemical_notation",
        )

        assert result["old"]["barrier_type"] == "concept"
        assert result["new"]["barrier_type"] == "reading"
        assert result["new"]["misconception_category"] == "chemical_notation"
        assert result["new"]["diagnosed_by"] == "teacher"

        await db_session.refresh(sa)
        assert sa.diagnosed_by == DiagnosisSource.teacher
        assert sa.diagnosis_overridden_at is not None

    @pytest.mark.anyio
    async def test_override_without_misconception(self, db_session):
        """覆盖时不提供 misconception_category → 清空为 None。"""
        q = await _create_question(db_session)
        sa = await _create_student_answer(
            db_session, question_id=q.id,
            barrier_type=BarrierType.concept,
            misconception_category=MisconceptionCategory.redox,
        )

        result = await DiagnosisService.override_diagnosis(
            db_session, student_answer_id=sa.id,
            barrier_type="expression",
            # 不传 misconception_category
        )

        assert result["new"]["misconception_category"] is None


# ═══════════════════════════════════════════════════════════════
# Warnings
# ═══════════════════════════════════════════════════════════════

class TestListWarnings:
    """GET warnings → list_warnings。"""

    @pytest.mark.anyio
    async def test_empty(self, db_session):
        """无预警时返回空。"""
        items, total = await DiagnosisService.list_warnings(db_session)
        assert total == 0
        assert items == []

    @pytest.mark.anyio
    async def test_with_data(self, db_session):
        """有预警时分页返回。"""
        for i in range(2):
            db_session.add(WarningLog(
                student_id=1,
                warning_type=WarningType.score_drop,
                severity=WarningSeverity.warning,
                message=f"测试预警{i}",
            ))
        await db_session.commit()

        items, total = await DiagnosisService.list_warnings(db_session)
        assert total == 2
        assert len(items) == 2

    @pytest.mark.anyio
    async def test_filter_by_severity(self, db_session):
        """按严重级别过滤。"""
        db_session.add(WarningLog(
            student_id=1, warning_type=WarningType.score_drop,
            severity=WarningSeverity.severe, message="严重预警",
        ))
        db_session.add(WarningLog(
            student_id=1, warning_type=WarningType.high_error_rate,
            severity=WarningSeverity.info, message="普通提示",
        ))
        await db_session.commit()

        items, total = await DiagnosisService.list_warnings(
            db_session, severity="severe",
        )
        assert total == 1
        assert items[0].severity == "severe"


class TestResolveWarning:
    """POST warnings/{id}/resolve → resolve_warning。"""

    @pytest.mark.anyio
    async def test_nonexistent_raises(self, db_session):
        """不存在的预警 → DiagnosisError。"""
        with pytest.raises(DiagnosisError, match="预警不存在"):
            await DiagnosisService.resolve_warning(db_session, 99999)

    @pytest.mark.anyio
    async def test_resolve_success(self, db_session):
        """解决预警成功（三端标记为已通知）。"""
        w = WarningLog(
            student_id=1, warning_type=WarningType.score_drop,
            severity=WarningSeverity.warning, message="测试预警",
            notified_teacher=False, notified_parent=False, notified_student=False,
        )
        db_session.add(w)
        await db_session.commit()
        wid = w.id

        result = await DiagnosisService.resolve_warning(db_session, wid)
        assert result.notified_teacher is True
        assert result.notified_parent is True
        assert result.notified_student is True


# ═══════════════════════════════════════════════════════════════
# Practice Assign (stub)
# ═══════════════════════════════════════════════════════════════

class TestAssignPracticeStub:
    """POST assign practice → assign_practice_stub（stub）。"""

    @pytest.mark.anyio
    async def test_returns_uuid(self):
        """Stub 返回标准格式。"""
        result = await DiagnosisService.assign_practice_stub(
            student_id=1, question_count=10,
        )

        assert result["success"] is True
        assert "practice_session_id" in result
        assert result["estimated_time_minutes"] == 30  # 10 * 3
