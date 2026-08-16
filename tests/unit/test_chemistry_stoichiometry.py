"""化学计量辅导引擎单测 — 四步法（提已知量 / 选公式 / 建比例 / 逐步计算）。"""

from chem_skills.chemistry_stoichiometry.engine.models import (
    QuantityInfo,
    QuantityType,
    StoichiometryProblem,
)
from chem_skills.chemistry_stoichiometry.engine.tutor import (
    calculate_stepwise,
    extract_known_quantities,
    select_formula,
    setup_proportion,
)


class TestStoichiometryModels:
    def test_quantity_type_enum(self):
        assert QuantityType.MASS.value == "mass"
        assert QuantityType.MOLES.value == "moles"
        assert QuantityType.VOLUME.value == "volume"
        assert QuantityType.CONCENTRATION.value == "concentration"
        assert QuantityType.PARTICLES.value == "particles"

    def test_quantity_info(self):
        q = QuantityInfo(symbol="m", value=10.0, unit="g", type=QuantityType.MASS)
        assert q.symbol == "m"
        assert q.value == 10.0
        assert q.type == QuantityType.MASS

    def test_problem_defaults(self):
        p = StoichiometryProblem(equation="2H2 + O2 → 2H2O")
        assert p.known_quantities == []
        assert p.unknown_quantity is None
        assert p.molar_masses == {}
        assert p.solution_steps == []
        assert p.result is None


class TestExtractKnownQuantities:
    def test_mass_moles_volume(self):
        q = extract_known_quantities("10 g 铁与 5 mol 氧气反应生成 2 L 气体")
        types = {x.type for x in q}
        assert QuantityType.MASS in types
        assert QuantityType.MOLES in types
        assert QuantityType.VOLUME in types
        assert len(q) == 3

    def test_mass_only(self):
        q = extract_known_quantities("取 58.5 g NaCl")
        assert len(q) == 1
        assert q[0].type == QuantityType.MASS
        assert q[0].value == 58.5
        assert q[0].unit == "g"


class TestSelectFormula:
    def test_mass_to_moles(self):
        known = QuantityInfo(symbol="m", value=36.5, unit="g", type=QuantityType.MASS)
        r = select_formula(known, QuantityType.MOLES)
        assert r["formula"] == "n = m / M"

    def test_moles_to_mass(self):
        known = QuantityInfo(symbol="n", value=1.0, unit="mol", type=QuantityType.MOLES)
        r = select_formula(known, QuantityType.MASS)
        assert r["formula"] == "m = n × M"

    def test_volume_to_moles(self):
        known = QuantityInfo(symbol="V", value=22.4, unit="L", type=QuantityType.VOLUME)
        r = select_formula(known, QuantityType.MOLES)
        assert r["formula"] == "n = V / Vm"

    def test_same_type_direct(self):
        known = QuantityInfo(symbol="n", value=1.0, unit="mol", type=QuantityType.MOLES)
        r = select_formula(known, QuantityType.MOLES)
        assert r["formula"] == "direct"

    def test_fallback_two_step(self):
        known = QuantityInfo(symbol="c", value=1.0, unit="mol/L", type=QuantityType.CONCENTRATION)
        r = select_formula(known, QuantityType.MASS)
        assert r["formula"] == "two_step"


class TestSetupProportion:
    def test_one_to_one(self):
        r = setup_proportion(known_moles=2.0, known_coefficient=1, unknown_coefficient=1)
        assert r["ratio"] == "1 : 1"
        assert r["unknown_moles"] == 2.0

    def test_non_trivial_ratio(self):
        r = setup_proportion(known_moles=2.0, known_coefficient=2, unknown_coefficient=1)
        assert r["ratio"] == "1 : 2"
        assert r["unknown_moles"] == 1.0

    def test_zero_coefficient(self):
        r = setup_proportion(known_moles=2.0, known_coefficient=0, unknown_coefficient=1)
        assert r["ratio"] == "N/A"
        assert r["unknown_moles"] == 0


class TestCalculateStepwise:
    def test_mass_to_moles_steps(self):
        problem = StoichiometryProblem(
            equation="2H2 + O2 → 2H2O",
            known_quantities=[
                QuantityInfo(symbol="m", value=36.5, unit="g", type=QuantityType.MASS),
            ],
            unknown_quantity=QuantityInfo(
                symbol="n", value=None, unit="mol", type=QuantityType.MOLES,
            ),
        )
        result = calculate_stepwise(problem)
        assert result is problem
        assert len(result.solution_steps) == 2
        assert "物质的量" in result.solution_steps[0]

    def test_moles_known_no_conversion(self):
        problem = StoichiometryProblem(
            equation="H2 + Cl2 → 2HCl",
            known_quantities=[
                QuantityInfo(symbol="n", value=2.0, unit="mol", type=QuantityType.MOLES),
            ],
            unknown_quantity=QuantityInfo(
                symbol="m", value=None, unit="g", type=QuantityType.MASS,
            ),
        )
        result = calculate_stepwise(problem)
        assert len(result.solution_steps) == 2
