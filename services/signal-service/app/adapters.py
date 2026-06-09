"""Signal service DB adapter — standalone SQLite support."""

import sqlite3, logging, os
from typing import Optional
import pandas as pd

logger = logging.getLogger("signal-service.adapters")


def inject_adapters(db_path: str):
    """Inject DB and market data adapters into kronos-factors."""
    from kronos_factors.scorer._db_stub import set_db_adapter, set_market_data_adapter
    adapter = _SQLiteAdapter(db_path)
    set_db_adapter(adapter)
    set_market_data_adapter(_MarketDataAdapter(db_path))
    logger.info("Signal DB adapters injected (path=%s)", db_path)


class _SQLiteAdapter:
    def __init__(self, path): self.db_path = path
    def _conn(self):
        c = sqlite3.connect(self.db_path); c.row_factory = sqlite3.Row; return c

    def execute(self, sql, params=None):
        conn = self._conn(); cur = conn.cursor()
        cur.execute(sql, params or ())
        class W:
            def fetchone(s): r = cur.fetchone(); return dict(r) if r else None
            def fetchall(s): return [dict(r) for r in cur.fetchall()]
        return W()

    def get_kline(self, code, lookback=400): return None
    def get_stock_info(self, code): return None
    def get_all_codes(self, exclude_st=True): return []
    def __enter__(s): return s
    def __exit__(s, *a): pass


class _MarketDataAdapter:
    def __init__(self, db_path): self.db_path = db_path

    def get_kline_df(self, code: str, lookback: int = 400) -> Optional[pd.DataFrame]:
        try:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            c.execute("SELECT trade_date, open, high, low, close, volume, amount FROM daily_kline WHERE code=? ORDER BY trade_date DESC LIMIT ?", (code, lookback))
            rows = c.fetchall()
            conn.close()
            if not rows: return None
            df = pd.DataFrame([{"trade_date": r[0], "open": r[1], "high": r[2], "low": r[3], "close": r[4], "volume": r[5], "amount": r[6]} for r in reversed(rows)])
            df["timestamps"] = pd.to_datetime(df["trade_date"])
            return df
        except Exception: return None

    def sync_stock_list(self) -> int: return 0
    def update_daily_kline(self, from_date: str) -> int: return 0
