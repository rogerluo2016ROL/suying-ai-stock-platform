"""Ablation contracts for supply-chain research selection V2."""

from __future__ import annotations

import importlib.util
from datetime import date
from pathlib import Path


MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "backtest_supply_chain_research_selection_v2.py"
)
SPEC = importlib.util.spec_from_file_location(
    "backtest_supply_chain_research_selection_v2",
    MODULE_PATH,
)
assert SPEC is not None and SPEC.loader is not None
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def test_seven_ablation_variants_are_fixed():
    assert module.ABLATIONS == (
        "v1",
        "v2_full",
        "v2_without_dimensions",
        "v2_without_market_expectation",
        "v2_without_risk_penalty",
        "v2_three_high_only",
        "v2_evidence_stage_only",
    )


def test_full_candidate_ranking_can_select_stock_not_in_snapshot_subset():
    rows = [
        {
            "trade_date": date(2026, 7, 1),
            "code": "000001.SZ",
            "mapping_id": "m1",
            "pool_code": "A",
            "eligibility_status": "eligible",
            "veto_reasons": [],
            "evidence_level": "E4",
            "benefit_score": 60,
            "opportunity_score": 55,
            "entry_open": 10,
            "entry_adj": 1,
            "exit_close": 11,
            "exit_adj": 1,
        },
        {
            "trade_date": date(2026, 7, 1),
            "code": "000002.SZ",
            "mapping_id": "m2",
            "pool_code": "B",
            "eligibility_status": "eligible",
            "veto_reasons": [],
            "evidence_level": "E3",
            "benefit_score": 80,
            "opportunity_score": 75,
            "entry_open": 10,
            "entry_adj": 1,
            "exit_close": 12,
            "exit_adj": 1,
        },
        {
            "trade_date": date(2026, 7, 1),
            "code": "000003.SZ",
            "mapping_id": "m3",
            "pool_code": "D",
            "eligibility_status": "watch",
            "veto_reasons": [],
            "evidence_level": "E1",
            "benefit_score": 99,
            "opportunity_score": 99,
        },
    ]

    selected = module.rank_full_candidate_set(
        rows,
        variant="v2_full",
        top_n=1,
    )

    assert [row["code"] for row in selected] == ["000002"]
    assert selected[0]["source_scope"] == "full_historical_candidate_set"


def test_v1_ablation_refuses_to_invent_unfrozen_legacy_score():
    assert module.ablation_score({"opportunity_score": 80}, "v1") is None


def test_ablation_report_is_insufficient_when_adjustment_factor_is_missing():
    report = module.evaluate_ablation_rows(
        [
            {
                "trade_date": date(2026, 7, 1),
                "pool_code": "A",
                "entry_open": 10,
                "entry_adj": None,
                "exit_close": 11,
                "exit_adj": 1,
            }
        ],
        cost_bps=14,
        min_dates=1,
        min_observations=1,
    )

    assert report["status"] == "INSUFFICIENT_EVIDENCE"
    assert report["coverage"]["missing_adj_factor_count"] == 1
