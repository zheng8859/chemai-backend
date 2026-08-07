"""API dependencies — authentication, authorization, permission checking.

Three-layer permission architecture (23号 §七):

Layer 1: HTTP Middleware (global) — JWT verification on all /api/* except whitelist
Layer 2: get_current_user — decode token, return UserContext with role/school_id
Layer 3: require_permission — per-endpoint resource × action check against ROLE_PERMISSIONS

Usage:
    from app.api.deps import get_current_user, require_permission, UserContext

    @router.get("/students")
    async def list_students(
        db = Depends(get_db),
        user: UserContext = Depends(get_current_user),
    ):
        ...

    @router.post("/students")
    async def create_student(
        db = Depends(get_db),
        user: UserContext = Depends(require_permission("student", "create")),
    ):
        ...
"""

from dataclasses import dataclass, field
from functools import wraps
from typing import Callable

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.security import decode_token
from ..infrastructure.database import get_db


# ═══════════════════════════════════════════════════════════
# Data structures
# ═══════════════════════════════════════════════════════════

@dataclass
class UserContext:
    """Authenticated user context extracted from JWT."""
    user_id: int
    role: str              # teacher | student | parent
    sub_role: str | None   # Teacher.sub_role (null for student/parent)
    school_id: int | None  # None for parent
    token_type: str        # access | refresh


# ═══════════════════════════════════════════════════════════
# ROLE_PERMISSIONS matrix (23号 §二)
# ═══════════════════════════════════════════════════════════

# Permission entries: set of actions per (resource, role)
# Roles: admin | academic_admin | subject_lead | teacher | student | parent
_RESOURCE_MATRIX: dict[str, dict[str, set[str]]] = {
    "school": {
        "admin": {"create", "read", "update", "delete"},
        "academic_admin": {"read"},
        "subject_lead": {"read"},
        "teacher": {"read"},
    },
    "grade": {
        "admin": {"create", "read", "update", "delete"},
        "academic_admin": {"create", "read", "update"},
        "subject_lead": {"read"},
        "teacher": {"read"},
        "student": {"read"},
    },
    "class": {
        "admin": {"create", "read", "update", "delete"},
        "academic_admin": {"create", "read", "update", "delete"},
        "subject_lead": {"read"},
        "teacher": {"read"},
    },
    "teacher": {
        "admin": {"create", "read", "update", "delete"},
        "academic_admin": {"read", "update"},
        "subject_lead": {"read"},
        "teacher": {"read"},
    },
    "student": {
        "admin": {"create", "read", "update", "delete"},
        "academic_admin": {"create", "read", "update", "delete"},
        "subject_lead": {"read"},
        "teacher": {"read"},
    },
    "analysis": {
        "admin": {"read"},
        "academic_admin": {"read"},
        "subject_lead": {"read"},
        "teacher": {"read"},
    },
    "exam": {
        "admin": {"create", "read"},
        "academic_admin": {"read"},
        "subject_lead": {"read"},
        "teacher": {"create", "read"},
    },
    "question": {
        "admin": {"create", "read"},
        "academic_admin": {"read"},
        "subject_lead": {"read"},
        "teacher": {"create", "read"},
    },
    "ocr": {
        "admin": {"create", "read"},
        "academic_admin": {"read"},
        "subject_lead": {"read"},
        "teacher": {"create", "read"},
    },
    "grading": {
        "admin": {"create", "read"},
        "academic_admin": {"read"},
        "subject_lead": {"read"},
        "teacher": {"create", "read"},
    },
}

# Parent permissions: only self_data read for bound children
# Student permissions: self_data read, assignment read, grade read
# Both are enforced at endpoint level, not via this matrix


def check_permission(role: str, resource: str, action: str, sub_role: str | None = None) -> bool:
    """Check if a role has permission for a resource + action.

    Returns True if allowed, False otherwise.
    Uses sub_role for permission lookup with fallback to role if sub_role is None.
    Admin role (system_admin) mapped to "admin" in matrix.
    """
    # Use sub_role for permission resolution, fall back to identity role
    lookup_role = sub_role if sub_role else role

    # Normalize teacher sub-roles to matrix keys
    role_key = {
        "system_admin": "admin",
        "academic_admin": "academic_admin",
        "subject_lead": "subject_lead",
        "teacher": "teacher",
        "admin": "admin",
    }.get(lookup_role, lookup_role)

    resource_perms = _RESOURCE_MATRIX.get(resource, {})
    allowed_actions = resource_perms.get(role_key, set())
    return action in allowed_actions


