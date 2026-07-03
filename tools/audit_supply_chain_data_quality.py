#!/usr/bin/env python3
"""Audit 18-chain business-tag evidence quality from PostgreSQL."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

import psycopg2
import psycopg2.extras


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PG_URL = os.environ.get("KRONOS_PG_URL", "postgresql://kronos:kronos@localhost:6432/kronos")
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "outputs" / "supply_chain_quality_audit_20260703"


def _ratio(numerator: float, denominator: float) -> float:
    return float(numerator or 0) / float(denominator or 1)


def _capped_score(value: float, target: float, weight: float) -> float:
    if target <= 0:
        return 0.0
    return min(max(value / target, 0.0), 1.0) * weight


def score_chain_quality(raw: dict[str, Any]) -> dict[str, Any]:
    mapping_count = int(raw.get("mapping_count") or 0)
    company_count = int(raw.get("company_count") or 0)
    fact_count = int(raw.get("fact_count") or 0)
    l8_status_count = int(raw.get("l8_status_count") or 0)
    stage_count = int(raw.get("stage_count") or 0)
    score_count = int(raw.get("score_count") or 0)
    fresh_count = int(raw.get("fresh_count") or 0)
    stale_count = int(raw.get("stale_count") or 0)
    expired_count = int(raw.get("expired_count") or 0)
    unknown_count = int(raw.get("unknown_count") or 0)

    facts_per_mapping = _ratio(fact_count, mapping_count)
    l8_per_mapping = _ratio(l8_status_count, mapping_count)
    stage_coverage = _ratio(stage_count, mapping_count)
    score_coverage = _ratio(score_count, mapping_count)
    freshness_coverage = _ratio(fresh_count, mapping_count)
    weak_freshness_ratio = _ratio(stale_count + expired_count + unknown_count, mapping_count)

    parts = {
        "mapping_depth": _capped_score(mapping_count, 30, 20),
        "company_breadth": _capped_score(company_count, 20, 10),
        "structured_evidence": _capped_score(facts_per_mapping, 5, 25),
        "l8_coverage": _capped_score(l8_per_mapping, 8, 20),
        "stage_coverage": _capped_score(stage_coverage, 1, 10),
        "score_coverage": _capped_score(score_coverage, 1, 5),
        "freshness": _capped_score(freshness_coverage, 0.9, 10),
    }
    quality_score = round(sum(parts.values()), 2)
    if quality_score >= 85:
        grade = "A"
    elif quality_score >= 70:
        grade = "B"
    elif quality_score >= 55:
        grade = "C"
    else:
        grade = "D"

    actions: list[str] = []
    if mapping_count < 10:
        actions.append("补公司/标签映射")
    if facts_per_mapping < 3:
        actions.append("补结构化证据")
    if l8_per_mapping < 6:
        actions.append("补 L8 级证据状态")
    if stage_coverage < 0.8:
        actions.append("补研发/商用阶段证据")
    if weak_freshness_ratio > 0.1:
        actions.append("刷新过期/未知证据")
    if not actions:
        actions.append("保持日更跟踪")

    if grade == "D" or facts_per_mapping < 2 or weak_freshness_ratio > 0.3:
        risk_level = "high"
    elif grade == "C" or weak_freshness_ratio > 0.1:
        risk_level = "medium"
    else:
        risk_level = "low"

    row = dict(raw)
    row.update({
        "facts_per_mapping": round(facts_per_mapping, 2),
        "l8_per_mapping": round(l8_per_mapping, 2),
        "stage_coverage": round(stage_coverage, 4),
        "score_coverage": round(score_coverage, 4),
        "freshness_coverage": round(freshness_coverage, 4),
        "weak_freshness_ratio": round(weak_freshness_ratio, 4),
        "quality_score": quality_score,
        "quality_grade": grade,
        "risk_level": risk_level,
        "priority_actions": actions,
        "score_parts": {key: round(value, 2) for key, value in parts.items()},
    })
    return row


def rank_chains_for_repair(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    risk_rank = {"high": 0, "medium": 1, "low": 2}
    ranked = sorted(
        rows,
        key=lambda item: (
            risk_rank.get(str(item.get("risk_level")), 9),
            float(item.get("quality_score") or 0),
            int(item.get("mapping_count") or 0),
        ),
    )
    for index, row in enumerate(ranked, 1):
        row["repair_priority"] = index
    return ranked


def fetch_chain_quality_raw(pg_url: str) -> list[dict[str, Any]]:
    sql = """
    WITH base AS (
        SELECT chain_id, mapping_id, code
        FROM business_tag_mapping
    ),
    mapping_stats AS (
        SELECT chain_id, count(*) AS mapping_count, count(DISTINCT code) AS company_count
        FROM base
        GROUP BY chain_id
    ),
    event_stats AS (
        SELECT b.chain_id, count(DISTINCT e.event_id) AS evidence_event_count
        FROM base b
        LEFT JOIN business_tag_evidence_events e ON e.mapping_id = b.mapping_id
        GROUP BY b.chain_id
    ),
    fact_stats AS (
        SELECT chain_id, count(DISTINCT fact_id) AS fact_count
        FROM evidence_extracted_facts
        GROUP BY chain_id
    ),
    l8_stats AS (
        SELECT b.chain_id, count(DISTINCT l.status_id) AS l8_status_count
        FROM base b
        LEFT JOIN business_tag_l8_evidence_status l ON l.mapping_id = b.mapping_id
        GROUP BY b.chain_id
    ),
    freshness_stats AS (
        SELECT
            b.chain_id,
            count(*) FILTER (WHERE f.freshness_status = 'fresh') AS fresh_count,
            count(*) FILTER (WHERE f.freshness_status = 'stale') AS stale_count,
            count(*) FILTER (WHERE f.freshness_status = 'expired') AS expired_count,
            count(*) FILTER (WHERE f.freshness_status = 'unknown' OR f.freshness_status IS NULL) AS unknown_count
        FROM base b
        LEFT JOIN business_tag_evidence_freshness f ON f.mapping_id = b.mapping_id
        GROUP BY b.chain_id
    ),
    stage_stats AS (
        SELECT b.chain_id, count(DISTINCT s.stage_id) AS stage_count
        FROM base b
        LEFT JOIN business_tag_stage_tracking s ON s.mapping_id = b.mapping_id
        GROUP BY b.chain_id
    ),
    score_stats AS (
        SELECT b.chain_id, count(DISTINCT s.score_id) AS score_count
        FROM base b
        LEFT JOIN business_tag_three_high_scores s ON s.mapping_id = b.mapping_id
        GROUP BY b.chain_id
    ),
    gap_stats AS (
        SELECT b.chain_id, count(DISTINCT g.gap_id) AS gap_count
        FROM base b
        LEFT JOIN business_tag_expectation_gap_scores g ON g.mapping_id = b.mapping_id
        GROUP BY b.chain_id
    )
    SELECT
        m.chain_id,
        m.mapping_count,
        m.company_count,
        COALESCE(e.evidence_event_count, 0) AS evidence_event_count,
        COALESCE(f.fact_count, 0) AS fact_count,
        COALESCE(l.l8_status_count, 0) AS l8_status_count,
        COALESCE(fr.fresh_count, 0) AS fresh_count,
        COALESCE(fr.stale_count, 0) AS stale_count,
        COALESCE(fr.expired_count, 0) AS expired_count,
        COALESCE(fr.unknown_count, 0) AS unknown_count,
        COALESCE(st.stage_count, 0) AS stage_count,
        COALESCE(sc.score_count, 0) AS score_count,
        COALESCE(g.gap_count, 0) AS gap_count
    FROM mapping_stats m
    LEFT JOIN event_stats e ON e.chain_id = m.chain_id
    LEFT JOIN fact_stats f ON f.chain_id = m.chain_id
    LEFT JOIN l8_stats l ON l.chain_id = m.chain_id
    LEFT JOIN freshness_stats fr ON fr.chain_id = m.chain_id
    LEFT JOIN stage_stats st ON st.chain_id = m.chain_id
    LEFT JOIN score_stats sc ON sc.chain_id = m.chain_id
    LEFT JOIN gap_stats g ON g.chain_id = m.chain_id
    ORDER BY m.chain_id
    """
    with psycopg2.connect(pg_url) as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql)
            return [dict(row) for row in cur.fetchall()]


def build_audit(pg_url: str) -> dict[str, Any]:
    raw_rows = fetch_chain_quality_raw(pg_url)
    rows = rank_chains_for_repair([score_chain_quality(row) for row in raw_rows])
    summary = {
        "chain_count": len(rows),
        "high_risk_chains": sum(1 for row in rows if row["risk_level"] == "high"),
        "medium_risk_chains": sum(1 for row in rows if row["risk_level"] == "medium"),
        "low_risk_chains": sum(1 for row in rows if row["risk_level"] == "low"),
        "avg_quality_score": round(sum(float(row["quality_score"]) for row in rows) / max(len(rows), 1), 2),
        "top_repair_chains": [row["chain_id"] for row in rows[:5]],
    }
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "summary": summary,
        "chains": rows,
    }


def write_json_report(audit: dict[str, Any], output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"chain_quality_audit_{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    path.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def write_markdown_report(audit: dict[str, Any], output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"chain_quality_audit_{datetime.now().strftime('%Y%m%d-%H%M%S')}.md"
    lines = [
        "# 18 条产业链数据质量体检报告",
        "",
        f"生成时间：{audit['generated_at']}",
        "",
        "## 总览",
        "",
        "| 指标 | 数值 |",
        "|---|---:|",
        f"| 产业链数量 | {audit['summary']['chain_count']} |",
        f"| 高风险链 | {audit['summary']['high_risk_chains']} |",
        f"| 中风险链 | {audit['summary']['medium_risk_chains']} |",
        f"| 低风险链 | {audit['summary']['low_risk_chains']} |",
        f"| 平均质量分 | {audit['summary']['avg_quality_score']} |",
        "",
        "## 补数优先级",
        "",
        "| 优先级 | chain_id | 风险 | 质量分 | 映射 | 公司 | 事实/映射 | L8/映射 | 新鲜度 | 建议动作 |",
        "|---:|---|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in audit["chains"]:
        actions = "；".join(row["priority_actions"])
        lines.append(
            f"| {row['repair_priority']} | {row['chain_id']} | {row['risk_level']} | "
            f"{row['quality_score']} | {row['mapping_count']} | {row['company_count']} | "
            f"{row['facts_per_mapping']} | {row['l8_per_mapping']} | "
            f"{round(row['freshness_coverage'] * 100, 1)}% | {actions} |"
        )
    lines.extend([
        "",
        "## 口径说明",
        "",
        "- 质量分由映射深度、公司覆盖、结构化证据、L8 覆盖、阶段覆盖、三高评分覆盖和新鲜度组成。",
        "- 高风险不代表公司不好，只代表该产业链的数据底座不足，排序和推荐前需要先补证据。",
        "- 财报、公告、互动问答、研报等证据只使用已落库数据，不用静态页面或模型编造补齐。",
        "",
    ])
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit 18-chain evidence data quality")
    parser.add_argument("--pg-url", default=DEFAULT_PG_URL)
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    args = parser.parse_args()

    audit = build_audit(args.pg_url)
    output_dir = Path(args.output_dir)
    json_path = write_json_report(audit, output_dir)
    md_path = write_markdown_report(audit, output_dir)
    print(json.dumps({
        "accepted": audit["summary"]["chain_count"] >= 18,
        "json_path": str(json_path),
        "markdown_path": str(md_path),
        "summary": audit["summary"],
    }, ensure_ascii=False, indent=2))
    return 0 if audit["summary"]["chain_count"] >= 18 else 1


if __name__ == "__main__":
    raise SystemExit(main())
