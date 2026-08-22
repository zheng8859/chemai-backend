"""诊断与学生 Agent 工具组单元测试 — 7 个工具 + 两级诊断 + LLM 周报。

覆盖 tasks 1.1–1.6：
- resolve_student_by_identity（数字 ID / 姓名精确 / 子串 / 多候选 / 无命中）
- diagnose_barrier 两级诊断（个体 + 班级 + 多候选 + 无标识符）
- assign_adaptive_practice 班级级批处理（5 人/批 + 单生兜底 + 审批元数据）
- weekly_report LLM 周报（生成 / 无数据 / 降级）
- generate_learning_plan 预览路由（_route 不写库）
- show_students 障碍过滤透传
- 工具元数据（persona / call_limit / 审批 / 前置条件）
"""

from types import SimpleNamespace

import pytest

# ── 触发所有 @register_tool 装饰器 ──
import agent.tools  # noqa: F401
import agent.tools.diagnosis_tools as dt
from app.services.diagnosis_service import DiagnosisService


class _FakeMainSession:
    """把 diagnosis_tools.MainSession 替换为返回固定测试 session 的伪工厂。"""

    def __init__(self, session):
        self._session = session

    def __call__(self):
        return self

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, exc_type, exc, tb):
        return False


@pytest.fixture
def fake_session(db_session, monkeypatch):
    """让工具走测试 db_session，而非生产 main_engine。"""
    monkeypatch.setattr(dt, "MainSession", _FakeMainSession(db_session))
    return db_session


def _fake_diag(dominant_type="concept"):
    """构造一个最小 StudentDiagnosisResponse 替身（只暴露 model_dump）。"""
    return SimpleNamespace(model_dump=lambda: {
        "barrier_profile": {"concept": {"ratio": 0.6, "trend": "up"}},
        "dominant_type": dominant_type,
        "weak_kps": [{"knowledge_point": "氧化还原反应", "error_rate": 0.4}],
        "last_diagnosis_date": "2026-08-13",
    })


# ═══════════════════════════════════════════════════════════════
# resolve_student_by_identity — 名称/ID 解析
# ═══════════════════════════════════════════════════════════════

class TestResolveStudentByIdentity:
    @pytest.mark.anyio
    async def test_numeric_id(self, fake_session, make_student):
        s = await make_student(name="张三")
        result = await DiagnosisService.resolve_student_by_identity(fake_session, str(s.id))
        assert len(result) == 1
        assert result[0].id == s.id

    @pytest.mark.anyio
    async def test_numeric_id_not_found(self, fake_session):
        result = await DiagnosisService.resolve_student_by_identity(fake_session, "99999")
        assert result == []

    @pytest.mark.anyio
    async def test_name_exact_preferred_over_substring(self, fake_session, make_student):
        await make_student(name="李四四")
        await make_student(name="李四")
        result = await DiagnosisService.resolve_student_by_identity(fake_session, "李四")
        assert len(result) == 1
        assert result[0].name == "李四"

    @pytest.mark.anyio
    async def test_name_substring_multiple_sorted_by_class(self, fake_session, make_student):
        await make_student(name="王大明", class_id=2)
        await make_student(name="王小明", class_id=1)
        result = await DiagnosisService.resolve_student_by_identity(fake_session, "王")
        assert len(result) == 2
        assert [r.class_id for r in result] == [1, 2]

    @pytest.mark.anyio
    async def test_no_match(self, fake_session):
        result = await DiagnosisService.resolve_student_by_identity(fake_session, "不存在的学生")
        assert result == []

    @pytest.mark.anyio
    async def test_empty_input_returns_empty(self, fake_session):
        result = await DiagnosisService.resolve_student_by_identity(fake_session, "  ")
        assert result == []


# ═══════════════════════════════════════════════════════════════
# diagnose_barrier — 两级诊断与名称解析
# ═══════════════════════════════════════════════════════════════

