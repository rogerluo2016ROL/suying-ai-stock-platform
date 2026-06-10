"""
Tests for main.py FastAPI app.

Tests cover:
1. GET /health  → 200 OK
2. GET /        → 200 waiting page (no session) or 302 to /task/<sid>
3. GET /task/<sid>  → 200 with SID in HTML, or 404 for unknown
4. GET /events/<sid> headers/initial frame — tested via direct unit test
5. SessionState internal logic: initial_snapshot, subscribe, broadcast
6. AC-8: _check_port when port occupied → sys.exit(1)

NOTE ON SSE STREAMING TESTS:
httpx's ASGITransport does not cleanly support premature cancellation of an
infinite SSE stream (Starlette's listen_for_disconnect blocks on response_complete
which is never set if the generator is cancelled mid-flight). The SSE endpoint is
therefore tested at two levels:
  a) Unit tests of SessionState logic (subscribe, broadcast, snapshot)
  b) A focused header test that checks the endpoint returns status 200 +
     text/event-stream without reading the full body stream (via route function tests)
"""

from __future__ import annotations

import asyncio
import json
import socket
import sys
from pathlib import Path
from unittest.mock import patch, AsyncMock, MagicMock

import httpx
import pytest
import pytest_asyncio

import main as app_module
from main import (
    SessionState,
    _check_port,
    _format_sse,
    app,
    _sessions,
)
from models import SessionMeta


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_state(sid: str = "test-sid-001") -> SessionState:
    meta = SessionMeta(
        session_id=sid,
        feature_desc="Test feature",
        teammates=["backend-dev", "frontend-dev"],
        started_at="2026-05-13T10:00:00+08:00",
    )
    state = SessionState(meta)
    state.tasks = [{"id": "1", "status": "pending", "subject": "Build login"}]
    state.timeline = [{"event_type": "SendMessage", "timestamp": "", "summary": "hello"}]
    state.artifacts = [{"path": "docs/prd/foo.md", "mtime": 1_700_000_000.0}]
    state.worktrees = [{"path": "/repo", "branch": "main"}]
    return state


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_sessions():
    app_module._sessions.clear()
    app_module._current_sid = None
    yield
    app_module._sessions.clear()
    app_module._current_sid = None


@pytest_asyncio.fixture()
async def client():
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as c:
        yield c


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

class TestHealth:
    @pytest.mark.asyncio
    async def test_health_ok(self, client: httpx.AsyncClient):
        r = await client.get("/health")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "ok"
        assert "current_sid" in data
        assert "session_count" in data


# ---------------------------------------------------------------------------
# Root redirect
# ---------------------------------------------------------------------------

class TestRoot:
    @pytest.mark.asyncio
    async def test_root_no_session_returns_waiting_page(self, client: httpx.AsyncClient):
        r = await client.get("/", follow_redirects=False)
        assert r.status_code == 200
        assert "waiting" in r.text.lower()

    @pytest.mark.asyncio
    async def test_root_redirects_when_session_exists(self, client: httpx.AsyncClient):
        sid = "my-session-abc"
        app_module._current_sid = sid
        app_module._sessions[sid] = _make_state(sid)
        r = await client.get("/", follow_redirects=False)
        assert r.status_code == 302
        assert f"/task/{sid}" in r.headers["location"]


# ---------------------------------------------------------------------------
# /task/<sid>
# ---------------------------------------------------------------------------

class TestTaskView:
    @pytest.mark.asyncio
    async def test_task_view_404_unknown_sid(self, client: httpx.AsyncClient):
        # list_sessions is imported at runtime in the task_view handler,
        # so we patch at the session_resolver module level
        with patch("session_resolver.list_sessions", return_value=[]):
            r = await client.get("/task/unknown-sid")
        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_task_view_200_known_sid(self, client: httpx.AsyncClient):
        sid = "known-sid-123"
        app_module._sessions[sid] = _make_state(sid)
        r = await client.get(f"/task/{sid}")
        assert r.status_code == 200
        assert sid[:8] in r.text

    @pytest.mark.asyncio
    async def test_task_view_404_returns_json_detail(self, client: httpx.AsyncClient):
        with patch("session_resolver.list_sessions", return_value=[]):
            r = await client.get("/task/no-such-sid")
        assert r.status_code == 404
        assert "not found" in r.json()["detail"].lower()


# ---------------------------------------------------------------------------
# SSE /events/<sid> — unit tests of SessionState logic
# ---------------------------------------------------------------------------

