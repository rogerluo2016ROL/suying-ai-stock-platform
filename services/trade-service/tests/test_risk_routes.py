"""Tests for app/routers/risk.py — risk dashboard + risk-control write ops.

Auth / DB stubbing follows tests/test_risk_verdict_routes.py: kronos_auth and
app.database are stubbed in sys.modules before importing the router, and a
minimal FastAPI app + TestClient exercises the HTTP layer (status codes).
"""

import sys
import types
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "packages" / "kronos-auth"))


def _require_role_stub(*_roles):
    async def _dependency():
        return {"sub": "7", "role": "admin"}

    return _dependency


sys.modules["kronos_auth"] = types.SimpleNamespace(require_role=_require_role_stub)
sys.modules["app.database"] = types.SimpleNamespace(get_db=lambda: None)

from app.engine import PaperTradingEngine  # noqa: E402
from app.routers import risk  # noqa: E402
from app import routes  # noqa: E402


@pytest.fixture
def client(monkeypatch):
    """TestClient over a minimal app with only the risk router + fresh engine."""
    monkeypatch.setattr(risk, "engine", PaperTradingEngine())
    app = FastAPI()
    app.include_router(risk.router)
    return TestClient(app)


def test_risk_dashboard_returns_five_aggregate_keys(client):
    risk.engine.place_order("600519", "BUY", 1500.0, 100)

    resp = client.get("/api/v1/trade/risk-dashboard")

    assert resp.status_code == 200
    data = resp.json()
    for key in ("circuitBreaker", "positions", "strategies", "marketRegime", "auditSummary"):
        assert key in data
    assert data["circuitBreaker"]["state"] == "NORMAL"
    assert data["positions"][0]["code"] == "600519"
    assert data["marketRegime"]["data_source"] == "mock"


def test_risk_dashboard_reads_rebound_broker_config_account_id(client, monkeypatch):
    """Regression #14: risk.py 必须在调用时读 routes._broker_config（模块属性），
    而非 import 时 by-value 绑定的旧对象——broker_connect rebind 后才能拿到真实 account_id。"""
    seen = {}
    real_get_state = risk.get_state

    async def spy_get_state(acct_id):
        seen["acct_id"] = acct_id
        return await real_get_state(acct_id)

    monkeypatch.setattr(routes, "_broker_config", {"account_id": "ACC-TEST-42"})
    monkeypatch.setattr(risk, "get_state", spy_get_state)

    resp = client.get("/api/v1/trade/risk-dashboard")

    assert resp.status_code == 200
    assert seen.get("acct_id") == "ACC-TEST-42"  # 未修则恒为 "default"


def test_pause_and_resume_strategy_return_200_and_increase_audit_count(client):
    before = len(risk._risk_audit_entries)

    resp = client.post("/api/v1/trade/risk/strategy/strat-1/pause", json={"reason": "回撤超限"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "paused"
    assert len(risk._risk_audit_entries) == before + 1

    resp = client.post("/api/v1/trade/risk/strategy/strat-1/resume")
    assert resp.status_code == 200
    assert resp.json()["status"] == "active"
    assert len(risk._risk_audit_entries) == before + 2

    summary = client.get("/api/v1/trade/risk-dashboard").json()["auditSummary"]
    assert summary["total"] == before + 2
    assert summary["byAction"]["RISK_PAUSE_STRATEGY"] >= 1
    assert summary["byAction"]["RISK_RESUME_STRATEGY"] >= 1


def test_stop_loss_sells_paper_position(client):
    risk.engine.place_order("300750", "BUY", 200.0, 100)
    before = len(risk._risk_audit_entries)

    resp = client.post("/api/v1/trade/risk/position/300750/stop-loss", json={"reason": "跌破止损线"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["applied"] == "executed"
    assert data["order"]["volume"] == 100
    assert "300750" not in risk.engine.positions
    assert len(risk._risk_audit_entries) == before + 1


def test_stop_loss_without_position_returns_mock_semantics(client):
    resp = client.post("/api/v1/trade/risk/position/000001/stop-loss")

    assert resp.status_code == 200
    assert resp.json()["applied"] == "mock"
    assert resp.json()["order"] is None


def test_reduce_position_executes_partial_sell(client):
    risk.engine.place_order("600519", "BUY", 1500.0, 1000)
    before = len(risk._risk_audit_entries)

    resp = client.post("/api/v1/trade/risk/position/600519/reduce", json={"pct": 0.5})

    assert resp.status_code == 200
    data = resp.json()
    assert data["applied"] == "executed"
    assert data["sell_volume"] == 500
    assert risk.engine.positions["600519"].volume == 500
    assert len(risk._risk_audit_entries) == before + 1


def test_reduce_position_accepts_percentage_convention(client):
    risk.engine.place_order("600519", "BUY", 1500.0, 1000)

    resp = client.post("/api/v1/trade/risk/position/600519/reduce", json={"pct": 25})

    assert resp.status_code == 200
    assert resp.json()["sell_volume"] == 250
    assert risk.engine.positions["600519"].volume == 750


@pytest.mark.parametrize("pct", [0, -5, 100.1, 150])
def test_reduce_position_invalid_pct_returns_422(client, pct):
    resp = client.post("/api/v1/trade/risk/position/600519/reduce", json={"pct": pct})

    assert resp.status_code == 422


def test_liquidate_all_requires_confirm_then_sells_everything(client):
    risk.engine.place_order("600519", "BUY", 1500.0, 100)
    risk.engine.place_order("300750", "BUY", 200.0, 100)

    resp = client.post("/api/v1/trade/risk/liquidate-all", json={"confirm": False})
    assert resp.status_code == 409
    assert resp.json()["detail"]["error_code"] == "CONFIRMATION_REQUIRED"

    before = len(risk._risk_audit_entries)
    resp = client.post(
        "/api/v1/trade/risk/liquidate-all",
        json={"confirm": True, "reason": "系统性风险"},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["applied"] == "executed"
    assert data["liquidated"] == 2
    assert risk.engine.get_positions() == []
    assert len(risk._risk_audit_entries) == before + 1


def test_check_batch_returns_per_item_verdicts(client):
    resp = client.post(
        "/api/v1/trade/risk/check-batch",
        json={
            "items": [
                {"code": "600519", "action": "buy", "qty": 100, "price": 100.0},
                {"code": "300750", "action": "sell", "qty": 100, "price": 200.0},
            ]
        },
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert len(data["results"]) == 2

    buy, sell = data["results"]
    assert buy["code"] == "600519"
    assert buy["passed"] is True
    assert sell["passed"] is False  # 未持有 → 持仓充足 REJECT
    assert any(c["rule"] == "持仓充足" and c["level"] == "reject" for c in sell["checks"])
    assert data["passed"] is False


def test_check_batch_rejects_invalid_action(client):
    resp = client.post(
        "/api/v1/trade/risk/check-batch",
        json={"items": [{"code": "600519", "action": "hold", "qty": 100, "price": 100.0}]},
    )

    assert resp.status_code == 422
