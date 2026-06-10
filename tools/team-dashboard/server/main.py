"""
main.py — Team Dashboard FastAPI application.

Endpoints:
  GET /              → 302 redirect to /task/<current-sid>
  GET /task/<sid>    → SPA HTML shell (dev: proxy hint; prod: static file)
  GET /events/<sid>  → SSE stream (initial full snapshot + deltas)

Port binding:
  Default :8765.  If the port is already occupied → print to stderr + sys.exit(1).
  (AC-8 fail-fast)

Usage:
    uvicorn main:app --port 8765
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import socket
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncGenerator

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

# ---------------------------------------------------------------------------
# Logging setup — stderr, with timestamp + level (observability.md)
# ---------------------------------------------------------------------------
logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger("team_dashboard.main")

# ---------------------------------------------------------------------------
# Local imports (run from server/ directory)
# ---------------------------------------------------------------------------
from models import (  # type: ignore[import-not-found]
    ArtifactUpdatePayload,
    InitialPayload,
    SessionMeta,
    SSEEvent,
    TaskUpdatePayload,
    TimelineEvent,
    WorktreeStatusPayload,
)
from session_resolver import resolve_session, SessionInfo  # type: ignore[import-not-found]
from transcript_parser import parse_all_events_from_line, parse_launch_prompt  # type: ignore[import-not-found]
from watcher import (  # type: ignore[import-not-found]
    JournalTailer,
    WatchEvent,
    WatchKind,
    load_all_tasks,
    parse_worktree_list,
    poll_worktrees,
    _collect_docs_dirs,
)

# ---------------------------------------------------------------------------
# Repository root (the git repo this dashboard is observing)
# ---------------------------------------------------------------------------
_REPO_PATH = os.environ.get(
    "DASHBOARD_REPO_PATH",
    str(Path(__file__).resolve().parents[4]),  # tools/team-dashboard/server → repo root
)

# ---------------------------------------------------------------------------
# In-memory session state
# ---------------------------------------------------------------------------

class SessionState:
    """Holds the current snapshot for a single session."""

    def __init__(self, meta: SessionMeta) -> None:
        self.meta = meta
        self.tasks: list[dict[str, Any]] = []
        self.timeline: list[dict[str, Any]] = []   # capped at 100
        self.artifacts: list[dict[str, Any]] = []
        self.worktrees: list[dict[str, Any]] = []
        self._subscribers: list[asyncio.Queue[dict[str, Any]]] = []

    def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        q: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue[dict[str, Any]]) -> None:
        try:
            self._subscribers.remove(q)
        except ValueError:
            pass

    async def broadcast(self, event: dict[str, Any]) -> None:
        for q in list(self._subscribers):
            await q.put(event)

    def initial_snapshot(self) -> dict[str, Any]:
        return {
            "type": "initial",
            "payload": {
                "meta": self.meta.model_dump(),
                "tasks": self.tasks,
                "timeline": self.timeline[-100:],
                "artifacts": self.artifacts,
                "worktree": self.worktrees,
            },
        }


# Global registry: sid → SessionState
_sessions: dict[str, SessionState] = {}
_current_sid: str | None = None
_watcher_task: asyncio.Task | None = None  # type: ignore[type-arg]


# ---------------------------------------------------------------------------
# Startup: resolve session + seed initial state
# ---------------------------------------------------------------------------

def _build_session_meta(session_info: SessionInfo) -> SessionMeta:
    """Read the JSONL and extract SessionMeta from the first user message."""
    meta = SessionMeta(
        session_id=session_info.session_id,
        started_at="",
        worktree_path=_REPO_PATH,
    )
    try:
        with session_info.jsonl_path.open("r", errors="replace") as fh:
            for raw in fh:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    obj = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if obj.get("type") == "user":
                    parsed = parse_launch_prompt(raw)
                    meta.feature_desc = parsed["feature_desc"]
                    meta.teammates = parsed["teammates"]
                    # Grab timestamp if available
                    ts = obj.get("timestamp", "")
                    if ts:
                        meta.started_at = ts
                    break  # only care about the first user message
    except OSError as exc:
        logger.warning("Could not read JSONL for meta: %s", exc)
    return meta


def _seed_timeline_from_jsonl(jsonl_path: Path, limit: int = 100) -> list[dict[str, Any]]:
    """Replay the JSONL to build the initial timeline (last *limit* events)."""
    events: list[dict[str, Any]] = []
    try:
        with jsonl_path.open("r", errors="replace") as fh:
            for raw in fh:
                raw = raw.strip()
                if raw:
                    for evt in parse_all_events_from_line(raw):
                        events.append(evt)
    except OSError:
        pass
    return events[-limit:]


def _seed_artifacts(repo_path: str) -> list[dict[str, Any]]:
    """Collect existing artifact files from docs/ subdirectories."""
    artifacts: list[dict[str, Any]] = []
    for d in _collect_docs_dirs(repo_path):
        if not d.exists():
            continue
        for p in d.rglob("*"):
            if p.is_file():
                try:
                    mtime = p.stat().st_mtime
                except OSError:
                    mtime = 0.0
                artifacts.append({"path": str(p), "mtime": mtime})
    return artifacts


def _init_session(session_info: SessionInfo) -> SessionState:
    """Build a fully-seeded SessionState from a SessionInfo."""
    meta = _build_session_meta(session_info)
    state = SessionState(meta)
    state.tasks = load_all_tasks(Path.home() / ".claude" / "tasks")
    state.timeline = _seed_timeline_from_jsonl(session_info.jsonl_path)
    state.artifacts = _seed_artifacts(_REPO_PATH)
    state.worktrees = poll_worktrees(_REPO_PATH)
    return state


# ---------------------------------------------------------------------------
# Background watcher loop
# ---------------------------------------------------------------------------

async def _watcher_loop() -> None:
    """Resolve the current session and start the filesystem watcher."""
    global _current_sid

    session_info = resolve_session(repo_path=_REPO_PATH)
    if session_info is None:
        logger.info("No session found yet — watching for new sessions…")
        # Keep trying until a session appears
        while True:
            await asyncio.sleep(2)
            session_info = resolve_session(repo_path=_REPO_PATH)
            if session_info:
                break

    sid = session_info.session_id
    _current_sid = sid

    if sid not in _sessions:
        logger.info("Initialising session state for %s", sid)
        _sessions[sid] = _init_session(session_info)

    from watcher import run_watcher  # type: ignore[import-not-found]

    queue: asyncio.Queue[WatchEvent] = asyncio.Queue()
    watcher_coro = run_watcher(
        queue=queue,
        repo_path=_REPO_PATH,
        session_id=sid,
        project_dir=session_info.project_dir,
    )

    watcher_task = asyncio.create_task(watcher_coro)

    try:
        while True:
            watch_event = await queue.get()
            state = _sessions.get(sid)
            if state is None:
                continue

            if watch_event.kind == WatchKind.TASK_CHANGE:
                state.tasks = watch_event.payload.get("tasks", [])
                sse = {"type": "task.update", "payload": {"tasks": state.tasks}}
                await state.broadcast(sse)

            elif watch_event.kind == WatchKind.TRANSCRIPT_APPEND:
                evt = watch_event.payload
                state.timeline.append(evt)
                if len(state.timeline) > 100:
                    state.timeline = state.timeline[-100:]
                sse = {"type": "timeline.append", "payload": evt}
                await state.broadcast(sse)

            elif watch_event.kind == WatchKind.ARTIFACT_CHANGE:
                art = watch_event.payload
                # Update or append
                existing = next(
                    (a for a in state.artifacts if a.get("path") == art.get("path")),
                    None,
                )
                if existing:
                    existing["mtime"] = art["mtime"]
                else:
                    state.artifacts.append(art)
                sse = {"type": "artifact.update", "payload": art}
                await state.broadcast(sse)

            elif watch_event.kind == WatchKind.WORKTREE_POLL:
                state.worktrees = watch_event.payload.get("worktrees", [])
                sse = {"type": "worktree.status", "payload": {"worktrees": state.worktrees}}
                await state.broadcast(sse)

    finally:
        watcher_task.cancel()
        try:
            await watcher_task
        except asyncio.CancelledError:
            pass


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    global _watcher_task
    _watcher_task = asyncio.create_task(_watcher_loop())
    logger.info("Team Dashboard server started. Repo: %s", _REPO_PATH)
    yield
    if _watcher_task:
        _watcher_task.cancel()
        try:
            await _watcher_task
        except asyncio.CancelledError:
            pass
    logger.info("Team Dashboard server stopped.")


app = FastAPI(
    title="Team Dashboard",
    description="Real-time observer for agf-team-start sessions",
    version="0.1.0",
    lifespan=lifespan,
)

# Mount static prod build if it exists
_STATIC_DIR = Path(__file__).parent.parent / "web" / "dist"
if _STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/")
async def root() -> RedirectResponse:
    """Redirect to /task/<current-sid>."""
    sid = _current_sid
    if sid is None:
        # No session yet; return a simple waiting page
        return HTMLResponse(
            "<html><body><h2>Team Dashboard — waiting for first session…</h2>"
            "<p>Start <code>./agf-team-start.sh</code> in another terminal, then refresh.</p>"
            "<script>setTimeout(()=>location.reload(),3000)</script></body></html>",
            status_code=200,
        )
    return RedirectResponse(url=f"/task/{sid}", status_code=302)


@app.get("/task/{sid}")
async def task_view(sid: str) -> HTMLResponse:
    """
    Serve the SPA shell for the given session.

    In production mode (dist/ present) serve index.html from static build.
    In dev mode, return a minimal shell that points the browser at Vite dev server (:5173).
    """
    state = _sessions.get(sid)

    # If the session isn't seeded yet, try to seed it on-demand
    if state is None:
        from session_resolver import list_sessions  # type: ignore[import-not-found]

        all_sessions = list_sessions(repo_path=_REPO_PATH)
        for info in all_sessions:
            if info.session_id == sid:
                _sessions[sid] = _init_session(info)
                state = _sessions[sid]
                break

    if state is None:
        raise HTTPException(status_code=404, detail=f"Session {sid!r} not found")

    # Try to serve prod build first
    static_index = _STATIC_DIR / "index.html"
    if static_index.exists():
        return HTMLResponse(static_index.read_text())

    # Dev mode: minimal shell redirecting to Vite
    vite_port = os.environ.get("VITE_PORT", "5173")
    return HTMLResponse(
        f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <title>Team Dashboard — {sid[:8]}</title>
  <meta http-equiv="refresh" content="0; url=http://localhost:{vite_port}/task/{sid}" />
</head>
<body>
  <p>Redirecting to Vite dev server at
     <a href="http://localhost:{vite_port}/task/{sid}">:{ vite_port }</a>…</p>
</body>
</html>"""
    )