# ═══════════════════════════════════════════════════════════
# Layer 2: get_current_user
# ═══════════════════════════════════════════════════════════

# Paths exempt from authentication (23号 §七.1, 35号 §五)
AUTH_WHITELIST_PREFIXES: tuple[str, ...] = (
    "/docs",
    "/redoc",
    "/openapi.json",
    "/health",
    "/api/v1/auth/",
)


async def get_current_user(request: Request) -> UserContext:
    """Extract and validate JWT from Authorization header.

    Raises 401 if token is missing, invalid, or expired.
    Skips whitelisted paths.
    """
    # Skip auth for whitelisted paths
    path = request.url.path
    if any(path.startswith(prefix) for prefix in AUTH_WHITELIST_PREFIXES):
        return UserContext(user_id=0, role="anonymous", sub_role=None, school_id=None, token_type="none")

    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未提供有效的认证令牌",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = auth_header[7:]  # strip "Bearer "
    try:
        payload = decode_token(token)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="令牌无效或已过期",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="请使用 access token",
        )

    return UserContext(
        user_id=payload["user_id"],
        role=payload.get("role", "unknown"),
        sub_role=payload.get("sub_role"),
        school_id=payload.get("school_id"),
        token_type=payload.get("type", "unknown"),
    )


# ═══════════════════════════════════════════════════════════
# Layer 3: require_permission
# ═══════════════════════════════════════════════════════════

def require_permission(resource: str, action: str):
    """Decorator-style permission check for FastAPI endpoints.

    Usage as a FastAPI dependency:
        @router.post("/exams")
        async def create_exam(user: UserContext = Depends(require_permission("exam", "create"))):
            ...

    This factory returns a dependency callable that:
    1. Extracts the current user via get_current_user
    2. Checks the permission matrix
    3. Returns UserContext if allowed, raises 403 if denied
    """

    async def _checker(
        request: Request,
        user: UserContext = Depends(get_current_user),
    ) -> UserContext:
        if user.role == "anonymous":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="请先登录",
            )

        if not check_permission(user.role, resource, action, user.sub_role):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"权限不足：需要 {resource}:{action}",
            )

        return user

    # Make the dependency look like get_current_user for FastAPI Depends()
    return _checker


# ═══════════════════════════════════════════════════════════
# Scope helpers (data-level filtering)
# ═══════════════════════════════════════════════════════════

async def get_teacher_class_ids(
    db: AsyncSession,
    teacher_id: int,
) -> list[int]:
    """Get class IDs that a teacher is authorized to access (23号 §三.3)."""
    from ..models.user import TeacherClassSubject
    from sqlalchemy import select

    result = await db.execute(
        select(TeacherClassSubject.class_id).where(
            TeacherClassSubject.teacher_id == teacher_id
        )
    )
    return result.scalars().all()


# ═══════════════════════════════════════════════════════════
# Pagination helper (通用分页参数依赖)
# ═══════════════════════════════════════════════════════════

async def get_pagination_params(
    limit: int = 20,
    offset: int = 0,
    sort_by: str = "created_at",
    order: str = "desc",
) -> dict[str, int | str]:
    """FastAPI 依赖：解析并校验分页/排序参数。

    返回 dict 供 service 层直接使用。
    - limit: 1-100，默认 20
    - offset: >= 0，默认 0
    - sort_by: 排序字段名（service 层负责白名单校验）
    - order: "asc" 或 "desc"，默认 "desc"
    """
    if limit < 1:
        limit = 1
    elif limit > 100:
        limit = 100
    if offset < 0:
        offset = 0
    if order not in ("asc", "desc"):
        order = "desc"
    return {"limit": limit, "offset": offset, "sort_by": sort_by, "order": order}


# ═══════════════════════════════════════════════════════════
# Account → Student 映射（学生端 API 专用）
# ═══════════════════════════════════════════════════════════

async def resolve_student_id(db: AsyncSession, account_id: int) -> int | None:
    """由 Account.id 反查 Student.id。

    学生端前端使用 JWT user_id (Account.id) 作为路径/查询参数，
    但 service 层查询的是 Student.id。本函数完成映射。

    Returns None 当 Account 未关联 Student（调用方自行决定处理方式）。
    """
    from ..models.user import Student
    from sqlalchemy import select
    result = await db.execute(
        select(Student).where(Student.account_id == account_id)
    )
    student = result.scalar_one_or_none()
    return student.id if student else None
