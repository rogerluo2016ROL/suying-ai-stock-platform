"""Pure scoring contracts for supply-chain research selection V2."""

from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
from datetime import date, datetime, timedelta

import pytest

from kronos_factors.engine.industry_chain_evidence_requirements import (
    load_evidence_requirements,
)
from kronos_factors.engine.industry_chain_templates import get_industry_template
from kronos_factors.scorer import supply_chain_selection_v2 as selection_v2

from kronos_factors.scorer.supply_chain_selection_v2 import (
    ApprovedScoreInput,
    ExpectationGapInputs,
    ScoreResult,
    aggregate_catalyst_score,
    aggregate_risk_score,
    aggregate_stock_mappings,
    assign_selection_pool,
    calculate_actual_progress_score,
    calculate_approved_expectation_gap,
    score_authenticity,
    score_company_benefit,
    score_node_attractiveness,
    score_operating_quality,
    score_selection_opportunity,
    weighted_available_score,
)


AS_OF_DATE = date(2026, 7, 9)


def test_approved_expectation_gap_uses_formula_without_neutral_fill():
    inputs = ExpectationGapInputs(
        actual_progress_score=80,
        market_expectation_score=50,
        evidence_delta_score=40,
        claim_risk_penalty_score=20,
        evidence_ids=("progress-1", "expectation-1"),
    )

    assert calculate_approved_expectation_gap(inputs) == 35.0
    assert (
        calculate_approved_expectation_gap(
            replace(inputs, market_expectation_score=None)
        )
        is None
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("actual_progress_score", -0.01),
        ("market_expectation_score", 100.01),
        ("evidence_delta_score", float("nan")),
        ("claim_risk_penalty_score", float("inf")),
        ("market_expectation_score", "50"),
    ],
)
def test_approved_expectation_gap_rejects_non_finite_or_out_of_range_inputs(
    field,
    value,
):
    inputs = ExpectationGapInputs(80, 50, 40, 20, ("e1",))

    assert calculate_approved_expectation_gap(replace(inputs, **{field: value})) is None


def test_actual_progress_requires_valid_stage_ranks_and_preserves_boundaries():
    assert calculate_actual_progress_score(0, 0, 0) == 0.0
    assert calculate_actual_progress_score(6, 7, 100) == 100.0
    with pytest.raises(ValueError, match="research_rank"):
        calculate_actual_progress_score(7, 7, 100)
    with pytest.raises(ValueError, match="commercialization_rank"):
        calculate_actual_progress_score(6, -1, 100)


def test_catalyst_aggregates_only_explicit_reviewed_scores():
    result = aggregate_catalyst_score(
        [
            ApprovedScoreInput("c1", 80, "strong", 1.0, 0.9),
            ApprovedScoreInput("c2", 60, "mid", 0.5, 0.7),
        ]
    )

    assert result.score == 74.4
    assert result.evidence_ids == ("c1", "c2")


def test_catalyst_rejects_weak_invalid_zero_weight_and_blank_ids():
    result = aggregate_catalyst_score(
        [
            ApprovedScoreInput("weak", 99, "weak", 1.0, 1.0),
            ApprovedScoreInput("range", 101, "strong", 1.0, 1.0),
            ApprovedScoreInput("confidence", 80, "strong", 1.1, 1.0),
            ApprovedScoreInput("reliability", 80, "strong", 1.0, -0.1),
            ApprovedScoreInput("zero", 80, "strong", 0.0, 1.0),
            ApprovedScoreInput("", 80, "strong", 1.0, 1.0),
            ApprovedScoreInput("nan", float("nan"), "strong", 1.0, 1.0),
            ApprovedScoreInput("string", "80", "strong", 1.0, 1.0),
        ]
    )

    assert result.score is None
    assert result.evidence_ids == ()


def test_catalyst_deduplicates_evidence_ids_deterministically():
    result = aggregate_catalyst_score(
        [
            ApprovedScoreInput("c2", 60, "mid", 0.5, 0.7),
            ApprovedScoreInput("c1", 80, "strong", 1.0, 0.9),
            ApprovedScoreInput("c1", 80, "strong", 1.0, 0.9),
        ]
    )

    assert result.evidence_ids == ("c1", "c2")


