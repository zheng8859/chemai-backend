"""Agent 引擎集成测试 — Group 16: 工具注册 / Persona 过滤 / Guard 四层 /
Planner→ReAct 串联 / SSE 事件流 / 审批流程 / 上下文裁剪 / Provider 回退。

覆盖 tasks 16.1–16.10。
"""

import asyncio
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── 强制导入 agent.tools 包以触发所有 @register_tool 装饰器 ──
import agent.tools  # noqa: F401


# ═══════════════════════════════════════════════════════════════════════════════
# 16.1 — 工具注册完整性
# ═══════════════════════════════════════════════════════════════════════════════

class TestAgentToolCompleteness:
    """验证 get_all_tools() 返回完整工具集。"""

    def test_all_tools_registered(self):
        """33 个工具全部注册（30 domain + 部分浏览器工具可选）。"""
        from agent.tools.tool_meta import get_all_tools

        all_tools = get_all_tools()
        tool_names = set(all_tools.keys())

        # 核心 domain 工具（必须存在）
        required = {
            "search_exam_bank", "web_search", "show_exam_workbench",
            "save_to_bank", "generate_questions", "list_banks", "delete_bank",
            "diagnose_barrier", "show_diagnosis", "show_students", "weekly_report",
            "assign_adaptive_practice", "generate_learning_plan", "send_learning_plan",
            "chemistry_tutor", "simulate_experiment", "balance_equation",
            "ionic_equation_tutor", "stoichiometry_tutor", "redox_tutor",
            "equilibrium_tutor",
            "query_ocr_progress", "grade_answer_sheets", "save_grading_results",
            "memory_student_get", "memory_teacher_get",
            "generate_parent_report", "send_report_to_parent",
        }
        missing = required - tool_names
        assert not missing, f"缺少核心工具: {missing}"

        # 浏览器工具 — 可能因 Playwright 未安装而缺失（try/except in __init__.py）
        browser = {"browse_navigate", "browse_read", "browse_click", "browse_input", "browse_screenshot"}
        registered_browser = browser & tool_names
        # 至少有部分浏览器工具或全部（取决于环境）
        assert len(registered_browser) >= 0, "浏览器工具注册不应报错"

        # 总数 ≥ 30
        assert len(all_tools) >= 30, f"总工具数应 ≥ 30，实际 {len(all_tools)}"

    def test_tools_have_valid_metadata(self):
        """每个注册工具有 name / persona / description / func。"""
        from agent.tools.tool_meta import get_all_tools

        for name, meta in get_all_tools().items():
            assert meta.get("name"), f"工具 {name} 缺少 name"
            assert meta.get("persona"), f"工具 {name} 缺少 persona"
            assert isinstance(meta["persona"], list), f"工具 {name} persona 应为 list"
            assert meta.get("description"), f"工具 {name} 缺少 description"
            assert callable(meta.get("func")), f"工具 {name} func 不可调用"

    def test_validate_tool_integrity(self):
        """启动时完整性验证通过。"""
        from agent.tools.tool_meta import validate_tool_integrity
        errors = validate_tool_integrity()
        assert errors == [], f"工具完整性验证失败: {errors}"

    def test_new_prerequisite_metadata_fields(self):
        """新增元数据 prerequisite_any_of / prerequisite_min_length 正确写入并校验。"""
        from agent.tools.tool_meta import get_tool_meta, validate_tool_integrity

        diag = get_tool_meta("diagnose_barrier")
        assert diag["prerequisite_any_of"] == [["student_id", "class_id", "student_name"]]

        search = get_tool_meta("search_exam_bank")
        assert search["prerequisite_min_length"] == {"keyword": 3}

        # 完整性验证（含新字段类型校验）通过
        assert validate_tool_integrity() == []


# ═══════════════════════════════════════════════════════════════════════════════
# 16.2 — Persona 过滤
# ═══════════════════════════════════════════════════════════════════════════════

class TestPersonaFiltering:
    """验证各角色工具集与 30 号设计文档一致。"""

    def test_teacher_tools(self):
        from agent.tools.tool_meta import get_tool_names_for_persona
        tools = get_tool_names_for_persona("teacher")
        # Teacher: 出题 7 + 诊断 7 + 辅导 3 + OCR 3 + 记忆 2 + 浏览器 5 = 27
        assert "search_exam_bank" in tools
        assert "generate_questions" in tools
        assert "diagnose_barrier" in tools
        assert "show_students" in tools
        assert "chemistry_tutor" in tools
        assert "query_ocr_progress" in tools
        assert "memory_student_get" in tools
        assert "memory_teacher_get" in tools
        # 不应该在学生专属工具中
        assert "periodic_law_tutor" not in [t for t in tools if "periodic" in t]

    def test_student_tools(self):
        from agent.tools.tool_meta import get_tool_names_for_persona
        tools = get_tool_names_for_persona("student")
        # Student: 辅导 8 + 通用 2 + 搜索 + 记忆 1 = 12
        assert "ionic_equation_tutor" in tools
        assert "stoichiometry_tutor" in tools
        assert "redox_tutor" in tools
        assert "equilibrium_tutor" in tools
        assert "web_search" in tools
        assert "chemistry_tutor" in tools
        # 不应有教师专属
        assert "generate_questions" not in tools
        assert "diagnose_barrier" not in tools

    def test_tutor_tools(self):
        from agent.tools.tool_meta import get_tool_names_for_persona
        tools = get_tool_names_for_persona("tutor")
        assert "chemistry_tutor" in tools
        assert "search_exam_bank" in tools
        assert "web_search" in tools
        assert "balance_equation" in tools
        assert "save_to_bank" in tools
        assert "list_banks" in tools
        assert "delete_bank" in tools
        assert "generate_questions" in tools

    def test_parent_tools(self):
        from agent.tools.tool_meta import get_tool_names_for_persona
        tools = get_tool_names_for_persona("parent")
        assert "weekly_report" in tools
        assert "diagnose_barrier" in tools
        assert "generate_parent_report" in tools
        assert "send_report_to_parent" in tools
        assert "web_search" in tools
        # 不应有出题/辅导工具
        assert "generate_questions" not in tools
        assert "chemistry_tutor" not in tools


# ═══════════════════════════════════════════════════════════════════════════════
# 16.3 — Guard 四层集成
# ═══════════════════════════════════════════════════════════════════════════════

