"""organic_tutor — 有机化学逆合成推理 Socratic 工具。

三阶段引导：
1. 官能团识别（目标分子 → 官能团拆解）
2. 逆合成路径（官能团 → 合成前体推断）
3. 反应条件验证（前体 → 反应条件/试剂选择）

注册给 Student persona，call_limit=5。
"""

from .tool_meta import register_tool
from .tutoring_factory import make_tutoring_tool

STEP_PROMPTS = [
    "【Step 1/3 — 官能团分析】请识别目标分子中含有的官能团，分析它们的化学性质。提示：关注碳碳双键、羟基、羧基、酯基等特征基团。",
    "【Step 2/3 — 逆合成路径】根据官能团的性质，倒推可能的合成前体。提示：思考哪些反应可以生成目标官能团（如醇氧化→醛、酯化→酯）。",
    "【Step 3/3 — 反应条件验证】为逆合成路径中的每一步选择合适的反应条件和试剂。提示：关注温度、催化剂、溶剂对反应选择性的影响。",
]

FEEDBACK_INSTRUCTION = (
    "你是一位有机化学教师，正在评估学生对有机合成问题的推理。"
    "请检查学生的官能团分析是否准确，逆合成路径是否可行，"
    "反应条件选择是否合理，并指出需要修正的地方（如有）。"
)

organic_tutor = register_tool(
    name="organic_tutor",
    persona=["student"],
    call_limit=5,
    description="Socratic tutoring for organic chemistry: retrosynthetic analysis and functional group transformation",
)(make_tutoring_tool("organic_tutor", STEP_PROMPTS, FEEDBACK_INSTRUCTION))
