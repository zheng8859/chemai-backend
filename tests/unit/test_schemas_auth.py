"""Auth schemas — LoginRequest, TeacherApplyRequest, TokenResponse, etc."""

import pytest
from pydantic import ValidationError

from app.schemas.auth import (
    LoginRequest,
    TeacherApplyRequest,
    ParentRegisterRequest,
    StudentBatchItem,
    StudentBatchCreateRequest,
    TokenResponse,
    StudentActivateRequest,
    RefreshRequest,
)


class TestLoginRequest:
    def test_valid(self):
        r = LoginRequest(phone="13800000000", password="demo123456")
        assert r.phone == "13800000000"

    def test_phone_required(self):
        with pytest.raises(ValidationError):
            LoginRequest(password="demo123456")

    def test_password_required(self):
        with pytest.raises(ValidationError):
            LoginRequest(phone="13800000000")

    def test_empty_phone_rejected(self):
        with pytest.raises(ValidationError):
            LoginRequest(phone="", password="x")


class TestTeacherApplyRequest:
    def test_valid(self):
        r = TeacherApplyRequest(
            phone="13900000001", password="pass1234",
            name="张老师", school_id=1,
        )
        assert r.name == "张老师"
        assert r.school_id == 1

    def test_password_too_short(self):
        with pytest.raises(ValidationError):
            TeacherApplyRequest(
                phone="13900000001", password="12345",
                name="张老师", school_id=1,
            )

    def test_name_required(self):
        with pytest.raises(ValidationError):
            TeacherApplyRequest(
                phone="13900000001", password="pass1234",
                name="", school_id=1,
            )


class TestParentRegisterRequest:
    def test_valid(self):
        r = ParentRegisterRequest(
            phone="13700000002", password="pass1234",
            bind_code="A1B2C3",
        )
        assert r.bind_code == "A1B2C3"

    def test_bind_code_too_short(self):
        with pytest.raises(ValidationError):
            ParentRegisterRequest(
                phone="13700000002", password="pass1234",
                bind_code="ABC",
            )

    def test_bind_code_too_long(self):
        with pytest.raises(ValidationError):
            ParentRegisterRequest(
                phone="13700000002", password="pass1234",
                bind_code="A1B2C3D",
            )


class TestStudentBatchItem:
    def test_valid(self):
        r = StudentBatchItem(
            name="小明", student_id="S2024001",
            initial_password="abc123",
        )
        assert r.name == "小明"
        assert r.student_id == "S2024001"


class TestStudentBatchCreateRequest:
    def test_valid(self):
        items = [
            StudentBatchItem(name="小明", student_id="S001", initial_password="p1"),
            StudentBatchItem(name="小红", student_id="S002", initial_password="p2"),
        ]
        r = StudentBatchCreateRequest(
            students=items, class_id=1, school_id=1,
        )
        assert len(r.students) == 2

    def test_empty_students_allowed_by_schema(self):
        """空列表在 schema 层不拒绝（业务层校验）。"""
        r = StudentBatchCreateRequest(students=[], class_id=1, school_id=1)
        assert r.students == []


class TestTokenResponse:
    def test_basic(self):
        r = TokenResponse(
            token="abc", refresh_token="def",
            user_id=1, name="张老师", role="teacher",
        )
        assert r.success is True
        assert r.sub_role is None
        assert r.school_id is None

    def test_with_sub_role_and_school(self):
        r = TokenResponse(
            token="abc", refresh_token="def",
            user_id=1, name="张老师", role="teacher",
            sub_role="system_admin", school_id=1,
        )
        assert r.sub_role == "system_admin"
        assert r.school_id == 1


class TestStudentActivateRequest:
    def test_valid(self):
        r = StudentActivateRequest(
            account_id=10, phone="13800000000",
            new_password="newpass123",
        )
        assert r.account_id == 10

    def test_short_password_rejected(self):
        with pytest.raises(ValidationError):
            StudentActivateRequest(
                account_id=10, phone="13800000000",
                new_password="12345",
            )


class TestRefreshRequest:
    def test_valid(self):
        r = RefreshRequest(refresh_token="some-refresh-token")
        assert r.refresh_token == "some-refresh-token"
