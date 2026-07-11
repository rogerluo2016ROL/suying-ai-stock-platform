"""Pure scoring contracts for supply-chain research selection V2."""

import pytest

from kronos_factors.scorer.supply_chain_selection_v2 import (
    ScoreResult,
    aggregate_stock_mappings,
    assign_selection_pool,
    score_authenticity,
    score_company_benefit,
    score_node_attractiveness,
    score_operating_quality,
    score_selection_opportunity,
    weighted_available_score,
)


def test_weighted_scores_keep_unknown_as_none():
    result = score_node_attractiveness(
        {
            "demand_certainty": None,
            "value_pool_score": None,
            "bottleneck_score": None,
            "supply_demand_score": None,
            "technology_maturity_score": None,
            "commercialization_score": None,
            "transmission_score": None,
            "evidence_quality_score": None,
        }
    )

    assert result == ScoreResult(
        score=None,
        coverage_ratio=0.0,
        detail={"status": "unknown"},
    )


def test_weighted_available_score_reweights_only_known_values():
    result = weighted_available_score(
        {"first": 80, "second": None},
        {"first": 0.25, "second": 0.75},
    )

    assert result.score == 80.0
    assert result.coverage_ratio == 0.25
    assert result.detail["known_fields"] == ["first"]


def test_weighted_available_score_rejects_invalid_weights_and_values():
    with pytest.raises(ValueError, match="sum to 1.0"):
        weighted_available_score({"first": 50}, {"first": 0.5})
    with pytest.raises(ValueError, match="between 0 and 100"):
        weighted_available_score({"first": 101}, {"first": 1.0})


def test_authenticity_is_a_multiplier_not_an_additive_bonus():
    benefit = score_company_benefit(
        {
            "node_attractiveness": 80,
            "operating_quality_score": 80,
            "revenue_exposure_score": 80,
            "order_certainty_score": 80,
            "profit_elasticity_score": 80,
            "delivery_capability_score": 80,
        },
        authenticity_score=50,
    )

    assert benefit.score == 40.0
    assert benefit.detail["benefit_raw"] == 80.0


def test_unknown_authenticity_does_not_become_zero_benefit():
    benefit = score_company_benefit(
        {"node_attractiveness": 80},
        authenticity_score=None,
    )

    assert benefit.score is None
    assert benefit.detail["status"] == "unknown_authenticity"


def test_growth_caps_only_expansion_without_orders_at_55():
    result = score_operating_quality(
        growth={
            "realized_revenue_growth": None,
            "backlog_growth": None,
            "customer_share_growth": None,
            "delivery_growth": 90,
            "growth_sustainability": None,
        },
        profit={},
        moat={},
        growth_cap=55,
    )

    assert result.detail["growth_score"] == 55.0
    assert "growth_cap:55" in result.detail["cap_hits"]
    assert result.detail["profit_score"] is None
    assert result.detail["profit_coverage"] == 0.0


def test_authenticity_score_uses_available_evidence_without_zero_filling():
    result = score_authenticity(
        {
            "product_evidence_score": 80,
            "customer_evidence_score": None,
            "order_revenue_evidence_score": None,
            "source_reliability_score": 60,
            "freshness_score": None,
        }
    )

    assert result.score == 75.0
    assert result.coverage_ratio == 0.4


def test_selection_score_requires_all_four_inputs():
    result = score_selection_opportunity(
        {
            "benefit_score": 70,
            "expectation_gap_score": 60,
            "catalyst_score": None,
            "risk_score": 20,
        }
    )

    assert result.score is None
    assert result.coverage_ratio == 0.75
    assert result.detail["status"] == "insufficient_evidence"


def test_pool_assignment_uses_hard_evidence_gates():
    base = {
        "commercial_stage": "C4",
        "authenticity_score": 80,
        "confidence_score": 75,
        "benefit_score": 70,
        "operating_quality_coverage": 0.8,
        "has_veto": False,
        "has_order_or_delivery_evidence": True,
        "has_product_evidence": True,
        "has_customer_validation": True,
        "has_next_validation": True,
    }

    assert assign_selection_pool({**base, "evidence_level": "E4"})["pool_code"] == "A"
    assert assign_selection_pool({**base, "evidence_level": "E3"})["pool_code"] == "B"
    assert (
        assign_selection_pool(
            {**base, "evidence_level": "E2", "has_customer_validation": False}
        )["pool_code"]
        == "C"
    )
    assert (
        assign_selection_pool(
            {**base, "evidence_level": "E1", "has_product_evidence": False}
        )["pool_code"]
        == "D"
    )


def test_veto_and_e0_are_not_selection_pool_members():
    vetoed = assign_selection_pool(
        {
            "evidence_level": "E6",
            "has_veto": True,
            "veto_reasons": ["mapping_contradicted"],
        }
    )
    rumor = assign_selection_pool({"evidence_level": "E0", "has_veto": False})

    assert vetoed["pool_code"] is None
    assert vetoed["eligibility_status"] == "rejected"
    assert rumor["pool_code"] is None
    assert rumor["eligibility_status"] == "excluded"


def test_multiple_mappings_choose_one_primary_and_cap_independent_bonus():
    selected = aggregate_stock_mappings(
        [
            {
                "code": "000001",
                "mapping_id": "m1",
                "benefit_score": 72,
                "evidence_level": "E4",
                "independent_revenue": True,
            },
            {
                "code": "000001",
                "mapping_id": "m2",
                "benefit_score": 65,
                "evidence_level": "E3",
                "independent_revenue": True,
            },
            {
                "code": "000001",
                "mapping_id": "m3",
                "benefit_score": 60,
                "evidence_level": "E2",
                "independent_revenue": False,
            },
            {
                "code": "000001",
                "mapping_id": "m4",
                "benefit_score": 55,
                "evidence_level": "E2",
                "independent_revenue": True,
            },
        ]
    )[0]

    assert selected["primary_mapping_id"] == "m1"
    assert selected["diversification_bonus"] == 5.0
    assert selected["stock_score"] == 77.0
    assert [row["mapping_id"] for row in selected["secondary_mappings"]] == [
        "m2",
        "m3",
        "m4",
    ]


def test_stock_aggregation_keeps_unknown_score_null_and_normalizes_code():
    selected = aggregate_stock_mappings(
        [
            {
                "code": "603662.SH",
                "mapping_id": "m1",
                "benefit_score": None,
                "evidence_level": "E1",
                "independent_revenue": False,
            },
            {
                "code": "603662",
                "mapping_id": "m2",
                "benefit_score": None,
                "evidence_level": "E1",
                "independent_revenue": False,
            },
        ]
    )

    assert len(selected) == 1
    assert selected[0]["code"] == "603662"
    assert selected[0]["stock_score"] is None
    assert len(selected[0]["secondary_mappings"]) == 1
