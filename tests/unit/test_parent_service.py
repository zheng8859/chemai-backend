"""ParentService 单元测试 — error class + data structures。

Service CRUD 方法依赖 AsyncSession，在 L2 集成测试中覆盖。
"""

import pytest

from app.services.parent_service import ParentService, ParentError


class TestParentError:
    def test_is_exception(self):
        err = ParentError("绑定失败")
        assert isinstance(err, Exception)

    def test_default_error_code(self):
        err = ParentError("资源不存在")
        assert err.error_code == "RESOURCE_NOT_FOUND"

    def test_custom_error_code(self):
        err = ParentError("绑定码无效", error_code="INVALID_BIND_CODE")
        assert err.error_code == "INVALID_BIND_CODE"

    def test_detail_preserved(self):
        err = ParentError("学生不存在: id=999")
        assert "id=999" in err.detail

    def test_string_repr(self):
        err = ParentError("测试错误")
        assert "测试错误" in str(err)
