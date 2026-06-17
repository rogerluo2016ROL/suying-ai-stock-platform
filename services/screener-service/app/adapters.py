"""Adapters that bridge kronos-factors with PG (primary) or SQLite (fallback).

On startup, inject real DB/Market adapters so the scoring functions
can access actual stock data via PostgreSQL instead of SQLite stubs.
"""

import os, sys, logging, re
from typing import Optional
import pandas as pd

logger = logging.getLogger("screener-service.adapters")

PG_URL = os.environ.get(
    "KRONOS_PG_URL", "postgresql://kronos:kronos@localhost:6432/kronos")


def inject_adapters(db_path: str):
    """Inject PG DB adapter (with SQLite fallback) into kronos-factors."""
    from kronos_factors.scorer._db_stub import set_db_adapter, set_market_data_adapter

    # Try PG first, fall back to SQLite
    try:
        adapter = _PGAdapter()
        # Health check: verify connection works before committing to PG
        try:
            adapter._get_conn()
            logger.info("DB adapters: PG mode (postgresql://%s)", PG_URL.split("@")[-1])
        except Exception as e:
            logger.warning("PG connection test failed (%s), falling back to SQLite", e)
            adapter = _LegacyDBAdapter(db_path)
    except Exception as e:
        logger.warning("PG adapter unavailable (%s), falling back to SQLite", e)
        adapter = _LegacyDBAdapter(db_path)

    set_db_adapter(adapter)
    set_market_data_adapter(_PGMarketDataAdapter() if isinstance(adapter, _PGAdapter)
                            else _LegacyMarketDataAdapter(db_path))
    logger.info("DB adapters injected")


