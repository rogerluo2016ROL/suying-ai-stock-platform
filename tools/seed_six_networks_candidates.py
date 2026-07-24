#!/usr/bin/env python3
"""从 foundation 映射（company_bom_mapping）生成六张网业务标签候选。

仅做关键词级候选迁移：不继承 verified 状态，不证明订单/客户/收入。
来源是 build_supply_chain_foundation.py 的主营/简介子串匹配，证据等级最低，
全部落 status='candidate'，待证据管线（LLM 提取 + 人工审核）补证后再升级。
"""

from __future__ import annotations

import argparse
from datetime import date
import hashlib
import json
import os
from typing import Any

import psycopg2
import psycopg2.extras


CHAINS: dict[str, str] = {
    "national_water_network": "国家水网",
    "new_power_grid": "新型电网",
    "compute_network": "算力网",
    "next_gen_comm_network": "新一代通信网",
    "urban_underground_pipeline": "城市地下管网",
    "logistics_network": "物流网",
}
THEME_ID = "future_industry_core"
MIN_CONFIDENCE = 0.50


def stable_id(prefix: str, *parts: object) -> str:
    digest = hashlib.sha1("|".join(str(part) for part in parts).encode("utf-8")).hexdigest()[:20]
    return f"{prefix}-{digest}"


def build_path(chain_name: str, layer_name: str, tag_name: str) -> list[dict[str, str]]:
    names = {
        "L1": "六张网（十五五现代化基础设施体系）",
        "L2": chain_name,
        "L3": f"{chain_name}产业链",
        "L4": layer_name,
        "L5": tag_name,
        "L6": "技术路线（待证据补充）",
        "L7": "公司业务分部（待证据补充）",
        "L8": "证据事件（待证据补充）",
    }
    return [
        {
            "level": f"L{i}",
            "name": names[f"L{i}"],
            "source": "six_networks_foundation_seed",
        }
        for i in range(1, 9)
    ]


def seed(pg_url: str, as_of_date: str, dry_run: bool = False) -> dict[str, Any]:
    with psycopg2.connect(pg_url) as conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(
            """
            SELECT m.mapping_id, m.code, m.node_id, m.product_name, m.confidence,
                   n.node_name AS layer_name
            FROM company_bom_mapping m
            LEFT JOIN chain_nodes n ON n.node_id = m.node_id
            WHERE m.node_id = ANY(%s)
              AND m.status <> 'rejected'
              AND m.confidence >= %s
            ORDER BY m.code, m.confidence DESC, m.mapping_id
            """,
            (
                [nid for cid in CHAINS for nid in _chain_node_ids(cur, cid)],
                MIN_CONFIDENCE,
            ),
        )
        source_rows = list(cur.fetchall())

        # 每公司每链只保留置信度最高的一条
        node_chain = {}
        cur.execute(
            "SELECT node_id, chain_id FROM supply_chain_bom_nodes WHERE chain_id = ANY(%s)",
            (list(CHAINS),),
        )
        for row in cur.fetchall():
            node_chain[row["node_id"]] = row["chain_id"]

        candidates: dict[tuple[str, str], dict[str, Any]] = {}
        for row in source_rows:
            chain_id = node_chain.get(row["node_id"])
            if not chain_id:
                continue
            key = (row["code"], chain_id)
            if key not in candidates or float(row["confidence"] or 0) > float(candidates[key]["confidence"] or 0):
                candidates[key] = {**row, "chain_id": chain_id}

        chain_counts = {cid: 0 for cid in CHAINS}
        if dry_run:
            for row in candidates.values():
                chain_counts[row["chain_id"]] += 1
            conn.rollback()
            return {"dry_run": True, "source_rows": len(source_rows),
                    "candidate_count": len(candidates), "chain_counts": chain_counts}

        for row in candidates.values():
            chain_id = row["chain_id"]
            chain_name = CHAINS[chain_id]
            layer_name = row.get("layer_name") or row["node_id"]
            mapping_id = stable_id("SIXNETMAP", row["code"], chain_id)
            event_id = stable_id("SIXNETEV", mapping_id, row["mapping_id"])
            confidence = min(float(row["confidence"] or 0), 0.70)
            tag_name = str(row.get("product_name") or layer_name)
            path = build_path(chain_name, layer_name, tag_name)
            cur.execute(
                """
                INSERT INTO business_tag_mapping (
                    mapping_id, code, node_id, theme_id, chain_id, tag_name,
                    l1_l8_path, confidence, status, evidence_ids
                ) VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb,%s,'candidate',%s::jsonb)
                ON CONFLICT (mapping_id) DO UPDATE SET
                    tag_name=EXCLUDED.tag_name, l1_l8_path=EXCLUDED.l1_l8_path,
                    confidence=EXCLUDED.confidence, status='candidate',
                    evidence_ids=EXCLUDED.evidence_ids, updated_at=CURRENT_TIMESTAMP
                """,
                (mapping_id, row["code"], row["node_id"], THEME_ID, chain_id,
                 tag_name, json.dumps(path, ensure_ascii=False), confidence,
                 json.dumps([event_id])),
            )
            excerpt = (
                f"由产业链数据底座关键词匹配生成（源映射 {row['mapping_id']}，"
                f"层级 {layer_name}）。该记录仅证明主营业务相关性，"
                "不证明订单、客户、收入或产能，待证据管线补证后再升级。"
            )
            cur.execute(
                """
                INSERT INTO business_tag_evidence_events (
                    event_id,mapping_id,code,node_id,event_date,source_type,source_id,title,excerpt,
                    evidence_type,impact_dimensions,confidence,review_status,stage_before,stage_after
                ) VALUES (%s,%s,%s,%s,%s,'foundation_seed',%s,%s,%s,'chain_candidate',%s::jsonb,%s,'candidate','{}'::jsonb,'{}'::jsonb)
                ON CONFLICT (event_id) DO UPDATE SET excerpt=EXCLUDED.excerpt, confidence=EXCLUDED.confidence,
                    review_status='candidate'
                """,
                (event_id, mapping_id, row["code"], row["node_id"], as_of_date,
                 row["mapping_id"], tag_name, excerpt,
                 json.dumps(["evidence_validation"]), confidence),
            )
            chain_counts[chain_id] += 1
        conn.commit()
        return {"dry_run": False, "source_rows": len(source_rows),
                "candidate_count": len(candidates), "chain_counts": chain_counts}


def _chain_node_ids(cur, chain_id: str) -> list[str]:
    cur.execute(
        "SELECT node_id FROM supply_chain_bom_nodes WHERE chain_id = %s",
        (chain_id,),
    )
    return [r["node_id"] for r in cur.fetchall()]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pg-url", default=os.environ.get(
        "KRONOS_PG_URL", "postgresql://kronos:kronos@localhost:6432/kronos"))
    parser.add_argument("--as-of-date", default=date.today().isoformat())
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    print(json.dumps(seed(args.pg_url, args.as_of_date, args.dry_run), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
