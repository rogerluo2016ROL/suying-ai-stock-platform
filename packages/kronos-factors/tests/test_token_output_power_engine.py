import pytest

from kronos_factors.engine.token_output_power import (
    EvidenceFlags,
    calculate_billable_tokens,
    calculate_cost_per_million_tokens,
    calculate_opportunity_score,
    dedupe_evidence_ids,
    derive_evidence_grade,
    derive_pool_code,
    select_primary_mapping,
)


def test_billable_tokens_uses_all_five_factors():
    assert calculate_billable_tokens(10, 100, 0.5, 2000, 0.8) == 800000.0


def test_missing_capacity_returns_none_instead_of_zero():
    assert calculate_billable_tokens(10, None, 0.5, 2000, 0.8) is None


def test_invalid_utilization_is_rejected():
    with pytest.raises(ValueError, match="utilization"):
        calculate_billable_tokens(10, 100, 1.2, 2000, 0.8)


def test_cost_per_million_tokens_is_cost_sum_divided_by_billable_tokens():
    assert calculate_cost_per_million_tokens(100, 200, 50, 25, 10, 15, 1000000) == 400.0


def test_evidence_grade_and_pool_do_not_use_market_signal():
    flags = EvidenceFlags(power_or_plan=True, facility_built=True, runtime=True, commercial=True, recurring_profit=False)
    assert derive_evidence_grade(flags) == "E4"
    assert derive_pool_code("E4", has_customer_validation=True, has_token_revenue=True, has_profit=False, veto=False) == "B"
    assert derive_pool_code("E4", has_customer_validation=True, has_token_revenue=True, has_profit=True, veto=False) == "A"


def test_market_signal_cannot_admit_e0_to_formal_pool():
    assert calculate_opportunity_score("D", 90, 90, 90, 100) is None
    assert calculate_opportunity_score("B", 80, 70, 60, 50) == 16.8


def test_evidence_ids_are_deduplicated_and_primary_mapping_uses_evidence_then_benefit():
    assert dedupe_evidence_ids(["e1", "e1", "e2", "", None]) == ["e1", "e2"]
    rows = [
        {"mapping_id": "m1", "evidence_grade": "E3", "benefit_score": 90},
        {"mapping_id": "m2", "evidence_grade": "E4", "benefit_score": 60},
    ]
    assert select_primary_mapping(rows)["mapping_id"] == "m2"
