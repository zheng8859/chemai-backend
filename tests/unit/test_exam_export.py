"""考试导出服务纯函数测试 — section_name 编号、常量定义。

不依赖 python-docx Document 对象。
"""

import pytest

from app.services.exam_export_service import (
    _section_name,
    TYPE_LABELS,
    TYPE_ORDER,
    ExamExportError,
)


class TestSectionName:
    def test_first_section_choice(self):
        assert "一" in _section_name(1, "choice")
        assert "选择题" in _section_name(1, "choice")

    def test_second_section_fill_blank(self):
        assert "二" in _section_name(2, "fill_blank")
        assert "填空题" in _section_name(2, "fill_blank")

    def test_third_section_calculation(self):
        assert "三" in _section_name(3, "calculation")
        assert "计算题" in _section_name(3, "calculation")

    def test_fourth_section_experiment(self):
        assert "四" in _section_name(4, "experiment_inquiry")
        assert "实验题" in _section_name(4, "experiment_inquiry")

    def test_fifth_section_equation(self):
        assert "五" in _section_name(5, "equation_balancing")
        assert "推断题" in _section_name(5, "equation_balancing")

    def test_beyond_five_uses_number(self):
        """超过五的部分直接用数字。"""
        result = _section_name(6, "choice")
        assert result.startswith("6")

    def test_unknown_type_shows_raw(self):
        result = _section_name(1, "unknown_type")
        assert "unknown_type" in result


class TestTypeLabels:
    def test_all_five_types(self):
        assert len(TYPE_LABELS) == 5
        assert TYPE_LABELS["choice"] == "选择题"
        assert TYPE_LABELS["fill_blank"] == "填空题"
        assert TYPE_LABELS["calculation"] == "计算题"
        assert TYPE_LABELS["experiment_inquiry"] == "实验题"
        assert TYPE_LABELS["equation_balancing"] == "推断题"


class TestTypeOrder:
    def test_order_matches_labels(self):
        assert len(TYPE_ORDER) == 5
        for t in TYPE_ORDER:
            assert t in TYPE_LABELS

    def test_choice_first(self):
        assert TYPE_ORDER[0] == "choice"


class TestExamExportError:
    def test_is_exception(self):
        err = ExamExportError("测试错误")
        assert isinstance(err, Exception)

    def test_detail_preserved(self):
        err = ExamExportError("考试不存在: id=999")
        assert "考试不存在" in err.detail
        assert "999" in err.detail

    def test_string_repr(self):
        err = ExamExportError("错误信息")
        assert "错误信息" in str(err)
