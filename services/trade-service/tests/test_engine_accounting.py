"""Accounting correctness tests for PaperTradingEngine (codegraph-driven).

Source: 2026-06-23 codegraph investigation found trade-service's order/accounting
path had NO correctness tests (only ``test_circuit_breaker_concurrency.py``).
These target the paper-trading accounting logic in ``app/engine.py`` — pure
in-memory calculations, no Xtquant / PG / network. See ``TEST_PLAN_engine.md``.

RED tests below pin three suspected money bugs:
  - B1 short-sell inflates ``available`` / ``total_capital`` out of thin air
  - B2 oversell (sell > position) inflates the balance by the oversold amount
  - B3 unknown direction (e.g. ``HOLD``) falls through the ``else`` to SELL

Each RED test asserts the CORRECT behavior and is expected to FAIL on the
current implementation; fixing the bug turns it green.
"""
from __future__ import annotations

import pytest

from app.engine import PaperTradingEngine


@pytest.fixture
def engine():
    """Fresh engine per test — do NOT use the module-level ``get_engine()``
    singleton, which would leak state across tests."""
    return PaperTradingEngine()


# --- GREEN: known-correct behavior (sanity that env + assertions work) ---

def test_limit_buy_decreases_available(engine):
    """Sanity: a limit BUY reduces available cash by price * volume."""
    engine.place_order("AAPL", "BUY", 100.0, 50)
    assert engine.account.available == pytest.approx(1_000_000 - 100.0 * 50)


# --- RED: suspected money bugs (expected to FAIL — these pin the bugs) ---

def test_short_sell_must_not_inflate_total_capital(engine):
    """B1: selling a position you don't own must NOT create money.
    No position exists for NOEXIST, so total_capital must stay at the initial
    1,000,000 (conservation — nothing of value changed hands).
    CURRENT (buggy): ``available += 50*100`` → total_capital becomes 1,005,000.
    """
    initial = engine.account.total_capital
    engine.place_order("NOEXIST", "SELL", 100.0, 50)
    assert engine.account.total_capital <= initial


def test_oversell_must_not_inflate_total_capital(engine):
    """B2: selling MORE than the position must NOT inflate the balance by the
    oversold amount. Buy 100 @ 100, then sell 150 @ 100 (price == cost → no
    PnL), so total_capital must conserve at 1,000,000.
    CURRENT (buggy): ``available += 150*100`` → total_capital 1,005,000.
    """
    engine.place_order("AAPL", "BUY", 100.0, 100)   # hold 100 @ 100
    engine.place_order("AAPL", "SELL", 100.0, 150)  # oversell 50
    assert engine.account.total_capital == pytest.approx(1_000_000)


def test_unknown_direction_must_not_act_as_sell(engine):
    """B3: a direction that is neither BUY nor SELL must NOT be treated as SELL.
    CURRENT (buggy): the ``else`` branch treats HOLD as SELL → available += 50*100.
    """
    initial_available = engine.account.available
    engine.place_order("AAPL", "HOLD", 100.0, 50)
    assert engine.account.available == pytest.approx(initial_available)
