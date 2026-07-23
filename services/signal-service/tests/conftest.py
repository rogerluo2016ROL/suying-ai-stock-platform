"""Shared test fixtures — bypass JWT auth for pre-existing test suites.

Uses FastAPI ``app.dependency_overrides`` (standard pattern) so existing tests
keep working without per-test token plumbing. ``test_auth_guards.py`` clears
the override locally to assert the real 401 behavior.
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