def test_risk_uses_worst_explicit_reviewed_risk_and_all_tied_ids():
    result = aggregate_risk_score(
        [
            ApprovedScoreInput("r-low", 40, "strong", 0.9, 0.9),
            ApprovedScoreInput("r2", 70, "mid", 0.8, 0.7),
            ApprovedScoreInput("r1", 70, "strong", 0.9, 0.9),
            ApprovedScoreInput("r1", 70, "strong", 0.9, 0.9),
        ]
    )

    assert result.score == 70.0
    assert result.evidence_ids == ("r1", "r2")


def test_ordinary_risk_does_not_reject_but_explicit_veto_still_does():
    ordinary = assign_selection_pool(
        {"evidence_level": "E1", "risk_score": 100, "has_veto": False}
    )
    vetoed = assign_selection_pool(
        {
            "evidence_level": "E4",
            "risk_score": 20,
            "has_veto": True,
            "veto_reasons": ["customer_cancelled"],
        }
    )

    assert ordinary["eligibility_status"] == "watch"
    assert ordinary["pool_code"] == "D"
    assert vetoed["eligibility_status"] == "rejected"
    assert vetoed["veto_reasons"] == ["customer_cancelled"]


@pytest.mark.parametrize("invalid", [float("nan"), float("inf"), -float("inf")])
def test_selection_opportunity_rejects_non_finite_explicit_scores(invalid):
    with pytest.raises(ValueError, match="between 0 and 100"):
        score_selection_opportunity(
            {
                "benefit_score": 60,
                "expectation_gap_score": 50,
                "catalyst_score": 40,
                "risk_score": invalid,
            }
        )


def reviewed_fact(
    fact_id,
    fact_type,
    *,
    metadata=None,
    source_level="strong",
    fact_nature="confirmed_fact",
    publish_date=AS_OF_DATE - timedelta(days=1),
    **overrides,
):
    fact = {
        "fact_id": fact_id,
        "event_id": f"event-{fact_id}",
        "fact_type": fact_type,
        "fact_nature": fact_nature,
        "validation_status": "confirmed",
        "source_level": source_level,
        "metadata": metadata or {},
        "publish_time": publish_date,
        "reviewer": "reviewer-1",
        "review_note": "reviewed against source",
        "reviewed_at": datetime(2026, 7, 8, 10, 0),
        "created_at": datetime(2026, 7, 8, 9, 0),
    }
    fact.update(overrides)
    return fact


def traceable_mapping(**overrides):
    mapping = {
        "mapping_id": "m-traceable",
        "code": "688001",
        "chain_id": "dexterous_hand",
        "tag_name": "空心杯电机",
        "status": "candidate",
        "l1_l8_path": {"derived_from_mapping_id": "source-mapping"},
    }
    mapping.update(overrides)
    return mapping


def fact_for_level(level):
    return {
        "E1": reviewed_fact(
            "fact-e1",
            "business_presence",
            source_level="mid",
            fact_nature="company_claim",
        ),
        "E2": reviewed_fact(
            "fact-e2",
            "product_spec",
            source_level="mid",
            fact_nature="company_claim",
        ),
        "E3": reviewed_fact(
            "fact-e3",
            "customer_validation",
            source_level="mid",
            fact_nature="company_claim",
        ),
        "E4": reviewed_fact("fact-e4", "order_award"),
        "E5": reviewed_fact(
            "fact-e5",
            "revenue_margin",
            metadata={"revenue_confirmed": True},
        ),
        "E6": reviewed_fact(
            "fact-e6",
            "revenue_margin",
            metadata={"profit_confirmed": True},
        ),
    }[level]


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


