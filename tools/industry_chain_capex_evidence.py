#!/usr/bin/env python3
"""Validate manually collected big-tech CAPEX evidence for complex-tech templates."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "packages" / "kronos-factors" / "configs" / "industry_chain_templates.json"
DEFAULT_TASK_ID = "collect_bigtech_ai_capex"


def load_config(config_path: str | Path = DEFAULT_CONFIG_PATH) -> dict[str, Any]:
    path = Path(config_path)
    return json.loads(path.read_text(encoding="utf-8"))


def _find_task(config: dict[str, Any], task_id: str) -> dict[str, Any]:
    for task in config.get("collection_task_catalog", []):
        if task.get("task_id") == task_id:
            return task
    valid = [task.get("task_id") for task in config.get("collection_task_catalog", [])]
    raise ValueError(f"Unknown collection task '{task_id}', valid tasks: {valid}")


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
    raise ValueError("Input must be a JSON list, JSON object with records/capex_evidence, or JSONL")


def build_template_records(
    config_path: str | Path = DEFAULT_CONFIG_PATH,
    *,
    task_id: str = DEFAULT_TASK_ID,
) -> list[dict[str, Any]]:
    config = load_config(config_path)
    task = _find_task(config, task_id)
    source_id = task["source_ids"][0]
    source_name = "SEC filing / investor relations / earnings call"
    examples: list[dict[str, Any]] = []
    layer_segments = {
        "demand": ["云厂商资本开支", "AI 数据中心"],
        "foundation": ["HBM", "CoWoS", "先进封装"],
        "infrastructure": ["IDC", "液冷", "高功率机柜"],
    }
    for layer_id in task.get("target_layers", []):
        if layer_id == "macro_context":
            continue
        examples.append({
            "evidence_id": f"replace_with_company_{layer_id}_capex_period",
            "source_id": source_id,
            "company": "REPLACE_WITH_COMPANY",
            "fiscal_period": "REPLACE_WITH_FISCAL_PERIOD",
            "capex_direction": ["REPLACE_WITH_CAPEX_DIRECTION"],
            "mapped_layer_id": layer_id,
            "mapped_segments": layer_segments.get(layer_id, ["REPLACE_WITH_SEGMENT"]),
            "source_type": "earnings_call",
            "source_name": source_name,
            "source_url": "",
            "quote": "PASTE_ORIGINAL_QUOTE_HERE",
            "as_of_date": "YYYY-MM-DD",
            "evidence_level": "reported",
        })
    return examples


def _missing_required_fields(record: dict[str, Any], required_fields: list[str]) -> list[str]:
    missing = []
    for field in required_fields:
        value = record.get(field)
        if value is None or value == "" or value == []:
            missing.append(field)
    return missing


def validate_records(
    records: list[dict[str, Any]],
    config_path: str | Path = DEFAULT_CONFIG_PATH,
    *,
    task_id: str = DEFAULT_TASK_ID,
) -> dict[str, Any]:
    config = load_config(config_path)
    task = _find_task(config, task_id)
    required_fields = list(task.get("output_contract", {}).get("required_fields", []))
    valid_sources = set(task.get("source_ids", []))
    valid_layers = set(task.get("target_layers", []))
    errors: list[dict[str, Any]] = []
    accepted: list[dict[str, Any]] = []

    for index, record in enumerate(records):
        record_errors = []
        missing = _missing_required_fields(record, required_fields)
        if missing:
            record_errors.append(f"missing required fields: {', '.join(missing)}")
        source_id = record.get("source_id")
        if source_id not in valid_sources:
            record_errors.append(f"source_id must be one of {sorted(valid_sources)}")
        mapped_layer_id = record.get("mapped_layer_id")
        if mapped_layer_id not in valid_layers:
            record_errors.append(f"mapped_layer_id must be one of {sorted(valid_layers)}")
        if not record.get("mapped_segments"):
            record_errors.append("mapped_segments must not be empty")
        if not record.get("capex_direction"):
            record_errors.append("capex_direction must not be empty")

        if record_errors:
            errors.append({
                "index": index,
                "evidence_id": record.get("evidence_id"),
                "message": "; ".join(record_errors),
            })
        else:
            accepted.append(record)

    return {
        "valid": not errors,
        "task_id": task_id,
        "input_count": len(records),
        "accepted_count": len(accepted),
        "errors": errors,
        "accepted_records": accepted,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate complex-tech big-tech CAPEX evidence records")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH))
    parser.add_argument("--task-id", default=DEFAULT_TASK_ID)
    parser.add_argument("--input", help="JSON or JSONL evidence file to validate")
    parser.add_argument("--emit-template", help="Write a JSON evidence template to this path")
    args = parser.parse_args(argv)

    if args.emit_template:
        records = build_template_records(args.config, task_id=args.task_id)
        output_path = Path(args.emit_template)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps({"records": records}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"template_path": str(output_path), "record_count": len(records)}, ensure_ascii=False, indent=2))
        return 0

    if not args.input:
        parser.error("--input is required unless --emit-template is used")

    records = load_records(args.input)
    report = validate_records(records, args.config, task_id=args.task_id)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
