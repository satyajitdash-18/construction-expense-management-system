from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
import redis.asyncio as redis
from minio import Minio

from app.core.config import settings


class Base(DeclarativeBase):
    pass


import os
from sqlalchemy.pool import NullPool

_is_testing = os.getenv("TESTING") == "1" or settings.APP_ENV in ("test", "testing")
_engine_kwargs = {"poolclass": NullPool} if _is_testing else {"pool_pre_ping": True, "pool_recycle": 3600}

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.APP_ENV == "development",
    **_engine_kwargs,
)


AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def init_db() -> None:
    """Initialize database connection without mutating schema in production."""
    if _is_testing:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    else:
        from sqlalchemy import text
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


@asynccontextmanager
async def get_db_context() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def get_redis() -> redis.Redis:
    """Get Redis client."""
    return redis.from_url(settings.REDIS_URL, decode_responses=True)


def get_minio() -> Minio:
    """Get MinIO client."""
    return Minio(
        settings.MINIO_ENDPOINT,
        access_key=settings.MINIO_ACCESS_KEY,
        secret_key=settings.MINIO_SECRET_KEY,
        secure=settings.MINIO_SECURE,
    )
