#!/usr/bin/env python3
"""Validate and import mapped-company CAPEX evidence records."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any

import psycopg2


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PG_URL = os.environ.get("KRONOS_PG_URL", "postgresql://kronos:kronos@localhost:6432/kronos")
DEFAULT_TEMPLATE_PATH = PROJECT_ROOT / "docs" / "data-templates" / "business-tag-capex-evidence.template.json"

REQUIRED_FIELDS = [
    "capex_evidence_id",
    "mapping_id",
    "code",
    "fiscal_period",
    "capex_direction",
    "mapped_layer_id",
    "mapped_segments",
    "source_type",
    "source_name",
    "quote",
    "as_of_date",
    "evidence_level",
]
VALID_REVIEW_STATUSES = {"pending_review", "approved", "rejected"}
VALID_SOURCE_LEVELS = {"strong", "mid", "weak"}
VALID_EVIDENCE_LEVELS = {"reported", "directional", "estimated", "manual_judgement"}
CAPEX_KEYWORDS = (
    "资本开支", "资本支出", "capex", "固定资产投资", "在建工程", "购建固定资产",
    "扩产", "产能", "产线", "项目建设", "建设项目", "设备投入", "设备购置",
    "数据中心", "智算中心", "服务器", "液冷", "算力中心", "厂房", "募投项目",
)
AI_DIRECTION_KEYWORDS = (
    "AI", "人工智能", "算力", "大模型", "数据中心", "智算", "服务器", "GPU",
    "光模块", "CPO", "液冷", "交换机", "HBM", "CoWoS", "先进封装", "PCB",
)
LAYER_SEGMENT_RULES = [
    ("foundation", ("HBM", "CoWoS", "先进封装", "芯片", "晶圆", "封装"), ["HBM/先进封装"]),
    ("infrastructure", ("数据中心", "智算中心", "服务器", "液冷", "光模块", "CPO", "交换机", "PCB", "算力中心"), ["AI服务器", "IDC"]),
    ("demand", ("云", "大模型", "AI应用", "人工智能应用"), ["云厂商资本开支", "企业AI应用"]),
]


def load_records(path: str | Path) -> list[dict[str, Any]]:
    input_path = Path(path)
    text = input_path.read_text(encoding="utf-8").strip()
    if not text:
        return []
    if input_path.suffix == ".jsonl":
        return [json.loads(line) for line in text.splitlines() if line.strip()]
    payload = json.loads(text)
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        records = payload.get("records") or payload.get("capex_evidence")
        if isinstance(records, list):
            return records
    raise ValueError("Input must be JSON list, JSON object with records/capex_evidence, or JSONL")


def _missing_required_fields(record: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    for field in REQUIRED_FIELDS:
        value = record.get(field)
        if value is None or value == "" or value == []:
            missing.append(field)
    return missing


def _parse_date(value: Any) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, (date, datetime)):
        return value.isoformat()[:10]
    text = str(value)
    try:
        return date.fromisoformat(text[:10]).isoformat()
    except ValueError:
        return None


def normalize_record(record: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(record)
    normalized.setdefault("review_status", "pending_review")
    normalized.setdefault("source_level", "mid")
    normalized.setdefault("confidence", 0.0)
    normalized.setdefault("currency", "CNY")
    normalized.setdefault("metadata", {})
    normalized.setdefault("amount_is_total_capex", False)
    normalized.setdefault("amount_is_segment_capex", False)
    normalized.setdefault("direction_is_ai_related", False)
    normalized["as_of_date"] = _parse_date(normalized.get("as_of_date"))
    normalized["report_date"] = _parse_date(normalized.get("report_date"))
    return normalized


def validate_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    accepted: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for index, raw in enumerate(records):
        record = normalize_record(raw)
        record_errors: list[str] = []
        missing = _missing_required_fields(record)
        if missing:
            record_errors.append(f"missing required fields: {', '.join(missing)}")
        capex_id = str(record.get("capex_evidence_id") or "")
        if capex_id in seen_ids:
            record_errors.append("duplicate capex_evidence_id in input")
        seen_ids.add(capex_id)
        if record.get("review_status") not in VALID_REVIEW_STATUSES:
            record_errors.append(f"review_status must be one of {sorted(VALID_REVIEW_STATUSES)}")
        if record.get("source_level") not in VALID_SOURCE_LEVELS:
            record_errors.append(f"source_level must be one of {sorted(VALID_SOURCE_LEVELS)}")
        if record.get("evidence_level") not in VALID_EVIDENCE_LEVELS:
            record_errors.append(f"evidence_level must be one of {sorted(VALID_EVIDENCE_LEVELS)}")
        if not record.get("as_of_date"):
            record_errors.append("as_of_date must be ISO date")
        try:
            confidence = float(record.get("confidence") or 0.0)
            if confidence < 0 or confidence > 1:
                record_errors.append("confidence must be between 0 and 1")
        except Exception:
            record_errors.append("confidence must be numeric")
        if record.get("capex_amount") is not None:
            try:
                float(record["capex_amount"])
            except Exception:
                record_errors.append("capex_amount must be numeric when provided")
            if not record.get("capex_amount_unit"):
                record_errors.append("capex_amount_unit is required when capex_amount is provided")
        if not isinstance(record.get("capex_direction"), list):
            record_errors.append("capex_direction must be a list")
        if not isinstance(record.get("mapped_segments"), list):
            record_errors.append("mapped_segments must be a list")
        if len(str(record.get("quote") or "").strip()) < 8:
            record_errors.append("quote must contain source text; no quote, no formal evidence")

        if record_errors:
            errors.append({
                "index": index,
                "capex_evidence_id": record.get("capex_evidence_id"),
                "message": "; ".join(record_errors),
            })
        else:
            accepted.append(record)
    return {
        "valid": not errors,
        "input_count": len(records),
        "accepted_count": len(accepted),
        "errors": errors,
        "accepted_records": accepted,
    }


def text_has_capex_signal(text: str) -> bool:
    lowered = text.lower()
    return any(keyword.lower() in lowered for keyword in CAPEX_KEYWORDS)


def is_ai_related_direction(text: str) -> bool:
    lowered = text.lower()
    return any(keyword.lower() in lowered for keyword in AI_DIRECTION_KEYWORDS)


def infer_layer_and_segments(text: str) -> tuple[str, list[str]]:
    lowered = text.lower()
    for layer_id, keywords, segments in LAYER_SEGMENT_RULES:
        if any(keyword.lower() in lowered for keyword in keywords):
            return layer_id, segments
    return "supporting", ["资本开支方向待审核"]


def infer_capex_direction(text: str) -> list[str]:
    directions: list[str] = []
    for keyword in CAPEX_KEYWORDS + AI_DIRECTION_KEYWORDS:
        if keyword.lower() in text.lower() and keyword not in directions:
            directions.append(keyword)
    return directions[:8] or ["资本开支方向待审核"]


def _stable_capex_id(mapping_id: str, fact_id: str, quote: str) -> str:
    digest = hashlib.sha1(f"{mapping_id}|{fact_id}|{quote}".encode("utf-8")).hexdigest()[:16]
    clean_mapping = re.sub(r"[^a-zA-Z0-9_-]+", "-", mapping_id.lower()).strip("-")
    return f"capex-{clean_mapping}-{digest}"


def build_record_from_fact(row: dict[str, Any]) -> dict[str, Any] | None:
    quote = str(row.get("original_quote") or row.get("fact_value") or "").strip()
    if not quote or not text_has_capex_signal(quote):
        return None
    mapping_id = str(row.get("mapping_id") or "")
    fact_id = str(row.get("fact_id") or "")
    layer_id, segments = infer_layer_and_segments(" ".join([
        quote,
        str(row.get("tag_name") or ""),
        str(row.get("node_id") or ""),
        str(row.get("industry") or ""),
    ]))
    created_at = row.get("created_at")
    as_of_date = _parse_date(created_at) or date.today().isoformat()
    return {
        "capex_evidence_id": _stable_capex_id(mapping_id, fact_id, quote),
        "mapping_id": mapping_id,
        "code": str(row.get("code") or ""),
        "company_name": str(row.get("company_name") or row.get("name") or ""),
        "chain_id": str(row.get("chain_id") or ""),
        "node_id": str(row.get("node_id") or ""),
        "fiscal_period": str(row.get("fiscal_period") or "unknown"),
        "report_date": as_of_date,
        "as_of_date": as_of_date,
        "capex_amount": None,
        "capex_amount_unit": "",
        "currency": "CNY",
        "capex_direction": infer_capex_direction(quote),
        "mapped_layer_id": layer_id,
        "mapped_segments": segments,
        "source_id": "evidence_extracted_facts",
        "source_type": str(row.get("source_type") or row.get("fact_type") or "evidence_fact"),
        "source_level": str(row.get("source_level") or "mid"),
        "source_name": f"evidence_extracted_facts:{fact_id}",
        "source_url": str(row.get("source_url") or ""),
        "quote": quote,
        "evidence_level": "directional",
        "confidence": float(row.get("confidence") or 0.5),
        "review_status": "pending_review",
        "amount_is_total_capex": False,
        "amount_is_segment_capex": False,
        "direction_is_ai_related": is_ai_related_direction(quote),
        "metadata": {
            "source_fact_id": fact_id,
            "auto_collected": True,
            "auto_collect_rule": "capex_keyword_from_evidence_extracted_facts",
        },
    }


def collect_records_from_facts(
    pg_url: str = DEFAULT_PG_URL,
    *,
    chain_id: str | None = None,
    limit: int = 500,
) -> list[dict[str, Any]]:
    params: list[Any] = []
    chain_filter = ""
    if chain_id:
        chain_filter = "AND m.chain_id = %s"
        params.append(chain_id)
    patterns = [
        "%资本开支%", "%资本支出%", "%固定资产投资%", "%在建工程%", "%购建固定资产%",
        "%扩产%", "%产能%", "%产线%", "%项目建设%", "%建设项目%", "%设备投入%",
        "%设备购置%", "%数据中心%", "%智算中心%", "%服务器%", "%液冷%", "%募投项目%",
    ]
    params.extend([patterns, patterns])
    params.append(limit)
    sql = f"""
    SELECT
        f.fact_id,
        f.mapping_id,
        split_part(m.code, '.', 1) AS code,
        s.name,
        s.industry,
        m.tag_name,
        m.chain_id,
        m.node_id,
        f.fact_type,
        f.fact_value,
        f.original_quote,
        f.source_level,
        f.confidence,
        f.created_at
    FROM evidence_extracted_facts f
    JOIN business_tag_mapping m ON m.mapping_id = f.mapping_id
    LEFT JOIN stocks s ON s.code = split_part(m.code, '.', 1)
    WHERE COALESCE(m.status, '') <> 'rejected'
      {chain_filter}
      AND (
        f.original_quote ILIKE ANY (%s)
        OR COALESCE(f.fact_value, '') ILIKE ANY (%s)
      )
    ORDER BY f.created_at DESC
    LIMIT %s
    """
    records: list[dict[str, Any]] = []
    with psycopg2.connect(pg_url) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            columns = [desc[0] for desc in cur.description]
            for raw in cur.fetchall():
                record = build_record_from_fact(dict(zip(columns, raw)))
                if record:
                    records.append(record)
    return records


def emit_template(path: str | Path = DEFAULT_TEMPLATE_PATH) -> dict[str, Any]:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "records": [
            {
                "capex_evidence_id": "replace_with_mapping_period_direction",
                "mapping_id": "replace_with_business_tag_mapping_id",
                "code": "000001",
                "company_name": "公司名称",
                "chain_id": "ai_compute",
                "node_id": "replace_with_node_id",
                "fiscal_period": "2026H1",
                "report_date": "2026-08-30",
                "as_of_date": "2026-08-30",
                "capex_amount": None,
                "capex_amount_unit": "",
                "currency": "CNY",
                "capex_direction": ["AI服务器", "数据中心"],
                "mapped_layer_id": "infrastructure",
                "mapped_segments": ["AI服务器", "IDC"],
                "source_id": "annual_report",
                "source_type": "annual_report",
                "source_level": "strong",
                "source_name": "2026年半年度报告",
                "source_url": "",
                "quote": "粘贴公告或报告中的原文，不允许留空。",
                "evidence_level": "directional",
                "confidence": 0.8,
                "review_status": "pending_review",
                "amount_is_total_capex": False,
                "amount_is_segment_capex": False,
                "direction_is_ai_related": True,
                "metadata": {},
            }
        ]
    }
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"template_path": str(output_path), "record_count": len(payload["records"])}


def import_records(records: list[dict[str, Any]], pg_url: str = DEFAULT_PG_URL, *, dry_run: bool = False) -> dict[str, Any]:
    report = validate_records(records)
    if not report["valid"] or dry_run:
        return {**report, "dry_run": dry_run, "written_count": 0}
    sql = """
    INSERT INTO business_tag_capex_evidence (
        capex_evidence_id, mapping_id, code, company_name, chain_id, node_id,
        fiscal_period, report_date, as_of_date, capex_amount, capex_amount_unit,
        currency, capex_direction, mapped_layer_id, mapped_segments, source_id,
        source_type, source_level, source_name, source_url, quote, evidence_level,
        confidence, review_status, amount_is_total_capex, amount_is_segment_capex,
        direction_is_ai_related, metadata, updated_at
    )
    VALUES (
        %(capex_evidence_id)s, %(mapping_id)s, %(code)s, %(company_name)s, %(chain_id)s, %(node_id)s,
        %(fiscal_period)s, %(report_date)s, %(as_of_date)s, %(capex_amount)s, %(capex_amount_unit)s,
        %(currency)s, %(capex_direction)s::jsonb, %(mapped_layer_id)s, %(mapped_segments)s::jsonb, %(source_id)s,
        %(source_type)s, %(source_level)s, %(source_name)s, %(source_url)s, %(quote)s, %(evidence_level)s,
        %(confidence)s, %(review_status)s, %(amount_is_total_capex)s, %(amount_is_segment_capex)s,
        %(direction_is_ai_related)s, %(metadata)s::jsonb, CURRENT_TIMESTAMP
    )
    ON CONFLICT (capex_evidence_id) DO UPDATE SET
        mapping_id = EXCLUDED.mapping_id,
        code = EXCLUDED.code,
        company_name = EXCLUDED.company_name,
        chain_id = EXCLUDED.chain_id,
        node_id = EXCLUDED.node_id,
        fiscal_period = EXCLUDED.fiscal_period,
        report_date = EXCLUDED.report_date,
        as_of_date = EXCLUDED.as_of_date,
        capex_amount = EXCLUDED.capex_amount,
        capex_amount_unit = EXCLUDED.capex_amount_unit,
        currency = EXCLUDED.currency,
        capex_direction = EXCLUDED.capex_direction,
        mapped_layer_id = EXCLUDED.mapped_layer_id,
        mapped_segments = EXCLUDED.mapped_segments,
        source_id = EXCLUDED.source_id,
        source_type = EXCLUDED.source_type,
        source_level = EXCLUDED.source_level,
        source_name = EXCLUDED.source_name,
        source_url = EXCLUDED.source_url,
        quote = EXCLUDED.quote,
        evidence_level = EXCLUDED.evidence_level,
        confidence = EXCLUDED.confidence,
        review_status = EXCLUDED.review_status,
        amount_is_total_capex = EXCLUDED.amount_is_total_capex,
        amount_is_segment_capex = EXCLUDED.amount_is_segment_capex,
        direction_is_ai_related = EXCLUDED.direction_is_ai_related,
        metadata = EXCLUDED.metadata,
        updated_at = CURRENT_TIMESTAMP
    """
    with psycopg2.connect(pg_url) as conn:
        with conn.cursor() as cur:
            for record in report["accepted_records"]:
                payload = dict(record)
                payload["capex_direction"] = json.dumps(payload.get("capex_direction") or [], ensure_ascii=False)
                payload["mapped_segments"] = json.dumps(payload.get("mapped_segments") or [], ensure_ascii=False)
                payload["metadata"] = json.dumps(payload.get("metadata") or {}, ensure_ascii=False)
                cur.execute(sql, payload)
        conn.commit()
    return {**report, "dry_run": False, "written_count": report["accepted_count"]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate/import mapped-company CAPEX evidence")
    parser.add_argument("--input", help="JSON/JSONL evidence input")
    parser.add_argument("--pg-url", default=DEFAULT_PG_URL)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--emit-template", nargs="?", const=str(DEFAULT_TEMPLATE_PATH))
    parser.add_argument("--collect-from-facts", action="store_true", help="Build CAPEX candidates from evidence_extracted_facts")
    parser.add_argument("--chain-id", help="Optional chain_id filter for --collect-from-facts")
    parser.add_argument("--limit", type=int, default=500, help="Maximum facts to scan for --collect-from-facts")
    args = parser.parse_args(argv)
    if args.emit_template:
        print(json.dumps(emit_template(args.emit_template), ensure_ascii=False, indent=2))
        return 0
    if args.collect_from_facts:
        records = collect_records_from_facts(args.pg_url, chain_id=args.chain_id, limit=args.limit)
        report = import_records(records, args.pg_url, dry_run=args.dry_run)
        report["collection"] = {
            "source": "evidence_extracted_facts",
            "chain_id": args.chain_id,
            "limit": args.limit,
            "candidate_count": len(records),
        }
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
        return 0 if report["valid"] else 1
    if not args.input:
        parser.error("--input is required unless --emit-template is used")
    records = load_records(args.input)
    report = import_records(records, args.pg_url, dry_run=args.dry_run)
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
