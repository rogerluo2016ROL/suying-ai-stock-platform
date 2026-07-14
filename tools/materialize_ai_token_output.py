#!/usr/bin/env python3
"""Materialize seven-dimension scores and A/B/C/D pools for ai_token_output."""

from __future__ import annotations

import argparse
from datetime import date
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any

import psycopg2
import psycopg2.extras


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages/kronos-factors"))
from kronos_factors.engine.token_commercial_output import derive_token_pool, score_token_dimensions  # noqa: E402


CHAIN_ID = "ai_token_output"


def stable_id(prefix: str, *parts: object) -> str:
    digest = hashlib.sha1("|".join(str(part) for part in parts).encode("utf-8")).hexdigest()[:20]
    return f"{prefix}-{digest}"


def _facts(row: dict[str, Any]) -> dict[str, bool]:
    return {
        "product": bool(row.get("product_verified")),
        "verified_product": bool(row.get("product_verified")),
        "verified_supply": bool(row.get("verified_supply")),
        "verified_order": bool(row.get("verified_order")),
        "verified_project": bool(row.get("verified_project")),
        "customer_usage": bool(row.get("customer_usage_verified")),
        "running": bool(row.get("runtime_verified")),
        "recurring_delivery": bool(row.get("recurring_delivery_verified")),
        "token_revenue": bool(row.get("token_revenue_verified")),
        "continuous_cashflow": bool(row.get("continuous_cashflow_verified")),
    }


def _dimension_values(row: dict[str, Any]) -> dict[str, float | None]:
    grade_score = {"E0": 10, "E1": 30, "E2": 55, "E3": 75, "E4": 90, "E5": 100}.get(str(row.get("evidence_grade")), 0)
    return {
        "business_authenticity": 80.0 if row.get("product_verified") else 30.0 if row.get("evidence_grade") == "E1" else None,
        "token_value_capture": 90.0 if row.get("token_revenue_verified") else None,
        "technology_inference_efficiency": None,
        "customer_commercialization": 80.0 if row.get("customer_usage_verified") else 65.0 if row.get("verified_order") else None,
        "competition_moat": 65.0 if row.get("verified_supply") or row.get("verified_project") else None,
        "growth_realization": 90.0 if row.get("continuous_cashflow_verified") else None,
        "evidence_quality": float(grade_score),
    }


def build_pool_state(row: dict[str, Any]) -> dict[str, Any]:
    dimensions = score_token_dimensions(_dimension_values(row))
    pool_code, reasons = derive_token_pool(str(row.get("evidence_grade") or "E0"), str(row.get("review_status") or "candidate"), _facts(row))
    return {
        "mapping_id": row["mapping_id"], "code": row["code"], "layer_id": row["layer_id"],
        "evidence_grade": row.get("evidence_grade") or "E0", "review_status": row.get("review_status") or "candidate",
        "pool_code": pool_code, "industry_score": dimensions["weighted_score"],
        "market_signal_score": row.get("market_signal_score"), "coverage_ratio": dimensions["coverage_ratio"],
        "formal_ranking_eligible": dimensions["formal_ranking_eligible"],
        "missing_dimensions": dimensions["missing_dimensions"], "reason_codes": reasons,
        "dimension_values": _dimension_values(row),
    }