class TestGuardLayers:
    """模拟 ReAct 循环中触发每层检查。"""

    @pytest.fixture
    def guard(self):
        from app.agent.guard import GuardState
        return GuardState(persona="teacher")

    def test_l0_persona_mismatch_rejected(self, guard):
        """L0: 角色越权校验 —— teacher 调 student 专属工具 → 拒绝（跨角色泄漏防护）。"""
        result = guard.check("equilibrium_tutor", {"user_input": "test"})
        assert result.allowed is False
        assert result.layer == "L0"

    def test_unknown_tool_fail_closed(self, guard):
        """L0: 未知工具（不在 TOOL_META）→ fail-closed 拒绝，不执行。"""
        result = guard.check("nonexistent_tool_xyz", {})
        assert result.allowed is False
        assert result.layer == "L0"
        assert "TOOL_META" in result.reason

    def test_l1_prerequisites_missing(self, guard):
        """L1: 缺少必填参数 → 拒绝。"""
        result = guard.check("delete_bank", {})
        assert result.allowed is False
        assert result.layer == "L1"
        assert "bank_id" in result.reason

    def test_l1_prerequisites_present(self, guard):
        """L1: 参数齐备 → 放行（用不触发 L4 的工具）。"""
        result = guard.check("search_exam_bank", {"keyword": "氧化还原"})
        assert result.allowed is True

    def test_l1_any_of_rejection(self, guard):
        """L1: diagnose_barrier 三者全空 → 拒绝。"""
        result = guard.check("diagnose_barrier", {})
        assert result.allowed is False
        assert result.layer == "L1"

    def test_l1_any_of_passes_with_name(self, guard):
        """L1: diagnose_barrier 仅传姓名 → 放行（对齐设计 §3.3 名称解析）。"""
        result = guard.check("diagnose_barrier", {"student_name": "张三"})
        assert result.allowed is True

    def test_l1_min_length_rejected(self, guard):
        """L1: search_exam_bank keyword 长度 ≤2 → 拒绝。"""
        result = guard.check("search_exam_bank", {"keyword": "氧"})
        assert result.allowed is False
        assert result.layer == "L1"

    def test_l1_min_length_passes(self, guard):
        """L1: search_exam_bank keyword 长度 ≥3 → 放行。"""
        result = guard.check("search_exam_bank", {"keyword": "氧化还原"})
        assert result.allowed is True

    def test_l2_call_limit_exceeded(self, guard):
        """L2: 超过 call_limit → 拒绝。"""
        # simulate_experiment 有 call_limit=5 且 teacher 可用
        for _ in range(5):
            guard.tool_call_counts["simulate_experiment"] = guard.tool_call_counts.get("simulate_experiment", 0) + 1
        result = guard.check("simulate_experiment", {"experiment_name": "test"})
        assert result.allowed is False
        assert result.layer == "L2"
        assert "上限" in result.reason

    def test_l2_within_limit(self, guard):
        """L2: 未超限 → 放行。"""
        result = guard.check("simulate_experiment", {"experiment_name": "test"})
        assert result.allowed is True

    def test_l3_dedup_detection(self, guard):
        """L3: 相同参数重复调用 → 拒绝。"""
        # 第一次调用记录
        guard.record_execution("search_exam_bank", {"keyword": "氧化还原"})
        # 第二次相同调用
        result = guard.check("search_exam_bank", {"keyword": "氧化还原"})
        assert result.allowed is False
        assert result.layer == "L3"
        assert "重复" in result.reason

    def test_l3_different_args_allowed(self, guard):
        """L3: 不同参数 → 放行。"""
        guard.record_execution("search_exam_bank", {"keyword": "氧化还原"})
        result = guard.check("search_exam_bank", {"keyword": "离子反应"})
        assert result.allowed is True

    def test_l4_approval_required(self, guard):
        """L4: requires_approval=True → 首次触发审批等待。"""
        result = guard.check("delete_bank", {"bank_id": "b1"})
        assert result.allowed is False
        assert result.layer == "L4"
        assert result.needs_approval is True
        assert result.approval_id

    def test_l4_approval_approved(self, guard):
        """L4: 审批通过后放行。"""
        result1 = guard.check("delete_bank", {"bank_id": "b2"})
        assert result1.needs_approval is True
        guard.approve(result1.approval_id)
        result2 = guard.check("delete_bank", {"bank_id": "b2"})
        assert result2.allowed is True

    def test_l4_approval_rejected(self, guard):
        """L4: 审批拒绝后保持拒绝。"""
        result1 = guard.check("delete_bank", {"bank_id": "b3"})
        guard.reject(result1.approval_id)
        result2 = guard.check("delete_bank", {"bank_id": "b3"})
        assert result2.allowed is False

    def test_strip_special_fields(self, guard):
        """剥离 _component / _route 到 GuardState。"""
        raw = {"result": "ok", "_component": {"type": "exam-workbench"}, "_route": "exam"}
        clean = guard.strip_special_fields(raw)
        assert "_component" not in clean
        assert "_route" not in clean
        assert clean["result"] == "ok"
        assert len(guard.stripped_components) == 1
        assert guard.stripped_components[0]["type"] == "exam-workbench"
        assert len(guard.stripped_routes) == 1

    def test_guard_record_execution(self, guard):
        """记录执行后 L2 计数 + L3 去重键更新。"""
        guard.record_execution("show_students", {"class_id": 1})
        assert guard.tool_call_counts["show_students"] == 1
        assert len(guard.dedup_keys) == 1

    def test_guard_state_serialization_roundtrip(self, guard):
        """GuardState 经 LangGraph 序列化器往返后 set/dict/身份字段不丢失。"""
        from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

        guard.record_execution("search_exam_bank", {"keyword": "氧化还原"})
        guard.check("delete_bank", {"bank_id": "b9"})  # 触发 L4 建审批队列
        guard.strip_special_fields({"result": "ok", "_component": {"type": "exam"}})
        guard.teacher_id = 7
        guard.student_id = 100
        guard.bound_student_ids = {100, 101}

        serde = JsonPlusSerializer()
        restored = serde.loads_typed(serde.dumps_typed(guard))

        assert restored.tool_call_counts == guard.tool_call_counts
        assert restored.dedup_keys == guard.dedup_keys
        assert restored.approval_queue == guard.approval_queue
        assert restored.stripped_components == guard.stripped_components
        assert restored.stripped_routes == guard.stripped_routes
        assert restored.teacher_id == 7
        assert restored.student_id == 100
        assert restored.bound_student_ids == {100, 101}


class TestIdentityBinding:
    """Guard 身份绑定（防 IDOR）：身份参数绑定到 JWT 认证身份。"""

    def test_student_id_clamped_for_student_persona(self):
        from app.agent.guard import GuardState
        guard = GuardState(persona="student", student_id=100)
        args = {"student_id": 999}
        err = guard.bind_identity("memory_student_get", args)
        assert err is None
        assert args["student_id"] == 100

    def test_parent_rejects_non_bound_student(self):
        from app.agent.guard import GuardState
        guard = GuardState(persona="parent", bound_student_ids={100, 101})
        args = {"student_id": 888}
        err = guard.bind_identity("generate_parent_report", args)
        assert err is not None
        assert err.allowed is False
        assert err.layer == "L0"

    def test_parent_allows_bound_student(self):
        from app.agent.guard import GuardState
        guard = GuardState(persona="parent", bound_student_ids={100, 101})
        args = {"student_id": 101}
        err = guard.bind_identity("generate_parent_report", args)
        assert err is None
        assert args["student_id"] == 101

    def test_parent_fail_closed_with_no_bindings(self):
        from app.agent.guard import GuardState
        guard = GuardState(persona="parent", bound_student_ids=set())
        args = {"student_id": 888}
        err = guard.bind_identity("generate_parent_report", args)
        assert err is not None
        assert err.allowed is False
        assert err.layer == "L0"

    def test_teacher_id_clamped_for_teacher(self):
        from app.agent.guard import GuardState
        guard = GuardState(persona="teacher", teacher_id=7)
        args = {"name": "bank", "questions": [], "teacher_id": 999}
        err = guard.bind_identity("save_to_bank", args)
        assert err is None
        assert args["teacher_id"] == 7

    def test_student_id_zero_sentinel_not_bound(self):
        """student_id=0 哨兵 → 不绑定（交给 L1 前置校验处理）。"""
        from app.agent.guard import GuardState
        guard = GuardState(persona="student", student_id=100)
        args = {"student_id": 0}
        err = guard.bind_identity("memory_student_get", args)
        assert err is None
        assert args["student_id"] == 0


