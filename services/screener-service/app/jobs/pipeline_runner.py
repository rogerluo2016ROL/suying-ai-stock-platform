"""Controlled pipeline run persistence and idempotency contract."""
from dataclasses import dataclass
import os
from uuid import uuid4

from sqlalchemy import text

@dataclass
class PipelineRun:
    run_id: str
    idempotency_key: str
    status: str = "queued"

_RUNS: dict[str, PipelineRun] = {}

def submit_pipeline(request: dict, idempotency_key: str) -> PipelineRun:
    """Legacy in-process helper retained for callers without a database session."""
    if idempotency_key in _RUNS:
        return _RUNS[idempotency_key]
    run = PipelineRun(uuid4().hex, idempotency_key)
    _RUNS[idempotency_key] = run
    return run


async def submit_persisted_pipeline(db, request: dict, idempotency_key: str) -> PipelineRun:
    """Create or return the durable run associated with an idempotency key."""
    existing = await db.execute(
        text("SELECT run_id, idempotency_key, status FROM task_runs WHERE idempotency_key = :key"),
        {"key": idempotency_key},
    )
    row = existing.mappings().first()
    if row:
        return PipelineRun(str(row["run_id"]), str(row["idempotency_key"]), str(row["status"]))

    run = PipelineRun(uuid4().hex, idempotency_key)
    await db.execute(
        text("""
            INSERT INTO task_runs (run_id, task_type, idempotency_key, status, request_payload, code_commit)
            VALUES (:run_id, 'screener.run', :key, 'running', CAST(:payload AS jsonb), :code_commit)
        """),
        {
            "run_id": run.run_id,
            "key": idempotency_key,
            "payload": __import__("json").dumps(request, ensure_ascii=False, default=str),
            "code_commit": os.environ.get("GIT_COMMIT", "unknown"),
        },
    )
    await db.commit()
    return PipelineRun(run.run_id, idempotency_key, "running")


async def finish_persisted_pipeline(db, run_id: str, *, result: dict | None = None, error: dict | None = None) -> None:
    status = "failed" if error else "succeeded"
    await db.execute(
        text("""
            UPDATE task_runs
            SET status = :status,
                result_payload = CAST(:result AS jsonb),
                error_payload = CAST(:error AS jsonb),
                finished_at = NOW()
            WHERE run_id = :run_id
        """),
        {
            "run_id": run_id,
            "status": status,
            "result": __import__("json").dumps(result, ensure_ascii=False, default=str) if result is not None else None,
            "error": __import__("json").dumps(error, ensure_ascii=False, default=str) if error is not None else None,
        },
    )
    await db.commit()