def materialize(pg_url: str, as_of_date: str, mode: str = "dry-run") -> dict[str, Any]:
    if mode not in {"dry-run", "staging", "apply"}:
        raise ValueError("mode must be dry-run, staging or apply")
    with psycopg2.connect(pg_url) as conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT e.*, NULL::double precision AS market_signal_score
            FROM business_tag_token_commercial_evidence e
            JOIN business_tag_mapping m ON m.mapping_id=e.mapping_id
            WHERE e.chain_id=%s AND e.as_of_date<=%s AND m.status NOT IN ('rejected')
            ORDER BY e.mapping_id,e.as_of_date DESC
        """, (CHAIN_ID, as_of_date))
        latest: dict[str, dict[str, Any]] = {}
        for row in cur.fetchall():
            latest.setdefault(row["mapping_id"], dict(row))
        states = [build_pool_state(row) for row in latest.values()]
        counts = {pool: sum(state["pool_code"] == pool for state in states) for pool in "ABCD"}
        if mode == "dry-run":
            conn.rollback()
            return {"mode": mode, "chain_id": CHAIN_ID, "as_of_date": as_of_date, "mapping_count": len(states), "pool_counts": counts, "formal_count": counts["A"] + counts["B"] + counts["C"], "provisional_count": counts["D"]}
        for state in states:
            values = state["dimension_values"]
            score_id = stable_id("TOKENOUTSCORE", state["mapping_id"], as_of_date)
            pool_id = stable_id("TOKENOUTPOOL", state["mapping_id"], as_of_date)
            cur.execute("""
                INSERT INTO business_tag_token_commercial_scores
                (score_id,mapping_id,business_authenticity,token_value_capture,technology_inference_efficiency,customer_commercialization,competition_moat,growth_realization,evidence_quality,weighted_score,coverage_ratio,formal_ranking_eligible,evidence_ids,score_detail,as_of_date)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'[]'::jsonb,%s::jsonb,%s)
                ON CONFLICT (mapping_id,as_of_date) DO UPDATE SET business_authenticity=EXCLUDED.business_authenticity,token_value_capture=EXCLUDED.token_value_capture,technology_inference_efficiency=EXCLUDED.technology_inference_efficiency,customer_commercialization=EXCLUDED.customer_commercialization,competition_moat=EXCLUDED.competition_moat,growth_realization=EXCLUDED.growth_realization,evidence_quality=EXCLUDED.evidence_quality,weighted_score=EXCLUDED.weighted_score,coverage_ratio=EXCLUDED.coverage_ratio,formal_ranking_eligible=EXCLUDED.formal_ranking_eligible,score_detail=EXCLUDED.score_detail
            """, (score_id, state["mapping_id"], values["business_authenticity"], values["token_value_capture"], values["technology_inference_efficiency"], values["customer_commercialization"], values["competition_moat"], values["growth_realization"], values["evidence_quality"], state["industry_score"], state["coverage_ratio"], state["formal_ranking_eligible"], json.dumps({"missing_dimensions": state["missing_dimensions"]}), as_of_date))
            cur.execute("""
                INSERT INTO business_tag_token_commercial_pool_states
                (pool_state_id,mapping_id,code,layer_id,evidence_grade,pool_code,industry_score,market_signal_score,coverage_ratio,reason_codes,review_status,next_validation_node,as_of_date)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,'company_product_evidence',%s)
                ON CONFLICT (mapping_id,as_of_date) DO UPDATE SET evidence_grade=EXCLUDED.evidence_grade,pool_code=EXCLUDED.pool_code,industry_score=EXCLUDED.industry_score,market_signal_score=EXCLUDED.market_signal_score,coverage_ratio=EXCLUDED.coverage_ratio,reason_codes=EXCLUDED.reason_codes,review_status=EXCLUDED.review_status
            """, (pool_id, state["mapping_id"], state["code"], state["layer_id"], state["evidence_grade"], state["pool_code"], state["industry_score"], state["market_signal_score"], state["coverage_ratio"], json.dumps(state["reason_codes"]), state["review_status"], as_of_date))
        conn.commit()
        return {"mode": mode, "chain_id": CHAIN_ID, "as_of_date": as_of_date, "mapping_count": len(states), "pool_counts": counts, "formal_count": counts["A"] + counts["B"] + counts["C"], "provisional_count": counts["D"]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pg-url", default=os.environ.get("KRONOS_PG_URL", "postgresql://kronos:kronos@localhost:6432/kronos"))
    parser.add_argument("--as-of-date", default=date.today().isoformat())
    parser.add_argument("--mode", choices=("dry-run", "staging", "apply"), default="dry-run")
    args = parser.parse_args()
    print(json.dumps(materialize(args.pg_url, args.as_of_date, args.mode), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
