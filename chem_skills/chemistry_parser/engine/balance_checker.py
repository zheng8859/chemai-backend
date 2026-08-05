"""维度 1：系数配平审核 — 化学方程式配平检查器。

核心算法（26号 §二）：
1. 解析方程式 → 反应物列表 + 产物列表
2. 逐化合物统计元素原子数（含系数乘法）
3. 按侧汇总 → left_elements vs right_elements
4. 逐元素比对 → 全部相等 = PASS，否则 = BLOCKED

红线要求：配平准确率 = 100%
"""

from .models import BalanceResult, BalanceDetail, BALANCE_PASSED, BALANCE_BLOCKED, BALANCE_ERROR
from .equation_parser import parse_equation
def check_balance(equation: str) -> BalanceResult:
    """检查化学方程式的系数配平。

    对所有元素逐一验证反应物侧原子总数 == 产物侧原子总数。

    Args:
        equation: 化学方程式字符串（支持 LaTeX、Unicode、纯文本）

    Returns:
        BalanceResult: 含 status (passed/blocked/error)、message、detail

    Examples:
        >>> r = check_balance('2H2 + O2 → 2H2O')
        >>> r.status
        'passed'
        >>> r = check_balance('Fe + O2 → Fe2O3')
        >>> r.status
        'blocked'
    """
    # Step 1: 解析方程式
    try:
        parts = parse_equation(equation)
    except ValueError as e:
        return BalanceResult(
            status=BALANCE_ERROR,
            message=f"无法解析方程式: {e}",
        )

    # Step 2-3: 统计两侧元素（委托给 EquationParts）
    left_elements, right_elements = parts.sum_elements()

    # Step 4: 逐元素比对
    all_elements = set(left_elements.keys()) | set(right_elements.keys())
    mismatches: list[str] = []

    for elem in sorted(all_elements):
        left = left_elements.get(elem, 0)
        right = right_elements.get(elem, 0)
        if left != right:
            mismatches.append(f"{elem}: 左{left} vs 右{right}")

    detail = BalanceDetail(
        left_elements=dict(sorted(left_elements.items())),
        right_elements=dict(sorted(right_elements.items())),
    )

    if not mismatches:
        return BalanceResult(
            status=BALANCE_PASSED,
            message="配平正确",
            detail=detail,
        )

    # 有未配平的元素
    return BalanceResult(
        status=BALANCE_BLOCKED,
        message=f"方程式未配平: {'; '.join(mismatches)}",
        detail=detail,
    )