def test_pool_gate_combination_takes_strictest_cap_and_sorted_fact_ids():
    evidence_gate = selection_v2.PoolGateResult(
        eligible=True,
        max_pool_code="A",
        level="E4",
        matched_fact_ids=("fact-order",),
        reasons=("matched_evidence_level:E4",),
    )
    route_gate = selection_v2.PoolGateResult(
        eligible=True,
        max_pool_code="D",
        level="AF1",
        matched_fact_ids=("fact-patent", "fact-order"),
        reasons=("matched_route_stage:AF1",),
    )

    result = selection_v2.combine_pool_gates(evidence_gate, route_gate)

    assert result == selection_v2.PoolGateResult(
        eligible=True,
        max_pool_code="D",
        level="AF1",
        matched_fact_ids=("fact-order", "fact-patent"),
        reasons=("matched_evidence_level:E4", "matched_route_stage:AF1"),
    )

    evidence_is_stricter = selection_v2.combine_pool_gates(
        selection_v2.PoolGateResult(True, "D", "E1", (), ()),
        selection_v2.PoolGateResult(True, "A", "AF6", (), ()),
    )
    assert evidence_is_stricter.max_pool_code == "D"
    assert evidence_is_stricter.level == "E1"


def test_pool_gate_result_is_immutable():
    gate = selection_v2.PoolGateResult(True, "D", "E1", (), ())

    with pytest.raises(FrozenInstanceError):
        gate.level = "E2"


@pytest.mark.parametrize(
    ("left_cap", "right_cap", "expected_cap"),
    [("D", "C", "D"), ("C", "B", "C"), ("B", "A", "B")],
)
def test_pool_gate_cap_order_uses_every_adjacent_pool_rank(
    left_cap,
    right_cap,
    expected_cap,
):
    result = selection_v2.combine_pool_gates(
        selection_v2.PoolGateResult(True, left_cap, "left", (), ()),
        selection_v2.PoolGateResult(True, right_cap, "right", (), ()),
    )

    assert result.max_pool_code == expected_cap


def test_pool_gate_combination_preserves_exclusion_order_and_no_cap():
    result = selection_v2.combine_pool_gates(
        selection_v2.PoolGateResult(False, None, "E0", (), ("evidence_e0",)),
        selection_v2.PoolGateResult(False, None, "AF0", (), ("axis_flux_af0",)),
    )

    assert result == selection_v2.PoolGateResult(
        eligible=False,
        max_pool_code=None,
        level="E0",
        matched_fact_ids=(),
        reasons=("evidence_e0", "axis_flux_af0"),
    )

    unrestricted = selection_v2.combine_pool_gates(
        selection_v2.PoolGateResult(True, None, "no_route", (), ()),
        selection_v2.PoolGateResult(True, None, "no_ladder", (), ()),
    )
    assert unrestricted == selection_v2.PoolGateResult(
        True,
        None,
        "unrestricted",
        (),
        (),
    )


def test_veto_precedes_hard_exclusion_and_hard_exclusion_has_stable_blocker():
    vetoed = assign_selection_pool(
        {
            "evidence_level": "E6",
            "veto_reasons": ["customer_cancelled"],
            "hard_exclusion_reasons": ["axis_flux_af0"],
        }
    )
    excluded = assign_selection_pool(
        {
            "evidence_level": "E6",
            "hard_exclusion_reasons": ["axis_flux_af0", "unresolved_route"],
        }
    )

    assert vetoed["eligibility_status"] == "rejected"
    assert vetoed["veto_reasons"] == ["customer_cancelled"]
    assert excluded == {
        "pool_code": None,
        "eligibility_status": "excluded",
        "veto_reasons": [],
        "blocking_gate": "axis_flux_af0",
        "hard_exclusion_reasons": ["axis_flux_af0", "unresolved_route"],
    }


@pytest.mark.parametrize(
    ("level", "expected_cap"),
    [
        ("E1", "D"),
        ("E2", "C"),
        ("E3", "B"),
        ("E4", "A"),
        ("E5", "A"),
        ("E6", "A"),
    ],
)
def test_evidence_gate_levels_and_caps_come_from_catalog(level, expected_cap):
    gate = selection_v2.derive_evidence_gate(
        {"status": "verified", "l1_l8_path": {}},
        [fact_for_level(level)],
        load_evidence_requirements(),
        as_of_date=AS_OF_DATE,
    )

    assert gate.level == level
    assert gate.eligible is True
    assert gate.max_pool_code == expected_cap


def test_business_presence_fact_can_establish_e1_without_candidate_provenance():
    gate = selection_v2.derive_evidence_gate(
        {"status": "verified", "l1_l8_path": {}},
        [fact_for_level("E1")],
        load_evidence_requirements(),
        as_of_date=AS_OF_DATE,
    )

    assert gate.level == "E1"
    assert gate.matched_fact_ids == ("fact-e1",)


