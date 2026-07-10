from datetime import date, datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

class ModelRunManifest(BaseModel):
    model_config = ConfigDict(frozen=True)
    schema_version: Literal["1.0"]
    run_id: str
    official: bool
    working_tree_dirty: bool
    strict_timeline: bool
    model_key: str
    model_version: str
    code_commit: str
    parameters_hash: str
    target_trade_date: date
    data_snapshot_id: str
    universe_hash: str
    result_status: str
    cutoff_time: datetime | None = None
    cost_bps: float = 0.0
    artifacts: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def official_gate(self):
        if self.official and (self.working_tree_dirty or not self.strict_timeline):
            raise ValueError("official runs require clean worktree and strict timeline")
        if self.official and (not self.data_snapshot_id or self.data_snapshot_id == "UNAVAILABLE"):
            raise ValueError("official runs require a persisted data snapshot")
        if self.official and self.cutoff_time is None:
            raise ValueError("official runs require an explicit cutoff time")
        return self
