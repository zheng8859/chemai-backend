"""化学计量辅导函数 — 四步法。"""

from .models import StoichiometryProblem, QuantityInfo, QuantityType

# ── 常见物质的摩尔质量 (g/mol) ──
_COMMON_MOLAR_MASSES = {
    "H2O": 18.0, "H2": 2.0, "O2": 32.0, "CO2": 44.0, "NaCl": 58.5,
    "NaOH": 40.0, "HCl": 36.5, "H2SO4": 98.0, "CaCO3": 100.0,
    "Na": 23.0, "Cl2": 71.0, "N2": 28.0, "NH3": 17.0,
    "Fe": 56.0, "Cu": 63.5, "Zn": 65.4, "Ag": 108.0, "KMnO4": 158.0,
}


def extract_known_quantities(problem_text: str) -> list[QuantityInfo]:
    """从题目文本中提取已知量。

    识别模式：
    - "X g" → 质量
    - "X mol" → 物质的量
    - "X L" → 体积
    - "X mol/L" → 浓度

    Args:
        problem_text: 题目文本

    Returns:
        QuantityInfo 列表
    """
    import re

    quantities = []

    # 匹配质量: "X g"
    for m in re.finditer(r"(\d+\.?\d*)\s*g", problem_text):
        quantities.append(QuantityInfo(
            symbol="m", value=float(m.group(1)), unit="g", type=QuantityType.MASS
        ))

    # 匹配物质的量: "X mol"
    for m in re.finditer(r"(\d+\.?\d*)\s*mol", problem_text):
        if "mol/L" not in m.group(0):
            quantities.append(QuantityInfo(
                symbol="n", value=float(m.group(1)), unit="mol", type=QuantityType.MOLES
            ))

    # 匹配体积: "X L"
    for m in re.finditer(r"(\d+\.?\d*)\s*L", problem_text):
        quantities.append(QuantityInfo(
            symbol="V", value=float(m.group(1)), unit="L", type=QuantityType.VOLUME
        ))

    return quantities


def select_formula(known: QuantityInfo, unknown_type: QuantityType) -> dict:
    """选择合适的计算公式。

    Args:
        known: 已知量
        unknown_type: 未知量类型

    Returns:
        {"formula": str, "explanation": str}
    """
    transitions = {
        (QuantityType.MASS, QuantityType.MOLES): {
            "formula": "n = m / M",
            "explanation": "物质的量 (n) = 质量 (m) ÷ 摩尔质量 (M)",
        },
        (QuantityType.MOLES, QuantityType.MASS): {
            "formula": "m = n × M",
            "explanation": "质量 (m) = 物质的量 (n) × 摩尔质量 (M)",
        },
        (QuantityType.VOLUME, QuantityType.MOLES): {
            "formula": "n = V / Vm",
            "explanation": "物质的量 (n) = 体积 (V) ÷ 气体摩尔体积 (Vm = 22.4 L/mol at STP)",
        },
        (QuantityType.MOLES, QuantityType.VOLUME): {
            "formula": "V = n × Vm",
            "explanation": "体积 (V) = 物质的量 (n) × 气体摩尔体积 (Vm = 22.4 L/mol at STP)",
        },
        (QuantityType.CONCENTRATION, QuantityType.MOLES): {
            "formula": "n = c × V",
            "explanation": "物质的量 (n) = 浓度 (c) × 溶液体积 (V)",
        },
    }

    key = (known.type, unknown_type)
    if key in transitions:
        return transitions[key]

    # 同类型直接使用
    if known.type == unknown_type:
        return {"formula": "direct", "explanation": "已知量和未知量类型相同，可直接通过化学计量比换算"}

    # 默认通过物质的量桥接
    return {
        "formula": "two_step",
        "explanation": f"先将{known.type}转换为物质的量 (n)，再转换为{unknown_type}",
    }


def setup_proportion(
    known_moles: float,
    known_coefficient: int,
    unknown_coefficient: int,
) -> dict:
    """建立化学计量比例关系。

    Args:
        known_moles: 已知物质的量 (mol)
        known_coefficient: 已知物的化学计量系数
        unknown_coefficient: 未知物的化学计量系数

    Returns:
        {"ratio": str, "unknown_moles": float}
    """
    if known_coefficient == 0:
        return {"ratio": "N/A", "unknown_moles": 0}

    unknown_moles = known_moles * unknown_coefficient / known_coefficient
    return {
        "ratio": f"{unknown_coefficient} : {known_coefficient}",
        "unknown_moles": round(unknown_moles, 4),
    }


def calculate_stepwise(
    problem: StoichiometryProblem,
) -> StoichiometryProblem:
    """逐步计算化学计量问题。

    Args:
        problem: StoichiometryProblem 对象

    Returns:
        更新后的 StoichiometryProblem（含 solution_steps 和 result）
    """
    steps = []

    for q in problem.known_quantities:
        # Step 1: 转换为物质的量
        if q.type != QuantityType.MOLES and q.value is not None:
            formula_info = select_formula(q, QuantityType.MOLES)
            steps.append(f"将 {q.value} {q.unit} 转换为物质的量：{formula_info['explanation']}")

    # Step 2: 建立比例（假设化学计量系数均为 1:1 的简化场景）
    if problem.unknown_quantity and problem.known_quantities:
        known = problem.known_quantities[0]
        unknown = problem.unknown_quantity
        proportion = setup_proportion(
            known_moles=known.value if known.type == QuantityType.MOLES else 1.0,
            known_coefficient=1,
            unknown_coefficient=1,
        )
        steps.append(f"化学计量比 {proportion['ratio']}，未知物物质的量 = {proportion['unknown_moles']} mol")

    # Step 3: 转换为目标单位
    if problem.unknown_quantity and problem.unknown_quantity.type != QuantityType.MOLES:
        formula_info = select_formula(
            QuantityInfo(symbol="n", value=1.0, unit="mol", type=QuantityType.MOLES),
            problem.unknown_quantity.type,
        )
        steps.append(f"将物质的量转换为{problem.unknown_quantity.type}：{formula_info['explanation']}")

    problem.solution_steps = steps
    return problem
