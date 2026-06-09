"""PostgreSQL database adapter for kronos-factors.

Usage:
    from kronos_factors.pg_adapter import create_pg_adapter
    set_db_adapter(create_pg_adapter(os.environ['KRONOS_PG_URL']))
"""

import logging, os
from typing import Optional
import pandas as pd

logger = logging.getLogger("kronos-factors.pg")


def create_pg_adapter(pg_url: str = None):
    """Create a PG-based DB adapter. Falls back to SQLite if PG unavailable."""
    pg_url = pg_url or os.environ.get('KRONOS_PG_URL', '')
    sqlite_path = os.environ.get('KRONOS_SQLITE_PATH', '')

    if pg_url:
        try:
            import psycopg2
            import psycopg2.extras
            return _PgAdapter(pg_url)
        except ImportError:
            logger.warning("psycopg2 not installed, falling back to SQLite")
        except Exception as e:
            logger.warning("PG connection failed: %s, falling back to SQLite", e)

    if sqlite_path:
        return _SqliteFallbackAdapter(sqlite_path)

    return None


class _PgAdapter:
    """PostgreSQL adapter for kronos-factors."""

    def __init__(self, pg_url: str):
        import psycopg2
        import psycopg2.extras
        self.pg_url = pg_url
        self._conn = None
        psycopg2.extras.register_default_jsonb(conn_or_curs=psycopg2)

    def _get_conn(self):
        if self._conn is None or self._conn.closed:
            import psycopg2
            self._conn = psycopg2.connect(self.pg_url)
        return self._conn

    def execute(self, sql: str, params: tuple = None):
        conn = self._get_conn()
        cur = conn.cursor()
        # Translate SQLite ? placeholders to PG %s
        sql_pg = sql.replace('?', '%s')
        cur.execute(sql_pg, params or ())
        return _PgCursor(cur)

    def get_kline(self, code: str, lookback: int = 400) -> Optional[pd.DataFrame]:
        try:
            cur = self._get_conn().cursor()
            cur.execute(
                "SELECT trade_date, open, high, low, close, volume, amount "
                "FROM daily_kline WHERE code=%s ORDER BY trade_date DESC LIMIT %s",
                (code, lookback))
            rows = cur.fetchall()
            if not rows: return None
            df = pd.DataFrame([dict(zip(['trade_date','open','high','low','close','volume','amount'], r))
                               for r in reversed(rows)])
            df['timestamps'] = pd.to_datetime(df['trade_date'])
            return df
        except Exception: return None

    def get_stock_info(self, code: str) -> Optional[dict]:
        try:
            cur = self._get_conn().cursor()
            cur.execute("SELECT * FROM stocks WHERE code=%s", (code,))
            row = cur.fetchone()
            return dict(zip([d[0] for d in cur.description], row)) if row else None
        except Exception: return None

    def get_all_codes(self, exclude_st: bool = True) -> list[str]:
        try:
            cur = self._get_conn().cursor()
            if exclude_st: cur.execute("SELECT code FROM stocks WHERE is_st=0 ORDER BY code")
            else: cur.execute("SELECT code FROM stocks ORDER BY code")
            return [r[0] for r in cur.fetchall()]
        except Exception: return []

    def __enter__(self): return self
    def __exit__(self, *args): pass


class _PgCursor:
    def __init__(self, cur): self._cur = cur
    def fetchone(self):
        row = self._cur.fetchone()
        if row is None: return None
        return dict(zip([d[0] for d in self._cur.description], row))
    def fetchall(self):
        return [dict(zip([d[0] for d in self._cur.description], r)) for r in self._cur.fetchall()]


class _SqliteFallbackAdapter:
    def __init__(self, db_path): self.db_path = db_path
    def execute(self, sql, params=None):
        import sqlite3
        c = sqlite3.connect(self.db_path); c.row_factory = sqlite3.Row
        cur = c.cursor(); cur.execute(sql, params or ())
        class W:
            def fetchone(s): r = cur.fetchone(); return dict(r) if r else None
            def fetchall(s): return [dict(r) for r in cur.fetchall()]
        return W()
    def get_kline(self, c, l=400): return None
    def get_stock_info(self, c): return None
    def get_all_codes(self, e=True): return []
    def __enter__(s): return s
    def __exit__(s,*a): pass
