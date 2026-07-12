"""Pure scoring functions for the supply-chain research selection V2 model.

The module intentionally has no database, HTTP, network, or current-time
dependency.  Callers must provide an explicit evidence cutoff and persist the
returned audit detail themselves.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
import math
from typing import TYPE_CHECKING, Any, Literal, Mapping, Sequence
from zoneinfo import ZoneInfo

if TYPE_CHECKING:
    from kronos_factors.engine.industry_chain_evidence_requirements import (
        EvidenceRequirementCatalog,
    )


@dataclass(frozen=True)
class ScoreResult:
    score: float | None
    coverage_ratio: float
    detail: dict[str, Any]


@dataclass(frozen=True)
class PoolGateResult:
    eligible: bool
    max_pool_code: str | None
    level: str
    matched_fact_ids: tuple[str, ...]
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class ApprovedScoreInput:
    evidence_id: str
    score: float
    source_level: Literal["mid", "strong"]
    confidence: float
    source_reliability: float


@dataclass(frozen=True)
class AggregatedEvidenceScore:
    score: float | None
    evidence_ids: tuple[str, ...]


@dataclass(frozen=True)
class ExpectationGapInputs:
    actual_progress_score: float | None
    market_expectation_score: float | None
    evidence_delta_score: float | None
    claim_risk_penalty_score: float | None
    evidence_ids: tuple[str, ...]


class UnresolvedTechnologyRoute(ValueError):
    """A mapping indicates a route but its configured identity is not auditable."""


NODE_WEIGHTS = {
    "demand_certainty": 0.20,
    "value_pool_score": 0.15,
    "bottleneck_score": 0.15,
    "supply_demand_score": 0.15,
    "technology_maturity_score": 0.10,
    "commercialization_score": 0.10,
    "transmission_score": 0.10,
    "evidence_quality_score": 0.05,
}

AUTHENTICITY_WEIGHTS = {
    "product_evidence_score": 0.30,
    "customer_evidence_score": 0.25,
    "order_revenue_evidence_score": 0.25,
    "source_reliability_score": 0.10,
    "freshness_score": 0.10,
}

GROWTH_WEIGHTS = {
    "realized_revenue_growth": 0.30,
    "backlog_growth": 0.25,
    "customer_share_growth": 0.20,
    "delivery_growth": 0.15,
    "growth_sustainability": 0.10,
}

PROFIT_WEIGHTS = {
    "segment_gross_margin": 0.30,
    "incremental_margin": 0.20,
    "price_cost_trend": 0.15,
    "cashflow_collection_quality": 0.15,
    "profit_sustainability": 0.10,
    "capex_efficiency": 0.10,
}

MOAT_WEIGHTS = {
    "technical_performance": 0.20,
    "yield_consistency": 0.20,
    "certification_switch": 0.20,
    "supply_scarcity": 0.15,
    "data_ecosystem": 0.10,
    "scale_cost": 0.10,
    "intellectual_property": 0.05,
}

OPERATING_WEIGHTS = {
    "growth_score": 0.35,
    "profit_score": 0.30,
    "moat_score": 0.35,
}

BENEFIT_WEIGHTS = {
    "node_attractiveness": 0.20,
    "operating_quality_score": 0.20,
    "revenue_exposure_score": 0.20,
    "order_certainty_score": 0.15,
    "profit_elasticity_score": 0.15,
    "delivery_capability_score": 0.10,
}

DEFAULT_POOL_THRESHOLDS = {
    "A": {
        "min_evidence_level": "E4",
        "min_commercial_stage": "C4",
        "min_authenticity": 75.0,
        "min_confidence": 70.0,
        "min_benefit": 60.0,
        "min_operating_coverage": 0.60,
    },
    "B": {
        "min_evidence_level": "E3",
        "min_authenticity": 60.0,
        "requires_next_validation": True,
    },
    "C": {"min_evidence_level": "E2", "requires_product": True},
    "D": {"min_evidence_level": "E1"},
}

EVIDENCE_RANK = {f"E{level}": level for level in range(7)}
POOL_RANK = {None: 0, "D": 1, "C": 2, "B": 3, "A": 4}
_SHANGHAI = ZoneInfo("Asia/Shanghai")


def _finite_in_range(value: object, low: float, high: float) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    numeric = float(value)
    return math.isfinite(numeric) and low <= numeric <= high


def calculate_actual_progress_score(
    research_rank: int,
    commercialization_rank: int,
    evidence_delta_score: float,
) -> float:
    if isinstance(research_rank, bool) or not isinstance(research_rank, int):
        raise ValueError("research_rank must be an integer from 0 to 6")
    if not 0 <= research_rank <= 6:
        raise ValueError("research_rank must be between 0 and 6")
    if isinstance(commercialization_rank, bool) or not isinstance(
        commercialization_rank,
        int,
    ):
        raise ValueError("commercialization_rank must be an integer from 0 to 7")
    if not 0 <= commercialization_rank <= 7:
        raise ValueError("commercialization_rank must be between 0 and 7")
    if not _finite_in_range(evidence_delta_score, 0.0, 100.0):
        raise ValueError("evidence_delta_score must be between 0 and 100")
    research = research_rank / 6 * 100
    commercial = commercialization_rank / 7 * 100
    stage_progress = research * 0.4 + commercial * 0.6
    return round(stage_progress * 0.65 + float(evidence_delta_score) * 0.35, 4)


def calculate_approved_expectation_gap(
    inputs: ExpectationGapInputs,
) -> float | None:
    values = (
        inputs.actual_progress_score,
        inputs.market_expectation_score,
        inputs.evidence_delta_score,
        inputs.claim_risk_penalty_score,
    )
    if not all(_finite_in_range(value, 0.0, 100.0) for value in values):
        return None
    actual, market, delta, claim_risk = (float(value) for value in values)
    raw = actual - market + delta * 0.35 - claim_risk * 0.45
    return round(min(100.0, max(0.0, raw)), 4)


def _approved_score_rows(
    inputs: Sequence[ApprovedScoreInput],
) -> list[ApprovedScoreInput]:
    by_id: dict[str, ApprovedScoreInput | None] = {}
    for item in inputs:
        evidence_id = str(item.evidence_id or "").strip()
        valid = bool(
            evidence_id
            and item.source_level in {"mid", "strong"}
            and _finite_in_range(item.score, 0.0, 100.0)
            and _finite_in_range(item.confidence, 0.0, 1.0)
            and _finite_in_range(item.source_reliability, 0.0, 1.0)
            and float(item.confidence) * float(item.source_reliability) > 0.0
        )
        if not valid:
            continue
        normalized = ApprovedScoreInput(
            evidence_id=evidence_id,
            score=float(item.score),
            source_level=item.source_level,
            confidence=float(item.confidence),
            source_reliability=float(item.source_reliability),
        )
        previous = by_id.get(evidence_id)
        if evidence_id not in by_id:
            by_id[evidence_id] = normalized
        elif previous != normalized:
            # One evidence row cannot carry two incompatible reviewed values.
            by_id[evidence_id] = None
    return [
        item
        for _, item in sorted(by_id.items())
        if item is not None
    ]


def aggregate_catalyst_score(
    inputs: Sequence[ApprovedScoreInput],
) -> AggregatedEvidenceScore:
    valid = _approved_score_rows(inputs)
    if not valid:
        return AggregatedEvidenceScore(None, ())
    weighted = [
        (item, item.source_reliability * item.confidence)
        for item in valid
    ]
    total = sum(weight for _, weight in weighted)
    if not math.isfinite(total) or total <= 0:
        return AggregatedEvidenceScore(None, ())
    score = sum(item.score * weight for item, weight in weighted) / total
    if not math.isfinite(score):
        return AggregatedEvidenceScore(None, ())
    return AggregatedEvidenceScore(
        round(score, 4),
        tuple(item.evidence_id for item in valid),
    )


def aggregate_risk_score(
    inputs: Sequence[ApprovedScoreInput],
) -> AggregatedEvidenceScore:
    valid = _approved_score_rows(inputs)
    if not valid:
        return AggregatedEvidenceScore(None, ())
    worst = max(item.score for item in valid)
    return AggregatedEvidenceScore(
        round(worst, 4),
        tuple(item.evidence_id for item in valid if item.score == worst),
    )


def combine_pool_gates(*gates: PoolGateResult) -> PoolGateResult:
    excluded = [gate for gate in gates if not gate.eligible]
    if excluded:
        return PoolGateResult(
            eligible=False,
            max_pool_code=None,
            level=excluded[0].level,
            matched_fact_ids=(),
            reasons=tuple(
                reason
                for gate in excluded
                for reason in gate.reasons
            ),
        )
    capped = [gate for gate in gates if gate.max_pool_code is not None]
    matched_fact_ids = tuple(
        sorted({fact_id for gate in gates for fact_id in gate.matched_fact_ids})
    )
    reasons = tuple(reason for gate in gates for reason in gate.reasons)
    if not capped:
        return PoolGateResult(
            eligible=True,
            max_pool_code=None,
            level="unrestricted",
            matched_fact_ids=matched_fact_ids,
            reasons=reasons,
        )
    strictest = min(
        capped,
        key=lambda gate: POOL_RANK.get(gate.max_pool_code, 0),
    )
    return PoolGateResult(
        eligible=True,
        max_pool_code=strictest.max_pool_code,
        level=strictest.level,
        matched_fact_ids=matched_fact_ids,
        reasons=reasons,
    )


def _non_empty_text(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()


def _provenance_nodes(value: object) -> Iterable[Mapping[str, Any]]:
    if isinstance(value, Mapping):
        yield value
        nested = value.get("l1_l8_path")
        if nested is not value:
            yield from _provenance_nodes(nested)
        return
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for item in value:
            yield from _provenance_nodes(item)


def _traceable_candidate(mapping: Mapping[str, Any]) -> bool:
    if str(mapping.get("status") or "").casefold() not in {
        "candidate",
        "pending_review",
        "verified",
    }:
        return False
    for node in _provenance_nodes(mapping.get("l1_l8_path")):
        if _non_empty_text(node.get("derived_from_mapping_id")):
            return True
        discovery_fact_ids = node.get("discovery_fact_ids")
        if isinstance(discovery_fact_ids, Sequence) and not isinstance(
            discovery_fact_ids,
            (str, bytes),
        ):
            if any(_non_empty_text(value) for value in discovery_fact_ids):
                return True
    return False


def _fact_identifier(fact: Mapping[str, Any]) -> str | None:
    value = fact.get("fact_id") or fact.get("event_id")
    return str(value) if value else None


def _parsed_datetime(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value
    elif type(value) is date:
        return datetime.combine(value, time.min)
    elif isinstance(value, str) and value.strip():
        normalized = value.strip()
        if normalized.endswith("Z"):
            normalized = normalized[:-1] + "+00:00"
        try:
            return datetime.fromisoformat(normalized)
        except ValueError:
            try:
                return datetime.combine(date.fromisoformat(normalized), time.min)
            except ValueError:
                return None
    return None


def _as_shanghai_moment(
    value: object,
    *,
    naive_timezone: object,
) -> datetime | None:
    parsed = _parsed_datetime(value)
    if parsed is None:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        parsed = parsed.replace(tzinfo=naive_timezone)
    return parsed.astimezone(_SHANGHAI)


def _as_of_date_value(value: object) -> date | None:
    parsed = _as_shanghai_moment(value, naive_timezone=_SHANGHAI)
    return parsed.date() if parsed is not None else None


def _fully_audited_as_of(
    fact: Mapping[str, Any],
    as_of_date: date,
) -> bool:
    if str(fact.get("validation_status") or "").casefold() != "confirmed":
        return False
    if not _non_empty_text(fact.get("reviewer")):
        return False
    if not _non_empty_text(fact.get("review_note")):
        return False
    cutoff = datetime.combine(as_of_date, time.max, tzinfo=_SHANGHAI)
    reviewed_at = _as_shanghai_moment(
        fact.get("reviewed_at"),
        naive_timezone=_SHANGHAI,
    )
    published_at = _as_shanghai_moment(
        fact.get("publish_time"),
        naive_timezone=_SHANGHAI,
    )
    created_at = _as_shanghai_moment(
        fact.get("created_at"),
        naive_timezone=timezone.utc,
    )
    return bool(
        reviewed_at is not None
        and published_at is not None
        and created_at is not None
        and reviewed_at <= cutoff
        and published_at <= cutoff
        and created_at <= cutoff
    )


def _matches_evidence_type(
    fact: Mapping[str, Any],
    rule: Mapping[str, Any],
    source_level_rank: Mapping[str, int],
) -> bool:
    if str(fact.get("fact_type") or "") not in set(rule.get("fact_types") or []):
        return False
    metadata = fact.get("metadata")
    if not isinstance(metadata, Mapping):
        metadata = {}
    if any(metadata.get(str(flag)) is not True for flag in rule.get("metadata_flags") or []):
        return False
    source_level = str(fact.get("source_level") or "").casefold()
    minimum_source = str(rule.get("minimum_source_level") or "").casefold()
    if source_level not in source_level_rank or minimum_source not in source_level_rank:
        return False
    if source_level_rank[source_level] < source_level_rank[minimum_source]:
        return False
    return str(fact.get("fact_nature") or "") in set(
        rule.get("allowed_fact_natures") or []
    )


def derive_evidence_gate(
    mapping: Mapping[str, Any],
    confirmed_facts: Iterable[Mapping[str, Any]],
    requirements: EvidenceRequirementCatalog,
    *,
    as_of_date: date,
) -> PoolGateResult:
    if type(as_of_date) is not date:
        raise ValueError("as_of_date must be a date")
    facts = tuple(confirmed_facts)
    matches: dict[str, set[str]] = defaultdict(set)
    stale_reasons: list[str] = []
    for evidence_type, rule in requirements.evidence_types.items():
        level = str(rule.get("level") or "")
        expiry_policy = rule.get("expiry_policy")
        expiry_days = (
            requirements.freshness_policies.get(str(expiry_policy))
            if expiry_policy
            else None
        )
        for fact in facts:
            if not _fully_audited_as_of(fact, as_of_date):
                continue
            if not _matches_evidence_type(fact, rule, requirements.source_level_rank):
                continue
            published_at = _as_of_date_value(fact.get("publish_time"))
            if (
                expiry_days is not None
                and published_at is not None
                and (as_of_date - published_at).days > expiry_days
            ):
                reason = f"stale_{evidence_type}"
                if reason not in stale_reasons:
                    stale_reasons.append(reason)
                continue
            fact_id = _fact_identifier(fact)
            if fact_id:
                matches[level].add(fact_id)

    matching_levels = [
        level
        for level, fact_ids in matches.items()
        if fact_ids and level in requirements.evidence_levels
    ]
    if matching_levels:
        selected_level = max(
            matching_levels,
            key=lambda level: int(requirements.evidence_levels[level]["rank"]),
        )
        selected_ids = tuple(sorted(matches[selected_level]))
        primary_reason = f"matched_evidence_level:{selected_level}"
    elif _traceable_candidate(mapping):
        selected_level = "E1"
        selected_ids = ()
        primary_reason = "traceable_candidate_mapping"
    else:
        selected_level = "E0"
        selected_ids = ()
        primary_reason = "evidence_e0"

    level_rule = requirements.evidence_levels[selected_level]
    return PoolGateResult(
        eligible=bool(level_rule.get("eligible")),
        max_pool_code=(
            str(level_rule["max_pool"])
            if level_rule.get("max_pool") is not None
            else None
        ),
        level=selected_level,
        matched_fact_ids=selected_ids,
        reasons=(primary_reason, *stale_reasons),
    )


def _route_values_from_provenance(
    mapping: Mapping[str, Any],
) -> tuple[list[str], bool, list[str]]:
    route_values: list[str] = []
    route_key_present = False
    requirement_ids: list[str] = []
    for node in _provenance_nodes(mapping.get("l1_l8_path")):
        if "technology_route_id" in node:
            route_key_present = True
            route = _non_empty_text(node.get("technology_route_id"))
            if route and route not in route_values:
                route_values.append(route)
        requirement_id = _non_empty_text(node.get("requirement_id"))
        if requirement_id and requirement_id not in requirement_ids:
            requirement_ids.append(requirement_id)
    return route_values, route_key_present, requirement_ids


def _unresolved_route(reason: str) -> UnresolvedTechnologyRoute:
    return UnresolvedTechnologyRoute(f"unresolved_route:{reason}")


def resolve_mapping_technology_route(
    mapping: Mapping[str, Any],
    industry_template: Mapping[str, Any] | None,
) -> str | None:
    explicit_route = _non_empty_text(mapping.get("technology_route_id"))
    provenance_routes, provenance_key_present, requirement_ids = (
        _route_values_from_provenance(mapping)
    )
    if len(provenance_routes) > 1 or len(requirement_ids) > 1:
        raise _unresolved_route("conflicting_provenance")

    if industry_template is None:
        if (
            explicit_route
            or provenance_key_present
            or requirement_ids
            or _non_empty_text(mapping.get("chain_id"))
            or _non_empty_text(mapping.get("tag_name"))
        ):
            raise _unresolved_route("template_unavailable")
        return None

    raw_routes = industry_template.get("technology_routes") or []
    routes = [route for route in raw_routes if isinstance(route, Mapping)]
    known_route_ids = {
        route_id
        for route in routes
        if (route_id := _non_empty_text(route.get("route_id")))
    }
    requirements = [
        row
        for row in industry_template.get("evidence_requirements") or []
        if isinstance(row, Mapping)
    ]
    if (
        known_route_ids
        and explicit_route is None
        and not provenance_routes
        and not requirement_ids
        and _non_empty_text(mapping.get("tag_name")) is None
    ):
        raise _unresolved_route("missing_route_context")

    requirement_by_id: Mapping[str, Any] | None = None
    if requirement_ids:
        matching = [
            row
            for row in requirements
            if str(row.get("requirement_id") or "") == requirement_ids[0]
        ]
        if len(matching) != 1:
            raise _unresolved_route("requirement_id_not_unique")
        requirement_by_id = matching[0]

    tag_name = _non_empty_text(mapping.get("tag_name"))
    tag_matches = [
        row
        for row in requirements
        if tag_name is not None and tag_name in (row.get("business_keywords") or [])
    ]
    if len(tag_matches) > 1:
        raise _unresolved_route("tag_requirement_not_unique")
    if (
        tag_name is not None
        and not tag_matches
        and requirement_by_id is None
        and explicit_route is None
        and not provenance_routes
    ):
        raise _unresolved_route("tag_requirement_not_found")
    requirement_by_tag = tag_matches[0] if tag_matches else None
    if (
        requirement_by_id is not None
        and requirement_by_tag is not None
        and requirement_by_id.get("requirement_id")
        != requirement_by_tag.get("requirement_id")
    ):
        raise _unresolved_route("requirement_conflict")
    requirement = requirement_by_id or requirement_by_tag
    expected_route = (
        _non_empty_text(requirement.get("technology_route_id"))
        if requirement is not None
        else None
    )
    provenance_route = provenance_routes[0] if provenance_routes else None
    if (
        requirement is not None
        and expected_route is None
        and (explicit_route is not None or provenance_route is not None)
    ):
        raise _unresolved_route("route_conflict")

    configured_signals = [
        signal
        for signal in (explicit_route, provenance_route, expected_route)
        if signal is not None
    ]
    if len(set(configured_signals)) > 1:
        raise _unresolved_route("route_conflict")
    if provenance_key_present and provenance_route is None and expected_route is not None:
        raise _unresolved_route("empty_provenance_route")
    selected = explicit_route or provenance_route or expected_route
    if selected is None:
        return None
    if selected not in known_route_ids:
        raise _unresolved_route("unknown_route")
    return selected


def _route_blocking_reason(route_id: str, stage: str) -> str:
    if route_id == "dexterous_axial_flux_motor" and stage == "AF0":
        return "axis_flux_af0"
    return f"route_stage_ineligible:{route_id}:{stage}"


def derive_route_gate(
    mapping: Mapping[str, Any],
    confirmed_facts: Sequence[Mapping[str, Any]],
    industry_template: Mapping[str, Any] | None,
    *,
    as_of_date: date,
) -> PoolGateResult:
    if type(as_of_date) is not date:
        raise ValueError("as_of_date must be a date")
    try:
        route_id = resolve_mapping_technology_route(mapping, industry_template)
    except UnresolvedTechnologyRoute as exc:
        return PoolGateResult(
            False,
            None,
            "unresolved_route",
            (),
            ("unresolved_route", str(exc)),
        )
    if route_id is None:
        return PoolGateResult(True, None, "unrestricted", (), ())
    if industry_template is None:
        return PoolGateResult(False, None, "unresolved_route", (), ("unresolved_route",))
    matches = [
        route
        for route in industry_template.get("technology_routes") or []
        if isinstance(route, Mapping) and route.get("route_id") == route_id
    ]
    if len(matches) != 1:
        return PoolGateResult(False, None, "unresolved_route", (), ("unresolved_route",))
    route = matches[0]
    ladder = route.get("authenticity_ladder")
    if not isinstance(ladder, Mapping) or not ladder:
        return PoolGateResult(True, None, "unrestricted", (), ())

    from kronos_factors.engine.supply_chain_evidence_orchestration import (
        derive_route_stage_result,
    )

    audited_facts = tuple(
        fact
        for fact in confirmed_facts
        if _fully_audited_as_of(fact, as_of_date)
    )
    stage_result = derive_route_stage_result(
        audited_facts,
        route,
        as_of_date=as_of_date,
    )
    stage_rule = ladder.get(stage_result.stage)
    if not isinstance(stage_rule, Mapping):
        return PoolGateResult(False, None, "unresolved_route", (), ("unresolved_route",))
    eligible = bool(stage_rule.get("eligible"))
    if eligible:
        reasons = (f"matched_route_stage:{stage_result.stage}", *stage_result.reasons)
    else:
        reasons = (
            _route_blocking_reason(route_id, stage_result.stage),
            *stage_result.reasons,
        )
    return PoolGateResult(
        eligible=eligible,
        max_pool_code=(
            str(stage_rule["max_pool"])
            if eligible and stage_rule.get("max_pool") is not None
            else None
        ),
        level=stage_result.stage,
        matched_fact_ids=stage_result.matched_fact_ids,
        reasons=reasons,
    )


def _clamp(value: float) -> float:
    return round(min(100.0, max(0.0, value)), 4)


def _validate_score(name: str, value: float) -> None:
    if not math.isfinite(value) or value < 0 or value > 100:
        raise ValueError(f"{name} must be between 0 and 100")


def _profile_weights(
    profile: Mapping[str, Any] | None,
    group: str,
    default: Mapping[str, float],
) -> Mapping[str, float]:
    if not profile:
        return default
    return profile.get("weights", {}).get(group, default)


def weighted_available_score(
    values: Mapping[str, float | None],
    weights: Mapping[str, float],
) -> ScoreResult:
    if abs(sum(float(weight) for weight in weights.values()) - 1.0) > 1e-9:
        raise ValueError("weights must sum to 1.0")

    known: dict[str, float] = {}
    for key in weights:
        value = values.get(key)
        if value is None:
            continue
        numeric = float(value)
        _validate_score(key, numeric)
        known[key] = numeric

    if not known:
        return ScoreResult(None, 0.0, {"status": "unknown"})

    known_weight = sum(float(weights[key]) for key in known)
    score = sum(known[key] * float(weights[key]) for key in known) / known_weight
    return ScoreResult(
        score=_clamp(score),
        coverage_ratio=round(known_weight, 4),
        detail={"known_fields": sorted(known)},
    )


def score_node_attractiveness(
    values: Mapping[str, float | None],
    profile: Mapping[str, Any] | None = None,
) -> ScoreResult:
    return weighted_available_score(
        values,
        _profile_weights(profile, "node", NODE_WEIGHTS),
    )


def score_authenticity(
    values: Mapping[str, float | None],
    profile: Mapping[str, Any] | None = None,
) -> ScoreResult:
    return weighted_available_score(
        values,
        _profile_weights(profile, "authenticity", AUTHENTICITY_WEIGHTS),
    )


def _cap_score(
    result: ScoreResult,
    *,
    label: str,
    cap: float | None,
    cap_hits: list[str],
) -> ScoreResult:
    if result.score is None or cap is None or result.score <= cap:
        return result
    _validate_score(label, float(cap))
    cap_hits.append(f"{label}:{cap:g}")
    return ScoreResult(float(cap), result.coverage_ratio, result.detail)


def score_operating_quality(
    growth: Mapping[str, float | None],
    profit: Mapping[str, float | None],
    moat: Mapping[str, float | None],
    profile: Mapping[str, Any] | None = None,
    *,
    growth_cap: float | None = None,
    profit_cap: float | None = None,
    moat_cap: float | None = None,
) -> ScoreResult:
    growth_result = weighted_available_score(
        growth,
        _profile_weights(profile, "growth", GROWTH_WEIGHTS),
    )
    profit_result = weighted_available_score(
        profit,
        _profile_weights(profile, "profit", PROFIT_WEIGHTS),
    )
    moat_result = weighted_available_score(
        moat,
        _profile_weights(profile, "moat", MOAT_WEIGHTS),
    )

    cap_hits: list[str] = []
    growth_result = _cap_score(
        growth_result,
        label="growth_cap",
        cap=growth_cap,
        cap_hits=cap_hits,
    )
    profit_result = _cap_score(
        profit_result,
        label="profit_cap",
        cap=profit_cap,
        cap_hits=cap_hits,
    )
    moat_result = _cap_score(
        moat_result,
        label="moat_cap",
        cap=moat_cap,
        cap_hits=cap_hits,
    )

    operating_weights = _profile_weights(profile, "operating", OPERATING_WEIGHTS)
    total = weighted_available_score(
        {
            "growth_score": growth_result.score,
            "profit_score": profit_result.score,
            "moat_score": moat_result.score,
        },
        operating_weights,
    )
    effective_coverage = sum(
        float(operating_weights[key]) * coverage
        for key, coverage in (
            ("growth_score", growth_result.coverage_ratio),
            ("profit_score", profit_result.coverage_ratio),
            ("moat_score", moat_result.coverage_ratio),
        )
    )
    return ScoreResult(
        score=total.score,
        coverage_ratio=round(effective_coverage, 4),
        detail={
            "growth_score": growth_result.score,
            "growth_coverage": growth_result.coverage_ratio,
            "profit_score": profit_result.score,
            "profit_coverage": profit_result.coverage_ratio,
            "moat_score": moat_result.score,
            "moat_coverage": moat_result.coverage_ratio,
            "cap_hits": cap_hits,
        },
    )


def score_company_benefit(
    values: Mapping[str, float | None],
    *,
    authenticity_score: float | None,
    profile: Mapping[str, Any] | None = None,
) -> ScoreResult:
    raw = weighted_available_score(
        values,
        _profile_weights(profile, "benefit", BENEFIT_WEIGHTS),
    )
    if authenticity_score is None:
        return ScoreResult(
            score=None,
            coverage_ratio=raw.coverage_ratio,
            detail={**raw.detail, "status": "unknown_authenticity"},
        )
    _validate_score("authenticity_score", float(authenticity_score))
    if raw.score is None:
        return raw
    return ScoreResult(
        score=_clamp(raw.score * float(authenticity_score) / 100.0),
        coverage_ratio=raw.coverage_ratio,
        detail={
            **raw.detail,
            "benefit_raw": raw.score,
            "authenticity_score": float(authenticity_score),
        },
    )


def score_selection_opportunity(
    inputs: Mapping[str, float | None],
    profile: Mapping[str, Any] | None = None,
) -> ScoreResult:
    required = (
        "benefit_score",
        "expectation_gap_score",
        "catalyst_score",
        "risk_score",
    )
    known = [key for key in required if inputs.get(key) is not None]
    if len(known) != len(required):
        return ScoreResult(
            score=None,
            coverage_ratio=round(len(known) / len(required), 4),
            detail={
                "status": "insufficient_evidence",
                "known_fields": known,
            },
        )
    values = {key: float(inputs[key]) for key in required}
    for key, value in values.items():
        _validate_score(key, value)
    opportunity_weights = _profile_weights(
        profile,
        "opportunity",
        {
            "benefit_score": 0.55,
            "expectation_gap_score": 0.30,
            "catalyst_score": 0.15,
        },
    )
    if abs(sum(float(weight) for weight in opportunity_weights.values()) - 1.0) > 1e-9:
        raise ValueError("weights must sum to 1.0")
    risk_penalty = float(profile.get("weights", {}).get("risk_penalty", 0.30)) if profile else 0.30
    score = (
        values["benefit_score"] * float(opportunity_weights["benefit_score"])
        + values["expectation_gap_score"]
        * float(opportunity_weights["expectation_gap_score"])
        + values["catalyst_score"] * float(opportunity_weights["catalyst_score"])
        - values["risk_score"] * risk_penalty
    )
    return ScoreResult(_clamp(score), 1.0, {"status": "ready"})


def _stage_rank(stage: str | None) -> int:
    if not stage or not stage.startswith("C"):
        return -1
    try:
        return int(stage[1:])
    except ValueError:
        return -1


def _meets_numeric(value: Any, threshold: float) -> bool:
    return value is not None and float(value) >= threshold


def assign_selection_pool(
    inputs: Mapping[str, Any],
    profile: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    veto_reasons = list(inputs.get("veto_reasons") or [])
    if inputs.get("has_veto") and not veto_reasons:
        veto_reasons = ["unspecified_veto"]
    if veto_reasons:
        return {
            "pool_code": None,
            "eligibility_status": "rejected",
            "veto_reasons": veto_reasons,
        }

    hard_exclusion_reasons = list(inputs.get("hard_exclusion_reasons") or [])
    if hard_exclusion_reasons:
        return {
            "pool_code": None,
            "eligibility_status": "excluded",
            "veto_reasons": [],
            "blocking_gate": str(hard_exclusion_reasons[0]),
            "hard_exclusion_reasons": hard_exclusion_reasons,
        }

    evidence_level = str(inputs.get("evidence_level") or "E0")
    evidence_rank = EVIDENCE_RANK.get(evidence_level, 0)
    if evidence_rank == 0:
        return {
            "pool_code": None,
            "eligibility_status": "excluded",
            "veto_reasons": [],
            "blocking_gate": "evidence_e0",
            "hard_exclusion_reasons": ["evidence_e0"],
        }

    thresholds = (
        profile.get("pool_thresholds", DEFAULT_POOL_THRESHOLDS)
        if profile
        else DEFAULT_POOL_THRESHOLDS
    )
    a = thresholds["A"]
    if (
        evidence_rank >= EVIDENCE_RANK[a["min_evidence_level"]]
        and _stage_rank(inputs.get("commercial_stage"))
        >= _stage_rank(a["min_commercial_stage"])
        and _meets_numeric(inputs.get("authenticity_score"), a["min_authenticity"])
        and _meets_numeric(inputs.get("confidence_score"), a["min_confidence"])
        and _meets_numeric(inputs.get("benefit_score"), a["min_benefit"])
        and _meets_numeric(
            inputs.get("operating_quality_coverage"),
            a["min_operating_coverage"],
        )
        and bool(inputs.get("has_order_or_delivery_evidence"))
    ):
        selected_pool: str | None = "A"
    else:
        b = thresholds["B"]
        b_validation_ok = (
            not b.get("requires_next_validation")
            or bool(inputs.get("has_next_validation"))
        )
        if (
            evidence_rank >= EVIDENCE_RANK[b["min_evidence_level"]]
            and _meets_numeric(inputs.get("authenticity_score"), b["min_authenticity"])
            and bool(inputs.get("has_customer_validation"))
            and b_validation_ok
        ):
            selected_pool = "B"
        else:
            c = thresholds["C"]
            c_product_ok = (
                not c.get("requires_product")
                or bool(inputs.get("has_product_evidence"))
            )
            if (
                evidence_rank >= EVIDENCE_RANK[c["min_evidence_level"]]
                and c_product_ok
            ):
                selected_pool = "C"
            else:
                selected_pool = "D"

    max_pool = inputs.get("max_pool_code")
    if (
        max_pool is not None
        and max_pool in POOL_RANK
        and POOL_RANK[selected_pool] > POOL_RANK[max_pool]
    ):
        selected_pool = max_pool
    return {
        "pool_code": selected_pool,
        "eligibility_status": "watch" if selected_pool == "D" else "eligible",
        "veto_reasons": [],
        "blocking_gate": None,
        "hard_exclusion_reasons": [],
    }


def aggregate_stock_mappings(
    mapping_scores: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in mapping_scores:
        normalized = dict(item)
        code = str(item.get("code") or "").split(".", 1)[0]
        normalized["code"] = code
        grouped[code].append(normalized)

    results: list[dict[str, Any]] = []
    for code, rows in grouped.items():
        ordered = sorted(
            rows,
            key=lambda row: (
                EVIDENCE_RANK.get(str(row.get("evidence_level") or "E0"), 0),
                row.get("benefit_score") is not None,
                float(row.get("benefit_score") or 0.0),
                str(row.get("mapping_id") or ""),
            ),
            reverse=True,
        )
        primary = ordered[0]
        secondary = ordered[1:]
        independent_count = sum(
            1 for row in secondary if bool(row.get("independent_revenue"))
        )
        bonus = min(5.0, independent_count * 2.5)
        primary_score = primary.get("benefit_score")
        results.append(
            {
                **primary,
                "code": code,
                "primary_mapping_id": primary.get("mapping_id"),
                "secondary_mappings": secondary,
                "diversification_bonus": bonus,
                "stock_score": (
                    None
                    if primary_score is None
                    else _clamp(float(primary_score) + bonus)
                ),
            }
        )
    return sorted(
        results,
        key=lambda row: (
            row["stock_score"] is None,
            -float(row["stock_score"] or 0.0),
            str(row["code"]),
        ),
    )
