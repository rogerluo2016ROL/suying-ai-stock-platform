import importlib.util
import sys
from pathlib import Path


_SCRIPT_PATH = Path(__file__).resolve().parents[1] / "audit_supply_chain_data_quality.py"
_SPEC = importlib.util.spec_from_file_location("audit_supply_chain_data_quality", _SCRIPT_PATH)
module = importlib.util.module_from_spec(_SPEC)
assert _SPEC and _SPEC.loader
sys.modules[_SPEC.name] = module
_SPEC.loader.exec_module(module)


def test_quality_score_penalizes_thin_mapping_and_evidence():
    row = module.score_chain_quality({
        "chain_id": "quantum_technology",
        "mapping_count": 5,
        "company_count": 5,
        "fact_count": 8,
        "l8_status_count": 10,
        "stage_count": 1,
        "score_count": 5,
        "fresh_count": 2,
        "stale_count": 2,
        "expired_count": 1,
        "unknown_count": 0,
    })

    assert row["quality_grade"] == "D"
    assert "补公司/标签映射" in row["priority_actions"]
    assert "补结构化证据" in row["priority_actions"]
    assert row["risk_level"] == "high"


def test_quality_score_marks_dense_fresh_chain_as_good():
    row = module.score_chain_quality({
        "chain_id": "ai_compute",
        "mapping_count": 2000,
        "company_count": 1000,
        "fact_count": 30000,
        "l8_status_count": 16000,
        "stage_count": 2200,
        "score_count": 2000,
        "fresh_count": 1980,
        "stale_count": 10,
        "expired_count": 5,
        "unknown_count": 5,
    })

    assert row["quality_grade"] in {"A", "B"}
    assert row["risk_level"] in {"low", "medium"}
    assert row["quality_score"] >= 75


def test_rank_chains_puts_high_risk_first():
    rows = [
        module.score_chain_quality({"chain_id": "good", "mapping_count": 100, "company_count": 80, "fact_count": 800, "l8_status_count": 700, "stage_count": 90, "score_count": 100, "fresh_count": 95, "stale_count": 3, "expired_count": 1, "unknown_count": 1}),
        module.score_chain_quality({"chain_id": "bad", "mapping_count": 4, "company_count": 4, "fact_count": 2, "l8_status_count": 0, "stage_count": 0, "score_count": 4, "fresh_count": 0, "stale_count": 1, "expired_count": 1, "unknown_count": 2}),
    ]

    ranked = module.rank_chains_for_repair(rows)

    assert ranked[0]["chain_id"] == "bad"
    assert ranked[0]["repair_priority"] == 1
