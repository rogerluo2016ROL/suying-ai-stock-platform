from __future__ import annotations

import importlib.util
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "register_supply_chain_expectation_gap_model.py"
SPEC = importlib.util.spec_from_file_location("register_supply_chain_expectation_gap_model", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


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
            "gap_momentum_score": 62.5,
            "three_high_total": 78.96,
            "signal_tier": "strong",
            "chain_id": "ai_compute",
            "tag_name": "高速光模块",
            "gap_type": "positive",
            "unused": "ignored",
        }
    )

    assert payload["model_score"] == 70.14
    assert payload["expectation_gap_score"] == 47.74
    assert payload["gap_momentum_score"] == 62.5
    assert payload["three_high_total"] == 78.96
    assert payload["signal_tier"] == "strong"
    assert payload["chain_id"] == "ai_compute"
    assert payload["tag_name"] == "高速光模块"
    assert payload["gap_type"] == "positive"
    assert "unused" not in payload
