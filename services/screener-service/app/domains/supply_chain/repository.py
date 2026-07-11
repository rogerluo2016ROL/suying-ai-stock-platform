"""PostgreSQL read boundary for supply-chain domain queries."""

import os
from psycopg2 import sql


def connect():
    import psycopg2
    return psycopg2.connect(os.environ.get("KRONOS_PG_URL", "postgresql://kronos:kronos@localhost:6432/kronos"), connect_timeout=5)


def table_exists(cur, table_name: str) -> bool:
    cur.execute("SELECT EXISTS(SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name=%s)", (table_name,))
    return bool(cur.fetchone()[0])


def column_exists(cur, table_name: str, column_name: str) -> bool:
    cur.execute("SELECT EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name=%s AND column_name=%s)", (table_name, column_name))
    return bool(cur.fetchone()[0])


def count(cur, table_name: str) -> int:
    if not table_exists(cur, table_name): return 0
    cur.execute(sql.SQL("SELECT COUNT(*) FROM {}").format(sql.Identifier(table_name)))
    return int(cur.fetchone()[0] or 0)


def distinct_count(cur, table_name: str, column_name: str) -> int:
    if not table_exists(cur, table_name) or not column_exists(cur, table_name, column_name): return 0
    cur.execute(sql.SQL("SELECT COUNT(DISTINCT {}) FROM {}").format(sql.Identifier(column_name), sql.Identifier(table_name)))
    return int(cur.fetchone()[0] or 0)


def nonempty_text_count(cur, table_name: str, column_name: str, min_length: int = 20) -> int:
    if not table_exists(cur, table_name) or not column_exists(cur, table_name, column_name): return 0
    cur.execute(sql.SQL("SELECT COUNT(*) FROM {} WHERE {} IS NOT NULL AND length({}::text) > %s").format(sql.Identifier(table_name), sql.Identifier(column_name), sql.Identifier(column_name)), (min_length,))
    return int(cur.fetchone()[0] or 0)


def status_from_rows(rows: int, *, ready: int, partial: int = 1) -> str:
    if rows >= ready: return "ready"
    if rows >= partial: return "partial"
    return "missing"
