"""化学式元素计数器单元测试。"""

import pytest
from chem_skills.chemistry_parser.engine.formula_counter import count_elements


class TestCountElements:
    """count_elements() — 中性化学式元素计数。"""

    def test_water(self):
        assert count_elements("H2O") == {"H": 2, "O": 1}

    def test_with_coefficient(self):
        assert count_elements("2H2O") == {"H": 4, "O": 2}

    def test_simple_parentheses(self):
        assert count_elements("Ca(OH)2") == {"Ca": 1, "O": 2, "H": 2}

    def test_complex_parentheses(self):
        assert count_elements("Fe2(SO4)3") == {"Fe": 2, "S": 3, "O": 12}

    def test_diatomic(self):
        assert count_elements("O2") == {"O": 2}

    def test_single_atom(self):
        assert count_elements("Fe") == {"Fe": 1}

    def test_pure_coefficient(self):
        assert count_elements("3Fe") == {"Fe": 3}

    def test_co2(self):
        assert count_elements("CO2") == {"C": 1, "O": 2}

    def test_sulfuric_acid(self):
        assert count_elements("H2SO4") == {"H": 2, "S": 1, "O": 4}

    def test_kmno4(self):
        assert count_elements("KMnO4") == {"K": 1, "Mn": 1, "O": 4}

    def test_aluminum_sulfate(self):
        assert count_elements("Al2(SO4)3") == {"Al": 2, "S": 3, "O": 12}

    def test_ammonium_sulfate(self):
        assert count_elements("(NH4)2SO4") == {"N": 2, "H": 8, "S": 1, "O": 4}

    def test_iron_oxide(self):
        assert count_elements("Fe2O3") == {"Fe": 2, "O": 3}


class TestCountElementsWithCharge:
    """含电荷标注的化学式计数。"""

    def test_fe3_charge(self):
        assert count_elements("Fe3+") == {"Fe": 1}

    def test_so4_charge(self):
        assert count_elements("SO42-") == {"S": 1, "O": 4}

    def test_nh4_charge(self):
        assert count_elements("NH4+") == {"N": 1, "H": 4}

    def test_oh_charge(self):
        assert count_elements("OH-") == {"O": 1, "H": 1}

    def test_fe2_charge(self):
        assert count_elements("Fe2+") == {"Fe": 1}

    def test_al3_charge(self):
        assert count_elements("Al3+") == {"Al": 1}

    def test_complex_ion_charge(self):
        """[Cu(NH3)4]2+ 络离子。"""
        assert count_elements("[Cu(NH3)4]2+") == {"Cu": 1, "N": 4, "H": 12}

    def test_coefficient_with_charge(self):
        """3OH- → 3 个氢氧根。"""
        r = count_elements("3OH-")
        assert r == {"O": 3, "H": 3}


class TestEmpty:
    def test_empty(self):
        assert count_elements("") == {}

    def test_none(self):
        assert count_elements("") == {}