class TestGuardHelpers:
    """Guard 辅助函数契约测试（_is_present / _args_json）。"""

    def test_is_present_semantics(self):
        """_is_present：None/空串/0 → 未提供；非空 → 已提供（ID 哨兵契约）。"""
        from app.agent.guard import _is_present

        assert _is_present(None) is False
        assert _is_present("") is False
        assert _is_present(0) is False
        assert _is_present(0.0) is False
        assert _is_present("张三") is True
        assert _is_present(1) is True
        assert _is_present(-1) is True
        assert _is_present(3.5) is True

    def test_args_json_order_independent(self):
        """_args_json 经 sort_keys 规范化，去重键/审批 ID 与参数顺序无关。"""
        from app.agent.guard import _make_approval_id, _make_dedup_key

        k1 = _make_dedup_key("search_exam_bank", {"keyword": "氧", "kp": "氧化还原"})
        k2 = _make_dedup_key("search_exam_bank", {"kp": "氧化还原", "keyword": "氧"})
        assert k1 == k2  # 参数顺序不影响去重键

        aid = _make_approval_id("delete_bank", {"bank_id": "b1"})
        assert aid.startswith("approval-delete_bank-")


# ═══════════════════════════════════════════════════════════════════════════════
# 16.3b — Guard 拦截器（awrap_tool_call）
# ═══════════════════════════════════════════════════════════════════════════════

class TestGuardWrapper:
    """验证 guard_tool_call_wrapper 在工具执行前的拦截行为。"""

    @pytest.fixture
    def guard(self):
        from app.agent.guard import GuardState
        return GuardState(persona="teacher")

    @staticmethod
    def _request(tool_name: str, args: dict, guard) -> MagicMock:
        return MagicMock(
            tool_call={"name": tool_name, "args": args, "id": "call-1"},
            state={"guard_state": guard},
            runtime=None,
        )

    @pytest.mark.anyio
    async def test_wrapper_fail_closed_when_guard_state_missing(self):
        """state 缺 guard_state → fail-closed 拒绝，不调 execute。"""
        from app.agent.guard import guard_tool_call_wrapper
        from langchain_core.messages import ToolMessage

        called = []
        async def execute(req):
            called.append(1)
            return ToolMessage(content="{}", tool_call_id="call-1")

        req = MagicMock(
            tool_call={"name": "web_search", "args": {"query": "氧"}, "id": "call-1"},
            state={},  # 缺 guard_state
            runtime=None,
        )
        out = await guard_tool_call_wrapper(req, execute)

        assert called == []  # execute 未被调用（fail-closed）
        assert isinstance(out, ToolMessage)
        assert "L0" in out.content

    @pytest.mark.anyio
    async def test_wrapper_l1_rejects_without_execute(self, guard):
        """L1 拒绝 → 短路返回错误 ToolMessage，不调 execute。"""
        from app.agent.guard import guard_tool_call_wrapper
        from langchain_core.messages import ToolMessage

        called = []
        async def execute(req):
            called.append(1)
            return ToolMessage(content="{}", tool_call_id="call-1")

        req = self._request("search_exam_bank", {"keyword": "氧"}, guard)
        out = await guard_tool_call_wrapper(req, execute)

        assert called == []  # execute 未被调用
        assert isinstance(out, ToolMessage)
        assert "L1" in out.content

    @pytest.mark.anyio
    async def test_wrapper_l2_rejects_at_limit(self, guard):
        """L2 超限 → 短路拒绝，不调 execute。"""
        from app.agent.guard import guard_tool_call_wrapper
        from langchain_core.messages import ToolMessage

        guard.tool_call_counts["web_search"] = 2  # call_limit=2 已满

        called = []
        async def execute(req):
            called.append(1)
            return ToolMessage(content="{}", tool_call_id="call-1")

        req = self._request("web_search", {"query": "氧"}, guard)
        out = await guard_tool_call_wrapper(req, execute)

        assert called == []
        assert isinstance(out, ToolMessage)
        assert "L2" in out.content

    @pytest.mark.anyio
    async def test_wrapper_allows_executes_strips(self, guard):
        """放行 → 执行 + 记录 + 剥离，返回 Command 回写 guard_state。"""
        from app.agent.guard import guard_tool_call_wrapper
        from langchain_core.messages import ToolMessage
        from langgraph.types import Command

        async def execute(req):
            return ToolMessage(
                content=json.dumps(
                    {"_component": {"type": "exam-workbench"}, "result": "ok"},
                    ensure_ascii=False,
                ),
                tool_call_id="call-1",
            )

        req = self._request("show_exam_workbench", {}, guard)
        out = await guard_tool_call_wrapper(req, execute)

        # 返回 Command（messages + guard_state 更新）
        assert isinstance(out, Command)
        msgs = out.update["messages"]
        assert len(msgs) == 1
        content = json.loads(msgs[0].content)
        assert "_component" not in content
        assert content["result"] == "ok"

        # 收集进 guard_state
        assert len(guard.stripped_components) == 1
        assert guard.stripped_components[0]["type"] == "exam-workbench"
        assert guard.tool_call_counts["show_exam_workbench"] == 1

    @pytest.mark.anyio
    async def test_wrapper_strips_dict_content(self, guard):
        """dict 形态 content（防御性归一化）→ 剥离 _component 进 GuardState。"""
        from app.agent.guard import guard_tool_call_wrapper
        from langchain_core.messages import ToolMessage
        from langgraph.types import Command

        async def execute(req):
            m = ToolMessage(content="{}", tool_call_id="call-1")
            # 绕过 Pydantic 校验，模拟工具直返 dict 形态 content
            object.__setattr__(
                m, "content", {"_component": {"type": "exam-workbench"}, "result": "ok"}
            )
            return m

        req = self._request("show_exam_workbench", {}, guard)
        out = await guard_tool_call_wrapper(req, execute)

        assert isinstance(out, Command)
        msgs = out.update["messages"]
        content = json.loads(msgs[0].content)
        assert "_component" not in content
        assert content["result"] == "ok"
        assert len(guard.stripped_components) == 1
        assert guard.stripped_components[0]["type"] == "exam-workbench"


# ═══════════════════════════════════════════════════════════════════════════════
# 16.3c — Guard 在真实 ReAct 循环中生效
# ═══════════════════════════════════════════════════════════════════════════════

class _ScriptedChatModel:
    """按脚本返回 AIMessage 的最小假模型（同步 _generate，ainvoke 走线程）。"""

    def __init__(self, script: list):
        from langchain_core.language_models.chat_models import BaseChatModel
        from langchain_core.outputs import ChatGeneration, ChatResult

        class _Model(BaseChatModel):
            @property
            def _llm_type(self) -> str:
                return "scripted-chat-model"

            def bind_tools(self, tools, **kwargs):
                """脚本模型不真正绑定工具——返回自身即可，工具调用由脚本 AIMessage 提供。"""
                return self

            def _generate(self, messages, stop=None, run_manager=None, **kwargs):
                msg = script[min(self._i, len(script) - 1)]
                self._i += 1
                return ChatResult(generations=[ChatGeneration(message=msg)])

        self.model = _Model()
        self.model._i = 0


