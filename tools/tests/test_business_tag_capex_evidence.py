import importlib.util
import json
import sys
from pathlib import Path


_SCRIPT_PATH = Path(__file__).resolve().parents[1] / "business_tag_capex_evidence.py"
_SPEC = importlib.util.spec_from_file_location("business_tag_capex_evidence", _SCRIPT_PATH)
module = importlib.util.module_from_spec(_SPEC)
assert _SPEC and _SPEC.loader
sys.modules[_SPEC.name] = module
_SPEC.loader.exec_module(module)


def valid_record():
    return {
        "capex_evidence_id": "capex-auto-300308-2026h1-ai-server",
        "mapping_id": "auto_300308_ai_compute_hardware",
        "code": "300308",
        "company_name": "中际旭创",
        "chain_id": "ai_compute",
        "node_id": "infrastructure",
        "fiscal_period": "2026H1",
        "report_date": "2026-08-30",
        "as_of_date": "2026-08-30",
        "capex_amount": 12000,
        "capex_amount_unit": "CNY万元",
        "currency": "CNY",
        "capex_direction": ["高速光模块产能", "AI数据中心"],
        "mapped_layer_id": "infrastructure",
        "mapped_segments": ["高速光模块", "AI 数据中心"],
        "source_id": "annual_report",
        "source_type": "annual_report",
        "source_level": "strong",
        "source_name": "2026年半年度报告",
        "source_url": "https://example.com/report.pdf",
        "quote": "公司资本开支主要投向高速光模块产能扩张和AI数据中心客户需求配套。",
        "evidence_level": "reported",
        "confidence": 0.85,
        "review_status": "approved",
        "amount_is_total_capex": False,
        "amount_is_segment_capex": True,
        "direction_is_ai_related": True,
        "metadata": {"page": 12},
    }


def test_validate_accepts_valid_capex_record():
    report = module.validate_records([valid_record()])

    assert report["valid"] is True
    assert report["accepted_count"] == 1
    assert report["accepted_records"][0]["review_status"] == "approved"


def test_validate_rejects_missing_quote():
    record = valid_record()
    record["quote"] = ""

    report = module.validate_records([record])

    assert report["valid"] is False
    assert "quote" in report["errors"][0]["message"]


def test_validate_rejects_missing_required_identity_fields():
    record = valid_record()
    record.pop("mapping_id")
    record["capex_direction"] = []

    report = module.validate_records([record])

    assert report["valid"] is False
    assert "mapping_id" in report["errors"][0]["message"]
    assert "capex_direction" in report["errors"][0]["message"]


def test_load_records_supports_jsonl(tmp_path):
    path = tmp_path / "capex.jsonl"
    path.write_text(json.dumps(valid_record(), ensure_ascii=False) + "\n", encoding="utf-8")

    records = module.load_records(path)

    assert len(records) == 1
    assert records[0]["code"] == "300308"


def test_emit_template_writes_valid_records(tmp_path):
    path = tmp_path / "template.json"
    result = module.emit_template(path)

    records = module.load_records(path)
    report = module.validate_records(records)

    assert result["record_count"] == 1
    assert report["valid"] is True


def test_build_record_from_fact_creates_pending_review_direction_evidence():
    record = module.build_record_from_fact({
        "fact_id": "FACT-1",
        "mapping_id": "18C-MAP-ai_compute-300308SZ",
        "code": "300308",
        "name": "中际旭创",
        "industry": "通信设备",
        "tag_name": "高速光模块",
        "chain_id": "ai_compute",
        "node_id": "infrastructure",
        "fact_type": "business_presence",
        "original_quote": "公司高速光模块需求强劲增长，进一步加大产能投入，服务AI数据中心客户。",
        "source_level": "mid",
        "confidence": 0.6,
        "created_at": "2026-07-07T09:39:04",
    })

    assert record is not None
    assert record["review_status"] == "pending_review"
    assert record["mapped_layer_id"] == "infrastructure"
    assert record["direction_is_ai_related"] is True
    assert "产能" in record["capex_direction"]
    assert record["quote"]


def test_build_record_from_fact_ignores_non_capex_text():
    record = module.build_record_from_fact({
        "fact_id": "FACT-2",
        "mapping_id": "m1",
        "code": "000001",
        "chain_id": "consumer_upgrade",
        "original_quote": "公司产品可用于多个下游场景，客户反馈良好。",
        "created_at": "2026-07-07T09:39:04",
    })

    assert record is None


def test_infer_layer_and_segments_routes_hbm_to_foundation():
    layer_id, segments = module.infer_layer_and_segments("HBM 和 CoWoS 先进封装产能扩张")

    assert layer_id == "foundation"
    assert segments
