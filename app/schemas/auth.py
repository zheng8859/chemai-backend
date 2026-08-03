"""Auth schemas — login, apply, register, token response.

Aligned with 45-数据模型与认证体系.
"""

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    phone: str = Field(..., min_length=1, max_length=20)
    password: str = Field(..., min_length=1)


class TeacherApplyRequest(BaseModel):
    phone: str = Field(..., min_length=1, max_length=20)
    password: str = Field(..., min_length=6)
    name: str = Field(..., min_length=1, max_length=100)
    school_id: int


class ParentRegisterRequest(BaseModel):
    phone: str = Field(..., min_length=1, max_length=20)
    password: str = Field(..., min_length=6)
    bind_code: str = Field(..., min_length=6, max_length=6)


class StudentBatchItem(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    student_id: str = Field(..., min_length=1, max_length=50)
    initial_password: str = Field(..., min_length=1)


class StudentBatchCreateRequest(BaseModel):
    students: list[StudentBatchItem]
    class_id: int
    school_id: int


class TokenResponse(BaseModel):
    success: bool = True
    token: str
    refresh_token: str
    user_id: int
    name: str
    role: str
    sub_role: str | None = None
    school_id: int | None = None


class StudentActivateRequest(BaseModel):
    account_id: int
    phone: str = Field(..., min_length=1, max_length=20)
    new_password: str = Field(..., min_length=6)


class RefreshRequest(BaseModel):
    refresh_token: str
