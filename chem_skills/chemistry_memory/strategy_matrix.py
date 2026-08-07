"""自适应策略矩阵 — 障碍类型 → 出题策略的纯函数映射。

设计文档 28 号 §3.1 策略总表：
    - concept（概念理解障碍）：降低难度，聚焦基础知识点，增加选择题+填空题
    - reading（审题障碍）：保持难度，混合知识点，增加推断题+陷阱选择题
    - expression（表述障碍）：保持难度，侧重方程式知识点，增加计算题+实验题
"""


def apply_strategy(barrier: str, zpd_difficulty: str) -> dict:
    """根据主导障碍类型和 ZPD 难度计算最终出题策略。

    Args:
        barrier: 主导障碍类型 ("concept" | "reading" | "expression")
        zpd_difficulty: ZPD 计算出的原始难度 ("easy" | "medium" | "hard")

    Returns:
        包含以下键的字典：
        - difficulty: 最终难度（可能被策略降低）
        - kp_preference: 知识点选择倾向 ("foundational" | "mixed" | "equation")
        - question_type_weights: {"choice": 0.x, "fill_blank": 0.x, "calculation": 0.x,
                                   "experiment": 0.x, "inference": 0.x}
    """
    strategies = {
        "concept": _concept_strategy,
        "reading": _reading_strategy,
        "expression": _expression_strategy,
    }

    handler = strategies.get(barrier, _concept_strategy)
    return handler(zpd_difficulty)


def _lower_difficulty(difficulty: str) -> str:
    """降一档难度（hard→medium, medium→easy, easy→easy）。"""
    mapping = {"hard": "medium", "medium": "easy", "easy": "easy"}
    return mapping.get(difficulty, "medium")


def _concept_strategy(zpd_difficulty: str) -> dict:
    """概念理解障碍策略：降低难度，聚焦基础，多选+填空为主。"""
    return {
        "difficulty": _lower_difficulty(zpd_difficulty),
        "kp_preference": "foundational",
        "question_type_weights": {
            "choice": 0.5,
            "fill_blank": 0.3,
            "calculation": 0.1,
            "experiment": 0.05,
            "inference": 0.05,
        },
    }


def _reading_strategy(zpd_difficulty: str) -> dict:
    """审题障碍策略：保持难度，混合知识点，推断+陷阱选择为主。"""
    return {
        "difficulty": zpd_difficulty,
        "kp_preference": "mixed",
        "question_type_weights": {
            "choice": 0.4,
            "fill_blank": 0.1,
            "calculation": 0.1,
            "experiment": 0.15,
            "inference": 0.25,
        },
    }


def _expression_strategy(zpd_difficulty: str) -> dict:
    """表述障碍策略：保持难度，侧重方程式，计算+实验为主。"""
    return {
        "difficulty": zpd_difficulty,
        "kp_preference": "equation",
        "question_type_weights": {
            "choice": 0.2,
            "fill_blank": 0.15,
            "calculation": 0.35,
            "experiment": 0.2,
            "inference": 0.1,
        },
    }
