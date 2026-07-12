#!/usr/bin/env python3
"""As-of scoring orchestration for supply-chain research selection V2."""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict
from datetime import date, datetime, time, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping
from zoneinfo import ZoneInfo

import psycopg2
from psycopg2.extras import RealDictCursor


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = PROJECT_ROOT / "packages" / "kronos-factors"
SCREENER_SERVICE_ROOT = PROJECT_ROOT / "services" / "screener-service"
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))
if str(SCREENER_SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SCREENER_SERVICE_ROOT))

from kronos_factors.engine.industry_chain_templates import (  # noqa: E402
    get_industry_template,
    load_selection_v2_profile,
    validate_selection_v2_profile,
)
from kronos_factors.engine.industry_chain_evidence_requirements import (  # noqa: E402
    EvidenceRequirementCatalog,
    load_evidence_requirements,
)
from kronos_factors.scorer.supply_chain_selection_v2 import (  # noqa: E402
    PoolGateResult,
    ScoreResult,
    UnresolvedTechnologyRoute,
    assign_selection_pool,
    combine_pool_gates,
    derive_evidence_gate,
    derive_route_gate,
    resolve_mapping_technology_route,
    score_authenticity,
    score_company_benefit,
    score_operating_quality,
    score_selection_opportunity,
)
from app.domains.supply_chain.selection_repository import (  # noqa: E402
    MissingSelectionTables,
    SelectionRepository,
)


SHANGHAI = ZoneInfo("Asia/Shanghai")
MODEL_VERSION = "v2.0"
DEFAULT_DSN = os.environ.get(
    "KRONOS_PG_URL",
    "postgresql://kronos:kronos@localhost:6432/kronos",
)


def _cutoff_utc(trade_date: date) -> datetime:
    return datetime.combine(trade_date, time.max, tzinfo=SHANGHAI).astimezone(
        timezone.utc
    )


