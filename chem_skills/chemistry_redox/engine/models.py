"""氧化还原数据模型。"""

from dataclasses import dataclass, field


@dataclass
class RedoxHalfReaction:
    """氧化/还原半反应。"""

    type: str  # "oxidation" or "reduction"
    equation: str  # 半反应方程式
    electron_count: int  # 转移电子数
    element: str  # 发生氧化数变化的元素


@dataclass
class RedoxAnalysis:
    """氧化还原分析结果。"""

    equation: str
    oxidation_states: dict[str, int] = field(default_factory=dict)  # {element: oxidation_state}
    oxidation_half: RedoxHalfReaction | None = None
    reduction_half: RedoxHalfReaction | None = None
    electron_transfer: int = 0  # 总转移电子数
    balanced_equation: str = ""
