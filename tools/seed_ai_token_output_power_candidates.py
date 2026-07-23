#!/usr/bin/env python3
"""从已存在的业务标签生成 Token 出口产业链候选映射。

这里只做跨链候选迁移，不把原产业链的 verified 状态继承为 Token 链已验证。
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


CHAIN_ID = "ai_token_output_power"
SOURCE_CHAINS = ("ai_compute", "data_ai_application_commercialization", "new_power_system_grid")

LAYER_RULES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("L7", "电力与智算基础设施", ("数据中心", "智算中心", "IDC", "电网", "绿电", "新能源", "储能", "变压器", "输配电", "电力")),
    ("L6", "集群配套与数据中心设备", ("液冷", "散热", "电源", "UPS", "PCB", "连接器", "交换机", "光纤", "机柜")),
    ("L5", "算力集群与调度", ("AI服务器", "服务器", "算力调度", "算力平台", "推理集群", "训练集群", "云计算")),
    ("L4", "核心算力硬件", ("AI芯片", "GPU", "ASIC", "HBM", "先进封装", "光模块", "高速光模块", "存储芯片", "算力芯片")),
    ("L8", "Token商业化与出口", ("AI应用", "SaaS", "智能体", "Agent", "API服务", "模型服务", "云服务", "出海")),
    ("L3", "模型与软件栈", ("大模型", "基础软件", "算法", "推理软件", "模型", "软件")),
)


def classify_layer(tag_name: str) -> tuple[str, str] | None:
    text = (tag_name or "").lower()
    for layer_id, layer_name, keywords in LAYER_RULES:
        if any(keyword.lower() in text for keyword in keywords):
            return layer_id, layer_name
    return None


def stable_id(prefix: str, *parts: object) -> str:
    digest = hashlib.sha1("|".join(str(part) for part in parts).encode("utf-8")).hexdigest()[:20]
    return f"{prefix}-{digest}"


def build_path(layer_id: str, layer_name: str, tag_name: str) -> list[dict[str, str]]:
    names = {
        "L1": "电力过剩转化为可计费Token",
        "L2": "电力约束与可利用电量",
        "L3": "模型与软件栈",
        "L4": "核心算力硬件",
        "L5": "算力集群与调度",
        "L6": "集群配套与数据中心设备",
        "L7": "电力与智算基础设施",
        "L8": "Token商业化与出口",
    }
    result = []
    for level in range(1, 9):
        key = f"L{level}"
        result.append({
            "level": key,
            "name": tag_name if key == layer_id else names[key],
            "source": "cross_chain_candidate" if key == layer_id else "token_output_chain_template",
        })
    return result


def seed(pg_url: str, as_of_date: str, dry_run: bool = False) -> dict[str, Any]:
    with psycopg2.connect(pg_url) as conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(
            """
            SELECT mapping_id, code, chain_id, tag_name, confidence, status
            FROM business_tag_mapping
            WHERE chain_id = ANY(%s)
              AND status NOT IN ('rejected')
              AND confidence >= 0.50
            ORDER BY code, confidence DESC, mapping_id
            """,
            (list(SOURCE_CHAINS),),
        )
        source_rows = list(cur.fetchall())

        candidates: dict[tuple[str, str], dict[str, Any]] = {}
        for row in source_rows:
            classified = classify_layer(row["tag_name"])
            if classified is None:
                continue
            layer_id, layer_name = classified
            key = (row["code"], layer_id)
            if key not in candidates or float(row["confidence"] or 0) > float(candidates[key]["confidence"] or 0):
                candidates[key] = {**row, "layer_id": layer_id, "layer_name": layer_name}

        layer_counts = {f"L{i}": 0 for i in range(1, 9)}
        if dry_run:
            for row in candidates.values():
                layer_counts[row["layer_id"]] += 1
            conn.rollback()
            return {"chain_id": CHAIN_ID, "dry_run": True, "source_rows": len(source_rows), "candidate_count": len(candidates), "layer_counts": layer_counts}

        for row in candidates.values():
            mapping_id = stable_id("TOKENMAP", row["code"], row["layer_id"])
            event_id = stable_id("TOKENEV", mapping_id, row["mapping_id"])
            power_evidence_id = stable_id("TOKENPOWER", mapping_id, row["mapping_id"])
            confidence = min(float(row["confidence"] or 0), 0.70)
            tag_name = f"Token出口候选：{row['tag_name']}"
            path = build_path(row["layer_id"], row["layer_name"], tag_name)
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
                (mapping_id, row["code"], f"{CHAIN_ID}:{row['layer_id']}", "future_industry_core", CHAIN_ID,
                 tag_name, json.dumps(path, ensure_ascii=False), confidence, json.dumps([event_id, power_evidence_id])),
            )
            excerpt = (
                f"由现有产业链 {row['chain_id']} 的业务标签“{row['tag_name']}”迁移为 Token 出口候选。"
                "该记录仅证明业务相关性，不证明电力、算力利用率、Token产量、客户或收入。"
            )
            cur.execute(
                """
                INSERT INTO business_tag_evidence_events (
                    event_id,mapping_id,code,node_id,event_date,source_type,source_id,title,excerpt,
                    evidence_type,impact_dimensions,confidence,review_status,stage_before,stage_after
                ) VALUES (%s,%s,%s,%s,%s,'derived_mapping',%s,%s,%s,'chain_candidate',%s::jsonb,%s,'candidate','{}'::jsonb,'{}'::jsonb)
                ON CONFLICT (event_id) DO UPDATE SET excerpt=EXCLUDED.excerpt, confidence=EXCLUDED.confidence,
                    review_status='candidate'
                """,
                (event_id, mapping_id, row["code"], f"{CHAIN_ID}:{row['layer_id']}", as_of_date,
                 row["mapping_id"], tag_name, excerpt, json.dumps([row["layer_id"], "evidence_validation"]), confidence),
            )
            cur.execute(
                """
                INSERT INTO business_tag_token_output_power_evidence (
                    evidence_id,mapping_id,code,chain_id,layer_id,power_source_type,evidence_grade,
                    review_status,source_type,source_name,quote,as_of_date,metadata
                ) VALUES (%s,%s,%s,%s,%s,'unknown','E0','candidate','derived_mapping','business_tag_mapping',%s,%s,%s::jsonb)
                ON CONFLICT (evidence_id) DO UPDATE SET quote=EXCLUDED.quote, as_of_date=EXCLUDED.as_of_date,
                    review_status='candidate', updated_at=CURRENT_TIMESTAMP
                """,
                (power_evidence_id, mapping_id, row["code"], CHAIN_ID, row["layer_id"], excerpt, as_of_date,
                 json.dumps({"source_mapping_id": row["mapping_id"], "source_chain_id": row["chain_id"], "unverified_fields": ["power", "capacity", "tokens", "customer", "revenue"]}, ensure_ascii=False)),
            )
            layer_counts[row["layer_id"]] += 1
        conn.commit()
        return {"chain_id": CHAIN_ID, "dry_run": False, "source_rows": len(source_rows), "candidate_count": len(candidates), "layer_counts": layer_counts}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pg-url", default=os.environ.get("KRONOS_PG_URL", "postgresql://kronos:kronos@localhost:6432/kronos"))
    parser.add_argument("--as-of-date", default=date.today().isoformat())
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    print(json.dumps(seed(args.pg_url, args.as_of_date, args.dry_run), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
