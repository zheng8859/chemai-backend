"""Auth service — login, register, token refresh business logic.

Handles multi-role account creation (teacher/student/parent) with the unified
Account + profile pattern. Parent uses independent auth flow (no school_id in JWT).
"""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..core.security import hash_password, verify_password, create_token_pair, decode_token
from ..core.enums import (
    AccountRole,
    TeacherRole,
    TeacherAccountStatus,
    StudentStatus,
    ApplicationStatus,
    BindingStatus,
    ParentRelation,
)
from ..models.user import Account, Teacher, Student, Parent
from ..schemas.auth import LoginRequest, TokenResponse, TeacherApplyRequest, ParentRegisterRequest


class AuthError(Exception):
    """Auth-related business error with error_code for API response mapping."""

    def __init__(self, detail: str, error_code: str = "AUTHENTICATION_REQUIRED"):
        self.detail = detail
        self.error_code = error_code
        super().__init__(detail)


class AuthService:
    """Stateless auth service. All DB operations go through the injected session."""

    # ── Login ──────────────────────────────────────────────

    @staticmethod
    async def login(db: AsyncSession, request: LoginRequest) -> TokenResponse:
        """Authenticate user with phone + password only. Role resolved from DB."""
        # Find account by phone
        result = await db.execute(
            select(Account).where(Account.phone == request.phone)
        )
        account = result.scalar_one_or_none()
        if account is None:
            raise AuthError("手机号或密码错误", "AUTHENTICATION_REQUIRED")

        # Verify password
        if not verify_password(request.password, account.password_hash):
            raise AuthError("手机号或密码错误", "AUTHENTICATION_REQUIRED")

        # Resolve profile for school_id, display name, and sub_role
        profile_name, school_id, sub_role = await AuthService._resolve_profile(db, account)

        # Check teacher approval status
        if account.role == AccountRole.teacher:
            teacher = await AuthService._get_teacher(db, account.id)
            if teacher and teacher.status != TeacherAccountStatus.approved:
                raise AuthError(
                    "账号尚未通过审核，请联系管理员",
                    "PERMISSION_DENIED",
                )

        # Check student activation
        if account.role == AccountRole.student:
            result = await db.execute(
                select(Student).where(Student.account_id == account.id)
            )
            student = result.scalar_one_or_none()
            if student and not student.is_activated:
                raise AuthError(
                    "请先激活账号",
                    "ACCOUNT_NOT_ACTIVATED",
                )

        tokens = create_token_pair(
            account.id, str(account.role), school_id, sub_role
        )
        return TokenResponse(
            token=tokens["token"],
            refresh_token=tokens["refresh_token"],
            user_id=account.id,
            name=profile_name,
            role=str(account.role),
            sub_role=sub_role,
            school_id=school_id,
        )

    # ── Register ───────────────────────────────────────────

    @staticmethod
    async def apply(db: AsyncSession, request: TeacherApplyRequest) -> TokenResponse:
        """Teacher application — creates Account+Teacher(pending)+TeacherApplication."""
        # Check phone uniqueness
        result = await db.execute(
            select(Account).where(Account.phone == request.phone)
        )
        if result.scalar_one_or_none() is not None:
            raise AuthError("手机号已注册", "DUPLICATE_RESOURCE")

        # Create account (pending approval)
        account = Account(
            phone=request.phone,
            password_hash=hash_password(request.password),
            role=AccountRole.teacher,
        )
        db.add(account)
        await db.flush()

        # Create teacher profile (pending)
        teacher = Teacher(
            account_id=account.id,
            school_id=request.school_id,
            name=request.name,
            status=TeacherAccountStatus.pending,
            role=TeacherRole.teacher,
        )
        db.add(teacher)

        # Create application record
        application = TeacherApplication(
            name=request.name,
            phone=request.phone,
            password_hash=hash_password(request.password),
            school_id=request.school_id,
            school_name="",
            status=ApplicationStatus.pending,
        )
        db.add(application)

        await db.commit()
        return TokenResponse(
            token="",
            refresh_token="",
            user_id=account.id,
            name=request.name,
            role="teacher",
            sub_role="teacher",
            school_id=request.school_id,
        )

    @staticmethod
    async def student_batch_create(
        db: AsyncSession, students: list[dict[str, str]], class_id: int, school_id: int
    ) -> list[dict[str, str | int]]:
        """Teacher batch-creates student accounts. Returns list of created students."""
        created: list[dict[str, str | int]] = []
        for s in students:
            # Create account with initial password
            account = Account(
                phone="",  # phone set during student activation
                password_hash=hash_password(s["initial_password"]),
                role=AccountRole.student,
            )
            db.add(account)
            await db.flush()

            student = Student(
                account_id=account.id,
                class_id=class_id,
                school_id=school_id,
                name=s["name"],
                student_id=s["student_id"],
                is_activated=False,
                status=StudentStatus.approved,
            )
            db.add(student)
            created.append({"account_id": account.id, "name": s["name"], "student_id": s["student_id"]})
        await db.commit()
        return created

    @staticmethod
    async def student_activate(db: AsyncSession, account_id: int, phone: str, new_password: str) -> None:
        """Student activates account on first login — sets phone, password, is_activated."""
        result = await db.execute(select(Student).where(Student.account_id == account_id))
        student = result.scalar_one_or_none()
        if student is None:
            raise AuthError("学生不存在", "RESOURCE_NOT_FOUND")
        if student.is_activated:
            raise AuthError("账号已激活", "ALREADY_ACTIVATED")

        # Update account
        result = await db.execute(select(Account).where(Account.id == account_id))
        account = result.scalar_one_or_none()
        if account:
            account.phone = phone
            account.password_hash = hash_password(new_password)

        student.is_activated = True
        await db.commit()

    @staticmethod
    async def parent_register(db: AsyncSession, request: ParentRegisterRequest) -> TokenResponse:
        """Parent registration — validates bind_code, creates Account+Parent+Binding."""
        # Find student by bind_code
        result = await db.execute(
            select(Student).where(Student.bind_code == request.bind_code)
        )
        student = result.scalar_one_or_none()
        if student is None:
            raise AuthError("绑定码无效", "RESOURCE_NOT_FOUND")

        # Check phone uniqueness
        result = await db.execute(
            select(Account).where(Account.phone == request.phone)
        )
        if result.scalar_one_or_none() is not None:
            raise AuthError("手机号已注册", "DUPLICATE_RESOURCE")

        # Create account
        account = Account(
            phone=request.phone,
            password_hash=hash_password(request.password),
            role=AccountRole.parent,
        )
        db.add(account)
        await db.flush()

        # Create parent profile
        parent = Parent(
            account_id=account.id,
            name=request.phone,  # default name = phone
        )
        db.add(parent)
        await db.flush()

        # Create binding from schemas.homework import StudentParentBinding
        from ..models.homework import StudentParentBinding
        binding = StudentParentBinding(
            student_id=student.id,
            parent_id=parent.id,
            status=BindingStatus.active,
            relationship=ParentRelation.other,
        )
        db.add(binding)

        await db.commit()

        tokens = create_token_pair(account.id, "parent", None, None)
        return TokenResponse(
            token=tokens["token"],
            refresh_token=tokens["refresh_token"],
            user_id=account.id,
            name=parent.name,
            role="parent",
            sub_role=None,
            school_id=None,
        )

    # ── Refresh ────────────────────────────────────────────

    @staticmethod
    async def refresh_token(refresh_token: str) -> dict:
        """Validate refresh token and issue new access token with preserved metadata."""
        try:
            payload = decode_token(refresh_token)
        except Exception:
            raise AuthError("refresh token 无效或已过期", "TOKEN_EXPIRED")

        if payload.get("type") != "refresh":
            raise AuthError("token 类型错误", "AUTHENTICATION_REQUIRED")

        user_id = payload["user_id"]
        role = payload["role"]
        sub_role = payload.get("sub_role")
        school_id = payload.get("school_id")

        new_access = create_token_pair(user_id, role, school_id, sub_role)
        return new_access

    # ── Helpers ────────────────────────────────────────────

    @staticmethod
    async def _resolve_profile(db: AsyncSession, account: Account) -> tuple[str, int | None, str | None]:
        """Resolve display name, school_id, and sub_role from profile tables."""
        if account.role == AccountRole.teacher:
            teacher = await AuthService._get_teacher(db, account.id)
            if teacher:
                return teacher.name, teacher.school_id, str(teacher.role)
        elif account.role == AccountRole.student:
            result = await db.execute(
                select(Student).where(Student.account_id == account.id)
            )
            student = result.scalar_one_or_none()
            if student:
                # Resolve school_id via Class→Grade→School chain
                from ..models.org import Class, Grade, School
                class_result = await db.execute(
                    select(Class).where(Class.id == student.class_id)
                )
                class_ = class_result.scalar_one_or_none()
                if class_:
                    grade_result = await db.execute(
                        select(Grade).where(Grade.id == class_.grade_id)
                    )
                    grade = grade_result.scalar_one_or_none()
                    if grade:
                        return student.name, grade.school_id, None
                return student.name, None, None
        elif account.role == AccountRole.parent:
            result = await db.execute(
                select(Parent).where(Parent.account_id == account.id)
            )
            parent = result.scalar_one_or_none()
            if parent:
                return parent.name, None, None  # parents have no school_id
        return account.phone, None, None

    @staticmethod
    async def _get_teacher(db: AsyncSession, account_id: int) -> Teacher | None:
        result = await db.execute(
            select(Teacher).where(Teacher.account_id == account_id)
        )
        return result.scalar_one_or_none()
