"""Auth guard tests — real 401/403 behavior with dependency_overrides cleared.

The autouse conftest fixture installs an admin bypass; these tests remove it
via monkeypatch.delitem so the real kronos_auth dependencies run.
"""

import time

import jwt
import pytest
from fastapi.testclient import TestClient

from kronos_auth import get_current_user_jwt
from kronos_auth.config import KRONOS_JWT_SECRET, JWT_ALGORITHM


def _mint_token(role: str = "admin") -> str:
    now = int(time.time())
    payload = {
        "sub": "u1",
        "name": "tester",
        "role": role,
        "type": "access",
        "iat": now,
        "exp": now + 600,
        "jti": "test-jti",
    }
    return jwt.encode(payload, KRONOS_JWT_SECRET, algorithm=JWT_ALGORITHM)


@pytest.fixture
def client(monkeypatch):
    from app.main import app

    monkeypatch.delitem(app.dependency_overrides, get_current_user_jwt, raising=False)
    return TestClient(app)


def test_sync_stocks_requires_auth(client):
    resp = client.post("/api/v1/data/sync/stocks")
    assert resp.status_code == 401


def test_wrong_service_auth_header_rejected(client):
    resp = client.post(
        "/api/v1/data/sync/stocks",
        headers={"X-Service-Auth": "wrong-secret"},
    )
    assert resp.status_code == 401


def test_read_endpoint_accepts_valid_jwt(client):
    resp = client.get(
        "/api/v1/data/jobs",
        headers={"Authorization": f"Bearer {_mint_token('user')}"},
    )
    assert resp.status_code == 200


def test_sync_stocks_rejects_plain_user_role(client):
    resp = client.post(
        "/api/v1/data/sync/stocks",
        headers={"Authorization": f"Bearer {_mint_token('user')}"},
    )
    assert resp.status_code == 403