class _PGAdapter:
    """PostgreSQL adapter — mimics the SQLite _db_stub interface with dict rows.

    Translates SQLite `?` placeholders to PG `%s`, and wraps psycopg2
    tuples into dict-like rows (compatible with sqlite3.Row access patterns).
    """

    def __init__(self):
        import psycopg2
        import psycopg2.extras
        self._url = PG_URL
        self._conn = None
        self._readonly = False

    def _get_conn(self):
        import psycopg2
        if self._conn is None or self._conn.closed:
            self._conn = psycopg2.connect(
                self._url, connect_timeout=5,
                options="-c statement_timeout=30000 -c lock_timeout=10000"
            )
            self._conn.autocommit = True
        return self._conn

    def execute(self, sql: str, params: tuple = None):
        conn = self._get_conn()
        cur = conn.cursor()
        # Translate SQLite ? placeholders to PG %s
        pg_sql = self._translate_sql(sql)
        if params:
            cur.execute(pg_sql, params)
        else:
            cur.execute(pg_sql)
        return _PGCursorWrapper(cur)

    def _translate_sql(self, sql: str) -> str:
        """Convert SQLite-style SQL to PG: ? → %s, fix table/column names.

        IMPORTANT: After replacing ? with %s, any remaining literal %
        characters (e.g., in LIKE '%ST%') must be escaped to %%
        to prevent psycopg2 from interpreting them as placeholders.
        """
        # Step 1: Replace ? placeholders with %s (preserving ? inside quoted strings)
        parts = re.split(r"('(?:[^'\\]|\\.)*')", sql)
        for i in range(0, len(parts), 2):
            parts[i] = parts[i].replace("?", "%s")
        sql = "".join(parts)
        # Step 2: Escape literal % in quoted strings to prevent psycopg2 errors
        # (psycopg2 treats %S, %T etc as placeholders, not just %s)
        def _escape_like_percent(m):
            return m.group(0).replace("%", "%%")
        sql = re.sub(r"'[^']*'", _escape_like_percent, sql)
        # Step 3: Fix common SQLite→PG issues
        sql = sql.replace("datetime('now','localtime')", "NOW()")
        sql = sql.replace("strftime(", "TO_CHAR(")
        # Kronos SQLite → PG column mapping (TABLE-AWARE)
        # PG actual column names:
        #   stk_mins → code (NOT ts_code!)
        #   index_daily → change_pct (NOT pct_chg!)
        #   limit_list_d → ts_code, pct_chg (Tushare names, engine uses these)
        #   daily_kline/stocks → code, change_pct
        if "stk_mins" in sql.lower():
            sql = re.sub(r'\bts_code\b', 'code', sql)  # stk_mins PG has 'code'
        if "index_daily" in sql.lower():
            sql = re.sub(r'\bts_code\b', 'code', sql)  # index_daily PG has 'code'
            sql = re.sub(r'\bpct_chg\b', 'change_pct', sql)  # index_daily PG has 'change_pct'
        if "limit_list_d" in sql.lower():
            sql = re.sub(r'\bcode\b(?!_)', 'ts_code', sql)  # limit_list_d PG has 'ts_code'
        sql = sql.replace("float_mv", "COALESCE(float_mv, market_cap)")
        return sql

    def get_kline(self, code: str, lookback: int = 400) -> Optional[pd.DataFrame]:
        try:
            cur = self._get_conn().cursor()
            cur.execute(
                "SELECT trade_date, open, high, low, close, volume, amount "
                "FROM daily_kline WHERE code=%s ORDER BY trade_date DESC LIMIT %s",
                (code, lookback))
            rows = cur.fetchall()
            if not rows:
                return None
            df = pd.DataFrame(
                [{"trade_date": str(r[0]), "open": float(r[1] or 0), "high": float(r[2] or 0),
                  "low": float(r[3] or 0), "close": float(r[4] or 0),
                  "volume": float(r[5] or 0), "amount": float(r[6] or 0)} for r in reversed(rows)])
            df["timestamps"] = pd.to_datetime(df["trade_date"])
            return df
        except Exception as e:
            logger.debug("PG get_kline(%s): %s", code, e)
            return None

    def get_stock_info(self, code: str) -> Optional[dict]:
        try:
            cur = self._get_conn().cursor()
            cur.execute("SELECT code, name, board, industry, market_cap, is_st FROM stocks WHERE code=%s", (code,))
            r = cur.fetchone()
            if r:
                return {"code": r[0], "name": r[1], "board": r[2], "industry": r[3],
                        "market_cap": float(r[4] or 0), "is_st": int(r[5] or 0)}
            return None
        except Exception as e:
            logger.debug("PG get_stock_info(%s): %s", code, e)
            return None

    def get_all_codes(self, exclude_st: bool = True) -> list[str]:
        try:
            cur = self._get_conn().cursor()
            if exclude_st:
                cur.execute("SELECT code FROM stocks WHERE is_st=0 AND name NOT LIKE '%%ST%%' ORDER BY code")
            else:
                cur.execute("SELECT code FROM stocks ORDER BY code")
            return [r[0] for r in cur.fetchall()]
        except Exception as e:
            logger.debug("PG get_all_codes: %s", e)
            return []

    def __enter__(self): return self
    def __exit__(self, *args): pass


class _PGCursorWrapper:
    """Wraps psycopg2 cursor to return dict-like rows (mimics sqlite3.Row)."""
    def __init__(self, cursor):
        self._cursor = cursor
        self._desc = [d[0] for d in cursor.description] if cursor.description else []

    def fetchone(self):
        row = self._cursor.fetchone()
        if row is None:
            return None
        return _DictRow(self._desc, row)

    def fetchall(self):
        return [_DictRow(self._desc, r) for r in self._cursor.fetchall()]

    def __iter__(self):
        for row in self._cursor:
            yield _DictRow(self._desc, row)


class _DictRow:
    """Mimics sqlite3.Row — supports both dict['key'] and row[0] access."""
    def __init__(self, columns, values):
        self._cols = columns
        self._vals = values

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._vals[key]
        if isinstance(key, str) and key in self._cols:
            return self._vals[self._cols.index(key)]
        raise KeyError(key)

    def keys(self):
        return self._cols

    def values(self):
        return self._vals

    def __len__(self):
        return len(self._vals)

    def __repr__(self):
        return "Row(" + ", ".join(f"{c}={v!r}" for c, v in zip(self._cols, self._vals)) + ")"

    def __iter__(self):
        return iter(self._vals)

    def get(self, key, default=None):
        try:
            return self[key]
        except (KeyError, IndexError):
            return default


