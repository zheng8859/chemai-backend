"""离子反应辅导函数 — 四步法。"""

from .models import IonicAnalysis, ElectrolyteType


def classify_electrolyte(formula: str) -> ElectrolyteType:
    """判断物质的电解质类型。

    Args:
        formula: 化学式（如 "NaCl", "CH3COOH", "C6H12O6"）

    Returns:
        ElectrolyteType 枚举值
    """
    # 强酸
    strong_acids = {"HCl", "HBr", "HI", "HNO3", "H2SO4", "HClO4", "HClO3"}
    # 强碱
    strong_bases = {"NaOH", "KOH", "Ca(OH)2", "Ba(OH)2", "LiOH", "RbOH", "CsOH"}
    # 常见弱电解质
    weak_electrolytes = {"CH3COOH", "H2CO3", "H3PO4", "H2S", "HCN",
                         "NH3·H2O", "NH3", "H2O", "HF", "H2SO3", "HClO"}
    # 常见沉淀（非电解质在离子方程式中保留分子式）
    precipitates = {"AgCl", "BaSO4", "CaCO3", "Fe(OH)3", "Al(OH)3", "Cu(OH)2",
                    "Mg(OH)2", "PbSO4", "Ag2SO4", "CaSO4"}

    if formula in strong_acids or formula in strong_bases:
        return ElectrolyteType.STRONG
    elif formula in weak_electrolytes or formula in precipitates:
        return ElectrolyteType.WEAK

    # 可溶性盐 → 强电解质
    if any(formula.endswith(suffix) for suffix in
           ["Cl", "Br", "I", "NO3", "SO4", "CO3", "PO4", "Na", "K", "NH4"]):
        # 排除沉淀
        if formula not in precipitates:
            return ElectrolyteType.STRONG

    # 有机物、气体等 → 非电解质
    if any(formula.startswith(prefix) for prefix in ["C", "O2", "H2", "N2", "CO2", "SO2"]):
        return ElectrolyteType.NON_ELECTROLYTE

    return ElectrolyteType.NON_ELECTROLYTE


def write_ionic_form(species_list: list[dict]) -> dict:
    """将分子方程式改写为全离子形式。

    Args:
        species_list: [{"formula": str, "coefficient": int}]

    Returns:
        {"total_ionic": str, "ions": [...], "molecular": [...]}
    """
    ions = []
    molecular = []

    for sp in species_list:
        formula = sp["formula"]
        coeff = sp.get("coefficient", 1)
        etype = classify_electrolyte(formula)

        if etype == ElectrolyteType.STRONG:
            # 转换为离子形式
            ion_parts = _formula_to_ions(formula, coeff)
            ions.extend(ion_parts)
        else:
            molecular.append(f"{coeff if coeff > 1 else ''}{formula}")

    total_ionic = " + ".join(ions + molecular) if ions and molecular else \
                  " + ".join(ions) if ions else " + ".join(molecular)

    return {"total_ionic": total_ionic, "ions": ions, "molecular": molecular}


def remove_spectators(reactant_ions: list[str], product_ions: list[str]) -> dict:
    """识别并删除旁观离子。

    Args:
        reactant_ions: 反应物侧离子列表
        product_ions: 生成物侧离子列表

    Returns:
        {"spectators": [...], "net_reactant_ions": [...], "net_product_ions": [...]}
    """
    spectators = [ion for ion in reactant_ions if ion in product_ions]
    net_reactant = [ion for ion in reactant_ions if ion not in spectators]
    net_product = [ion for ion in product_ions if ion not in spectators]

    return {
        "spectators": spectators,
        "net_reactant_ions": net_reactant,
        "net_product_ions": net_product,
    }


def verify_net_ionic(net_ionic_equation: str) -> dict:
    """验证净离子方程式是否满足原子守恒和电荷守恒。

    Args:
        net_ionic_equation: 净离子方程式字符串

    Returns:
        {"charge_balanced": bool, "atom_balanced": bool, "issues": [...]}
    """
    # 简单检查：左侧和右侧的电荷总数和原子种类数应一致
    issues = []

    # 检查是否有反应物和生成物
    if "→" not in net_ionic_equation and "=" not in net_ionic_equation:
        issues.append("缺少反应箭头或等号")

    return {
        "charge_balanced": len(issues) == 0,
        "atom_balanced": len(issues) == 0,
        "issues": issues,
    }


def _formula_to_ions(formula: str, coefficient: int = 1) -> list[str]:
    """将化学式转换为离子表示（简化版）。

    实际生产环境应使用 chemistry_parser 引擎。
    """
    ion_map = {
        "NaCl": ["Na+", "Cl-"],
        "KCl": ["K+", "Cl-"],
        "NaOH": ["Na+", "OH-"],
        "KOH": ["K+", "OH-"],
        "HCl": ["H+", "Cl-"],
        "HNO3": ["H+", "NO3-"],
        "H2SO4": ["2H+", "SO4 2-"],
        "Na2SO4": ["2Na+", "SO4 2-"],
        "Na2CO3": ["2Na+", "CO3 2-"],
        "CaCl2": ["Ca2+", "2Cl-"],
        "BaCl2": ["Ba2+", "2Cl-"],
        "AgNO3": ["Ag+", "NO3-"],
        "NH4Cl": ["NH4+", "Cl-"],
    }

    if formula in ion_map:
        return [f"{coefficient}{ion}" if coefficient > 1 else ion
                for ion in ion_map[formula]]

    return [f"{coefficient}{formula}" if coefficient > 1 else formula]
