"""AC-10 Verification — risk-check DB unreachable must pause the executor, not trade.

The 3 risk-check functions (_check_announcement_risk / _get_atr_stop_loss /
_check_forecast_risk) raise RiskCheckUnavailable when the risk DB is down.
_run_one_check catches it and calls mgr.pause() so the loop stops trading
until manual resume — it must NOT fall back to a neutral default that would
let trading continue without stop-loss / risk gating.

Run: cd services/strategy-service && ../../../backend/.venv/bin/pytest tests/test_fail_safe_db_unreachable.py -v
"""

from __future__ import annotations

import asyncio
from unittest.mock import patch, AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import OperationalError

from app.auto_trading_engine import (
    StrategyConfig,
    PositionRule,
    RiskRule,
    BuyCondition,
    SellCondition,
)
from app import auto_trading_executor as exec_mod


def _make_strategy() -> StrategyConfig:
    """A strategy holding one position + one buy pick so both the SELL and
    BUY branches exercise a risk check."""
    return StrategyConfig(
        id="sit-strat-failsafe",
        name="failsafe-sit",
        trade_mode="paper",
        check_interval_sec=60,
        capital=1_000_000,
        position_rules=PositionRule(max_positions=5, single_max_pct=0.20),
        risk_rules=RiskRule(daily_max_loss_pct=0.03),
        buy_conditions=[BuyCondition(field="signal_strength", operator=">=", threshold=999)],
        sell_conditions=[SellCondition(field="pnl_pct", operator="<=", threshold=-2.0)],
        picks=[{"code": "000001", "entry_price": 10.0}],
    )


def _register_in_store(strategy: StrategyConfig) -> None:
    """Register the strategy in the singleton store so ExecutorManager.pause()
    can update its status (pause calls store.update)."""
    store = exec_mod.get_strategy_store()
    store.create(strategy)


def _make_running_state(strategy: StrategyConfig) -> exec_mod.ExecutorState:
    state = exec_mod.ExecutorState(strategy)
    state.status = "running"
    state._pause_event = asyncio.Event()
    state._pause_event.set()  # not paused initially
    state._stop_event = asyncio.Event()
    # _run_one_check calls mgr.pause(strategy.id) — that looks up the global
    # ExecutorManager._executors, so the state must be registered there.
    mgr = exec_mod.get_executor_manager()
    mgr._executors[strategy.id] = state
    return state


def _dead_engine():
    """A stand-in _risk_engine whose .connect() async-CM raises on enter."""
    engine = MagicMock()

    class _BoomCM:
        async def __aenter__(self, *a, **kw):
            raise OperationalError("SELECT 1", {}, OperationalError("connect ECONNREFUSED"))
        async def __aexit__(self, *a, **kw):
            return False

    engine.connect = MagicMock(return_value=_BoomCM())
    return engine


@pytest.mark.asyncio
async def test_db_unreachable_pauses_executor_not_orders():
    """AC-10: DB unreachable on a risk check → executor paused, no order placed."""
    strategy = _make_strategy()
    _register_in_store(strategy)
    state = _make_running_state(strategy)

    # Stub out HTTP dependencies so the test stays local.
    async def _positions(_mode):
        return {"positions": [{"code": "600000", "volume": 100, "pnl_pct": -5.0,
                                "market_value": 1000}]}

    async def _account(_mode):
        return {"daily_pnl": 0}

    async def _signal(_code):
        return {"price": 10.0, "score": 50}

    placed_orders = []
    async def _place_order(**kw):
        placed_orders.append(kw)
        return {"order_id": "SHOULD-NOT-HAPPEN"}

    with patch.object(exec_mod, "_risk_engine", _dead_engine()), \
         patch.object(exec_mod, "_fetch_positions", _positions), \
         patch.object(exec_mod, "_fetch_account", _account), \
         patch.object(exec_mod, "_fetch_signal", _signal), \
         patch.object(exec_mod, "_place_order", _place_order):
        await exec_mod._run_one_check(state, strategy)

    # ── Assertions (AC-10 Verification) ──────────────────────────────
    assert state.status == "paused", f"expected paused, got {state.status}"
    assert state.orders_placed == 0, "no order must be placed on DB failure"
    assert placed_orders == [], "place_order must never be called"
    assert state._pause_event is not None and not state._pause_event.is_set(), \
        "pause_event must be cleared (loop blocked)"

    fail_safe_logs = [e for e in state.logs if e.details.get("fail_safe")]
    assert fail_safe_logs, "a fail-safe log entry must be recorded"
    assert any("fail-safe" in e.message.lower() or "暂停" in e.message for e in state.logs), \
        "structured log must announce the pause"


@pytest.mark.asyncio
async def test_db_healthy_does_not_pause():
    """Regression: DB healthy → risk checks return normally, executor keeps running."""
    strategy = _make_strategy()
    _register_in_store(strategy)
    state = _make_running_state(strategy)

    # Healthy risk checks: no risk found.
    with patch.object(exec_mod, "_check_announcement_risk", AsyncMock(return_value=(False, ""))), \
         patch.object(exec_mod, "_check_forecast_risk", AsyncMock(return_value="")), \
         patch.object(exec_mod, "_get_atr_stop_loss", AsyncMock(return_value=0.0)), \
         patch.object(exec_mod, "_fetch_positions", AsyncMock(return_value={"positions": []})), \
         patch.object(exec_mod, "_fetch_account", AsyncMock(return_value={"daily_pnl": 0})), \
         patch.object(exec_mod, "_fetch_signal", AsyncMock(return_value={"price": 10.0})), \
         patch.object(exec_mod, "_place_order", AsyncMock(return_value={"order_id": "x"})):
        await exec_mod._run_one_check(state, strategy)

    assert state.status == "running", "healthy DB must not pause"
    assert state.checks_completed == 1
    fail_safe_logs = [e for e in state.logs if e.details.get("fail_safe")]
    assert not fail_safe_logs, "no fail-safe log when DB is healthy"


@pytest.mark.asyncio
async def test_risk_functions_raise_on_db_failure():
    """Unit: each risk function raises RiskCheckUnavailable (not a neutral default)."""
    with patch.object(exec_mod, "_risk_engine", _dead_engine()):
        with pytest.raises(exec_mod.RiskCheckUnavailable):
            await exec_mod._check_announcement_risk("600000")
        with pytest.raises(exec_mod.RiskCheckUnavailable):
            await exec_mod._get_atr_stop_loss("600000")
        with pytest.raises(exec_mod.RiskCheckUnavailable):
            await exec_mod._check_forecast_risk("600000")