class TestDiagnoseBarrier:
    @pytest.mark.anyio
    async def test_individual_by_numeric_id(self, fake_session, monkeypatch):
        async def fake_get_student(db, student_id):
            return _fake_diag()
        monkeypatch.setattr(dt.DiagnosisService, "get_student_diagnosis", fake_get_student)

        result = await dt.diagnose_barrier(student_id=1)
        assert result["scope"] == "student"
        assert result["student_id"] == 1
        assert result["dominant_type"] == "concept"
        assert result["barrier_profile"]["concept"]["ratio"] == 0.6
        assert result["last_diagnosis_date"] == "2026-08-13"

    @pytest.mark.anyio
    async def test_numeric_id_not_found_returns_error(self, fake_session):
        result = await dt.diagnose_barrier(student_id=99999)
        assert result["scope"] == "error"

    @pytest.mark.anyio
    async def test_name_unique_resolves_and_diagnoses(self, fake_session, make_student, monkeypatch):
        await make_student(name="李雷")
        async def fake_get_student(db, student_id):
            return _fake_diag("reading")
        monkeypatch.setattr(dt.DiagnosisService, "get_student_diagnosis", fake_get_student)

        result = await dt.diagnose_barrier(student_name="李雷")
        assert result["scope"] == "student"
        assert result["dominant_type"] == "reading"

    @pytest.mark.anyio
    async def test_name_ambiguous_returns_candidates(self, fake_session, make_student):
        await make_student(name="张伟", class_id=1)
        await make_student(name="张伟", class_id=2)

        result = await dt.diagnose_barrier(student_name="张伟")
        assert result["scope"] == "ambiguous"
        assert len(result["candidates"]) == 2
        assert {c["name"] for c in result["candidates"]} == {"张伟"}
        assert all("student_id" in c and "class_id" in c for c in result["candidates"])

    @pytest.mark.anyio
    async def test_class_level(self, fake_session, monkeypatch):
        async def fake_get_barriers(db, class_id):
            return [
                {"barrier_type": "concept", "count": 12, "percentage": 60.0},
                {"barrier_type": "reading", "count": 8, "percentage": 40.0},
            ]
        monkeypatch.setattr(dt.PanelService, "get_barriers", fake_get_barriers)

        result = await dt.diagnose_barrier(class_id=5)
        assert result["scope"] == "class"
        assert result["class_id"] == 5
        assert result["barrier_distribution"][0]["barrier_type"] == "concept"

    @pytest.mark.anyio
    async def test_no_identifier_returns_error(self, fake_session):
        result = await dt.diagnose_barrier()
        assert result["scope"] == "error"

    @pytest.mark.anyio
    async def test_name_not_found_returns_error(self, fake_session):
        result = await dt.diagnose_barrier(student_name="不存在")
        assert result["scope"] == "error"
        assert "不存在" in result["message"]


# ═══════════════════════════════════════════════════════════════
# show_diagnosis — 诊断面板路由
# ═══════════════════════════════════════════════════════════════

class TestShowDiagnosis:
    @pytest.mark.anyio
    async def test_opens_diagnosis_panel(self, fake_session, monkeypatch):
        async def fake_overview(db, class_id):
            return {"class_id": class_id, "avg_score": 82.5}
        monkeypatch.setattr(dt.PanelService, "get_class_overview", fake_overview)

        result = await dt.show_diagnosis(class_id=5)
        assert result["_component"]["type"] == "diagnosis"
        assert result["_component"]["action"] == "open"
        assert result["_component"]["data"]["class_id"] == 5
        assert result["message"] == "诊断面板已打开。"


# ═══════════════════════════════════════════════════════════════
# assign_adaptive_practice — 班级级批处理 + 单生兜底
# ═══════════════════════════════════════════════════════════════