def test_evidence_gate_materializes_generator_before_catalog_scan():
    gate = selection_v2.derive_evidence_gate(
        traceable_mapping(),
        iter([fact_for_level("E2")]),
        load_evidence_requirements(),
        as_of_date=AS_OF_DATE,
    )

    assert gate.level == "E2"
    assert gate.matched_fact_ids == ("fact-e2",)


@pytest.mark.parametrize(
    "provenance",
    [
        {"derived_from_mapping_id": "source-mapping"},
        {"discovery_fact_ids": ["pending-axis-1"]},
        {"l1_l8_path": [{"discovery_fact_ids": ["pending-axis-2"]}]},
    ],
    ids=["derived-mapping", "discovery-facts", "nested-list-path"],
)
def test_traceable_candidate_e1_supports_three_provenance_shapes(provenance):
    gate = selection_v2.derive_evidence_gate(
        {"status": "candidate", "l1_l8_path": provenance},
        [],
        load_evidence_requirements(),
        as_of_date=AS_OF_DATE,
    )

    assert gate.level == "E1"
    assert gate.max_pool_code == "D"
    assert gate.matched_fact_ids == ()


@pytest.mark.parametrize("status", ["pending_review", "verified"])
def test_traceable_candidate_e1_accepts_reviewable_mapping_statuses(status):
    gate = selection_v2.derive_evidence_gate(
        {
            "status": status,
            "l1_l8_path": {"derived_from_mapping_id": "source-mapping"},
        },
        [],
        load_evidence_requirements(),
        as_of_date=AS_OF_DATE,
    )

    assert gate.level == "E1"


@pytest.mark.parametrize(
    "provenance",
    [
        {"derived_from_mapping_id": "   "},
        {"discovery_fact_ids": []},
        {"discovery_fact_ids": ["", "   "]},
        {"discovery_fact_ids": "truthy-but-not-an-array"},
        {"discovery_fact_ids": {"fact_id": "truthy-object"}},
    ],
    ids=[
        "blank-derived",
        "empty-discovery",
        "blank-discovery",
        "string-discovery",
        "object-discovery",
    ],
)
def test_empty_candidate_provenance_does_not_establish_e1(provenance):
    gate = selection_v2.derive_evidence_gate(
        {"status": "candidate", "l1_l8_path": provenance},
        [],
        load_evidence_requirements(),
        as_of_date=AS_OF_DATE,
    )

    assert gate.level == "E0"
    assert gate.eligible is False


@pytest.mark.parametrize("status", [None, "approved", "archived"])
def test_traceable_lineage_with_disallowed_status_does_not_establish_e1(status):
    gate = selection_v2.derive_evidence_gate(
        {
            "status": status,
            "l1_l8_path": {"derived_from_mapping_id": "source-mapping"},
        },
        [],
        load_evidence_requirements(),
        as_of_date=AS_OF_DATE,
    )

    assert gate.level == "E0"


@pytest.mark.parametrize(
    "mapping",
    [
        {"status": "candidate", "tag_name": "轴向磁通电机", "l1_l8_path": {}},
        {"status": "candidate", "evidence_ids": ["source-fact"], "l1_l8_path": {}},
        {
            "status": "rejected",
            "l1_l8_path": {"derived_from_mapping_id": "source-mapping"},
        },
    ],
    ids=["tag-only", "source-evidence-ids-only", "disallowed-status"],
)
def test_untraceable_mapping_is_e0_and_ineligible(mapping):
    gate = selection_v2.derive_evidence_gate(
        mapping,
        [],
        load_evidence_requirements(),
        as_of_date=AS_OF_DATE,
    )

    assert gate.level == "E0"
    assert gate.eligible is False
    assert gate.max_pool_code is None
    assert gate.reasons == ("evidence_e0",)


def test_injected_catalog_cap_change_proves_gate_is_not_hard_coded():
    catalog = load_evidence_requirements()
    levels = deepcopy(catalog.evidence_levels)
    levels["E2"]["max_pool"] = "D"
    injected = replace(catalog, evidence_levels=levels)

    gate = selection_v2.derive_evidence_gate(
        traceable_mapping(),
        [fact_for_level("E2")],
        injected,
        as_of_date=AS_OF_DATE,
    )

    assert gate.level == "E2"
    assert gate.max_pool_code == "D"


