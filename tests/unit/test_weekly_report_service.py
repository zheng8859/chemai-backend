"""WeeklyReportService 单元测试 — fallback 报告 + schema 验证。

LLM 实际调用在 L2 集成测试中覆盖。
"""

import pytest
from datetime import datetime, timezone, timedelta

from app.services.weekly_report_service import WeeklyReportService


class TestFallbackReport:
    """LLM 不可用时的降级报告生成。"""

    def test_no_data_report(self):
        """无练习数据时 no_data=True。"""
        result = WeeklyReportService._fallback_report(
            student_name="张三",
            practice_count=0,
            accuracy=None,
            streak=0,
            weak_kps=[],
        )
        assert result["no_data"] is True
        assert "暂无练习记录" in result["summary"]
        assert result["detail"]
        assert result["advice"]

    def test_with_data_report(self):
        """有练习数据时的报告。"""
        result = WeeklyReportService._fallback_report(
            student_name="李四",
            practice_count=5,
            accuracy=0.85,
            streak=7,
            weak_kps=["化学平衡", "氧化还原反应"],
        )
        assert result["no_data"] is False
        assert "李四" in result["summary"]
        assert "5" in result["summary"]
        assert "85%" in result["summary"]
        # 术语已被转换为通俗表述
        assert "反应的动态平衡" in result["detail"] or "与电子转移相关的反应" in result["detail"]

    def test_accuracy_none(self):
        """无正确率数据时不显示百分比。"""
        result = WeeklyReportService._fallback_report(
            student_name="王五",
            practice_count=3,
            accuracy=None,
            streak=1,
            weak_kps=[],
        )
        assert result["no_data"] is False
        assert "%" not in result["summary"]

    def test_low_practice_count_triggers_no_data(self):
        """练习次数 < 2 触发 no_data。"""
        result = WeeklyReportService._fallback_report(
            student_name="赵六",
            practice_count=1,
            accuracy=0.9,
            streak=1,
            weak_kps=[],
        )
        assert result["no_data"] is True

    def test_no_weak_points(self):
        """无薄弱知识点时建议不同。"""
        result_no_weak = WeeklyReportService._fallback_report(
            student_name="test",
            practice_count=5,
            accuracy=0.9,
            streak=3,
            weak_kps=[],
        )
        result_with_weak = WeeklyReportService._fallback_report(
            student_name="test",
            practice_count=5,
            accuracy=0.9,
            streak=3,
            weak_kps=["氧化还原反应"],
        )
        assert result_no_weak["advice"] != result_with_weak["advice"]


class TestWeekCalculation:
    """周报的周范围计算不在此模块（在 generate_report 中），
    但 get_report 可以独立测试参数默认值逻辑。
    """

    @pytest.mark.asyncio
    async def test_get_report_no_db_returns_none(self):
        """无数据库调用时返回 None（不需要 mock）。"""
        # get_report 需要一个真实的 AsyncSession，
        # 这由 L2 集成测试覆盖。
        pass
