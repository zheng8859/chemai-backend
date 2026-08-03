"""ChemAI 智辅化学 — FastAPI 应用入口。

三层 Fallback LLM 路由：MiMo → 通义千问 → DeepSeek。
Agent 引擎：LangGraph create_react_agent (v2)，保留 Multi-Agent v1 为回退。
Auth：JWT HS256，三层权限检查（中间件 → get_current_user → require_permission）。
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import RequestResponseEndpoint
from starlette.responses import Response

from .api.deps import AUTH_WHITELIST_PREFIXES
from .api.v1.auth import router as auth_router, student_router


# ── Lifespan (startup / shutdown) ──────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: engines are lazily created on first request.
    Shutdown: dispose all engines.
    """
    yield
    # Dispose engines on shutdown
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
    allow_origins=["*"],  # 桌面应用内嵌场景；生产应收紧
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
app.include_router(auth_router)
app.include_router(student_router)


# ── Health ─────────────────────────────────────────────────
@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "chemai-api"}