@app.get("/events/{sid}")
async def sse_events(sid: str, request: Request):  # type: ignore[return]
    """
    SSE endpoint.  Immediately sends the full initial snapshot, then streams
    delta events (task.update / timeline.append / artifact.update / worktree.status).

    Uses a plain text/event-stream response so no extra SSE library is required.
    """
    from starlette.responses import StreamingResponse  # type: ignore[import-untyped]

    state = _sessions.get(sid)
    if state is None:
        # Try to seed on-demand
        from session_resolver import list_sessions  # type: ignore[import-not-found]

        all_sessions = list_sessions(repo_path=_REPO_PATH)
        for info in all_sessions:
            if info.session_id == sid:
                _sessions[sid] = _init_session(info)
                state = _sessions[sid]
                break

    if state is None:
        raise HTTPException(status_code=404, detail=f"Session {sid!r} not found")

    subscriber_q = state.subscribe()

    async def event_generator() -> AsyncGenerator[str, None]:
        try:
            # 1. Initial full snapshot
            snapshot = state.initial_snapshot()
            yield _format_sse(snapshot)

            # 2. Deltas — relies on CancelledError for client disconnection
            while True:
                try:
                    delta = await asyncio.wait_for(subscriber_q.get(), timeout=15.0)
                    yield _format_sse(delta)
                except asyncio.TimeoutError:
                    # Heartbeat comment to keep connection alive
                    yield ": heartbeat\n\n"
        except (asyncio.CancelledError, GeneratorExit):
            pass
        finally:
            state.unsubscribe(subscriber_q)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/health")
async def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "current_sid": _current_sid,
        "session_count": len(_sessions),
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _format_sse(data: dict[str, Any]) -> str:
    """Format a dict as an SSE message string."""
    return f"data: {json.dumps(data)}\n\n"


# ---------------------------------------------------------------------------
# Port-occupied check (AC-8 fail-fast)
# ---------------------------------------------------------------------------

def _check_port(host: str, port: int) -> None:
    """
    Check if the given port is already in use.
    If so, print an error to stderr and exit with code 1.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind((host, port))
        except OSError:
            print(
                f"[team-dashboard] ERROR: port {port} in use. "
                f"Stop the existing process or use a different port (--port <N>).",
                file=sys.stderr,
            )
            sys.exit(1)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse
    import uvicorn

    parser = argparse.ArgumentParser(description="Team Dashboard server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--repo", default=None, help="Path to the repository root")
    args = parser.parse_args()

    if args.repo:
        os.environ["DASHBOARD_REPO_PATH"] = args.repo
        _REPO_PATH = args.repo  # type: ignore[assignment]

    _check_port(args.host, args.port)

    uvicorn.run(
        "main:app",
        host=args.host,
        port=args.port,
        reload=False,
        log_level="info",
    )
