"""障碍诊断引擎 — 全量导出。

纯函数库，零外部依赖，可直接 import 使用。

用法:
    from chem_skills.chemistry_diagnosis.engine import (
        DiagnosisResult, BarrierProfile, ClassDistribution,
        diagnose_single, diagnose_batch,
        aggregate_student, aggregate_class,
    )
"""

# ── 数据模型 ──
from .models import (
    DiagnosisResult,
    BarrierProfile,
    ClassDistribution,
    WeakKnowledgePoint,
    VALID_BARRIER_TYPES,
    VALID_MISCONCEPTION_CATEGORIES,
)

# ── LLM 诊断 ──
from .llm_diagnoser import diagnose_single, diagnose_batch

# ── 聚合统计 ──
from .aggregator import aggregate_student, aggregate_class

__all__ = [
    # 数据模型
    "DiagnosisResult",
    "BarrierProfile",
    "ClassDistribution",
    "WeakKnowledgePoint",
    "VALID_BARRIER_TYPES",
    "VALID_MISCONCEPTION_CATEGORIES",
    # 诊断
    "diagnose_single",
    "diagnose_batch",
    # 聚合
    "aggregate_student",
    "aggregate_class",
]