class _PGMarketDataAdapter:
    """PG-backed MarketDataAdapter."""
    def __init__(self):
        self._adapter = _PGAdapter()

    def get_kline_df(self, code: str, lookback: int = 400) -> Optional[pd.DataFrame]:
        return self._adapter.get_kline(code, lookback)

    def sync_stock_list(self) -> int:
        return 0

    def update_daily_kline(self, from_date: str) -> int:
        return 0


class _LegacyDBAdapter:
    """Wraps the legacy SQLite DB behind the kronos-factors DBAdapter interface."""

    def __init__(self, db_path: str):
        import sqlite3
        self.db_path = db_path
        self._conn = None

    def _get_conn(self):
        if self._conn is None:
            import sqlite3
            self._conn = sqlite3.connect(self.db_path)
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def execute(self, sql: str, params: tuple = None):
        conn = self._get_conn()
        cursor = conn.cursor()
        if params:
            cursor.execute(sql, params)
        else:
            cursor.execute(sql)
        return _CursorWrapper(cursor)

    def get_kline(self, code: str, lookback: int = 400) -> Optional[pd.DataFrame]:
        try:
            cursor = self._get_conn().cursor()
            cursor.execute(
                "SELECT trade_date, open, high, low, close, volume, amount "
                "FROM daily_kline WHERE code=? ORDER BY trade_date DESC LIMIT ?",
                (code, lookback)
            )
            rows = cursor.fetchall()
            if not rows:
                return None
            df = pd.DataFrame(
                [dict(r) for r in reversed(rows)],
                columns=["trade_date", "open", "high", "low", "close", "volume", "amount"]
            )
            df["timestamps"] = pd.to_datetime(df["trade_date"])
            return df
        except Exception:
            return None

    def get_stock_info(self, code: str) -> Optional[dict]:
        try:
            cursor = self._get_conn().cursor()
            cursor.execute("SELECT * FROM stocks WHERE code=?", (code,))
            row = cursor.fetchone()
            return dict(row) if row else None
        except Exception:
            return None

    def get_all_codes(self, exclude_st: bool = True) -> list[str]:
        try:
            cursor = self._get_conn().cursor()
            if exclude_st:
                cursor.execute("SELECT code FROM stocks WHERE is_st=0 ORDER BY code")
            else:
                cursor.execute("SELECT code FROM stocks ORDER BY code")
            return [r["code"] for r in cursor.fetchall()]
        except Exception:
            return []

    def __enter__(self): return self
    def __exit__(self, *args): pass


class _CursorWrapper:
    def __init__(self, cursor):
        self._cursor = cursor

    def fetchone(self):
        row = self._cursor.fetchone()
        return dict(row) if row else None

    def fetchall(self):
        return [dict(r) for r in self._cursor.fetchall()]


class _LegacyMarketDataAdapter:
    """Wraps legacy market data service behind the kronos-factors MarketDataAdapter interface."""

    def __init__(self, db_path: str):
        self.db_path = db_path

    def get_kline_df(self, code: str, lookback: int = 400) -> Optional[pd.DataFrame]:
        try:
            import sqlite3
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute(
                "SELECT trade_date, open, high, low, close, volume, amount "
                "FROM daily_kline WHERE code=? ORDER BY trade_date DESC LIMIT ?",
                (code, lookback)
            )
            rows = cursor.fetchall()
            conn.close()
            if not rows:
                return None
            df = pd.DataFrame(
                [{"trade_date": r[0], "open": r[1], "high": r[2], "low": r[3],
                  "close": r[4], "volume": r[5], "amount": r[6]} for r in reversed(rows)]
            )
            df["timestamps"] = pd.to_datetime(df["trade_date"])
            return df
        except Exception:
            return None

    def sync_stock_list(self) -> int:
        return 0  # Handled by ETL pipeline

    def update_daily_kline(self, from_date: str) -> int:
        return 0  # Handled by ETL pipeline
