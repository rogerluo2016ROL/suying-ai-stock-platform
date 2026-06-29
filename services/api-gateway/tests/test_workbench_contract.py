import importlib.util
from pathlib import Path

from fastapi.testclient import TestClient


MODULE_PATH = Path(__file__).resolve().parents[1] / "app" / "main.py"
spec = importlib.util.spec_from_file_location("api_gateway_main_workbench", MODULE_PATH)
gateway = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(gateway)


def test_workbench_route_returns_page_envelope_with_platform_context():
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
    assert body["status"] == "ok"
    assert body["page"] == {
        "module": "p0",
        "route": "/workflow/p0",
        "title": "P0 主链路",
    }
    assert body["context"]["tenant_id"] == "tenant-alpha"
    assert body["context"]["account_id"] == "paper-001"
    assert body["context"]["data_scope"] == "account"
    assert body["data_domain"] == "account"
    assert body["freshness"]["status"] in {"fresh", "fallback"}
    assert any(section["key"] == "main_flow" for section in body["sections"])
    assert any(action["key"] == "open_candidate" for action in body["actions"])


def test_unknown_workbench_route_returns_normalized_empty_envelope():
    client = TestClient(gateway.app)

    response = client.get("/api/v1/workbench/unknown-module")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["page"]["module"] == "unknown-module"
    assert body["freshness"]["status"] == "fallback"
    assert body["freshness"]["fallback_reason"] == "workbench module not implemented"
    assert body["sections"] == []
    assert body["actions"] == []
