"""四维安全审核引擎 — 全量导出（设计决策 #12）。

纯函数库，零外部依赖，可直接 import 使用。

用法:
    from chem_skills.chemistry_parser.engine import audit_equation

    report = audit_equation("2H2 + O2 → 2H2O")
    print(report.overall_status)  # "passed"
"""

# ── 综合入口 ──
from .audit_engine import audit_equation

# ── 四维独立函数 ──
from .balance_checker import check_balance
from .balancer import balance
from .condition_checker import check_conditions
from .product_checker import check_product_stability
from .structure_checker import check_structure

# ── 数据模型 ──
from .models import (
    EquationParts,
    BalanceDetail,
    BalanceResult,
    ConditionResult,
    ProductResult,
    StructureResult,
    AuditReport,
    # 状态常量
    BALANCE_PASSED, BALANCE_BLOCKED, BALANCE_UNCERTAIN, BALANCE_ERROR,
    CONDITION_PASSED, CONDITION_WARNING, CONDITION_FAILED, CONDITION_UNCERTAIN, CONDITION_ERROR,
    PRODUCT_PASSED, PRODUCT_WARNING, PRODUCT_FAILED, PRODUCT_UNCERTAIN, PRODUCT_ERROR,
    STRUCTURE_PASSED, STRUCTURE_FAILED, STRUCTURE_UNCERTAIN, STRUCTURE_ERROR,
    OVERALL_PASSED, OVERALL_BLOCKED, OVERALL_UNCERTAIN, OVERALL_ERROR,
)

# ── 工具函数 ──
from .equation_parser import parse_equation, extract_equations
from .chem_normalizer import normalize_formulas, normalize_single_formula
from .formula_counter import count_elements

__all__ = [
    # 综合入口
    "audit_equation",
    # 四维独立
    "check_balance",
    "balance",
    "check_conditions",
    "check_product_stability",
    "check_structure",
    # 数据模型
    "EquationParts",
    "BalanceDetail",
    "BalanceResult",
    "ConditionResult",
    "ProductResult",
    "StructureResult",
    "AuditReport",
    # 工具
    "parse_equation",
    "extract_equations",
    "normalize_formulas",
    "normalize_single_formula",
    "count_elements",
]
