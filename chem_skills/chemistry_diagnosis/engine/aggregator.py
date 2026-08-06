"""诊断结果聚合器 — 学生画像 + 班级分布。

纯计数 + 归一化逻辑，不访问数据库。输入为 dict 列表（与 ORM 解耦），
输出为 engine models 中的 BarrierProfile 和 ClassDistribution。
"""

from collections import Counter

from .models import BarrierProfile, ClassDistribution, WeakKnowledgePoint


# ═══════════════════════════════════════════════════════════════
# 公共 API
# ═══════════════════════════════════════════════════════════════

def aggregate_student(
    student_id: int,
    diagnosed_answers: list[dict],
) -> BarrierProfile:
    """聚合单个学生的三维障碍画像。

    Args:
        student_id: 学生 ID
        diagnosed_answers: 该生所有已诊断错误作答列表。
            每项 dict 至少含 barrier_type (str)，可选 misconception_category (str|None)
            和 knowledge_point_tags (list[str])。

    Returns:
        BarrierProfile，含三障碍占比 + 薄弱知识点列表。
        零已诊断作答时三个比率均为 0.0。
    """
    total = len(diagnosed_answers)

    if total == 0:
        return BarrierProfile(student_id=student_id)

    # 计数各障碍类型
    barrier_counts = Counter(a.get("barrier_type", "") for a in diagnosed_answers)

    concept = barrier_counts.get("concept", 0)
    reading = barrier_counts.get("reading", 0)
    expression = barrier_counts.get("expression", 0)

    # 归一化
    profile = BarrierProfile(
        student_id=student_id,
        concept_ratio=concept / total,
        reading_ratio=reading / total,
        expression_ratio=expression / total,
        total_diagnosed=total,
    )

    # 提取薄弱知识点：在所有已诊断作答中，统计知识点出现频次
    kp_counter: Counter[str] = Counter()
    for a in diagnosed_answers:
        tags = a.get("knowledge_point_tags") or []
        for tag in tags:
            kp_counter[tag] += 1

    # 取出现次数最多的前 5 个作为薄弱知识点
    profile.weak_kps = [kp for kp, _ in kp_counter.most_common(5)]

    return profile


def aggregate_class(
    class_id: int,
    exam_id: int,
    student_answers: dict[int, list[dict]],
) -> ClassDistribution:
    """聚合班级级障碍分布统计。

    Args:
        class_id: 班级 ID
        exam_id: 考试 ID
        student_answers: {student_id: [answer_dict, ...]}，
            每个 answer_dict 含 barrier_type、misconception_category、knowledge_point_tags。

    Returns:
        ClassDistribution，含主导障碍学生分布 + 班级薄弱知识点排名。
    """
    distribution = ClassDistribution(
        class_id=class_id,
        exam_id=exam_id,
    )

    if not student_answers:
        return distribution

    # 逐生计算主导障碍
    for sid, answers in student_answers.items():
        profile = aggregate_student(sid, answers)
        dominant = profile.dominant_barrier()

        if dominant == "concept":
            distribution.concept_student_count += 1
        elif dominant == "reading":
            distribution.reading_student_count += 1
        elif dominant == "expression":
            distribution.expression_student_count += 1
        # dominant 为 None（平局或零诊断）时不计入任何类型

    distribution.total_diagnosed_students = (
        distribution.concept_student_count
        + distribution.reading_student_count
        + distribution.expression_student_count
    )

    # 班级薄弱知识点排名：汇总所有学生的 KP 频次
    kp_counter: Counter[str] = Counter()
    kp_error_counter: Counter[str] = Counter()
    kp_total_counter: Counter[str] = Counter()

    for answers in student_answers.values():
        for a in answers:
            tags = a.get("knowledge_point_tags") or []
            for tag in tags:
                kp_total_counter[tag] += 1
                # 错题
                if not a.get("is_correct", True):
                    kp_error_counter[tag] += 1

    # 按错误率排序，取前 10
    all_kps = set(list(kp_total_counter.keys()) + list(kp_error_counter.keys()))
    weak_kps: list[WeakKnowledgePoint] = []
    for kp in all_kps:
        total_count = kp_total_counter.get(kp, 0)
        error_count = kp_error_counter.get(kp, 0)
        if total_count > 0:
            weak_kps.append(WeakKnowledgePoint(
                name=kp,
                error_count=error_count,
                error_rate=error_count / total_count,
            ))

    # 按错误率降序排列
    weak_kps.sort(key=lambda x: (-x.error_rate, x.name))
    distribution.top_weak_kps = weak_kps[:10]

    return distribution
