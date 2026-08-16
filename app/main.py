"""ChemAI 智辅化学 — FastAPI 应用入口。

三层 Fallback LLM 路由：MiMo → 通义千问 → DeepSeek。
Agent 引擎：LangGraph create_react_agent (v2)，保留 Multi-Agent v1 为回退。
Auth：JWT HS256，三层权限检查（中间件 → get_current_user → require_permission）。
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import RequestResponseEndpoint
from starlette.responses import Response

from .api.deps import AUTH_WHITELIST_PREFIXES
from .api.v1 import v1_router
from .config import CORS_ALLOWED_ORIGINS


# ── Lifespan (startup / shutdown) ──────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: 安全守卫 + 启动调度器。Shutdown: 关闭调度器 + dispose engines。"""
    from .config import JWT_SECRET, DEFAULT_JWT_SECRET
    if not JWT_SECRET or JWT_SECRET == DEFAULT_JWT_SECRET:
        raise RuntimeError(
            "JWT_SECRET 未配置或仍为默认弱密钥，禁止启动。"
            "请用 `openssl rand -hex 32` 生成强密钥写入 .env 的 JWT_SECRET。"
        )

    from .infrastructure.scheduler import start_scheduler, shutdown_scheduler
    start_scheduler()
    yield
    # 关闭资源
    shutdown_scheduler()
    from .infrastructure.database import main_engine, checkpoint_engine, memory_engine
    await main_engine.dispose()
    await checkpoint_engine.dispose()
    await memory_engine.dispose()


app = FastAPI(
    title="ChemAI — 智辅化学",
    description="AI 驱动的化学教学辅助平台 API",
    version="0.1.0",
    lifespan=lifespan,
)

# ── CORS ───────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOWED_ORIGINS,  # 白名单源（config.CORS_ALLOWED_ORIGINS），禁止通配符 + 凭证并存
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Global Auth Middleware (Layer 1: header presence check) ──
@app.middleware("http")
async def auth_middleware(
    request: Request, call_next: RequestResponseEndpoint
) -> Response:
    """Check Authorization header presence on /api/* paths.

    Layer 1 only checks that a Bearer header exists.
    Full JWT decode + validation is in get_current_user (Layer 2, deps.py).
    """

    path = request.url.path

    # Skip OPTIONS preflight (CORS)
    if request.method == "OPTIONS":
        return await call_next(request)

    # Skip whitelisted paths
    if any(path.startswith(prefix) for prefix in AUTH_WHITELIST_PREFIXES):
        return await call_next(request)

    # Only enforce auth on /api/* paths
    if not path.startswith("/api/"):
        return await call_next(request)

    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"detail": "未提供有效的认证令牌", "error_code": "AUTHENTICATION_REQUIRED"},
        )

    return await call_next(request)


# ── Routers ────────────────────────────────────────────────
# 逐个注册子路由到 v1_router，按领域增量添加
from .api.v1.auth import router as auth_router, student_router
from .api.v1.org import router as org_router
from .api.v1.user import router as user_router
from .api.v1.teaching import router as teaching_router
from .api.v1.diagnosis import router as diagnosis_router
from .api.v1.homework import router as homework_router
from .api.v1.ocr import router as ocr_router
from .api.v1.question_bank import router as question_bank_router
from .api.v1.audit import router as audit_router
from .api.v1.practice import router as practice_router
from .api.v1.review import router as review_router
from .api.v1.panel import router as panel_router
from .api.v1.warning import router as warning_router
from .api.v1.stats import router as stats_router
from .api.v1.learning_plan import router as learning_plan_router
from .api.v1.notification import router as notification_router
from .api.v1.parent import router as parent_router

v1_router.include_router(auth_router)
v1_router.include_router(student_router)
v1_router.include_router(org_router)
v1_router.include_router(user_router)
v1_router.include_router(teaching_router)
v1_router.include_router(diagnosis_router)
v1_router.include_router(homework_router)
v1_router.include_router(ocr_router)
v1_router.include_router(question_bank_router)
v1_router.include_router(audit_router)
v1_router.include_router(practice_router)
v1_router.include_router(review_router)
v1_router.include_router(panel_router)
v1_router.include_router(warning_router)
v1_router.include_router(stats_router)
v1_router.include_router(learning_plan_router)
v1_router.include_router(notification_router)
v1_router.include_router(parent_router)
from .api.v1.chat import router as chat_router
v1_router.include_router(chat_router)

app.include_router(v1_router)


# ── Health ─────────────────────────────────────────────────
@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "chemai-api"}


# ── Frontend Static Files (dev/test) ───────────────────────
import os
frontend_dir = os.path.join(os.path.dirname(__file__), "..", "frontend")
if os.path.isdir(frontend_dir):
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
