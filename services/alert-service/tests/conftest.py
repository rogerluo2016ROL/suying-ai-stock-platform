"""Shared test fixtures — path setup + JWT auth bypass for existing suites.

The sys.path insert also fixes the baseline collection error
(``ModuleNotFoundError: No module named 'app'`` when running
``pytest tests/`` without PYTHONPATH).
"""

import os
import sys

import pytest

SERVICE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if SERVICE_ROOT not in sys.path:
    sys.path.insert(0, SERVICE_ROOT)

from kronos_auth import get_current_user_jwt

_SERVICE_PAYLOAD = {
    "sub": "test-user",
    "name": "test",
    "role": "admin",
    "type": "access",
    "jti": "",
}


@pytest.fixture(autouse=True)
def _override_auth(monkeypatch):
    from app.main import app

    async def _fake_user():
        return _SERVICE_PAYLOAD

    monkeypatch.setitem(app.dependency_overrides, get_current_user_jwt, _fake_user)
