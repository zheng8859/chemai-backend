"""化学式归一化器单元测试。"""

import pytest
from chem_skills.chemistry_parser.engine.chem_normalizer import (
    normalize_formulas,
    normalize_single_formula,
)


class TestNormalizeFormulas:
    """方程式归一化 — 完整方程式的 LaTeX/Unicode → ASCII 转换。"""

    def test_latex_wrapped(self):
        """$...$ 包裹的 LaTeX 方程式。"""
        assert normalize_formulas(
            "$2H_2 + O_2 \\rightarrow 2H_2O$"
        ) == "2H2 + O2 → 2H2O"

    def test_mhchem_wrapped(self):
        """\\ce{...} 包装。"""
        assert normalize_formulas(
            "$\\ce{2H2 + O2 -> 2H2O}$"
        ) == "2H2 + O2 → 2H2O"

    def test_unicode_subscripts(self):
        """Unicode 下标字符 → ASCII 数字。"""
        assert normalize_formulas("2H₂ + O₂ → 2H₂O") == "2H2 + O2 → 2H2O"

    def test_parentheses_with_unicode(self):
        """含括号 + Unicode 下标。"""
        assert normalize_formulas(
            "Ca(OH)₂ + CO₂ → CaCO₃ + H₂O"
        ) == "Ca(OH)2 + CO2 → CaCO3 + H2O"

    def test_reversible_arrow(self):
        """可逆反应箭头 \\rightleftharpoons → ⇌。"""
        r = normalize_formulas("$N_2 + 3H_2 \\rightleftharpoons 2NH_3$")
        assert "N2" in r
        assert "3H2" in r
        assert "⇌" in r
        assert "2NH3" in r

    def test_xrightarrow_stripped(self):
        """\\xrightarrow{条件} 剥离条件，保留 →。"""
        r = normalize_formulas(
            "$2KClO_3 \\xrightarrow{MnO_2} 2KCl + 3O_2$"
        )
        assert r == "2KClO3 → 2KCl + 3O2"

    def test_ionic_charge(self):
        """离子电荷上标正确转换。"""
        r = normalize_formulas(
            "$Fe^{3+} + 3OH^- \\rightarrow Fe(OH)_3$"
        )
        assert r == "Fe3+ + 3OH- → Fe(OH)3"

    def test_equal_sign_as_arrow(self):
        """= 号转换为 →。"""
        assert normalize_formulas("2H2 + O2 = 2H2O") == "2H2 + O2 → 2H2O"

    def test_ascii_arrow(self):
        """-> 转换为 →。"""
        assert normalize_formulas("2H2 + O2 -> 2H2O") == "2H2 + O2 → 2H2O"

    def test_iron_oxidation(self):
        """Fe + O2 → Fe2O3（未配平，仅测试归一化）。"""
        assert normalize_formulas("Fe + O₂ → Fe₂O₃") == "Fe + O2 → Fe2O3"

    def test_sodium_water(self):
        """Na + H2O 反应，含气体箭头。"""
        r = normalize_formulas("2Na + 2H₂O → 2NaOH + H₂↑")
        assert r == "2Na + 2H2O → 2NaOH + H2↑"

    def test_sulfate_ion(self):
        """SO₄²⁻ 离子完整转换。"""
        assert normalize_formulas("$SO_4^{2-}$") == "SO42-"

    def test_ammonia_synthesis(self):
        """工业合成氨，可逆。"""
        assert normalize_formulas("N₂ + 3H₂ ⇌ 2NH₃") == "N2 + 3H2 ⇌ 2NH3"

    def test_methane_combustion(self):
        """甲烷燃烧（含条件关键词）。"""
        r = normalize_formulas("CH₄ + 2O₂ → CO₂ + 2H₂O")
        assert r == "CH4 + 2O2 → CO2 + 2H2O"

    def test_complex_parentheses(self):
        """Ca(OH)₂ + CO₂ → CaCO₃ + H₂O"""
        assert normalize_formulas(
            "Ca(OH)₂ + CO₂ → CaCO₃ + H₂O"
        ) == "Ca(OH)2 + CO2 → CaCO3 + H2O"

    def test_empty_input(self):
        """空字符串返回空。"""
        assert normalize_formulas("") == ""
        assert normalize_formulas("   ") == ""


class TestNormalizeSingleFormula:
    """单个化学式归一化。"""

    def test_iron_oxide(self):
        assert normalize_single_formula("Fe_{2}O_{3}") == "Fe2O3"

    def test_calcium_hydroxide_unicode(self):
        assert normalize_single_formula("Ca(OH)₂") == "Ca(OH)2"

    def test_sulfuric_acid(self):
        assert normalize_single_formula("H_{2}SO_{4}") == "H2SO4"

    def test_ammonium(self):
        assert normalize_single_formula("NH₄⁺") == "NH4+"

    def test_nitrate(self):
        assert normalize_single_formula("NO₃⁻") == "NO3-"
