"""Adapters for backtest-service — reuses screener-service adapter pattern."""

import os, sys, logging

logger = logging.getLogger("backtest-service.adapters")

# Reuse the screener-service adapter if installed, or use standalone
def inject_adapters():
    """Inject DB adapter into kronos-factors for backtest operations."""
    try:
        # Try to use screener-service's adapter
        sys.path.insert(0, os.path.abspath(os.path.join(
            os.path.dirname(__file__), "..", "..", "screener-service")))
        from app.adapters import _LegacyDBAdapter
    except ImportError:
        # Standalone: use a simple SQLite adapter
        db_path = os.environ.get(
            "KRONOS_DB_PATH",
            os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
                os.path.dirname(os.path.abspath(__file__)))), "Kronos", "data", "kronos.db"))
        )
        import sqlite3

        class _LegacyDBAdapter:
            def __init__(self, path):
                self.path = path
            def execute(self, sql, params=None):
                conn = sqlite3.connect(self.path); conn.row_factory = sqlite3.Row
                c = conn.cursor()
                c.execute(sql, params or ())
                class W:
                    def fetchone(s): r = c.fetchone(); return dict(r) if r else None
                    def fetchall(s): return [dict(r) for r in c.fetchall()]
                return W()
            def __enter__(s): return s
            def __exit__(s,*a): pass
            def get_kline(s, code, lookback=400): return None
            def get_stock_info(s, code): return None
            def get_all_codes(s, exclude_st=True): return []

        _LegacyDBAdapter = _LegacyDBAdapter(db_path)

    from kronos_factors.scorer._db_stub import set_db_adapter
    set_db_adapter(_LegacyDBAdapter)
    logger.info("Backtest DB adapter injected")
