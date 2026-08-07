"""Security token 测试 — create_access_token, create_refresh_token, create_token_pair.

覆盖 JWT 载荷结构、过期时间、可选字段 school_id/sub_role。
"""

import time
import pytest
from jose import jwt

from app.config import JWT_SECRET, JWT_ALGORITHM
from app.core.security import (
    create_access_token,
    create_refresh_token,
    create_token_pair,
    decode_token,
)


class TestCreateAccessToken:
    def test_returns_string(self):
        token = create_access_token(user_id=1, role="teacher")
        assert isinstance(token, str)
        assert token.count(".") == 2  # JWT 三段式

    def test_decodable(self):
        token = create_access_token(user_id=42, role="student")
        payload = decode_token(token)
        assert payload["user_id"] == 42
        assert payload["role"] == "student"

    def test_token_type_is_access(self):
        token = create_access_token(user_id=1, role="teacher")
        payload = decode_token(token)
        assert payload["type"] == "access"

    def test_has_iat_and_exp(self):
        token = create_access_token(user_id=1, role="teacher")
        payload = decode_token(token)
        assert "iat" in payload
        assert "exp" in payload
        assert payload["exp"] > payload["iat"]

    def test_exp_is_8_hours(self):
        """Access token 过期时间为 8 小时（480 分钟）。"""
        token = create_access_token(user_id=1, role="teacher")
        payload = decode_token(token)
        delta = payload["exp"] - payload["iat"]
        assert delta == 480 * 60  # 480 minutes in seconds

    def test_with_school_id(self):
        token = create_access_token(user_id=1, role="teacher", school_id=5)
        payload = decode_token(token)
        assert payload["school_id"] == 5

    def test_without_school_id(self):
        """Parent 角色不携带 school_id（23号 §八.4）。"""
        token = create_access_token(user_id=1, role="parent")
        payload = decode_token(token)
        assert "school_id" not in payload

    def test_with_sub_role(self):
        token = create_access_token(
            user_id=1, role="teacher", school_id=3, sub_role="subject_lead"
        )
        payload = decode_token(token)
        assert payload["sub_role"] == "subject_lead"

    def test_without_sub_role(self):
        token = create_access_token(user_id=1, role="student")
        payload = decode_token(token)
        assert "sub_role" not in payload

    def test_large_user_id(self):
        token = create_access_token(user_id=999999, role="teacher")
        payload = decode_token(token)
        assert payload["user_id"] == 999999


class TestCreateRefreshToken:
    def test_returns_string(self):
        token = create_refresh_token(user_id=1, role="teacher")
        assert isinstance(token, str)
        assert token.count(".") == 2

    def test_token_type_is_refresh(self):
        token = create_refresh_token(user_id=1, role="teacher")
        payload = decode_token(token)
        assert payload["type"] == "refresh"

    def test_exp_is_7_days(self):
        """Refresh token 过期时间为 7 天。"""
        token = create_refresh_token(user_id=1, role="teacher")
        payload = decode_token(token)
        delta = payload["exp"] - payload["iat"]
        assert delta == 7 * 24 * 3600

    def test_with_optional_fields(self):
        token = create_refresh_token(
            user_id=10, role="teacher", school_id=3, sub_role="teacher"
        )
        payload = decode_token(token)
        assert payload["user_id"] == 10
        assert payload["school_id"] == 3
        assert payload["sub_role"] == "teacher"


class TestCreateTokenPair:
    def test_returns_dict_with_both_tokens(self):
        pair = create_token_pair(user_id=1, role="teacher")
        assert "token" in pair
        assert "refresh_token" in pair
        assert isinstance(pair["token"], str)
        assert isinstance(pair["refresh_token"], str)

    def test_tokens_are_different(self):
        pair = create_token_pair(user_id=1, role="teacher")
        assert pair["token"] != pair["refresh_token"]

    def test_both_tokens_decodable(self):
        pair = create_token_pair(user_id=7, role="student")
        access_payload = decode_token(pair["token"])
        refresh_payload = decode_token(pair["refresh_token"])
        assert access_payload["user_id"] == 7
        assert access_payload["type"] == "access"
        assert refresh_payload["user_id"] == 7
        assert refresh_payload["type"] == "refresh"

    def test_forward_optional_fields(self):
        pair = create_token_pair(
            user_id=3, role="teacher", school_id=8, sub_role="academic_admin"
        )
        access = decode_token(pair["token"])
        refresh = decode_token(pair["refresh_token"])
        assert access["school_id"] == 8
        assert access["sub_role"] == "academic_admin"
        assert refresh["school_id"] == 8

    def test_parent_no_school_id(self):
        pair = create_token_pair(user_id=1, role="parent")
        access = decode_token(pair["token"])
        assert "school_id" not in access


class TestAlgorithmAndSecret:
    def test_algorithm_is_hs256(self):
        token = create_access_token(user_id=1, role="teacher")
        # jwt.decode with correct secret succeeds
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        assert payload["user_id"] == 1

    def test_wrong_secret_rejected(self):
        token = create_access_token(user_id=1, role="teacher")
        with pytest.raises(Exception):
            jwt.decode(token, "wrong-secret", algorithms=[JWT_ALGORITHM])

    def test_wrong_algorithm_rejected(self):
        token = create_access_token(user_id=1, role="teacher")
        with pytest.raises(Exception):
            jwt.decode(token, JWT_SECRET, algorithms=["HS512"])
