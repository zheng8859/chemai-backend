"""Auth API 集成测试 — 教师申请/登录、家长注册、学生激活、Token 刷新。

覆盖 auth_service 全部端点。
"""

import pytest


class TestTeacherApply:
    """POST /api/v1/auth/apply — 教师注册申请。"""

    @pytest.mark.anyio
    async def test_apply_success(self, async_client, school):
        resp = await async_client.post("/api/v1/auth/apply", json={
            "phone": "13800000001",
            "password": "test123456",
            "name": "张老师",
            "school_id": school["id"],
        })
        assert resp.status_code == 201
        data = resp.json()
        assert "token" in data
        assert data["role"] == "teacher"

    @pytest.mark.anyio
    async def test_login_before_approval_blocked(self, async_client, school):
        """教师申请后 status=pending，登录应被拒绝。"""
        # 先申请
        resp = await async_client.post("/api/v1/auth/apply", json={
            "phone": "13800000002",
            "password": "test123456",
            "name": "待审批教师",
            "school_id": school["id"],
        })
        assert resp.status_code == 201

        # 尝试登录
        resp = await async_client.post("/api/v1/auth/login", json={
            "phone": "13800000002",
            "password": "test123456",
        })
        assert resp.status_code == 401

    @pytest.mark.anyio
    async def test_duplicate_phone_rejected(self, async_client, school):
        """重复手机号申请被拒。"""
        payload = {
            "phone": "13800000003",
            "password": "test123456",
            "name": "李老师",
            "school_id": school["id"],
        }
        resp = await async_client.post("/api/v1/auth/apply", json=payload)
        assert resp.status_code == 201

        resp = await async_client.post("/api/v1/auth/apply", json=payload)
        assert resp.status_code == 400

    @pytest.mark.anyio
    async def test_short_password_rejected(self, async_client, school):
        """密码不足 6 位。"""
        resp = await async_client.post("/api/v1/auth/apply", json={
            "phone": "13800000004",
            "password": "12345",
            "name": "短密码",
            "school_id": school["id"],
        })
        assert resp.status_code == 422

    @pytest.mark.anyio
    async def test_nonexistent_school_allowed_by_sqlite(self, async_client):
        """申请时 school_id 不存在 —— SQLite 不强制 FK，服务层也未校验。

        TODO: 在 AuthService.apply() 中加 school_id 存在性校验，然后改为 expect 400。
        """
        resp = await async_client.post("/api/v1/auth/apply", json={
            "phone": "13800000005",
            "password": "test123456",
            "name": "无校教师",
            "school_id": 99999,
        })
        assert resp.status_code == 201  # SQLite 允许此操作


# ── 辅助：直接在数据库创建已审批教师 ───────────────────

async def _create_approved_teacher(db_session, phone, password, school_id, name):
    """直接在 DB 创建 Account + approved Teacher（绕过 HTTP API 审批流程）。"""
    from app.models.user import Account, Teacher
    from app.core.security import hash_password
    from app.core.enums import AccountRole, TeacherAccountStatus

    account = Account(
        phone=phone, password_hash=hash_password(password),
        role=AccountRole.teacher,
    )
    db_session.add(account)
    await db_session.flush()

    teacher = Teacher(
        account_id=account.id, school_id=school_id,
        name=name, status=TeacherAccountStatus.approved,
    )
    db_session.add(teacher)
    await db_session.flush()
    return account


