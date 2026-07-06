#!/usr/bin/env python3
"""Build 大葱产业链 data-foundation nodes, edges, mappings and report."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "packages" / "kronos-factors"))

from kronos_factors.engine.supply_chain_foundation import (  # noqa: E402
    build_foundation_catalog,
    build_foundation_report,
    load_supply_chain_config,
    mapping_to_pg_rows,
    score_company_mappings,
)


def collect_company_texts(pg_url: str) -> list[dict[str, Any]]:
    import psycopg2

    conn = psycopg2.connect(pg_url, connect_timeout=5)
    cur = conn.cursor()
    cur.execute("""
        SELECT s.code, s.name, s.industry,
               COALESCE(p.main_business, '') AS main_business,
               COALESCE(p.introduction, '') AS introduction
        FROM stocks s
        LEFT JOIN stock_profiles p ON p.code = s.code
        WHERE s.is_st = 0 AND s.name NOT LIKE '%ST%'
    """)
    companies = {
        str(code): {
            "code": str(code),
            "name": name or "",
            "industry": industry or "",
            "main_business": main_business or "",
            "introduction": introduction or "",
            "report_titles": [],
        }
        for code, name, industry, main_business, introduction in cur.fetchall()
    }
    cur.execute("""
        SELECT code, title
        FROM research_reports_tushare
        WHERE code IS NOT NULL AND code != 'nan'
        ORDER BY pub_date DESC
        LIMIT 50000
    """)
    seen: dict[str, int] = {}
    for code, title in cur.fetchall():
        code = str(code)
        if code not in companies or seen.get(code, 0) >= 5:
            continue
        companies[code]["report_titles"].append(str(title or ""))
        seen[code] = seen.get(code, 0) + 1
    cur.close()
    conn.close()
    return list(companies.values())


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Generate report without writing PostgreSQL")
    parser.add_argument("--persist", action="store_true", help="Write generated rows to PostgreSQL")
    parser.add_argument("--chains", nargs="*", default=None, help="Optional Chinese chain names to include")
    parser.add_argument("--min-confidence", type=float, default=0.30)
    parser.add_argument("--report-path", default="outputs/supply_chain_foundation_report.json")
    return parser.parse_args()


def _chain_node_layer(node: dict[str, Any], index_by_id: dict[str, int]) -> int:
    if node.get("level") == "chain":
        return 0
    return index_by_id.get(str(node.get("node_id")), 1)


def persist_foundation(pg_url: str, catalog, mappings: list) -> dict[str, int]:
    import psycopg2
    from psycopg2.extras import Json

    conn = psycopg2.connect(pg_url, connect_timeout=5)
    cur = conn.cursor()
    node_count = edge_count = bom_count = chain_count = chain_node_count = 0
    node_ids = [node["node_id"] for node in catalog.nodes]
    layer_index = {node["node_id"]: idx for idx, node in enumerate(catalog.nodes, start=1)}

    cur.execute("""
        INSERT INTO industry_themes
            (theme_id, theme_name, category, key_directions, policy_intensity_stars)
        VALUES (%s,%s,%s,%s,%s)
        ON CONFLICT (theme_id) DO UPDATE SET
            theme_name=EXCLUDED.theme_name,
            category=EXCLUDED.category,
            key_directions=EXCLUDED.key_directions,
            policy_intensity_stars=EXCLUDED.policy_intensity_stars,
            updated_at=NOW()
    """, (
        "future_industry_core",
        "未来产业主攻方向",
        "战新",
        Json(["半导体", "新能源", "AI算力", "机器人", "创新药", "新能源车", "消费升级", "国防军工", "高端制造", "周期资源"]),
        3,
    ))

    # Remove generated company-chain rows first because company_chain_mapping has no unique key.
    cur.execute("DELETE FROM company_chain_mapping WHERE node_id = ANY(%s)", (node_ids,))
    cur.execute(
        "DELETE FROM company_bom_mapping WHERE mapping_id LIKE 'auto_%%' AND node_id = ANY(%s)",
        (node_ids,),
    )

    for node in catalog.nodes:
        cur.execute("""
            INSERT INTO supply_chain_bom_nodes
                (node_id, theme_id, chain_id, parent_node_id, level, name, node_type, keywords, policy_weight)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (node_id) DO UPDATE SET
                theme_id=EXCLUDED.theme_id,
                chain_id=EXCLUDED.chain_id,
                parent_node_id=EXCLUDED.parent_node_id,
                level=EXCLUDED.level,
                name=EXCLUDED.name,
                node_type=EXCLUDED.node_type,
                keywords=EXCLUDED.keywords,
                policy_weight=EXCLUDED.policy_weight
        """, (
            node["node_id"], node["theme_id"], node["chain_id"], node["parent_node_id"],
            node["level"], node["name"], node["node_type"], Json(node["keywords"]), node["policy_weight"],
        ))
        node_count += 1
        cur.execute("""
            INSERT INTO chain_nodes
                (node_id, theme_id, node_name, layer, parent_node_id, upstream_nodes, downstream_nodes, value_chain, competition)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (node_id) DO UPDATE SET
                theme_id=EXCLUDED.theme_id,
                node_name=EXCLUDED.node_name,
                layer=EXCLUDED.layer,
                parent_node_id=EXCLUDED.parent_node_id,
                upstream_nodes=EXCLUDED.upstream_nodes,
                downstream_nodes=EXCLUDED.downstream_nodes,
                value_chain=EXCLUDED.value_chain,
                competition=EXCLUDED.competition
        """, (
            node["node_id"], node["theme_id"], node["name"], _chain_node_layer(node, layer_index),
            node["parent_node_id"], Json([]), Json([]),
            Json({"margin": None, "pricing_power": None, "value_added": None,
                  "note": "待填充", "_meta": {"keywords": node["keywords"],
                  "chain_id": node["chain_id"], "node_type": node["node_type"]}}),
            Json({"concentration": None, "leader_share": None, "barrier": None, "threat": None,
                  "note": "待填充", "_status": "foundation_seed"}),
        ))
        chain_node_count += 1

    for edge in catalog.edges:
        cur.execute("""
            INSERT INTO supply_chain_bom_edges (edge_id, from_node_id, to_node_id, relation)
            VALUES (%s,%s,%s,%s)
            ON CONFLICT (edge_id) DO UPDATE SET
                from_node_id=EXCLUDED.from_node_id,
                to_node_id=EXCLUDED.to_node_id,
                relation=EXCLUDED.relation
        """, (edge["edge_id"], edge["from_node_id"], edge["to_node_id"], edge["relation"]))
        edge_count += 1

    for mapping in mappings:
        rows = mapping_to_pg_rows(mapping)
        bom = rows["company_bom_mapping"]
        cur.execute("""
            INSERT INTO company_bom_mapping
                (mapping_id, code, node_id, product_name, material_name, evidence_ids, confidence, status, updated_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,CURRENT_TIMESTAMP)
            ON CONFLICT (mapping_id) DO UPDATE SET
                product_name=EXCLUDED.product_name,
                material_name=EXCLUDED.material_name,
                evidence_ids=EXCLUDED.evidence_ids,
                confidence=EXCLUDED.confidence,
                status=EXCLUDED.status,
                updated_at=CURRENT_TIMESTAMP
        """, (
            bom["mapping_id"], bom["code"], bom["node_id"], bom["product_name"], bom["material_name"],
            Json(bom["evidence_ids"]), bom["confidence"], bom["status"],
        ))
        bom_count += 1

        chain = rows["company_chain_mapping"]
        cur.execute("""
            INSERT INTO company_chain_mapping
                (code, node_id, main_pct, policy_match_score, chokepoint_score, evidence, three_factors, trade_signal)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
        """, (
            chain["code"], chain["node_id"], chain["main_pct"], chain["policy_match_score"],
            chain["chokepoint_score"], Json(chain["evidence"]), Json(chain["three_factors"]), chain["trade_signal"],
        ))
        chain_count += 1

    conn.commit()
    cur.close()
    conn.close()
    return {
        "nodes": node_count,
        "chain_nodes": chain_node_count,
        "edges": edge_count,
        "company_bom_mapping": bom_count,
        "company_chain_mapping": chain_count,
    }


def main() -> int:
    args = parse_args()
    if args.persist and args.dry_run:
        raise SystemExit("--persist and --dry-run cannot be used together")
    pg_url = os.environ.get("KRONOS_PG_URL", "postgresql://kronos:kronos@localhost:6432/kronos")
    config = load_supply_chain_config()
    catalog = build_foundation_catalog(config, chains=args.chains)
    companies = collect_company_texts(pg_url)
    mappings = score_company_mappings(catalog, companies, min_confidence=args.min_confidence)
    report = build_foundation_report(catalog, mappings)
    if args.persist:
        report["persist_counts"] = persist_foundation(pg_url, catalog, mappings)
    report.update({
        "dry_run": not args.persist,
        "persisted": bool(args.persist),
        "min_confidence": args.min_confidence,
    })

    report_path = REPO_ROOT / args.report_path
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
