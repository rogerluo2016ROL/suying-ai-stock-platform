+"""Adapters for backtest-service — PG-first, explicit legacy SQLite fallback."""

import os, sys, logging

logger = logging.getLogger("backtest-service.adapters")


def inject_adapters():
    """Inject DB adapter into kronos-factors for backtest operations.

    Priority: PG (KRONOS_PG_URL) > explicit SQLite fallback > None.
    """
    pg_url = os.environ.get('KRONOS_PG_URL', '')
    if pg_url:
        try:
            from kronos_factors.pg_adapter import create_pg_adapter
            adapter = create_pg_adapter(pg_url)
            if adapter is not None:
                from kronos_factors.scorer._db_stub import set_db_adapter
                set_db_adapter(adapter)
                logger.info("Backtest DB: PG mode")
                return
        except Exception as e:
            logger.warning("Backtest PG adapter failed: %s", e)

    if os.environ.get("KRONOS_ALLOW_SQLITE_FALLBACK", "").lower() not in {"1", "true", "yes", "on"}:
        logger.warning("Backtest DB: SQLite fallback disabled")
        return

    # Legacy fallback: SQLite
    db_path = os.environ.get("KRONOS_DB_PATH",
        os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.dirname(os.path.abspath(__file__)))), "Kronos", "data", "kronos.db")))
    import sqlite3

    class _LegacyDBAdapter:
        def __init__(self, path): self.path = path
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

    adapter = _LegacyDBAdapter(db_path)
    from kronos_factors.scorer._db_stub import set_db_adapter
    set_db_adapter(adapter)
    logger.info("Backtest DB: SQLite fallback mode")

