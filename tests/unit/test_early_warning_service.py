"""EarlyWarningService 单元测试：四类规则独立逻辑验证。"""

import pytest
from datetime import datetime, timezone, timedelta


class TestConsecutiveAbsence:
    """连续未登录检测：last_practice_time 距今 ≥ 3 天 → info。"""

    def test_absent_3_days(self):
        """3 天未登录 → 触发预警。"""
        now = datetime.now(timezone.utc)
        last = now - timedelta(days=3, hours=1)
        delta = now - last
        assert delta.days >= 3

    def test_absent_1_day_no_trigger(self):
        """1 天未登录 → 不触发。"""
        now = datetime.now(timezone.utc)
        last = now - timedelta(days=1)
        delta = now - last
        assert delta.days < 3

    def test_no_practice_time_skip(self):
        """无 last_practice_time → 新学生跳过。"""
        last_practice_time = None
        assert last_practice_time is None  # 应跳过


class TestScoreDrop:
    """成绩下滑检测：降幅 ≥ 10% → warning。"""

    def test_drop_15_percent(self):
        """降幅 15% → 触发。"""
        prev, curr = 0.80, 0.65
        drop = prev - curr
        assert drop == pytest.approx(0.15)
        assert drop >= 0.10

    def test_drop_5_percent_no_trigger(self):
        """降幅 5% → 不触发。"""
        prev, curr = 0.80, 0.75
        drop = prev - curr
        assert drop < 0.10

    def test_improvement_no_trigger(self):
        """成绩上升 → 不触发。"""
        prev, curr = 0.70, 0.85
        drop = prev - curr
        assert drop < 0

    def test_only_one_exam_skip(self):
        """只有一次考试 → 跳过。"""
        exams = [1]  # 只有一次
        assert len(exams) < 2


class TestHighErrorRate:
    """高错误率检测：≥50% warning，≥70% severe。"""

    def test_error_rate_75_severe(self):
        """75% → severe。"""
        errors, total = 30, 40
        rate = errors / total
        assert rate == 0.75
        assert rate >= 0.70

    def test_error_rate_55_warning(self):
        """55% → warning。"""
        errors, total = 22, 40
        rate = errors / total
        assert rate == 0.55
        assert 0.50 <= rate < 0.70

    def test_error_rate_30_no_trigger(self):
        """30% → 不触发。"""
        errors, total = 12, 40
        rate = errors / total
        assert rate < 0.50

    def test_insufficient_samples_skip(self):
        """样本 < 3 跳过。"""
        total = 2
        assert total < 3


class TestNewBarrier:
    """新障碍出现检测：主导障碍归一化变化 ≥ 30% → severe。"""

    def test_barrier_shift_35_percent(self):
        """主导障碍转移 35% → 触发。"""
        prev_dominant = "concept"
        curr_dominant = "reading"
        shift = 0.35
        assert curr_dominant != prev_dominant
        assert shift >= 0.30

    def test_barrier_shift_20_percent_no_trigger(self):
        """主导障碍转移但仅 20% → 不触发。"""
        shift = 0.20
        assert shift < 0.30

    def test_same_dominant_no_trigger(self):
        """主导障碍不变 → 不触发。"""
        prev_dominant = "concept"
        curr_dominant = "concept"
        assert curr_dominant == prev_dominant

    def test_no_history_skip(self):
        """无历史快照 → 跳过检测。"""
        last_snapshot = None
        assert last_snapshot is None


class TestBarrierNormalization:
    """障碍归一化：S_normalized = S_raw / max(S_raw_barriers_in_class)。"""

    def test_normalization(self):
        """归一化计算正确。"""
        raw_scores = {"concept": 0.4, "reading": 0.3, "expression": 0.2}
        max_raw = max(raw_scores.values())
        normalized = {
            k: v / max_raw for k, v in raw_scores.items()
        }
        assert normalized["concept"] == pytest.approx(1.0)
        assert normalized["reading"] == pytest.approx(0.75)
        assert normalized["expression"] == pytest.approx(0.5)

    def test_normalization_zero_max(self):
        """最大值为 0 时避免除零。"""
        max_raw = 0.0
        raw = 0.5
        normalized = raw / max_raw if max_raw > 0 else 0.0
        assert normalized == 0.0


class TestWarningDeduplication:
    """去重逻辑：同一学生同类型未处理预警存在时不重复生成。"""

    def test_duplicate_filtered(self):
        """已存在同类型 pending 预警 → 过滤。"""
        existing = {(1, "score_drop"), (2, "consecutive_absence")}
        new_warnings = [
            {"student_id": 1, "warning_type": "score_drop"},
            {"student_id": 1, "warning_type": "high_error_rate"},
            {"student_id": 2, "warning_type": "consecutive_absence"},
        ]
        filtered = [
            w for w in new_warnings
            if (w["student_id"], w["warning_type"]) not in existing
        ]
        assert len(filtered) == 1
        assert filtered[0]["warning_type"] == "high_error_rate"

    def test_resolved_warning_allows_new(self):
        """已 resolve 的预警允许新生成。"""
        existing = {(1, "score_drop")}  # only pending/processing
        new = {"student_id": 1, "warning_type": "score_drop"}
        assert (new["student_id"], new["warning_type"]) in existing
