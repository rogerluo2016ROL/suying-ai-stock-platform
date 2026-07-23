"""Auth guard tests — real 401/403 behavior with dependency_overrides cleared."""

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


def test_modes_requires_auth(client):
    resp = client.get("/api/v1/screener/modes")
    assert resp.status_code == 401


def test_dashboard_summary_requires_auth(client):
    resp = client.get("/api/v1/dashboard/summary")
    assert resp.status_code == 401


def test_refresh_workflow_rejects_wrong_service_auth(client):
    resp = client.post(
        "/api/v1/screener/supply-chain/refresh-workflow",
        headers={"X-Service-Auth": "wrong-secret"},
    )
    assert resp.status_code == 401


def test_refresh_workflow_rejects_plain_user_role(client):
    resp = client.post(
        "/api/v1/screener/supply-chain/refresh-workflow",
        headers={"Authorization": f"Bearer {_mint_token('user')}"},
    )
    assert resp.status_code == 403


def test_modes_accepts_valid_jwt(client):
    resp = client.get(
        "/api/v1/screener/modes",
        headers={"Authorization": f"Bearer {_mint_token('user')}"},
    )
    assert resp.status_code == 200


def test_lark_events_stays_open(client):
    # 飞书事件回调走 LARK_EVENT_VERIFICATION_TOKEN 校验，不吃 JWT。
    resp = client.post("/api/v1/lark/events", json={"type": "url_verification", "challenge": "c1"})
    assert resp.status_code == 200
