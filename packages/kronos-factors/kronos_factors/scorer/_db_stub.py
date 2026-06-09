"""DB adapter stub — provides neutral fallback when no real DB is connected.

In production, inject a real DBAdapter via set_db_adapter().
"""

from contextlib import contextmanager
from typing import Optional

_db_adapter = None
_market_data_adapter = None


def set_db_adapter(adapter):
    """Inject a real DBAdapter instance. Call once at application startup."""
    global _db_adapter
    _db_adapter = adapter


def set_market_data_adapter(adapter):
    """Inject a real MarketDataAdapter instance."""
    global _market_data_adapter
    _market_data_adapter = adapter


@contextmanager
def _get_db(readonly: bool = True):
    """Context manager that yields either the injected DB adapter or a stub."""
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
