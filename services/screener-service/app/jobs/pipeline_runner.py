"""Controlled pipeline run contract; execution is explicit and observable."""
from dataclasses import dataclass
from uuid import uuid4

@dataclass
class PipelineRun:
    run_id: str
    idempotency_key: str
    status: str = "queued"

_RUNS: dict[str, PipelineRun] = {}

def submit_pipeline(request: dict, idempotency_key: str) -> PipelineRun:
    if idempotency_key in _RUNS:
        return _RUNS[idempotency_key]
    run = PipelineRun(uuid4().hex, idempotency_key)
    _RUNS[idempotency_key] = run
    return run
