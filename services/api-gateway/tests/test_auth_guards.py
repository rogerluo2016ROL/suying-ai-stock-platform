"""Gateway JWT guard tests — 401 without token, claims injected on success."""

import time
from email.message import Message

import jwt
import pytest
from fastapi.testclient import TestClient

from kronos_auth.config import KRONOS_JWT_SECRET, JWT_ALGORITHM


def _mint_token(role: str = "user", sub: str = "u1") -> str:
    now = int(time.time())
    payload = {
        "sub": sub,
        "name": "tester",
        "role": role,
        "type": "access",
        "iat": now,
        "exp": now + 600,
        "jti": "test-jti",
    }
    return jwt.encode(payload, KRONOS_JWT_SECRET, algorithm=JWT_ALGORITHM)


class _FakeUpstream:
    """Minimal urllib response stand-in (read/status/headers)."""

    def __init__(self):
        self.status = 200
        self.headers = Message()
        self.headers.add_header("Content-Type", "application/json")

    def read(self):
        return b'{"ok": true}'


@pytest.fixture
def upstream(monkeypatch):
    """Capture the outbound UrlRequest instead of hitting a real service."""
    import app.main as gateway

    captured = {}

    def _fake_urlopen(req, timeout=30):
        captured["url"] = req.full_url
        captured["headers"] = dict(req.header_items())
        return _FakeUpstream()

    monkeypatch.setattr(gateway, "urlopen", _fake_urlopen)
    return captured


@pytest.fixture
def client():
    from app.main import app

    return TestClient(app)


def test_proxy_requires_auth(client, upstream):
    resp = client.get("/api/v1/screener/modes")
    assert resp.status_code == 401
    assert "url" not in upstream  # 未触达上游


def test_proxy_rejects_invalid_token(client, upstream):
    resp = client.get(
        "/api/v1/screener/modes",
        headers={"Authorization": "Bearer not-a-token"},
    )
    assert resp.status_code == 401
    assert "url" not in upstream


def test_proxy_injects_owner_and_strips_spoofed_headers(client, upstream):
    resp = client.get(
        "/api/v1/screener/modes",
        headers={
            "Authorization": f"Bearer {_mint_token(sub='u-42')}",
            "X-Owner-User-Id": "victim",
        },
    )
    assert resp.status_code == 200
    assert upstream["headers"].get("X-owner-user-id") == "u-42"


def test_proxy_rejects_forged_service_auth_even_with_valid_jwt(client, upstream):
    # kronos_auth 优先校验 X-Service-Auth：dev fallback secret 一律拒绝（fail-closed），
    # 伪造头即使搭配有效 JWT 也 401，绝不授予服务间豁免。
    resp = client.get(
        "/api/v1/screener/modes",
        headers={
            "Authorization": f"Bearer {_mint_token(sub='u-42')}",
            "X-Service-Auth": "forged",
        },
    )
    assert resp.status_code == 401
    assert "url" not in upstream


def test_options_preflight_passes_without_token(client, upstream):
    resp = client.options("/api/v1/screener/modes")
    assert resp.status_code == 200
    assert "url" in upstream


def test_auth_endpoints_pass_without_token(client, upstream):
    resp = client.post("/api/v1/auth/login", content=b"{}")
    assert resp.status_code == 200
    assert upstream["url"].endswith("/api/v1/auth/login")


def test_service_health_alias_passes_without_token(client, upstream):
    resp = client.get("/api/v1/trade/health")
    assert resp.status_code == 200
    assert upstream["url"].endswith("/api/v1/health")
