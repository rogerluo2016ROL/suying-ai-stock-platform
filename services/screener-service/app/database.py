"""Async database dependency for screener-service persisted candidate pools."""

from __future__ import annotations

import os
from typing import Any

from kronos_contracts.db import resolve_async_url as _resolve_async_url

try:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool
except ModuleNotFoundError:
    AsyncSession = Any  # type: ignore[misc,assignment]
    async_sessionmaker = None  # type: ignore[assignment]
    create_async_engine = None  # type: ignore[assignment]
    NullPool = None  # type: ignore[assignment]


DATABASE_URL = _resolve_async_url()
engine = None
AsyncSessionLocal = None


def _get_sessionmaker():
    global engine, AsyncSessionLocal
    if AsyncSessionLocal is not None:
        return AsyncSessionLocal
    if async_sessionmaker is None or create_async_engine is None:
        raise ModuleNotFoundError("sqlalchemy")

    engine_kwargs: dict = {"echo": False, "pool_pre_ping": True}
    if os.environ.get("DATABASE_TEST_NULLPOOL", "") == "1" and NullPool is not None:
        engine_kwargs["poolclass"] = NullPool

    engine = create_async_engine(DATABASE_URL, **engine_kwargs)
    AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return AsyncSessionLocal


async def get_db() -> AsyncSession | None:
    try:
        sessionmaker = _get_sessionmaker()
    except ModuleNotFoundError:
        yield None
        return
    async with sessionmaker() as session:
        yield session