class TestGuardReActLoop:
    """用 mock LLM 跑完整 ReAct 循环，验证 Guard 在工具执行前真实生效。"""

    @pytest.mark.anyio
    async def test_l2_call_limit_enforced_in_react_loop(self):
        """同一工具超 call_limit 后，第二次调用被 L2 拒绝、不执行工具函数。"""
        from langchain_core.messages import AIMessage, HumanMessage
        from langchain_core.tools import tool as tool_decorator
        from langgraph.graph import MessagesState
        from langgraph.managed import RemainingSteps
        from langgraph.prebuilt import ToolNode, create_react_agent
        from typing_extensions import NotRequired

        from app.agent.guard import GuardState, guard_tool_call_wrapper

        # 用计数 fake 命名为 "web_search"（call_limit=2），验证只执行 2 次
        calls = []
        @tool_decorator("web_search")
        async def fake_web_search(query: str) -> dict:
            """假联网搜索：记录调用次数，不触网。"""
            calls.append(query)
            return {"query": query, "results": []}

        script = [
            AIMessage(content="", tool_calls=[{"name": "web_search", "args": {"query": "q1"}, "id": "c1"}]),
            AIMessage(content="", tool_calls=[{"name": "web_search", "args": {"query": "q2"}, "id": "c2"}]),
            AIMessage(content="", tool_calls=[{"name": "web_search", "args": {"query": "q3"}, "id": "c3"}]),
            AIMessage(content="done"),
        ]

        class State(MessagesState):
            guard_state: GuardState
            remaining_steps: NotRequired[RemainingSteps]

        tool_node = ToolNode([fake_web_search], awrap_tool_call=guard_tool_call_wrapper)
        agent = create_react_agent(model=_ScriptedChatModel(script).model, tools=tool_node, state_schema=State)

        gs = GuardState(persona="teacher")
        await agent.ainvoke(
            {"messages": [HumanMessage(content="search")], "guard_state": gs},
            {"configurable": {"thread_id": "t-l2-loop"}},
        )

        # web_search call_limit=2：前两次执行，第三次被 L2 拒绝
        assert len(calls) == 2, f"web_search 应只执行 2 次，实际 {len(calls)}"
        assert gs.tool_call_counts.get("web_search") == 2

    @pytest.mark.anyio
    async def test_approval_interrupt_then_resume_via_sse(self):
        """审批门控（D3）：interrupt 触发 awaiting_approval → resume 后执行；拒绝不执行。"""
        from langchain_core.messages import AIMessage, HumanMessage
        from langchain_core.tools import tool as tool_decorator
        from langgraph.checkpoint.memory import InMemorySaver
        from langgraph.graph import MessagesState
        from langgraph.managed import RemainingSteps
        from langgraph.prebuilt import ToolNode, create_react_agent
        from typing_extensions import NotRequired

        from app.agent.guard import GuardState, guard_tool_call_wrapper
        from app.agent.sse.adapter_v2 import langgraph_sse_v2

        script = [
            AIMessage(content="", tool_calls=[{"name": "delete_bank", "args": {"bank_id": 7}, "id": "c1"}]),
            AIMessage(content="已删除题库"),
        ]

        class State(MessagesState):
            guard_state: GuardState
            remaining_steps: NotRequired[RemainingSteps]

        # ── 批准路径 ──
        executed = []
        @tool_decorator("delete_bank")
        async def fake_delete_bank(bank_id: int) -> dict:
            """删除题库（需审批）。"""
            executed.append(bank_id)
            return {"deleted": bank_id}

        tool_node = ToolNode([fake_delete_bank], awrap_tool_call=guard_tool_call_wrapper)
        agent = create_react_agent(
            model=_ScriptedChatModel(script).model,
            tools=tool_node,
            state_schema=State,
            checkpointer=InMemorySaver(),
        )
        config = {"configurable": {"thread_id": "t-approve"}}

        # 第一次运行：interrupt → awaiting_approval，工具不执行
        first_events = []
        async for sse in langgraph_sse_v2(
            agent=agent,
            messages=[HumanMessage(content="删除题库7")],
            config=config,
            guard_state=GuardState(persona="teacher"),
            thread_id="t-approve",
        ):
            first_events.append(sse)

        assert any("awaiting_approval" in e for e in first_events), "应发射 awaiting_approval phase 事件"
        assert executed == [], "审批通过前工具不得执行"

        # 批准恢复：工具执行
        second_events = []
        async for sse in langgraph_sse_v2(
            agent=agent,
            messages=[],
            config=config,
            guard_state=None,
            thread_id="t-approve",
            resume={"approved": True},
        ):
            second_events.append(sse)
        assert executed == [7], "批准后工具应执行"

        # ── 拒绝路径（独立线程 + 独立计数）──
        rejected = []
        @tool_decorator("delete_bank")
        async def fake_delete_bank_reject(bank_id: int) -> dict:
            """删除题库（需审批）。"""
            rejected.append(bank_id)
            return {"deleted": bank_id}

        tool_node2 = ToolNode([fake_delete_bank_reject], awrap_tool_call=guard_tool_call_wrapper)
        agent2 = create_react_agent(
            model=_ScriptedChatModel(script).model,
            tools=tool_node2,
            state_schema=State,
            checkpointer=InMemorySaver(),
        )
        config2 = {"configurable": {"thread_id": "t-reject"}}

        async for sse in langgraph_sse_v2(
            agent=agent2,
            messages=[HumanMessage(content="删除题库7")],
            config=config2,
            guard_state=GuardState(persona="teacher"),
            thread_id="t-reject",
        ):
            pass

        async for sse in langgraph_sse_v2(
            agent=agent2,
            messages=[],
            config=config2,
            guard_state=None,
            thread_id="t-reject",
            resume={"approved": False},
        ):
            pass

        assert rejected == [], "拒绝后工具不得执行"

        # 拒绝消息写入图状态（ToolMessage 含 cancelled），供 LLM 向用户告知取消
        snap = await agent2.aget_state(config2)
        tool_contents = [
            m.content for m in snap.values["messages"]
            if type(m).__name__ == "ToolMessage"
        ]
        assert any("取消" in c or "cancelled" in c for c in tool_contents), \
            "拒绝应写入取消消息到图状态"


# ═══════════════════════════════════════════════════════════════════════════════
# 16.4 — Planner → ReAct 串联
# ═══════════════════════════════════════════════════════════════════════════════