def test_injected_catalog_matching_and_expiry_rules_change_gate_behavior():
    catalog = load_evidence_requirements()

    nature_types = deepcopy(catalog.evidence_types)
    nature_types["order_or_delivery"]["allowed_fact_natures"].append(
        "company_claim"
    )
    nature_catalog = replace(catalog, evidence_types=nature_types)
    claimed_order = reviewed_fact(
        "claimed-order",
        "order_award",
        fact_nature="company_claim",
    )
    assert selection_v2.derive_evidence_gate(
        traceable_mapping(),
        [claimed_order],
        nature_catalog,
        as_of_date=AS_OF_DATE,
    ).level == "E4"

    source_rank = deepcopy(catalog.source_level_rank)
    source_rank["weak"] = source_rank["mid"]
    source_catalog = replace(catalog, source_level_rank=source_rank)
    assert selection_v2.derive_evidence_gate(
        traceable_mapping(),
        [reviewed_fact("weak-product", "product_spec", source_level="weak")],
        source_catalog,
        as_of_date=AS_OF_DATE,
    ).level == "E2"

    metadata_types = deepcopy(catalog.evidence_types)
    metadata_types["recognized_revenue"]["metadata_flags"] = []
    metadata_catalog = replace(catalog, evidence_types=metadata_types)
    assert selection_v2.derive_evidence_gate(
        traceable_mapping(),
        [reviewed_fact("unflagged-revenue", "revenue_margin")],
        metadata_catalog,
        as_of_date=AS_OF_DATE,
    ).level == "E5"

    freshness = deepcopy(catalog.freshness_policies)
    freshness["customer_test"] = 1
    freshness_catalog = replace(catalog, freshness_policies=freshness)
    stale = selection_v2.derive_evidence_gate(
        traceable_mapping(),
        [
            reviewed_fact(
                "customer",
                "customer_validation",
                source_level="mid",
                fact_nature="company_claim",
                publish_date=AS_OF_DATE - timedelta(days=2),
            )
        ],
        freshness_catalog,
        as_of_date=AS_OF_DATE,
    )
    assert stale.level == "E1"
    assert "stale_customer_validation" in stale.reasons


@pytest.mark.parametrize(
    "fact",
    [
        reviewed_fact("weak-product", "product_spec", source_level="weak"),
        reviewed_fact(
            "wrong-flag-type",
            "revenue_margin",
            metadata={"revenue_confirmed": 1},
        ),
    ],
    ids=["below-minimum-source", "metadata-flag-wrong-type"],
)
def test_catalog_source_rank_and_metadata_flags_fail_closed(fact):
    gate = selection_v2.derive_evidence_gate(
        traceable_mapping(),
        [fact],
        load_evidence_requirements(),
        as_of_date=AS_OF_DATE,
    )

    assert gate.level == "E1"
    assert gate.matched_fact_ids == ()


@pytest.mark.parametrize(
    "metadata",
    [
        {"revenue_confirmed": True},
        {"profit_confirmed": True},
    ],
    ids=["e5-company-claim", "e6-company-claim"],
)
def test_financial_company_claim_cannot_establish_e5_or_e6(metadata):
    gate = selection_v2.derive_evidence_gate(
        traceable_mapping(),
        [
            reviewed_fact(
                "financial-claim",
                "revenue_margin",
                metadata=metadata,
                fact_nature="company_claim",
            )
        ],
        load_evidence_requirements(),
        as_of_date=AS_OF_DATE,
    )

    assert gate.level == "E1"
    assert gate.max_pool_code == "D"
    assert gate.matched_fact_ids == ()


@pytest.mark.parametrize(
    ("age_days", "expected_level", "expected_cap", "is_stale"),
    [
        (180, "E3", "B", False),
        (181, "E1", "D", True),
    ],
)
def test_customer_validation_expiry_boundary_is_180_days(
    age_days,
    expected_level,
    expected_cap,
    is_stale,
):
    fact = reviewed_fact(
        "customer",
        "customer_validation",
        source_level="mid",
        fact_nature="company_claim",
        publish_date=AS_OF_DATE - timedelta(days=age_days),
    )

    gate = selection_v2.derive_evidence_gate(
        traceable_mapping(),
        [fact],
        load_evidence_requirements(),
        as_of_date=AS_OF_DATE,
    )

    assert gate.level == expected_level
    assert gate.max_pool_code == expected_cap
    assert ("stale_customer_validation" in gate.reasons) is is_stale
    assert ("customer" in gate.matched_fact_ids) is (not is_stale)


