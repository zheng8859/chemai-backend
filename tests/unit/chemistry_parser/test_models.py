"""四维审核引擎 models.py 单元测试。"""

import pytest
from chem_skills.chemistry_parser.engine.models import (
    EquationParts,
    BalanceDetail,
    BalanceResult,
    ConditionResult,
    ProductResult,
    StructureResult,
    AuditReport,
    BALANCE_PASSED,
    BALANCE_BLOCKED,
    BALANCE_UNCERTAIN,
    BALANCE_ERROR,
    CONDITION_PASSED,
    CONDITION_WARNING,
    CONDITION_FAILED,
    CONDITION_UNCERTAIN,
    PRODUCT_PASSED,
    PRODUCT_WARNING,
    PRODUCT_FAILED,
    STRUCTURE_PASSED,
    STRUCTURE_FAILED,
    OVERALL_PASSED,
    OVERALL_BLOCKED,
    OVERALL_UNCERTAIN,
    OVERALL_ERROR,
)


class TestEquationParts:
    def test_basic(self):
        parts = EquationParts(
            original="2H2 + O2 = 2H2O",
            normalized="2H2 + O2 → 2H2O",
            reactants=["2H2", "O2"],
            products=["2H2O"],
        )
        assert parts.reactants == ["2H2", "O2"]
        assert len(parts.products) == 1
        assert parts.separator == "→"

    def test_default_separator(self):
        parts = EquationParts(
            original="A+B=C", normalized="A+B→C",
            reactants=["A", "B"], products=["C"],
        )
        assert parts.separator == "→"


class TestBalanceResult:
    def test_is_balanced_true(self):
        r = BalanceResult(status=BALANCE_PASSED)
        assert r.is_balanced() is True

    def test_is_balanced_false(self):
        r = BalanceResult(status=BALANCE_BLOCKED)
        assert r.is_balanced() is False

    def test_detail(self):
        detail = BalanceDetail(
            left_elements={"H": 4, "O": 2},
            right_elements={"H": 4, "O": 2},
        )
        assert detail.left_elements["H"] == 4
        assert detail.right_elements["O"] == 2


class TestAuditReportOverall:
    """综合判定逻辑：blocked > failed > uncertain > warning > passed。"""

    def _make_report(self, balance_status=BALANCE_PASSED, cond_status=CONDITION_PASSED,
                     prod_status=PRODUCT_PASSED, struct_status=STRUCTURE_PASSED):
        return AuditReport(
            question_id="q_test",
            equation="TEST",
            balance=BalanceResult(status=balance_status, message="" if balance_status == BALANCE_PASSED else "err"),
            condition=ConditionResult(status=cond_status, message="" if cond_status == CONDITION_PASSED else "err"),
            product=ProductResult(status=prod_status, message="" if prod_status == PRODUCT_PASSED else "err"),
            structure=StructureResult(status=struct_status, message="" if struct_status == STRUCTURE_PASSED else "err"),
        )

    def test_all_passed(self):
        r = self._make_report()
        assert r.compute_overall() == OVERALL_PASSED

    def test_balance_blocked(self):
        r = self._make_report(balance_status=BALANCE_BLOCKED)
        assert r.compute_overall() == OVERALL_BLOCKED

    def test_condition_failed_not_blocked(self):
        """条件 failed 不阻断输出（仅配平 blocked 是红线）。"""
        r = self._make_report(cond_status=CONDITION_FAILED)
        assert r.compute_overall() == OVERALL_PASSED

    def test_product_failed_not_blocked(self):
        """产物 failed 不阻断输出。"""
        r = self._make_report(prod_status=PRODUCT_FAILED)
        assert r.compute_overall() == OVERALL_PASSED

    def test_balance_uncertain_not_blocked(self):
        """uncertain 不阻断，传递为 uncertain。"""
        r = self._make_report(balance_status=BALANCE_UNCERTAIN)
        assert r.compute_overall() == OVERALL_UNCERTAIN

    def test_condition_warning_not_blocked(self):
        """warning 不阻断，仍为 passed。"""
        r = self._make_report(cond_status=CONDITION_WARNING)
        assert r.compute_overall() == OVERALL_PASSED

    def test_balance_error(self):
        r = self._make_report(balance_status=BALANCE_ERROR)
        assert r.compute_overall() == OVERALL_ERROR

    def test_overall_message_has_blocked_first(self):
        """blocked 消息排在 overall_message 最前面。"""
        r = self._make_report(
            balance_status=BALANCE_BLOCKED,
            cond_status=CONDITION_WARNING,
        )
        r.compute_overall()
        assert "配平" in r.overall_message
        # blocked 的配平消息应在 warning 的条件消息之前
        assert r.overall_message.startswith("[配平]")

    def test_empty_message_when_all_pass(self):
        r = self._make_report()
        r.compute_overall()
        assert r.overall_message == "四维审核全部通过"

    def test_none_dimension_skipped(self):
        """某维度为 None 时不影响综合判定。"""
        report = AuditReport(
            question_id="q", equation="E",
            balance=BalanceResult(status=BALANCE_PASSED),
            condition=None,  # 未执行
            product=ProductResult(status=PRODUCT_PASSED),
            structure=None,
        )
        assert report.compute_overall() == OVERALL_PASSED
