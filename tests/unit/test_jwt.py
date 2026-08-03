"""Test JWT token creation — sub_role, school_id in access and refresh tokens."""

import pytest

from app.core.security import (
    create_access_token,
    create_refresh_token,
    create_token_pair,
    decode_token,
)


class TestAccessToken:
    def test_contains_sub_role(self):
        token = create_access_token(user_id=1, role="teacher", school_id=1, sub_role="system_admin")
        payload = decode_token(token)
        assert payload["user_id"] == 1
        assert payload["role"] == "teacher"
        assert payload["sub_role"] == "system_admin"
        assert payload["school_id"] == 1
        assert payload["type"] == "access"

    def test_sub_role_null_for_student(self):
        token = create_access_token(user_id=2, role="student", school_id=1, sub_role=None)
        payload = decode_token(token)
        assert payload["role"] == "student"
        assert "sub_role" not in payload  # null sub_role not written

    def test_no_school_id_for_parent(self):
        token = create_access_token(user_id=3, role="parent", school_id=None, sub_role=None)
        payload = decode_token(token)
        assert payload["role"] == "parent"
        assert "school_id" not in payload


class TestRefreshToken:
    def test_contains_sub_role_and_school_id(self):
        token = create_refresh_token(user_id=1, role="teacher", school_id=1, sub_role="teacher")
        payload = decode_token(token)
        assert payload["role"] == "teacher"
        assert payload["sub_role"] == "teacher"
        assert payload["school_id"] == 1
        assert payload["type"] == "refresh"


class TestTokenPair:
    def test_both_tokens_carry_metadata(self):
        pair = create_token_pair(user_id=1, role="teacher", school_id=1, sub_role="system_admin")
        access = decode_token(pair["token"])
        refresh = decode_token(pair["refresh_token"])
        assert access["sub_role"] == "system_admin"
        assert refresh["sub_role"] == "system_admin"
        assert access["type"] == "access"
        assert refresh["type"] == "refresh"
