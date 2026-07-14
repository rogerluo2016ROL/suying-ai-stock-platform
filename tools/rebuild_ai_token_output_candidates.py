#!/usr/bin/env python3
"""Rebuild traceable candidates for the AI Token commercial output chain."""

from __future__ import annotations

import argparse
from datetime import date
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from typing import Any

import psycopg2
import psycopg2.extras


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages/kronos-factors"))
from kronos_factors.engine.token_commercial_output import classify_token_role, normalize_stock_code  # noqa: E402


CHAIN_ID = "ai_token_output"
SOURCE_CHAINS = ("ai_token_output_power", "ai_compute", "data_ai_application_commercialization")


def stable_id(prefix: str, *parts: object) -> str:
    digest = hashlib.sha1("|".join(str(part) for part in parts).encode("utf-8")).hexdigest()[:20]
    return f"{prefix}-{digest}"


def normalize_tag(tag: str) -> str:
    return re.sub(r"[\s/_-]+", "", str(tag or "")).lower()


def build_candidates(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[tuple[str, str | None, str], dict[str, Any]] = {}
    for source in rows:
        code = normalize_stock_code(source.get("code") or "")
        tag = str(source.get("tag_name") or "").strip()
        facts = dict(source.get("facts") or {})
        layer_id = classify_token_role(tag, facts)
        reasons = [] if layer_id else ["broad_tag_requires_review"]
        key = (code, layer_id, normalize_tag(tag))
        candidate = {
            "mapping_id": stable_id("TOKENOUT", code, layer_id or "UNCLASSIFIED", normalize_tag(tag)),
            "code": code,
            "tag_name": tag,
            "layer_id": layer_id,
            "node_id": f"{CHAIN_ID}:{layer_id}" if layer_id else None,
            "status": "candidate",
            "evidence_grade": "E0",
            "review_status": "candidate",
            "confidence": min(float(source.get("confidence") or 0), 0.70),
            "source_mapping_ids": [str(source.get("mapping_id") or "")],
            "source_chain_ids": [str(source.get("chain_id") or "")],
            "reason_codes": reasons,
            "facts": facts,
        }
        if key in deduped:
            prior = deduped[key]
            prior["source_mapping_ids"] = sorted(set(prior["source_mapping_ids"] + candidate["source_mapping_ids"]))
            prior["source_chain_ids"] = sorted(set(prior["source_chain_ids"] + candidate["source_chain_ids"]))
            prior["confidence"] = max(prior["confidence"], candidate["confidence"])
        else:
            deduped[key] = candidate
    return sorted(deduped.values(), key=lambda row: (row["layer_id"] or "L9", row["code"], row["tag_name"]))


def _path(candidate: dict[str, Any]) -> list[dict[str, str]]:
    names = ["Token需求场景", "模型与AI产品", "推理优化软件", "核心算力硬件", "集群与网络支撑", "Token服务与交付平台", "计量计费与运营", "商业变现与输出"]
    return [{"level": f"L{i}", "name": candidate["tag_name"] if candidate["layer_id"] == f"L{i}" else name, "source": "cross_chain_candidate" if candidate["layer_id"] == f"L{i}" else "token_output_template"} for i, name in enumerate(names, 1)]


def rebuild(pg_url: str, as_of_date: str, dry_run: bool = False) -> dict[str, Any]:
    with psycopg2.connect(pg_url) as conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT mapping_id,code,tag_name,status,confidence,chain_id
            FROM business_tag_mapping
            WHERE chain_id = ANY(%s) AND status NOT IN ('rejected') AND confidence >= 0.50
            ORDER BY code,mapping_id
        """, (list(SOURCE_CHAINS),))
        sources = [dict(row, facts={}) for row in cur.fetchall()]
        candidates = build_candidates(sources)
        classified = [row for row in candidates if row["layer_id"]]
        layer_counts = {f"L{i}": 0 for i in range(1, 9)}
        for row in classified:
            layer_counts[row["layer_id"]] += 1
        if dry_run:
            conn.rollback()
            return {"chain_id": CHAIN_ID, "dry_run": True, "source_count": len(sources), "candidate_count": len(candidates), "classified_count": len(classified), "manual_review_count": len(candidates) - len(classified), "unique_company_count": len({row['code'] for row in classified}), "layer_counts": layer_counts}

        for row in classified:
            evidence_id = stable_id("TOKENOUTEV", row["mapping_id"], as_of_date)
            cur.execute("""
                INSERT INTO business_tag_mapping (mapping_id,code,node_id,theme_id,chain_id,tag_name,l1_l8_path,confidence,status,evidence_ids)
                VALUES (%s,%s,%s,'future_industry_core',%s,%s,%s::jsonb,%s,'candidate',%s::jsonb)
                ON CONFLICT (mapping_id) DO UPDATE SET code=EXCLUDED.code,node_id=EXCLUDED.node_id,tag_name=EXCLUDED.tag_name,l1_l8_path=EXCLUDED.l1_l8_path,confidence=EXCLUDED.confidence,status='candidate',evidence_ids=EXCLUDED.evidence_ids,updated_at=CURRENT_TIMESTAMP
            """, (row["mapping_id"], row["code"], row["node_id"], CHAIN_ID, f"Token输出候选：{row['tag_name']}", json.dumps(_path(row), ensure_ascii=False), row["confidence"], json.dumps([evidence_id])))
            cur.execute("""
                INSERT INTO business_tag_token_commercial_evidence
                (evidence_id,mapping_id,code,chain_id,layer_id,token_role,evidence_grade,review_status,source_type,source_name,source_id,quote,missing_fields,next_validation_node,metadata,as_of_date)
                VALUES (%s,%s,%s,%s,%s,%s,'E0','candidate','derived_mapping','business_tag_mapping',%s,%s,%s::jsonb,%s,%s::jsonb,%s)
                ON CONFLICT (mapping_id,as_of_date) DO UPDATE SET source_id=EXCLUDED.source_id,quote=EXCLUDED.quote,metadata=EXCLUDED.metadata,updated_at=CURRENT_TIMESTAMP
            """, (evidence_id, row["mapping_id"], row["code"], CHAIN_ID, row["layer_id"], row["layer_id"], json.dumps(row["source_mapping_ids"]), "跨链候选仅证明业务标签相关，不证明客户调用、Token收入或持续交付。", json.dumps(["customer_usage", "delivery", "token_revenue", "cashflow"]), "company_product_evidence", json.dumps({"source_mapping_ids": row["source_mapping_ids"], "source_chain_ids": row["source_chain_ids"], "reason_codes": row["reason_codes"]}, ensure_ascii=False), as_of_date))
        conn.commit()
        return {"chain_id": CHAIN_ID, "dry_run": False, "source_count": len(sources), "candidate_count": len(candidates), "classified_count": len(classified), "manual_review_count": len(candidates) - len(classified), "unique_company_count": len({row['code'] for row in classified}), "layer_counts": layer_counts}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pg-url", default=os.environ.get("KRONOS_PG_URL", "postgresql://kronos:kronos@localhost:6432/kronos"))
    parser.add_argument("--as-of-date", default=date.today().isoformat())
    parser.add_argument("--mode", choices=("dry-run", "staging"), default="dry-run")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    print(json.dumps(rebuild(args.pg_url, args.as_of_date, args.dry_run or args.mode == "dry-run"), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
