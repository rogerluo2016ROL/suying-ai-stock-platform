from __future__ import annotations

import importlib.util
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "register_supply_chain_expectation_gap_model.py"
SPEC = importlib.util.spec_from_file_location("register_supply_chain_expectation_gap_model", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def test_registered_model_identity_is_explicit() -> None:
    assert module.MODEL_KEY == "supply_chain_expectation_gap_v1"
    assert module.MODEL_NAME == "产业链预期差选股模型"
    assert module.DISPLAY_NAME == "产业链预期差选股模型 V1.0"


def test_grade_from_score_boundaries() -> None:
    assert module.grade_from_score(65) == "S"
    assert module.grade_from_score(55) == "A"
    assert module.grade_from_score(45) == "B"
    assert module.grade_from_score(44.99) == "C"


def test_signal_tier_from_gap_boundaries() -> None:
    assert module.signal_tier_from_gap(15) == "strong"
    assert module.signal_tier_from_gap(8) == "watch"
    assert module.signal_tier_from_gap(3) == "early"
    assert module.signal_tier_from_gap(2.99) == "none"


def test_factor_payload_keeps_scores_and_metadata() -> None:
    payload = module.factor_payload(
        {
            "model_score": 70.14,
            "expectation_gap_score": 47.74,
            "reliability_adjusted_gap_score": 31.46,
            "evidence_quality_score": 98,
            "label_fit_score": 93,
            "gap_momentum_score": 62.5,
            "three_high_total": 78.96,
            "reassessment_status": "watch_review",
            "signal_tier": "strong",
            "chain_id": "ai_compute",
            "tag_name": "高速光模块",
            "gap_type": "positive",
            "unused": "ignored",
        }
    )

    assert payload["model_score"] == 70.14
    assert payload["expectation_gap_score"] == 47.74
    assert payload["reliability_adjusted_gap_score"] == 31.46
    assert payload["evidence_quality_score"] == 98
    assert payload["label_fit_score"] == 93
    assert payload["gap_momentum_score"] == 62.5
    assert payload["three_high_total"] == 78.96
    assert payload["reassessment_status"] == "watch_review"
    assert payload["signal_tier"] == "strong"
    assert payload["chain_id"] == "ai_compute"
    assert payload["tag_name"] == "高速光模块"
    assert payload["gap_type"] == "positive"
    assert "unused" not in payload


def test_model_score_uses_reliability_adjusted_gap_and_quality_gate() -> None:
    strong_row = {
        "expectation_gap_score": 80,
        "reliability_adjusted_gap_score": 20,
        "gap_momentum_score": 60,
        "three_high_total": 70,
        "evidence_delta_score": 90,
        "moat_score": 75,
        "prosperity_score": 55,
        "price_change_20d": 10,
        "evidence_quality_score": 80,
        "label_fit_score": 75,
        "reassessment_status": "watch_review",
    }
    weak_row = {
        **strong_row,
        "reliability_adjusted_gap_score": 5,
        "evidence_quality_score": 20,
        "label_fit_score": 40,
        "reassessment_status": "downgrade_or_remove",
    }

    assert module.is_reassessment_eligible(strong_row)
    assert not module.is_reassessment_eligible(weak_row)
    assert module.model_score_from_row(strong_row) < module.model_score_from_row({
        **strong_row,
        "reliability_adjusted_gap_score": 40,
    })
