"""Socratic 辅导工具集（4 个新增）— 离子反应、化学计量、氧化还原、化学平衡。

通过 tutoring_factory 生成，每个工具支持 3 种模式（entry / step / complete）。
注册给 Student persona，call_limit=5。
"""

from .tool_meta import register_tool
from .tutoring_factory import make_tutoring_tool

# ═══════════════════════════════════════════════════════════════════════════════
# ionic_equation_tutor — 离子反应四步法
# ═══════════════════════════════════════════════════════════════════════════════

IONIC_STEPS = [
    "【Step 1/4 — 识别可解离物质】请判断反应中各物质哪些可解离为离子。提示：可溶性强电解质（强酸、强碱、可溶性盐）在水中完全解离。",
    "【Step 2/4 — 写离子形式】将可解离物质拆分为离子形式，保留不可解离物质（沉淀、气体、弱电解质）的分子式。",
    "【Step 3/4 — 删除旁观离子】找出反应前后不变的物质（旁观离子），将其从方程式两侧删除。",
    "【Step 4/4 — 验证守恒】检查净离子方程式的原子守恒和电荷守恒是否成立。",
]

IONIC_FEEDBACK = (
    "你是一位化学教师，正在评估学生对离子反应方程式的书写。"
    "请检查：(1) 物质是否正确地拆分为离子，(2) 旁观离子的识别是否准确，"
    "(3) 净离子方程式是否同时满足原子守恒和电荷守恒。"
)

ionic_equation_tutor = register_tool(
    name="ionic_equation_tutor",
    persona=["student"],
    call_limit=5,
    description="Socratic tutoring for ionic reaction equations: identify dissociable species → write ion form → remove spectator ions → verify conservation. 4-step guided approach.",
)(make_tutoring_tool("ionic_equation_tutor", IONIC_STEPS, IONIC_FEEDBACK))

# ═══════════════════════════════════════════════════════════════════════════════
# stoichiometry_tutor — 化学计量四步法
# ═══════════════════════════════════════════════════════════════════════════════

STOICHIOMETRY_STEPS = [
    "【Step 1/4 — 提取已知量】请从题目中提取所有已知的物质的量、质量、体积等数据。提示：注意单位换算（g ↔ mol ↔ L）。",
    "【Step 2/4 — 选择公式】根据你提取的已知量和未知量，选择合适的关系式（n=m/M、n=V/Vm、化学计量比等）。",
    "【Step 3/4 — 建立比例关系】根据配平的化学方程式，建立已知物与未知物之间的计量比例关系。",
    "【Step 4/4 — 逐步计算】按照比例关系一步一步计算。注意有效数字和单位。",
]

STOICHIOMETRY_FEEDBACK = (
    "你是一位化学教师，正在评估学生的化学计量计算。"
    "请检查：(1) 已知量提取是否完整准确，(2) 公式选择是否恰当，"
    "(3) 比例关系是否正确，(4) 计算过程和结果是否有误。"
)

stoichiometry_tutor = register_tool(
    name="stoichiometry_tutor",
    persona=["student"],
    call_limit=5,
    description="Socratic tutoring for stoichiometry calculations: extract known quantities → select formula → set up proportion → calculate step by step. 4-step guided approach.",
)(make_tutoring_tool("stoichiometry_tutor", STOICHIOMETRY_STEPS, STOICHIOMETRY_FEEDBACK))

# ═══════════════════════════════════════════════════════════════════════════════
# redox_tutor — 氧化还原三步法
# ═══════════════════════════════════════════════════════════════════════════════

REDOX_STEPS = [
    "【Step 1/3 — 标定氧化数】请给反应中每个元素的氧化数赋值。提示：单质氧化数为 0，化合物中 H 为 +1、O 为 -2（过氧化物除外）。",
    "【Step 2/3 — 识别氧化与还原】找出哪些元素氧化数升高（被氧化）、哪些降低（被还原）。写出氧化半反应和还原半反应。",
    "【Step 3/3 — 电子守恒配平】根据得失电子总数相等的原则，配平氧化还原方程式。注意：酸性介质中加 H+ 和 H2O，碱性介质中加 OH- 和 H2O。",
]

REDOX_FEEDBACK = (
    "你是一位化学教师，正在评估学生对氧化还原反应的分析。"
    "请检查：(1) 氧化数标定是否正确，(2) 氧化剂/还原剂的识别是否准确，"
    "(3) 电子守恒是否满足，(4) 介质条件是否考虑。"
)

redox_tutor = register_tool(
    name="redox_tutor",
    persona=["student"],
    call_limit=5,
    description="Socratic tutoring for redox reactions: assign oxidation states → identify oxidation/reduction → balance by electron conservation. 3-step guided approach.",
)(make_tutoring_tool("redox_tutor", REDOX_STEPS, REDOX_FEEDBACK))

# ═══════════════════════════════════════════════════════════════════════════════
# equilibrium_tutor — 化学平衡三段式
# ═══════════════════════════════════════════════════════════════════════════════

EQUILIBRIUM_STEPS = [
    "【Step 1/3 — 分析平衡体系】请确定反应的化学方程式、各物质的初始浓度以及平衡常数的表达式。",
    "【Step 2/3 — 建立三段式表格】使用「初始/变化/平衡」（ICE）三段式表格列出各物质的浓度变化。提示：设未知变化量为 x。",
    "【Step 3/3 — 代入求解】将平衡浓度代入平衡常数表达式，求解 x，并回答题目问题。注意检验解的合理性（浓度不能为负）。",
]

EQUILIBRIUM_FEEDBACK = (
    "你是一位化学教师，正在评估学生对化学平衡的分析。"
    "请检查：(1) 平衡常数表达式是否正确，(2) ICE 表格是否合理，"
    "(3) 计算过程和结果是否有误，(4) 对勒夏特列原理的应用是否恰当。"
)

equilibrium_tutor = register_tool(
    name="equilibrium_tutor",
    persona=["student"],
    call_limit=5,
    description="Socratic tutoring for chemical equilibrium: analyze equilibrium system → apply Le Chatelier's principle → ICE table calculation. 3-step guided approach with three-line table rendering.",
)(make_tutoring_tool("equilibrium_tutor", EQUILIBRIUM_STEPS, EQUILIBRIUM_FEEDBACK))
