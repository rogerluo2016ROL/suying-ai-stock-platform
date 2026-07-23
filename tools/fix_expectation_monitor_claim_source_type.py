#!/usr/bin/env python3
"""修复 business_tag_expectation_monitor.claim_source_type 存量脏数据。

背景:supply_chain_evidence_pipeline.build_expectation_monitor_record 曾把
fact.source_level(strong/mid/weak)误写入 claim_source_type。本脚本按
source_doc_id 关联 raw_evidence_documents.source_id 分桶改回正确口径:

- broker_expectation / broker_expectation_local / broker_report -> broker_report
- financial_news_authoritative -> financial_news
- legacy_mid_evidence_event -> exchange_interaction
- 剩余行 metadata->>'fact_nature' = 'media_report' -> financial_news
- 其余兜底 -> other

只动 claim_source_type IN ('mid','weak','strong') 的行,不改 review_status,
因此无需 SET app.supply_chain_review_action GUC。默认 dry-run,--apply 才执行。
"""

from __future__ import annotations

import argparse
import json
import os

import psycopg2

BROKEN_TYPES = ("mid", "weak", "strong")

# (步骤名, 目标 claim_source_type, 匹配条件 SQL, 参数)
STEPS = [
    (
        "broker source_id -> broker_report",
        "broker_report",
        "d.source_id IN ('broker_expectation', 'broker_expectation_local', 'broker_report')",
        (),
    ),
    (
        "news source_id -> financial_news",
        "financial_news",
        "d.source_id IN ('financial_news_authoritative')",
        (),
    ),
    (
        "legacy_mid source_id -> exchange_interaction",
        "exchange_interaction",
        "d.source_id IN ('legacy_mid_evidence_event')",
        (),
    ),
    (
        "metadata fact_nature=media_report -> financial_news",
        "financial_news",
        "m.metadata->>'fact_nature' = 'media_report'",
        (),
    ),
    (
        "fallback -> other",
        "other",
        "TRUE",
        (),
    ),
]

_FROM_JOIN = """
    FROM business_tag_expectation_monitor m
    LEFT JOIN raw_evidence_documents d ON d.doc_id = m.source_doc_id
"""


def fix_claim_source_type(pg_url: str, *, apply: bool) -> dict:
    summary = {"apply": apply, "steps": []}
    with psycopg2.connect(pg_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT coalesce(claim_source_type, 'NULL'), count(*)
                FROM business_tag_expectation_monitor
                GROUP BY 1 ORDER BY 2 DESC
                """
            )
            summary["before"] = {str(row[0]): int(row[1]) for row in cur.fetchall()}
            print(f"[before] {json.dumps(summary['before'], ensure_ascii=False)}")

            for name, target, condition, params in STEPS:
                count_sql = (
                    "SELECT count(*) " + _FROM_JOIN
                    + " WHERE m.claim_source_type IN %s AND " + condition
                )
                cur.execute(count_sql, (BROKEN_TYPES, *params))
                matched = int(cur.fetchone()[0])
                updated = 0
                if apply and matched:
                    # condition 里 d.* 指向 FROM 子查询,m.* 指目标表
                    update_sql = (
                        "UPDATE business_tag_expectation_monitor AS m"
                        " SET claim_source_type = %s, updated_at = CURRENT_TIMESTAMP"
                        " FROM (SELECT doc_id, source_id FROM raw_evidence_documents) AS d"
                        " WHERE d.doc_id = m.source_doc_id"
                        " AND m.claim_source_type IN %s AND " + condition
                    )
                    cur.execute(update_sql, (target, BROKEN_TYPES, *params))
                    updated = cur.rowcount
                    conn.commit()
                step = {"step": name, "target": target, "matched": matched, "updated": updated}
                summary["steps"].append(step)
                print(f"[step] {name}: matched={matched} updated={updated}")

            cur.execute(
                """
                SELECT coalesce(claim_source_type, 'NULL'), count(*)
                FROM business_tag_expectation_monitor
                GROUP BY 1 ORDER BY 2 DESC
                """
            )
            summary["after"] = {str(row[0]): int(row[1]) for row in cur.fetchall()}
            print(f"[after] {json.dumps(summary['after'], ensure_ascii=False)}")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pg-url", default=os.environ.get("KRONOS_PG_URL", "postgresql://kronos:kronos@localhost:6432/kronos"))
    parser.add_argument("--apply", action="store_true", help="实际执行 UPDATE(默认 dry-run)")
    args = parser.parse_args()
    summary = fix_claim_source_type(args.pg_url, apply=args.apply)
    if not args.apply:
        print("[dry-run] 未写入;加 --apply 执行")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
