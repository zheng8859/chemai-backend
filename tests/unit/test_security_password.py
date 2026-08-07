"""Security password hashing — hash_password and verify_password (补充这 2 个函数的覆盖)."""

import pytest
from app.core.security import hash_password, verify_password, decode_token
from jose import JWTError


class TestHashPassword:
    def test_returns_string(self):
        hashed = hash_password("mysecret")
        assert isinstance(hashed, str)
        assert len(hashed) > 0

    def test_different_salts_produce_different_hashes(self):
        h1 = hash_password("mysecret")
        h2 = hash_password("mysecret")
        assert h1 != h2  # bcrypt auto-salt → 每次不同

    def test_special_characters(self):
        hashed = hash_password("密码!@#$%^&*()")
        assert isinstance(hashed, str)

    def test_empty_password(self):
        """空密码也能 hash（业务层应拒绝，但安全层不限制）。"""
        hashed = hash_password("")
        assert isinstance(hashed, str)


class TestVerifyPassword:
    def test_correct_password(self):
        hashed = hash_password("mysecret")
        assert verify_password("mysecret", hashed) is True

    def test_wrong_password(self):
        hashed = hash_password("mysecret")
        assert verify_password("wrongpassword", hashed) is False

    def test_case_sensitive(self):
        hashed = hash_password("MySecret")
        assert verify_password("mysecret", hashed) is False

    def test_empty_vs_nonempty(self):
        hashed = hash_password("secret")
        assert verify_password("", hashed) is False

    def test_unicode_password(self):
        """中文密码。"""
        hashed = hash_password("密码123")
        assert verify_password("密码123", hashed) is True
        assert verify_password("密码124", hashed) is False


class TestDecodeTokenEdgeCases:
    def test_invalid_token_raises_jwt_error(self):
        with pytest.raises(JWTError):
            decode_token("not.a.valid.token")

    def test_empty_token_raises(self):
        with pytest.raises(JWTError):
            decode_token("")

    def test_tampered_token_raises(self):
        """篡改过的 token 无法解码。"""
        from app.core.security import create_access_token
        token = create_access_token(user_id=1, role="teacher")
        # 修改 token 中间的 payload 部分
        parts = token.split(".")
        tampered = parts[0] + ".tampered." + parts[2]
        with pytest.raises(JWTError):
            decode_token(tampered)
