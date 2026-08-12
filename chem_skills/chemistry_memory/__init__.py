"""ChemAI - chemistry_memory 记忆与复习引擎。

导出 7 个核心函数：
- ZPD 引擎: compute_zpd_difficulty, extract_weak_knowledge_points, identify_dominant_barrier
- 间隔复习: compute_next_review, evaluate_level_change
- 变式生成: build_variant_prompt
- 策略矩阵: apply_strategy
"""

from .zpd_engine import (
    compute_zpd_difficulty,
    extract_weak_knowledge_points,
    identify_dominant_barrier,
)
from .spaced_repetition import compute_next_review, evaluate_level_change
from .variant_generator import build_variant_prompt
from .strategy_matrix import apply_strategy, BarrierType

__all__ = [
    "compute_zpd_difficulty",
    "extract_weak_knowledge_points",
    "identify_dominant_barrier",
    "compute_next_review",
    "evaluate_level_change",
    "build_variant_prompt",
    "apply_strategy",
    "BarrierType",
]
