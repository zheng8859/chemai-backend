"""化学平衡辅导函数 — 三段式表格与勒夏特列原理。"""

from .models import EquilibriumTable, ICERow


def build_ice_table(
    equation: str,
    species: list[str],
    initial_concentrations: list[float],
    stoichiometry: list[int],
) -> EquilibriumTable:
    """构建 ICE 三段式表格。

    Args:
        equation: 配平的化学方程式（如 "N2 + 3H2 ⇌ 2NH3"）
        species: 物种列表（按方程式顺序）
        initial_concentrations: 初始浓度列表 (mol/L)
        stoichiometry: 化学计量系数列表（反应物为负，生成物为正）

    Returns:
        EquilibriumTable 对象
    """
    rows = []
    for i, sp in enumerate(species):
        coeff = stoichiometry[i]
        change_str = f"+{coeff}x" if coeff > 0 else f"{coeff}x"
        equil_str = f"{initial_concentrations[i]} + {change_str}" if initial_concentrations[i] > 0 else change_str
        rows.append(ICERow(
            species=sp,
            initial=initial_concentrations[i],
            change=change_str,
            equilibrium=equil_str,
        ))

    return EquilibriumTable(equation=equation, rows=rows)


def apply_le_chatelier(
    stress_type: str,
    stress_detail: str,
    reaction_type: str = "exothermic",
) -> dict:
    """应用勒夏特列原理分析平衡移动方向。

    Args:
        stress_type: 扰动类型（concentration/pressure/temperature/catalyst）
        stress_detail: 扰动详情
        reaction_type: 反应热类型（exothermic/endothermic）

    Returns:
        {"shift_direction": str, "reasoning": str, "affected_species": [...]}
    """
    shifts = {
        "concentration": {
            "add_reactant": "right",
            "add_product": "left",
            "remove_reactant": "left",
            "remove_product": "right",
        },
        "pressure": {
            "increase": "fewer_moles",  # 向气体分子数减少方向移动
            "decrease": "more_moles",   # 向气体分子数增加方向移动
        },
        "temperature": {
            "increase": "left" if reaction_type == "exothermic" else "right",
            "decrease": "right" if reaction_type == "exothermic" else "left",
        },
        "catalyst": {
            "add": "none",  # 催化剂不改变平衡位置
        },
    }

    direction = "unknown"
    reasoning = ""

    if stress_type in shifts:
        direction_map = shifts[stress_type]
        if isinstance(direction_map, dict):
            for key, val in direction_map.items():
                if key in stress_detail.lower():
                    direction = val
                    break

    return {
        "shift_direction": direction,
        "reasoning": f"施加{stress_type}扰动（{stress_detail}），平衡向{direction}移动",
        "affected_species": [],
    }