def _publish_time_utc(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        value = datetime.combine(value, time.min)
    if not isinstance(value, datetime):
        raise TypeError("publish_time must be a date or datetime")
    if value.tzinfo is None:
        value = value.replace(tzinfo=SHANGHAI)
    return value.astimezone(timezone.utc)


def _reviewed_time_utc(value: Any) -> datetime | None:
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        return None
    return value.astimezone(timezone.utc)


def _created_time_utc(value: Any) -> datetime | None:
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _has_review_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _evidence_id(item: Mapping[str, Any]) -> str | None:
    value = item.get("fact_id") or item.get("event_id")
    return str(value) if value else None


def _confirmed_evidence(
    evidence: Iterable[Mapping[str, Any]],
    *,
    cutoff: datetime,
) -> tuple[list[dict[str, Any]], list[str]]:
    confirmed: list[dict[str, Any]] = []
    limitations: list[str] = []
    for item in evidence:
        row = dict(item)
        published = _publish_time_utc(row.get("publish_time"))
        event_id = _evidence_id(row) or "unknown"
        if published is None:
            limitations.append(f"evidence_missing_publish_time:{event_id}")
            continue
        if published > cutoff:
            continue
        if row.get("validation_status") != "confirmed":
            continue
        if not _has_review_text(row.get("reviewer")):
            limitations.append(f"evidence_incomplete_review:{event_id}")
            continue
        if not _has_review_text(row.get("review_note")):
            limitations.append(f"evidence_incomplete_review:{event_id}")
            continue
        reviewed_at = _reviewed_time_utc(row.get("reviewed_at"))
        if reviewed_at is None:
            limitations.append(f"evidence_invalid_reviewed_at:{event_id}")
            continue
        if reviewed_at > cutoff:
            limitations.append(f"evidence_reviewed_after_cutoff:{event_id}")
            continue
        created_at = _created_time_utc(row.get("created_at"))
        if created_at is None:
            limitations.append(f"evidence_invalid_created_at:{event_id}")
            continue
        if created_at > cutoff:
            limitations.append(f"evidence_created_after_cutoff:{event_id}")
            continue
        row["publish_time"] = published
        row["reviewed_at"] = reviewed_at
        row["created_at"] = created_at
        confirmed.append(row)
    return confirmed, limitations


def prepare_mapping_for_score(
    mapping: Mapping[str, Any],
    *,
    trade_date: date,
) -> dict[str, Any]:
    """Fail closed for repository commercial stages without their audit chain."""

    prepared = dict(mapping)
    limitations = list(prepared.get("data_limitations") or [])
    prepared["data_limitations"] = limitations
    if prepared.get("commercial_stage") is None:
        return prepared

    cutoff = _cutoff_utc(trade_date)
    reviewed_at = _reviewed_time_utc(prepared.get("source_event_reviewed_at"))
    stage_created_at = _created_time_utc(prepared.get("stage_created_at"))
    source_event_created_at = _created_time_utc(
        prepared.get("source_event_created_at")
    )
    try:
        event_time = _publish_time_utc(prepared.get("source_event_date"))
    except TypeError:
        event_time = None
    audited = bool(
        str(prepared.get("stage_review_status") or "").casefold() == "approved"
        and str(prepared.get("source_event_review_status") or "").casefold()
        == "approved"
        and _has_review_text(prepared.get("source_event_reviewer"))
        and _has_review_text(prepared.get("source_event_review_note"))
        and reviewed_at is not None
        and reviewed_at <= cutoff
        and event_time is not None
        and event_time <= cutoff
        and stage_created_at is not None
        and stage_created_at <= cutoff
        and source_event_created_at is not None
        and source_event_created_at <= cutoff
    )
    if not audited:
        prepared["commercial_stage"] = None
        if "unaudited_commercial_stage" not in limitations:
            limitations.append("unaudited_commercial_stage")
    return prepared


def _fact_types(evidence: Iterable[Mapping[str, Any]]) -> set[str]:
    return {str(item.get("fact_type") or "") for item in evidence}


def _freshness_score(confirmed: list[dict[str, Any]], cutoff: datetime) -> float | None:
    if not confirmed:
        return None
    latest = max(item["publish_time"] for item in confirmed)
    days = max(0, (cutoff.date() - latest.date()).days)
    if days <= 30:
        return 100.0
    if days <= 90:
        return 85.0
    if days <= 180:
        return 65.0
    if days <= 365:
        return 40.0
    return 20.0


def _source_reliability_score(
    confirmed: list[dict[str, Any]],
) -> float | None:
    if not confirmed:
        return None
    values = {"strong": 90.0, "mid": 65.0, "weak": 35.0}
    scored = [
        values[str(item.get("source_level") or "weak")]
        for item in confirmed
        if str(item.get("source_level") or "weak") in values
    ]
    return max(scored) if scored else None


def _authenticity_inputs(
    confirmed: list[dict[str, Any]],
    evidence_level: str,
    cutoff: datetime,
) -> dict[str, float | None]:
    rank = int(evidence_level[1:])
    return {
        "product_evidence_score": 80.0 if rank >= 2 else None,
        "customer_evidence_score": 85.0 if rank >= 3 else None,
        "order_revenue_evidence_score": 90.0 if rank >= 4 else None,
        "source_reliability_score": _source_reliability_score(confirmed),
        "freshness_score": _freshness_score(confirmed, cutoff),
    }


def _structured_score(
    evidence: Iterable[Mapping[str, Any]],
    key: str,
) -> float | None:
    values: list[float] = []
    for item in evidence:
        metadata = item.get("metadata") or {}
        value = metadata.get(key)
        if value is None:
            continue
        numeric = float(value)
        if not 0 <= numeric <= 100:
            raise ValueError(f"{key} must be between 0 and 100")
        values.append(numeric)
    return max(values) if values else None


def _operating_quality(
    confirmed: list[dict[str, Any]],
    profile: dict[str, Any],
) -> ScoreResult:
    fact_types = _fact_types(confirmed)
    growth = {
        key: _structured_score(confirmed, key)
        for key in profile["weights"]["growth"]
    }
    profit = {
        key: _structured_score(confirmed, key)
        for key in profile["weights"]["profit"]
    }
    moat = {
        key: _structured_score(confirmed, key)
        for key in profile["weights"]["moat"]
    }
    growth_cap: float | None = None
    if "capacity_mass_production" in fact_types and "order_award" not in fact_types:
        growth_cap = 55.0
    elif "prototype_delivery" in fact_types and "order_award" not in fact_types:
        growth_cap = 45.0
    return score_operating_quality(
        growth,
        profit,
        moat,
        profile,
        growth_cap=growth_cap,
    )


def _revenue_exposure_score(mapping: Mapping[str, Any]) -> float | None:
    ratio = mapping.get("revenue_ratio")
    if ratio is None:
        return None
    ratio_score = min(100.0, max(0.0, float(ratio)))
    confidence = min(1.0, max(0.0, float(mapping.get("confidence") or 0.0)))
    return round(ratio_score * confidence, 4)


def _order_certainty_score(evidence_level: str) -> float | None:
    return {
        "E0": None,
        "E1": None,
        "E2": 30.0,
        "E3": 60.0,
        "E4": 85.0,
        "E5": 90.0,
        "E6": 95.0,
    }[evidence_level]


def _delivery_capability_score(
    confirmed: list[dict[str, Any]],
) -> float | None:
    return 70.0 if "capacity_mass_production" in _fact_types(confirmed) else None


def _confidence_score(
    authenticity: ScoreResult,
    evidence_level: str,
) -> float | None:
    if authenticity.score is None:
        return None
    level_coverage = int(evidence_level[1:]) / 6.0
    return round(
        authenticity.score * 0.6
        + authenticity.coverage_ratio * 100 * 0.2
        + level_coverage * 100 * 0.2,
        4,
    )


def _selection_inputs(
    mapping: Mapping[str, Any],
    confirmed: list[dict[str, Any]],
    benefit: ScoreResult,
) -> dict[str, float | None]:
    expectation_gap = mapping.get("expectation_gap_score")
    catalyst = mapping.get("catalyst_score")
    risk = mapping.get("risk_score")
    return {
        "benefit_score": benefit.score,
        "expectation_gap_score": (
            float(expectation_gap) if expectation_gap is not None else None
        ),
        "catalyst_score": float(catalyst) if catalyst is not None else None,
        "risk_score": float(risk) if risk is not None else None,
    }


def _veto_reasons(confirmed: list[dict[str, Any]]) -> list[str]:
    reasons: set[str] = set()
    for item in confirmed:
        metadata = item.get("metadata") or {}
        reason = metadata.get("veto_reason")
        explicit = metadata.get("is_veto") is True or (
            isinstance(reason, str) and bool(reason.strip())
        )
        if explicit:
            reasons.add(str(reason).strip() if reason else "explicit_veto")
    return sorted(reasons)


def score_mapping(
    mapping: Mapping[str, Any],
    evidence: list[dict[str, Any]],
    *,
    trade_date: date,
    node_score: float | None,
    profile: dict[str, Any] | None = None,
    evidence_requirements: EvidenceRequirementCatalog | None = None,
    industry_template: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    configured_profile = profile or load_selection_v2_profile()
    validate_selection_v2_profile(configured_profile)
    cutoff = _cutoff_utc(trade_date)
    confirmed, evidence_limitations = _confirmed_evidence(evidence, cutoff=cutoff)
    limitations = list(mapping.get("data_limitations") or [])
    for limitation in evidence_limitations:
        if limitation not in limitations:
            limitations.append(limitation)

    catalog = evidence_requirements or load_evidence_requirements()
    template = industry_template
    chain_id = str(mapping.get("chain_id") or "")
    if template is None and chain_id:
        try:
            template = get_industry_template(chain_id)
        except ValueError:
            template = None
    evidence_gate = derive_evidence_gate(
        mapping,
        confirmed,
        catalog,
        as_of_date=trade_date,
    )
    try:
        resolved_route_id = resolve_mapping_technology_route(mapping, template)
    except UnresolvedTechnologyRoute:
        resolved_route_id = None
    route_gate = derive_route_gate(
        mapping,
        confirmed,
        template,
        as_of_date=trade_date,
    )
    combined_gate = combine_pool_gates(evidence_gate, route_gate)
    evidence_level = evidence_gate.level
    authenticity_inputs = _authenticity_inputs(
        confirmed,
        evidence_level,
        cutoff,
    )
    authenticity = score_authenticity(
        authenticity_inputs,
        configured_profile,
    )
    operating = _operating_quality(confirmed, configured_profile)
    benefit_inputs = {
        "node_attractiveness": node_score,
        "operating_quality_score": operating.score,
        "revenue_exposure_score": _revenue_exposure_score(mapping),
        "order_certainty_score": _order_certainty_score(evidence_level),
        "profit_elasticity_score": _structured_score(
            confirmed,
            "profit_elasticity_score",
        ),
        "delivery_capability_score": _delivery_capability_score(confirmed),
    }
    benefit = score_company_benefit(
        benefit_inputs,
        authenticity_score=authenticity.score,
        profile=configured_profile,
    )
    selection_inputs = _selection_inputs(mapping, confirmed, benefit)
    opportunity = score_selection_opportunity(
        selection_inputs,
        configured_profile,
    )
    veto_reasons = _veto_reasons(confirmed)
    confidence = _confidence_score(authenticity, evidence_level)
    rank = int(catalog.evidence_levels[evidence_level]["rank"])
    pool_inputs = {
        "evidence_level": evidence_level,
        "commercial_stage": mapping.get("commercial_stage"),
        "authenticity_score": authenticity.score,
        "confidence_score": confidence,
        "benefit_score": benefit.score,
        "operating_quality_coverage": operating.coverage_ratio,
        "has_veto": bool(veto_reasons),
        "veto_reasons": veto_reasons,
        "has_order_or_delivery_evidence": rank
        >= int(catalog.evidence_levels["E4"]["rank"]),
        "has_product_evidence": rank
        >= int(catalog.evidence_levels["E2"]["rank"]),
        "has_customer_validation": rank
        >= int(catalog.evidence_levels["E3"]["rank"]),
        "has_next_validation": bool(mapping.get("next_validation_event"))
        and mapping.get("next_validation_date") is not None,
        "max_pool_code": combined_gate.max_pool_code,
        "hard_exclusion_reasons": (
            list(combined_gate.reasons) if not combined_gate.eligible else []
        ),
    }
    pool = assign_selection_pool(
        pool_inputs,
        configured_profile,
    )
    evidence_ids = sorted(
        {
            evidence_id
            for item in confirmed
            if (evidence_id := _evidence_id(item)) is not None
        }
    )
    return {
        "mapping_id": mapping["mapping_id"],
        "code": mapping["code"],
        "trade_date": trade_date,
        "model_version": MODEL_VERSION,
        "authenticity": {
            **asdict(authenticity),
            "detail": {
                **authenticity.detail,
                **authenticity_inputs,
                "evidence_gate": asdict(evidence_gate),
            },
            "evidence_level": evidence_level,
            "max_pool_code": evidence_gate.max_pool_code,
        },
        "operating_quality": asdict(operating),
        "benefit": {
            **asdict(benefit),
            "detail": {**benefit.detail, **benefit_inputs},
        },
        "selection": {
            **asdict(opportunity),
            "detail": {
                **opportunity.detail,
                **selection_inputs,
                "resolved_technology_route_id": resolved_route_id,
                "pool_gates": {
                    "evidence": asdict(evidence_gate),
                    "route": asdict(route_gate),
                    "combined": asdict(combined_gate),
                },
            },
            "opportunity_score": opportunity.score,
            "confidence_score": confidence,
            **pool,
        },
        "evidence_ids": evidence_ids,
        "data_limitations": limitations,
        "next_validation_event": mapping.get("next_validation_event"),
        "next_validation_date": mapping.get("next_validation_date"),
    }


_SELECTION_CONTEXT_MAPPING_KEYS = (
    "actual_progress_score",
    "market_expectation_score",
    "evidence_delta_score",
    "claim_risk_penalty_score",
    "expectation_gap_score",
    "catalyst_score",
    "risk_score",
    "adjusted_price_reaction",
)


def _apply_selection_context(
    prepared_mapping: Mapping[str, Any],
    context: Mapping[str, Any],
) -> dict[str, Any]:
    merged = dict(prepared_mapping)
    for key in _SELECTION_CONTEXT_MAPPING_KEYS:
        if key in context:
            merged[key] = context[key]
    return merged


def _complete_context_bundle(
    bundle: dict[str, Any],
    *,
    context: Mapping[str, Any],
) -> dict[str, Any]:
    context_ids = sorted(
        {
            item.strip()
            for item in (context.get("selection_context_evidence_ids") or [])
            if isinstance(item, str) and item.strip()
        }
    )
    bundle["evidence_ids"] = sorted(
        {
            item.strip()
            for item in [*(bundle.get("evidence_ids") or []), *context_ids]
            if isinstance(item, str) and item.strip()
        }
    )
    limitations = sorted(
        {
            item.strip()
            for item in [
                *(bundle.get("data_limitations") or []),
                *(context.get("selection_context_limitations") or []),
            ]
            if isinstance(item, str) and item.strip()
        }
    )
    bundle["data_limitations"] = limitations
    selection = bundle.setdefault("selection", {})
    detail = selection.setdefault("detail", {})
    detail["selection_context"] = {
        key: context.get(key) for key in _SELECTION_CONTEXT_MAPPING_KEYS
    }
    detail["selection_context_evidence_ids"] = context_ids
    detail["pool_gate"] = (
        (detail.get("pool_gates") or {}).get("combined")
        if isinstance(detail.get("pool_gates"), Mapping)
        else None
    )
    detail["blocking_gate"] = selection.get("blocking_gate")
    detail["data_limitations"] = limitations
    detail["next_validation"] = {
        "event": bundle.get("next_validation_event"),
        "date": bundle.get("next_validation_date"),
        "actions": [],
    }
    return bundle


def run_batch_score_in_connection(
    connection,
    *,
    chain_id: str,
    trade_date: date,
    model_version: str,
    dry_run: bool,
    mapping_ids: list[str] | None,
    repository: SelectionRepository,
) -> dict[str, Any]:
    bundles: list[dict[str, Any]] = []
    transitions = 0
    with connection.cursor(cursor_factory=RealDictCursor) as cur:
        missing = repository.preflight(cur)
        if missing:
            raise MissingSelectionTables(missing)
        mappings = repository.fetch_mappings(
            cur,
            chain_id=chain_id,
            mapping_ids=mapping_ids,
            trade_date=trade_date,
        )
        cutoff = _cutoff_utc(trade_date)
        for mapping in mappings:
            prepared_mapping = prepare_mapping_for_score(
                mapping,
                trade_date=trade_date,
            )
            mapping_id = str(mapping["mapping_id"])
            evidence_rows = repository.fetch_asof_evidence(
                cur,
                mapping_id,
                cutoff,
            )
            node_row = repository.fetch_node_score(
                cur,
                node_id=str(mapping.get("node_id") or ""),
                trade_date=trade_date,
                model_version=model_version,
            )
            context = repository.fetch_selection_context(
                cur,
                mapping_id=mapping_id,
                code=str(mapping.get("code") or ""),
                trade_date=trade_date,
                cutoff=cutoff,
            )
            scoring_mapping = _apply_selection_context(prepared_mapping, context)
            bundle = score_mapping(
                scoring_mapping,
                evidence_rows,
                trade_date=trade_date,
                node_score=(
                    float(node_row["total_score"])
                    if node_row and node_row.get("total_score") is not None
                    else None
                ),
            )
            _complete_context_bundle(bundle, context=context)
            bundles.append(bundle)
            if not dry_run:
                repository.upsert_score_bundle(cur, bundle)
                transitions += int(repository.transition_pool(cur, bundle))

    pool_counts: dict[str, int] = {}
    excluded = 0
    limitation_count = 0
    for bundle in bundles:
        pool_code = bundle["selection"].get("pool_code")
        if pool_code is None:
            excluded += 1
        else:
            pool_counts[pool_code] = pool_counts.get(pool_code, 0) + 1
        limitation_count += len(bundle.get("data_limitations") or [])
    return {
        "dry_run": dry_run,
        "chain_id": chain_id,
        "trade_date": trade_date.isoformat(),
        "model_version": model_version,
        "mapping_count": len(bundles),
        "pool_counts": pool_counts,
        "excluded_count": excluded,
        "limitation_count": limitation_count,
        "written": 0 if dry_run else len(bundles),
        "transitions": transitions,
        "results": bundles,
    }


def run_batch_score(
    *,
    pg_url: str,
    chain_id: str,
    trade_date: date,
    model_version: str,
    dry_run: bool,
    mapping_ids: list[str] | None = None,
    repository: SelectionRepository | None = None,
    connection_factory=None,
    connection=None,
) -> dict[str, Any]:
    if model_version != MODEL_VERSION:
        raise ValueError(f"model_version must be {MODEL_VERSION}")
    factory = connection_factory or (
        lambda: psycopg2.connect(pg_url, connect_timeout=5)
    )
    owns_connection = connection is None
    active = factory() if owns_connection else connection
    repo = repository or SelectionRepository(lambda: active)
    try:
        result = run_batch_score_in_connection(
            active,
            chain_id=chain_id,
            trade_date=trade_date,
            model_version=model_version,
            dry_run=dry_run,
            mapping_ids=mapping_ids,
            repository=repo,
        )
        if owns_connection:
            active.rollback() if dry_run else active.commit()
        return result
    except Exception:
        if owns_connection:
            active.rollback()
        raise
    finally:
        if owns_connection:
            active.close()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Score supply-chain mappings with the V2 evidence model"
    )
    parser.add_argument("--chain-id", required=True)
    parser.add_argument("--trade-date", required=True)
    parser.add_argument("--model-version", default=MODEL_VERSION)
    parser.add_argument("--mapping-id", action="append", dest="mapping_ids")
    parser.add_argument("--pg-url", default=DEFAULT_DSN)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    result = run_batch_score(
        pg_url=args.pg_url,
        chain_id=args.chain_id,
        trade_date=date.fromisoformat(args.trade_date),
        model_version=args.model_version,
        dry_run=args.dry_run,
        mapping_ids=args.mapping_ids,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
