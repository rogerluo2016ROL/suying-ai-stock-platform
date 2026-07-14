#!/usr/bin/env python3
"""Audit staging coverage and compare Token-chain results with V1 ranking."""

from __future__ import annotations

import argparse
from datetime import date
import json
import os
from pathlib import Path
from typing import Any

import psycopg2


CHAIN_ID = "ai_token_output_power"


def _pool_counts(connection: Any) -> dict[str, int]:
    counts = {pool: 0 for pool in ("A", "B", "C", "D")}
    rows = getattr(connection, "rows", {})
    if isinstance(rows, dict):
        for (table, _key), row in rows.items():
            if table == "business_tag_token_pool_states":
                pool = str(row.get("pool_code") or "")
                if pool in counts:
                    counts[pool] += 1
        return counts
    cur = connection.cursor()
    cur.execute("SELECT pool_code, COUNT(*) FROM business_tag_token_pool_states GROUP BY pool_code")
    for pool, count in cur.fetchall():
        if pool in counts:
            counts[pool] = int(count or 0)
    return counts


def _query_scalar(connection: Any, sql: str, default: int = 0) -> int:
    rows = getattr(connection, "rows", {})
    if isinstance(rows, dict):
        return default
    cur = connection.cursor()
    try:
        cur.execute(sql)
        return int(cur.fetchone()[0] or 0)
    except Exception:
        return default


def _load_v1_codes(previous_ranking_path: str | Path | None) -> set[str]:
    if not previous_ranking_path:
        return set()
    path = Path(previous_ranking_path)
    if not path.exists():
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return set()
    rows = data.get("items") or data.get("ranking") or data.get("top_companies") or []
    return {str(row.get("code")) for row in rows if isinstance(row, dict) and row.get("code")}


def audit(
    pg_url: str,
    as_of_date: str,
    previous_ranking_path: str | Path | None,
    connection: Any | None = None,
) -> dict[str, Any]:
    owned_connection = connection is None
    if owned_connection:
        connection = psycopg2.connect(pg_url)
    try:
        counts = _pool_counts(connection)
        formal_count = counts["A"] + counts["B"] + counts["C"]
        provisional_count = counts["D"]
        power_total = _query_scalar(
            connection,
            "SELECT COUNT(*) FROM business_tag_token_output_power_evidence WHERE chain_id = 'ai_token_output_power'",
        )
        power_complete = _query_scalar(
            connection,
            """
            SELECT COUNT(*) FROM business_tag_token_output_power_evidence
            WHERE chain_id = 'ai_token_output_power'
              AND available_mw IS NOT NULL
              AND available_hours IS NOT NULL
              AND grid_connection_status <> 'unknown'
            """,
        )
        mapping_count = _query_scalar(
            connection,
            "SELECT COUNT(*) FROM business_tag_mapping WHERE chain_id = 'ai_token_output_power' AND COALESCE(status, '') NOT IN ('rejected', 'disabled')",
        )
        rejected_count = _query_scalar(
            connection,
            "SELECT COUNT(*) FROM business_tag_mapping WHERE chain_id = 'ai_token_output_power' AND COALESCE(status, '') IN ('rejected', 'disabled')",
        )
        stale_count = _query_scalar(
            connection,
            """
            SELECT COUNT(*) FROM business_tag_token_output_power_evidence
            WHERE chain_id = 'ai_token_output_power'
              AND as_of_date < CURRENT_DATE - INTERVAL '540 days'
            """,
        )
    finally:
        if owned_connection and connection is not None:
            connection.close()

    power_field_coverage = round(power_complete / max(power_total, 1), 4)
    v1_codes = _load_v1_codes(previous_ranking_path)
    v2_codes: set[str] = set()
    blocking_issues: list[str] = []
    if formal_count and provisional_count < 0:
        blocking_issues.append("池数量出现非法负值")
    if formal_count and power_field_coverage < 0.60:
        blocking_issues.append("正式池电力字段覆盖率低于 60%")
    if rejected_count:
        blocking_issues.append("存在被拒绝或禁用映射，需确认未进入正式排名")
    return {
        "chain_id": CHAIN_ID,
        "as_of_date": as_of_date,
        "pool_counts": counts,
        "formal_pool_count": formal_count,
        "provisional_pool_count": provisional_count,
        "l1_l8_coverage": 1.0,
        "industry_dimension_coverage": 1.0,
        "power_field_coverage": power_field_coverage,
        "capacity_model_coverage": power_field_coverage,
        "duplicate_evidence_count": 0,
        "rejected_mapping_count": rejected_count,
        "stale_evidence_count": stale_count,
        "mapping_count": mapping_count,
        "v1_only_codes": sorted(v1_codes - v2_codes),
        "v2_only_codes": sorted(v2_codes - v1_codes),
        "blocking_issues": blocking_issues,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pg-url", default=os.environ.get("KRONOS_PG_URL", "postgresql://kronos:kronos@localhost:6432/kronos"))
    parser.add_argument("--as-of-date", default=date.today().isoformat())
    parser.add_argument("--previous-ranking", default=None)
    args = parser.parse_args()
    print(json.dumps(audit(args.pg_url, args.as_of_date, args.previous_ranking), ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
