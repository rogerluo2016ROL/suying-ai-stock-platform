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

def test_probe_service_names_are_stable(monkeypatch):
    async def fake_probe(name, base):
        return name, {"ready": True}
    monkeypatch.setattr(runtime, "_probe", fake_probe)
    import asyncio
    result = asyncio.run(runtime.probe_services())
    assert "api-gateway" in result
    assert "backend-auth" in result
    assert "trade-service" in result
