"""记忆 Agent 工具单元测试 — memory_student_get / memory_teacher_get + Store 读取。

覆盖 tasks 1.1–1.5：
- memory_student_get 读取诊断历史（最近 5 条）+ 学习计划 + 无数据兜底
- memory_teacher_get 无偏好返回默认值 / 有偏好返回真实值
- store.read_teacher_preference 读取教师偏好
"""

import pytest

# ── 触发所有 @register_tool 装饰器 ──
import agent.tools  # noqa: F401
import agent.tools.memory_tools as mt


@pytest.fixture
def fake_session(db_session, monkeypatch, fake_main_session_cls):
    """让工具走测试 db_session，而非生产 main_engine。"""
    monkeypatch.setattr(mt, "MainSession", fake_main_session_cls(db_session))
    return db_session


# ═══════════════════════════════════════════════════════════════
# memory_student_get — 诊断历史 + 学习计划
# ═══════════════════════════════════════════════════════════════

class TestMemoryStudentGet:

    @pytest.mark.anyio
    async def test_reads_diagnosis_history_limited_to_5(self, fake_session, make_student):
        """读取最近 5 条诊断历史，映射 barrier_type/distribution/timestamp。

        diagnosis_history 截断为 5 条，但 diagnosis_count 为全部记录数（6）。
        """
        from app.agent.store import write_diagnosis_snapshot

        student = await make_student()
        for i in range(6):
            await write_diagnosis_snapshot(
                fake_session, student.id,
                profile={"concept": 0.1 * i}, dominant_barrier="concept",
            )

        result = await mt.memory_student_get(student.id)
        assert result["student_id"] == student.id
        assert result["diagnosis_count"] == 6
        assert len(result["diagnosis_history"]) == 5
        item = result["diagnosis_history"][0]
        assert item["barrier_type"] == "concept"
        assert "concept" in item["distribution"]
        assert item["timestamp"] is not None

    @pytest.mark.anyio
    async def test_reads_learning_plan(self, fake_session, make_student):
        """读取最新学习计划摘要。"""
        from app.agent.store import write_learning_plan_summary

        student = await make_student()
        await write_learning_plan_summary(
            fake_session, student.id, plan_id=7, title="氧还复习计划", task_count=3,
        )

        result = await mt.memory_student_get(student.id)
        assert result["active_learning_plan"] is not None
        assert result["active_learning_plan"]["title"] == "氧还复习计划"

    @pytest.mark.anyio
    async def test_no_data_returns_empty(self, fake_session):
        """无记忆数据时返回空列表 / None / 0，不抛异常。"""
        result = await mt.memory_student_get(99999)
        assert result["student_id"] == 99999
        assert result["diagnosis_history"] == []
        assert result["active_learning_plan"] is None
        assert result["diagnosis_count"] == 0


# ═══════════════════════════════════════════════════════════════
# memory_teacher_get — 教师偏好读取
# ═══════════════════════════════════════════════════════════════

class TestMemoryTeacherGet:

    @pytest.mark.anyio
    async def test_no_preference_returns_default(self, fake_session):
        """无偏好记录时返回默认值。"""
        result = await mt.memory_teacher_get(99999)
        assert result["teacher_id"] == 99999
        assert result["teaching_style"] == "balanced"
        assert result["difficulty_preference"] == "auto"
        assert result["class_configuration"] == {}

    @pytest.mark.anyio
    async def test_reads_stored_preference(self, fake_session):
        """存在偏好记录时返回真实值。"""
        from app.models.agent_memory import LongTermMemory
        from app.core.enums import MemoryType

        fake_session.add(LongTermMemory(
            teacher_id=42,
            memory_type=MemoryType.teacher_preference,
            content={
                "teaching_style": "strict",
                "difficulty_preference": "hard",
                "class_configuration": {"grade": "高二", "size": 45},
            },
        ))
        await fake_session.commit()

        result = await mt.memory_teacher_get(42)
        assert result["teacher_id"] == 42
        assert result["teaching_style"] == "strict"
        assert result["difficulty_preference"] == "hard"
        assert result["class_configuration"]["grade"] == "高二"


# ═══════════════════════════════════════════════════════════════
# store.read_teacher_preference — 底层读取
# ═══════════════════════════════════════════════════════════════

class TestReadTeacherPreference:

    @pytest.mark.anyio
    async def test_returns_none_when_missing(self, db_session):
        """无记录返回 None。"""
        from app.agent.store import read_teacher_preference
        assert await read_teacher_preference(db_session, 1) is None

    @pytest.mark.anyio
    async def test_returns_latest_preference(self, db_session):
        """返回最新一条偏好。"""
        from app.agent.store import read_teacher_preference
        from app.models.agent_memory import LongTermMemory
        from app.core.enums import MemoryType

        db_session.add(LongTermMemory(
            teacher_id=7,
            memory_type=MemoryType.teacher_preference,
            content={"teaching_style": "old"},
        ))
        db_session.add(LongTermMemory(
            teacher_id=7,
            memory_type=MemoryType.teacher_preference,
            content={"teaching_style": "new"},
        ))
        await db_session.commit()

        pref = await read_teacher_preference(db_session, 7)
        assert pref is not None
        assert pref["teaching_style"] == "new"
