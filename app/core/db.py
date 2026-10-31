"""
数据库连接模块
配置 SQLAlchemy AsyncSession
"""
from typing import AsyncGenerator
from fastapi import HTTPException
from sqlalchemy.exc import DBAPIError
from asyncpg import PostgresError

from sqlalchemy.ext.asyncio import (
    AsyncSession, 
    AsyncEngine,
    create_async_engine,
    async_sessionmaker
)
from sqlalchemy.orm import declarative_base
from app.core.config import settings

# 创建异步引擎
engine = create_async_engine(
    settings.async_database_url,
    echo=settings.debug,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
)

# 创建异步会话工厂
async_session_factory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

# 声明基类
Base = declarative_base()


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """
    获取异步数据库会话
    用于 FastAPI 依赖注入
    """
    async with async_session_factory() as session:
        try:
            yield session
            # Write endpoints commit before sending their response. Read-only dependencies
            # must not commit after a long-running stream has already been sent.
        except (DBAPIError, PostgresError, OSError) as exc:
            try:
                await session.rollback()
            except Exception:
                pass
            raise HTTPException(503, '数据库暂不可用，请检查 Docker 数据库状态后重试') from exc
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db() -> None:
    """
    初始化数据库（创建表）
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("[DB] Database initialized")


async def close_db() -> None:
    """
    关闭数据库连接
    """
    await engine.dispose()
    print("[DB] Database connection closed")
