"""Aggregator 聚合器单元测试。

验证 aggregate_student 和 aggregate_class 的计数、归一化和边界处理。
"""

import pytest
from chem_skills.chemistry_diagnosis.engine.aggregator import (
    aggregate_student,
    aggregate_class,
)
from chem_skills.chemistry_diagnosis.engine.models import BarrierProfile, ClassDistribution


# ═══════════════════════════════════════════════════════════════
# aggregate_student 测试
# ═══════════════════════════════════════════════════════════════

class TestAggregateStudent:

    def test_normal_distribution(self):
        """10 条：concept 4、reading 3、expression 3。"""
        answers = (
            [{"barrier_type": "concept"}] * 4
            + [{"barrier_type": "reading"}] * 3
            + [{"barrier_type": "expression"}] * 3
        )
        profile = aggregate_student(1, answers)
        assert profile.student_id == 1
        assert profile.total_diagnosed == 10
        assert profile.concept_ratio == 0.4
        assert profile.reading_ratio == 0.3
        assert profile.expression_ratio == 0.3
        assert profile.dominant_barrier() == "concept"

    def test_all_concept(self):
        """全部 concept。"""
        answers = [{"barrier_type": "concept"}] * 5
        profile = aggregate_student(2, answers)
        assert profile.concept_ratio == 1.0
        assert profile.reading_ratio == 0.0
        assert profile.expression_ratio == 0.0
        assert profile.dominant_barrier() == "concept"

    def test_zero_answers(self):
        """无已诊断作答 → 全零。"""
        profile = aggregate_student(3, [])
        assert profile.total_diagnosed == 0
        assert profile.concept_ratio == 0.0
        assert profile.reading_ratio == 0.0
        assert profile.expression_ratio == 0.0
        assert profile.dominant_barrier() is None

    def test_to_dict_rounding(self):
        """to_dict 保留两位小数。"""
        answers = [{"barrier_type": "concept"}] * 3 + [{"barrier_type": "reading"}] * 1
        profile = aggregate_student(4, answers)
        d = profile.to_dict()
        assert d == {"concept": 0.75, "reading": 0.25, "expression": 0.0}

    def test_dominant_barrier_tie(self):
        """平局 → dominant_barrier 返回 None。"""
        answers = [{"barrier_type": "concept"}, {"barrier_type": "reading"}]
        profile = aggregate_student(5, answers)
        assert profile.dominant_barrier() is None

    def test_teacher_overridden_equal_weight(self):
        """教师覆盖的记录与 LLM 诊断等权计数。"""
        answers = [
            {"barrier_type": "concept"},      # LLM
            {"barrier_type": "reading"},       # 教师覆盖
            {"barrier_type": "concept"},       # LLM
        ]
        profile = aggregate_student(6, answers)
        assert profile.concept_ratio == pytest.approx(2 / 3, 0.01)
        assert profile.reading_ratio == pytest.approx(1 / 3, 0.01)

    def test_weak_kps_extraction(self):
        """从 knowledge_point_tags 提取薄弱知识点。"""
        answers = [
            {"barrier_type": "concept", "knowledge_point_tags": ["氧化还原", "电化学"]},
            {"barrier_type": "concept", "knowledge_point_tags": ["氧化还原"]},
            {"barrier_type": "reading", "knowledge_point_tags": ["摩尔计算"]},
        ]
        profile = aggregate_student(7, answers)
        assert "氧化还原" in profile.weak_kps
        # 出现次数最多的排前面
        assert profile.weak_kps[0] == "氧化还原"

    def test_empty_kp_tags(self):
        """无 knowledge_point_tags → weak_kps 为空。"""
        answers = [{"barrier_type": "concept"}] * 3
        profile = aggregate_student(8, answers)
        assert profile.weak_kps == []


# ═══════════════════════════════════════════════════════════════
# aggregate_class 测试
# ═══════════════════════════════════════════════════════════════

class TestAggregateClass:

    def test_class_distribution(self):
        """3 个学生：concept 主导 2 人、reading 主导 1 人。"""
        student_answers = {
            1: [{"barrier_type": "concept"}] * 5 + [{"barrier_type": "reading"}] * 2,
            2: [{"barrier_type": "concept"}] * 8 + [{"barrier_type": "expression"}] * 2,
            3: [{"barrier_type": "reading"}] * 4 + [{"barrier_type": "concept"}] * 1,
        }
        dist = aggregate_class(1, 100, student_answers)
        assert dist.class_id == 1
        assert dist.exam_id == 100
        assert dist.concept_student_count == 2  # 学生 1、2 主导为 concept
        assert dist.reading_student_count == 1   # 学生 3 主导为 reading
        assert dist.expression_student_count == 0
        assert dist.total_diagnosed_students == 3

    def test_empty_class(self):
        """无学生作答 → 全零。"""
        dist = aggregate_class(1, 100, {})
        assert dist.total_diagnosed_students == 0
        assert dist.concept_student_count == 0
        assert dist.to_summary_dict()["concept_rate"] == 0.0

    def test_weak_kps_ranking(self):
        """班级薄弱知识点按错误率排名。"""
        student_answers = {
            1: [
                {"barrier_type": "concept", "knowledge_point_tags": ["氧化还原"], "is_correct": False},
                {"barrier_type": "concept", "knowledge_point_tags": ["氧化还原"], "is_correct": False},
                {"barrier_type": "concept", "knowledge_point_tags": ["摩尔计算"], "is_correct": True},
            ],
            2: [
                {"barrier_type": "reading", "knowledge_point_tags": ["摩尔计算"], "is_correct": False},
                {"barrier_type": "reading", "knowledge_point_tags": ["电化学"], "is_correct": False},
            ],
        }
        dist = aggregate_class(1, 100, student_answers)
        assert len(dist.top_weak_kps) > 0
        # 氧化还原：2 错 / 2 总 = 1.0 错误率 → 应排第一
        top = dist.top_weak_kps[0]
        assert top.name == "氧化还原"
        assert top.error_rate == 1.0

    def test_to_summary_dict(self):
        """验证 class_summary 输出格式。"""
        student_answers = {
            1: [{"barrier_type": "concept"}] * 3,
            2: [{"barrier_type": "concept"}] * 1 + [{"barrier_type": "reading"}] * 4,
        }
        dist = aggregate_class(2, 200, student_answers)
        summary = dist.to_summary_dict()
        assert "concept_rate" in summary
        assert "reading_rate" in summary
        assert "expression_rate" in summary
        assert "top_weak_kps" in summary
        # 学生 1 主导 concept，学生 2 主导 reading
        assert summary["concept_rate"] == 0.5
        assert summary["reading_rate"] == 0.5

    def test_tie_students_not_counted(self):
        """平局学生不计入任何主导障碍。"""
        student_answers = {
            1: [{"barrier_type": "concept"}, {"barrier_type": "reading"}],  # 平局
            2: [{"barrier_type": "concept"}] * 3,  # concept 主导
        }
        dist = aggregate_class(1, 100, student_answers)
        assert dist.concept_student_count == 1  # 只有学生 2
        assert dist.total_diagnosed_students == 1  # 学生 1 不计入
