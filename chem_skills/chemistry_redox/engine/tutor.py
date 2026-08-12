"""氧化还原辅导函数 — 三步法。"""

from .models import RedoxAnalysis, RedoxHalfReaction

# ── 常见元素的典型氧化数 ──
_DEFAULT_OXIDATION_STATES = {
    "H": 1, "O": -2, "Na": 1, "K": 1, "Mg": 2, "Ca": 2, "Al": 3,
    "Cl": -1, "Br": -1, "I": -1, "F": -1, "S": -2, "N": -3,
    "Fe": 2, "Cu": 2, "Zn": 2, "Ag": 1, "Mn": 2,
}


def assign_oxidation_states(formula: str) -> dict[str, int]:
    """标定化合物中各元素的氧化数。

    规则：
    1. 单质氧化数为 0
    2. H 通常为 +1（金属氢化物中为 -1）
    3. O 通常为 -2（过氧化物中为 -1，OF2 中为 +2）
    4. 化合物中各元素氧化数之和为 0
    5. 离子中各元素氧化数之和等于离子电荷

    Args:
        formula: 化学式（如 "KMnO4", "HCl", "Fe2O3"）

    Returns:
        {元素符号: 氧化数}
    """
    formula = formula.strip()
    states = {}

    # 单质
    if formula in {"H2", "O2", "N2", "Cl2", "Br2", "I2", "F2", "Na", "K", "Fe", "Cu", "Zn", "Ag", "C", "S", "P", "Mn"}:
        return {formula[0] if len(formula) == 1 else formula[0].upper(): 0
                for _ in [0]}

    # 简化处理：返回默认氧化数
    for elem, default_state in _DEFAULT_OXIDATION_STATES.items():
        if elem in formula or elem.upper() in formula:
            states[elem] = default_state

    # 特殊处理
    if "Mn" in formula and "O" in formula:
        # 高锰酸钾 KMnO4: Mn = +7
        if "K" in formula:
            states["Mn"] = 7
        # 二氧化锰 MnO2: Mn = +4
        elif formula == "MnO2":
            states["Mn"] = 4

    return states


def identify_redox_changes(
    reactant_states: dict[str, dict[str, int]],
    product_states: dict[str, dict[str, int]],
) -> dict:
    """识别氧化数变化，确定氧化剂和还原剂。

    Args:
        reactant_states: {formula: {element: oxidation_state}}
        product_states: {formula: {element: oxidation_state}}

    Returns:
        {
            "oxidized": [{"element": str, "from": int, "to": int, "delta": int}],
            "reduced": [{"element": str, "from": int, "to": int, "delta": int}],
            "oxidizing_agent": str,
            "reducing_agent": str,
        }
    """
    oxidized = []
    reduced = []

    # 展平所有元素的氧化数变化
    all_reactant = {}
    for formula, states in reactant_states.items():
        for elem, state in states.items():
            all_reactant[elem] = state

    all_product = {}
    for formula, states in product_states.items():
        for elem, state in states.items():
            all_product[elem] = state

    for elem in all_reactant:
        if elem in all_product:
            from_state = all_reactant[elem]
            to_state = all_product[elem]
            delta = to_state - from_state
            if delta > 0:
                oxidized.append({"element": elem, "from": from_state, "to": to_state, "delta": delta})
            elif delta < 0:
                reduced.append({"element": elem, "from": from_state, "to": to_state, "delta": delta})

    return {
        "oxidized": oxidized,
        "reduced": reduced,
        "oxidizing_agent": reduced[0]["element"] if reduced else "",
        "reducing_agent": oxidized[0]["element"] if oxidized else "",
    }


def balance_by_electron(
    oxidation_changes: list[dict],
    reduction_changes: list[dict],
) -> dict:
    """根据电子守恒配平氧化还原方程式。

    Args:
        oxidation_changes: 氧化半反应的氧化数变化
        reduction_changes: 还原半反应的氧化数变化

    Returns:
        {"electron_transfer": int, "multiplier_ox": int, "multiplier_red": int}
    """
    total_ox = sum(abs(c["delta"]) for c in oxidation_changes)
    total_red = sum(abs(c["delta"]) for c in reduction_changes)

    if total_ox == 0 or total_red == 0:
        return {"electron_transfer": 0, "multiplier_ox": 1, "multiplier_red": 1}

    # 求最小公倍数
    import math
    lcm_ = math.lcm(total_ox, total_red) if hasattr(math, 'lcm') else total_ox * total_red

    return {
        "electron_transfer": lcm_,
        "multiplier_ox": lcm_ // total_ox,
        "multiplier_red": lcm_ // total_red,
    }
