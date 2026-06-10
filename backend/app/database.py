"""Database session factory — async SQLAlchemy + PostgreSQL."""

import os

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import DATABASE_URL


def _is_test() -> bool:
    return os.environ.get("DATABASE_TEST_NULLPOOL", "") == "1"


_engine_kwargs = {"echo": False, "pool_pre_ping": True}
if _is_test():
    _engine_kwargs["poolclass"] = NullPool

engine = create_async_engine(DATABASE_URL, **_engine_kwargs)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db() -> AsyncSession:
    """FastAPI dependency: yield an async database session."""
    async with AsyncSessionLocal() as session:
        yield session
