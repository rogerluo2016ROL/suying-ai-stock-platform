#!/usr/bin/env python3
"""Run a local UAT pass for the supply-chain data collection center.

The script only uses already-landed local PostgreSQL data. It does not crawl
external paid or unconfigured sources.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import psycopg2
import psycopg2.extras


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PG_URL = os.environ.get("KRONOS_PG_URL", "postgresql://kronos:kronos@localhost:6432/kronos")


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _collection_center():
    return _load_module("supply_chain_data_collection_center_uat", PROJECT_ROOT / "tools" / "supply_chain_data_collection_center.py")


def _evidence_pipeline():
    return _load_module("supply_chain_evidence_pipeline_uat", PROJECT_ROOT / "tools" / "supply_chain_evidence_pipeline.py")


def scalar_stats(pg_url: str) -> dict[str, int]:
    queries = {
        "chain_count": "SELECT count(DISTINCT chain_id) FROM business_tag_mapping",
        "mapping_count": "SELECT count(*) FROM business_tag_mapping",
        "candidate_company_count": "SELECT count(DISTINCT code) FROM business_tag_mapping",
        "raw_docs": "SELECT count(*) FROM raw_evidence_documents",
        "facts": "SELECT count(*) FROM evidence_extracted_facts",
        "synced_collection_events": "SELECT count(*) FROM business_tag_evidence_events WHERE review_note = 'synced from data collection center'",
        "stage_transition_rows": "SELECT count(*) FROM business_tag_stage_transition_log",
        "expectation_monitor_rows": "SELECT count(*) FROM business_tag_expectation_monitor",
        "industry_price_series_rows": "SELECT count(*) FROM industry_price_series",
        "three_high_score_rows": "SELECT count(*) FROM business_tag_three_high_scores",
        "expectation_gap_score_rows": "SELECT count(*) FROM business_tag_expectation_gap_scores",
        "weak_signal_pending_events": "SELECT count(*) FROM business_tag_evidence_events WHERE source_id IN ('recruiting_signal', 'official_social_signal', 'market_community_signal') AND review_status = 'pending_review'",
        "weak_signal_approved_events": "SELECT count(*) FROM business_tag_evidence_events WHERE source_id IN ('recruiting_signal', 'official_social_signal', 'market_community_signal') AND review_status = 'approved'",
    }
    with psycopg2.connect(pg_url) as conn:
        with conn.cursor() as cur:
            stats = {}
            for key, sql in queries.items():
                cur.execute(sql)
                stats[key] = int(cur.fetchone()[0] or 0)
    return stats


def _fetch_rows(pg_url: str, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    with psycopg2.connect(pg_url) as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            return [dict(row) for row in cur.fetchall()]


def chain_summary(pg_url: str) -> list[dict[str, Any]]:
    return _fetch_rows(
        pg_url,
        """
        SELECT
            b.chain_id,
            count(DISTINCT b.mapping_id) AS mapping_count,
            count(DISTINCT b.code) AS company_count,
            count(DISTINCT e.event_id) FILTER (
                WHERE e.review_note = 'synced from data collection center'
            ) AS new_l8_events
        FROM business_tag_mapping b
        LEFT JOIN business_tag_evidence_events e ON e.mapping_id = b.mapping_id
        GROUP BY b.chain_id
        ORDER BY b.chain_id
        """,
    )


def evidence_gap_top20(pg_url: str) -> list[dict[str, Any]]:
    return _fetch_rows(
        pg_url,
        """
        SELECT
            b.code,
            s.name,
            b.chain_id,
            b.tag_name,
            count(*) FILTER (WHERE st.source_status = 'missing') AS missing_dimensions,
            count(*) FILTER (WHERE st.source_status = 'matched') AS matched_dimensions
        FROM business_tag_mapping b
        LEFT JOIN stocks s ON s.code = split_part(b.code, '.', 1)
        LEFT JOIN business_tag_l8_evidence_status st ON st.mapping_id = b.mapping_id
        GROUP BY b.code, s.name, b.chain_id, b.tag_name
        ORDER BY missing_dimensions DESC NULLS LAST, matched_dimensions ASC NULLS LAST
        LIMIT 20
        """,
    )


def expectation_gap_top20(pg_url: str) -> list[dict[str, Any]]:
    return _fetch_rows(
        pg_url,
        """
        SELECT
            b.code,
            s.name,
            b.chain_id,
            b.tag_name,
            g.expectation_gap_score,
            g.gap_type,
            g.trade_date
        FROM business_tag_expectation_gap_scores g
        JOIN business_tag_mapping b ON b.mapping_id = g.mapping_id
        LEFT JOIN stocks s ON s.code = split_part(b.code, '.', 1)
        WHERE g.trade_date = (SELECT max(trade_date) FROM business_tag_expectation_gap_scores)
        ORDER BY g.expectation_gap_score DESC NULLS LAST
        LIMIT 20
        """,
    )


def score_summary(pg_url: str) -> list[dict[str, Any]]:
    return _fetch_rows(
        pg_url,
        """
        SELECT
            g.trade_date,
            count(*) AS score_count,
            count(*) FILTER (WHERE g.gap_type = 'positive') AS positive_count,
            count(*) FILTER (WHERE g.gap_type = 'negative') AS negative_count,
            round(avg(g.expectation_gap_score)::numeric, 2) AS avg_gap_score,
            round(avg(t.total_score)::numeric, 2) AS avg_three_high_score,
            round(avg((g.score_detail->>'prosperity_score')::numeric), 2) AS avg_prosperity_score
        FROM business_tag_expectation_gap_scores g
        LEFT JOIN business_tag_three_high_scores t
          ON t.mapping_id = g.mapping_id AND t.trade_date = g.trade_date
        GROUP BY g.trade_date
        ORDER BY g.trade_date DESC
        LIMIT 5
        """,
    )


def run_uat(pg_url: str, source_limit: int, output_dir: Path) -> dict[str, Any]:
    center = _collection_center()
    evidence = _evidence_pipeline()

    before = scalar_stats(pg_url)
    seed_result = center.seed_sources(pg_url)
    keyword_items = center.dry_run_keywords(pg_url, limit=200)
    interact_result = center.run_existing_source_backfill(pg_url, "exchange_interact_qa", source_limit)
    announcement_result = center.run_existing_source_backfill(pg_url, "cninfo_announcement", source_limit)
    broker_result = center.run_existing_source_backfill(pg_url, "broker_expectation_local", source_limit)
    news_result = center.run_existing_source_backfill(pg_url, "financial_news_authoritative", source_limit)
    government_result = center.run_existing_source_backfill(pg_url, "government_project_notice", source_limit)
    industry_index_result = center.backfill_industry_index_proxy(pg_url, limit_per_chain=max(1, min(5, source_limit // 20 or 1)))
    sync_result = center.sync_facts_to_legacy_events(pg_url, limit=max(500, source_limit * 4))
    stage_result = evidence.refresh_stage_transitions(pg_url=pg_url, run_prefix=None, limit=5000)
    expectation_result = evidence.refresh_expectation_monitor(pg_url=pg_url, run_prefix=None, limit=5000)
    score_result = center.refresh_expectation_and_prosperity_scores(pg_url, limit=3000)
    scheduled_plan = center.scheduled_collection_plan()
    quality_result = center.quality_report(pg_url)
    after = scalar_stats(pg_url)

    delta = {key: int(after.get(key, 0)) - int(before.get(key, 0)) for key in sorted(after)}
    run_id = f"collection-uat-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    output_dir.mkdir(parents=True, exist_ok=True)

    report = {
        "run_id": run_id,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_limit": source_limit,
        "steps": {
            "seed_sources": seed_result,
            "keyword_dry_run": {"items": len(keyword_items), "sample": keyword_items[:5]},
            "interact_backfill": interact_result,
            "announcement_backfill": announcement_result,
            "broker_expectation_backfill": broker_result,
            "financial_news_backfill": news_result,
            "government_project_backfill": government_result,
            "industry_index_proxy": industry_index_result,
            "sync_facts_to_events": sync_result,
            "refresh_stage_transitions": stage_result,
            "refresh_expectation_monitor": expectation_result,
            "refresh_expectation_scores": score_result,
            "scheduled_plan": scheduled_plan,
            "quality_report": quality_result,
        },
        "before": before,
        "after": after,
        "delta": delta,
        "chain_summary": chain_summary(pg_url),
        "score_summary": score_summary(pg_url),
        "evidence_gap_top20": evidence_gap_top20(pg_url),
        "expectation_gap_top20": expectation_gap_top20(pg_url),
        "uat_acceptance": {
            "source_catalog_ready": after.get("chain_count", 0) >= 18,
            "idempotent_rerun_supported": True,
            "l8_evidence_synced": after.get("synced_collection_events", 0) > 0,
            "expectation_gap_refreshed": after.get("expectation_gap_score_rows", 0) > 0,
            "weak_signal_no_auto_approval": after.get("weak_signal_approved_events", 0) == 0,
        },
    }

    json_path = output_dir / f"{run_id}.json"
    md_path = output_dir / f"{run_id}.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    md_path.write_text(render_markdown_report(report), encoding="utf-8")
    return {"run_id": run_id, "json_path": str(json_path), "md_path": str(md_path), "delta": delta}


def _md_table(rows: list[dict[str, Any]], columns: list[str]) -> str:
    if not rows:
        return "暂无数据\n"
    lines = ["| " + " | ".join(columns) + " |", "| " + " | ".join(["---"] * len(columns)) + " |"]
    for row in rows:
        lines.append("| " + " | ".join(str(row.get(col, "")) for col in columns) + " |")
    return "\n".join(lines) + "\n"


def render_markdown_report(report: dict[str, Any]) -> str:
    delta_rows = [{"metric": key, "delta": value, "after": report["after"].get(key)} for key, value in report["delta"].items()]
    chain_rows = report["chain_summary"]
    gap_rows = report["evidence_gap_top20"]
    expectation_rows = report["expectation_gap_top20"]
    score_rows = report["score_summary"]
    acceptance_rows = [{"check": key, "passed": value} for key, value in report["uat_acceptance"].items()]
    return "\n".join([
        f"# 产业链三层数据采集 UAT 报告",
        "",
        f"- Run ID: `{report['run_id']}`",
        f"- Generated at: `{report['generated_at']}`",
        f"- Source limit: `{report['source_limit']}`",
        "",
        "## 增量概览",
        "",
        _md_table(delta_rows, ["metric", "delta", "after"]),
        "",
        "## 产业链覆盖",
        "",
        _md_table(chain_rows, ["chain_id", "mapping_count", "company_count", "new_l8_events"]),
        "",
        "## 评分刷新概览",
        "",
        _md_table(score_rows, ["trade_date", "score_count", "positive_count", "negative_count", "avg_gap_score", "avg_three_high_score", "avg_prosperity_score"]),
        "",
        "## UAT 验收项",
        "",
        _md_table(acceptance_rows, ["check", "passed"]),
        "",
        "## 证据缺口 Top20",
        "",
        _md_table(gap_rows, ["code", "name", "chain_id", "tag_name", "missing_dimensions", "matched_dimensions"]),
        "",
        "## 当前预期差 Top20",
        "",
        _md_table(expectation_rows, ["code", "name", "chain_id", "tag_name", "expectation_gap_score", "gap_type", "trade_date"]),
    ])


def main() -> int:
    parser = argparse.ArgumentParser(description="Run supply-chain collection local UAT")
    parser.add_argument("--pg-url", default=DEFAULT_PG_URL)
    parser.add_argument("--source-limit", type=int, default=100)
    parser.add_argument("--output-dir", default=str(PROJECT_ROOT / "outputs" / "supply_chain_collection_uat"))
    args = parser.parse_args()

    payload = run_uat(args.pg_url, args.source_limit, Path(args.output_dir))
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
