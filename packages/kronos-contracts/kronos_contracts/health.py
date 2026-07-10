from datetime import datetime, timezone
from typing import Literal
from pydantic import BaseModel, Field

class ComponentCheck(BaseModel):
    status: Literal["ready", "degraded", "unavailable"]
    latency_ms: int | None = None
    reason: str | None = None

class ServiceHealth(BaseModel):
    service: str
    version: str = "unknown"
    live: bool = True
    ready: bool
    checks: dict[str, ComponentCheck] = Field(default_factory=dict)
    checked_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
