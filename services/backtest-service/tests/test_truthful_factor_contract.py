import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.main import app


def test_backtest_endpoints_fail_closed():
    client = TestClient(app)
    assert client.post("/api/v1/backtest/run").json()["detail"]["code"] == "MODEL_BACKTEST_NOT_IMPLEMENTED"
    assert client.post("/api/v1/backtest/run").status_code == 409
    response = client.post("/api/v1/backtest/calibrate")
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "MODEL_CALIBRATION_NOT_IMPLEMENTED"


def test_factor_evidence_and_compare_are_truthful():
    client = TestClient(app)
    evidence = client.get("/api/v1/backtest/factor-evidence", params={"model_key": "x"})
    assert evidence.json()["status"] == "unsupported"
    compare = client.post("/api/v1/backtest/compare")
    assert compare.status_code == 422
    assert compare.json()["detail"]["code"] == "INSUFFICIENT_EVIDENCE"
