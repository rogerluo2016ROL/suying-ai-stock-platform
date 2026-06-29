from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from app.auto_trading_engine import (
    BuyCondition,
    PositionRule,
    RiskRule,
    StrategyConfig,
)
from app import auto_trading_executor as exec_mod


def _make_strategy() -> StrategyConfig:
    return StrategyConfig(
        id="strat-lineage",
        name="lineage strategy",
        trade_mode="paper",
        check_interval_sec=60,
        capital=1_000_000,
        position_rules=PositionRule(max_positions=5, single_max_pct=0.20),
        risk_rules=RiskRule(daily_max_loss_pct=0.03),
        buy_conditions=[BuyCondition(field="signal_strength", operator=">=", threshold=80)],
        sell_conditions=[],
        picks=[
            {
                "code": "300750",
                "entry_price": 200.0,
                "candidate_id": "CAND-300750",
                "plan_id": "PLAN-AUTO",
            }
        ],
    )


def _make_running_state(strategy: StrategyConfig) -> exec_mod.ExecutorState:
    state = exec_mod.ExecutorState(strategy)
    state.status = "running"
    state._pause_event = asyncio.Event()
    state._pause_event.set()
    state._stop_event = asyncio.Event()
    return state


@pytest.mark.asyncio
async def test_place_order_sends_json_body_with_lineage_fields_to_trade_service():
    calls = []

    async def _post(url, payload, timeout=10):
        calls.append((url, payload, timeout))
        return {"order_id": "ORD-AUTO"}

    with patch.object(exec_mod, "_http_post_json", _post):
        await exec_mod._place_order(
            symbol="300750",
            direction="BUY",
            price=200.0,
            volume=100,
            trade_mode="paper",
            decision_context_id="CTX-AUTO",
            candidate_id="CAND-300750",
            plan_id="PLAN-AUTO",
        )

    assert calls, "trade-service should be called"
    _, payload, _ = calls[0]
    assert payload["code"] == "300750"
    assert payload["direction"] == "BUY"
    assert payload["decision_context_id"] == "CTX-AUTO"
    assert payload["candidate_id"] == "CAND-300750"
    assert payload["plan_id"] == "PLAN-AUTO"


@pytest.mark.asyncio
async def test_run_one_check_buy_order_carries_strategy_lineage():
    strategy = _make_strategy()
    state = _make_running_state(strategy)
    placed_orders = []

    async def _place_order(**kwargs):
        placed_orders.append(kwargs)
        return {"order_id": "ORD-AUTO"}

    with patch.object(exec_mod, "_check_forecast_risk", AsyncMock(return_value="")), \
         patch.object(exec_mod, "_fetch_positions", AsyncMock(return_value={"positions": []})), \
         patch.object(exec_mod, "_fetch_account", AsyncMock(return_value={"daily_pnl": 0})), \
         patch.object(exec_mod, "_fetch_signal", AsyncMock(return_value={"price": 200.0, "signal": {"score": 88}})), \
         patch.object(exec_mod, "_place_order", _place_order):
        await exec_mod._run_one_check(state, strategy)

    assert placed_orders, "BUY condition should place one order"
    order = placed_orders[0]
    assert order["trade_mode"] == "paper"
    assert order["decision_context_id"].startswith("CTX-auto-strat-lineage-300750-")
    assert order["candidate_id"] == "CAND-300750"
    assert order["plan_id"] == "PLAN-AUTO"
    submitted_logs = [entry for entry in state.logs if entry.message.startswith("买单已提交")]
    assert submitted_logs, "submitted order log should be recorded"
    assert submitted_logs[-1].details["decision_context_id"] == order["decision_context_id"]
    assert submitted_logs[-1].details["candidate_id"] == "CAND-300750"
    assert submitted_logs[-1].details["plan_id"] == "PLAN-AUTO"
