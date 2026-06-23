"""Build and optionally persist supply-chain graph records from LLM extraction."""

import hashlib
import json
from datetime import date
from typing import Any


def _stable_id(prefix: str, *parts: object) -> str:
    raw = "|".join(str(p or "") for p in parts)
    return f"{prefix}_{hashlib.sha1(raw.encode('utf-8')).hexdigest()[:16]}"


def _first(items: list[Any]) -> Any:
    return items[0] if items else None


def _node_id(name: str) -> str | None:
    if not name:
        return None
    known = {
        "量子科技": "quantum_core",
        "生物制造": "bio_manufacturing_core",
        "氢能": "hydrogen_fusion_core",
        "核聚变能": "hydrogen_fusion_core",
        "脑机接口": "brain_computer_core",
        "具身智能": "embodied_ai_core",
        "第六代移动通信": "6g_core",
        "6G": "6g_core",
        "半导体设备材料": "semiconductor_equipment_materials",
        "工业软件": "industrial_software_core",
    }
    return known.get(name) or _stable_id("node", name)


def build_graph_records(extraction: dict, source: dict | None = None) -> dict:
    source = source or {}
    title = source.get("title") or "manual_supply_chain_extraction"
    source_type = source.get("source_type") or "manual"
    source_url = source.get("source_url")
    published_at = source.get("published_at")
    source_id = _stable_id("src", source_type, title, source_url, published_at)

    source_record = {
        "source_id": source_id,
        "source_type": source_type,
        "title": title,
        "source_url": source_url,
        "published_at": published_at,
        "content_hash": _stable_id("hash", extraction),
        "raw_text": source.get("raw_text", ""),
    }

    bom_nodes = extraction.get("bom_nodes") if isinstance(extraction.get("bom_nodes"), list) else []
    companies = extraction.get("companies") if isinstance(extraction.get("companies"), list) else []
    products = extraction.get("products") if isinstance(extraction.get("products"), list) else []
    materials = extraction.get("materials") if isinstance(extraction.get("materials"), list) else []
    evidence_items = extraction.get("evidence") if isinstance(extraction.get("evidence"), list) else []

    node_name = _first(bom_nodes) or extraction.get("policy_theme", "")
    node_id = _node_id(str(node_name or ""))
    product = _first(products)
    material = _first(materials)

    evidence_records = []
    for index, item in enumerate(evidence_items):
        if not isinstance(item, dict):
            continue
        evidence_type = item.get("source_type") or item.get("evidence_type") or source_type
        summary = item.get("summary") or ""
        evidence_records.append({
            "evidence_id": _stable_id("ev", source_id, node_id, summary, index),
            "code": None,
            "node_id": node_id,
            "source_id": source_id,
            "evidence_type": evidence_type,
            "summary": summary,
            "excerpt": item.get("excerpt"),
            "confidence": float(item.get("confidence") or 0),
            "evidence_date": item.get("evidence_date") or published_at,
            "status": "pending_review",
        })

    mappings = []
    for company in companies:
        if not isinstance(company, dict) or not company.get("code"):
            continue
        code = str(company["code"])
        company_evidence = []
        for evidence in evidence_records:
            linked = dict(evidence)
            linked["code"] = code
            company_evidence.append(linked)
        evidence_ids = [e["evidence_id"] for e in company_evidence]
        mappings.append({
            "mapping_id": _stable_id("map", code, node_id, product, material),
            "code": code,
            "name": company.get("name"),
            "node_id": node_id,
            "product_name": product,
            "material_name": material,
            "evidence_ids": evidence_ids,
            "confidence": max([e["confidence"] for e in company_evidence] or [0.0]),
            "status": "pending_review",
        })
        evidence_records = company_evidence

    return {
        "source": source_record,
        "mappings": mappings,
        "evidence": evidence_records,
        "commercialization_stage": extraction.get("commercialization_stage", ""),
        "policy_theme": extraction.get("policy_theme", ""),
    }


def persist_graph_records(records: dict) -> dict:
    from kronos_factors.scorer._db_stub import _get_db

    source = records.get("source") or {}
    mappings = records.get("mappings") or []
    evidence = records.get("evidence") or []
    written = {"policy_sources": 0, "company_bom_mapping": 0, "company_evidence": 0}
    with _get_db(readonly=False) as db:
        db.execute(
            """
            INSERT INTO policy_sources(source_id, source_type, title, source_url, published_at, content_hash, raw_text)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (source_id) DO NOTHING
            """,
            (
                source.get("source_id"),
                source.get("source_type") or "manual",
                source.get("title") or "manual_supply_chain_extraction",
                source.get("source_url"),
                source.get("published_at"),
                source.get("content_hash"),
                source.get("raw_text") or "",
            ),
        )
        written["policy_sources"] = 1

        for mapping in mappings:
            db.execute(
                """
                INSERT INTO company_bom_mapping(mapping_id, code, node_id, product_name, material_name, evidence_ids, confidence, status, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (mapping_id) DO NOTHING
                """,
                (
                    mapping.get("mapping_id"),
                    mapping.get("code"),
                    mapping.get("node_id"),
                    mapping.get("product_name"),
                    mapping.get("material_name"),
                    json.dumps(mapping.get("evidence_ids") or [], ensure_ascii=False),
                    mapping.get("confidence") or 0,
                    mapping.get("status") or "pending_review",
                    date.today().isoformat(),
                ),
            )
            written["company_bom_mapping"] += 1

        for item in evidence:
            db.execute(
                """
                INSERT INTO company_evidence(evidence_id, code, node_id, source_id, evidence_type, summary, excerpt, confidence, evidence_date, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (evidence_id) DO NOTHING
                """,
                (
                    item.get("evidence_id"),
                    item.get("code"),
                    item.get("node_id"),
                    item.get("source_id"),
                    item.get("evidence_type") or "manual",
                    item.get("summary") or "",
                    item.get("excerpt"),
                    item.get("confidence") or 0,
                    item.get("evidence_date"),
                    item.get("status") or "pending_review",
                ),
            )
            written["company_evidence"] += 1

    return {"status": "ok", "written": written}