class TestAssignAdaptivePractice:
    @staticmethod
    def _practice_result(student_id, question_count):
        return {
            "practice_id": f"PR-{student_id}",
            "title": "自适应练习",
            "question_count": question_count,
            "questions": [],
            "zpd_difficulty": "medium",
            "dominant_barrier": "concept",
            "target_kps": ["氧化还原反应"],
        }

    @pytest.mark.anyio
    async def test_class_batch(self, fake_session, make_student, monkeypatch):
        s1 = await make_student(name="甲")
        cid = s1.class_id
        for i in range(6):
            await make_student(name=f"乙{i}", class_id=cid)

        calls = []
        async def fake_create_practice(db, student_id, question_count=10, kp_override=None):
            calls.append(student_id)
            return self._practice_result(student_id, question_count)
        monkeypatch.setattr(dt.AdaptivePracticeService, "create_practice", fake_create_practice)

        result = await dt.assign_adaptive_practice(class_id=cid, count=3)
        assert result["scope"] == "class"
        assert result["total_students"] == 7
        assert len(result["practices"]) == 7
        assert len(calls) == 7
        assert result["practices"][0]["question_count"] == 3
        assert result["practices"][0]["practice_id"] == f"PR-{calls[0]}"

    @pytest.mark.anyio
    async def test_single_student_fallback(self, fake_session, monkeypatch):
        async def fake_create_practice(db, student_id, question_count=10, kp_override=None):
            return self._practice_result(student_id, question_count)
        monkeypatch.setattr(dt.AdaptivePracticeService, "create_practice", fake_create_practice)

        result = await dt.assign_adaptive_practice(
            student_id=9, knowledge_point="离子反应", count=4,
        )
        assert result["scope"] == "single"
        assert result["total_students"] == 1
        assert result["practices"][0]["practice_id"] == "PR-9"

    @pytest.mark.anyio
    async def test_class_name_resolves_fullwidth_parens(self, fake_session, make_student, monkeypatch):
        # 库中班级名为半角括号「高一(1)班」，用户输入全角「高一（1）班」应能命中
        s = await make_student(name="甲", class_name="高一(1)班")
        cid = s.class_id

        calls = []
        async def fake_create_practice(db, student_id, question_count=10, kp_override=None):
            calls.append(student_id)
            return self._practice_result(student_id, question_count)
        monkeypatch.setattr(dt.AdaptivePracticeService, "create_practice", fake_create_practice)

        result = await dt.assign_adaptive_practice(class_name="高一（1）班", count=3)
        assert result["scope"] == "class"
        assert result["class_id"] == cid
        assert len(calls) == 1
        assert calls[0] == s.id

    @pytest.mark.anyio
    async def test_class_name_not_found_returns_error(self, fake_session):
        result = await dt.assign_adaptive_practice(class_name="高二（9）班")
        assert result["scope"] == "error"
        assert "未找到班级" in result["message"]

    @pytest.mark.anyio
    async def test_no_identifier_returns_error(self, fake_session):
        result = await dt.assign_adaptive_practice()
        assert result["scope"] == "error"

    @pytest.mark.anyio
    async def test_create_practice_error_appended(self, fake_session, make_student, monkeypatch):
        s1 = await make_student(name="甲")
        cid = s1.class_id
        await make_student(name="乙", class_id=cid)

        async def fake_create_practice(db, student_id, question_count=10, kp_override=None):
            raise dt.AdaptivePracticeError("题库为空")

        monkeypatch.setattr(dt.AdaptivePracticeService, "create_practice", fake_create_practice)

        result = await dt.assign_adaptive_practice(class_id=cid, count=3)
        assert result["scope"] == "class"
        assert result["total_students"] == 2
        assert all(p.get("error") == "题库为空" for p in result["practices"])


# ═══════════════════════════════════════════════════════════════
# weekly_report — LLM 自然语言周报
# ═══════════════════════════════════════════════════════════════

class TestWeeklyReport:
    @pytest.mark.anyio
    async def test_student_llm_report(self, fake_session, monkeypatch):
        async def fake_student_detail(db, class_id, student_id):
            return {"student_info": {"name": "李雷"}, "accuracy_trend": [0.8, 0.9]}
        async def fake_llm(messages, temperature=None, max_tokens=None, json_mode=False):
            return "本周李雷同学练习 12 次，正确率稳步提升，继续保持！"
        monkeypatch.setattr(dt.PanelService, "get_student_detail", fake_student_detail)
        monkeypatch.setattr(dt, "llm_chat", fake_llm)

        result = await dt.weekly_report(student_id=1, class_id=1)
        assert result["scope"] == "student"
        assert result["report"] == "本周李雷同学练习 12 次，正确率稳步提升，继续保持！"

    @pytest.mark.anyio
    async def test_class_llm_report(self, fake_session, monkeypatch):
        async def fake_class_overview(db, class_id):
            return {"class_name": "高一(1)班", "barrier_distribution": []}
        async def fake_llm(messages, **kwargs):
            return "高一(1)班本周整体表现良好。"
        monkeypatch.setattr(dt.PanelService, "get_class_overview", fake_class_overview)
        monkeypatch.setattr(dt, "llm_chat", fake_llm)

        result = await dt.weekly_report(class_id=2)
        assert result["scope"] == "class"
        assert result["class_id"] == 2
        assert "高一(1)班" in result["report"]

    @pytest.mark.anyio
    async def test_no_data(self, fake_session, monkeypatch):
        async def fake_student_detail(db, class_id, student_id):
            return None
        monkeypatch.setattr(dt.PanelService, "get_student_detail", fake_student_detail)

        result = await dt.weekly_report(student_id=1, class_id=1)
        assert result["no_data"] is True

    @pytest.mark.anyio
    async def test_llm_failure_degrades_to_structured(self, fake_session, monkeypatch):
        async def fake_student_detail(db, class_id, student_id):
            return {"student_info": {"name": "李雷"}}
        async def fake_llm(messages, **kwargs):
            raise Exception("LLM 不可用")
        monkeypatch.setattr(dt.PanelService, "get_student_detail", fake_student_detail)
        monkeypatch.setattr(dt, "llm_chat", fake_llm)

        result = await dt.weekly_report(student_id=1, class_id=1)
        assert result["degraded"] is True
        assert result["report"]["student_info"]["name"] == "李雷"


