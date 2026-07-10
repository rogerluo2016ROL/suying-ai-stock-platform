from fastapi.testclient import TestClient
from app.main import app
from app import runtime

def test_gateway_readiness_survives_one_timeout(monkeypatch):
    async def probes():
        return {"trade-service": {"ready": False, "error": "timeout"}}
    monkeypatch.setattr(runtime, "probe_services", probes)
    monkeypatch.setattr(runtime, "probe_services", probes)
    response = TestClient(app).get("/api/v1/runtime/readiness")
    assert response.status_code == 200
    assert response.json()["ready"] is False
