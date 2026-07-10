import importlib.util
from email.message import Message
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "app" / "main.py"
spec = importlib.util.spec_from_file_location("api_gateway_main", MODULE_PATH)
gateway = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(gateway)


def test_resolve_target_routes_core_service_prefixes():
    target = gateway._resolve_target("/api/v1/trade/orders", "page=1")

    assert target == "http://localhost:8006/api/v1/trade/orders?page=1"


def test_resolve_target_covers_frontend_module_prefixes():
    expected = {
        "/api/v1/auth/me": "http://localhost:9001/api/v1/auth/me",
        "/api/v1/admin/users": "http://localhost:9001/api/v1/admin/users",
        "/api/v1/screener/modes": "http://localhost:8001/api/v1/screener/modes",
        "/api/v1/prediction/status": "http://localhost:8002/api/v1/prediction/status",
        "/api/v1/strategy/templates": "http://localhost:8003/api/v1/strategy/templates",
        "/api/v1/signal/levels": "http://localhost:8004/api/v1/signal/levels",
        "/api/v1/dashboard/summary": "http://localhost:8001/api/v1/dashboard/summary",
        "/api/v1/data/status": "http://localhost:8010/api/v1/data/status",
        "/api/v1/alert/unread-count": "http://localhost:8005/api/v1/alert/unread-count",
        "/api/v1/trade/orders": "http://localhost:8006/api/v1/trade/orders",
        "/api/v1/backtest/factors": "http://localhost:8007/api/v1/backtest/factors",
        "/api/v1/training/tasks": "http://localhost:8008/api/v1/training/tasks",
        "/api/v1/diagnosis/history": "http://localhost:8009/api/v1/diagnosis/history",
    }

    for path, target in expected.items():
        assert gateway._resolve_target(path, "") == target


def test_resolve_target_rewrites_service_health_alias():
    target = gateway._resolve_target("/api/v1/trade/health", "")

    assert target == "http://localhost:8006/api/v1/health"


def test_resolve_target_rewrites_backend_health_alias_to_api_health():
    target = gateway._resolve_target("/api/v1/auth/health", "")

    assert target == "http://localhost:9001/api/health"


def test_resolve_target_keeps_gateway_health_local():
    assert gateway._resolve_target("/health", "") is None


def test_resolve_target_does_not_match_similar_prefixes():
    assert gateway._resolve_target("/api/v1/tradeoff", "") is None


def test_data_routes_to_dedicated_data_service():
    assert gateway._resolve_target("/api/v1/data/status", "") == "http://localhost:8010/api/v1/data/status"


def test_default_network_mode_uses_compose_inside_container(monkeypatch):
    monkeypatch.delenv("GATEWAY_NETWORK_MODE", raising=False)
    monkeypatch.setattr(gateway.os.path, "exists", lambda path: path == "/.dockerenv")

    assert gateway._default_network_mode() == "compose"


def test_proxy_response_forwards_multiple_set_cookie_headers():
    upstream_headers = Message()
    upstream_headers.add_header("Set-Cookie", "refresh_token=one; Path=/api/v1/auth")
    upstream_headers.add_header("Set-Cookie", "csrf=two; Path=/")
    upstream_headers.add_header("X-Request-ID", "req-1")
    upstream_headers.add_header("Content-Type", "application/json")

    response = gateway._proxy_response(b"{}", 200, upstream_headers)

    assert response.headers["x-request-id"] == "req-1"
    set_cookie_headers = [
        value.decode("latin-1")
        for key, value in response.raw_headers
        if key == b"set-cookie"
    ]
    assert set_cookie_headers == [
        "refresh_token=one; Path=/api/v1/auth",
        "csrf=two; Path=/",
    ]
