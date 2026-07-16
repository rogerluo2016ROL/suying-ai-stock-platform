"""Conservative and atomic mapping state transitions."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from hashlib import sha1
import json
from typing import Any, Sequence

from .evidence import can_auto_verify, normalize_evidence
from .models import NormalizedEvidence, RawEvidence


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
    run_id: str | None = None
    source_name: str | None = None
    source_names: Sequence[str] = ()


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
    existing_node_id: str | None = None
    proposed_node_id: str | None = None
    mapping_id: str | None = None
    conflict_type: str = "node_mismatch"
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
    persist: bool = True,
    commit: bool = True,
) -> MappingChangeSet:
    """Apply mapping and audit rows in one caller-visible transaction."""
    effective_as_of = as_of or _evidence_as_of(evidence)
    changes = MappingChangeSet()
    grouped: dict[tuple[str, str], list[MappingEvidence]] = {}
    for item in evidence:
        grouped.setdefault((item.chain_id, item.code), []).append(item)

    try:
        with connection.cursor() as cursor:
            if persist:
                _persist_evidence_events(cursor, evidence)
            for (chain_id, code), items in grouped.items():
                lock_clause = "FOR UPDATE" if persist else ""
                cursor.execute(
                    f"""
                    SELECT mapping_id, status, node_id, COALESCE(evidence_ids, '[]'::jsonb)
                      FROM business_tag_mapping
                     WHERE chain_id = %s AND code = %s
                     {lock_clause}
                    """,
                    (chain_id, code),
                )
                existing_rows = list(cursor.fetchall())
                proposed_nodes = tuple(sorted({item.node_id for item in items}))
                existing_nodes = tuple(sorted({row[2] for row in existing_rows if row[2]}))
                conflict_pairs = _conflict_pairs(existing_nodes, proposed_nodes)
                if conflict_pairs:
                    for existing_node, proposed_node in conflict_pairs:
                        related = [item for item in items if item.node_id == proposed_node]
                        conflict = MappingConflict(
                            code=code,
                            chain_id=chain_id,
                            node_ids=tuple(sorted(set(existing_nodes + proposed_nodes))),
                            existing_node_id=existing_node,
                            proposed_node_id=proposed_node,
                            mapping_id=next(
                                (row[0] for row in existing_rows if row[2] == existing_node),
                                None,
                            ),
                            conflict_type=(
                                "batch_ambiguity" if existing_node is None else "node_mismatch"
                            ),
                        )
                        if persist:
                            _persist_conflict(cursor, conflict, related, effective_as_of)
                        changes.conflicts.append(conflict)
                    continue

                item = _merge_same_node(items)
                existing = next((row for row in existing_rows if row[2] == item.node_id), None)
                if existing is None:
                    target = "verified" if can_auto_verify(item.events, as_of=effective_as_of) else "candidate"
                    change = _new_mapping(cursor, item, effective_as_of, persist=persist, target=target)
                    changes.created.append(change)
                    if persist:
                        _log_transition(cursor, change, item, effective_as_of)
                    continue

                mapping_id, raw_status, _node_id = existing[:3]
                old_status = _canonical_status(raw_status)
                if not item.sources_available:
                    changes.unchanged.append(
                        MappingChange(mapping_id, code, item.node_id, old_status, old_status, "source_unavailable")
                    )
                    continue
                historical_ids = list(existing[3] or []) if len(existing) > 3 else []
                historical = _load_historical_events(cursor, historical_ids) if persist else []
                accumulated = _merge_events([*historical, *item.events])
                target = "verified" if can_auto_verify(accumulated, as_of=effective_as_of) else old_status
                if target not in ALLOWED_TRANSITIONS.get(old_status, set()):
                    raise ValueError(f"illegal mapping transition: {old_status} -> {target}")
                change = MappingChange(mapping_id, code, item.node_id, old_status, target, "evidence_refresh")
                if persist:
                    cursor.execute(
                        "UPDATE business_tag_mapping SET status = %s, evidence_ids = (SELECT jsonb_agg(DISTINCT value) FROM jsonb_array_elements(COALESCE(evidence_ids,'[]'::jsonb) || %s::jsonb)), updated_at = now() WHERE mapping_id = %s",
                        (target, json.dumps([event.fingerprint for event in item.events]), mapping_id),
                    )
                    cursor.execute(
                        "UPDATE business_tag_evidence_events SET mapping_id=%s WHERE event_id = ANY(%s)",
                        (mapping_id, [event.fingerprint for event in item.events]),
                    )
                    if target != old_status:
                        _log_transition(cursor, change, item, effective_as_of)
                (changes.updated if target != old_status else changes.unchanged).append(change)
        if persist and commit:
            connection.commit()
        return changes
    except Exception:
        if commit:
            connection.rollback()
        raise


def _new_mapping(cursor: Any, item: MappingEvidence, as_of: date | datetime, *, persist: bool, target: str) -> MappingChange:
    mapping_id = _stable_id("EMB-MAP", item.chain_id, item.code, item.node_id)
    if persist:
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
            target,
            json.dumps([event.fingerprint for event in item.events], ensure_ascii=False),
        ),
        )
        cursor.execute(
            "UPDATE business_tag_evidence_events SET mapping_id=%s WHERE event_id = ANY(%s)",
            (mapping_id, [event.fingerprint for event in item.events]),
        )
    return MappingChange(mapping_id, item.code, item.node_id, None, target, "new_evidence")


def _merge_events(events: Sequence[NormalizedEvidence]) -> list[NormalizedEvidence]:
    return list({event.fingerprint: event for event in events}.values())


def _load_historical_events(cursor: Any, event_ids: list[str]) -> list[NormalizedEvidence]:
    if not event_ids:
        return []
    cursor.execute(
        """SELECT event_id, source_id, source_type, excerpt, event_date, node_id, original_url
             FROM business_tag_evidence_events WHERE event_id = ANY(%s)""",
        (event_ids,),
    )
    result = []
    for event_id, source_id, source_type, content, event_date, node_id, url in cursor.fetchall():
        identity = source_id or event_id
        normalized = normalize_evidence(RawEvidence(identity, source_type, content or "", event_date, node_id, url,
                                                     canonical_source_id=identity))
        result.append(NormalizedEvidence(**{**normalized.__dict__, "fingerprint": event_id}))
    return result


def _persist_evidence_events(cursor: Any, evidence: Sequence[MappingEvidence]) -> None:
    seen: set[str] = set()
    for item in evidence:
        for event in item.events:
            if event.fingerprint in seen:
                continue
            seen.add(event.fingerprint)
            cursor.execute(
                """INSERT INTO business_tag_evidence_events
                       (event_id, code, node_id, event_date, source_type, source_id,
                        title, excerpt, original_url, evidence_type, confidence, review_status)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'mapping_evidence',%s,'pending_review')
                   ON CONFLICT (event_id) DO NOTHING""",
                (event.fingerprint, item.code, item.node_id, event.event_date,
                 event.source_type, event.source_id, event.content[:200], event.content,
                 event.source_url, item.confidence),
            )


def _log_transition(cursor: Any, change: MappingChange, item: MappingEvidence, as_of: date | datetime) -> None:
    cursor.execute(
        """
        INSERT INTO embodied_mapping_transitions
            (transition_id, run_id, mapping_id, chain_id, code, node_id,
             from_status, to_status, source_record_ids, evidence_fingerprints,
             source_names, reason,
             review_status, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb,
                %s::jsonb, %s, %s, now())
        """,
        (
            _stable_id("EMB-TRANS", change.mapping_id, change.from_status, change.to_status, as_of),
            item.run_id,
            change.mapping_id,
            item.chain_id,
            change.code,
            change.node_id,
            change.from_status,
            change.to_status,
            json.dumps([event.source_id for event in item.events], ensure_ascii=False),
            json.dumps([event.fingerprint for event in item.events], ensure_ascii=False),
            json.dumps(list(item.source_names) or ([item.source_name] if item.source_name else []), ensure_ascii=False),
            change.reason,
            "pending_review",
        ),
    )


def _persist_conflict(
    cursor: Any,
    conflict: MappingConflict,
    items: Sequence[MappingEvidence],
    as_of: date | datetime,
) -> None:
    events = [event for item in items for event in item.events]
    cursor.execute(
        """
        INSERT INTO embodied_mapping_conflicts
            (conflict_id, run_id, mapping_id, chain_id, code, existing_node_id,
             proposed_node_id, conflict_type, status, source_record_ids,
             evidence_fingerprints, source_names, proposed_node_ids, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb,
                %s::jsonb, %s::jsonb, %s::jsonb, now())
        """,
        (
            _stable_id("EMB-CONFLICT", conflict.chain_id, conflict.code, conflict.existing_node_id, conflict.proposed_node_id, as_of),
            next((item.run_id for item in items if item.run_id), None),
            conflict.mapping_id,
            conflict.chain_id,
            conflict.code,
            conflict.existing_node_id,
            conflict.proposed_node_id,
            conflict.conflict_type,
            "pending_review",
            json.dumps([event.source_id for event in events], ensure_ascii=False),
            json.dumps([event.fingerprint for event in events], ensure_ascii=False),
            json.dumps(sorted({name for item in items for name in (*item.source_names, *((item.source_name,) if item.source_name else ())) }), ensure_ascii=False),
            json.dumps(list(conflict.node_ids), ensure_ascii=False),
        ),
    )


def _conflict_pairs(
    existing_nodes: tuple[str, ...], proposed_nodes: tuple[str, ...]
) -> list[tuple[str | None, str]]:
    if existing_nodes:
        return [
            (existing, proposed)
            for existing in existing_nodes
            for proposed in proposed_nodes
            if existing != proposed
        ]
    if len(proposed_nodes) > 1:
        return [(None, proposed_nodes[0])]
    return []


def _merge_same_node(items: Sequence[MappingEvidence]) -> MappingEvidence:
    first = items[0]
    events: list[NormalizedEvidence] = []
    seen: set[str] = set()
    for item in items:
        if item.node_id != first.node_id:
            raise ValueError("cannot merge evidence for different nodes")
        for event in item.events if item.sources_available else ():
            if event.fingerprint not in seen:
                seen.add(event.fingerprint)
                events.append(event)
    return MappingEvidence(
        first.code,
        first.chain_id,
        first.node_id,
        first.tag_name,
        events,
        any(item.sources_available for item in items),
        max(item.confidence for item in items),
        next((item.l1_l8_path for item in items if item.l1_l8_path), ()),
        next((item.run_id for item in items if item.run_id), None),
        next((item.source_name for item in items if item.source_name), None),
        tuple(sorted({name for item in items for name in (*item.source_names, *((item.source_name,) if item.source_name else ())) })),
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
