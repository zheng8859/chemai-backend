"""配平检查器单元测试 — 维度 1：系数配平审核。"""

import pytest
from chem_skills.chemistry_parser.engine.balance_checker import check_balance
from chem_skills.chemistry_parser.engine.models import (
    BALANCE_PASSED,
    BALANCE_BLOCKED,
    BALANCE_ERROR,
)


class TestBalancedEquations:
    """配平正确的方程式 → PASSED。"""

    def test_water_synthesis(self):
        r = check_balance("2H2 + O2 → 2H2O")
        assert r.status == BALANCE_PASSED
        assert r.detail.left_elements == {"H": 4, "O": 2}
        assert r.detail.right_elements == {"H": 4, "O": 2}

    def test_carbonate_decomposition(self):
        r = check_balance("CaCO3 → CaO + CO2")
        assert r.status == BALANCE_PASSED

    def test_ammonia_synthesis(self):
        r = check_balance("N2 + 3H2 → 2NH3")
        assert r.status == BALANCE_PASSED

    def test_reversible(self):
        r = check_balance("N2 + 3H2 ⇌ 2NH3")
        assert r.status == BALANCE_PASSED

    def test_iron_combustion_balanced(self):
        r = check_balance("4Fe + 3O2 → 2Fe2O3")
        assert r.status == BALANCE_PASSED

    def test_methane_combustion(self):
        r = check_balance("CH4 + 2O2 → CO2 + 2H2O")
        assert r.status == BALANCE_PASSED

    def test_carbonate_with_hydroxide(self):
        r = check_balance("Ca(OH)2 + CO2 → CaCO3 + H2O")
        assert r.status == BALANCE_PASSED

    def test_sodium_water_balanced(self):
        r = check_balance("2Na + 2H2O → 2NaOH + H2")
        assert r.status == BALANCE_PASSED

    def test_kclo3_decomposition(self):
        r = check_balance("2KClO3 → 2KCl + 3O2")
        assert r.status == BALANCE_PASSED

    def test_sulfuric_acid_neutralization(self):
        r = check_balance("H2SO4 + 2NaOH → Na2SO4 + 2H2O")
        assert r.status == BALANCE_PASSED

    def test_complex_ion_reaction(self):
        r = check_balance("[Cu(NH3)4]2+ + 2OH- → Cu(OH)2 + 4NH3")
        assert r.status == BALANCE_PASSED

    def test_ionic_reaction(self):
        r = check_balance("Fe3+ + 3OH- → Fe(OH)3")
        assert r.status == BALANCE_PASSED


class TestUnbalancedEquations:
    """配平错误的方程式 → BLOCKED。"""

    def test_iron_oxidation_unbalanced(self):
        r = check_balance("Fe + O2 → Fe2O3")
        assert r.status == BALANCE_BLOCKED
        assert r.detail.left_elements == {"Fe": 1, "O": 2}
        assert r.detail.right_elements == {"Fe": 2, "O": 3}
        assert "Fe" in r.message
        assert "O" in r.message

    def test_sodium_water_unbalanced(self):
        r = check_balance("Na + H2O → NaOH + H2")
        assert r.status == BALANCE_BLOCKED
        assert r.detail.left_elements == {"H": 2, "Na": 1, "O": 1}
        assert r.detail.right_elements == {"H": 3, "Na": 1, "O": 1}

    def test_message_contains_element_diff(self):
        r = check_balance("H2 + O2 → H2O")
        assert r.status == BALANCE_BLOCKED
        assert "O" in r.message


class TestErrorEquations:
    """无法解析的方程式 → ERROR。"""

    def test_plain_text(self):
        r = check_balance("not an equation")
        assert r.status == BALANCE_ERROR

    def test_empty(self):
        r = check_balance("")
        assert r.status == BALANCE_ERROR

    def test_only_reactants(self):
        r = check_balance("H2 + O2")
        assert r.status == BALANCE_ERROR


class TestLaTeXInput:
    """LaTeX 格式输入（自动归一化后审核）。"""

    def test_latex_balanced(self):
        r = check_balance(r"$2H_2 + O_2 \rightarrow 2H_2O$")
        assert r.status == BALANCE_PASSED

    def test_latex_unbalanced(self):
        r = check_balance(r"$Fe + O_2 \rightarrow Fe_2O_3$")
        assert r.status == BALANCE_BLOCKED

    def test_xrightarrow(self):
        r = check_balance(
            r"$2KClO_3 \xrightarrow{MnO_2} 2KCl + 3O_2$"
        )
        assert r.status == BALANCE_PASSED
