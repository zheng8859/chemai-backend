"""Homework service 测试 — error class + stub method。

Service CRUD 方法依赖 AsyncSession + model_validate 链，
需在 L2 集成测试中覆盖（使用真实数据库）。
"""

import pytest

from app.services.homework_service import HomeworkService, HomeworkError


class TestHomeworkError:
    def test_is_exception(self):
        err = HomeworkError("绑定失败")
        assert isinstance(err, Exception)

    def test_default_error_code(self):
        err = HomeworkError("资源不存在")
        assert err.error_code == "RESOURCE_NOT_FOUND"

    def test_custom_error_code(self):
        err = HomeworkError("绑定码无效", error_code="INVALID_BIND_CODE")
        assert err.error_code == "INVALID_BIND_CODE"

    def test_detail_preserved(self):
        err = HomeworkError("学生不存在: id=999")
        assert "id=999" in err.detail

    def test_string_repr(self):
        err = HomeworkError("测试错误")
        assert "测试错误" in str(err)


class TestSendExamReports:
    """send_exam_reports 是纯 stub 方法，无需数据库。"""

    @pytest.mark.asyncio
    async def test_returns_success_dict(self):
        import asyncio
        result = await HomeworkService.send_exam_reports(None, exam_id=1)
        assert result["success"] is True
        assert result["sent_count"] == 0
        assert result["failed_count"] == 0

