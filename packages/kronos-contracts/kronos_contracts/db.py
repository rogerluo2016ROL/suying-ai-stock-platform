"""Shared DB helpers for Kronos services.

Centralizes URL resolution (阶段2) + connection pooling (阶段3, 待加) so
individual services stop copy-pasting ``_resolve_async_url``.
"""

import os


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
