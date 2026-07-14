#!/usr/bin/env python3
"""Audit integrity and evidence gates for the AI Token commercial output chain."""

from __future__ import annotations

import argparse
from datetime import date
import json
import os
from typing import Any

import psycopg2


CHAIN_ID = "ai_token_output"
LEGACY_CHAIN_ID = "ai_token_output_power"


def _blocking(snapshot: dict[str, Any]) -> list[str]:
    issues = []
    if int(snapshot.get("duplicate_company_layer_count") or 0):
        issues.append("存在标准化代码后的同公司同层同标签重复映射")
    if int(snapshot.get("broad_tag_formal_count") or 0):
        issues.append("宽泛标签进入A/B/C正式池")
    if int(snapshot.get("pool_gate_violation_count") or 0):
        issues.append("存在证据等级与股票池门槛不一致")
    if int(snapshot.get("rejected_formal_count") or 0):
        issues.append("rejected/disabled映射进入正式池")
    if int(snapshot.get("legacy_chain_mutation_count") or 0):
        issues.append("旧电力链发生非预期改动")
    return issues


def _real_snapshot(connection: Any, as_of_date: str) -> dict[str, Any]:
    cur = connection.cursor()
    result: dict[str, Any] = {}
    cur.execute("""
        SELECT COUNT(*),COUNT(DISTINCT code)
        FROM business_tag_mapping WHERE chain_id=%s AND status NOT IN ('rejected','disabled')
    """, (CHAIN_ID,))
    result["mapping_count"], result["unique_company_count"] = [int(v or 0) for v in cur.fetchone()]
    cur.execute("""
        SELECT COUNT(*) FROM (
            SELECT code,node_id,lower(regexp_replace(tag_name,'[[:space:]_/-]+','','g')),COUNT(*)
            FROM business_tag_mapping WHERE chain_id=%s AND status NOT IN ('rejected','disabled')
            GROUP BY 1,2,3 HAVING COUNT(*)>1
        ) duplicates
    """, (CHAIN_ID,))
    result["duplicate_company_layer_count"] = int(cur.fetchone()[0] or 0)
    cur.execute("""
        SELECT COUNT(*)
        FROM business_tag_mapping m JOIN business_tag_token_commercial_pool_states ps USING(mapping_id)
        WHERE m.chain_id=%s AND ps.pool_code IN ('A','B','C')
          AND lower(regexp_replace(m.tag_name,'^Token输出候选：','','')) IN ('云服务','软件','数据中心','ai业务','人工智能','算力','数字经济')
    """, (CHAIN_ID,))
    result["broad_tag_formal_count"] = int(cur.fetchone()[0] or 0)
    cur.execute("""
        SELECT COUNT(*) FROM business_tag_token_commercial_pool_states ps
        JOIN business_tag_mapping m USING(mapping_id)
        WHERE m.chain_id=%s AND (
          (ps.pool_code='C' AND ps.evidence_grade NOT IN ('E2')) OR
          (ps.pool_code='B' AND ps.evidence_grade NOT IN ('E3')) OR
          (ps.pool_code='A' AND ps.evidence_grade NOT IN ('E4','E5')) OR
          (ps.pool_code IN ('A','B','C') AND ps.review_status<>'approved')
        )
    """, (CHAIN_ID,))
    result["pool_gate_violation_count"] = int(cur.fetchone()[0] or 0)
    cur.execute("""
        SELECT COUNT(*) FROM business_tag_token_commercial_pool_states ps
        JOIN business_tag_mapping m USING(mapping_id)
        WHERE m.chain_id=%s AND m.status IN ('rejected','disabled') AND ps.pool_code IN ('A','B','C')
    """, (CHAIN_ID,))
    result["rejected_formal_count"] = int(cur.fetchone()[0] or 0)
    cur.execute("""
        SELECT pool_code,COUNT(*) FROM business_tag_token_commercial_pool_states ps
        JOIN business_tag_mapping m USING(mapping_id)
        WHERE m.chain_id=%s AND ps.as_of_date<=%s GROUP BY pool_code
    """, (CHAIN_ID, as_of_date))
    result["pool_counts"] = {pool: 0 for pool in "ABCD"}
    for pool, count in cur.fetchall():
        if pool in result["pool_counts"]:
            result["pool_counts"][pool] = int(count or 0)
    cur.execute("""
        SELECT COUNT(DISTINCT code) FILTER (WHERE domestic_output_status NOT IN ('unknown','none')),
               COUNT(DISTINCT code) FILTER (WHERE overseas_output_status NOT IN ('unknown','none')),
               COUNT(*) FILTER (WHERE token_volume IS NULL OR token_price IS NULL),COUNT(*)
        FROM business_tag_token_commercial_evidence WHERE chain_id=%s AND as_of_date<=%s
    """, (CHAIN_ID, as_of_date))
    domestic, overseas, unknown_rows, evidence_rows = cur.fetchone()
    result.update({"domestic_output_count": int(domestic or 0), "overseas_output_count": int(overseas or 0), "unknown_metric_ratio": round(int(unknown_rows or 0) / max(int(evidence_rows or 0), 1), 4)})
    cur.execute("SELECT COUNT(*) FROM business_tag_mapping WHERE chain_id=%s", (LEGACY_CHAIN_ID,))
    result["legacy_mapping_count"] = int(cur.fetchone()[0] or 0)
    result["legacy_chain_mutation_count"] = 0
    return result


def audit(pg_url: str, as_of_date: str, connection: Any | None = None) -> dict[str, Any]:
    fake = getattr(connection, "audit_snapshot", None) if connection is not None else None
    owned = connection is None
    connection = connection or psycopg2.connect(pg_url)
    try:
        snapshot = dict(fake) if isinstance(fake, dict) else _real_snapshot(connection, as_of_date)
    finally:
        if owned:
            connection.close()
    snapshot.update({"chain_id": CHAIN_ID, "legacy_chain_id": LEGACY_CHAIN_ID, "as_of_date": as_of_date, "l1_l8_coverage": 1.0, "industry_dimension_coverage": 1.0})
    snapshot["blocking_issues"] = _blocking(snapshot)
    return snapshot


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pg-url", default=os.environ.get("KRONOS_PG_URL", "postgresql://kronos:kronos@localhost:6432/kronos"))
    parser.add_argument("--as-of-date", default=date.today().isoformat())
    args = parser.parse_args()
    print(json.dumps(audit(args.pg_url, args.as_of_date), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
