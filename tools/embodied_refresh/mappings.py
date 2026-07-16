"""Conservative and atomic mapping state transitions."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from hashlib import sha1
import json
from typing import Any, Sequence

from .evidence import can_auto_verify
from .models import NormalizedEvidence


ALLOWED_TRANSITIONS = {
    "candidate": {"candidate", "verified", "weak_evidence", "rejected"},
    "verified": {"verified", "weak_evidence", "rejected"},
    "weak_evidence": {"candidate", "verified", "weak_evidence", "rejected"},
}


@dataclass(frozen=True)
class MappingEvidence:
    code: str
    chain_id: str
    node_id: str
    tag_name: str
    events: Sequence[NormalizedEvidence]
    sources_available: bool = True
    confidence: float = 0.0
    l1_l8_path: Sequence[dict[str, Any]] = ()


@dataclass(frozen=True)
class MappingChange:
    mapping_id: str
    code: str
    node_id: str
    from_status: str | None
    to_status: str
    reason: str


@dataclass(frozen=True)
class MappingConflict:
    code: str
    chain_id: str
    node_ids: tuple[str, ...]
    review_status: str = "pending_review"


@dataclass
class MappingChangeSet:
    created: list[MappingChange] = field(default_factory=list)
    updated: list[MappingChange] = field(default_factory=list)
    unchanged: list[MappingChange] = field(default_factory=list)
    conflicts: list[MappingConflict] = field(default_factory=list)


def apply_mapping_changes(
    connection: Any,
    evidence: Sequence[MappingEvidence],
    *,
    as_of: date | datetime | None = None,
) -> MappingChangeSet:
    """Apply mapping and audit rows in one caller-visible transaction."""
    effective_as_of = as_of or _evidence_as_of(evidence)
    changes = MappingChangeSet()
    grouped: dict[tuple[str, str], list[MappingEvidence]] = {}
    for item in evidence:
        grouped.setdefault((item.chain_id, item.code), []).append(item)

    try:
        with connection.cursor() as cursor:
            for (chain_id, code), items in grouped.items():
                node_ids = tuple(sorted({
                    node_id
                    for item in items
                    for node_id in (item.node_id, *(event.node_id for event in item.events))
                    if node_id
                }))
                if len(node_ids) > 1:
                    changes.conflicts.append(MappingConflict(code, chain_id, node_ids))
                    continue
                item = items[0]
                cursor.execute(
                    """
                    SELECT mapping_id, status, node_id
                      FROM business_tag_mapping
                     WHERE chain_id = %s AND code = %s AND node_id = %s
                     FOR UPDATE
                    """,
                    (chain_id, code, item.node_id),
                )
                existing = cursor.fetchone()
                if existing is None:
                    change = _new_mapping(cursor, item, effective_as_of)
                    changes.created.append(change)
                    _log_transition(cursor, change, item.events, effective_as_of)
                    continue

                mapping_id, raw_status, _node_id = existing[:3]
                old_status = _canonical_status(raw_status)
                if not item.sources_available:
                    changes.unchanged.append(
                        MappingChange(mapping_id, code, item.node_id, old_status, old_status, "source_unavailable")
                    )
                    continue
                target = "verified" if can_auto_verify(item.events, as_of=effective_as_of) else old_status
                if target not in ALLOWED_TRANSITIONS.get(old_status, set()):
                    raise ValueError(f"illegal mapping transition: {old_status} -> {target}")
                change = MappingChange(mapping_id, code, item.node_id, old_status, target, "evidence_refresh")
                if target == old_status:
                    changes.unchanged.append(change)
                    continue
                cursor.execute(
                    "UPDATE business_tag_mapping SET status = %s, updated_at = now() WHERE mapping_id = %s",
                    (target, mapping_id),
                )
                _log_transition(cursor, change, item.events, effective_as_of)
                changes.updated.append(change)
        connection.commit()
        return changes
    except Exception:
        connection.rollback()
        raise


def _new_mapping(cursor: Any, item: MappingEvidence, as_of: date | datetime) -> MappingChange:
    mapping_id = _stable_id("EMB-MAP", item.chain_id, item.code, item.node_id)
    cursor.execute(
        """
        INSERT INTO business_tag_mapping
            (mapping_id, code, node_id, chain_id, tag_name, l1_l8_path,
             confidence, status, evidence_ids, created_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s::jsonb, now(), now())
        """,
        (
            mapping_id,
            item.code,
            item.node_id,
            item.chain_id,
            item.tag_name,
            json.dumps(list(item.l1_l8_path), ensure_ascii=False),
            item.confidence,
            "candidate",
            json.dumps([event.source_id for event in item.events], ensure_ascii=False),
        ),
    )
    return MappingChange(mapping_id, item.code, item.node_id, None, "candidate", "new_evidence")


def _log_transition(cursor: Any, change: MappingChange, events: Sequence[NormalizedEvidence], as_of: date | datetime) -> None:
    cursor.execute(
        """
        INSERT INTO business_tag_stage_transition_log
            (transition_id, mapping_id, old_commercial_stage, new_commercial_stage,
             change_reason, review_status, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, now())
        """,
        (
            _stable_id("EMB-TRANS", change.mapping_id, change.from_status, change.to_status, as_of),
            change.mapping_id,
            change.from_status,
            change.to_status,
            json.dumps({"reason": change.reason, "evidence_ids": [event.source_id for event in events]}, ensure_ascii=False),
            "pending_review",
        ),
    )


def _canonical_status(status: str) -> str:
    return "candidate" if status == "pending_review" else status


def _stable_id(prefix: str, *parts: Any) -> str:
    raw = "|".join("" if part is None else str(part) for part in parts)
    return f"{prefix}-{sha1(raw.encode('utf-8')).hexdigest()[:18]}"


def _evidence_as_of(evidence: Sequence[MappingEvidence]) -> date:
    dates = [
        event.event_date
        for item in evidence
        for event in item.events
        if event.event_date is not None
    ]
    if not dates:
        raise ValueError("as_of is required when evidence has no event_date")
    normalized = [value.date() if isinstance(value, datetime) else value for value in dates]
    return max(normalized)
