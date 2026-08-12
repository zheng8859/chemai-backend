"""化学计量数据模型。"""

from dataclasses import dataclass, field
from enum import Enum


class QuantityType(str, Enum):
    MASS = "mass"        # 质量 (g)
    MOLES = "moles"      # 物质的量 (mol)
    VOLUME = "volume"    # 气体体积 (L)
    CONCENTRATION = "concentration"  # 浓度 (mol/L)
    PARTICLES = "particles"  # 粒子数


@dataclass
class QuantityInfo:
    """已知量/未知量信息。"""

    symbol: str  # 物理量符号（如 "m", "n", "V", "c"）
    value: float | None  # 数值（未知时为 None）
    unit: str  # 单位
    type: QuantityType


@dataclass
class StoichiometryProblem:
    """化学计量问题。"""

    equation: str  # 配平的化学方程式
    known_quantities: list[QuantityInfo] = field(default_factory=list)
    unknown_quantity: QuantityInfo | None = None
    molar_masses: dict[str, float] = field(default_factory=dict)  # {formula: M (g/mol)}
    solution_steps: list[str] = field(default_factory=list)
    result: float | None = None
