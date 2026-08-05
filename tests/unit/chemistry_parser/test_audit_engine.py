"""四维审核引擎端到端测试。"""

import pytest
from chem_skills.chemistry_parser.engine.audit_engine import audit_equation


class TestEndToEnd:
    """综合四维审核 → AuditReport。"""

    def test_perfect_equation(self):
        r = audit_equation("2H2 + O2 → 2H2O", question_id="q_001")
        assert r.overall_status == "passed"
        assert r.balance.status == "passed"
        assert r.condition.status == "passed"
        assert r.product.status == "passed"
        assert r.structure.status == "passed"

    def test_unbalanced_blocked(self):
        r = audit_equation("Fe + O2 → Fe2O3")
        assert r.overall_status == "blocked"
        assert r.balance.status == "blocked"

    def test_combustion_no_condition(self):
        """条件缺失不阻断输出（仅配平错误是红线）。"""
        r = audit_equation("CH4 + 2O2 → CO2 + 2H2O")
        assert r.overall_status == "passed"
        assert r.condition.status == "failed"

    def test_unstable_product(self):
        """产物问题不阻断输出（仅配平错误是红线）。"""
        r = audit_equation("CaCO3 + 2HCl → CaCl2 + H2CO3")
        assert r.overall_status == "passed"
        assert r.product.status == "failed"

    def test_latex_input(self):
        r = audit_equation(r"$2H_2 + O_2 \rightarrow 2H_2O$")
        assert r.overall_status == "passed"

    def test_invalid_input(self):
        r = audit_equation("not an equation")
        assert r.overall_status == "error"

    def test_question_id_preserved(self):
        r = audit_equation("2H2 + O2 → 2H2O", question_id="q_test_123")
        assert r.question_id == "q_test_123"

    def test_report_has_all_dimensions(self):
        r = audit_equation("2H2 + O2 → 2H2O")
        assert r.balance is not None
        assert r.condition is not None
        assert r.product is not None
        assert r.structure is not None
