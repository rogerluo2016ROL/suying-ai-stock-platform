#!/usr/bin/env python3
"""Build a company-level ranking from supply-chain business-tag evidence."""

from __future__ import annotations

import argparse
import csv
import json
import os
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Any

import psycopg2
import psycopg2.extras


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PG_URL = os.environ.get("KRONOS_PG_URL", "postgresql://kronos:kronos@localhost:6432/kronos")
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "outputs" / "supply_chain_candidate_ranking_20260703"


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, float(value or 0)))


def normalize_expectation_gap(value: float | None) -> float:
    # Gap scores are centered around 0. Positive means actual evidence is
    # stronger than market expectation; map -100..100 into 0..100.
    return clamp((float(value or 0) + 100.0) / 2.0)


def normalize_momentum(change_20d_pct: float | None) -> float:
    # Keep price action as a small helper only. -20% => 0, +40% => 100.
    return clamp((float(change_20d_pct or 0) + 20.0) / 60.0 * 100.0)


def score_candidate(row: dict[str, Any]) -> dict[str, Any]:
    three_high = clamp(row.get("three_high_total"))
    moat = clamp(row.get("moat_score"))
    stage = clamp(row.get("stage_score"))
    evidence = clamp(row.get("evidence_score"))
    l8 = clamp(float(row.get("l8_match_rate") or 0) * 100.0)
    fresh = clamp(float(row.get("fresh_rate") or 0) * 100.0)
    gap = normalize_expectation_gap(row.get("expectation_gap_score"))
    momentum = normalize_momentum(row.get("change_20d_pct"))
    rank_score = round(
        three_high * 0.35
        + moat * 0.15
        + stage * 0.12
        + evidence * 0.12
        + l8 * 0.10
        + fresh * 0.08
        + gap * 0.06
        + momentum * 0.02,
        2,
    )
    if rank_score >= 80 and fresh >= 70 and l8 >= 50:
        signal = "重点候选"
    elif rank_score >= 65:
        signal = "观察"
    else:
        signal = "暂缓"
    payload = dict(row)
    payload.update({
        "rank_score": rank_score,
        "signal": signal,
        "score_parts": {
            "three_high": round(three_high, 2),
            "moat": round(moat, 2),
            "stage": round(stage, 2),
            "evidence": round(evidence, 2),
            "l8": round(l8, 2),
            "freshness": round(fresh, 2),
            "expectation_gap": round(gap, 2),
            "momentum": round(momentum, 2),
        },
    })
    return payload


def aggregate_company_chain(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(str(row.get("chain_id")), str(row.get("code")))].append(row)
    result: list[dict[str, Any]] = []
    for (chain_id, code), items in grouped.items():
        best = max(items, key=lambda item: float(item.get("rank_score") or 0))
        avg_rank = sum(float(item.get("rank_score") or 0) for item in items) / max(len(items), 1)
        result.append({
            "chain_id": chain_id,
            "code": code,
            "name": best.get("name") or "",
            "industry": best.get("industry") or "",
            "tag_count": len({item.get("mapping_id") for item in items}),
            "best_mapping_id": best.get("mapping_id"),
            "best_tag_name": best.get("tag_name"),
            "rank_score": round(float(best.get("rank_score") or 0), 2),
            "avg_rank_score": round(avg_rank, 2),
            "signal": best.get("signal"),
            "three_high_total": round(float(best.get("three_high_total") or 0), 2),
            "growth_score": round(float(best.get("growth_score") or 0), 2),
            "profit_score": round(float(best.get("profit_score") or 0), 2),
            "moat_score": round(float(best.get("moat_score") or 0), 2),
            "stage_score": round(float(best.get("stage_score") or 0), 2),
            "evidence_score": round(float(best.get("evidence_score") or 0), 2),
            "expectation_gap_score": round(float(best.get("expectation_gap_score") or 0), 2),
            "gap_type": best.get("gap_type") or "",
            "l8_match_rate": round(float(best.get("l8_match_rate") or 0), 4),
            "fresh_rate": round(float(best.get("fresh_rate") or 0), 4),
            "fact_count": int(sum(int(item.get("fact_count") or 0) for item in items)),
            "latest_price": best.get("latest_price"),
            "latest_trade_date": str(best.get("latest_trade_date") or ""),
            "change_1d_pct": best.get("change_1d_pct"),
            "change_20d_pct": best.get("change_20d_pct"),
            "mapping_ids": [item.get("mapping_id") for item in sorted(items, key=lambda item: -float(item.get("rank_score") or 0))[:8]],
            "tag_names": [item.get("tag_name") for item in sorted(items, key=lambda item: -float(item.get("rank_score") or 0))[:8]],
        })
    return sorted(result, key=lambda item: (-float(item["rank_score"]), item["chain_id"], item["code"]))


