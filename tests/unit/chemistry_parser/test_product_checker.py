"""产物稳定性审核器单元测试 — 维度 3。"""

from chem_skills.chemistry_parser.engine.product_checker import check_product_stability
from chem_skills.chemistry_parser.engine.models import (
    PRODUCT_PASSED,
    PRODUCT_WARNING,
    PRODUCT_FAILED,
)


class TestStableProducts:
    """正常产物 → PASSED。"""

    def test_water(self):
        assert check_product_stability("2H2 + O2 → 2H2O").status == PRODUCT_PASSED

    def test_neutralization(self):
        assert check_product_stability("NaOH + HCl → NaCl + H2O").status == PRODUCT_PASSED

    def test_carbonate_correct(self):
        """正确写 CO2+H2O 而非 H2CO3。"""
        assert check_product_stability(
            "CaCO3 + 2HCl → CaCl2 + CO2 + H2O"
        ).status == PRODUCT_PASSED


class TestUnstableIntermediates:
    """不稳定中间产物 → FAILED。"""

    def test_h2co3(self):
        r = check_product_stability("CaCO3 + 2HCl → CaCl2 + H2CO3")
        assert r.status == PRODUCT_FAILED
        assert any("H2CO3" in i for i in r.issues)

    def test_h2so3(self):
        r = check_product_stability("Na2SO3 + 2HCl → 2NaCl + H2SO3")
        assert r.status == PRODUCT_FAILED
        assert any("H2SO3" in i for i in r.issues)

    def test_nh4oh(self):
        r = check_product_stability("NH3 + H2O → NH4OH")
        assert r.status == PRODUCT_FAILED
        assert any("NH4OH" in i for i in r.issues)


class TestEmpty:
    def test_empty(self):
        assert check_product_stability("").status == "error"
