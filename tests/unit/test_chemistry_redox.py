"""氧化还原辅导引擎单测 — 三步法（标氧化数 / 识别变化 / 电子守恒配平）。"""

from chem_skills.chemistry_redox.engine.models import (
    RedoxAnalysis,
    RedoxHalfReaction,
)
from chem_skills.chemistry_redox.engine.tutor import (
    assign_oxidation_states,
    balance_by_electron,
    identify_redox_changes,
)


class TestRedoxModels:
    def test_half_reaction_instantiation(self):
        hr = RedoxHalfReaction(
            type="oxidation", equation="Fe - 3e- → Fe3+",
            electron_count=3, element="Fe",
        )
        assert hr.type == "oxidation"
        assert hr.electron_count == 3
        assert hr.element == "Fe"

    def test_analysis_defaults(self):
        a = RedoxAnalysis(equation="4Fe + 3O2 → 2Fe2O3")
        assert a.oxidation_states == {}
        assert a.oxidation_half is None
        assert a.reduction_half is None
        assert a.electron_transfer == 0
        assert a.balanced_equation == ""


class TestAssignOxidationStates:
    def test_elemental_substance_zero(self):
        assert assign_oxidation_states("H2") == {"H": 0}
        assert assign_oxidation_states("O2") == {"O": 0}
        assert assign_oxidation_states("Fe") == {"F": 0}

    def test_hydrochloric_acid(self):
        states = assign_oxidation_states("HCl")
        assert states["H"] == 1
        assert states["Cl"] == -1

    def test_iron_oxide(self):
        states = assign_oxidation_states("Fe2O3")
        assert states["Fe"] == 2
        assert states["O"] == -2

    def test_kmno4_manganese_seven(self):
        states = assign_oxidation_states("KMnO4")
        assert states["Mn"] == 7
        assert states["K"] == 1
        assert states["O"] == -2

    def test_mno2_manganese_four(self):
        states = assign_oxidation_states("MnO2")
        assert states["Mn"] == 4
        assert states["O"] == -2


class TestIdentifyRedoxChanges:
    def test_iron_oxidizes_oxygen_reduces(self):
        result = identify_redox_changes(
            {"Fe": {"Fe": 0}, "O2": {"O": 0}},
            {"Fe2O3": {"Fe": 3, "O": -2}},
        )
        assert result["oxidized"] == [{"element": "Fe", "from": 0, "to": 3, "delta": 3}]
        assert result["reduced"] == [{"element": "O", "from": 0, "to": -2, "delta": -2}]
        assert result["oxidizing_agent"] == "O"
        assert result["reducing_agent"] == "Fe"

    def test_no_change(self):
        result = identify_redox_changes(
            {"Na": {"Na": 1}},
            {"Na": {"Na": 1}},
        )
        assert result["oxidized"] == []
        assert result["reduced"] == []
        assert result["oxidizing_agent"] == ""
        assert result["reducing_agent"] == ""


class TestBalanceByElectron:
    def test_fe_o2_lcm(self):
        result = balance_by_electron(
            [{"delta": 3}],
            [{"delta": -2}],
        )
        assert result["electron_transfer"] == 6
        assert result["multiplier_ox"] == 2
        assert result["multiplier_red"] == 3

    def test_zero_transfer_fallback(self):
        result = balance_by_electron([{"delta": 0}], [{"delta": -2}])
        assert result["electron_transfer"] == 0
        assert result["multiplier_ox"] == 1
        assert result["multiplier_red"] == 1
