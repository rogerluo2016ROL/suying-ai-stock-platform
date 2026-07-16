"""Structural chain audit and evidence-constrained leader ranking."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence


LEADER_WEIGHTS = {
    "business_authenticity": 25,
    "commercialization": 20,
    "technology_moat": 15,
    "revenue_realization": 15,
    "node_importance": 10,
    "evidence_quality": 10,
    "competition_position": 5,
}

WATCH_STATUSES = {"candidate", "weak_evidence", "pending_review"}


@dataclass(frozen=True)
class DuplicateNodeGroup:
    semantic_key: str
    canonical_node_id: str
    duplicate_node_ids: tuple[str, ...]


@dataclass(frozen=True)
class ChainAudit:
    run_id: str
    coverage_by_layer: dict[str, int]
    empty_core_node_ids: list[str]
    duplicate_groups: list[DuplicateNodeGroup]
    orphan_node_ids: list[str]
    mappings_with_missing_nodes: list[str]
    verified_with_unapproved_evidence: list[str]


@dataclass(frozen=True)
class LeaderSnapshot:
    code: str
    company_name: str | None
    node_id: str | None
    score: float
    dimension_scores: dict[str, float | None]
    mapping_status: str
    candidate_label: str
    source: Any


class LeaderRanking(list[LeaderSnapshot]):
    """List-compatible result with explicitly separated publishing pools."""

    def __init__(
        self,
        formal_top3: Sequence[LeaderSnapshot],
        watch_top3: Sequence[LeaderSnapshot],
    ) -> None:
        self.formal_top3 = list(formal_top3)
        self.watch_top3 = list(watch_top3)
        super().__init__([*self.formal_top3, *self.watch_top3])


def audit_chain(connection: Any, run_id: str) -> ChainAudit:
    """Audit one embodied chain snapshot without mutating repository state."""
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT node_id, parent_node_id, layer_level, display_name,
                   metadata, chain_id
              FROM supply_chain_hierarchy_nodes
             WHERE chain_id = 'embodied_intelligence'
                OR chain_id = 'embodied'
             ORDER BY layer_level, node_id
            """
        )
        raw_nodes = cursor.fetchall()
        cursor.execute(
            """
            SELECT m.mapping_id, m.code, m.node_id, m.status,
                   COALESCE(m.evidence_ids, '[]'::jsonb),
                   COALESCE(
                       array_agg(DISTINCT e.review_status)
                           FILTER (WHERE e.event_id IS NOT NULL),
                       ARRAY[]::text[]
                   ) AS evidence_review_statuses,
                   count(DISTINCT e.event_id)::integer AS joined_evidence_count
              FROM business_tag_mapping AS m
              LEFT JOIN business_tag_evidence_events AS e
                ON e.event_id IN (
                    SELECT jsonb_array_elements_text(COALESCE(m.evidence_ids, '[]'::jsonb))
                )
             WHERE m.chain_id IN ('embodied_intelligence', 'embodied')
             GROUP BY m.mapping_id, m.code, m.node_id, m.status, m.evidence_ids
             ORDER BY m.mapping_id
            """
        )
        raw_mappings = cursor.fetchall()

    nodes = [_node_row(row) for row in raw_nodes]
    mappings = [_mapping_row(row) for row in raw_mappings]
    node_ids = {row["node_id"] for row in nodes}
    coverage = Counter(row["layer_level"] for row in nodes)
    coverage_by_layer = {f"L{level}": coverage.get(f"L{level}", 0) for level in range(1, 9)}

    semantic_groups: dict[str, list[str]] = {}
    for node in nodes:
        key = _semantic_key(node["display_name"])
        if key:
            semantic_groups.setdefault(key, []).append(node["node_id"])
    duplicate_groups = []
    for key, ids in sorted(semantic_groups.items()):
        if len(ids) < 2:
            continue
        ordered = sorted(ids, key=_canonical_priority)
        duplicate_groups.append(DuplicateNodeGroup(key, ordered[0], tuple(ordered[1:])))

    return ChainAudit(
        run_id=run_id,
        coverage_by_layer=coverage_by_layer,
        empty_core_node_ids=sorted(
            node["node_id"] for node in nodes if not str(node["display_name"] or "").strip()
        ),
        duplicate_groups=duplicate_groups,
        orphan_node_ids=sorted(
            node["node_id"]
            for node in nodes
            if node["parent_node_id"] and node["parent_node_id"] not in node_ids
        ),
        mappings_with_missing_nodes=sorted(
            row["mapping_id"] for row in mappings if not row["node_id"] or row["node_id"] not in node_ids
        ),
        verified_with_unapproved_evidence=sorted(
            row["mapping_id"]
            for row in mappings
            if row["status"] == "verified"
            and (
                not row["evidence_ids"]
                or not row["review_statuses"]
                or row["joined_evidence_count"] != len(row["evidence_ids"])
                or any(status != "approved" for status in row["review_statuses"])
            )
        ),
    )


