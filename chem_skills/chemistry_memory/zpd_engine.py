"""ZPD 难度计算引擎 — 纯函数，零外部依赖。

提供三个核心能力：
1. compute_zpd_difficulty — 30 题滑动窗口 → easy/medium/hard
2. extract_weak_knowledge_points — 全量错题统计 → Top N
3. identify_dominant_barrier — barrier_profile JSON → 主导障碍类型
"""

from collections import Counter
from typing import Optional


def compute_zpd_difficulty(
    answers: list[bool],
    min_sample_size: int = 5,
) -> str:
    """根据最近 N 条作答记录的正确率计算 ZPD 难度档位。

    Args:
        answers: 作答结果列表（True=答对，False=答错），按时间降序（最新在前）。
        min_sample_size: 最小可信样本量，不足时返回 cold start 默认值。

    Returns:
        "easy" | "medium" | "hard"

    阈值规则（设计文档 28 号 §2.2）：
        - 正确率 < 40%  → easy
        - 40% ≤ 正确率 ≤ 70% → medium（含 40% 和 70%）
        - 正确率 > 70%  → hard
        - 样本不足       → medium（冷启动）
    """
    if len(answers) < min_sample_size:
        return "medium"

    correct = sum(1 for a in answers if a)
    accuracy = correct / len(answers)

    if accuracy < 0.4:
        return "easy"
    elif accuracy <= 0.7:
        return "medium"
    else:
        return "hard"


def extract_weak_knowledge_points(
    wrong_answers: list[dict],
    top_n: int = 3,
) -> list[str]:
    """从全量错题记录中提取错误频次最高的知识点。

    Args:
        wrong_answers: 错题记录列表，每条需包含 "knowledge_points" 键
                       （值为知识点名称列表）。
        top_n: 返回前 N 个高频知识点。

    Returns:
        按错误频次降序排列的知识点名称列表（最多 top_n 个）。

    注意：
        - 一题多知识点：每个知识点独立计数。
        - 无错题记录时返回空列表。
    """
    counter: Counter = Counter()
    for record in wrong_answers:
        kps = record.get("knowledge_points", [])
        if isinstance(kps, list):
            for kp in kps:
                if kp:
                    counter[kp] += 1

    return [kp for kp, _ in counter.most_common(top_n)]


def identify_dominant_barrier(
    barrier_profile: Optional[dict],
    default: str = "concept",
) -> str:
    """从障碍画像 JSON 中提取占比最高的障碍类型。

    Args:
        barrier_profile: 障碍画像字典，如 {"concept": 0.7, "reading": 0.15, "expression": 0.15}。
                         为 None 或空字典时返回默认值。
        default: 无有效数据时的默认障碍类型。

    Returns:
        主导障碍类型键名："concept" | "reading" | "expression"
    """
    if not barrier_profile or not isinstance(barrier_profile, dict):
        return default

    # 过滤掉无效值，取最大值的键
    valid = {k: v for k, v in barrier_profile.items() if isinstance(v, (int, float))}
    if not valid:
        return default

    return max(valid, key=valid.__getitem__)