@pytest.mark.parametrize(
    ("metadata", "active_level", "stale_reason"),
    [
        ({"revenue_confirmed": True}, "E5", "stale_recognized_revenue"),
        ({"profit_confirmed": True}, "E6", "stale_recognized_profit"),
    ],
)
def test_financial_evidence_uses_catalog_180_day_expiry(
    metadata,
    active_level,
    stale_reason,
):
    def gate_for_age(age_days):
        return selection_v2.derive_evidence_gate(
            traceable_mapping(),
            [
                reviewed_fact(
                    "financial",
                    "revenue_margin",
                    metadata=metadata,
                    publish_date=AS_OF_DATE - timedelta(days=age_days),
                )
            ],
            load_evidence_requirements(),
            as_of_date=AS_OF_DATE,
        )

    fresh = gate_for_age(180)
    stale = gate_for_age(181)

    assert fresh.level == active_level
    assert stale.level == "E1"
    assert stale.max_pool_code == "D"
    assert stale.matched_fact_ids == ()
    assert stale_reason in stale.reasons


def test_route_resolution_uses_tag_and_nested_provenance_but_rejects_conflicts():
    template = get_industry_template("dexterous_hand")
    tag_only = traceable_mapping(
        tag_name="轴向磁通电机",
        l1_l8_path={"derived_from_mapping_id": "source-mapping"},
    )
    provenance = traceable_mapping(
        tag_name="不能由标签自行解析",
        l1_l8_path={
            "l1_l8_path": {
                "technology_route_id": "dexterous_axial_flux_motor",
            }
        },
    )
    explicit_provenance_conflict = traceable_mapping(
        tag_name="不能由标签自行解析",
        technology_route_id="dexterous_axial_flux_motor",
        l1_l8_path={
            "technology_route_id": "dexterous_hollow_cup_screw",
        },
    )
    explicit_template_conflict = traceable_mapping(
        tag_name="轴向磁通电机",
        technology_route_id="dexterous_hollow_cup_screw",
    )
    provenance_template_conflict = traceable_mapping(
        tag_name="轴向磁通电机",
        l1_l8_path={
            "derived_from_mapping_id": "source-mapping",
            "technology_route_id": "dexterous_hollow_cup_screw",
        },
    )

    assert (
        selection_v2.resolve_mapping_technology_route(tag_only, template)
        == "dexterous_axial_flux_motor"
    )
    assert (
        selection_v2.resolve_mapping_technology_route(provenance, template)
        == "dexterous_axial_flux_motor"
    )
    conflicts = (
        explicit_provenance_conflict,
        explicit_template_conflict,
        provenance_template_conflict,
    )
    for conflict in conflicts:
        with pytest.raises(
            selection_v2.UnresolvedTechnologyRoute,
            match="unresolved_route",
        ):
            selection_v2.resolve_mapping_technology_route(conflict, template)

    tag_gate = selection_v2.derive_route_gate(
        tag_only,
        [],
        template,
        as_of_date=AS_OF_DATE,
    )
    assert tag_gate.level == "AF0"
    assert tag_gate.eligible is False
    for conflict in conflicts:
        conflict_gate = selection_v2.derive_route_gate(
            conflict,
            [],
            template,
            as_of_date=AS_OF_DATE,
        )
        assert conflict_gate.level == "unresolved_route"
        assert conflict_gate.reasons[0] == "unresolved_route"


