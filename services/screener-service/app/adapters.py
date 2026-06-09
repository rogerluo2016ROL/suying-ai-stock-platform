"""Adapters that bridge kronos-factors with the legacy Kronos data layer.

On startup, inject real DB/Market adapters so the scoring functions
can access actual stock data instead of returning neutral stubs.
"""

import os, sys, logging
from typing import Optional
import pandas as pd

logger = logging.getLogger("screener-service.adapters")


def inject_adapters(db_path: str):
    """Inject real DB and market data adapters into kronos-factors.

    This must be called once at service startup, before any screening requests.
    """
    from kronos_factors.scorer._db_stub import set_db_adapter, set_market_data_adapter

    adapter = _LegacyDBAdapter(db_path)
    set_db_adapter(adapter)
    set_market_data_adapter(_LegacyMarketDataAdapter(db_path))
    logger.info("DB adapters injected (path=%s)", db_path)


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
