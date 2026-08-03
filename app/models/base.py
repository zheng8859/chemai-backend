"""ChemAI 模型基类 — declarative_base, UUID PK, TimestampMixin.

SQLAlchemy 2.0 风格：mapped_column + Mapped 类型注解。
SQLite 兼容：Integer PK（利用 rowid 性能优势）。
"""

from datetime import datetime

from sqlalchemy import Integer, DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """SQLAlchemy 2.0 声明式基类。"""
    pass


class TimestampMixin:
    """创建时间 + 更新时间 mixin。"""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="记录创建时间",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        comment="记录最后更新时间",
    )
