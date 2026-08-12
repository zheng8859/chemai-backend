"""化学平衡辅导引擎 — 三段式表格（ICE）计算。

导出：
- EquilibriumTable: 三段式表格数据模型
- build_ice_table: 构建初始/变化/平衡三段式表格
- apply_le_chatelier: 应用勒夏特列原理分析平衡移动
"""

from .models import EquilibriumTable, ICERow
from .tutor import build_ice_table, apply_le_chatelier

__all__ = [
    "EquilibriumTable",
    "ICERow",
    "build_ice_table",
    "apply_le_chatelier",
]
