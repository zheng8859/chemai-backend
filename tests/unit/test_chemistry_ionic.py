"""离子反应辅导引擎单测 — 四步法（电解质分类 / 写离子式 / 去旁观离子 / 守恒验证）。"""

from chem_skills.chemistry_ionic.engine.models import ElectrolyteType, IonicAnalysis
from chem_skills.chemistry_ionic.engine.tutor import (
    classify_electrolyte,
    remove_spectators,
    verify_net_ionic,
    write_ionic_form,
)


class TestIonicModels:
    def test_electrolyte_type_enum(self):
        assert ElectrolyteType.STRONG.value == "strong"
        assert ElectrolyteType.WEAK.value == "weak"
        assert ElectrolyteType.NON_ELECTROLYTE.value == "non"

    def test_analysis_defaults(self):
        a = IonicAnalysis(molecular_equation="NaCl + AgNO3 → AgCl↓ + NaNO3")
        assert a.species == []
        assert a.total_ionic == ""
        assert a.spectators == []
        assert a.net_ionic == ""
        assert a.charge_balanced is False
        assert a.atom_balanced is False


class TestClassifyElectrolyte:
    def test_strong_acid_base(self):
        assert classify_electrolyte("HCl") == ElectrolyteType.STRONG
        assert classify_electrolyte("NaOH") == ElectrolyteType.STRONG

    def test_weak_electrolyte(self):
        assert classify_electrolyte("CH3COOH") == ElectrolyteType.WEAK
        assert classify_electrolyte("H2O") == ElectrolyteType.WEAK

    def test_precipitate_treated_as_weak(self):
        assert classify_electrolyte("AgCl") == ElectrolyteType.WEAK

    def test_soluble_salt_strong(self):
        assert classify_electrolyte("NaCl") == ElectrolyteType.STRONG
        assert classify_electrolyte("NaNO3") == ElectrolyteType.STRONG

    def test_organic_non_electrolyte(self):
        assert classify_electrolyte("C6H12O6") == ElectrolyteType.NON_ELECTROLYTE
        assert classify_electrolyte("CO2") == ElectrolyteType.NON_ELECTROLYTE


class TestWriteIonicForm:
    def test_strong_salts_fully_ionized(self):
        result = write_ionic_form([
            {"formula": "NaCl", "coefficient": 1},
            {"formula": "AgNO3", "coefficient": 1},
        ])
        assert "Na+" in result["ions"]
        assert "Cl-" in result["ions"]
        assert "Ag+" in result["ions"]
        assert "NO3-" in result["ions"]
        assert result["molecular"] == []

    def test_precipitate_kept_molecular(self):
        result = write_ionic_form([{"formula": "AgCl", "coefficient": 1}])
        assert result["ions"] == []
        assert result["molecular"] == ["AgCl"]

    def test_coefficient_multiplies_ions(self):
        result = write_ionic_form([{"formula": "NaCl", "coefficient": 2}])
        assert "2Na+" in result["ions"]
        assert "2Cl-" in result["ions"]


class TestRemoveSpectators:
    def test_spectators_identified(self):
        result = remove_spectators(
            ["Na+", "Cl-", "Ag+", "NO3-"],
            ["Na+", "NO3-", "AgCl"],
        )
        assert set(result["spectators"]) == {"Na+", "NO3-"}
        assert set(result["net_reactant_ions"]) == {"Cl-", "Ag+"}
        assert result["net_product_ions"] == ["AgCl"]

    def test_no_spectators(self):
        result = remove_spectators(["Ag+", "Cl-"], ["AgCl"])
        assert result["spectators"] == []
        assert result["net_reactant_ions"] == ["Ag+", "Cl-"]


class TestVerifyNetIonic:
    def test_with_arrow_balanced(self):
        result = verify_net_ionic("Ag+ + Cl- → AgCl↓")
        assert result["charge_balanced"] is True
        assert result["atom_balanced"] is True
        assert result["issues"] == []

    def test_missing_arrow(self):
        result = verify_net_ionic("Ag+ + Cl- AgCl")
        assert result["charge_balanced"] is False
        assert result["atom_balanced"] is False
        assert any("箭头" in i for i in result["issues"])
