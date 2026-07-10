"""Controlled in-process pipeline jobs with idempotency and explicit state."""
from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import datetime, timezone
from typing import Awaitable, Callable

_runs: dict[str, dict] = {}
_keys: dict[str, str] = {}

def submit_pipeline(request: dict, idempotency_key: str, worker: Callable[[dict], Awaitable[dict]]) -> str:
    if idempotency_key in _keys:
        return _keys[idempotency_key]
    digest = hashlib.sha256((idempotency_key + json.dumps(request, sort_keys=True)).encode()).hexdigest()[:24]
    run_id = f"pipe-{digest}"
    _keys[idempotency_key] = run_id
    _runs[run_id] = {"run_id": run_id, "status": "queued", "request": request, "created_at": datetime.now(timezone.utc).isoformat()}
    async def execute():
        _runs[run_id]["status"] = "running"
        try:
            _runs[run_id]["result"] = await worker(request)
            _runs[run_id]["status"] = "completed"
        except Exception as exc:
            _runs[run_id]["status"] = "failed"
            _runs[run_id]["error"] = str(exc)
        _runs[run_id]["finished_at"] = datetime.now(timezone.utc).isoformat()
    asyncio.create_task(execute())
    return run_id

def get_pipeline_run(run_id: str) -> dict | None:
    return _runs.get(run_id)
