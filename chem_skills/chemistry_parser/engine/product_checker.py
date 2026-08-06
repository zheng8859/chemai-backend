"""维度 3：产物稳定性审核 — 气体逸出/沉淀/氧化还原产物/特殊反应。

算法（26号 §四）：
1. 不稳定中间产物检测（H2CO3/H2SO3/NH4OH）
2. 气体逸出规则检测
3. 氧化还原产物合理性检测

规则数据存于 data/audit_product_rules.json（设计决策 #25）。
"""

import re
from typing import Any

from .models import (
    ProductResult,
    PRODUCT_PASSED,
    PRODUCT_WARNING,
    PRODUCT_FAILED,
    PRODUCT_ERROR,
)
from .equation_parser import parse_equation
from .rule_loader import load_json_rules


# ═══════════════════════════════════════════════════════════════
# JSON 规则加载
# ═══════════════════════════════════════════════════════════════

_FALLBACK_PRODUCT: dict[str, Any] = {
    "unstable_intermediates": [],
    "redox_products": [],
    "gas_evolution": [],
}

_RULES = load_json_rules("audit_product_rules.json", _FALLBACK_PRODUCT)


# ═══════════════════════════════════════════════════════════════
# Public API
# ═══════════════════════════════════════════════════════════════

def check_product_stability(equation: str) -> ProductResult:
    """检查方程式的产物稳定性。

    检测不稳定中间产物、气体逸出遗漏、明显错误的氧化还原产物。

    Args:
        equation: 化学方程式字符串

    Returns:
        ProductResult: 含 status、issues
    """
    if not equation or not equation.strip():
        return ProductResult(status=PRODUCT_ERROR, message="方程式为空")

    eq = equation.strip()
    issues: list[str] = []
    warnings: list[str] = []

    # 1. 不稳定中间产物检测
    _check_unstable(eq, issues)

    # 2. 氧化还原产物合理性
    _check_redox(eq, warnings)

    # 综合判定
    if issues:
        return ProductResult(
            status=PRODUCT_FAILED,
            message=f"产物问题: {'; '.join(issues)}",
            issues=issues,
        )

    if warnings:
        return ProductResult(
            status=PRODUCT_WARNING,
            message=f"产物建议: {'; '.join(warnings)}",
            issues=warnings,
        )

    return ProductResult(status=PRODUCT_PASSED, message="产物稳定")


# ═══════════════════════════════════════════════════════════════
# Internal
# ═══════════════════════════════════════════════════════════════

def _check_unstable(eq: str, issues: list[str]) -> None:
    """检测不稳定中间产物（H2CO3/H2SO3/NH4OH）。

    这些物质在常温下分解，不应作为最终产物出现。
    """
    for rule in _RULES.get("unstable_intermediates", []):
        pattern = rule["pattern"]
        if _pattern_present(eq, pattern):
            issues.append(rule["reason"])


def _check_redox(eq: str, warnings: list[str]) -> None:
    """检测氧化还原产物合理性。

    当前实现：检测常见氧化还原模式。
    - 浓H2SO4 + Cu → 应生成SO2而非H2
    - 稀H2SO4 + 活泼金属 → 应生成H2
    """
    for rule in _RULES.get("redox_products", []):
        acid = rule.get("acid", "")
        metal = rule.get("metal", "")
        not_expected = rule.get("not_expected", "")

        if acid and metal and not_expected:
            if acid in eq and metal in eq and not_expected in eq:
                warnings.append(rule.get("reason", f"{acid}+{metal}不应生成{not_expected}"))


def _pattern_present(eq: str, pattern: str) -> bool:
    """词边界匹配。"""
    pat = r'(?<![A-Za-z])' + re.escape(pattern) + r'(?![A-Za-z])'
    return bool(re.search(pat, eq))
