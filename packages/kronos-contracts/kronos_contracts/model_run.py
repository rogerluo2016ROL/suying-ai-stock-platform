"""Immutable contract for reproducible model runs."""
from __future__ import annotations

from datetime import date, datetime
from typing import Literal
from pydantic import BaseModel, Field, model_validator


class ModelRunManifest(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    run_id: str
    official: bool = False
    working_tree_dirty: bool
    strict_timeline: bool
    model_key: str
    model_version: str
    code_commit: str
    parameters_hash: str
    target_trade_date: date
    cutoff_time: datetime | None = None
    data_snapshot_id: str
    universe_hash: str
    transaction_cost_bps: float = 0.0
    artifacts: tuple[str, ...] = Field(default_factory=tuple)
    result_status: Literal["success", "blocked", "failed", "unsupported", "insufficient_data"]

    @model_validator(mode="after")
    def require_official_guards(self):
        if self.official and (self.working_tree_dirty or not self.strict_timeline):
            raise ValueError("official runs require a clean worktree and strict timeline")
        return self
