import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.industry_chain_capex_evidence import (
    build_template_records,
    load_records,
    validate_records,
)


CONFIG_PATH = Path("packages/kronos-factors/configs/industry_chain_templates.json")


def _valid_capex_record() -> dict:
    return {
        "evidence_id": "msft_ai_capex_2026q2",
        "source_id": "company_investor_relations",
        "company": "Microsoft",
        "fiscal_period": "2026Q2",
        "capex_direction": ["AI data center", "GPU cluster"],
        "mapped_layer_id": "infrastructure",
        "mapped_segments": ["IDC", "液冷", "AI服务器"],
        "source_type": "earnings_call",
        "source_name": "Microsoft FY2026 Q2 earnings call",
        "source_url": "https://example.com/msft-call",
        "quote": "We continue to invest in AI infrastructure and data center capacity.",
        "as_of_date": "2026-07-08",
        "evidence_level": "reported",
    }


def test_build_template_records_matches_capex_task_contract():
    records = build_template_records(CONFIG_PATH, task_id="collect_bigtech_ai_capex")

    assert len(records) >= 3
    assert {"demand", "foundation", "infrastructure"} <= {record["mapped_layer_id"] for record in records}
    for record in records:
        assert record["source_id"] in {"sec_company_filings", "company_investor_relations"}
        assert record["quote"]
        assert record["source_url"] == ""
        assert record["evidence_level"] == "reported"


def test_validate_records_accepts_valid_capex_record():
    report = validate_records([_valid_capex_record()], CONFIG_PATH, task_id="collect_bigtech_ai_capex")

    assert report["valid"] is True
    assert report["accepted_count"] == 1
    assert report["errors"] == []


def test_validate_records_rejects_missing_quote():
    record = _valid_capex_record()
    record["quote"] = ""

    report = validate_records([record], CONFIG_PATH, task_id="collect_bigtech_ai_capex")

    assert report["valid"] is False
    assert report["accepted_count"] == 0
    assert any("quote" in error["message"] for error in report["errors"])


def test_validate_records_rejects_invalid_layer():
    record = _valid_capex_record()
    record["mapped_layer_id"] = "supporting"

    report = validate_records([record], CONFIG_PATH, task_id="collect_bigtech_ai_capex")

    assert report["valid"] is False
    assert report["accepted_count"] == 0
    assert any("mapped_layer_id" in error["message"] for error in report["errors"])


def test_load_records_supports_json_and_jsonl(tmp_path):
    records = [_valid_capex_record()]
    json_path = tmp_path / "capex.json"
    jsonl_path = tmp_path / "capex.jsonl"
    json_path.write_text(json.dumps({"records": records}, ensure_ascii=False), encoding="utf-8")
    jsonl_path.write_text(json.dumps(records[0], ensure_ascii=False) + "\n", encoding="utf-8")

    assert load_records(json_path) == records
    assert load_records(jsonl_path) == records
