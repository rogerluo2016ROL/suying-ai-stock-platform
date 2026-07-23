#!/usr/bin/env python3
"""Register supply-chain selection V2 and write idempotent daily snapshots."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path
from typing import Any, Callable

import psycopg2
from psycopg2.extras import RealDictCursor, execute_values


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = PROJECT_ROOT / "packages" / "kronos-factors"
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from kronos_factors.scorer.supply_chain_selection_v2 import (  # noqa: E402
    aggregate_stock_mappings,
)


MODEL_ID = "supply_chain_research_selection_v2"
MODEL_NAME = "产业链研究与选股模型"
DISPLAY_NAME = "产业链研究与选股模型 V2.0"
VERSION_TAG = "v2.0"
MODEL_STAGE = "staging"
REGISTRY_VERSION = 2
ELIGIBLE_POOLS = ("A", "B", "C")
FACTOR_KEYS = [
    "pool_code",
    "primary_mapping_id",
    "model_version",
    "benefit_score",
    "expectation_gap_score",
    "risk_score",
    "confidence_score",
    "opportunity_score",
    "evidence_level",
    "coverage_ratio",
    "veto_reasons",
]
NUMERIC_FACTOR_KEYS = (
    "benefit_score",
    "expectation_gap_score",
    "risk_score",
    "confidence_score",
    "opportunity_score",
    "coverage_ratio",
)
REQUIRED_SCHEMA = {
    "screening_models": {
        "model_key",
        "display_name",
        "category",
        "factor_keys",
        "is_active",
    },
    "model_registry": {
        "id",
        "name",
        "version",
        "model_type",
        "stage",
        "params",
        "metrics",
        "artifact_uri",
    },
    "model_versions": {
        "model_name",
        "version_tag",
        "snapshot_count",
        "win_rate",
        "mean_return",
        "is_current",
    },
    "screening_snapshots": {
        "model_key",
        "trade_date",
        "stock_code",
        "time_slot",
        "factors",
        "total_score",
        "grade",
        "rank_in_day",
    },
}
POOL_PRIORITY = {"A": 0, "B": 1, "C": 2}
DEFAULT_DSN = os.environ.get(
    "KRONOS_PG_URL",
    "postgresql://kronos:kronos@localhost:6432/kronos",
)


class MissingRegistrationSchema(RuntimeError):
    def __init__(self, missing: dict[str, list[str]]):
        self.missing = missing
        summary = "; ".join(
            f"{table}: {', '.join(columns)}"
            for table, columns in sorted(missing.items())
        )
        super().__init__("missing registration schema: " + summary)


def normalize_stock_code(value: Any) -> str:
    return str(value or "").split(".", 1)[0]


def snapshot_factor_payload(row: dict[str, Any]) -> dict[str, Any]:
    payload = {key: row.get(key) for key in FACTOR_KEYS}
    for key in NUMERIC_FACTOR_KEYS:
        if payload.get(key) is not None:
            payload[key] = float(payload[key])
    return payload


def _snapshot_total_score(row: dict[str, Any]) -> float | None:
    value = row.get("opportunity_score")
    if value is None:
        value = row.get("stock_score")
    return None if value is None else float(value)


def filter_snapshot_candidates(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        dict(row)
        for row in rows
        if row.get("pool_code") in ELIGIBLE_POOLS
        and not row.get("veto_reasons")
        and row.get("eligibility_status", "eligible") == "eligible"
    ]


def fetch_pool_candidates(
    cur,
    *,
    trade_date: str | date,
    model_version: str,
) -> list[dict[str, Any]]:
    cur.execute(
        """
        SELECT
            b.code,
            b.mapping_id,
            b.business_segment_id,
            b.node_id,
            b.chain_id,
            b.tag_name,
            b.revenue_ratio,
            b.gross_profit_ratio,
            (b.business_segment_id IS NOT NULL AND
             (b.revenue_ratio IS NOT NULL OR b.gross_profit_ratio IS NOT NULL))
                AS independent_revenue,
            s.model_version,
            s.benefit_score,
            s.expectation_gap_score,
            s.catalyst_score,
            s.risk_score,
            s.confidence_score,
            s.opportunity_score,
            s.pool_code,
            s.eligibility_status,
            s.veto_reasons,
            s.factor_detail,
            s.evidence_ids,
            a.evidence_level,
            least(
                a.coverage_ratio,
                o.total_coverage,
                ben.coverage_ratio
            ) AS coverage_ratio
        FROM business_tag_selection_scores s
        JOIN business_tag_mapping b ON b.mapping_id = s.mapping_id
        JOIN business_tag_authenticity_scores a
          ON a.mapping_id = s.mapping_id
         AND a.trade_date = s.trade_date
         AND a.model_version = s.model_version
        JOIN business_tag_operating_quality_scores o
          ON o.mapping_id = s.mapping_id
         AND o.trade_date = s.trade_date
         AND o.model_version = s.model_version
        JOIN business_tag_benefit_scores ben
          ON ben.mapping_id = s.mapping_id
         AND ben.trade_date = s.trade_date
         AND ben.model_version = s.model_version
        WHERE s.trade_date = %s
          AND s.model_version = %s
          AND s.pool_code IS NOT NULL
          AND b.status <> 'rejected'
        ORDER BY b.code, b.mapping_id
        """,
        (trade_date, model_version),
    )
    return aggregate_stock_mappings([dict(row) for row in cur.fetchall()])


def limit_candidates_by_pool(
    rows: list[dict[str, Any]],
    *,
    top_a: int,
    top_b: int,
    top_c: int,
) -> list[dict[str, Any]]:
    limits = {"A": top_a, "B": top_b, "C": top_c}
    selected: list[dict[str, Any]] = []
    for pool_code in ELIGIBLE_POOLS:
        pool_rows = [row for row in rows if row.get("pool_code") == pool_code]
        pool_rows.sort(
            key=lambda row: (
                -float(row.get("opportunity_score") or -1.0),
                -float(row.get("stock_score") or 0.0),
                normalize_stock_code(row.get("code")),
            )
        )
        selected.extend(pool_rows[: limits[pool_code]])
    selected.sort(
        key=lambda row: (
            POOL_PRIORITY[str(row["pool_code"])],
            -float(row.get("opportunity_score") or -1.0),
            -float(row.get("stock_score") or 0.0),
            normalize_stock_code(row.get("code")),
        )
    )
    for rank, row in enumerate(selected, start=1):
        row["rank"] = rank
    return selected


def preflight_schema(cur) -> None:
    cur.execute(
        """
        SELECT table_name, column_name
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = ANY(%s)
        """,
        (list(REQUIRED_SCHEMA),),
    )
    present: dict[str, set[str]] = {}
    for row in cur.fetchall():
        if isinstance(row, dict):
            table_name = str(row["table_name"])
            column_name = str(row["column_name"])
        else:
            table_name = str(row[0])
            column_name = str(row[1])
        present.setdefault(table_name, set()).add(column_name)
    missing = {
        table: sorted(required - present.get(table, set()))
        for table, required in REQUIRED_SCHEMA.items()
        if required - present.get(table, set())
    }
    if missing:
        raise MissingRegistrationSchema(missing)


def _register_model(
    cur,
    *,
    trade_date: str,
    snapshot_count: int,
    pool_counts: dict[str, int],
) -> None:
    params = {
        "model_id": MODEL_ID,
        "version_tag": VERSION_TAG,
        "stage": MODEL_STAGE,
        "factor_keys": FACTOR_KEYS,
        "selection_unit": "business_tag_mapping",
        "aggregation": "one_primary_mapping_per_stock",
        "eligible_pools": list(ELIGIBLE_POOLS),
        "guardrails": [
            "D pool is research-only and excluded from snapshots",
            "vetoed or ineligible mappings are excluded",
            "staging until real no-lookahead backtest metrics exist",
        ],
    }
    metrics = {
        "status": "insufficient_evidence",
        "trade_date": trade_date,
        "snapshot_count": snapshot_count,
        "pool_counts": pool_counts,
    }
    cur.execute(
        """
        INSERT INTO screening_models (
            model_key, display_name, category, factor_keys, is_active
        ) VALUES (%s, %s, %s, %s, true)
        ON CONFLICT (model_key) DO UPDATE SET
            display_name = EXCLUDED.display_name,
            category = EXCLUDED.category,
            factor_keys = EXCLUDED.factor_keys,
            is_active = true
        """,
        (MODEL_ID, DISPLAY_NAME, "产业链", FACTOR_KEYS),
    )
    cur.execute(
        """
        INSERT INTO model_registry (
            id, name, version, model_type, stage, run_id, params, metrics,
            artifact_uri, created_by, updated_at, notes
        ) VALUES (
            %s, %s, %s, 'screener', %s, %s, %s::jsonb, %s::jsonb,
            %s, 'system', now(), %s
        )
        ON CONFLICT (name, version) DO UPDATE SET
            id = EXCLUDED.id,
            model_type = 'screener',
            stage = EXCLUDED.stage,
            run_id = EXCLUDED.run_id,
            params = EXCLUDED.params,
            metrics = EXCLUDED.metrics,
            artifact_uri = EXCLUDED.artifact_uri,
            updated_at = now(),
            notes = EXCLUDED.notes
        """,
        (
            MODEL_ID,
            MODEL_NAME,
            REGISTRY_VERSION,
            MODEL_STAGE,
            f"{MODEL_ID}-{trade_date}",
            json.dumps(params, ensure_ascii=False),
            json.dumps(metrics, ensure_ascii=False),
            "tools/register_supply_chain_research_selection_v2.py",
            "证据驱动的产业链研究与选股模型；当前为 staging，真实回测完成前不得转 production。",
        ),
    )
    cur.execute(
        "UPDATE model_versions SET is_current = false WHERE model_name = %s",
        (MODEL_ID,),
    )
    cur.execute(
        "DELETE FROM model_versions WHERE model_name = %s AND version_tag = %s",
        (MODEL_ID, VERSION_TAG),
    )
    cur.execute(
        """
        INSERT INTO model_versions (
            model_name, version_tag, snapshot_count, win_rate,
            mean_return, is_current, deployed_at
        ) VALUES (%s, %s, %s, NULL, NULL, true, now())
        """,
        (MODEL_ID, VERSION_TAG, snapshot_count),
    )


def _write_snapshots(
    cur,
    picks: list[dict[str, Any]],
    *,
    trade_date: str,
    time_slot: str,
    execute_values_fn: Callable[..., Any],
) -> int:
    cur.execute(
        """
        DELETE FROM screening_snapshots
        WHERE model_key = %s AND trade_date = %s AND time_slot = %s
        """,
        (MODEL_ID, trade_date, time_slot),
    )
    rows = [
        (
            MODEL_ID,
            trade_date,
            normalize_stock_code(row["code"]),
            time_slot,
            json.dumps(snapshot_factor_payload(row), ensure_ascii=False),
            _snapshot_total_score(row),
            row["pool_code"],
            int(row["rank"]),
        )
        for row in picks
    ]
    if rows:
        execute_values_fn(
            cur,
            """
            INSERT INTO screening_snapshots (
                model_key, trade_date, stock_code, time_slot,
                factors, total_score, grade, rank_in_day
            ) VALUES %s
            """,
            rows,
            page_size=100,
        )
    return len(rows)


def register_and_snapshot(
    *,
    pg_url: str,
    trade_date: str | date,
    time_slot: str = "close",
    top_a: int = 20,
    top_b: int = 20,
    top_c: int = 20,
    model_version: str = VERSION_TAG,
    dry_run: bool = False,
    connection_factory: Callable[[str], Any] | None = None,
    execute_values_fn: Callable[..., Any] = execute_values,
) -> dict[str, Any]:
    if model_version != VERSION_TAG:
        raise ValueError(f"model_version must be {VERSION_TAG}")
    if any(limit < 0 for limit in (top_a, top_b, top_c)):
        raise ValueError("pool limits must be non-negative")
    if not time_slot:
        raise ValueError("time_slot must not be empty")
    score_date = (
        trade_date.isoformat() if isinstance(trade_date, date) else str(trade_date)
    )
    date.fromisoformat(score_date)
    factory = connection_factory or (lambda dsn: psycopg2.connect(dsn))
    connection = factory(pg_url)
    try:
        with connection.cursor(cursor_factory=RealDictCursor) as cur:
            preflight_schema(cur)
            candidates = fetch_pool_candidates(
                cur,
                trade_date=score_date,
                model_version=model_version,
            )
            eligible = filter_snapshot_candidates(candidates)
            picks = limit_candidates_by_pool(
                eligible,
                top_a=top_a,
                top_b=top_b,
                top_c=top_c,
            )
            pool_counts = {
                pool_code: sum(
                    1 for row in picks if row.get("pool_code") == pool_code
                )
                for pool_code in ELIGIBLE_POOLS
            }
            if dry_run:
                snapshot_count = 0
            else:
                _register_model(
                    cur,
                    trade_date=score_date,
                    snapshot_count=len(picks),
                    pool_counts=pool_counts,
                )
                snapshot_count = _write_snapshots(
                    cur,
                    picks,
                    trade_date=score_date,
                    time_slot=time_slot,
                    execute_values_fn=execute_values_fn,
                )
        if dry_run:
            connection.rollback()
        else:
            connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
    return {
        "model_id": MODEL_ID,
        "display_name": DISPLAY_NAME,
        "version_tag": VERSION_TAG,
        "stage": MODEL_STAGE,
        "trade_date": score_date,
        "time_slot": time_slot,
        "dry_run": dry_run,
        "eligible_count": len(eligible),
        "selected_count": len(picks),
        "snapshot_count": snapshot_count,
        "pool_counts": pool_counts,
        "candidates": [
            {
                "rank": row["rank"],
                "code": normalize_stock_code(row["code"]),
                "pool_code": row["pool_code"],
                "primary_mapping_id": row.get("primary_mapping_id"),
                "benefit_score": row.get("benefit_score"),
                "opportunity_score": row.get("opportunity_score"),
                "evidence_level": row.get("evidence_level"),
            }
            for row in picks
        ],
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Register supply-chain research selection V2 snapshots"
    )
    parser.add_argument("--pg-url", default=DEFAULT_DSN)
    parser.add_argument("--trade-date", required=True)
    parser.add_argument("--time-slot", default="close")
    parser.add_argument("--top-a", type=int, default=20)
    parser.add_argument("--top-b", type=int, default=20)
    parser.add_argument("--top-c", type=int, default=20)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    result = register_and_snapshot(
        pg_url=args.pg_url,
        trade_date=args.trade_date,
        time_slot=args.time_slot,
        top_a=args.top_a,
        top_b=args.top_b,
        top_c=args.top_c,
        dry_run=args.dry_run,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
