"""Test RBAC permissions — check_permission with sub_role."""

import pytest

from app.api.deps import check_permission, UserContext


class TestCheckPermission:
    def test_system_admin_can_create_school(self):
        assert check_permission("teacher", "school", "create", "system_admin") is True

    def test_teacher_cannot_create_school(self):
        assert check_permission("teacher", "school", "create", "teacher") is False

    def test_teacher_can_read_school(self):
        assert check_permission("teacher", "school", "read", "teacher") is True

    def test_sub_role_fallback_to_role(self):
        """When sub_role is None, fall back to identity role."""
        assert check_permission("teacher", "school", "read", None) is True
        assert check_permission("teacher", "school", "create", None) is False

    def test_academic_admin_can_manage_class(self):
        assert check_permission("teacher", "class", "create", "academic_admin") is True
        assert check_permission("teacher", "class", "delete", "academic_admin") is True

    def test_subject_lead_read_only(self):
        assert check_permission("teacher", "exam", "read", "subject_lead") is True
        assert check_permission("teacher", "exam", "create", "subject_lead") is False


class TestUserContext:
    def test_has_sub_role_field(self):
        ctx = UserContext(user_id=1, role="teacher", sub_role="system_admin", school_id=1, token_type="access")
        assert ctx.sub_role == "system_admin"

    def test_sub_role_none_for_parent(self):
        ctx = UserContext(user_id=2, role="parent", sub_role=None, school_id=None, token_type="access")
        assert ctx.sub_role is None
        assert ctx.school_id is None
