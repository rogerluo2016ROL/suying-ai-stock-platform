#!/usr/bin/env python3
"""Register and snapshot the supply-chain expectation-gap screener.

This script is intentionally SQL-backed: it registers the model in the project
model tables and records the latest pick snapshot from already-landed
business-tag scores. It does not invent evidence or call an LLM.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime

import psycopg2
import psycopg2.extras


MODEL_KEY = "supply_chain_expectation_gap_v1"
MODEL_NAME = "产业链预期差选股模型"
DISPLAY_NAME = "产业链预期差选股模型 V1.0"
VERSION_TAG = "v1.0"

FACTOR_KEYS = [
    "model_score",
    "expectation_gap_score",
    "reliability_adjusted_gap_score",
    "evidence_quality_score",
    "label_fit_score",
    "gap_momentum_score",
    "actual_progress_score",
    "market_expectation_score",
    "evidence_delta_score",
    "risk_penalty_score",
    "three_high_total",
    "growth_score",
    "profit_score",
    "moat_score",
    "stage_score",
    "evidence_score",
    "prosperity_score",
    "price_change_20d",
    "approved_evidence_count",
]

REASSESSMENT_ALLOWED_STATUSES = {"strong_confirmed", "watch_review"}

SIGNAL_TIER_THRESHOLDS = {
    "strong": 15.0,
    "watch": 8.0,
    "early": 3.0,
}


def grade_from_score(score: float) -> str:
    if score >= 65:
        return "S"
    if score >= 55:
        return "A"
    if score >= 45:
        return "B"
    return "C"


def signal_tier_from_gap(gap_score: float) -> str:
    score = float(gap_score or 0.0)
    if score >= SIGNAL_TIER_THRESHOLDS["strong"]:
        return "strong"
    if score >= SIGNAL_TIER_THRESHOLDS["watch"]:
        return "watch"
    if score >= SIGNAL_TIER_THRESHOLDS["early"]:
        return "early"
    return "none"


def latest_trade_date(cur) -> str:
    cur.execute("SELECT max(trade_date) AS trade_date FROM business_tag_expectation_gap_scores")
    row = cur.fetchone()
    if not row or not row["trade_date"]:
        raise RuntimeError("business_tag_expectation_gap_scores has no trade_date")
    return str(row["trade_date"])[:10]


def _num(row: dict, key: str, default: float = 0.0) -> float:
    value = row.get(key)
    if value is None:
        return default
    return float(value)


def is_reassessment_eligible(row: dict) -> bool:
    return str(row.get("reassessment_status") or "") in REASSESSMENT_ALLOWED_STATUSES


def model_score_from_row(row: dict) -> float:
    """Score one already re-assessed mapping.

    The important change is that the leading gap factor uses the conservative
    reliability-adjusted score, not the raw expectation-gap score.
    """

    score = (
        _num(row, "reliability_adjusted_gap_score") * 0.40
        + _num(row, "gap_momentum_score", 50) * 0.12
        + _num(row, "three_high_total") * 0.20
        + _num(row, "evidence_delta_score") * 0.10
        + _num(row, "moat_score") * 0.08
        + _num(row, "prosperity_score", 50) * 0.08
        + _num(row, "evidence_quality_score") * 0.12
        + _num(row, "label_fit_score") * 0.08
        - max(_num(row, "price_change_20d"), 0) * 0.08
    )
    return round(score, 2)


def fetch_picks(cur, trade_date: str, top_n: int, min_gap: float) -> list[dict]:
    cur.execute(
        """
        WITH latest_reassessment AS (
            SELECT max(assessment_date) AS assessment_date
            FROM business_tag_evidence_reassessment
        ),
        scored AS (
            SELECT
                b.mapping_id,
                b.code,
                coalesce(s.name, split_part(b.code, '.', 1)) AS name,
                b.chain_id,
                b.tag_name,
                g.expectation_gap_score,
                g.gap_type,
                r.reliability_adjusted_gap_score,
                r.evidence_quality_score,
                r.label_fit_score,
                r.review_status AS reassessment_status,
                g.actual_progress_score,
                g.market_expectation_score,
                g.evidence_delta_score,
                g.risk_penalty_score,
                t.total_score AS three_high_total,
                t.growth_score,
                t.profit_score,
                t.moat_score,
                t.stage_score,
                t.evidence_score,
                coalesce((g.score_detail->>'prosperity_score')::numeric, 50) AS prosperity_score,
                coalesce((g.score_detail->>'gap_momentum_score')::numeric, 50) AS gap_momentum_score,
                (g.score_detail->>'price_change_20d')::numeric AS price_change_20d,
                coalesce((g.score_detail->>'approved_evidence_count')::int, 0) AS approved_evidence_count,
                dk.close,
                dk.change_pct,
                round((
                    r.reliability_adjusted_gap_score * 0.40
                    + coalesce((g.score_detail->>'gap_momentum_score')::numeric, 50) * 0.12
                    + coalesce(t.total_score, 0) * 0.20
                    + g.evidence_delta_score * 0.10
                    + coalesce(t.moat_score, 0) * 0.08
                    + coalesce((g.score_detail->>'prosperity_score')::numeric, 50) * 0.08
                    + r.evidence_quality_score * 0.12
                    + r.label_fit_score * 0.08
                    - greatest(coalesce((g.score_detail->>'price_change_20d')::numeric, 0), 0) * 0.08
                )::numeric, 2) AS model_score
            FROM business_tag_expectation_gap_scores g
            JOIN business_tag_mapping b ON b.mapping_id = g.mapping_id
            JOIN latest_reassessment lr ON lr.assessment_date IS NOT NULL
            JOIN business_tag_evidence_reassessment r
              ON r.mapping_id = g.mapping_id
             AND r.assessment_date = lr.assessment_date
            LEFT JOIN business_tag_three_high_scores t
              ON t.mapping_id = g.mapping_id AND t.trade_date = g.trade_date
            LEFT JOIN stocks s ON s.code = split_part(b.code, '.', 1)
            LEFT JOIN daily_kline dk
              ON dk.code = split_part(b.code, '.', 1) AND dk.trade_date = g.trade_date
            WHERE g.trade_date = %s
              AND g.gap_type IN ('positive', 'positive_evidence_delta', 'neutral')
              AND r.review_status IN ('strong_confirmed', 'watch_review')
              AND r.reliability_adjusted_gap_score >= %s
              AND coalesce(s.is_st, 0) = 0
        ),
        ranked AS (
            SELECT *,
                row_number() OVER (
                    PARTITION BY split_part(code, '.', 1)
                    ORDER BY model_score DESC, reliability_adjusted_gap_score DESC
                ) AS rn
            FROM scored
        )
        SELECT *
        FROM ranked
        WHERE rn = 1
        ORDER BY model_score DESC, reliability_adjusted_gap_score DESC, expectation_gap_score DESC
        LIMIT %s
        """,
        (trade_date, min_gap, top_n),
    )
    rows = [dict(row) for row in cur.fetchall()]
    for index, row in enumerate(rows, start=1):
        row["rank"] = index
        row["grade"] = grade_from_score(float(row.get("model_score") or 0))
        row["signal_tier"] = signal_tier_from_gap(float(row.get("reliability_adjusted_gap_score") or 0))
    return rows


def factor_payload(row: dict) -> dict:
    payload = {}
    for key in FACTOR_KEYS:
        value = row.get(key)
        if value is not None:
            payload[key] = float(value)
    payload.update({
        "chain_id": row.get("chain_id"),
        "tag_name": row.get("tag_name"),
        "gap_type": row.get("gap_type"),
        "reassessment_status": row.get("reassessment_status"),
        "signal_tier": row.get("signal_tier") or signal_tier_from_gap(float(row.get("reliability_adjusted_gap_score") or row.get("expectation_gap_score") or 0)),
    })
    return payload


def register_model(cur, *, trade_date: str, top_n: int, pick_count: int, positive_count: int) -> None:
    params = {
        "model_key": MODEL_KEY,
        "display_name": DISPLAY_NAME,
        "version_tag": VERSION_TAG,
        "selection_universe": "business_tag_mapping candidates across 18 supply chains",
        "dedupe": "one strongest mapping per stock code",
        "hard_filters": [
            "latest expectation-gap score date",
            "latest evidence reassessment date",
            "gap_type in positive-compatible or neutral labels",
            "reassessment_status in strong_confirmed/watch_review",
            "reliability_adjusted_gap_score >= 8 by default",
            "exclude ST stocks",
        ],
        "ranking_formula": (
            "reliability_adjusted_gap*0.40 + gap_momentum*0.12 + three_high*0.20 "
            "+ evidence_delta*0.10 + moat*0.08 + prosperity*0.08 "
            "+ evidence_quality*0.12 + label_fit*0.08 - positive_20d_return*0.08"
        ),
        "guardrails": [
            "not an automatic buy list",
            "weak signals cannot approve evidence or upgrade stages",
            "downgrade_or_remove and manual_review mappings are excluded from recommendations",
            "staging until forward returns are backfilled",
        ],
    }
    metrics = {
        "trade_date": trade_date,
        "top_n": top_n,
        "snapshot_count": pick_count,
        "positive_candidate_count": positive_count,
    }
    cur.execute(
        """
        INSERT INTO screening_models (model_key, display_name, category, factor_keys, is_active)
        VALUES (%s, %s, %s, %s, true)
        ON CONFLICT (model_key) DO UPDATE SET
            display_name = EXCLUDED.display_name,
            category = EXCLUDED.category,
            factor_keys = EXCLUDED.factor_keys,
            is_active = true
        """,
        (MODEL_KEY, DISPLAY_NAME, "产业链", FACTOR_KEYS),
    )
    cur.execute(
        """
        INSERT INTO model_registry (
            id, name, version, model_type, stage, run_id, params, metrics,
            artifact_uri, created_by, updated_at, notes
        )
        VALUES (%s, %s, 1, 'screener', 'staging', %s, %s::json, %s::json,
                %s, 'codex', now(), %s)
        ON CONFLICT (name, version) DO UPDATE SET
            id = EXCLUDED.id,
            model_type = EXCLUDED.model_type,
            stage = EXCLUDED.stage,
            run_id = EXCLUDED.run_id,
            params = EXCLUDED.params,
            metrics = EXCLUDED.metrics,
            artifact_uri = EXCLUDED.artifact_uri,
            updated_at = now(),
            notes = EXCLUDED.notes
        """,
        (
            MODEL_KEY,
            MODEL_NAME,
            f"{MODEL_KEY}-{trade_date}",
            json.dumps(params, ensure_ascii=False),
            json.dumps(metrics, ensure_ascii=False),
            "tools/register_supply_chain_expectation_gap_model.py",
            "三层证据驱动的产业链预期差选股模型；当前为 staging，需回填收益后再转 production。",
        ),
    )
    cur.execute(
        """
        UPDATE model_versions
        SET is_current = false
        WHERE model_name = %s
        """,
        (MODEL_KEY,),
    )
    cur.execute(
        """
        DELETE FROM model_versions
        WHERE model_name = %s AND version_tag = %s
        """,
        (MODEL_KEY, VERSION_TAG),
    )
    cur.execute(
        """
        INSERT INTO model_versions (
            model_name, version_tag, snapshot_count, win_rate,
            mean_return, is_current, deployed_at
        )
        VALUES (%s, %s, %s, NULL, NULL, true, now())
        """,
        (MODEL_KEY, VERSION_TAG, pick_count),
    )


def write_snapshot(cur, picks: list[dict], trade_date: str, time_slot: str) -> int:
    cur.execute(
        """
        DELETE FROM screening_snapshots
        WHERE model_key = %s AND trade_date = %s AND time_slot = %s
        """,
        (MODEL_KEY, trade_date, time_slot),
    )
    rows = []
    for row in picks:
        rows.append(
            (
                MODEL_KEY,
                trade_date,
                str(row["code"]),
                time_slot,
                json.dumps(factor_payload(row), ensure_ascii=False),
                float(row.get("model_score") or 0),
                row["grade"],
                int(row["rank"]),
            )
        )
    psycopg2.extras.execute_values(
        cur,
        """
        INSERT INTO screening_snapshots (
            model_key, trade_date, stock_code, time_slot,
            factors, total_score, grade, rank_in_day
        )
        VALUES %s
        """,
        rows,
        page_size=100,
    )
    return len(rows)


def register_and_snapshot(pg_url: str, trade_date: str | None, top_n: int, min_gap: float, time_slot: str) -> dict:
    with psycopg2.connect(pg_url) as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            score_date = trade_date or latest_trade_date(cur)
            picks = fetch_picks(cur, score_date, top_n, min_gap)
            cur.execute(
                """
                WITH latest_reassessment AS (
                    SELECT max(assessment_date) AS assessment_date
                    FROM business_tag_evidence_reassessment
                )
                SELECT count(*)
                FROM business_tag_expectation_gap_scores g
                JOIN latest_reassessment lr ON lr.assessment_date IS NOT NULL
                JOIN business_tag_evidence_reassessment r
                  ON r.mapping_id = g.mapping_id
                 AND r.assessment_date = lr.assessment_date
                WHERE g.trade_date = %s
                  AND g.gap_type IN ('positive', 'positive_evidence_delta', 'neutral')
                  AND r.review_status IN ('strong_confirmed', 'watch_review')
                  AND r.reliability_adjusted_gap_score >= %s
                """,
                (score_date, min_gap),
            )
            positive_count = int(cur.fetchone()["count"] or 0)
            register_model(
                cur,
                trade_date=score_date,
                top_n=top_n,
                pick_count=len(picks),
                positive_count=positive_count,
            )
            snapshot_count = write_snapshot(cur, picks, score_date, time_slot)
        conn.commit()
    return {
        "model_key": MODEL_KEY,
        "display_name": DISPLAY_NAME,
        "version_tag": VERSION_TAG,
        "stage": "staging",
        "trade_date": score_date,
        "top_n": top_n,
        "min_gap": min_gap,
        "positive_candidate_count": positive_count,
        "snapshot_count": snapshot_count,
        "top_picks": [
            {
                "rank": row["rank"],
                "code": row["code"],
                "name": row["name"],
                "chain_id": row["chain_id"],
                "tag_name": row["tag_name"],
                "model_score": float(row["model_score"]),
                "expectation_gap_score": float(row["expectation_gap_score"]),
                "reliability_adjusted_gap_score": float(row.get("reliability_adjusted_gap_score") or 0),
                "evidence_quality_score": float(row.get("evidence_quality_score") or 0),
                "label_fit_score": float(row.get("label_fit_score") or 0),
                "reassessment_status": row.get("reassessment_status"),
                "gap_momentum_score": float(row.get("gap_momentum_score") or 0),
                "three_high_total": float(row["three_high_total"] or 0),
                "grade": row["grade"],
                "signal_tier": row["signal_tier"],
            }
            for row in picks[:10]
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Register supply-chain expectation-gap screener")
    parser.add_argument("--pg-url", default=os.environ.get("KRONOS_PG_URL", "postgresql://kronos:kronos@localhost:6432/kronos"))
    parser.add_argument("--trade-date", default=None)
    parser.add_argument("--top-n", type=int, default=30)
    parser.add_argument("--min-gap", type=float, default=8.0)
    parser.add_argument("--time-slot", default="close")
    args = parser.parse_args()
    payload = register_and_snapshot(args.pg_url, args.trade_date, args.top_n, args.min_gap, args.time_slot)
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
