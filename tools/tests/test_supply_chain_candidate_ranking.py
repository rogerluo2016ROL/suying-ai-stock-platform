import importlib.util
import sys
from pathlib import Path


_SCRIPT_PATH = Path(__file__).resolve().parents[1] / "build_supply_chain_candidate_ranking.py"
_SPEC = importlib.util.spec_from_file_location("build_supply_chain_candidate_ranking", _SCRIPT_PATH)
module = importlib.util.module_from_spec(_SPEC)
assert _SPEC and _SPEC.loader
sys.modules[_SPEC.name] = module
_SPEC.loader.exec_module(module)


def test_rank_score_prioritizes_tag_evidence_over_short_term_momentum():
    strong = module.score_candidate({
        "three_high_total": 82,
        "moat_score": 88,
        "stage_score": 76,
        "evidence_score": 90,
        "l8_match_rate": 0.9,
        "fresh_rate": 0.95,
        "expectation_gap_score": 20,
        "change_20d_pct": -5,
    })
    hype = module.score_candidate({
        "three_high_total": 50,
        "moat_score": 45,
        "stage_score": 35,
        "evidence_score": 35,
        "l8_match_rate": 0.2,
        "fresh_rate": 0.2,
        "expectation_gap_score": -20,
        "change_20d_pct": 45,
    })

    assert strong["rank_score"] > hype["rank_score"]
    assert strong["signal"] == "重点候选"
    assert hype["signal"] in {"观察", "暂缓"}


def test_expectation_gap_is_normalized_and_clamped():
    assert module.normalize_expectation_gap(1000) == 100
    assert module.normalize_expectation_gap(-1000) == 0
    assert module.normalize_expectation_gap(0) == 50


def test_aggregate_company_chain_keeps_best_mapping_and_counts_tags():
    rows = [
        {"code": "300503", "name": "昊志机电", "chain_id": "embodied_intelligence", "mapping_id": "m1", "tag_name": "关节模组", "rank_score": 70},
        {"code": "300503", "name": "昊志机电", "chain_id": "embodied_intelligence", "mapping_id": "m2", "tag_name": "六维力", "rank_score": 82},
    ]

    result = module.aggregate_company_chain(rows)[0]

    assert result["code"] == "300503"
    assert result["tag_count"] == 2
    assert result["best_mapping_id"] == "m2"
    assert result["best_tag_name"] == "六维力"
