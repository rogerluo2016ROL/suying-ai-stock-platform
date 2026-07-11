"""Pure scoring functions for the supply-chain research selection V2 model.

The module intentionally has no database, HTTP, network, or current-time
dependency.  Callers must provide an explicit evidence cutoff and persist the
returned audit detail themselves.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Mapping, Sequence


@dataclass(frozen=True)
class ScoreResult:
    score: float | None
    coverage_ratio: float
    detail: dict[str, Any]


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


def _clamp(value: float) -> float:
    return round(min(100.0, max(0.0, value)), 4)


def _validate_score(name: str, value: float) -> None:
    if value < 0 or value > 100:
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

    evidence_level = str(inputs.get("evidence_level") or "E0")
    evidence_rank = EVIDENCE_RANK.get(evidence_level, 0)
    if evidence_rank == 0:
        return {
            "pool_code": None,
            "eligibility_status": "excluded",
            "veto_reasons": [],
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