class TestLogin:
    """POST /api/v1/auth/login — 统一手机号登录。"""

    @pytest.mark.anyio
    async def test_login_approved_teacher(self, async_client, school, db_session):
        """已审批教师可登录获取真实 token。"""
        await _create_approved_teacher(
            db_session, "13810000001", "pass123456", school["id"], "已审批教师",
        )

        resp = await async_client.post("/api/v1/auth/login", json={
            "phone": "13810000001",
            "password": "pass123456",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["token"]) > 0
        assert len(data["refresh_token"]) > 0
        assert data["role"] == "teacher"

    @pytest.mark.anyio
    async def test_wrong_password(self, async_client, school, db_session):
        """密码错误返回 401。"""
        await _create_approved_teacher(
            db_session, "13810000002", "correct", school["id"], "密码测试",
        )

        resp = await async_client.post("/api/v1/auth/login", json={
            "phone": "13810000002",
            "password": "wrongpassword",
        })
        assert resp.status_code == 401

    @pytest.mark.anyio
    async def test_nonexistent_phone(self, async_client):
        """不存在的手机号 → 401。"""
        resp = await async_client.post("/api/v1/auth/login", json={
            "phone": "13999999999",
            "password": "anything",
        })
        assert resp.status_code == 401


class TestRefreshToken:
    """POST /api/v1/auth/refresh — 刷新 access token。"""

    @pytest.mark.anyio
    async def test_refresh_valid_token(self, async_client, school, db_session):
        """有效 refresh_token 可换取新 token pair。"""
        from app.core.security import create_refresh_token

        account = await _create_approved_teacher(
            db_session, "13810000003", "pass", school["id"], "刷新测试",
        )

        refresh_token = create_refresh_token(
            user_id=account.id, role="teacher",
            school_id=school["id"],
        )

        resp = await async_client.post("/api/v1/auth/refresh", json={
            "refresh_token": refresh_token,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert len(data["token"]) > 0

    @pytest.mark.anyio
    async def test_refresh_invalid_token(self, async_client):
        """无效 refresh_token → 401。"""
        resp = await async_client.post("/api/v1/auth/refresh", json={
            "refresh_token": "invalid.token.here",
        })
        assert resp.status_code == 401


class TestParentRegister:
    """POST /api/v1/auth/register/parent — 家长注册。"""

    @pytest.mark.anyio
    async def test_parent_register_success(self, async_client, db_session, school, class_):
        """有效绑定码注册家长成功。"""
        from app.models.user import Account, Student
        from app.core.enums import AccountRole, StudentStatus

        # 先创建学生 Account + Student（带 bind_code）
        student_account = Account(
            phone="", password_hash="hash",
            role=AccountRole.student,
        )
        db_session.add(student_account)
        await db_session.flush()

        student = Student(
            account_id=student_account.id, class_id=class_["id"],
            school_id=school["id"],
            name="测试学生", student_id="S001",
            bind_code="ABC123", is_activated=True,
            status=StudentStatus.approved,
        )
        db_session.add(student)
        await db_session.flush()

        resp = await async_client.post("/api/v1/auth/register/parent", json={
            "phone": "13820000001",
            "password": "pass123456",
            "bind_code": "ABC123",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["role"] == "parent"
        assert len(data["token"]) > 0

    @pytest.mark.anyio
    async def test_parent_register_invalid_bind_code(self, async_client):
        """不存在的绑定码（6 位）→ 400。"""
        resp = await async_client.post("/api/v1/auth/register/parent", json={
            "phone": "13820000002",
            "password": "pass123456",
            "bind_code": "ZZZZZZ",
        })
        assert resp.status_code == 400


class TestStudentActivate:
    """POST /api/v1/auth/activate — 学生激活账号。"""

    @pytest.mark.anyio
    async def test_activate_success(self, async_client, db_session, school, class_):
        """未激活学生可激活账号。"""
        from app.models.user import Account, Student
        from app.core.enums import AccountRole, StudentStatus

        account = Account(
            phone="", password_hash="hash",
            role=AccountRole.student,
        )
        db_session.add(account)
        await db_session.flush()

        student = Student(
            account_id=account.id, class_id=class_["id"],
            school_id=school["id"],
            name="待激活学生", student_id="S002",
            is_activated=False, status=StudentStatus.approved,
        )
        db_session.add(student)
        await db_session.flush()

        resp = await async_client.post("/api/v1/auth/activate", json={
            "account_id": account.id,
            "phone": "13830000001",
            "new_password": "newpass123",
        })
        assert resp.status_code == 200
        assert resp.json()["success"] is True

        # 激活后应可登录
        resp = await async_client.post("/api/v1/auth/login", json={
            "phone": "13830000001",
            "password": "newpass123",
        })
        assert resp.status_code == 200


class TestAuthWhitelist:
    """验证 auth 端点无需 token 即可访问（白名单）。"""

    @pytest.mark.anyio
    async def test_login_no_auth_header(self, async_client):
        resp = await async_client.post("/api/v1/auth/login", json={
            "phone": "13800000000", "password": "test",
        })
        assert resp.status_code in (200, 401)  # 不要求 token

    @pytest.mark.anyio
    async def test_apply_no_auth_header(self, async_client, school):
        resp = await async_client.post("/api/v1/auth/apply", json={
            "phone": "13840000001",
            "password": "test123456",
            "name": "白名单测试",
            "school_id": school["id"],
        })
        assert resp.status_code in (201, 400)
