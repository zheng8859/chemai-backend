"""periodic_law_tutor — 元素周期律 Socratic 推理工具。

三阶段引导：
1. 位置推断（原子序数 → 周期/族）
2. 结构推断（电子排布 → 金属性/非金属性）
3. 性质验证（实验现象 → 元素判定）

注册给 Student persona，call_limit=5。
"""

from .tool_meta import register_tool
from .tutoring_factory import make_tutoring_tool

STEP_PROMPTS = [
    "【Step 1/3 — 位置推断】请根据题目给出的信息，推断该元素的原子序数和在周期表中的位置（周期、族）。提示：关注原子序数与电子排布的关系。",
    "【Step 2/3 — 结构推断】根据第 1 步得出的位置，分析该元素的电子排布特征，推断其金属性/非金属性、化合价等性质。提示：同一周期从左到右金属性减弱。",
    "【Step 3/3 — 性质验证】结合元素的化学性质（如与水的反应、氧化物的酸碱性等），验证你的推断是否正确。如有实验现象描述，请与你的推断对照。",
]

FEEDBACK_INSTRUCTION = (
    "你是一位化学教师，正在评估学生对周期律问题的推理。"
    "请检查学生的推理逻辑是否严谨，对元素周期律的理解是否正确，"
    "并指出需要修正的地方（如有）。鼓励性反馈优先。"
)

periodic_law_tutor = register_tool(
    name="periodic_law_tutor",
    persona=["student"],
    call_limit=5,
    description="Socratic tutoring for periodic law problems: position → structure → property inference",
)(make_tutoring_tool("periodic_law_tutor", STEP_PROMPTS, FEEDBACK_INSTRUCTION))
