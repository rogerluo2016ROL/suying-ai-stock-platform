import asyncio
from datetime import datetime, timezone
import json

from app import auto_strategy_pg_store
from app.auto_trading_engine import (
    BuyCondition,
    PositionRule,
    RiskRule,
    SellCondition,
    StrategyConfig,
)


class _FakeResult:
    def __init__(self, *, row=None, rows=None):
        self._row = row
        self._rows = rows or []

    def fetchone(self):
        return self._row

    def fetchall(self):
        return self._rows


class _FakeDb:
    def __init__(self):
        self.calls = []

    async def execute(self, statement, params=None):
        sql = str(statement)
        params = params or {}
        self.calls.append((sql, params))
        if "DELETE FROM auto_trading_strategies" in sql:
            return _FakeResult(row=("STR-1",))
        row = {
            "strategy_id": "STR-1",
            "name": "UAT策略",
            "description": "持久化验证",
            "status": "draft",
            "source_type": "custom",
            "source_scheme_id": "",
            "buy_conditions": [{"field": "signal_strength", "operator": ">=", "threshold": 60, "description": "UAT"}],
            "sell_conditions": [{"field": "stop_loss", "operator": ">=", "threshold": 3, "description": "UAT"}],
            "position_rules": {"max_positions": 5, "single_max_pct": 0.2, "total_position_cap_pct": 0.8},
            "risk_rules": {"daily_max_loss_pct": 0.03, "stop_loss_pct": 0.03, "take_profit_pct": 0.15},
            "trade_mode": "paper",
            "check_interval_sec": 300,
            "capital": 1_000_000,
            "picks": [{"code": "000001", "name": "平安银行"}],
            "created_at": datetime(2026, 6, 29, 10, 0, tzinfo=timezone.utc),
            "updated_at": datetime(2026, 6, 29, 10, 1, tzinfo=timezone.utc),
        }
        if "WHERE strategy_id = :strategy_id" in sql:
            return _FakeResult(row=row)
        return _FakeResult(rows=[row])


def test_record_strategy_persists_conditions_rules_and_picks():
    db = _FakeDb()
    strategy = StrategyConfig(
        id="STR-1",
        name="UAT策略",
        description="持久化验证",
        buy_conditions=[BuyCondition(field="signal_strength", operator=">=", threshold=60, description="UAT")],
        sell_conditions=[SellCondition(field="stop_loss", operator=">=", threshold=3, description="UAT")],
        position_rules=PositionRule(max_positions=5, single_max_pct=0.2, total_position_cap_pct=0.8),
        risk_rules=RiskRule(daily_max_loss_pct=0.03, stop_loss_pct=0.03, take_profit_pct=0.15),
        picks=[{"code": "000001", "name": "平安银行"}],
        created_at="2026-06-29T10:00:00+00:00",
        updated_at="2026-06-29T10:01:00+00:00",
    )

    asyncio.run(auto_strategy_pg_store.record(db, strategy=strategy))

    sql, params = db.calls[0]
    assert "INSERT INTO auto_trading_strategies" in sql
    assert "ON CONFLICT (strategy_id) DO UPDATE" in sql
    assert json.loads(params["buy_conditions"])[0]["field"] == "signal_strength"
    assert json.loads(params["picks"])[0]["code"] == "000001"


def test_query_strategy_round_trips_to_strategy_config():
    db = _FakeDb()

    strategies = asyncio.run(auto_strategy_pg_store.list_all(db))
    detail = asyncio.run(auto_strategy_pg_store.get(db, "STR-1"))
    deleted = asyncio.run(auto_strategy_pg_store.delete(db, "STR-1"))

    assert strategies[0].id == "STR-1"
    assert strategies[0].buy_conditions[0].threshold == 60
    assert strategies[0].picks[0]["code"] == "000001"
    assert detail is not None
    assert detail.risk_rules.stop_loss_pct == 0.03
    assert deleted is True