def rank_node_leaders(candidates: Iterable[Any]) -> LeaderRanking:
    """Score candidates and return at most three formal and three watch names.

    Missing dimensions are excluded from both numerator and denominator. A
    company is selected once using its best eligible mapping, so extra tags can
    never add points or occupy another rank.
    """
    eligible_statuses = {"verified"} | WATCH_STATUSES
    snapshots = [
        _score_candidate(candidate)
        for candidate in candidates
        if str(_get(candidate, "mapping_status", _get(candidate, "status", "candidate")))
        in eligible_statuses
    ]
    by_company: dict[str, list[LeaderSnapshot]] = {}
    for snapshot in snapshots:
        by_company.setdefault(snapshot.code, []).append(snapshot)

    deduplicated: list[LeaderSnapshot] = []
    for company_rows in by_company.values():
        verified = [row for row in company_rows if row.mapping_status == "verified"]
        eligible = verified or company_rows
        deduplicated.append(max(eligible, key=_leader_sort_value))

    formal = sorted(
        (row for row in deduplicated if row.mapping_status == "verified"),
        key=_leader_sort_key,
    )[:3]
    watch = sorted(
        (row for row in deduplicated if row.mapping_status in WATCH_STATUSES),
        key=_leader_sort_key,
    )[:3]
    return LeaderRanking(formal, watch)


def _score_candidate(candidate: Any) -> LeaderSnapshot:
    values: dict[str, float | None] = {}
    numerator = 0.0
    available_weight = 0
    nested_scores = _get(candidate, "dimension_scores", {}) or {}
    for name, weight in LEADER_WEIGHTS.items():
        raw = _get(candidate, name, nested_scores.get(name))
        if raw is None:
            values[name] = None
            continue
        value = float(raw)
        if not 0 <= value <= 100:
            raise ValueError(f"{name} must be between 0 and 100")
        values[name] = value
        numerator += value * weight
        available_weight += weight
    if available_weight == 0:
        raise ValueError("candidate must have at least one available scoring dimension")
    status = str(_get(candidate, "mapping_status", _get(candidate, "status", "candidate")))
    return LeaderSnapshot(
        code=str(_get(candidate, "code")),
        company_name=_get(candidate, "company_name"),
        node_id=_get(candidate, "node_id"),
        score=round(numerator / available_weight, 4),
        dimension_scores=values,
        mapping_status=status,
        candidate_label="formal" if status == "verified" else status,
        source=candidate,
    )


def _get(candidate: Any, name: str, default: Any = None) -> Any:
    if isinstance(candidate, Mapping):
        return candidate.get(name, default)
    return getattr(candidate, name, default)


def _node_row(row: Any) -> dict[str, Any]:
    if isinstance(row, Mapping):
        return dict(row)
    return dict(zip(("node_id", "parent_node_id", "layer_level", "display_name", "metadata", "chain_id"), row))


def _mapping_row(row: Any) -> dict[str, Any]:
    if isinstance(row, Mapping):
        result = dict(row)
    else:
        result = dict(zip(("mapping_id", "code", "node_id", "status", "evidence_ids", "review_statuses", "joined_evidence_count"), row))
    result["evidence_ids"] = list(result.get("evidence_ids") or [])
    result["review_statuses"] = list(result.get("review_statuses") or [])
    result["joined_evidence_count"] = int(
        result.get("joined_evidence_count", len(result["review_statuses"]))
    )
    return result


def _semantic_key(value: Any) -> str:
    # Treat typography as presentation only: spaces, underscores, slashes,
    # hyphens and other punctuation must not split semantically equal names.
    return "".join(character for character in str(value or "").casefold() if character.isalnum())


def _canonical_priority(node_id: str) -> tuple[int, str]:
    return (0 if node_id.startswith("EI-") else 1, node_id)


def _leader_sort_value(row: LeaderSnapshot) -> tuple[float, str]:
    return (row.score, row.node_id or "")


def _leader_sort_key(row: LeaderSnapshot) -> tuple[float, str, str]:
    return (-row.score, row.code, row.node_id or "")
