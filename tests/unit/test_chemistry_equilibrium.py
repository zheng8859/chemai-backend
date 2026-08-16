"""化学平衡辅导引擎单测 — ICE 三段式 + 勒夏特列原理。"""

from chem_skills.chemistry_equilibrium.engine.models import (
    EquilibriumTable,
    ICERow,
)
from chem_skills.chemistry_equilibrium.engine.tutor import (
    apply_le_chatelier,
    build_ice_table,
)


class TestEquilibriumModels:
    def test_ice_row(self):
        row = ICERow(species="N2", initial=0.1, change="-x", equilibrium="0.1 - x")
        assert row.species == "N2"
        assert row.initial == 0.1
        assert row.change == "-x"

    def test_table_defaults(self):
        t = EquilibriumTable(equation="N2 + 3H2 ⇌ 2NH3")
        assert t.rows == []
        assert t.k_expression == ""
        assert t.k_value is None
        assert t.solved_x is None


class TestBuildIceTable:
    def test_reactant_and_product_rows(self):
        table = build_ice_table(
            equation="N2 + 3H2 ⇌ 2NH3",
            species=["N2", "H2", "NH3"],
            initial_concentrations=[0.1, 0.3, 0.0],
            stoichiometry=[-1, -3, 2],
        )
        assert table.equation == "N2 + 3H2 ⇌ 2NH3"
        assert len(table.rows) == 3

        n2 = table.rows[0]
        assert n2.species == "N2"
        assert n2.initial == 0.1
        assert n2.change == "-1x"
        assert n2.equilibrium == "0.1 + -1x"

        nh3 = table.rows[2]
        assert nh3.species == "NH3"
        assert nh3.change == "+2x"
        # 初始浓度为 0 → equilibrium 只保留 change 表达式
        assert nh3.equilibrium == "+2x"


class TestApplyLeChatelier:
    def test_concentration_add_reactant(self):
        r = apply_le_chatelier("concentration", "add_reactant")
        assert r["shift_direction"] == "right"

    def test_concentration_remove_product(self):
        r = apply_le_chatelier("concentration", "remove_product")
        assert r["shift_direction"] == "right"

    def test_pressure_increase(self):
        r = apply_le_chatelier("pressure", "increase")
        assert r["shift_direction"] == "fewer_moles"

    def test_temperature_increase_exothermic(self):
        r = apply_le_chatelier("temperature", "increase", reaction_type="exothermic")
        assert r["shift_direction"] == "left"

    def test_temperature_decrease_endothermic(self):
        r = apply_le_chatelier("temperature", "decrease", reaction_type="endothermic")
        assert r["shift_direction"] == "left"

    def test_catalyst_no_shift(self):
        r = apply_le_chatelier("catalyst", "add")
        assert r["shift_direction"] == "none"

    def test_unknown_stress(self):
        r = apply_le_chatelier("magnetic_field", "increase")
        assert r["shift_direction"] == "unknown"