# ═══════════════════════════════════════════════════════════════
# generate_learning_plan — 预览路由（不写库）
# ═══════════════════════════════════════════════════════════════

class TestGenerateLearningPlan:
    @pytest.mark.anyio
    async def test_returns_route_not_plan_record(self):
        result = await dt.generate_learning_plan(42)
        assert result["_route"]["page"] == "students"
        assert result["_route"]["params"]["student_id"] == 42
        assert result["_route"]["params"]["action"] == "open_learning_plan"
        # 不写库：无 plan_id，不依赖任何会话
        assert "plan_id" not in result


# ═══════════════════════════════════════════════════════════════
# send_learning_plan — 发送学习计划（审批门控工具）
# ═══════════════════════════════════════════════════════════════

class TestSendLearningPlan:
    @pytest.mark.anyio
    async def test_sends_notification(self, fake_session, monkeypatch):
        calls = []

        async def fake_create_notification(db, student_id, type_, title, body, related_id=None):
            calls.append({
                "student_id": student_id, "type_": type_, "title": title,
                "body": body, "related_id": related_id,
            })

        monkeypatch.setattr(dt.NotificationService, "create_notification", fake_create_notification)

        result = await dt.send_learning_plan(plan_id=7, student_id=3)
        assert result["status"] == "sent"
        assert result["plan_id"] == 7
        assert result["student_id"] == 3
        assert len(calls) == 1
        assert calls[0]["title"] == "新的学习计划"
        assert calls[0]["type_"] == "plan_updated"
        assert calls[0]["related_id"] == 7
        assert "7" in calls[0]["body"]


# ═══════════════════════════════════════════════════════════════
# show_students — 障碍过滤透传
# ═══════════════════════════════════════════════════════════════

class TestShowStudents:
    @pytest.mark.anyio
    async def test_barrier_passthrough(self):
        result = await dt.show_students(class_id=3, keyword="张", barrier="reading")
        comp = result["_component"]
        assert comp["type"] == "student-list"
        assert comp["class_id"] == 3
        assert comp["keyword"] == "张"
        assert comp["barrier"] == "reading"

    @pytest.mark.anyio
    async def test_no_barrier_defaults_empty(self):
        result = await dt.show_students(class_id=3)
        assert result["_component"]["barrier"] == ""


# ═══════════════════════════════════════════════════════════════
# 工具元数据 — persona / call_limit / 审批 / 前置条件
# ═══════════════════════════════════════════════════════════════

class TestDiagnosisToolMetadata:
    def test_call_limits_personas_approval(self):
        from agent.tools.tool_meta import get_all_tools
        all_tools = get_all_tools()
        expected = {
            "diagnose_barrier": (2, ["teacher", "parent"], False),
            "show_diagnosis": (1, ["teacher"], False),
            "show_students": (1, ["teacher"], False),
            "weekly_report": (2, ["teacher", "parent"], False),
            "assign_adaptive_practice": (1, ["teacher"], True),
            "generate_learning_plan": (5, ["teacher"], False),
            "send_learning_plan": (2, ["teacher"], True),
        }
        for name, (limit, persona, approval) in expected.items():
            meta = all_tools.get(name)
            assert meta is not None, f"工具 {name} 未注册"
            assert meta["call_limit"] == limit, f"{name} call_limit 应为 {limit}"
            assert meta["persona"] == persona, f"{name} persona 应为 {persona}"
            assert meta["requires_approval"] is approval, f"{name} 审批标记应为 {approval}"

    def test_or_semantics_prerequisites_cleared(self):
        from agent.tools.tool_meta import get_all_tools
        all_tools = get_all_tools()
        # OR 语义工具（student_id OR class_id）不再依赖 Guard L1 AND 前置条件
        for name in ["diagnose_barrier", "assign_adaptive_practice", "weekly_report"]:
            assert all_tools[name]["prerequisites"] == [], f"{name} 前置条件应为空"
        # send_learning_plan 保持 AND 前置条件（plan_id + student_id 同时必需）
        assert all_tools["send_learning_plan"]["prerequisites"] == ["plan_id", "student_id"]
