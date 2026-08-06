"""障碍诊断引擎 — 纯 dataclass 数据模型。

设计原则（零外部依赖）：
- 全部使用 Python @dataclass，不依赖 Pydantic
- 与 app/core/enums.py 中的 BarrierType/MisconceptionCategory 对齐
- 聚合结果直接可序列化为 JSON（用于 Student.barrier_profile）
"""

from dataclasses import dataclass, field


# ═══════════════════════════════════════════════════════════════
# 合法值常量（与 app/core/enums.py 对齐，避免跨层依赖）
# ═══════════════════════════════════════════════════════════════

VALID_BARRIER_TYPES = ("concept", "reading", "expression")

VALID_MISCONCEPTION_CATEGORIES = (
    "chemical_equilibrium",
    "redox",
    "mole_calculation",
    "organic_chemistry",
    "chemical_notation",
    "structure_of_matter",
)


# ═══════════════════════════════════════════════════════════════
# 单条诊断结果
# ═══════════════════════════════════════════════════════════════

@dataclass
class DiagnosisResult:
    """LLM 对单条错误作答的诊断结果。

    对应 spec/llm-diagnoser：LLM 返回的四字段 JSON。
    barrier_type 和 misconception_category 构成 3×6 诊断矩阵。
    """
    barrier_type: str                                    # concept | reading | expression
    misconception_category: str | None                   # 6 类迷思概念 或 null
    reasoning: str                                       # 判定依据（自然语言）
    suggestion: str                                      # 教学干预建议

    def is_valid(self) -> bool:
        """barrier_type 必须在合法枚举内。

        misconception_category 为 None 或合法枚举值均可。
        """
        if self.barrier_type not in VALID_BARRIER_TYPES:
            return False
        if self.misconception_category is not None and \
           self.misconception_category not in VALID_MISCONCEPTION_CATEGORIES:
            return False
        return True

    def to_dict(self) -> dict:
        return {
            "barrier_type": self.barrier_type,
            "misconception_category": self.misconception_category,
            "reasoning": self.reasoning,
            "suggestion": self.suggestion,
        }


# ═══════════════════════════════════════════════════════════════
# 学生障碍画像
# ═══════════════════════════════════════════════════════════════

@dataclass
class BarrierProfile:
    """单个学生的三维障碍画像。

    由 aggregate_student() 产出，直接写入 Student.barrier_profile JSON 字段。
    三个占比之和恒为 1.0（保留两位小数），无已诊断作答时全为 0.00。
    """
    student_id: int
    concept_ratio: float = 0.0
    reading_ratio: float = 0.0
    expression_ratio: float = 0.0
    weak_kps: list[str] = field(default_factory=list)   # 薄弱知识点名称列表
    total_diagnosed: int = 0                             # 已诊断作答总数

    def to_dict(self) -> dict:
        """序列化为 Student.barrier_profile JSON 格式。

        格式：{"concept": 0.40, "reading": 0.30, "expression": 0.30}
        """
        return {
            "concept": round(self.concept_ratio, 2),
            "reading": round(self.reading_ratio, 2),
            "expression": round(self.expression_ratio, 2),
        }

    def dominant_barrier(self) -> str | None:
        """返回占比最高的障碍类型。

        Returns:
            障碍类型字符串，无诊断或平局时返回 None。
        """
        if self.total_diagnosed == 0:
            return None
        scores = {
            "concept": self.concept_ratio,
            "reading": self.reading_ratio,
            "expression": self.expression_ratio,
        }
        max_val = max(scores.values())
        winners = [k for k, v in scores.items() if v == max_val]
        return winners[0] if len(winners) == 1 else None


# ═══════════════════════════════════════════════════════════════
# 班级诊断分布
# ═══════════════════════════════════════════════════════════════

@dataclass
class WeakKnowledgePoint:
    """薄弱知识点 — 班级级聚合中的单个知识点统计。"""
    name: str
    error_count: int
    error_rate: float

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "error_count": self.error_count,
            "error_rate": round(self.error_rate, 2),
        }


@dataclass
class ClassDistribution:
    """班级级障碍分布统计。

    由 aggregate_class() 产出，用于 GET /diagnosis/class/{id}/exam/{id} 响应。
    concept/reading/expression_student_count 记录以此为主导障碍的学生数。
    """
    class_id: int
    exam_id: int
    concept_student_count: int = 0       # 以此为主导障碍的学生数
    reading_student_count: int = 0
    expression_student_count: int = 0
    top_weak_kps: list[WeakKnowledgePoint] = field(default_factory=list)
    total_diagnosed_students: int = 0    # 已诊断学生总数

    def to_summary_dict(self) -> dict:
        """序列化为 class_summary JSON，含各障碍占比和薄弱知识点排名。"""
        if self.total_diagnosed_students == 0:
            return {
                "concept_rate": 0.0,
                "reading_rate": 0.0,
                "expression_rate": 0.0,
                "top_weak_kps": [kp.to_dict() for kp in self.top_weak_kps],
            }
        total = self.total_diagnosed_students
        return {
            "concept_rate": round(self.concept_student_count / total, 2),
            "reading_rate": round(self.reading_student_count / total, 2),
            "expression_rate": round(self.expression_student_count / total, 2),
            "top_weak_kps": [kp.to_dict() for kp in self.top_weak_kps],
        }