def test_route_resolution_rejects_unknown_and_ambiguous_routes():
    template = get_industry_template("dexterous_hand")
    unknown = traceable_mapping(
        tag_name="轴向磁通电机",
        technology_route_id="unknown_route",
    )
    ambiguous_template = deepcopy(template)
    duplicate = deepcopy(
        next(
            row
            for row in ambiguous_template["evidence_requirements"]
            if row["requirement_id"] == "dexterous_axial_flux_motor"
        )
    )
    duplicate["requirement_id"] = "duplicate_axial_requirement"
    ambiguous_template["evidence_requirements"].append(duplicate)

    with pytest.raises(selection_v2.UnresolvedTechnologyRoute, match="unresolved_route"):
        selection_v2.resolve_mapping_technology_route(unknown, template)
    with pytest.raises(selection_v2.UnresolvedTechnologyRoute, match="unresolved_route"):
        selection_v2.resolve_mapping_technology_route(
            traceable_mapping(tag_name="轴向磁通电机"),
            ambiguous_template,
        )


def test_explicit_route_resolves_independently_of_tag_and_provenance():
    template = get_industry_template("dexterous_hand")
    mapping = traceable_mapping(
        tag_name="不能由标签自行解析",
        technology_route_id="dexterous_axial_flux_motor",
        l1_l8_path={"derived_from_mapping_id": "source-mapping"},
    )

    assert (
        selection_v2.resolve_mapping_technology_route(mapping, template)
        == "dexterous_axial_flux_motor"
    )
    gate = selection_v2.derive_route_gate(
        mapping,
        [reviewed_fact("prototype", "prototype_delivery")],
        template,
        as_of_date=AS_OF_DATE,
    )
    assert gate.level == "AF1"
    assert gate.matched_fact_ids == ("prototype",)


def test_missing_template_with_chain_context_is_unresolved_not_unrestricted():
    mapping = traceable_mapping(
        chain_id="unknown_chain",
        tag_name="可能需要路线的业务",
        l1_l8_path={"derived_from_mapping_id": "source-mapping"},
    )

    with pytest.raises(
        selection_v2.UnresolvedTechnologyRoute,
        match="template_unavailable",
    ):
        selection_v2.resolve_mapping_technology_route(mapping, None)
    gate = selection_v2.derive_route_gate(
        mapping,
        [],
        None,
        as_of_date=AS_OF_DATE,
    )
    assert gate.level == "unresolved_route"
    assert gate.eligible is False
    assert gate.reasons[0] == "unresolved_route"


def test_route_template_with_blank_mapping_context_is_unresolved():
    mapping = {"status": "candidate", "l1_l8_path": {}}
    routed_template = get_industry_template("dexterous_hand")

    with pytest.raises(
        selection_v2.UnresolvedTechnologyRoute,
        match="missing_route_context",
    ):
        selection_v2.resolve_mapping_technology_route(mapping, routed_template)
    gate = selection_v2.derive_route_gate(
        mapping,
        [],
        routed_template,
        as_of_date=AS_OF_DATE,
    )
    assert gate.level == "unresolved_route"

    route_free_template = {
        "technology_routes": [],
        "evidence_requirements": [],
    }
    assert (
        selection_v2.resolve_mapping_technology_route(mapping, route_free_template)
        is None
    )


def test_nonroute_requirement_rejects_injected_known_route():
    template = {
        "technology_routes": [{"route_id": "known_route"}],
        "evidence_requirements": [
            {
                "requirement_id": "plain_business",
                "business_keywords": ["普通业务"],
                "technology_route_id": None,
            }
        ],
    }
    mapping = traceable_mapping(
        tag_name="普通业务",
        technology_route_id="known_route",
    )

    with pytest.raises(selection_v2.UnresolvedTechnologyRoute, match="route_conflict"):
        selection_v2.resolve_mapping_technology_route(mapping, template)


def test_naive_created_at_uses_utc_cutoff_not_shanghai_wall_clock():
    future_created = reviewed_fact(
        "future-created",
        "product_spec",
        created_at=datetime(2026, 7, 9, 16, 0),
    )

    gate = selection_v2.derive_evidence_gate(
        traceable_mapping(),
        [future_created],
        load_evidence_requirements(),
        as_of_date=AS_OF_DATE,
    )

    assert gate.level == "E1"
    assert gate.matched_fact_ids == ()


