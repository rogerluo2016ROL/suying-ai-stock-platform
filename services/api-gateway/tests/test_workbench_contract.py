import importlib.util
from pathlib import Path

from fastapi.testclient import TestClient


MODULE_PATH = Path(__file__).resolve().parents[1] / "app" / "main.py"
spec = importlib.util.spec_from_file_location("api_gateway_main_workbench", MODULE_PATH)
gateway = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(gateway)


def test_workbench_never_returns_preview_business_values():
    client = TestClient(gateway.app)

    response = client.get(
        "/api/v1/workbench/p0",
        headers={
            "X-Tenant-Id": "tenant-alpha",
            "X-Trade-Account-Id": "paper-001",
            "X-Data-Scope": "account",
            "X-Trade-Mode": "paper",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "unavailable"
    assert body["page"] == {
        "module": "p0",
        "route": "/p0",
        "title": "p0",
    }
    assert body["context"]["tenant_id"] == "tenant-alpha"
    assert body["context"]["account_id"] == "paper-001"
    assert body["context"]["data_scope"] == "account"
    assert body["freshness"]["status"] == "missing"
    assert body["sections"] == []
    assert body["actions"] == []


def test_unknown_workbench_route_returns_normalized_empty_envelope():
    client = TestClient(gateway.app)

    response = client.get("/api/v1/workbench/unknown-module")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "unavailable"
    assert body["page"]["module"] == "unknown-module"
    assert body["freshness"]["status"] == "missing"
    assert body["freshness"]["fallback_reason"] == "real workbench aggregation is not connected"
    assert body["sections"] == []
    assert body["actions"] == []
