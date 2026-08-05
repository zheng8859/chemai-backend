"""四维安全审核引擎 — audit_equation() 综合入口。

设计决策（#3、#6）：
- 引擎内部自动归一化，调用方无需预处理
- 四维顺序执行：归一化→解析→配平→条件→产物→结构
- 返回 AuditReport（含 overall_status 综合判定）

用法：
    from chem_skills.chemistry_parser.engine.audit_engine import audit_equation

    report = audit_equation("2H2 + O2 → 2H2O")
    print(report.overall_status)  # "passed"
"""

from .models import (
    AuditReport,
    BALANCE_ERROR,
    OVERALL_ERROR,
)
from .equation_parser import parse_equation
from .balance_checker import check_balance
from .condition_checker import check_conditions
from .product_checker import check_product_stability
from .structure_checker import check_structure


def audit_equation(equation: str, question_id: str = "") -> AuditReport:
    """对单个化学方程式执行四维安全审核。

    顺序执行四个维度：
    1. 系数配平审核（红线：100% 准确率）
    2. 反应条件审核（14 条件 + 10 反应类型）
    3. 产物稳定性审核（不稳定中间产物、氧化还原）
    4. 分子结构审核（括号、元素格式）

    Args:
        equation: 待审核的化学方程式（支持 LaTeX、Unicode、纯文本）
        question_id: 可选的题目标识符

    Returns:
        AuditReport: 含四维结果 + overall_status + overall_message

    Examples:
        >>> report = audit_equation('2H2 + O2 → 2H2O')
        >>> report.overall_status
        'passed'

        >>> report = audit_equation('Fe + O2 → Fe2O3')
        >>> report.overall_status
        'blocked'
        >>> report.balance.status
        'blocked'
    """
    report = AuditReport(question_id=question_id)

    # 保存原始方程式
    try:
        parts = parse_equation(equation)
        report.equation = parts.original
    except ValueError:
        report.equation = equation
        report.overall_status = OVERALL_ERROR
        report.overall_message = "无法解析方程式"
        return report

    # 维度 1: 配平审核
    report.balance = check_balance(equation)

    # 维度 2: 条件审核
    report.condition = check_conditions(parts.normalized)

    # 维度 3: 产物审核
    report.product = check_product_stability(parts.normalized)

    # 维度 4: 结构审核
    report.structure = check_structure(parts.normalized)

    # 综合判定
    report.compute_overall()

    return report
