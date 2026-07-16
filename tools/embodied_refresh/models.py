from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import IntEnum
from typing import Any


class EvidenceGrade(IntEnum):
    """Source authority, ordered from weakest to strongest."""

    D = 1
    C = 2
    B = 3
    A = 4
    S = 5


class CommercializationStage(IntEnum):
    """Ordered commercialization maturity used to detect stage movement."""

    CONCEPT_RELATED = 0
    TECHNOLOGY_RESEARCH = 1
    SAMPLE = 2
    CUSTOMER_VALIDATION = 3
    DESIGN_WIN = 4
    SMALL_BATCH = 5
    MASS_PRODUCTION = 6
    CONFIRMED_ORDER = 7
    REVENUE_RECOGNITION = 8
    SIGNIFICANT_REVENUE_SHARE = 9


@dataclass(frozen=True)
class RawEvidence:
    source_id: str
    source_type: str
    content: str
    event_date: date | None = None
    node_id: str | None = None
    source_url: str | None = None
    publisher_id: str | None = None
    canonical_source_id: str | None = None
    valid_until: date | None = None
    is_valid: bool = True
    valid: bool | None = None


@dataclass(frozen=True)
class NormalizedEvidence:
    source_id: str
    source_type: str
    content: str
    event_date: date | None
    node_id: str | None
    source_url: str | None
    grade: EvidenceGrade
    has_explicit_relation: bool
    stage: CommercializationStage
    fingerprint: str
    publisher_id: str | None = None
    canonical_source_id: str | None = None
    valid_until: date | None = None
    is_valid: bool = True
    fingerprint_version: str = "v1"
    valid: bool = True


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
