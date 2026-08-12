"""离子反应数据模型。"""

from dataclasses import dataclass, field
from enum import Enum


class ElectrolyteType(str, Enum):
    STRONG = "strong"        # 强电解质（完全解离）
    WEAK = "weak"            # 弱电解质（部分解离）
    NON_ELECTROLYTE = "non"  # 非电解质（不解离）


@dataclass
class IonicAnalysis:
    """离子反应分析结果。"""

    molecular_equation: str
    species: list[dict] = field(default_factory=list)  # [{"formula": str, "type": ElectrolyteType, "ions": [...]}]
    total_ionic: str = ""  # 全离子方程式
    spectators: list[str] = field(default_factory=list)  # 旁观离子
    net_ionic: str = ""  # 净离子方程式
    charge_balanced: bool = False
    atom_balanced: bool = False
