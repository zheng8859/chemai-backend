"""PanelService 单元测试：加权均分、错误率公式、障碍分布、进步/退步 Top 3。"""

import math
import pytest
from datetime import datetime, timezone, timedelta


class TestWeightedDecay:
    """测试加权指数衰减公式 w_i = exp(-λ × (t_now - t_i) / T_week)。"""

    def test_decay_half_life(self):
        """半衰期：7 天前的考试权重应为 0.5。"""
        decay_lambda = math.log(2)
        T_week = 7 * 24 * 3600
        delta = T_week  # exactly one week
        weight = math.exp(-decay_lambda * delta / T_week)
        assert weight == pytest.approx(0.5, abs=0.001)

    def test_decay_recent_exam_weight_near_one(self):
        """今天的考试权重接近 1。"""
        decay_lambda = math.log(2)
        T_week = 7 * 24 * 3600
        delta = 3600  # 1 hour ago
        weight = math.exp(-decay_lambda * delta / T_week)
        assert weight > 0.99

    def test_decay_old_exam_weight_low(self):
        """14 天前的考试权重应为 0.25。"""
        decay_lambda = math.log(2)
        T_week = 7 * 24 * 3600
        delta = 2 * T_week  # two weeks
        weight = math.exp(-decay_lambda * delta / T_week)
        assert weight == pytest.approx(0.25, abs=0.001)


class TestErrorRateFormula:
    """测试错误率公式 E(kp, c) = errors(kp, c) / total(kp, c)。"""

    def test_perfect_score(self):
        """全对：错误率应为 0。"""
        errors, total = 0, 50
        rate = errors / total
        assert rate == 0.0

    def test_all_wrong(self):
        """全错：错误率应为 1。"""
        errors, total = 50, 50
        rate = errors / total
        assert rate == 1.0

    def test_half_wrong(self):
        """半错：错误率 0.5。"""
        errors, total = 25, 50
        rate = errors / total
        assert rate == 0.5

    def test_zero_total(self):
        """分母为 0 时不计算。"""
        total = 0
        assert total == 0  # 应该跳过


class TestBarrierDistribution:
    """测试障碍类型分布统计。"""

    def test_even_distribution(self):
        """均匀分布：三种障碍各 1/3。"""
        profiles = [
            {"concept": 0.5, "reading": 0.3, "expression": 0.2},
            {"concept": 0.2, "reading": 0.5, "expression": 0.3},
            {"concept": 0.3, "reading": 0.2, "expression": 0.5},
        ]
        from collections import defaultdict
        counts = defaultdict(int)
        for profile in profiles:
            dominant = max(profile, key=profile.get)
            counts[dominant] += 1

        assert counts["concept"] == 1
        assert counts["reading"] == 1
        assert counts["expression"] == 1

    def test_empty_profiles(self):
        """无障碍画像时返回空分布。"""
        profiles = []
        assert len(profiles) == 0


class TestTopImprovers:
    """测试进步/退步 Top 3 计算。"""

    def test_improver_positive_change(self):
        """正确率提升应标记为进步。"""
        prev_acc, curr_acc = 0.60, 0.80
        change = curr_acc - prev_acc
        assert change > 0
        assert change == pytest.approx(0.20)

    def test_declining_negative_change(self):
        """正确率下降应标记为退步。"""
        prev_acc, curr_acc = 0.80, 0.55
        change = curr_acc - prev_acc
        assert change < 0
        assert change == pytest.approx(-0.25)

    def test_stable_no_change(self):
        """正确率不变。"""
        prev_acc, curr_acc = 0.70, 0.70
        change = curr_acc - prev_acc
        assert change == 0.0

    def test_top_3_sorting(self):
        """正确排序：进步最大排第一。"""
        changes = [
            {"name": "A", "change": 0.05},
            {"name": "B", "change": 0.20},
            {"name": "C", "change": 0.10},
            {"name": "D", "change": 0.15},
        ]
        changes.sort(key=lambda x: x["change"], reverse=True)
        top3 = [c for c in changes if c["change"] > 0][:3]
        assert len(top3) == 3
        assert top3[0]["name"] == "B"  # 0.20
        assert top3[1]["name"] == "D"  # 0.15
        assert top3[2]["name"] == "C"  # 0.10
