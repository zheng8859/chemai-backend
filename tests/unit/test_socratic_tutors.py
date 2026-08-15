"""专题辅导 Socratic 工具单元测试 — make_tutoring_tool 三态 + 6 专题结构。

覆盖 tasks 3.1–3.2：
- make_tutoring_tool entry → step → complete 流转
- 6 专题工具的 step 数量与 persona/call_limit 元数据
"""

import pytest

# ── 触发所有 @register_tool 装饰器 ──
import agent.tools  # noqa: F401
from agent.tools.tutoring_factory import make_tutoring_tool


# ═══════════════════════════════════════════════════════════════
# make_tutoring_tool — 三态流转
# ═══════════════════════════════════════════════════════════════

class TestMakeTutoringTool:

    @pytest.mark.anyio
    async def test_entry_mode(self):
        """无输入 → entry 模式，引导提供问题。"""
        tool = make_tutoring_tool("demo_tutor", ["s1", "s2", "s3"], "反馈指令")
        result = await tool("")
        assert result["mode"] == "entry"
        assert result["step"] == 0
        assert result["total_steps"] == 3
        assert result["is_complete"] is False

    @pytest.mark.anyio
    async def test_step_mode_returns_prompt(self):
        """有输入且未到最后一步 → step 模式，返回当前步骤引导。"""
        tool = make_tutoring_tool("demo_tutor", ["s1", "s2", "s3"], "反馈指令")
        result = await tool("一个问题", step=0)
        assert result["mode"] == "step"
        assert result["step"] == 1
        assert result["prompt"] == "s1"
        assert result["is_complete"] is False
        assert "反馈指令" in result["feedback"]

    @pytest.mark.anyio
    async def test_last_step_completes(self):
        """最后一步 → is_complete=True，返回最后引导。"""
        tool = make_tutoring_tool("demo_tutor", ["s1", "s2", "s3"], "反馈指令")
        result = await tool("回答", step=2)
        assert result["is_complete"] is True
        assert result["prompt"] == "s3"

    @pytest.mark.anyio
    async def test_beyond_steps_summarizes(self):
        """步骤超界 → 总结模式，is_complete=True。"""
        tool = make_tutoring_tool("demo_tutor", ["s1", "s2", "s3"], "反馈指令")
        result = await tool("回答", step=3)
        assert result["is_complete"] is True
        assert "完成" in result["prompt"]


# ═══════════════════════════════════════════════════════════════
# 6 专题工具 — 结构与元数据
# ═══════════════════════════════════════════════════════════════

_TUTOR_STEPS = {
    "ionic_equation_tutor": 4,
    "stoichiometry_tutor": 4,
    "redox_tutor": 3,
    "equilibrium_tutor": 3,
    "organic_tutor": 3,
    "periodic_law_tutor": 3,
}


class TestSixTutors:

    @pytest.mark.anyio
    async def test_metadata_and_step_counts(self):
        """6 专题工具 persona=student、call_limit=5、step 数量正确。"""
        from agent.tools.tool_meta import get_tool_meta

        for name, expected_steps in _TUTOR_STEPS.items():
            meta = get_tool_meta(name)
            assert meta is not None, f"{name} 未注册"
            assert meta["persona"] == ["student"], f"{name} persona 应为 [student]"
            assert meta["call_limit"] == 5, f"{name} call_limit 应为 5"

            result = await meta["func"]("")
            assert result["total_steps"] == expected_steps, f"{name} 应有 {expected_steps} 步"
