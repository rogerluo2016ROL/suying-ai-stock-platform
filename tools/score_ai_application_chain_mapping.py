#!/usr/bin/env python3
"""Score seeded chain mappings and write back three-factor / chokepoint results.

Default target is the 数据要素/AI应用商业化 chain; any chain seeded by
materialize_priority_complex_chains.py can be scored via --chain-id/--theme-id
(e.g. --chain-id embodied_intelligence --theme-id future_industry_embodied_intelligence).

Reads the seeded company_chain_mapping rows for the 数据要素/AI应用商业化 chain,
computes V6 performance-yield from financial_indicator and the canonical V5
chokepoint keyword score from stock_profiles text, then:

1. UPDATE company_chain_mapping: three_factors (PRD shape), chokepoint_score,
   trade_signal, and merges a financial/chokepoint snapshot into evidence.
2. Seed evidence_extracted_facts with one structured financial fact per mapping
   (idempotent via deterministic fact_id).

Re-runnable after re-seeding (materialize_priority_complex_chains.py wipes
generated company_chain_mapping rows for seed codes; run this tool again after).
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import psycopg2
from psycopg2.extras import Json

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "packages" / "kronos-factors"))

from kronos_factors.engine.supply_chain_bom_v5 import (  # noqa: E402
    CHOKEPOINT_WEIGHTS,
    DIM_WEIGHTS,
    INDUSTRY_CYCLE_SCORE,
    _clip,
    _score_performance_yield,
    classify_chokepoint_level,
    derive_resonance_v6,
)

CHAIN_ID = "data_ai_application_commercialization"
THEME_ID = "future_industry_data_ai_app_commercialization"
DEFAULT_DSN = os.environ.get("KRONOS_PG_URL", "postgresql://kronos:kronos@localhost:6432/kronos")


def _chokepoint_from_text(text: str) -> tuple[float, list[str], str]:
    """Canonical V5 chokepoint scoring: per-keyword count capped at 2, clip to 20."""
    total = 0.0
    keywords: list[str] = []
    for keyword, weight in CHOKEPOINT_WEIGHTS.items():
        count = text.count(keyword)
        if count > 0:
            total += min(count, 2) * weight
            keywords.append(keyword)
    score = _clip(total, DIM_WEIGHTS["chokepoint"])
    return score, keywords, classify_chokepoint_level(score, keywords)


def _perf_status(perf_score: float) -> str:
    if perf_score >= 15:
        return "业绩兑现"
    if perf_score >= 10:
        return "增长中"
    return "待验证"


def run(pg_url: str, chain_id: str = CHAIN_ID, theme_id: str = THEME_ID, dry_run: bool = False) -> dict:
    conn = psycopg2.connect(pg_url, connect_timeout=5)
    cur = conn.cursor()

    cur.execute(
        """
        SELECT m.id, m.code, m.node_id, m.evidence
        FROM company_chain_mapping m
        JOIN chain_nodes n ON n.node_id = m.node_id
        WHERE n.theme_id = %s
        """,
        (theme_id,),
    )
    rows = cur.fetchall()
    codes = [r[1] for r in rows]

    cur.execute(
        """
        SELECT DISTINCT ON (code) code, end_date, gross_margin, revenue_growth, profit_growth
        FROM financial_indicator WHERE code = ANY(%s) ORDER BY code, end_date DESC
        """,
        (codes,),
    )
    fin = {r[0]: r[1:] for r in cur.fetchall()}

    cur.execute(
        """
        SELECT code, COALESCE(main_business, '') || ' ' || COALESCE(introduction, '')
        FROM stock_profiles WHERE code = ANY(%s)
        """,
        (codes,),
    )
    texts = {r[0]: r[1] for r in cur.fetchall()}

    # business_tag_mapping mapping_id 由种子工具按 (code, node_id) 生成, 供 facts 挂靠
    cur.execute(
        "SELECT code, node_id, mapping_id FROM business_tag_mapping WHERE chain_id = %s",
        (chain_id,),
    )
    tag_ids = {(r[0], r[1]): r[2] for r in cur.fetchall()}

    updated = facts = 0
    signal_counts: dict[str, int] = {}
    for mapping_row_id, code, node_id, evidence in rows:
        end_date, gross_margin, rev_yoy, prof_yoy = fin.get(code, (None, None, None, None))
        best_yoy = max([y for y in (rev_yoy, prof_yoy) if y is not None], default=None)
        perf_score = _score_performance_yield(best_yoy)

        choke_score, choke_keywords, choke_level = _chokepoint_from_text(texts.get(code, ""))

        # 产业周期/政策强度两因子当前无数据支撑, 按"未识别"/0 诚实落库
        three_factors = {
            "industry_cycle": {"stage": "未识别", "score": INDUSTRY_CYCLE_SCORE["未识别"]},
            "policy_intensity": {"stars": 0, "score": 0.0},
            "performance_proof": {"status": _perf_status(perf_score), "score": perf_score},
        }
        resonance = derive_resonance_v6({"policy_score": 0, "q_sales_yoy": rev_yoy, "netprofit_yoy": prof_yoy})
        trade_signal = resonance["resonance_signal"]
        signal_counts[trade_signal] = signal_counts.get(trade_signal, 0) + 1

        evidence_patch = {
            "chokepoint_score": choke_score,
            "chokepoint_level": choke_level,
            "chokepoint_keywords": choke_keywords,
            "financial_snapshot": {
                "end_date": str(end_date) if end_date else None,
                "gross_margin": gross_margin,
                "revenue_growth": rev_yoy,
                "profit_growth": prof_yoy,
                "performance_yield_score": perf_score,
            },
            "scored_by": "score_ai_application_chain_mapping",
        }

        if not dry_run:
            cur.execute(
                """
                UPDATE company_chain_mapping
                SET three_factors = %s,
                    chokepoint_score = %s,
                    trade_signal = %s,
                    evidence = COALESCE(evidence, '{}'::jsonb) || %s::jsonb
                WHERE id = %s
                """,
                (Json(three_factors), int(round(choke_score)), trade_signal, Json(evidence_patch), mapping_row_id),
            )
        updated += 1

        # 财务结构化事实 → evidence_extracted_facts (幂等)
        if end_date is None:
            continue
        tag_id = tag_ids.get((code, node_id))
        if not tag_id:
            continue
        layer = node_id.rsplit("_", 1)[-1]
        fact_id = f"FACT-FIN-{code}-{layer}-{end_date}"
        quote = (
            f"{end_date} 报告期: 营收同比 {rev_yoy}%, 利润同比 {prof_yoy}%, "
            f"毛利率 {gross_margin}% (数据源: financial_indicator)"
        )
        if not dry_run:
            cur.execute(
                """
                INSERT INTO evidence_extracted_facts (
                    fact_id, mapping_id, company_code, chain_id,
                    fact_type, fact_nature, fact_value, original_quote,
                    source_level, confidence, confidence_cap,
                    growth_signal, profit_signal, moat_signal,
                    validation_status, metadata
                )
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (fact_id) DO UPDATE SET
                    fact_value = EXCLUDED.fact_value,
                    original_quote = EXCLUDED.original_quote,
                    growth_signal = EXCLUDED.growth_signal,
                    profit_signal = EXCLUDED.profit_signal,
                    moat_signal = EXCLUDED.moat_signal,
                    metadata = EXCLUDED.metadata,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    fact_id, tag_id, code, chain_id,
                    "commercial_progress", "confirmed_fact", quote, quote,
                    "strong", 0.85, 0.9,
                    (best_yoy or 0) >= 20, (gross_margin or 0) >= 50,
                    any(kw in ("垄断", "独家", "首家", "稀缺", "寡头", "唯一", "打破垄断", "卡脖子") for kw in choke_keywords),
                    "pending",
                    Json({"source": "score_ai_application_chain_mapping", "end_date": str(end_date)}),
                ),
            )
        facts += 1

    if not dry_run:
        conn.commit()
    cur.close()
    conn.close()
    return {
        "dry_run": dry_run,
        "mappings_scored": updated,
        "facts_seeded": facts,
        "trade_signal_counts": signal_counts,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pg-url", default=DEFAULT_DSN)
    parser.add_argument("--chain-id", default=CHAIN_ID)
    parser.add_argument("--theme-id", default=THEME_ID)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    import json

    print(json.dumps(
        run(args.pg_url, chain_id=args.chain_id, theme_id=args.theme_id, dry_run=args.dry_run),
        ensure_ascii=False, indent=2,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