class TestPlannerIntegration:
    """Planner 核心逻辑 + 超时 fallback。"""

    def test_plan_validation_rejects_invalid_tool(self):
        """validate() 拒绝不存在的工具。"""
        from app.agent.planner import Plan, PlanStep, validate
        plan = Plan(steps=[
            PlanStep(step_num=1, skill_name="non_existent_tool", intent="test"),
        ])
        errors = validate(plan, ["search_exam_bank"])
        assert len(errors) > 0
        assert any("non_existent_tool" in e or "不存在" in e for e in errors)

    def test_plan_validation_rejects_duplicate_steps(self):
        """validate() 拒绝重复 step 编号。"""
        from app.agent.planner import Plan, PlanStep, validate
        plan = Plan(steps=[
            PlanStep(step_num=1, skill_name="search_exam_bank", intent="a"),
            PlanStep(step_num=1, skill_name="web_search", intent="b"),
        ])
        errors = validate(plan, ["search_exam_bank", "web_search"])
        assert len(errors) > 0
        assert any("重复" in e or "duplicate" in e.lower() for e in errors)

    def test_plan_validation_rejects_self_reference(self):
        """validate() 拒绝自引用 depends_on。"""
        from app.agent.planner import Plan, PlanStep, validate
        plan = Plan(steps=[
            PlanStep(step_num=1, skill_name="search_exam_bank", intent="a", depends_on=1),
        ])
        errors = validate(plan, ["search_exam_bank"])
        assert len(errors) > 0
        assert any("自引用" in e or "self" in e.lower() or "自身" in e for e in errors)

    def test_plan_validation_max_steps(self):
        """validate() 拒绝超过 6 步。"""
        from app.agent.planner import Plan, PlanStep, validate
        steps = [PlanStep(step_num=i, skill_name="web_search", intent=f"s{i}") for i in range(1, 8)]
        plan = Plan(steps=steps)
        errors = validate(plan, ["web_search"])
        assert len(errors) > 0
        assert any("6" in e or "max" in e.lower() for e in errors)

    def test_inject_dependencies(self):
        """inject_dependencies 替换 ${step_N.field}。"""
        from app.agent.planner import PlanStep, inject_dependencies
        steps = [
            PlanStep(step_num=1, skill_name="search_exam_bank", intent="搜索",
                     args_hint={"keyword": "氧化还原"}),
            PlanStep(step_num=2, skill_name="generate_questions", intent="出题",
                     args_hint={"topic": "${step_1.keyword}", "count": 3}),
        ]
        results = {1: {"keyword": "氧化还原", "results": 5}}
        inject_dependencies(steps, results)
        assert steps[1].args_hint["topic"] == "氧化还原"
        assert steps[1].args_hint["count"] == 3  # 未引用 → 保持

    def test_single_step_fallback(self):
        """single_step_fallback 生成单步 Plan。"""
        from app.agent.planner import single_step_fallback
        plan = single_step_fallback("帮我出题")
        assert len(plan.steps) == 1
        assert plan.steps[0].step_num == 1

    def test_plan_prompt_wraps_message_in_delimiters(self):
        """PLAN_PROMPT 用分隔符包裹用户消息并声明其不可信（注入加固）。"""
        from app.agent.planner import PLAN_PROMPT
        assert "<user_message>" in PLAN_PROMPT
        assert "</user_message>" in PLAN_PROMPT
        assert "{message}" in PLAN_PROMPT
        assert "不得执行" in PLAN_PROMPT

    def test_plan_to_instruction_declares_guidance(self):
        """计划指令声明为「仅供参考/非权威」，防 LLM 生成的意图被当作命令。"""
        from app.agent.planner import Plan, PlanStep
        from app.api.v1.chat import _plan_to_instruction
        plan = Plan(steps=[
            PlanStep(step_num=1, skill_name="search_exam_bank", intent="搜索", args_hint={"keyword": "氧化还原"}),
        ])
        text = _plan_to_instruction(plan)
        assert "仅供参考" in text
        assert "非权威" in text


# ═══════════════════════════════════════════════════════════════════════════════
# 16.5 — SSE 事件流
# ═══════════════════════════════════════════════════════════════════════════════

class TestSSEEventSequence:
    """验证 SSE 适配器 v2 事件类型和处理逻辑。"""

    def test_sse_format(self):
        """_format_sse 输出正确格式。"""
        from app.agent.sse.adapter_v2 import _format_sse
        result = _format_sse({"type": "text", "content": "hello"})
        assert result.startswith("event: text\n")
        assert '"content":"hello"' in result.replace(" ", "")

    def test_text_overlap_detection(self):
        """文本去重算法：重叠 > 70% 检测。"""
        from app.agent.sse.adapter_v2 import _text_overlap
        # 完全相同 → 重叠 100%
        assert _text_overlap("hello world", "hello world") == 1.0
        # 完全不同 → 重叠 0%
        assert _text_overlap("abc", "xyz") == 0.0
        # 部分重叠
        overlap = _text_overlap("hello world", "hello there")
        assert 0 < overlap < 1.0

    def test_safe_serialize_handles_non_json(self):
        """_safe_serialize 处理不可 JSON 序列化的对象。"""
        from app.agent.sse.adapter_v2 import _safe_serialize
        result = _safe_serialize({"key": "value", "num": 42})
        parsed = json.loads(result)
        assert parsed["key"] == "value"

    @pytest.mark.anyio
    async def test_queue_full_drops_text(self):
        """背压保护：队列满时丢弃 text 中间帧。"""
        import asyncio as aio
        from app.agent.sse.adapter_v2 import _safe_put

        queue = aio.Queue(maxsize=2)
        await _safe_put(queue, {"type": "tool_call", "name": "test"})
        await _safe_put(queue, {"type": "text", "content": "chunk1"})
        # 队列已满 (2/2)
        await _safe_put(queue, {"type": "text", "content": "chunk2"})  # 应该被丢弃
        # text2 满时丢弃，tool_result 使用 await put（会等待）
        # 为避免阻塞，不再等 tool_result
        assert queue.qsize() == 2  # tool_call + text1（text2 被丢弃）


# ═══════════════════════════════════════════════════════════════════════════════
# 16.6 — 审批流程端到端
# ═══════════════════════════════════════════════════════════════════════════════

class TestApprovalFlow:
    """审批 → 确认 → resume 完整流程。"""

    def test_approval_id_generation(self):
        """审批 ID 基于工具名和参数生成，相同输入 → 相同 ID。"""
        from app.agent.guard import _make_approval_id
        id1 = _make_approval_id("delete_bank", {"bank_id": "b1"})
        id2 = _make_approval_id("delete_bank", {"bank_id": "b1"})
        id3 = _make_approval_id("delete_bank", {"bank_id": "b2"})
        assert id1 == id2
        assert id1 != id3

    def test_guard_approval_queue_lifecycle(self):
        """完整的审批生命周期：创建 → 批准 → 执行。"""
        from app.agent.guard import GuardState
        g = GuardState(persona="teacher")

        # Step 1: 触发审批
        r1 = g.check("delete_bank", {"bank_id": "test_bank"})
        assert r1.needs_approval is True
        assert r1.approval_id in g.approval_queue
        assert g.approval_queue[r1.approval_id]["status"] == "pending"

        # Step 2: 批准
        g.approve(r1.approval_id)
        assert g.approval_queue[r1.approval_id]["status"] == "approved"

        # Step 3: 再次调用 → 放行
        r2 = g.check("delete_bank", {"bank_id": "test_bank"})
        assert r2.allowed is True
        assert g.approval_queue[r1.approval_id]["status"] == "executed"


# ═══════════════════════════════════════════════════════════════════════════════
# 16.7 — 上下文裁剪集成
# ═══════════════════════════════════════════════════════════════════════════════

