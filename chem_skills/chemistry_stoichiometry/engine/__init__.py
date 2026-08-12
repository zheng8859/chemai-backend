"""化学计量辅导引擎 — 四步法（提取已知量→选择公式→建立比例→逐步计算）。

导出：
- extract_known_quantities: 从题目提取已知量
- select_formula: 选择合适的计算公式
- setup_proportion: 建立化学计量比例关系
- calculate_stepwise: 逐步计算未知量
"""

from .models import StoichiometryProblem, QuantityInfo
from .tutor import (
    extract_known_quantities,
    select_formula,
    setup_proportion,
    calculate_stepwise,
)

__all__ = [
    "StoichiometryProblem",
    "QuantityInfo",
    "extract_known_quantities",
    "select_formula",
    "setup_proportion",
    "calculate_stepwise",
]
