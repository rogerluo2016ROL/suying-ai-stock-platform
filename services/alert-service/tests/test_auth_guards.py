"""Auth guard tests — real 401 behavior with dependency_overrides cleared."""

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


def test_list_alerts_requires_auth(client):
    resp = client.get("/api/v1/alert/alerts")
    assert resp.status_code == 401


def test_trigger_rejects_wrong_service_auth(client):
    resp = client.post(
        "/api/v1/alert/trigger?title=t&message=m",
        headers={"X-Service-Auth": "wrong-secret"},
    )
    assert resp.status_code == 401


def test_trigger_rejects_plain_user_role(client):
    resp = client.post(
        "/api/v1/alert/trigger?title=t&message=m",
        headers={"Authorization": f"Bearer {_mint_token('user')}"},
    )
    assert resp.status_code == 403


def test_unread_count_accepts_valid_jwt(client):
    resp = client.get(
        "/api/v1/alert/unread-count",
        headers={"Authorization": f"Bearer {_mint_token('user')}"},
    )
    assert resp.status_code == 200
