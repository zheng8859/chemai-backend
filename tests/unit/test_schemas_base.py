"""Base schemas — SuccessResponse, PaginationParams, PaginatedResponse, ErrorResponse, ORMBase."""

import pytest
from pydantic import ValidationError

from app.schemas.base import (
    SuccessResponse,
    PaginationParams,
    PaginatedResponse,
    ErrorResponse,
    ORMBase,
)


class TestSuccessResponse:
    def test_defaults(self):
        r = SuccessResponse()
        assert r.success is True
        assert r.message == "操作成功"
        assert r.data is None

    def test_with_typed_data(self):
        r = SuccessResponse[str](data="hello")
        assert r.data == "hello"

    def test_with_dict_data(self):
        r = SuccessResponse[dict](data={"id": 1})
        assert r.data == {"id": 1}

    def test_custom_message(self):
        r = SuccessResponse(message="完成")
        assert r.message == "完成"


class TestPaginationParams:
    def test_defaults(self):
        p = PaginationParams()
        assert p.limit == 20
        assert p.offset == 0
        assert p.sort_by == "created_at"
        assert p.order == "desc"

    def test_custom(self):
        p = PaginationParams(limit=50, offset=10, sort_by="name", order="asc")
        assert p.limit == 50
        assert p.offset == 10
        assert p.sort_by == "name"
        assert p.order == "asc"


class TestPaginatedResponse:
    def test_basic(self):
        r = PaginatedResponse[int](items=[1, 2, 3], total=100, limit=20, offset=0)
        assert r.items == [1, 2, 3]
        assert r.total == 100

    def test_empty(self):
        r = PaginatedResponse[str](items=[], total=0, limit=20, offset=0)
        assert r.items == []
        assert r.total == 0


class TestErrorResponse:
    def test_basic(self):
        r = ErrorResponse(detail="未找到", error_code="NOT_FOUND")
        assert r.detail == "未找到"
        assert r.error_code == "NOT_FOUND"
        assert r.suggestion is None

    def test_with_suggestion(self):
        r = ErrorResponse(
            detail="未找到", error_code="NOT_FOUND",
            suggestion="请检查 ID 是否正确"
        )
        assert r.suggestion == "请检查 ID 是否正确"


class TestORMBase:
    def test_config_from_attributes(self):
        """ORMBase 配置 from_attributes=True，支持从 ORM 对象构造。"""
        assert ORMBase.model_config.get("from_attributes") is True
