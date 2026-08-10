"""Tests for GET /api/v1/strategy/plans/{plan_id}/settlement-report.

Auth + DB are stubbed exactly like services/trade-service/tests/: kronos_auth
and app.database are replaced in sys.modules before importing app.routes, and
route handlers are invoked directly with user=/db= kwargs.
"""

import sys
import types
from pathlib import Path

import pytest
from fastapi import HTTPException

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "packages" / "kronos-auth"))


def _require_role_stub(*_roles):
    async def _dependency():
        return {"sub": "7", "role": "user"}

    return _dependency


sys.modules["kronos_auth"] = types.SimpleNamespace(require_role=_require_role_stub)
sys.modules["app.database"] = types.SimpleNamespace(get_db=lambda: None)

from app import routes  # noqa: E402
from app.settlement_store import SettlementRecord, get_settlement_store  # noqa: E402

USER = {"sub": "7", "role": "user"}


def _create_plan(**kwargs) -> object:
    kwargs.setdefault("name", "结算测试方案")
    kwargs.setdefault("picks", [{"code": "300750", "name": "宁德时代", "price": 218.5}])
    kwargs.setdefault("owner_user_id", "7")
    return routes.store.create(**kwargs)


async def _call(plan_id: str):
    return await routes.get_settlement_report(
        plan_id=plan_id,
        tenant_id=None,
        account_id=None,
        data_scope=None,
        db=None,
        user=USER,
    )


@pytest.mark.asyncio
async def test_settled_plan_with_record_returns_report():
    plan = _create_plan()
    get_settlement_store().record(SettlementRecord(
        plan_id=plan.id,
        settled_at="2026-06-25",
        period={"start_date": "2026-06-21", "end_date": "2026-06-25", "holding_days": 5},
        summary={
            "total_pnl": 12580.0, "total_pnl_pct": 0.032,
            "annualized_return": 0.39, "max_drawdown": -0.021,
            "win_rate": 0.8, "win_count": 4, "total_stock_count": 5,
            "profit_loss_ratio": 1.9, "sharpe_ratio": 1.85, "trade_count": 10,
        },
        trades=[
            {"time": "2026-06-21T09:35:00+00:00", "code": "300750", "name": "宁德时代",
             "direction": "buy", "qty": 1000, "price": 218.5, "pnl": 0.0},
            {"time": "2026-06-25T14:55:00+00:00", "code": "300750", "name": "宁德时代",
             "direction": "sell", "qty": 1000, "price": 226.8, "pnl": 8300.0},
        ],
        positions=[
            {"code": "600519", "name": "贵州茅台", "qty": 100, "avg_cost": 1750.0,
             "close_price": 1820.0, "market_value": 182000.0, "pnl": 7000.0, "pnl_pct": 0.04},
        ],
    ))

    resp = await _call(plan.id)

    assert resp["plan_id"] == plan.id
    assert resp["settlement_date"] == "2026-06-25"
    for key in ("summary", "trades", "positions", "period"):
        assert key in resp
    summary = resp["summary"]
    for key in ("total_pnl", "annualized_return", "max_drawdown",
                "win_rate", "profit_loss_ratio", "sharpe_ratio"):
        assert key in summary
    assert summary["total_pnl"] == 12580.0
    assert resp["period"] == {"start_date": "2026-06-21", "end_date": "2026-06-25", "holding_days": 5}
    assert resp["trades"][0]["code"] == "300750"
    assert resp["trades"][0]["direction"] == "buy"
    assert resp["positions"][0]["code"] == "600519"
    assert resp["data_source"] == "memory"


@pytest.mark.asyncio
async def test_settled_plan_without_record_falls_back_to_mock():
    plan = _create_plan()
    routes.store.update(plan.id, status="settled")

    resp = await _call(plan.id)

    assert resp["plan_id"] == plan.id
    assert resp["data_source"] == "mock"
    assert resp["summary"]["total_pnl_pct"] is not None
    assert resp["trades"] and resp["positions"]
    assert resp["period"]["start_date"] and resp["period"]["end_date"]


@pytest.mark.asyncio
async def test_unsettled_plan_returns_409():
    plan = _create_plan()  # status stays "draft"

    with pytest.raises(HTTPException) as exc:
        await _call(plan.id)

    assert exc.value.status_code == 409
    assert "结算" in exc.value.detail


@pytest.mark.asyncio
async def test_missing_plan_returns_404():
    with pytest.raises(HTTPException) as exc:
        await _call("PLAN-NO-SUCH-PLAN")

    assert exc.value.status_code == 404
    assert exc.value.detail == "方案不存在"
