from fastapi.testclient import TestClient

from app.main import app


def test_gateway_live_endpoint_is_process_only():
    body = TestClient(app).get("/api/v1/health/live").json()
    assert body["live"] is True


def test_gateway_readiness_is_structured():
    response = TestClient(app).get("/api/v1/runtime/readiness")
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body["ready"], bool)
    assert isinstance(body["services"], dict)