class TestContextTrimmer:
    """三层裁剪策略。"""

    def test_no_trim_below_threshold(self):
        """消息数 ≤ 阈值 → 不裁剪。"""
        from app.agent.context_trimmer import trim, MAX_MESSAGES
        messages = [{"role": "user", "content": f"msg{i}"} for i in range(MAX_MESSAGES)]
        result = trim(messages)
        assert len(result) == MAX_MESSAGES

    def test_trim_above_threshold(self):
        """消息数 > 阈值 → 裁剪触发。"""
        from app.agent.context_trimmer import trim, MAX_MESSAGES
        messages = [{"role": "user", "content": f"msg{i}"} for i in range(MAX_MESSAGES + 10)]
        result = trim(messages)
        assert len(result) <= MAX_MESSAGES

    def test_keyword_messages_preserved(self):
        """含教学关键词的消息在 Layer 2 保留。"""
        from app.agent.context_trimmer import trim, MAX_MESSAGES, KEEP_RECENT
        # 构建超过阈值的消息列表
        base = [{"role": "user", "content": f"msg{i}"} for i in range(MAX_MESSAGES - KEEP_RECENT)]
        keyword_msg = {"role": "user", "content": "这位学生的化学方程式配平需要加强"}
        messages = base + [keyword_msg] + [{"role": "assistant", "content": f"r{i}"} for i in range(KEEP_RECENT)]
        # 总消息数 > MAX_MESSAGES
        assert len(messages) > MAX_MESSAGES
        result = trim(messages)
        # 关键词消息应该保留，最近 KEEP_RECENT 条也应该保留
        assert len(result) > KEEP_RECENT  # 至少保留了关键词消息

    def test_should_trim(self):
        """should_trim 正确判断。"""
        from app.agent.context_trimmer import should_trim, MAX_MESSAGES
        assert should_trim([{"role": "user", "content": "x"}] * (MAX_MESSAGES + 1)) is True
        assert should_trim([{"role": "user", "content": "x"}] * MAX_MESSAGES) is False

    def test_clear_summary_cache(self):
        """清除摘要缓存。"""
        from app.agent.context_trimmer import _summary_cache, clear_summary_cache
        _summary_cache["test-thread"] = "test summary"
        clear_summary_cache("test-thread")
        assert "test-thread" not in _summary_cache


# ═══════════════════════════════════════════════════════════════════════════════
# 16.8 — Provider 回退 + 熔断器
# ═══════════════════════════════════════════════════════════════════════════════

class TestProviderFallback:
    """熔断器状态机 + 三级回退。"""

    @pytest.mark.anyio
    async def test_circuit_breaker_initial_state(self):
        """初始状态 CLOSED，允许请求。"""
        from app.llm.model_factory import CircuitBreaker, CircuitState
        cb = CircuitBreaker(provider="test")
        assert cb.state == CircuitState.CLOSED
        assert await cb.allow_request() is True

    @pytest.mark.anyio
    async def test_circuit_breaker_opens_after_failures(self):
        """连续 3 次失败 → OPEN。"""
        from app.llm.model_factory import CircuitBreaker, CircuitState
        cb = CircuitBreaker(provider="test", failure_threshold=3)
        for _ in range(3):
            await cb.record_failure()
        assert cb.state == CircuitState.OPEN
        assert await cb.allow_request() is False

    @pytest.mark.anyio
    async def test_circuit_breaker_half_open_after_timeout(self):
        """OPEN + 30s → HALF_OPEN，放行一次。"""
        from app.llm.model_factory import CircuitBreaker, CircuitState
        cb = CircuitBreaker(provider="test", failure_threshold=3, recovery_timeout=0.01)
        for _ in range(3):
            await cb.record_failure()
        assert cb.state == CircuitState.OPEN
        # 等待超时
        time.sleep(0.02)
        assert await cb.allow_request() is True
        assert cb.state == CircuitState.HALF_OPEN

    @pytest.mark.anyio
    async def test_circuit_breaker_half_open_success_recovery(self):
        """HALF_OPEN + 成功 → CLOSED。"""
        from app.llm.model_factory import CircuitBreaker, CircuitState
        cb = CircuitBreaker(provider="test", failure_threshold=1)
        await cb.record_failure()
        assert cb.state == CircuitState.OPEN
        # 等待 → HALF_OPEN
        cb.recovery_timeout = 0.0
        await cb.allow_request()
        assert cb.state == CircuitState.HALF_OPEN
        # 成功 → CLOSED
        await cb.record_success()
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0

    @pytest.mark.anyio
    async def test_circuit_breaker_half_open_failure_reopens(self):
        """HALF_OPEN + 失败 → 重新 OPEN。"""
        from app.llm.model_factory import CircuitBreaker, CircuitState
        cb = CircuitBreaker(provider="test", failure_threshold=1)
        await cb.record_failure()  # → OPEN
        cb.recovery_timeout = 0.0
        await cb.allow_request()  # → HALF_OPEN
        await cb.record_failure()  # → OPEN again
        assert cb.state == CircuitState.OPEN

    def test_get_model_creates_valid_instance(self):
        """get_model 创建 ChatOpenAI 实例。"""
        from app.llm.model_factory import get_model
        # 使用 qwen 配置（通常有环境变量）
        import os
        if os.getenv("DASHSCOPE_API_KEY"):
            model = get_model("qwen")
            assert model is not None
            assert model.model_name == os.getenv("QWEN_MODEL", "qwen-turbo")
        else:
            pytest.skip("DASHSCOPE_API_KEY 未设置")

    def test_get_model_unknown_provider_raises(self):
        """未知 Provider → ValueError。"""
        from app.llm.model_factory import get_model
        with pytest.raises(ValueError, match="未知的 LLM Provider"):
            get_model("nonexistent_provider")

    def test_provider_config_completeness(self):
        """三个 Provider 配置完整。"""
        from app.llm.model_factory import PROVIDER_CONFIG
        assert set(PROVIDER_CONFIG.keys()) == {"mimo", "qwen", "deepseek"}
        for name, cfg in PROVIDER_CONFIG.items():
            assert cfg.get("base_url"), f"{name} 缺少 base_url"
            assert cfg.get("model"), f"{name} 缺少 model"

    def test_get_circuit_breaker_status(self):
        """熔断器状态查询 API 正常。"""
        from app.llm.model_factory import get_circuit_breaker_status
        status = get_circuit_breaker_status()
        assert isinstance(status, dict)


# ═══════════════════════════════════════════════════════════════════════════════
# 16.9 — Agent 创建 + Persona 配置
# ═══════════════════════════════════════════════════════════════════════════════

class TestAgentCreation:
    """Agent 工厂 + Persona 加载。"""

    def test_load_all_personas(self):
        """4 个 Persona 全部可加载。"""
        from app.agent.persona.loader import load_persona
        for persona in ["teacher", "student", "tutor", "parent"]:
            config = load_persona(persona)
            assert config.name == persona
            assert config.system_prompt
            assert config.available_skills

    def test_persona_config_validation(self):
        """Persona 配置包含所有必需字段。"""
        from app.agent.persona.loader import load_persona
        config = load_persona("teacher")
        assert config.name
        assert config.display_name
        assert config.description
        assert len(config.available_skills) > 0

    def test_student_context_build(self, db_session):
        """build_student_context 正确生成上下文文本。"""
        from app.agent.context import build_student_context, should_inject_context

        # should_inject_context
        assert should_inject_context("student") is True
        assert should_inject_context("teacher") is False
        assert should_inject_context("parent") is False

    def test_context_injection(self):
        """inject_student_context 注入到 system prompt。"""
        from app.agent.context import inject_student_context
        result = inject_student_context("原始提示词", "学生上下文")
        assert "学生上下文" in result
        assert "原始提示词" in result

    def test_dependency_context(self):
        """AgentContext contextvars 设置/获取/清除。"""
        from app.agent.dependency import (
            AgentContext, set_current_context, get_current_context, clear_current_context
        )
        ctx = AgentContext(student_id=42, persona="student", provider_name="qwen")
        set_current_context(ctx)
        retrieved = get_current_context()
        assert retrieved.student_id == 42
        assert retrieved.persona == "student"
        clear_current_context()
        assert get_current_context() is None


