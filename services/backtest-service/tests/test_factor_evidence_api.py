from fastapi.testclient import TestClient
import pytest

from app.main import app
from app.adapters.base import BacktestRequest, compute_adjusted_return
from app.adapters.bi_trend import BiTrendAdapter
from app.adapters import registry
from app import routes


class _FakeAdapter:
    model_key = "test_model"
    def run(self, request, readiness):
        return {"status": "ready", "observations": 600, "factors": [{"factor_name": "score"}]}


def test_factor_evidence_runs_registered_adapter_and_persists_id(monkeypatch):
    monkeypatch.setitem(registry.BACKTEST_ADAPTERS, "test_model", _FakeAdapter())
    monkeypatch.setattr(routes, "_latest_backtest_readiness", lambda: {"status": "ready", "snapshot_id": "DS-1"})
    monkeypatch.setattr(routes, "_save_factor_evaluation", lambda *args: "FE-1")
    response = TestClient(app).get("/api/v1/backtest/factor-evidence", params={"model_key": "test_model"})
    assert response.status_code == 200
    assert response.json()["evaluation_id"] == "FE-1"


def test_unregistered_model_fails_closed():
    response = TestClient(app).get("/api/v1/backtest/factor-evidence", params={"model_key": "missing"})
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "MODEL_BACKTEST_NOT_IMPLEMENTED"


def test_adapter_blocks_without_readiness():
    report = BiTrendAdapter().run(BacktestRequest(model_key="bi_trend_launch"), {"status": "blocked"})
    assert report["status"] == "blocked"


def test_adjusted_return_uses_t1_open_adjustment_and_cost():
    # Entry adjusted value=10*2, exit adjusted value=12*2.1; gross=26%, cost=14bp.
    assert compute_adjusted_return(10, 2, 12, 2.1, 14) == pytest.approx(0.2586)