def fetch_mapping_rows(pg_url: str) -> list[dict[str, Any]]:
    sql = """
    WITH mapping_base AS (
        SELECT
            m.mapping_id,
            split_part(m.code, '.', 1) AS code,
            m.chain_id,
            m.node_id,
            m.tag_name,
            m.status AS mapping_status
        FROM business_tag_mapping m
    ),
    latest_score AS (
        SELECT DISTINCT ON (mapping_id)
            mapping_id, trade_date, growth_score, profit_score, moat_score,
            stage_score, evidence_score, total_score
        FROM business_tag_three_high_scores
        ORDER BY mapping_id, trade_date DESC, created_at DESC
    ),
    latest_gap AS (
        SELECT DISTINCT ON (mapping_id)
            mapping_id, expectation_gap_score, gap_type
        FROM business_tag_expectation_gap_scores
        ORDER BY mapping_id, trade_date DESC, created_at DESC
    ),
    latest_stage AS (
        SELECT DISTINCT ON (mapping_id)
            mapping_id, research_stage, commercialization_stage
        FROM business_tag_stage_tracking
        ORDER BY mapping_id, trade_date DESC, created_at DESC
    ),
    l8 AS (
        SELECT
            mapping_id,
            count(*) AS l8_total,
            count(*) FILTER (WHERE source_status = 'matched') AS l8_matched,
            sum(coalesce(evidence_count, 0)) AS l8_evidence_count
        FROM business_tag_l8_evidence_status
        GROUP BY mapping_id
    ),
    facts AS (
        SELECT mapping_id, count(*) AS fact_count
        FROM evidence_extracted_facts
        GROUP BY mapping_id
    ),
    market_latest AS (
        SELECT DISTINCT ON (code)
            code, trade_date AS latest_trade_date, close AS latest_price,
            change_pct AS change_1d_pct
        FROM daily_kline
        ORDER BY code, trade_date DESC
    ),
    market_20d AS (
        SELECT
            code,
            max(close) FILTER (WHERE rn = 1) AS latest_close,
            max(close) FILTER (WHERE rn = 20) AS close_20d
        FROM (
            SELECT code, trade_date, close,
                   row_number() OVER (PARTITION BY code ORDER BY trade_date DESC) AS rn
            FROM daily_kline
        ) x
        WHERE rn IN (1, 20)
        GROUP BY code
    )
    SELECT
        b.mapping_id,
        b.code,
        s.name,
        s.industry,
        b.chain_id,
        b.node_id,
        b.tag_name,
        b.mapping_status,
        coalesce(sc.growth_score, 0) AS growth_score,
        coalesce(sc.profit_score, 0) AS profit_score,
        coalesce(sc.moat_score, 0) AS moat_score,
        coalesce(sc.stage_score, 0) AS stage_score,
        coalesce(sc.evidence_score, 0) AS evidence_score,
        coalesce(sc.total_score, 0) AS three_high_total,
        coalesce(g.expectation_gap_score, 0) AS expectation_gap_score,
        coalesce(g.gap_type, '') AS gap_type,
        coalesce(st.research_stage, '') AS research_stage,
        coalesce(st.commercialization_stage, '') AS commercialization_stage,
        coalesce(l8.l8_total, 0) AS l8_total,
        coalesce(l8.l8_matched, 0) AS l8_matched,
        CASE WHEN coalesce(l8.l8_total, 0) = 0 THEN 0
             ELSE coalesce(l8.l8_matched, 0)::float / l8.l8_total END AS l8_match_rate,
        coalesce(l8.l8_evidence_count, 0) AS l8_evidence_count,
        coalesce(f.fact_count, 0) AS fact_count,
        CASE WHEN fr.freshness_status = 'fresh' THEN 1.0
             WHEN fr.freshness_status = 'stale' THEN 0.6
             WHEN fr.freshness_status = 'expired' THEN 0.2
             ELSE 0.0 END AS fresh_rate,
        coalesce(fr.freshness_status, 'unknown') AS freshness_status,
        ml.latest_trade_date,
        ml.latest_price,
        ml.change_1d_pct,
        CASE WHEN m20.close_20d IS NULL OR m20.close_20d = 0 THEN NULL
             ELSE (m20.latest_close / m20.close_20d - 1) * 100 END AS change_20d_pct
    FROM mapping_base b
    LEFT JOIN stocks s ON s.code = b.code
    LEFT JOIN latest_score sc ON sc.mapping_id = b.mapping_id
    LEFT JOIN latest_gap g ON g.mapping_id = b.mapping_id
    LEFT JOIN latest_stage st ON st.mapping_id = b.mapping_id
    LEFT JOIN l8 ON l8.mapping_id = b.mapping_id
    LEFT JOIN facts f ON f.mapping_id = b.mapping_id
    LEFT JOIN business_tag_evidence_freshness fr ON fr.mapping_id = b.mapping_id
    LEFT JOIN market_latest ml ON ml.code = b.code
    LEFT JOIN market_20d m20 ON m20.code = b.code
    WHERE b.chain_id IS NOT NULL
    """
    with psycopg2.connect(pg_url) as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql)
            return [dict(row) for row in cur.fetchall()]