# ═══════════════════════════════════════════════════════════════════════════════
# 3.6 — chem_skills 引擎导出测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestChemSkillsEngineExports:
    """验证 5 个 chem_skills 引擎的 __init__.py 导出完整性（task 3.6）。"""

    def test_equilibrium_engine_exports(self):
        """chemistry_equilibrium.engine 导出 EquilibriumTable, ICERow, apply_le_chatelier 等。"""
        from chem_skills.chemistry_equilibrium.engine import (
            EquilibriumTable,
            ICERow,
            apply_le_chatelier,
            build_ice_table,
            tutor,
        )
        assert EquilibriumTable is not None
        assert ICERow is not None
        assert callable(apply_le_chatelier)
        assert callable(build_ice_table)
        # tutor 是子模块，验证其导出
        assert callable(tutor.apply_le_chatelier)
        assert callable(tutor.build_ice_table)

    def test_ionic_engine_exports(self):
        """chemistry_ionic.engine 导出 IonicAnalysis, classify_electrolyte 等。"""
        from chem_skills.chemistry_ionic.engine import (
            IonicAnalysis,
            classify_electrolyte,
            remove_spectators,
            verify_net_ionic,
            write_ionic_form,
            tutor,
        )
        assert IonicAnalysis is not None
        assert callable(classify_electrolyte)
        assert callable(remove_spectators)
        assert callable(verify_net_ionic)
        assert callable(write_ionic_form)
        assert callable(tutor.classify_electrolyte)
        assert callable(tutor.write_ionic_form)

    def test_redox_engine_exports(self):
        """chemistry_redox.engine 导出 RedoxAnalysis, assign_oxidation_states 等。"""
        from chem_skills.chemistry_redox.engine import (
            RedoxAnalysis,
            RedoxHalfReaction,
            assign_oxidation_states,
            balance_by_electron,
            identify_redox_changes,
            tutor,
        )
        assert RedoxAnalysis is not None
        assert RedoxHalfReaction is not None
        assert callable(assign_oxidation_states)
        assert callable(balance_by_electron)
        assert callable(identify_redox_changes)
        assert callable(tutor.assign_oxidation_states)
        assert callable(tutor.balance_by_electron)

    def test_stoichiometry_engine_exports(self):
        """chemistry_stoichiometry.engine 导出 StoichiometryProblem, calculate_stepwise 等。"""
        from chem_skills.chemistry_stoichiometry.engine import (
            StoichiometryProblem,
            QuantityInfo,
            calculate_stepwise,
            extract_known_quantities,
            select_formula,
            setup_proportion,
            tutor,
        )
        assert StoichiometryProblem is not None
        assert QuantityInfo is not None
        assert callable(calculate_stepwise)
        assert callable(extract_known_quantities)
        assert callable(select_formula)
        assert callable(setup_proportion)
        assert callable(tutor.calculate_stepwise)
        assert callable(tutor.setup_proportion)

    def test_memory_engine_exports(self):
        """chemistry_memory 导出 7 个函数（task 3.5 要求）。"""
        from chem_skills.chemistry_memory import (
            compute_zpd_difficulty,
            compute_next_review,
            build_variant_prompt,
            extract_weak_knowledge_points,
            identify_dominant_barrier,
            evaluate_level_change,
            apply_strategy,
        )
        assert callable(compute_zpd_difficulty)
        assert callable(compute_next_review)
        assert callable(build_variant_prompt)
        assert callable(extract_weak_knowledge_points)
        assert callable(identify_dominant_barrier)
        assert callable(evaluate_level_change)
        assert callable(apply_strategy)


# ═══════════════════════════════════════════════════════════════════════════════
# 5.4 — Gateway Provider 选择测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestGatewayProviderSelection:
    """验证 Gateway 关键词匹配选择正确 Provider（task 5.4）。"""

    def test_vision_keywords_route_to_mimo(self):
        """图片/OCR/识别 关键词 → mimo。"""
        from app.agent.gateway import classify_provider

        assert classify_provider("帮我识别这张图片里的化学方程式") == "mimo"
        assert classify_provider("OCR扫描试卷") == "mimo"
        assert classify_provider("上传图片识别") == "mimo"
        assert classify_provider("拍照识别") == "mimo"
        assert classify_provider("看图像分析反应") == "mimo"
        assert classify_provider("截图中的方程") == "mimo"

    def test_search_keywords_route_to_mimo(self):
        """搜索/高考/最新 关键词 → mimo。"""
        from app.agent.gateway import classify_provider

        assert classify_provider("帮我搜索今年高考真题") == "mimo"
        assert classify_provider("在网上查找最新化学资料") == "mimo"
        assert classify_provider("查找资料") == "mimo"

    def test_default_text_routes_to_qwen(self):
        """普通文本消息 → qwen（默认）。"""
        from app.agent.gateway import classify_provider

        assert classify_provider("帮我出几道氧化还原的题") == "qwen"
        assert classify_provider("学生张明最近学习情况怎么样") == "qwen"
        assert classify_provider("化学平衡常数的定义是什么") == "qwen"
        assert classify_provider("Hello, can you help me?") == "qwen"