def test_true_no_route_is_unrestricted_and_route_without_ladder_is_unrestricted():
    template = get_industry_template("dexterous_hand")
    no_route_mapping = traceable_mapping(tag_name="灵巧手")
    no_ladder_mapping = traceable_mapping(
        tag_name="空心杯电机",
        technology_route_id="dexterous_hollow_cup_screw",
    )

    assert selection_v2.resolve_mapping_technology_route(no_route_mapping, template) is None
    no_route_gate = selection_v2.derive_route_gate(
        {**no_route_mapping, "technology_route_id": None},
        [],
        template,
        as_of_date=AS_OF_DATE,
    )
    no_ladder_gate = selection_v2.derive_route_gate(
        no_ladder_mapping,
        [],
        template,
        as_of_date=AS_OF_DATE,
    )

    assert no_route_gate.level == "unrestricted"
    assert no_route_gate.eligible is True
    assert no_ladder_gate.level == "unrestricted"
    assert no_ladder_gate.eligible is True


def test_unmatched_tag_without_any_route_signal_is_unresolved():
    template = get_industry_template("dexterous_hand")
    mapping = traceable_mapping(tag_name="未配置的业务标签")

    with pytest.raises(
        selection_v2.UnresolvedTechnologyRoute,
        match="tag_requirement_not_found",
    ):
        selection_v2.resolve_mapping_technology_route(mapping, template)
    gate = selection_v2.derive_route_gate(
        mapping,
        [],
        template,
        as_of_date=AS_OF_DATE,
    )
    assert gate.level == "unresolved_route"


@pytest.mark.parametrize(
    "fact",
    [
        reviewed_fact(
            "patent",
            "patent_standard",
            metadata={"legal_status": "active", "legal_status_date": "2026-06-01"},
        ),
        reviewed_fact("prototype", "prototype_delivery"),
    ],
    ids=["active-patent", "laboratory-prototype"],
)
def test_route_gate_af1_accepts_either_configured_clause(fact):
    template = get_industry_template("dexterous_hand")
    mapping = traceable_mapping(
        tag_name="轴向磁通电机",
        technology_route_id="dexterous_axial_flux_motor",
    )

    gate = selection_v2.derive_route_gate(
        mapping,
        [fact],
        template,
        as_of_date=AS_OF_DATE,
    )

    assert gate.level == "AF1"
    assert gate.max_pool_code == "D"
    assert gate.matched_fact_ids == (fact["fact_id"],)


@pytest.mark.parametrize(
    "created_at",
    [None, datetime(2026, 7, 9, 16, 0)],
    ids=["missing-created-at", "future-created-at-utc"],
)
def test_route_gate_rejects_fact_without_historical_created_at(created_at):
    template = get_industry_template("dexterous_hand")
    mapping = traceable_mapping(
        tag_name="轴向磁通电机",
        technology_route_id="dexterous_axial_flux_motor",
    )
    fact = reviewed_fact(
        "prototype",
        "prototype_delivery",
        created_at=created_at,
    )

    gate = selection_v2.derive_route_gate(
        mapping,
        [fact],
        template,
        as_of_date=AS_OF_DATE,
    )

    assert gate.level == "AF0"
    assert gate.eligible is False
    assert gate.matched_fact_ids == ()


def test_route_gate_af6_requires_order_and_revenue_and_ignores_automotive_fact():
    template = get_industry_template("dexterous_hand")
    mapping = traceable_mapping(
        tag_name="轴向磁通电机",
        technology_route_id="dexterous_axial_flux_motor",
    )
    automotive = reviewed_fact(
        "automotive-product",
        "product_spec",
        metadata={"application_domain": "automotive"},
    )
    order = reviewed_fact(
        "robot-order",
        "order_award",
        metadata={"application_domain": "robot_hand"},
    )
    revenue = reviewed_fact(
        "robot-revenue",
        "revenue_margin",
        metadata={"application_domain": "robot_hand", "revenue_confirmed": True},
    )

    incomplete = selection_v2.derive_route_gate(
        mapping,
        [automotive, order],
        template,
        as_of_date=AS_OF_DATE,
    )
    complete = selection_v2.derive_route_gate(
        mapping,
        [automotive, order, revenue],
        template,
        as_of_date=AS_OF_DATE,
    )

    assert incomplete.level == "AF0"
    assert incomplete.eligible is False
    assert complete.level == "AF6"
    assert complete.eligible is True
    assert complete.matched_fact_ids == ("robot-order", "robot-revenue")


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
