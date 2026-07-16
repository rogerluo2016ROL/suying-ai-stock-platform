from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any


@dataclass(frozen=True)
class RefreshRun:
    run_id: str
    run_date: date
    mode: str
    status: str
    summary: dict[str, Any] = field(default_factory=dict)
    started_at: datetime | None = None
    finished_at: datetime | None = None


@dataclass(frozen=True)
class SourceCursor:
    chain_id: str
    source_name: str
    cursor_value: str
    run_id: str
    updated_at: datetime | None = None


@dataclass(frozen=True)
class EvidenceChange:
    change_fingerprint: str
    run_id: str
    node_id: str
    change_type: str
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class LeaderSnapshot:
    snapshot_id: str
    run_id: str
    node_id: str
    rank: int
    score: float
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DeliveryRecord:
    delivery_id: str
    change_batch_id: str
    chat_id: str
    status: str
    message_id: str | None = None
    detail: dict[str, Any] = field(default_factory=dict)