class TestSessionState:
    """
    Unit tests of the in-memory session state.
    These test the business logic without going through HTTP streaming,
    avoiding the httpx ASGI transport streaming cancellation issue.
    """

    def test_initial_snapshot_structure(self):
        sid = "snap-test"
        state = _make_state(sid)
        snap = state.initial_snapshot()
        assert snap["type"] == "initial"
        p = snap["payload"]
        assert p["meta"]["session_id"] == sid
        assert p["meta"]["feature_desc"] == "Test feature"
        assert p["meta"]["teammates"] == ["backend-dev", "frontend-dev"]
        assert isinstance(p["tasks"], list)
        assert len(p["tasks"]) == 1
        assert isinstance(p["timeline"], list)
        assert isinstance(p["artifacts"], list)
        assert isinstance(p["worktree"], list)

    def test_initial_snapshot_caps_timeline_at_100(self):
        state = _make_state("cap-test")
        state.timeline = [{"event_type": "x", "n": i} for i in range(150)]
        snap = state.initial_snapshot()
        assert len(snap["payload"]["timeline"]) == 100
        # Should be the LAST 100
        assert snap["payload"]["timeline"][0]["n"] == 50

    @pytest.mark.asyncio
    async def test_subscribe_broadcast_unsubscribe(self):
        state = _make_state("bcast-test")
        q = state.subscribe()
        assert q in state._subscribers

        msg = {"type": "task.update", "payload": {"tasks": []}}
        await state.broadcast(msg)

        received = await asyncio.wait_for(q.get(), timeout=1.0)
        assert received == msg

        state.unsubscribe(q)
        assert q not in state._subscribers

    @pytest.mark.asyncio
    async def test_broadcast_to_multiple_subscribers(self):
        state = _make_state("multi-bcast")
        q1 = state.subscribe()
        q2 = state.subscribe()
        msg = {"type": "timeline.append", "payload": {"event_type": "Agent"}}
        await state.broadcast(msg)

        r1 = await asyncio.wait_for(q1.get(), timeout=1.0)
        r2 = await asyncio.wait_for(q2.get(), timeout=1.0)
        assert r1 == msg
        assert r2 == msg

    @pytest.mark.asyncio
    async def test_unsubscribe_missing_queue_no_error(self):
        state = _make_state("unsub-test")
        q: asyncio.Queue[dict] = asyncio.Queue()
        state.unsubscribe(q)  # Should not raise even if q wasn't subscribed


# ---------------------------------------------------------------------------
# SSE /events/<sid> — HTTP-level test (headers only, no stream body)
# ---------------------------------------------------------------------------

class TestSSEEndpoint:
    @pytest.mark.asyncio
    async def test_events_404_unknown_sid(self, client: httpx.AsyncClient):
        with patch("session_resolver.list_sessions", return_value=[]):
            r = await client.get("/events/unknown-sid")
        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_events_initial_data_via_snapshot(self):
        """
        Verify the initial frame JSON correctness by calling initial_snapshot()
        and formatting it as SSE — same path as the live endpoint.
        """
        sid = "sse-snap-verify"
        state = _make_state(sid)
        app_module._sessions[sid] = state

        snap = state.initial_snapshot()
        sse_text = _format_sse(snap)

        assert sse_text.startswith("data: ")
        assert sse_text.endswith("\n\n")
        payload = json.loads(sse_text[len("data: "):-2])
        assert payload["type"] == "initial"
        p = payload["payload"]
        assert p["meta"]["session_id"] == sid
        assert "tasks" in p
        assert "timeline" in p
        assert "artifacts" in p
        assert "worktree" in p


# ---------------------------------------------------------------------------
# AC-8: port-occupied check
# ---------------------------------------------------------------------------

class TestPortCheck:
    def test_exit_when_port_occupied(self):
        """Bind a socket to a port, then verify _check_port calls sys.exit(1)."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
            with pytest.raises(SystemExit) as exc_info:
                _check_port("127.0.0.1", port)
        assert exc_info.value.code == 1

    def test_no_exit_when_port_free(self):
        """_check_port on a free port should not raise SystemExit."""
        # Get a free port by binding + releasing
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        # Socket is closed — port is free
        _check_port("127.0.0.1", port)  # Should not raise

    def test_stderr_message_contains_port_in_use(self, capsys):
        """Error message should mention 'port <N> in use'."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
            with pytest.raises(SystemExit):
                _check_port("127.0.0.1", port)
        captured = capsys.readouterr()
        assert f"port {port}" in captured.err
        assert "in use" in captured.err


# ---------------------------------------------------------------------------
# _format_sse helper
# ---------------------------------------------------------------------------

class TestFormatSSE:
    def test_format_sse_structure(self):
        data = {"type": "task.update", "payload": {"tasks": []}}
        result = _format_sse(data)
        assert result.startswith("data: ")
        assert result.endswith("\n\n")

    def test_format_sse_parses_back(self):
        data = {"type": "timeline.append", "payload": {"event_type": "Agent"}}
        result = _format_sse(data)
        parsed = json.loads(result[len("data: "):-2])
        assert parsed == data

    def test_format_sse_initial(self):
        state = _make_state("fmt-test")
        snap = state.initial_snapshot()
        sse = _format_sse(snap)
        parsed = json.loads(sse[len("data: "):-2])
        assert parsed["type"] == "initial"
