"""Async database dependency for strategy-service durable plan storage."""

from __future__ import annotations

import os

from kronos_contracts.db import resolve_async_url as _resolve_async_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool


DATABASE_URL = _resolve_async_url()
engine = None
AsyncSessionLocal = None


def _get_sessionmaker():
    global engine, AsyncSessionLocal
    if AsyncSessionLocal is not None:
        return AsyncSessionLocal

    engine_kwargs: dict = {"echo": False, "pool_pre_ping": True}
    if os.environ.get("DATABASE_TEST_NULLPOOL", "") == "1":
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
