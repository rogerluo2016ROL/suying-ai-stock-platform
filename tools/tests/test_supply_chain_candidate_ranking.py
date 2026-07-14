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


def test_bigtech_capex_tailwind_only_applies_to_ai_compute():
    context = {
        "company_count": 5,
        "record_count": 13,
        "companies": ["Alphabet", "Amazon", "Meta", "Microsoft", "Oracle"],
    }
    ai_row = {
        "chain_id": "ai_compute",
        "tag_name": "AI服务器",
        "node_id": "infrastructure",
        "industry": "通信设备",
    }
    other_row = {
        "chain_id": "consumer_upgrade",
        "tag_name": "品牌零售",
        "node_id": "retail",
    }

    ai_score = module.score_bigtech_capex_tailwind(ai_row, context)
    other_score = module.score_bigtech_capex_tailwind(other_row, context)

    assert ai_score["score"] > 0
    assert "infrastructure" in ai_score["matched_layers"]
    assert "CAPEX" in ai_score["expectation_gap_indicator"]
    assert other_score["score"] == 0


def test_score_candidate_exposes_capex_commercialization_gap_and_trigger_fields():
    context = {
        "company_count": 5,
        "record_count": 13,
        "companies": ["Alphabet", "Amazon", "Meta", "Microsoft", "Oracle"],
    }
    result = module.score_candidate({
        "chain_id": "ai_compute",
        "tag_name": "液冷服务器",
        "node_id": "infrastructure",
        "three_high_total": 70,
        "moat_score": 70,
        "stage_score": 70,
        "evidence_score": 70,
        "l8_match_rate": 0.8,
        "fresh_rate": 0.9,
        "expectation_gap_score": 20,
        "change_20d_pct": 5,
    }, context)

    assert result["score_parts"]["bigtech_capex_tailwind"] > 0
    assert result["bigtech_capex_tailwind"]["company_count"] == 5
    assert result["commercialization_indicator"]
    assert result["expectation_gap_indicator"]
    assert result["trigger_signal_indicator"]


def test_company_capex_evidence_scores_amount_direction_freshness_and_confidence():
    result = module.score_company_capex_evidence({
        "capex_evidence_count": 2,
        "capex_amount_count": 1,
        "capex_direction_ai_count": 2,
        "capex_fresh_count": 2,
        "capex_avg_confidence": 0.8,
        "capex_latest_as_of_date": "2026-08-30",
        "capex_directions": [["AI服务器", "数据中心"]],
    })

    assert result["score"] > 70
    assert result["amount_count"] == 1
    assert result["direction_ai_count"] == 2
    assert "AI相关投入方向" in result["indicator"]


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


def test_build_mapping_sql_excludes_rejected_and_requires_formal_token_pool():
    sql = module.build_mapping_sql("ai_token_output_power", formal_only=True)
    assert "COALESCE(m.status, '') NOT IN ('rejected', 'disabled')" in sql
    assert "m.chain_id = 'ai_token_output_power'" in sql
    assert "ps.pool_code IN ('A', 'B', 'C')" in sql
    assert "ps.evidence_grade IN ('E2', 'E3', 'E4', 'E5')" in sql
