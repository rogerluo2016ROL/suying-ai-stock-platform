"""Database session factory — async SQLAlchemy + PostgreSQL.

Mirrors ``services/diagnosis-service/app/database.py`` (ADR-005 / ADR-007 Q-3):
``create_async_engine`` + ``async_sessionmaker(expire_on_commit=False)`` +
``get_db()`` FastAPI dependency.

URL scheme adaptation: docker-compose only sets ``KRONOS_PG_URL`` with the
psycopg2 scheme (``postgresql://``); the async engine needs the asyncpg driver
(``postgresql+asyncpg://``). We derive the async URL from ``KRONOS_PG_URL`` so
docker-compose stays untouched (T-005 critical section). ``DATABASE_URL`` (if
already in the asyncpg scheme) takes precedence.
"""

import os

from kronos_contracts.db import resolve_async_url as _resolve_async_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool


DATABASE_URL = _resolve_async_url()

_is_test = os.environ.get("DATABASE_TEST_NULLPOOL", "") == "1"
_engine_kwargs: dict = {"echo": False, "pool_pre_ping": True}
if _is_test:
    _engine_kwargs["poolclass"] = NullPool

engine = create_async_engine(DATABASE_URL, **_engine_kwargs)
AsyncSessionLocal = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)


async def get_db() -> AsyncSession:
    """FastAPI dependency: yield an async database session."""
    async with AsyncSessionLocal() as session:
        yield session
