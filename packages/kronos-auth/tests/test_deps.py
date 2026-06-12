"""Unit tests for kronos_auth.deps — JWT decode + role check + service auth."""

import time

import jwt
import pytest
from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient

from kronos_auth.config import KRONOS_JWT_SECRET, JWT_ALGORITHM, KRONOS_SERVICE_SECRET
from kronos_auth.deps import get_current_user_jwt, require_role


# ── Helpers ───────────────────────────────────────────────────────────────

def _make_token(role="user", exp_offset=3600, token_type="access", sub="1"):
    """Create a valid HS256 JWT for testing."""
    now = int(time.time())
    payload = {
        "sub": sub,
        "name": "Test User",
        "role": role,
        "iat": now,
        "exp": now + exp_offset,
        "type": token_type,
        "jti": "test-jti",
    }
    return jwt.encode(payload, KRONOS_JWT_SECRET, algorithm=JWT_ALGORITHM)


# ── Test app ──────────────────────────────────────────────────────────────

@pytest.fixture
def app():
    """Minimal FastAPI app with auth-protected test routes."""
    app = FastAPI()

    @app.get("/open")
    async def open_route():
        return {"status": "ok"}

    @app.get("/me")
    async def me(user: dict = Depends(get_current_user_jwt)):
        return {"sub": user["sub"], "role": user["role"]}

    @app.get("/admin-only")
    async def admin_only(user: dict = Depends(require_role("admin"))):
        return {"role": user["role"]}

    @app.get("/analyst-or-admin")
    async def analyst_or_admin(
        user: dict = Depends(require_role("admin", "internal_analyst")),
    ):
        return {"role": user["role"]}

    return app


@pytest.fixture
def client(app):
    return TestClient(app)


# ══════════════════════════════════════════════════════════════════════════
# AC-1: Valid token → 200
# ══════════════════════════════════════════════════════════════════════════

class TestValidToken:
    """AC-203.6: 有效 token → 200"""

    def test_valid_user_token_200(self, client):
        """Valid access token for 'user' returns 200 with decoded payload."""
        token = _make_token(role="user")
        r = client.get("/me", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["sub"] == "1"
        assert body["role"] == "user"

    def test_valid_admin_token_200(self, client):
        """Valid access token for 'admin' returns 200."""
        token = _make_token(role="admin")
        r = client.get("/admin-only", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200, r.text

    def test_valid_token_wrong_role_403(self, client):
        """Valid token but wrong role → 403."""
        token = _make_token(role="user")
        r = client.get("/admin-only", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 403, r.text

    def test_valid_token_multi_role_200(self, client):
        """internal_analyst can access analyst-or-admin route."""
        token = _make_token(role="internal_analyst")
        r = client.get("/analyst-or-admin", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200, r.text


# ══════════════════════════════════════════════════════════════════════════
# AC-2: 无 token → 401
# ══════════════════════════════════════════════════════════════════════════

class TestMissingToken:
    """AC-203.6: 无 token → 401"""

    def test_no_auth_header_401(self, client):
        """No Authorization header → 401."""
        r = client.get("/me")
        assert r.status_code == 401, r.text

    def test_empty_auth_header_401(self, client):
        """Empty Authorization header → 401."""
        r = client.get("/me", headers={"Authorization": ""})
        assert r.status_code == 401, r.text

    def test_not_bearer_401(self, client):
        """Authorization header that doesn't start with 'Bearer ' → 401."""
        r = client.get("/me", headers={"Authorization": "Basic dGVzdDpwYXNz"})
        assert r.status_code == 401, r.text

    def test_open_route_no_auth_200(self, client):
        """Open route without auth should still work."""
        r = client.get("/open")
        assert r.status_code == 200, r.text


# ══════════════════════════════════════════════════════════════════════════
# AC-3: 过期 token → 401
# ══════════════════════════════════════════════════════════════════════════

class TestExpiredToken:
    """Expired token → 401"""

    def test_expired_token_401(self, client):
        """Token with negative exp_offset (already expired) → 401."""
        token = _make_token(role="user", exp_offset=-3600)
        r = client.get("/me", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 401, r.text
        assert "expired" in r.text.lower()

    def test_expired_token_require_role_401(self, client):
        """Expired token on role-protected route → 401 (not 403)."""
        token = _make_token(role="admin", exp_offset=-3600)
        r = client.get("/admin-only", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 401, r.text


# ══════════════════════════════════════════════════════════════════════════
# AC-4: 错 role → 403
# ══════════════════════════════════════════════════════════════════════════

class TestWrongRole:
    """AC-203.6: 错 role → 403"""

    def test_user_access_admin_route_403(self, client):
        """user role trying admin-only route → 403."""
        token = _make_token(role="user")
        r = client.get("/admin-only", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 403, r.text
        assert "roles" in r.text.lower()

    def test_external_analyst_access_admin_route_403(self, client):
        """external_analyst trying admin-only route → 403."""
        token = _make_token(role="external_analyst")
        r = client.get("/admin-only", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 403, r.text


# ══════════════════════════════════════════════════════════════════════════
# AC-5: X-Service-Auth 豁免
# ══════════════════════════════════════════════════════════════════════════

class TestServiceAuthExemption:
    """AC-203.3: X-Service-Auth exemption"""

    def test_valid_service_auth_200(self, client):
        """Valid X-Service-Auth header grants admin-equivalent access."""
        r = client.get("/admin-only", headers={
            "X-Service-Auth": KRONOS_SERVICE_SECRET,
        })
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["role"] == "admin"

    def test_invalid_service_auth_401(self, client):
        """Wrong X-Service-Auth secret → 401."""
        r = client.get("/admin-only", headers={
            "X-Service-Auth": "wrong-secret",
        })
        assert r.status_code == 401, r.text

    def test_service_auth_me_returns_service_user(self, client):
        """Service auth /me returns the synthetic service user."""
        r = client.get("/me", headers={
            "X-Service-Auth": KRONOS_SERVICE_SECRET,
        })
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["sub"] == "service"
        assert body["role"] == "admin"


# ══════════════════════════════════════════════════════════════════════════
# Edge cases
# ══════════════════════════════════════════════════════════════════════════

class TestEdgeCases:

    def test_refresh_token_type_rejected(self, client):
        """A refresh-type JWT should be rejected (only 'access' allowed)."""
        token = _make_token(role="user", token_type="refresh")
        r = client.get("/me", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 401, r.text

    def test_tampered_token_401(self, client):
        """Tampered signature → 401."""
        token = _make_token(role="user")
        tampered = token[:-1] + ("A" if token[-1] != "A" else "B")
        r = client.get("/me", headers={"Authorization": f"Bearer {tampered}"})
        assert r.status_code == 401, r.text

    def test_service_auth_overrides_jwt(self, client):
        """When both X-Service-Auth and Authorization are present, service auth wins."""
        token = _make_token(role="user")
        r = client.get("/admin-only", headers={
            "X-Service-Auth": KRONOS_SERVICE_SECRET,
            "Authorization": f"Bearer {token}",
        })
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["role"] == "admin"  # service auth wins
