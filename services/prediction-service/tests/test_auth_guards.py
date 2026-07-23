"""Auth guard tests — real 401/403 behavior on prediction-service routes.

Builds a standalone FastAPI app around the router (same ``app.main`` stub
pattern as test_prediction_contracts.py) so no model load is triggered and
module import order between test files stays harmless.
"""

import sys
import time
from pathlib import Path
from types import SimpleNamespace

import jwt
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.modules.setdefault(
    "app.main",
    SimpleNamespace(
        _model_loaded=False,
        _predictor=None,
        _model_checkpoint_status="not_loaded",
    ),
)

from app import routes
from kronos_auth.config import KRONOS_JWT_SECRET, JWT_ALGORITHM

app = FastAPI()
app.include_router(routes.router)
client = TestClient(app)


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


def test_predict_fast_requires_auth():
    resp = client.post("/api/v1/prediction/600000/fast")
    assert resp.status_code == 401


def test_predict_fast_rejects_wrong_service_auth():
    resp = client.post(
        "/api/v1/prediction/600000/fast",
        headers={"X-Service-Auth": "wrong-secret"},
    )
    assert resp.status_code == 401


def test_predict_fast_rejects_external_analyst_role():
    resp = client.post(
        "/api/v1/prediction/600000/fast",
        headers={"Authorization": f"Bearer {_mint_token('external_analyst')}"},
    )
    assert resp.status_code == 403


def test_status_accepts_valid_jwt():
    resp = client.get(
        "/api/v1/prediction/status",
        headers={"Authorization": f"Bearer {_mint_token('user')}"},
    )
    assert resp.status_code == 200
