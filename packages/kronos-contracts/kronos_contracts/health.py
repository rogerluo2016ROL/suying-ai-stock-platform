from datetime import datetime, timezone
from typing import Literal
import time
from pydantic import BaseModel

class ComponentCheck(BaseModel):
    status: Literal["ready", "degraded", "unavailable"]
    latency_ms: int | None = None
    reason: str | None = None

class ServiceHealth(BaseModel):
    service: str
    version: str
    live: bool
    ready: bool
    checks: dict[str, ComponentCheck]
    checked_at: datetime

async def check_postgres() -> ComponentCheck:
    """Best-effort database probe; services without a DB remain live."""
    started = time.perf_counter()
    try:
        from sqlalchemy import text
        from app.database import engine
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return ComponentCheck(status="ready", latency_ms=round((time.perf_counter()-started)*1000))
    except Exception as exc:
        return ComponentCheck(status="unavailable", latency_ms=round((time.perf_counter()-started)*1000), reason=str(exc))

def build_health(service: str, version: str, checks: dict[str, ComponentCheck] | None = None) -> ServiceHealth:
    checks = checks or {}
    return ServiceHealth(service=service, version=version, live=True,
                         ready=all(c.status == "ready" for c in checks.values()),
                         checks=checks, checked_at=datetime.now(timezone.utc))
