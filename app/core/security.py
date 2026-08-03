"""Auth security — JWT token handling and password hashing.

Aligned with 23号 §八, 35号 §五.
- Algorithm: HS256
- Access token: 8h (JWT_EXPIRE_MINUTES)
- Refresh token: 7d
- Stateless JWT (no server-side blacklist)
"""

from datetime import datetime, timedelta, timezone

import bcrypt
from jose import JWTError, jwt

from ..config import JWT_SECRET, JWT_ALGORITHM, JWT_EXPIRE_MINUTES

# ── Password hashing (direct bcrypt, no passlib) ──────────
# passlib 1.7.4 is incompatible with bcrypt 5.0.0.
# bcrypt.hashpw / checkpw are the standard interface.

# Token expiry
ACCESS_TOKEN_EXPIRE_MINUTES = JWT_EXPIRE_MINUTES  # 480 min (8h)
REFRESH_TOKEN_EXPIRE_DAYS = 7


def hash_password(password: str) -> str:
    """Hash a plaintext password with bcrypt (auto-salted, 12 rounds)."""
    return bcrypt.hashpw(
        password.encode("utf-8"),
        bcrypt.gensalt(rounds=12),
    ).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against a bcrypt hash."""
    return bcrypt.checkpw(
        plain_password.encode("utf-8"),
        hashed_password.encode("utf-8"),
    )


# ── JWT ───────────────────────────────────────────────────

def create_access_token(
    user_id: int,
    role: str,
    school_id: int | None = None,
    sub_role: str | None = None,
) -> str:
    """Create a JWT access token (24h expiry).

    Parent role does NOT carry school_id (23号 §八.4).
    sub_role is the Teacher.sub_role (null for student/parent).
    """
    now = datetime.now(timezone.utc)
    payload = {
        "user_id": user_id,
        "role": role,
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    if school_id is not None:
        payload["school_id"] = school_id
    if sub_role is not None:
        payload["sub_role"] = sub_role
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def create_refresh_token(
    user_id: int,
    role: str,
    school_id: int | None = None,
    sub_role: str | None = None,
) -> str:
    """Create a JWT refresh token (7d expiry). Carries metadata for rotation."""
    now = datetime.now(timezone.utc)
    payload = {
        "user_id": user_id,
        "role": role,
        "type": "refresh",
        "iat": now,
        "exp": now + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
    }
    if school_id is not None:
        payload["school_id"] = school_id
    if sub_role is not None:
        payload["sub_role"] = sub_role
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    """Decode and verify a JWT token. Raises JWTError on failure."""
    return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])


def create_token_pair(
    user_id: int,
    role: str,
    school_id: int | None = None,
    sub_role: str | None = None,
) -> dict:
    """Create both access + refresh tokens. Returns {token, refresh_token}.

    sub_role carries Teacher.sub_role for permission resolution (null for student/parent).
    """
    return {
        "token": create_access_token(user_id, role, school_id, sub_role),
        "refresh_token": create_refresh_token(user_id, role, school_id, sub_role),
    }
