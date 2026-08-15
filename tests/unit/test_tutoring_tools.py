"""通用辅导 Agent 工具单元测试 — chemistry_tutor / simulate_experiment / balance_equation。

覆盖 tasks 2.1–2.3：
- chemistry_tutor 教师/学生双模式
- simulate_experiment 结构完整性 + experiment-card 组件标记
- balance_equation 三态（引擎可用→verified=True / 引擎不可用 / 配平失败→verified=False）
"""

import pytest

# ── 触发所有 @register_tool 装饰器 ──
import agent.tools  # noqa: F401
import agent.tools.tutoring_tools as tt


# ═══════════════════════════════════════════════════════════════
# chemistry_tutor — 教师/学生双模式
# ═══════════════════════════════════════════════════════════════

class TestChemistryTutor:

    @pytest.mark.anyio
    async def test_teacher_mode(self):
        """教师角色 → detailed 模式 + 800 字上限。"""
        result = await tt.chemistry_tutor(topic="氧化还原反应", persona="teacher")
        assert result["mode"] == "detailed"
        assert result["max_length"] == 800
        assert result["topic"] == "氧化还原反应"

    @pytest.mark.anyio
    async def test_student_mode(self):
        """学生角色 → guided 模式 + 500 字上限。"""
        result = await tt.chemistry_tutor(topic="氧化还原反应", persona="student")
        assert result["mode"] == "guided"
        assert result["max_length"] == 500


# ═══════════════════════════════════════════════════════════════
# simulate_experiment — 结构完整性
# ═══════════════════════════════════════════════════════════════

class TestSimulateExperiment:

    @pytest.mark.anyio
    async def test_structure_complete(self):
        """返回非空 steps/equations/safety_notes + experiment-card 标记。"""
        result = await tt.simulate_experiment("铁与硫酸铜溶液反应")

        exp = result["experiment"]
        assert exp["name"] == "铁与硫酸铜溶液反应"
        assert len(exp["steps"]) > 0
        assert len(exp["equations"]) > 0
        assert len(exp["safety_notes"]) > 0
        assert exp["phenomena"]  # 非空字符串

        assert result["_component"]["type"] == "experiment-card"
        assert result["_component"]["experiment_name"] == "铁与硫酸铜溶液反应"


# ═══════════════════════════════════════════════════════════════
# balance_equation — 三态
# ═══════════════════════════════════════════════════════════════

class TestBalanceEquation:

    @pytest.mark.anyio
    async def test_success_when_engine_available(self):
        """引擎可用时透传配平结果，verified=True。"""
        result = await tt.balance_equation("H2 + O2", "H2O")
        assert result["verified"] is True
        assert result["balanced"] == "2H2 + O2 → 2H2O"
        assert result["coefficients"]["H2"] == 2
        assert result["coefficients"]["O2"] == 1
        assert result["equation_type"] == "irreversible"

    @pytest.mark.anyio
    async def test_engine_unavailable_returns_false(self, monkeypatch):
        """引擎不可用（ImportError）→ verified=False，不抛异常。"""
        import sys
        import chem_skills.chemistry_parser.engine.balancer as balancer_mod  # noqa: F401

        monkeypatch.setitem(sys.modules, balancer_mod.__name__, None)
        result = await tt.balance_equation("H2 + O2", "H2O")
        assert result["verified"] is False
        assert "不可用" in result.get("error", "")

    @pytest.mark.anyio
    async def test_balance_failure_returns_false(self, monkeypatch):
        """引擎抛异常 → verified=False，携带错误信息，不抛未捕获异常。"""
        from chem_skills.chemistry_parser.engine import balancer

        def fake_balance(reactants, products):
            raise ValueError("无法配平该方程式")

        monkeypatch.setattr(balancer, "balance", fake_balance)
        result = await tt.balance_equation("Fe + O2", "Fe3O4")
        assert result["verified"] is False
        assert "无法配平" in result["error"]
