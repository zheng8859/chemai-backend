"""分子结构审核器单元测试 — 维度 4。"""

from chem_skills.chemistry_parser.engine.structure_checker import check_structure
from chem_skills.chemistry_parser.engine.models import STRUCTURE_PASSED, STRUCTURE_FAILED


class TestValidStructure:
    def test_simple(self):
        assert check_structure("2H2 + O2 → 2H2O").status == STRUCTURE_PASSED

    def test_complex(self):
        assert check_structure("Ca(OH)2 + CO2 → CaCO3 + H2O").status == STRUCTURE_PASSED


class TestBracketErrors:
    def test_unmatched_open(self):
        r = check_structure("Ca(OH)2 + CO2 → CaCO3 + H2O(")
        assert r.status == STRUCTURE_FAILED
        assert any("未闭合" in i for i in r.issues)

    def test_unmatched_close(self):
        r = check_structure("Ca(OH)2 + CO2 → CaCO3 + H2O)")
        assert r.status == STRUCTURE_FAILED
        assert any("多余" in i for i in r.issues)


class TestEmpty:
    def test_empty(self):
        assert check_structure("").status == "error"
