"""Read-only inventory semantics for data tables."""
from __future__ import annotations

from typing import Any

from app.sync.pg_writer import PG_URL

TABLES = ("daily_kline", "daily_basic", "adj_factor", "stocks")


def count_table(table: str) -> int:
    if table not in TABLES:
        raise ValueError(f"unsupported table: {table}")
    try:
        import psycopg2
        conn = psycopg2.connect(PG_URL, connect_timeout=3)
        cur = conn.cursor()
        cur.execute(f"SELECT COUNT(*) FROM {table}")
        value = int(cur.fetchone()[0] or 0)
        conn.close()
        return value
    except Exception:
        return 0


def build_inventory() -> dict[str, Any]:
    return {"tables": {table: {"rows": count_table(table)} for table in TABLES}}
