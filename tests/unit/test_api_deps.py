"""API deps 纯函数测试 — check_permission、get_pagination_params、UserContext。

不依赖 FastAPI Request、数据库连接。
"""

import pytest
from dataclasses import asdict

from app.api.deps import (
    UserContext,
    check_permission,
    get_pagination_params,
    require_permission,
    AUTH_WHITELIST_PREFIXES,
)


class TestUserContext:
    def test_construction(self):
        ctx = UserContext(
            user_id=42, role="teacher", sub_role="subject_lead",
            school_id=5, token_type="access",
        )
        assert ctx.user_id == 42
        assert ctx.role == "teacher"
        assert ctx.sub_role == "subject_lead"
        assert ctx.school_id == 5
        assert ctx.token_type == "access"

    def test_sub_role_can_be_none(self):
        ctx = UserContext(user_id=1, role="student", sub_role=None,
                          school_id=None, token_type="access")
        assert ctx.sub_role is None

    def test_school_id_can_be_none(self):
        ctx = UserContext(user_id=1, role="parent", sub_role=None,
                          school_id=None, token_type="access")
        assert ctx.school_id is None

    def test_is_dataclass(self):
        ctx = UserContext(user_id=1, role="teacher", sub_role=None,
                          school_id=5, token_type="access")
        d = asdict(ctx)
        assert d["user_id"] == 1
        assert d["role"] == "teacher"


class TestCheckPermission:
    """check_permission(role, resource, action, sub_role) — 纯权限矩阵查找。"""

    # ── Admin (system_admin) ──
    def test_admin_full_access_school(self):
        assert check_permission("system_admin", "school", "create") is True
        assert check_permission("system_admin", "school", "delete") is True

    def test_admin_access_exam(self):
        assert check_permission("system_admin", "exam", "read") is True
        assert check_permission("system_admin", "exam", "create") is True

    def test_admin_cannot_delete_exam(self):
        """考试资源没有 delete 权限。"""
        assert check_permission("system_admin", "exam", "delete") is False

    # ── academic_admin (教务管理员) ──
    def test_academic_admin_school_read_only(self):
        assert check_permission("academic_admin", "school", "read") is True
        assert check_permission("academic_admin", "school", "create") is False

    def test_academic_admin_full_class(self):
        assert check_permission("academic_admin", "class", "delete") is True

    # ── subject_lead (学科组长) ──
    def test_subject_lead_read_only(self):
        assert check_permission("subject_lead", "student", "read") is True
        assert check_permission("subject_lead", "student", "create") is False
        assert check_permission("subject_lead", "exam", "create") is False

    # ── teacher ──
    def test_teacher_read_student(self):
        assert check_permission("teacher", "student", "read") is True

    def test_teacher_create_exam(self):
        assert check_permission("teacher", "exam", "create") is True

    def test_teacher_no_grade_create(self):
        assert check_permission("teacher", "grade", "create") is False

    # ── unknown role ──
    def test_unknown_role_always_denied(self):
        assert check_permission("hacker", "school", "read") is False
        assert check_permission("student", "school", "read") is False

    # ── unknown resource ──
    def test_unknown_resource_denied(self):
        assert check_permission("admin", "nonexistent", "read") is False

    # ── unknown action ──
    def test_unknown_action_denied(self):
        assert check_permission("admin", "school", "execute") is False

    # ── sub_role fallback ──
    def test_sub_role_takes_priority(self):
        """sub_role 优先于 identity role 进行权限查找。"""
        # teacher with sub_role=subject_lead → uses subject_lead permissions
        assert check_permission("teacher", "student", "create", sub_role="subject_lead") is False

    def test_sub_role_system_admin(self):
        assert check_permission("teacher", "school", "delete", sub_role="system_admin") is True

    def test_role_key_normalization(self):
        """'admin' role name normalized to 'admin' in matrix."""
        assert check_permission("admin", "school", "read") is True
        assert check_permission("admin", "school", "create") is True


class TestGetPaginationParams:
    """分页参数校验 — 纯函数，无依赖。"""

    @pytest.mark.asyncio
    async def test_defaults(self):
        params = await get_pagination_params()
        assert params == {"limit": 20, "offset": 0, "sort_by": "created_at", "order": "desc"}

    @pytest.mark.asyncio
    async def test_custom_values(self):
        params = await get_pagination_params(limit=10, offset=5, sort_by="name", order="asc")
        assert params == {"limit": 10, "offset": 5, "sort_by": "name", "order": "asc"}

    @pytest.mark.asyncio
    async def test_limit_clamped_min(self):
        params = await get_pagination_params(limit=0)
        assert params["limit"] == 1

    @pytest.mark.asyncio
    async def test_limit_clamped_max(self):
        params = await get_pagination_params(limit=200)
        assert params["limit"] == 100

    @pytest.mark.asyncio
    async def test_offset_clamped_min(self):
        params = await get_pagination_params(offset=-1)
        assert params["offset"] == 0

    @pytest.mark.asyncio
    async def test_order_invalid_clamped(self):
        params = await get_pagination_params(order="random")
        assert params["order"] == "desc"


class TestRequirePermission:
    """require_permission 工厂函数 — 返回一个 FastAPI dependency callable。"""

    def test_returns_callable(self):
        checker = require_permission("exam", "read")
        assert callable(checker)

    def test_returns_async_function(self):
        import inspect
        checker = require_permission("exam", "read")
        assert inspect.iscoroutinefunction(checker)


class TestAuthWhitelist:
    def test_contains_docs(self):
        assert any(p == "/docs" for p in AUTH_WHITELIST_PREFIXES)

    def test_contains_auth_endpoint(self):
        assert any(p == "/api/v1/auth/" for p in AUTH_WHITELIST_PREFIXES)

    def test_contains_health(self):
        assert any(p == "/health" for p in AUTH_WHITELIST_PREFIXES)
