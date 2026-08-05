"""方程式解析器单元测试。"""

import pytest
from chem_skills.chemistry_parser.engine.equation_parser import (
    parse_equation,
    extract_equations,
)


class TestParseEquation:
    """parse_equation() — 拆分反应物/产物/分隔符。"""

    def test_simple(self):
        p = parse_equation("2H2 + O2 → 2H2O")
        assert p.reactants == ["2H2", "O2"]
        assert p.products == ["2H2O"]
        assert p.separator == "→"

    def test_latex_input_normalized(self):
        """LaTeX 输入自动归一化后解析。"""
        p = parse_equation(r"$2H_2 + O_2 \rightarrow 2H_2O$")
        assert p.reactants == ["2H2", "O2"]
        assert p.products == ["2H2O"]

    def test_parentheses_preserved(self):
        """括号保护的 + 号不被拆分。"""
        p = parse_equation("Ca(OH)2 + CO2 → CaCO3 + H2O")
        assert p.reactants == ["Ca(OH)2", "CO2"]
        assert p.products == ["CaCO3", "H2O"]

    def test_reversible(self):
        """可逆反应。"""
        p = parse_equation("N2 + 3H2 ⇌ 2NH3")
        assert p.separator == "⇌"
        assert p.products == ["2NH3"]

    def test_complex_ion(self):
        """络离子 [Cu(NH3)4]2+ 中的括号不误拆。"""
        p = parse_equation("[Cu(NH3)4]2+ + 2OH- → Cu(OH)2 + 4NH3")
        assert "[Cu(NH3)4]2+" in p.reactants
        assert "2OH-" in p.reactants

    def test_unicode_auto_normalized(self):
        """Unicode 下标自动转为 ASCII 后解析。"""
        p = parse_equation("2H₂ + O₂ → 2H₂O")
        assert p.reactants == ["2H2", "O2"]

    def test_original_preserved(self):
        """original 保留原始输入（含 Unicode）。"""
        p = parse_equation("2H₂ + O₂ → 2H₂O")
        assert "₂" in p.original

    def test_xrightarrow_stripped(self):
        """\\xrightarrow 条件被归一化剥离后解析。"""
        p = parse_equation(r"$2KClO_3 \xrightarrow{MnO_2} 2KCl + 3O_2$")
        assert p.reactants == ["2KClO3"]
        assert p.products == ["2KCl", "3O2"]

    def test_iron_oxidation(self):
        p = parse_equation("Fe + O2 → Fe2O3")
        assert p.reactants == ["Fe", "O2"]
        assert p.products == ["Fe2O3"]

    def test_equal_sign(self):
        """= 号作为分隔符。"""
        p = parse_equation("2H2 + O2 = 2H2O")
        assert p.separator == "→"  # 归一化后 = → →
        assert p.reactants == ["2H2", "O2"]

    def test_single_reactant(self):
        """只有一个反应物的分解反应。"""
        p = parse_equation("CaCO3 → CaO + CO2")
        assert p.reactants == ["CaCO3"]
        assert len(p.products) == 2

    def test_single_product(self):
        """只有一个产物的化合反应。"""
        p = parse_equation("2H2 + O2 → 2H2O")
        assert len(p.reactants) == 2
        assert p.products == ["2H2O"]

    def test_multiple_compounds(self):
        """多化合物反应。"""
        p = parse_equation("2Na + 2H2O → 2NaOH + H2")
        assert len(p.reactants) == 2
        assert len(p.products) == 2
        assert "H2" in p.products

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            parse_equation("")

    def test_no_separator_raises(self):
        with pytest.raises(ValueError):
            parse_equation("just some text without arrow")

    def test_empty_reactants_raises(self):
        with pytest.raises(ValueError):
            parse_equation(" → H2O")

    def test_empty_products_raises(self):
        with pytest.raises(ValueError):
            parse_equation("H2 + O2 → ")


class TestExtractEquations:
    """extract_equations() — 从文本中提取方程式。"""

    def test_extract_from_text(self):
        text = "CH4 + 2O2 → CO2 + 2H2O and 2H2 + O2 → 2H2O"
        eqs = extract_equations(text)
        assert len(eqs) >= 2

    def test_extract_latex_equations(self):
        text = r"The reaction is $2H_2 + O_2 \rightarrow 2H_2O$ in textbooks."
        eqs = extract_equations(text)
        assert len(eqs) >= 1

    def test_no_equation_returns_empty(self):
        eqs = extract_equations("This text has no chemical equation.")
        assert eqs == []

    def test_extract_deduplicates(self):
        text = "2H2 + O2 → 2H2O and again 2H2 + O2 → 2H2O"
        eqs = extract_equations(text)
        # 不应有重复
        assert len(eqs) == len(set(eqs))
