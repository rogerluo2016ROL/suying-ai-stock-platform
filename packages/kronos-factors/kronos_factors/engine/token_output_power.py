"""Pure calculations for the AI Token output power chain.

The module deliberately has no database or network dependency.  Missing values
remain unknown instead of being converted to zero so callers can persist a
coverage ratio and an explicit data-quality limitation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable


EVIDENCE_GRADE_ORDER = {f"E{i}": i for i in range(6)}


@dataclass(frozen=True)
class EvidenceFlags:
    power_or_plan: bool = False
    facility_built: bool = False
    runtime: bool = False
    commercial: bool = False
    recurring_profit: bool = False


def _number(value: Any, name: str, *, non_negative: bool = True) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if non_negative and result < 0:
        raise ValueError(f"{name} must be non-negative")
    return result


def _fraction(value: Any, name: str) -> float:
    result = _number(value, name)
    if result > 1:
        raise ValueError(f"{name} must be between 0 and 1")
    return result


def calculate_billable_tokens(
    available_mw: float | None,
    operating_hours: float | None,
    utilization: float | None,
    tokens_per_mw_hour: float | None,
    cluster_availability: float | None,
) -> float | None:
    """Calculate billable output tokens from the five required factors."""

    values = {
        "available_mw": available_mw,
        "operating_hours": operating_hours,
        "tokens_per_mw_hour": tokens_per_mw_hour,
    }
    for name, value in values.items():
        if value is not None:
            _number(value, name)
    if utilization is not None:
        _fraction(utilization, "utilization")
    if cluster_availability is not None:
        _fraction(cluster_availability, "cluster_availability")
    if any(value is None for value in (available_mw, operating_hours, utilization, tokens_per_mw_hour, cluster_availability)):
        return None
    return round(
        _number(available_mw, "available_mw")
        * _number(operating_hours, "operating_hours")
        * _fraction(utilization, "utilization")
        * _number(tokens_per_mw_hour, "tokens_per_mw_hour")
        * _fraction(cluster_availability, "cluster_availability"),
        6,
    )


def calculate_cost_per_million_tokens(
    electricity_cost: float | None,
    compute_depreciation: float | None,
    facility_and_cooling_cost: float | None,
    network_cost: float | None,
    operation_cost: float | None,
    financing_cost: float | None,
    billable_tokens: float | None,
) -> float | None:
    """Return cost for one million tokens, retaining unknowns as ``None``."""

    if billable_tokens is None:
        return None
    denominator = _number(billable_tokens, "billable_tokens")
    if denominator <= 0:
        return None
    costs = (
        electricity_cost,
        compute_depreciation,
        facility_and_cooling_cost,
        network_cost,
        operation_cost,
        financing_cost,
    )
    if any(value is None for value in costs):
        return None
    total = sum(_number(value, "cost") for value in costs)
    return round(total / denominator * 1_000_000, 6)


def derive_evidence_grade(flags: EvidenceFlags) -> str:
    """Derive the highest evidence grade reached by a mapping."""

    if flags.recurring_profit:
        return "E5"
    if flags.commercial:
        return "E4"
    if flags.runtime:
        return "E3"
    if flags.facility_built:
        return "E2"
    if flags.power_or_plan:
        return "E1"
    return "E0"


def derive_pool_code(
    evidence_grade: str,
    *,
    has_customer_validation: bool = False,
    has_token_revenue: bool = False,
    has_profit: bool = False,
    has_product_or_device: bool = False,
    veto: bool = False,
) -> str:
    """Map evidence and commercial conditions to the formal A/B/C/D pools."""

    grade = str(evidence_grade or "E0").upper()
    level = EVIDENCE_GRADE_ORDER.get(grade, 0)
    if veto:
        return "D"
    if level >= 4 and has_customer_validation and has_token_revenue and has_profit:
        return "A"
    if level >= 3 and (has_customer_validation or has_token_revenue):
        return "B"
    if level >= 2 and (has_product_or_device or not has_customer_validation):
        return "C"
    return "D"


def calculate_opportunity_score(
    pool_code: str,
    industrial_score: float | None,
    authenticity_score: float | None,
    commercialization_score: float | None,
    market_signal_score: float | None,
) -> float | None:
    """Apply the market layer only after industrial evidence admits the pool."""

    if str(pool_code or "").upper() not in {"A", "B", "C"}:
        return None
    scores = (industrial_score, authenticity_score, commercialization_score, market_signal_score)
    if any(value is None for value in scores):
        return None
    normalized = [_number(value, "score") for value in scores]
    if any(value > 100 for value in normalized):
        raise ValueError("score must be between 0 and 100")
    industrial, authenticity, commercialization, market = normalized
    return round(industrial * authenticity * commercialization * market / 1_000_000, 4)


def dedupe_evidence_ids(ids: Iterable[Any]) -> list[str]:
    """Deduplicate evidence IDs while preserving source order."""

    seen: set[str] = set()
    result: list[str] = []
    for raw in ids:
        value = str(raw or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def select_primary_mapping(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Select the strongest mapping without rewarding duplicate evidence."""

    candidates = [row for row in rows if str(row.get("mapping_id") or "")]
    if not candidates:
        return {}
    return max(
        candidates,
        key=lambda row: (
            EVIDENCE_GRADE_ORDER.get(str(row.get("evidence_grade") or "E0").upper(), 0),
            float(row.get("benefit_score") or 0),
        ),
    )
