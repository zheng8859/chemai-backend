"""Async database engine and session management — ChemAI.

Provides:
- Three async engines (main, checkpoint, memory) from app.config
- AsyncSession factory for FastAPI dependency injection
- get_db / get_checkpoint_db / get_memory_db yield-style dependencies
"""

from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from ..config import DATABASE_URL, CHECKPOINT_DB_URL, MEMORY_DB_URL

# ── Engines ─────────────────────────────────────────────────
# echo=False by default; set echo=True for SQL debug in dev
main_engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,
)

checkpoint_engine = create_async_engine(
    CHECKPOINT_DB_URL,
    echo=False,
)

memory_engine = create_async_engine(
    MEMORY_DB_URL,
    echo=False,
)

# ── Session factories ───────────────────────────────────────
MainSession = async_sessionmaker(
    main_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

CheckpointSession = async_sessionmaker(
    checkpoint_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

MemorySession = async_sessionmaker(
    memory_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


# ── FastAPI dependencies ────────────────────────────────────

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yields an async session bound to the main chemai.db.

    Usage:
        @app.get("/api/students/{id}")
        async def get_student(id: int, db = Depends(get_db)):
            ...
    """
    async with MainSession() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_checkpoint_db() -> AsyncGenerator[AsyncSession, None]:
    """Yields an async session bound to checkpoint.db (LangGraph checkpoints)."""
    async with CheckpointSession() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_memory_db() -> AsyncGenerator[AsyncSession, None]:
    """Yields an async session bound to memory.db (long-term memory)."""
    async with MemorySession() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