def build_ranking(pg_url: str, top_n: int = 100) -> dict[str, Any]:
    mapping_rows = [score_candidate(row) for row in fetch_mapping_rows(pg_url)]
    company_chain_rows = aggregate_company_chain(mapping_rows)
    global_top = company_chain_rows[:top_n]
    by_chain: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in company_chain_rows:
        if len(by_chain[row["chain_id"]]) < top_n:
            by_chain[row["chain_id"]].append(row)
    summary = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "mapping_rows": len(mapping_rows),
        "company_chain_rows": len(company_chain_rows),
        "chain_count": len(by_chain),
        "top_n": top_n,
        "signal_distribution": {},
    }
    for row in company_chain_rows:
        summary["signal_distribution"][row["signal"]] = summary["signal_distribution"].get(row["signal"], 0) + 1
    return {
        "summary": summary,
        "global_top": global_top,
        "by_chain": dict(by_chain),
    }


def _json_default(value: Any) -> str:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value)


def write_reports(ranking: dict[str, Any], output_dir: Path) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    json_path = output_dir / f"supply_chain_candidate_ranking_{stamp}.json"
    csv_path = output_dir / f"supply_chain_candidate_ranking_{stamp}.csv"
    md_path = output_dir / f"supply_chain_candidate_ranking_{stamp}.md"

    json_path.write_text(json.dumps(ranking, ensure_ascii=False, indent=2, default=_json_default), encoding="utf-8")

    rows = ranking["global_top"]
    fields = [
        "chain_id", "code", "name", "industry", "rank_score", "signal", "tag_count",
        "best_tag_name", "three_high_total", "growth_score", "profit_score", "moat_score",
        "stage_score", "evidence_score", "expectation_gap_score", "l8_match_rate",
        "fresh_rate", "fact_count", "latest_price", "latest_trade_date", "change_1d_pct",
        "change_20d_pct", "best_mapping_id",
    ]
    with csv_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key) for key in fields})

    lines = [
        "# 18 条产业链候选公司总榜",
        "",
        f"生成时间：{ranking['summary']['generated_at']}",
        "",
        "## 总览",
        "",
        "| 指标 | 数值 |",
        "|---|---:|",
        f"| 标签映射评分行 | {ranking['summary']['mapping_rows']} |",
        f"| 公司-产业链组合 | {ranking['summary']['company_chain_rows']} |",
        f"| 产业链数量 | {ranking['summary']['chain_count']} |",
        "",
        "## 全局 Top 30",
        "",
        "| 排名 | chain_id | 代码 | 名称 | 分数 | 信号 | 标签数 | 最强标签 | 三高 | 围墙 | 阶段 | L8 | 新鲜度 | 20日涨幅 |",
        "|---:|---|---|---|---:|---|---:|---|---:|---:|---:|---:|---:|---:|",
    ]
    for idx, row in enumerate(rows[:30], 1):
        lines.append(
            f"| {idx} | {row['chain_id']} | {row['code']} | {row['name']} | "
            f"{row['rank_score']} | {row['signal']} | {row['tag_count']} | {row['best_tag_name']} | "
            f"{row['three_high_total']} | {row['moat_score']} | {row['stage_score']} | "
            f"{round(row['l8_match_rate'] * 100, 1)}% | {round(row['fresh_rate'] * 100, 1)}% | "
            f"{'' if row['change_20d_pct'] is None else round(float(row['change_20d_pct']), 2)} |"
        )
    lines.extend([
        "",
        "## 分产业链 Top 5",
        "",
    ])
    for chain_id in sorted(ranking["by_chain"]):
        lines.extend([
            f"### {chain_id}",
            "",
            "| 排名 | 代码 | 名称 | 分数 | 信号 | 标签数 | 最强标签 | 三高 | 围墙 | L8 | 新鲜度 |",
            "|---:|---|---|---:|---|---:|---|---:|---:|---:|---:|",
        ])
        for idx, row in enumerate(ranking["by_chain"][chain_id][:5], 1):
            lines.append(
                f"| {idx} | {row['code']} | {row['name']} | {row['rank_score']} | "
                f"{row['signal']} | {row['tag_count']} | {row['best_tag_name']} | "
                f"{row['three_high_total']} | {row['moat_score']} | "
                f"{round(row['l8_match_rate'] * 100, 1)}% | {round(row['fresh_rate'] * 100, 1)}% |"
            )
        lines.append("")
    lines.extend([
        "",
        "## 口径",
        "",
        "- 总榜按公司-产业链聚合，同一公司在同一产业链可有多个业务标签，展示分数最高的标签。",
        "- 评分核心是标签级三高、围墙、阶段、证据、L8 和新鲜度，20 日涨幅只占 2%。",
        "- `重点候选` 不是买入建议，只表示产业链证据和标签级评分较强，仍需结合交易系统和风控。",
        "",
    ])
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return {"json_path": str(json_path), "csv_path": str(csv_path), "markdown_path": str(md_path)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Build supply-chain candidate ranking")
    parser.add_argument("--pg-url", default=DEFAULT_PG_URL)
    parser.add_argument("--top-n", type=int, default=100)
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    args = parser.parse_args()

    ranking = build_ranking(args.pg_url, top_n=args.top_n)
    paths = write_reports(ranking, Path(args.output_dir))
    print(json.dumps({
        "accepted": ranking["summary"]["chain_count"] >= 18 and ranking["summary"]["company_chain_rows"] > 0,
        **paths,
        "summary": ranking["summary"],
        "top5": ranking["global_top"][:5],
    }, ensure_ascii=False, indent=2, default=_json_default))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
