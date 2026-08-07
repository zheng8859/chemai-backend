"""ChemAI 集成测试基础设施 — 数据库隔离 + JWT fixtures + 工厂方法。

关键设计：
- 模块级 os.environ 在 app 导入前设置 test DB URL
- Function scope test_engine：每个测试独立数据库文件 + create_all
- teardown 删除文件 → 完全物理隔离，无事务回滚魔法
- dependency_overrides 注入 test session 到 FastAPI 端点
"""

import os
import uuid
from pathlib import Path

# ═══════════════════════════════════════════════════════════════
# 模块级：必须在任何 app 模块导入前设置 test DB URL
# ═══════════════════════════════════════════════════════════════
_TEST_ROOT = Path(__file__).resolve().parent.parent / "data"
_TEST_MAIN = _TEST_ROOT / "test_chemai.db"

# 初始设置为公共 test URL（session scope 终态会被 override）
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_TEST_MAIN}"

# ── 现在安全导入 app 模块 ──────────────────────────────────
import pytest
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from httpx import AsyncClient, ASGITransport

from app.models.base import Base
from app.core.security import create_access_token


# ═══════════════════════════════════════════════════════════════
# Engine — function scope：每测试独立 DB 文件，物理隔离
# ═══════════════════════════════════════════════════════════════

@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


def _make_test_engine():
    """创建指向临时测试数据库文件的引擎，含 create_all。"""
    db_path = _TEST_ROOT / f"test_{uuid.uuid4().hex[:8]}.db"
    env_url = f"sqlite+aiosqlite:///{db_path}"
    os.environ["DATABASE_URL"] = env_url
    engine = create_async_engine(env_url, echo=False)
    return engine, db_path


@pytest.fixture
async def test_engine():
    """每个测试独立的数据库引擎 + 文件。

    配合 db_session 和 override，每个测试有完全独立的数据库文件。
    测试结束后删除文件。
    """
    engine, db_path = _make_test_engine()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    await engine.dispose()
    try:
        if db_path.exists():
            db_path.unlink()
        # 清理 WAL 文件
        wal = db_path.with_suffix(".db-wal")
        if wal.exists():
            wal.unlink()
        shm = db_path.with_suffix(".db-shm")
        if shm.exists():
            shm.unlink()
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════════
# DB Session — function scope
# ═══════════════════════════════════════════════════════════════

@pytest.fixture
async def db_session(test_engine):
    """测试直接 DB 访问 session。

    服务层内部调用的 session.commit() 提交到当前测试的独立数据库文件。
    HTTP 端点和测试代码共享此 session。
    """
    session = AsyncSession(test_engine, expire_on_commit=False)
    yield session
    await session.rollback()
    await session.close()


# ═══════════════════════════════════════════════════════════════
# HTTP Client — function scope：覆盖 get_db 依赖
# ═══════════════════════════════════════════════════════════════

@pytest.fixture
async def async_client(db_session, test_engine):
    """httpx AsyncClient，get_db 依赖被替换为 test session。

    延迟导入 app.main 以避免在 engine 创建前触发数据库连接。
    """
    from app.main import app
    from app.infrastructure.database import get_db

    async def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        yield client

    app.dependency_overrides.clear()


# ═══════════════════════════════════════════════════════════════
# Auth Header fixtures
# ═══════════════════════════════════════════════════════════════

@pytest.fixture
def admin_headers():
    """system_admin 角色 — 最高权限（可创建学校）。"""
    token = create_access_token(
        user_id=999, role="teacher", school_id=1, sub_role="system_admin",
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def teacher_headers():
    """普通教师角色。"""
    token = create_access_token(
        user_id=998, role="teacher", school_id=1, sub_role="teacher",
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def student_headers():
    """学生角色（无 sub_role）。"""
    token = create_access_token(user_id=997, role="student", school_id=1)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def parent_headers():
    """家长角色（无 school_id，23号 §八.4）。"""
    token = create_access_token(user_id=996, role="parent")
    return {"Authorization": f"Bearer {token}"}


# ═══════════════════════════════════════════════════════════════
# 工厂方法 — 创建测试数据
# ═══════════════════════════════════════════════════════════════

@pytest.fixture
async def school(async_client, admin_headers):
    """创建一个测试学校，返回其 id 和 name。"""
    resp = await async_client.post(
        "/api/v1/schools",
        json={"name": "集成测试学校", "region": "测试区"},
        headers=admin_headers,
    )
    assert resp.status_code == 201, f"创建学校失败: {resp.text}"
    data = resp.json()
    return {"id": data["id"], "name": data["name"]}


@pytest.fixture
async def grade(async_client, admin_headers, school):
    """在学校下创建一个年级。"""
    resp = await async_client.post(
        "/api/v1/grades",
        json={"school_id": school["id"], "name": "高一"},
        headers=admin_headers,
    )
    assert resp.status_code == 201, f"创建年级失败: {resp.text}"
    data = resp.json()
    return {"id": data["id"], "name": data["name"], "school_id": school["id"]}


@pytest.fixture
async def class_(async_client, admin_headers, grade):
    """在年级下创建一个班级。"""
    resp = await async_client.post(
        "/api/v1/classes",
        json={"grade_id": grade["id"], "name": "高一(1)班"},
        headers=admin_headers,
    )
    assert resp.status_code == 201, f"创建班级失败: {resp.text}"
    data = resp.json()
    return {"id": data["id"], "name": data["name"], "grade_id": grade["id"]}
