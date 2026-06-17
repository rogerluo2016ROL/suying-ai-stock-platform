"""DB adapter stub — auto-initializes PG-first with SQLite fallback.

Resolution order:
  1. Explicitly injected adapter (via set_db_adapter())
  2. KRONOS_PG_URL env var → PostgreSQL adapter
  3. KRONOS_SQLITE_PATH env var → SQLite fallback adapter
  4. Neutral stub (returns empty results, safe default)

In production, inject a real DBAdapter via set_db_adapter() at startup.
For dev, set KRONOS_PG_URL to auto-connect.
"""

import logging
import os
from contextlib import contextmanager
from typing import Optional

logger = logging.getLogger("kronos-factors.db_stub")

_db_adapter = None
_market_data_adapter = None
_adapter_initialized = False


def set_db_adapter(adapter):
    """Inject a real DBAdapter instance. Call once at application startup."""
    global _db_adapter
    _db_adapter = adapter


def set_market_data_adapter(adapter):
    """Inject a real MarketDataAdapter instance."""
    global _market_data_adapter
    _market_data_adapter = adapter


def _auto_init_adapter():
    """Auto-initialize DB adapter from environment (PG-first, SQLite fallback).

    Called lazily on first _get_db() call if no adapter is injected.
    This ensures PG-first read path without requiring every service to
    manually call create_pg_adapter() at startup.
    """
    global _db_adapter, _adapter_initialized
    if _adapter_initialized:
        return
    _adapter_initialized = True

    pg_url = os.environ.get("KRONOS_PG_URL", "")
    if pg_url:
        try:
            from kronos_factors.pg_adapter import create_pg_adapter
            adapter = create_pg_adapter(pg_url)
            if adapter is not None:
                _db_adapter = adapter
                logger.info("Auto-initialized PG adapter: %s", pg_url.split("@")[-1] if "@" in pg_url else pg_url)
                return
        except Exception as e:
            logger.debug("PG auto-init failed: %s", e)

    sqlite_path = os.environ.get("KRONOS_SQLITE_PATH", "")
    if sqlite_path:
        try:
            from kronos_factors.pg_adapter import create_pg_adapter
            adapter = create_pg_adapter("")  # empty PG URL → SQLite fallback
            if adapter is not None:
                _db_adapter = adapter
                logger.info("Auto-initialized SQLite adapter: %s", sqlite_path)
                return
        except Exception as e:
            logger.debug("SQLite auto-init failed: %s", e)

    logger.debug("No DB configured — using stub (empty results)")


@contextmanager
def _get_db(readonly: bool = True):
    """Context manager yielding PG adapter (auto-init) or SQLite fallback or stub.

    Resolution: injected adapter → KRONOS_PG_URL → KRONOS_SQLITE_PATH → stub.
    """
    if _db_adapter is None:
        _auto_init_adapter()

    if _db_adapter is not None:
        yield _db_adapter
    else:
        yield _StubDB()


class StubMarketDataService:
    """Neutral market data stub."""
    @staticmethod
    def get_kline_df(code: str, lookback: int = 400):
        return None
    @staticmethod
    def get_stock_info(code: str):
        return None


def _get_market_data():
    """Get market data service (real or stub)."""
    if _market_data_adapter is not None:
        return _market_data_adapter
    return StubMarketDataService()


class _StubDB:
    """Neutral stub — returns empty results, triggering default scores."""

    class _StubResult:
        def fetchone(self): return None
        def fetchall(self): return []

    def execute(self, sql: str, params: tuple = None):
        return self._StubResult()

    def __enter__(self): return self
    def __exit__(self, *args): pass
