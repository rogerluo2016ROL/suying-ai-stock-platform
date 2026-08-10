from fastapi.testclient import TestClient
from app.main import app
from app import runtime

MICROSERVICE_NAMES = {
    "api-gateway", "backend-auth", "screener-service", "prediction-service",
    "strategy-service", "signal-service", "alert-service", "trade-service",
    "backtest-service", "training-service", "diagnosis-service", "data-service",
}


def _ok_http(name, port, base):
    return {"name": name, "port": port, "status": "ok", "latency_ms": 1.0}


def _ok_tcp(name, host, port):
    return {"name": name, "port": port, "status": "ok", "latency_ms": 1.0}


def test_gateway_readiness_survives_one_timeout(monkeypatch):
    async def fake_matrix():
        return [
            {"name": "api-gateway", "port": 8080, "status": "ok", "latency_ms": 0.0},
            {"name": "trade-service", "port": 8006, "status": "timeout", "latency_ms": 2000.0},
            {"name": "postgresql", "port": 6432, "status": "ok", "latency_ms": 1.0},
        ]
    monkeypatch.setattr(runtime, "probe_runtime_matrix", fake_matrix)
    response = TestClient(app).get("/api/v1/runtime/readiness")
    assert response.status_code == 200
    body = response.json()
    assert body["ready"] is False
    assert body["status"] == "degraded"
    assert body["services"]["trade-service"]["status"] == "timeout"


def test_probe_service_names_are_stable(monkeypatch):
    async def fake_probe(name, base):
        return name, {"ready": True}
    monkeypatch.setattr(runtime, "_probe", fake_probe)
    import asyncio
    result = asyncio.run(runtime.probe_services())
    assert "api-gateway" in result
    assert "backend-auth" in result
    assert "trade-service" in result


def test_readiness_all_ok(monkeypatch):
    async def fake_http(name, port, base):
        return _ok_http(name, port, base)

    async def fake_tcp(name, host, port):
        return _ok_tcp(name, host, port)

    monkeypatch.setattr(runtime, "_probe_http", fake_http)
    monkeypatch.setattr(runtime, "_probe_tcp", fake_tcp)
    monkeypatch.setenv("KRONOS_PG_PORT", "6432")
    monkeypatch.setenv("KRONOS_REDIS_PORT", "7379")
    body = TestClient(app).get("/api/v1/runtime/readiness").json()
    assert body["live"] is True
    assert body["ready"] is True
    assert body["status"] == "ok"

    components = body["components"]
    # 12 个微服务（含 self）+ PostgreSQL + Redis
    assert len(components) == 14
    names = {c["name"] for c in components}
    assert names == MICROSERVICE_NAMES | {"postgresql", "redis"}
    for c in components:
        assert set(c) == {"name", "port", "status", "latency_ms"}
        assert isinstance(c["port"], int)
        assert c["status"] == "ok"
        assert isinstance(c["latency_ms"], (int, float))
    # self 直接标记 ok，不自探
    assert components[0] == {"name": "api-gateway", "port": 8080, "status": "ok", "latency_ms": 0.0}
    # 兼容键: services 只含微服务
    assert set(body["services"]) == MICROSERVICE_NAMES
    assert all(v["ready"] is True for v in body["services"].values())


def test_readiness_partial_timeout(monkeypatch):
    async def fake_http(name, port, base):
        if name == "trade-service":
            return {"name": name, "port": port, "status": "timeout", "latency_ms": 2000.0}
        if name == "alert-service":
            return {"name": name, "port": port, "status": "down", "latency_ms": None}
        return _ok_http(name, port, base)

    async def fake_tcp(name, host, port):
        return _ok_tcp(name, host, port)

    monkeypatch.setattr(runtime, "_probe_http", fake_http)
    monkeypatch.setattr(runtime, "_probe_tcp", fake_tcp)
    body = TestClient(app).get("/api/v1/runtime/readiness").json()
    assert body["ready"] is False
    assert body["status"] == "degraded"

    by_name = {c["name"]: c for c in body["components"]}
    assert by_name["trade-service"]["status"] == "timeout"
    assert isinstance(by_name["trade-service"]["latency_ms"], (int, float))
    assert by_name["alert-service"]["status"] == "down"
    assert by_name["alert-service"]["latency_ms"] is None
    assert body["services"]["trade-service"] == {"ready": False, "status": "timeout", "latency_ms": 2000.0}
    assert body["services"]["alert-service"] == {"ready": False, "status": "down", "latency_ms": None}


def test_readiness_infra_tcp_failure(monkeypatch):
    async def fake_http(name, port, base):
        return _ok_http(name, port, base)

    async def fake_tcp(name, host, port):
        return {"name": name, "port": port, "status": "down", "latency_ms": None}

    monkeypatch.setattr(runtime, "_probe_http", fake_http)
    monkeypatch.setattr(runtime, "_probe_tcp", fake_tcp)
    monkeypatch.setenv("KRONOS_PG_PORT", "6432")
    monkeypatch.setenv("KRONOS_REDIS_PORT", "7379")
    body = TestClient(app).get("/api/v1/runtime/readiness").json()
    # 微服务全部 ok → 旧契约 ready 仍为 True；总状态含基础设施 → degraded
    assert body["ready"] is True
    assert body["status"] == "degraded"
    assert set(body["services"]) == MICROSERVICE_NAMES

    by_name = {c["name"]: c for c in body["components"]}
    for infra in ("postgresql", "redis"):
        assert by_name[infra]["status"] == "down"
        assert by_name[infra]["latency_ms"] is None
        assert infra not in body["services"]


def test_readiness_skips_infra_when_port_env_unset(monkeypatch):
    """Regression #16: KRONOS_PG_PORT/REDIS_PORT 未设时不探 infra、不报 down，
    避免容器内默认端口不通造成 status 误判 degraded。"""
    async def fake_http(name, port, base):
        return _ok_http(name, port, base)

    tcp_calls = []

    async def fake_tcp(name, host, port):
        tcp_calls.append((name, host, port))
        return _ok_tcp(name, host, port)

    monkeypatch.setattr(runtime, "_probe_http", fake_http)
    monkeypatch.setattr(runtime, "_probe_tcp", fake_tcp)
    monkeypatch.delenv("KRONOS_PG_PORT", raising=False)
    monkeypatch.delenv("KRONOS_REDIS_PORT", raising=False)

    body = TestClient(app).get("/api/v1/runtime/readiness").json()

    names = {c["name"] for c in body["components"]}
    assert "postgresql" not in names
    assert "redis" not in names
    assert tcp_calls == []  # infra 未被探活
    assert body["ready"] is True
    assert body["status"] == "ok"  # infra 缺席不导致 degraded


def test_probe_http_does_not_follow_redirects(monkeypatch):
    """Regression #16: _probe_http 不跟随重定向（302 不再被误判 ok）。"""
    from urllib.error import HTTPError
    import asyncio

    class _RedirectingOpener:
        def open(self, url, timeout=None):
            raise HTTPError(url, 302, "Found", {}, None)

    monkeypatch.setattr(runtime, "_http_opener", _RedirectingOpener())

    result = asyncio.run(runtime._probe_http("svc", 8000, "http://svc:8000"))
    assert result["status"] == "down"
