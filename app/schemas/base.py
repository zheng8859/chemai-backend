"""Base schemas — unified response format, pagination, error response.

Aligned with 35-API Design sections 1, 6, 7.
"""

from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict

T = TypeVar("T")


# ── Unified success response (35号 §一) ───────────────────
class SuccessResponse(BaseModel, Generic[T]):
    success: bool = True
    message: str = "操作成功"
    data: T | None = None


# ── Pagination (35号 §六) ─────────────────────────────────
class PaginationParams(BaseModel):
    limit: int = 20
    offset: int = 0
    sort_by: str = "created_at"
    order: str = "desc"  # asc | desc


class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int


# ── Error response (35号 §七) ─────────────────────────────
class ErrorResponse(BaseModel):
    detail: str
    error_code: str
    suggestion: str | None = None


# ── ORM-compatible base (Pydantic v2 from_attributes) ─────
class ORMBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)
