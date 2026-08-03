"""Auth router — login, apply, register, token refresh.

Endpoints (45-数据模型与认证体系):
  POST /api/auth/login           — unified phone-based login
  POST /api/auth/apply           — teacher application registration
  POST /api/auth/register/parent — parent registration with bind_code
  POST /api/auth/refresh         — refresh access token
  POST /api/students/batch       — teacher batch-creates students
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.database import get_db
from ...services.auth_service import AuthService, AuthError
from ...schemas.auth import (
    LoginRequest,
    TeacherApplyRequest,
    ParentRegisterRequest,
    StudentBatchCreateRequest,
    StudentActivateRequest,
    TokenResponse,
    RefreshRequest,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])
student_router = APIRouter(prefix="/api/students", tags=["students"])


@router.post("/login", response_model=TokenResponse)
async def login(request: LoginRequest, db: AsyncSession = Depends(get_db)):
    """Authenticate user by phone + password and return tokens."""
    try:
        return await AuthService.login(db, request)
    except AuthError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"detail": e.detail, "error_code": e.error_code},
        )


@router.post("/apply", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def apply(request: TeacherApplyRequest, db: AsyncSession = Depends(get_db)):
    """Submit teacher application (Account+Teacher+Application created)."""
    try:
        return await AuthService.apply(db, request)
    except AuthError as e:
        status_map = {
            "DUPLICATE_RESOURCE": status.HTTP_400_BAD_REQUEST,
        }
        http_status = status_map.get(e.error_code, status.HTTP_400_BAD_REQUEST)
        raise HTTPException(
            status_code=http_status,
            detail={"detail": e.detail, "error_code": e.error_code},
        )


@router.post("/register/parent", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register_parent(request: ParentRegisterRequest, db: AsyncSession = Depends(get_db)):
    """Register a parent account with valid bind_code."""
    try:
        return await AuthService.parent_register(db, request)
    except AuthError as e:
        status_map = {
            "DUPLICATE_RESOURCE": status.HTTP_400_BAD_REQUEST,
            "RESOURCE_NOT_FOUND": status.HTTP_400_BAD_REQUEST,
        }
        http_status = status_map.get(e.error_code, status.HTTP_400_BAD_REQUEST)
        raise HTTPException(
            status_code=http_status,
            detail={"detail": e.detail, "error_code": e.error_code},
        )


@router.post("/refresh")
async def refresh(request: RefreshRequest):
    """Exchange a refresh token for a new access token pair."""
    try:
        tokens = await AuthService.refresh_token(request.refresh_token)
        return {"success": True, **tokens}
    except AuthError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"detail": e.detail, "error_code": e.error_code},
        )


@router.post("/activate")
async def activate(request: StudentActivateRequest, db: AsyncSession = Depends(get_db)):
    """Student activates account on first login — sets phone, password, is_activated."""
    try:
        await AuthService.student_activate(db, request.account_id, request.phone, request.new_password)
        return {"success": True, "message": "账号已激活"}
    except AuthError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"detail": e.detail, "error_code": e.error_code},
        )


@student_router.post("/batch")
async def batch_create_students(request: StudentBatchCreateRequest, db: AsyncSession = Depends(get_db)):
    """Teacher batch-creates student accounts."""
    try:
        result = await AuthService.student_batch_create(
            db, [s.model_dump() for s in request.students], request.class_id, request.school_id
        )
        return {"success": True, "students": result}
    except AuthError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"detail": e.detail, "error_code": e.error_code},
        )
