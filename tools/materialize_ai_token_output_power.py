#!/usr/bin/env python3
"""Materialize the AI Token output power chain into staging snapshots."""

from __future__ import annotations

import argparse
from datetime import date, datetime
import json
import os
from pathlib import Path
from typing import Any, Iterable

import psycopg2
import psycopg2.extras

from kronos_factors.engine.token_output_power import (
    EvidenceFlags,
    calculate_billable_tokens,
    calculate_cost_per_million_tokens,
    derive_evidence_grade,
    derive_pool_code,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PG_URL = os.environ.get("KRONOS_PG_URL", "postgresql://kronos:kronos@localhost:6432/kronos")
CHAIN_ID = "ai_token_output_power"


def build_capacity_snapshot(row: dict[str, Any]) -> dict[str, Any]:
    billable_tokens = calculate_billable_tokens(
        row.get("available_mw"),
        row.get("operating_hours", row.get("available_hours")),
        row.get("utilization"),
        row.get("tokens_per_mw_hour"),
        row.get("cluster_availability"),
    )
    cost_per_million_tokens = calculate_cost_per_million_tokens(
        row.get("electricity_cost"),
        row.get("compute_depreciation"),
        row.get("facility_and_cooling_cost"),
        row.get("network_cost"),
        row.get("operation_cost"),
        row.get("financing_cost"),
        billable_tokens,
    )
    snapshot = {
        "snapshot_id": str(row.get("snapshot_id") or ""),
        "mapping_id": str(row.get("mapping_id") or ""),
        "code": str(row.get("code") or ""),
        "model_profile": str(row.get("model_profile") or "unknown"),
        "hardware_type": str(row.get("hardware_type") or "unknown"),
        "precision": str(row.get("precision") or "unknown"),
        "batch_mode": str(row.get("batch_mode") or "unknown"),
        "available_mw": row.get("available_mw"),
        "operating_hours": row.get("operating_hours", row.get("available_hours")),
        "utilization": row.get("utilization"),
        "tokens_per_mw_hour": row.get("tokens_per_mw_hour"),
        "cluster_availability": row.get("cluster_availability"),
        "billable_tokens": billable_tokens,
        "electricity_cost": row.get("electricity_cost"),
        "compute_depreciation": row.get("compute_depreciation"),
        "facility_and_cooling_cost": row.get("facility_and_cooling_cost"),
        "network_cost": row.get("network_cost"),
        "operation_cost": row.get("operation_cost"),
        "financing_cost": row.get("financing_cost"),
        "cost_per_million_tokens": cost_per_million_tokens,
        "calculation_status": "ready" if billable_tokens is not None and cost_per_million_tokens is not None else "unknown",
        "evidence_ids": list(row.get("evidence_ids") or []),
        "as_of_date": str(row.get("as_of_date") or ""),
    }
    if not snapshot["snapshot_id"]:
        snapshot["snapshot_id"] = ":".join([
            "token_capacity",
            snapshot["mapping_id"],
            snapshot["as_of_date"],
            snapshot["model_profile"],
            snapshot["hardware_type"],
            snapshot["precision"],
            snapshot["batch_mode"],
        ])
    return snapshot


def build_pool_state(row: dict[str, Any], as_of_date: str) -> dict[str, Any]:
    flags = EvidenceFlags(
        power_or_plan=bool(row.get("power_or_plan") or row.get("power_source_type")),
        facility_built=bool(row.get("facility_built")),
        runtime=bool(row.get("runtime") or row.get("tokens_per_mw_hour")),
        commercial=bool(row.get("commercial") or row.get("has_customer_validation") or row.get("has_token_revenue")),
        recurring_profit=bool(row.get("recurring_profit") or row.get("has_profit")),
    )
    grade = str(row.get("evidence_grade") or derive_evidence_grade(flags))
    pool_code = derive_pool_code(
        grade,
        has_customer_validation=bool(row.get("has_customer_validation")),
        has_token_revenue=bool(row.get("has_token_revenue")),
        has_profit=bool(row.get("has_profit")),
        has_product_or_device=bool(row.get("has_product_or_device") or row.get("hardware_type")),
        veto=bool(row.get("veto")),
    )
    return {
        "pool_state_id": f"token_pool:{row.get('mapping_id')}:{as_of_date}",
        "mapping_id": str(row.get("mapping_id") or ""),
        "evidence_grade": grade,
        "pool_code": pool_code,
        "authenticity_score": row.get("authenticity_score"),
        "commercialization_score": row.get("commercialization_score"),
        "industrial_attractiveness_score": row.get("industrial_attractiveness_score"),
        "coverage_ratio": row.get("coverage_ratio"),
        "reason_codes": list(row.get("reason_codes") or []),
        "next_validation_node": row.get("next_validation_node"),
        "next_validation_date": row.get("next_validation_date"),
        "review_status": str(row.get("review_status") or "pending_review"),
        "as_of_date": as_of_date,
    }


def split_formal_and_provisional(rows: Iterable[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    formal_items: list[dict[str, Any]] = []
    provisional_items: list[dict[str, Any]] = []
    for row in rows:
        if str(row.get("pool_code") or "").upper() in {"A", "B", "C"}:
            formal_items.append(row)
        else:
            provisional_items.append(row)
    return {"formal_items": formal_items, "provisional_items": provisional_items}


def build_mapping_sql(chain_id: str | None = None, formal_only: bool = False) -> str:
    clauses = ["COALESCE(m.status, '') NOT IN ('rejected', 'disabled')"]
    if chain_id:
        clauses.append("m.chain_id = 'ai_token_output_power'")
    pool_join = ""
    if formal_only:
        pool_join = "JOIN business_tag_token_pool_states ps ON ps.mapping_id = m.mapping_id"
        clauses.extend([
            "ps.pool_code IN ('A', 'B', 'C')",
            "ps.evidence_grade IN ('E2', 'E3', 'E4', 'E5')",
            "COALESCE(ps.coverage_ratio, 0) >= 0.60",
        ])
    where_sql = " AND ".join(clauses)
    return f"""
        SELECT m.mapping_id, m.code, m.chain_id, m.node_id, m.tag_name, m.status
        FROM business_tag_mapping m
        {pool_join}
        WHERE {where_sql}
        ORDER BY m.confidence DESC NULLS LAST, m.updated_at DESC NULLS LAST
    """


def _fetch_rows(pg_url: str, chain_id: str, as_of_date: str) -> list[dict[str, Any]]:
    sql = """
        SELECT
            e.evidence_id,
            e.mapping_id,
            e.code,
            e.chain_id,
            e.available_mw,
            e.available_hours,
            e.hardware_type,
            e.model_profile,
            e.precision,
            e.batch_mode,
            e.tokens_per_mw_hour,
            e.cluster_availability,
            e.evidence_grade,
            e.review_status,
            e.as_of_date,
            e.metadata
        FROM business_tag_token_output_power_evidence e
        JOIN business_tag_mapping m ON m.mapping_id = e.mapping_id
        WHERE e.chain_id = %s
          AND e.as_of_date <= %s::date
          AND COALESCE(m.status, '') NOT IN ('rejected', 'disabled')
          AND e.review_status <> 'rejected'
        ORDER BY e.as_of_date DESC, e.created_at DESC
    """
    with psycopg2.connect(pg_url) as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (chain_id, as_of_date))
            return [dict(row) for row in cur.fetchall()]


def _persist_snapshots(pg_url: str, capacity_rows: list[dict[str, Any]], pool_rows: list[dict[str, Any]]) -> None:
    with psycopg2.connect(pg_url) as conn:
        with conn.cursor() as cur:
            for row in capacity_rows:
                cur.execute(
                    """
                    INSERT INTO business_tag_token_output_capacity_snapshots (
                        snapshot_id, mapping_id, code, model_profile, hardware_type,
                        precision, batch_mode, available_mw, operating_hours,
                        utilization, tokens_per_mw_hour, cluster_availability,
                        billable_tokens, electricity_cost, compute_depreciation,
                        facility_and_cooling_cost, network_cost, operation_cost,
                        financing_cost, cost_per_million_tokens, calculation_status,
                        evidence_ids, as_of_date
                    ) VALUES (
                        %(snapshot_id)s, %(mapping_id)s, %(code)s, %(model_profile)s,
                        %(hardware_type)s, %(precision)s, %(batch_mode)s,
                        %(available_mw)s, %(operating_hours)s, %(utilization)s,
                        %(tokens_per_mw_hour)s, %(cluster_availability)s,
                        %(billable_tokens)s, %(electricity_cost)s,
                        %(compute_depreciation)s, %(facility_and_cooling_cost)s,
                        %(network_cost)s, %(operation_cost)s, %(financing_cost)s,
                        %(cost_per_million_tokens)s, %(calculation_status)s,
                        %(evidence_ids)s, %(as_of_date)s
                    )
                    ON CONFLICT (snapshot_id) DO UPDATE SET
                        billable_tokens = EXCLUDED.billable_tokens,
                        cost_per_million_tokens = EXCLUDED.cost_per_million_tokens,
                        calculation_status = EXCLUDED.calculation_status,
                        evidence_ids = EXCLUDED.evidence_ids
                    """,
                    {**row, "evidence_ids": json.dumps(row["evidence_ids"])},
                )
            for row in pool_rows:
                cur.execute(
                    """
                    INSERT INTO business_tag_token_pool_states (
                        pool_state_id, mapping_id, evidence_grade, pool_code,
                        authenticity_score, commercialization_score,
                        industrial_attractiveness_score, coverage_ratio,
                        reason_codes, next_validation_node, next_validation_date,
                        review_status, as_of_date
                    ) VALUES (
                        %(pool_state_id)s, %(mapping_id)s, %(evidence_grade)s,
                        %(pool_code)s, %(authenticity_score)s,
                        %(commercialization_score)s, %(industrial_attractiveness_score)s,
                        %(coverage_ratio)s, %(reason_codes)s, %(next_validation_node)s,
                        %(next_validation_date)s, %(review_status)s, %(as_of_date)s
                    )
                    ON CONFLICT (pool_state_id) DO UPDATE SET
                        evidence_grade = EXCLUDED.evidence_grade,
                        pool_code = EXCLUDED.pool_code,
                        coverage_ratio = EXCLUDED.coverage_ratio,
                        reason_codes = EXCLUDED.reason_codes,
                        review_status = EXCLUDED.review_status
                    """,
                    {**row, "reason_codes": json.dumps(row["reason_codes"])},
                )
        conn.commit()


def materialize(
    pg_url: str = DEFAULT_PG_URL,
    as_of_date: str | None = None,
    mode: str = "dry-run",
    top_n: int = 200,
    rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if mode not in {"dry-run", "staging", "apply"}:
        raise ValueError("mode must be dry-run, staging, or apply")
    effective_date = as_of_date or date.today().isoformat()
    source_rows = list(rows) if rows is not None else []
    limitations: list[str] = []
    if rows is None:
        try:
            source_rows = _fetch_rows(pg_url, CHAIN_ID, effective_date)
        except Exception as exc:
            source_rows = []
            limitations.append(f"power evidence lookup failed: {exc}")
    source_rows = source_rows[: max(1, int(top_n))]
    capacity_rows = [build_capacity_snapshot(row) for row in source_rows]
    pool_rows = [build_pool_state(row, effective_date) for row in source_rows]
    split = split_formal_and_provisional(pool_rows)
    if mode in {"staging", "apply"} and capacity_rows:
        _persist_snapshots(pg_url, capacity_rows, pool_rows)
    return {
        "mode": mode,
        "as_of_date": effective_date,
        "chain_id": CHAIN_ID,
        "mapping_count": len({row.get("mapping_id") for row in source_rows if row.get("mapping_id")}),
        "evidence_count": len(source_rows),
        "capacity_snapshot_count": len(capacity_rows),
        "pool_counts": {
            pool: sum(1 for row in pool_rows if row.get("pool_code") == pool)
            for pool in ("A", "B", "C", "D")
        },
        "formal_count": len(split["formal_items"]),
        "provisional_count": len(split["provisional_items"]),
        "excluded_count": sum(1 for row in source_rows if row.get("review_status") == "rejected"),
        "coverage_ratio": round(
            sum(1 for row in source_rows if row.get("available_mw") is not None and row.get("available_hours") is not None)
            / max(len(source_rows), 1),
            4,
        ),
        "limitations": limitations,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pg-url", default=DEFAULT_PG_URL)
    parser.add_argument("--as-of-date", default=None)
    parser.add_argument("--mode", choices=("dry-run", "staging", "apply"), default="dry-run")
    parser.add_argument("--top-n", type=int, default=200)
    args = parser.parse_args()
    print(json.dumps(materialize(args.pg_url, args.as_of_date, args.mode, args.top_n), ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
