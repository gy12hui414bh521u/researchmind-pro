"""
PostgreSQL 数据库连接管理
使用 SQLAlchemy 2.0 async engine + asyncpg driver
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import settings


# ── SQLAlchemy Base ───────────────────────────────────────────────────

class Base(DeclarativeBase):
    """所有 ORM 模型的基类"""
    pass


# ── Engine & Session Factory ──────────────────────────────────────────

def create_engine() -> AsyncEngine:
    return create_async_engine(
        settings.postgres_url,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_timeout=settings.db_pool_timeout,
        pool_recycle=settings.db_pool_recycle,
        pool_pre_ping=True,        # 连接前 ping，自动剔除失效连接
        echo=settings.debug,       # debug 模式打印 SQL
    )


# 模块级单例
engine: AsyncEngine = create_engine()

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,   # commit 后不过期，避免 lazy load 报错
    autoflush=False,
    autocommit=False,
)


# ── FastAPI Depends 注入 ──────────────────────────────────────────────

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI 依赖注入用的数据库会话。
    用法：
        async def endpoint(db: AsyncSession = Depends(get_db)):
            ...
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# ── 上下文管理器（非 FastAPI 场景）──────────────────────────────────

@asynccontextmanager
async def get_db_context() -> AsyncGenerator[AsyncSession, None]:
    """
    非 FastAPI 场景（如 Agent 内部）使用的数据库会话上下文。
    用法：
        async with get_db_context() as db:
            result = await db.execute(...)
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# ── 健康检查 ──────────────────────────────────────────────────────────

async def check_db_connection() -> bool:
    """检查数据库连接是否正常"""
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


# ── 关闭连接池 ────────────────────────────────────────────────────────

async def close_db() -> None:
    """应用关闭时释放连接池"""
    await engine.dispose()
