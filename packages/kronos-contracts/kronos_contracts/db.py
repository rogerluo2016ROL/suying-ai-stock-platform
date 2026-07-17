"""Shared DB helpers for Kronos services.

Centralizes URL resolution (阶段2) + connection pooling (阶段3, 待加) so
individual services stop copy-pasting ``_resolve_async_url``.
"""

import os
from contextlib import contextmanager


def resolve_async_url() -> str:
    """Resolve an asyncpg-compatible Postgres URL.

    Priority: explicit ``DATABASE_URL`` > ``KRONOS_PG_URL`` (psycopg2 scheme)
    > localhost default. Any ``postgresql://`` scheme is rewritten to
    ``postgresql+asyncpg://`` (leftmost occurrence only, so credentials are safe).
    """
    url = os.environ.get("DATABASE_URL")
    if not url:
        url = os.environ.get(
            "KRONOS_PG_URL",
            "postgresql://kronos:kronos@localhost:6432/kronos",
        )
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


# ── 连接池 (阶段3 / P0-2): 复用连接, 防裸 psycopg2.connect 撑爆 PG max_connections ──
# 仅用于高频查询/写入路径; readiness/health 检查需 connect_timeout 快速失败, 仍用裸 connect。
_pg_pools: dict = {}


def _default_pg_dsn() -> str:
    return (
        os.environ.get("KRONOS_PG_URL")
        or os.environ.get("DATABASE_URL")
        or "postgresql://kronos:kronos@localhost:6432/kronos"
    )


def get_pg_pool(dsn: str | None = None, maxconn: int | None = None):
    """Get/create a thread-safe psycopg2 connection pool (singleton per dsn)."""
    from psycopg2.pool import ThreadedConnectionPool

    dsn = dsn or _default_pg_dsn()
    if dsn not in _pg_pools:
        cap = maxconn or int(os.environ.get("PG_POOL_MAXCONN", "8"))
        _pg_pools[dsn] = ThreadedConnectionPool(1, cap, dsn)
    return _pg_pools[dsn]


@contextmanager
def pg_conn(dsn: str | None = None, maxconn: int | None = None):
    """Context manager: borrow a pooled connection; commit on success / rollback on error; return to pool."""
    pool = get_pg_pool(dsn, maxconn)
    conn = pool.getconn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)