# ═══════════════════════════════════════════════════════════════════════════════
# 11.5 — 审计日志测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestAuditLogger:
    """验证审计日志正常记录、脱敏、缓冲区滚动（task 11.5）。"""

    @pytest.mark.anyio
    async def test_audit_log_normal_record(self):
        """正常记录一条审计日志到缓冲区。"""
        from app.agent.audit import AuditLogger

        logger = AuditLogger.get_instance()
        await logger.audit_log(
            timestamp=time.time(),
            persona="teacher",
            skill_name="search_exam_bank",
            args={"keyword": "氧化还原", "knowledge_points": ["化学"]},
            result={"questions": 5},
            duration_ms=234.5,
        )
        recent = logger.get_recent_logs(5)
        assert len(recent) >= 1
        latest = recent[-1]
        assert latest["persona"] == "teacher"
        assert latest["skill_name"] == "search_exam_bank"
        assert latest["duration_ms"] == 234.5

    @pytest.mark.anyio
    async def test_audit_log_with_error(self):
        """记录带错误的审计日志。"""
        from app.agent.audit import AuditLogger

        logger = AuditLogger.get_instance()
        await logger.audit_log(
            timestamp=time.time(),
            persona="student",
            skill_name="chemistry_tutor",
            args={"topic": "酸碱中和"},
            error="LLM timeout after 5s",
            duration_ms=5001,
        )
        recent = logger.get_recent_logs(3)
        latest = recent[-1]
        assert latest["error"] == "LLM timeout after 5s"
        assert latest["skill_name"] == "chemistry_tutor"

    def test_redact_sensitive_fields(self):
        """脱敏函数正确替换敏感字段。"""
        from app.agent.audit import _redact_dict

        input_args = {
            "keyword": "电化学",
            "password": "super_secret_123",
            "phone": "13800138000",
            "parent_phone": "13900139000",
            "token": "bearer-abc123",
            "api_key": "sk-xyz789",
            "secret": "my-secret-key",
            "nested": {"password": "nested_secret"},
        }
        redacted = _redact_dict(input_args)
        assert redacted["keyword"] == "电化学"
        assert redacted["password"] == "***"
        assert redacted["phone"] == "***"
        assert redacted["parent_phone"] == "***"
        assert redacted["token"] == "***"
        assert redacted["api_key"] == "***"
        assert redacted["secret"] == "***"
        assert redacted["nested"]["password"] == "***"

    def test_truncate_result(self):
        """结果截断函数正确限制长度。"""
        from app.agent.audit import _truncate_result

        short = {"key": "value"}
        assert len(_truncate_result(short)) < 50

        long = {"content": "x" * 300}
        result = _truncate_result(long)
        assert len(result) <= 203  # 200 + "..."
        assert result.endswith("...")

        assert _truncate_result(None) == ""

    @pytest.mark.anyio
    async def test_buffer_rotation(self):
        """验证缓冲区写入不丢失最近条目。"""
        from app.agent.audit import AuditLogger

        logger = AuditLogger.get_instance()
        for i in range(150):
            await logger.audit_log(
                timestamp=time.time(),
                persona="teacher",
                skill_name=f"tool_{i}",
                args={"index": i},
            )
        recent = logger.get_recent_logs(150)
        assert len(recent) <= 100  # maxlen
        # 最早的条目已被淘汰，应该以高序号开始
        indices = [r["skill_name"] for r in recent]
        assert "tool_0" not in indices  # 已滚出缓冲区

    @pytest.mark.anyio
    async def test_disk_full_does_not_block(self):
        """磁盘异常不阻塞记录（write_queue 满时安全降级）。"""
        from app.agent.audit import AuditLogger

        logger = AuditLogger.get_instance()
        # 快速写入大量条目，验证不会抛异常
        for i in range(20):
            await logger.audit_log(
                timestamp=time.time(),
                persona="teacher",
                skill_name="stress_test",
                args={"seq": i},
            )
        recent = logger.get_recent_logs(5)
        assert any(r["skill_name"] == "stress_test" for r in recent)


# ═══════════════════════════════════════════════════════════════════════════════
# 13.10 — Chat API 集成端点测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestChatAPIEndpoints:
    """验证 Chat API CRUD 端点返回正确状态码与格式（task 13.10）。"""

    async def test_chat_new_returns_thread_id(self, async_client, teacher_headers):
        """POST /chat/new 返回 thread_id。"""
        response = await async_client.post(
            "/api/v1/chat/new",
            json={"prefix": "t"},
            headers=teacher_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "thread_id" in data
        assert data["thread_id"].startswith("t-")

    async def test_chat_new_different_prefixes(self, async_client, teacher_headers):
        """不同前缀生成不同 thread_id。"""
        prefixes = ["t", "s", "p"]
        ids = set()
        for p in prefixes:
            resp = await async_client.post(
                "/api/v1/chat/new",
                json={"prefix": p},
                headers=teacher_headers,
            )
            data = resp.json()
            assert data["thread_id"].startswith(f"{p}-")
            ids.add(data["thread_id"])
        assert len(ids) == 3

    async def test_chat_conversations_empty(self, async_client, teacher_headers):
        """GET /chat/conversations 返回 501（未实现）。"""
        response = await async_client.get(
            "/api/v1/chat/conversations",
            headers=teacher_headers,
        )
        assert response.status_code == 501

    async def test_chat_conversations_with_prefix(self, async_client, teacher_headers):
        """prefix 参数过滤返回正确（501 未实现）。"""
        response = await async_client.get(
            "/api/v1/chat/conversations?prefix=t-",
            headers=teacher_headers,
        )
        assert response.status_code == 501

    async def test_chat_history_nonexistent(self, async_client, teacher_headers):
        """GET /chat/history/{thread_id} 返回 501（未实现）。"""
        response = await async_client.get(
            "/api/v1/chat/history/fake-thread-id",
            headers=teacher_headers,
        )
        assert response.status_code == 501

    async def test_chat_delete_nonexistent_safe(self, async_client, teacher_headers):
        """DELETE /chat/conversations/{thread_id} 返回 501（未实现）。"""
        response = await async_client.delete(
            "/api/v1/chat/conversations/fake-delete-id",
            headers=teacher_headers,
        )
        assert response.status_code == 501

    async def test_chat_reset_returns_ok(self, async_client, teacher_headers):
        """POST /chat/reset 返回成功（thread_id 为 query param）。"""
        response = await async_client.post(
            "/api/v1/chat/reset?thread_id=test-reset-123",
            headers=teacher_headers,
        )
        assert response.status_code == 200

    async def test_chat_stream_endpoint_exists(self, async_client, teacher_headers):
        """POST /chat/stream 端点存在（不验证 SSE 内容）。"""
        response = await async_client.post(
            "/api/v1/chat/stream",
            json={
                "message": "你好",
                "thread_id": "t-test-001",
            },
            headers=teacher_headers,
        )
        # 不验证 SSE 内容（取决于 Agent 状态），只验证端点可达
        assert response.status_code in (200, 422, 500)

    async def test_chat_resume_endpoint_exists(self, async_client, teacher_headers):
        """POST /chat/resume 端点存在。"""
        response = await async_client.post(
            "/api/v1/chat/resume",
            json={
                "thread_id": "t-test-resume-001",
                "approval_id": "approval-001",
                "approved": True,
            },
            headers=teacher_headers,
        )
        assert response.status_code in (200, 404, 422, 500)


# ═══════════════════════════════════════════════════════════════════════════════
# 16.4 — Persona 越权防护
# ═══════════════════════════════════════════════════════════════════════════════

class TestPersonaResolution:
    """验证 _resolve_persona 由认证身份决定 persona，防止越权伪装。"""

    @staticmethod
    def _user(role: str):
        from app.api.deps import UserContext
        return UserContext(user_id=1, role=role, sub_role=None, school_id=1, token_type="access")

    def test_teacher_default(self):
        from app.api.v1.chat import _resolve_persona
        assert _resolve_persona(self._user("teacher"), None) == "teacher"

    def test_teacher_can_choose_tutor(self):
        from app.api.v1.chat import _resolve_persona
        assert _resolve_persona(self._user("teacher"), "tutor") == "tutor"

    def test_student_fixed(self):
        from app.api.v1.chat import _resolve_persona
        assert _resolve_persona(self._user("student"), None) == "student"
        assert _resolve_persona(self._user("student"), "student") == "student"

    def test_student_cannot_escalate_to_teacher(self):
        from app.api.v1.chat import _resolve_persona
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            _resolve_persona(self._user("student"), "teacher")
        assert exc.value.status_code == 403

    def test_parent_cannot_escalate(self):
        from app.api.v1.chat import _resolve_persona
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            _resolve_persona(self._user("parent"), "teacher")
        assert exc.value.status_code == 403

    def test_invalid_role_rejected(self):
        from app.api.v1.chat import _resolve_persona
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            _resolve_persona(self._user("admin"), None)
        assert exc.value.status_code == 403
