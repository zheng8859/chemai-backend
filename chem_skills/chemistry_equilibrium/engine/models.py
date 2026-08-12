"""化学平衡数据模型 — 三段式表格（ICE: Initial/Change/Equilibrium）。"""

from dataclasses import dataclass, field


@dataclass
class ICERow:
    """ICE 表格的一行（一个物种的浓度变化）。"""

    species: str
    initial: float  # 初始浓度 (mol/L)
    change: str  # 变化量（如 "-x", "+2x"）
    equilibrium: str  # 平衡浓度表达式（如 "0.1 - x"）


@dataclass
class EquilibriumTable:
    """ICE 三段式表格。"""

    equation: str  # 配平的化学方程式
    rows: list[ICERow] = field(default_factory=list)
    k_expression: str = ""  # 平衡常数表达式
    k_value: float | None = None  # 平衡常数值
    solved_x: float | None = None  # 求解得到的 x 值
