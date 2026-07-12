"""As-of and evidence-gate contracts for supply-chain selection V2 scoring."""

from copy import deepcopy
from dataclasses import replace
import importlib.util
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import pytest


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "score_supply_chain_selection_v2.py"
SPEC = importlib.util.spec_from_file_location(
    "score_supply_chain_selection_v2",
    SCRIPT_PATH,
)
module = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


def base_mapping(**overrides):
    mapping = {
        "mapping_id": "m1",
        "code": "000001",
        "chain_id": "dexterous_hand",
        "node_id": "dexterous_hand_foundation",
        "tag_name": "空心杯电机",
        "status": "candidate",
        "l1_l8_path": {"derived_from_mapping_id": "source-m0"},
        "confidence": 0.35,
        "commercial_stage": "C1",
        "revenue_ratio": None,
        "gross_profit_ratio": None,
        "next_validation_event": None,
        "next_validation_date": None,
    }
    mapping.update(overrides)
    return mapping


def axial_mapping(**overrides):
    mapping = base_mapping(
        mapping_id="axis-m1",
        tag_name="轴向磁通电机",
        technology_route_id="dexterous_axial_flux_motor",
        l1_l8_path={
            "derived_from_mapping_id": "source-axis",
            "technology_route_id": "dexterous_axial_flux_motor",
        },
    )
    mapping.update(overrides)
    return mapping


def repository_mapping_with_stage(**overrides):
    mapping = base_mapping(
        commercial_stage="C5",
        stage_review_status="approved",
        source_event_review_status="approved",
        source_event_reviewer="reviewer-1",
        source_event_review_note="source event checked",
        source_event_reviewed_at=datetime(2026, 7, 10, 10, tzinfo=timezone.utc),
        source_event_date=date(2026, 7, 10),
        stage_created_at=datetime(2026, 7, 9, 10),
        source_event_created_at=datetime(2026, 7, 9, 11),
    )
    mapping.update(overrides)
    return mapping


def evidence(event_id, publish_time, fact_type, **overrides):
    row = {
        "event_id": event_id,
        "publish_time": publish_time,
        "fact_type": fact_type,
        "fact_nature": "confirmed_fact",
        "validation_status": "confirmed",
        "source_level": "strong",
        "confidence": 0.9,
        "metadata": {},
        "reviewer": "reviewer-1",
        "review_note": "checked against source",
        "reviewed_at": datetime(2026, 7, 10, 10, tzinfo=timezone.utc),
        "created_at": datetime(2026, 7, 9, 10, tzinfo=timezone.utc),
    }
    row.update(overrides)
    return row


def test_score_mapping_ignores_evidence_after_trade_date():
    mapping = base_mapping(commercial_stage="C4")
    rows = [
        evidence(
            "old",
            datetime(2026, 7, 10, 9, tzinfo=timezone.utc),
            "order_award",
        ),
        evidence(
            "future",
            datetime(2026, 7, 12, 9, tzinfo=timezone.utc),
            "revenue_margin",
            metadata={"revenue_confirmed": True},
        ),
    ]

    result = module.score_mapping(
        mapping,
        rows,
        trade_date=date(2026, 7, 11),
        node_score=70,
    )

    assert "old" in result["evidence_ids"]
    assert "future" not in result["evidence_ids"]
    assert result["authenticity"]["evidence_level"] == "E4"


def test_score_mapping_never_promotes_pending_review_evidence():
    rows = [
        evidence(
            "pending",
            datetime(2026, 7, 10, 9, tzinfo=timezone.utc),
            "order_award",
            fact_nature="media_report",
            validation_status="pending",
        )
    ]

    result = module.score_mapping(
        base_mapping(),
        rows,
        trade_date=date(2026, 7, 11),
        node_score=70,
    )

    assert result["authenticity"]["evidence_level"] == "E1"
    assert result["selection"]["pool_code"] == "D"
    assert result["evidence_ids"] == []


def test_score_mapping_rejects_approved_as_a_fact_validation_status():
    rows = [
        evidence(
            "approved",
            datetime(2026, 7, 10, 9, tzinfo=timezone.utc),
            "order_award",
            validation_status="approved",
        )
    ]

    result = module.score_mapping(
        base_mapping(),
        rows,
        trade_date=date(2026, 7, 11),
        node_score=70,
    )

    assert result["authenticity"]["evidence_level"] == "E1"
    assert result["evidence_ids"] == []


def test_confirmed_evidence_delegates_fact_nature_policy_to_catalog():
    row = evidence(
        "company-claim",
        datetime(2026, 7, 10, 9, tzinfo=timezone.utc),
        "prototype_delivery",
        fact_nature="company_claim",
        validation_status="confirmed",
    )

    confirmed, limitations = module._confirmed_evidence(
        [row],
        cutoff=module._cutoff_utc(date(2026, 7, 11)),
    )

    assert confirmed == [row]
    assert limitations == []

    result = module.score_mapping(
        base_mapping(),
        [row],
        trade_date=date(2026, 7, 11),
        node_score=70,
    )

    assert result["authenticity"]["evidence_level"] == "E2"
    assert result["selection"]["pool_code"] == "C"


def test_score_mapping_uses_fact_id_as_the_persisted_evidence_id():
    row = evidence(
        "shared-event",
        datetime(2026, 7, 10, 9, tzinfo=timezone.utc),
        "order_award",
        fact_id="fact-1",
    )

    result = module.score_mapping(
        base_mapping(),
        [row],
        trade_date=date(2026, 7, 11),
        node_score=70,
    )

    assert result["evidence_ids"] == ["fact-1"]


def test_score_mapping_preserves_multiple_fact_ids_from_one_event():
    rows = [
        evidence(
            "shared-event",
            datetime(2026, 7, 10, 9, tzinfo=timezone.utc),
            fact_type,
            fact_id=fact_id,
        )
        for fact_id, fact_type in (
            ("fact-1", "order_award"),
            ("fact-2", "capacity_mass_production"),
        )
    ]

    result = module.score_mapping(
        base_mapping(),
        rows,
        trade_date=date(2026, 7, 11),
        node_score=70,
    )

    assert result["evidence_ids"] == ["fact-1", "fact-2"]


@pytest.mark.parametrize(
    "validation_status,audit_overrides",
    [
        ("confirmed", {"reviewer": None}),
        ("confirmed", {"reviewer": "   "}),
        ("confirmed", {"review_note": None}),
        ("confirmed", {"review_note": "   "}),
        ("confirmed", {"reviewed_at": None}),
        ("confirmed", {"reviewed_at": "not-a-timestamp"}),
        ("confirmed", {"reviewed_at": datetime(2026, 7, 10, 10)}),
        (
            "confirmed",
            {"reviewed_at": datetime(2026, 7, 12, 9, tzinfo=timezone.utc)},
        ),
        ("confirmed", {"created_at": None}),
        ("confirmed", {"created_at": "not-a-timestamp"}),
        ("confirmed", {"created_at": datetime(2026, 7, 11, 16)}),
        (
            "confirmed",
            {"created_at": datetime(2026, 7, 12, 9, tzinfo=timezone.utc)},
        ),
    ],
    ids=[
        "confirmed-missing-reviewer",
        "confirmed-blank-reviewer",
        "confirmed-missing-note",
        "confirmed-blank-note",
        "confirmed-missing-reviewed-at",
        "confirmed-invalid-reviewed-at",
        "confirmed-naive-reviewed-at",
        "confirmed-future-reviewed-at",
        "confirmed-missing-created-at",
        "confirmed-invalid-created-at",
        "confirmed-future-naive-utc-created-at",
        "confirmed-future-created-at",
    ],
)
def test_score_mapping_rejects_evidence_without_a_safe_audit_trail(
    validation_status,
    audit_overrides,
):
    rows = [
        evidence(
            "unsafe",
            datetime(2026, 7, 10, 9, tzinfo=timezone.utc),
            "order_award",
            fact_id="fact-unsafe",
            validation_status=validation_status,
            **audit_overrides,
        )
    ]

    result = module.score_mapping(
        base_mapping(),
        rows,
        trade_date=date(2026, 7, 11),
        node_score=70,
    )

    assert result["authenticity"]["evidence_level"] == "E1"
    assert result["evidence_ids"] == []
    assert any(
        "fact-unsafe" in limitation
        for limitation in result["data_limitations"]
    )


@pytest.mark.parametrize(
    "unsafe_overrides",
    [
        {"validation_status": "pending"},
        {"publish_time": datetime(2026, 7, 12, 9, tzinfo=timezone.utc)},
        {"reviewed_at": datetime(2026, 7, 12, 9, tzinfo=timezone.utc)},
        {"reviewer": None},
        {"created_at": None},
        {"created_at": datetime(2026, 7, 12, 9, tzinfo=timezone.utc)},
    ],
    ids=[
        "pending",
        "future-publish",
        "future-review",
        "unaudited",
        "missing-created",
        "future-created",
    ],
)
def test_unsafe_fact_cannot_pollute_any_score_component(unsafe_overrides):
    row = evidence(
        "unsafe-negative",
        datetime(2026, 7, 10, 9, tzinfo=timezone.utc),
        "negative",
        fact_id="fact-unsafe-negative",
        metadata={
            "veto_reason": "must-not-veto",
            "realized_revenue_growth": 100,
            "segment_gross_margin": 100,
            "technical_performance": 100,
            "profit_elasticity_score": 100,
        },
    )
    row.update(unsafe_overrides)

    result = module.score_mapping(
        base_mapping(),
        [row],
        trade_date=date(2026, 7, 11),
        node_score=70,
    )

    assert result["authenticity"]["evidence_level"] == "E1"
    assert result["operating_quality"]["score"] is None
    assert result["benefit"]["score"] is None
    assert result["selection"]["detail"]["risk_score"] is None
    assert result["selection"]["eligibility_status"] != "rejected"
    assert result["selection"]["veto_reasons"] == []
    assert result["evidence_ids"] == []


def test_confirmed_prototype_can_reach_c_but_not_customer_pool():
    rows = [
        evidence(
            "prototype",
            datetime(2026, 7, 10, 9, tzinfo=timezone.utc),
            "prototype_delivery",
        )
    ]

    result = module.score_mapping(
        base_mapping(),
        rows,
        trade_date=date(2026, 7, 11),
        node_score=70,
    )

    assert result["authenticity"]["evidence_level"] == "E2"
    assert result["selection"]["pool_code"] == "C"


def test_confirmed_customer_validation_needs_next_event_for_b_pool():
    rows = [
        evidence(
            "customer",
            datetime(2026, 7, 10, 9, tzinfo=timezone.utc),
            "customer_validation",
        )
    ]
    mapping = base_mapping(
        next_validation_event="客户测试完成",
        next_validation_date=date(2026, 12, 31),
    )

    result = module.score_mapping(
        mapping,
        rows,
        trade_date=date(2026, 7, 11),
        node_score=70,
    )

    assert result["authenticity"]["evidence_level"] == "E3"
    assert result["selection"]["pool_code"] == "B"


def test_missing_publish_time_is_not_treated_as_historical_evidence():
    rows = [evidence("undated", None, "order_award")]

    result = module.score_mapping(
        base_mapping(),
        rows,
        trade_date=date(2026, 7, 11),
        node_score=None,
    )

    assert result["authenticity"]["evidence_level"] == "E1"
    assert "evidence_missing_publish_time:undated" in result["data_limitations"]


def test_negative_confirmed_fact_is_a_veto_not_a_small_penalty():
    rows = [
        evidence(
            "negative",
            datetime(2026, 7, 10, 9, tzinfo=timezone.utc),
            "negative",
            metadata={"veto_reason": "customer_cancelled"},
        )
    ]

    result = module.score_mapping(
        base_mapping(),
        rows,
        trade_date=date(2026, 7, 11),
        node_score=70,
    )

    assert result["selection"]["pool_code"] is None
    assert result["selection"]["eligibility_status"] == "rejected"
    assert result["selection"]["veto_reasons"] == ["customer_cancelled"]


def test_reviewed_negative_risk_without_explicit_veto_only_reduces_score():
    row = evidence(
        "supply-risk",
        datetime(2026, 7, 10, 9, tzinfo=timezone.utc),
        "negative",
        metadata={
            "review_normalization": {
                "method_version": "risk-v1",
                "as_of_date": "2026-07-11",
                "risk_score": 85,
            }
        },
    )

    result = module.score_mapping(
        base_mapping(risk_score=85, expectation_gap_score=60, catalyst_score=50),
        [row],
        trade_date=date(2026, 7, 11),
        node_score=70,
    )

    assert result["selection"]["eligibility_status"] != "rejected"
    assert result["selection"]["veto_reasons"] == []
    assert result["selection"]["detail"]["risk_score"] == 85.0


def test_score_bundle_keeps_component_inputs_for_auditable_persistence():
    rows = [
        evidence(
            "prototype",
            datetime(2026, 7, 10, 9, tzinfo=timezone.utc),
            "prototype_delivery",
        )
    ]
    mapping = base_mapping(
        expectation_gap_score=55,
        catalyst_score=60,
        risk_score=20,
    )

    result = module.score_mapping(
        mapping,
        rows,
        trade_date=date(2026, 7, 11),
        node_score=70,
    )

    assert result["authenticity"]["detail"]["product_evidence_score"] == 80
    assert result["benefit"]["detail"]["node_attractiveness"] == 70
    assert result["benefit"]["detail"]["order_certainty_score"] == 30
    assert result["selection"]["detail"]["expectation_gap_score"] == 55
    assert result["selection"]["detail"]["risk_score"] == 20


def test_af0_excludes_even_when_automotive_revenue_evidence_is_e6():
    row = evidence(
        "automotive-revenue",
        datetime(2026, 7, 10, 9, tzinfo=timezone.utc),
        "revenue_margin",
        fact_id="fact-automotive-revenue",
        metadata={
            "application_domain": "automotive",
            "revenue_confirmed": True,
            "profit_confirmed": True,
        },
    )

    result = module.score_mapping(
        axial_mapping(),
        [row],
        trade_date=date(2026, 7, 11),
        node_score=80,
    )

    assert result["authenticity"]["evidence_level"] == "E6"
    assert result["selection"]["pool_code"] is None
    assert result["selection"]["eligibility_status"] == "excluded"
    assert result["selection"]["blocking_gate"] == "axis_flux_af0"


def test_e4_plus_af1_is_capped_at_d_and_gate_detail_is_persistable():
    rows = [
        evidence(
            "shared-event",
            datetime(2026, 7, 10, 9, tzinfo=timezone.utc),
            "order_award",
            fact_id="fact-order",
            metadata={"application_domain": "robot_hand"},
        ),
        evidence(
            "shared-event",
            datetime(2026, 7, 10, 9, tzinfo=timezone.utc),
            "prototype_delivery",
            fact_id="fact-prototype",
        ),
    ]

    result = module.score_mapping(
        axial_mapping(),
        rows,
        trade_date=date(2026, 7, 11),
        node_score=80,
    )

    assert result["authenticity"]["evidence_level"] == "E4"
    assert result["selection"]["pool_code"] == "D"
    gates = result["selection"]["detail"]["pool_gates"]
    assert gates["evidence"]["level"] == "E4"
    assert gates["route"]["level"] == "AF1"
    assert gates["combined"]["max_pool_code"] == "D"
    assert gates["combined"]["matched_fact_ids"] == (
        "fact-order",
        "fact-prototype",
    )


def test_score_mapping_uses_injected_evidence_catalog_cap():
    catalog = module.load_evidence_requirements()
    levels = deepcopy(catalog.evidence_levels)
    levels["E4"]["max_pool"] = "D"
    injected_catalog = replace(catalog, evidence_levels=levels)
    row = evidence(
        "order",
        datetime(2026, 7, 10, 9, tzinfo=timezone.utc),
        "order_award",
        fact_id="fact-order",
    )

    result = module.score_mapping(
        base_mapping(),
        [row],
        trade_date=date(2026, 7, 11),
        node_score=80,
        evidence_requirements=injected_catalog,
    )

    assert result["authenticity"]["evidence_level"] == "E4"
    assert result["authenticity"]["max_pool_code"] == "D"
    assert result["selection"]["pool_code"] == "D"

    excluded_levels = deepcopy(levels)
    excluded_levels["E4"]["eligible"] = False
    excluded_levels["E4"]["max_pool"] = None
    excluded_catalog = replace(catalog, evidence_levels=excluded_levels)
    excluded = module.score_mapping(
        base_mapping(),
        [row],
        trade_date=date(2026, 7, 11),
        node_score=80,
        evidence_requirements=excluded_catalog,
    )
    assert excluded["selection"]["pool_code"] is None
    assert excluded["selection"]["eligibility_status"] == "excluded"


def test_score_mapping_uses_injected_route_eligible_and_cap_rules():
    rows = [
        evidence(
            "shared-event",
            datetime(2026, 7, 10, 9, tzinfo=timezone.utc),
            "order_award",
            fact_id="fact-order",
            metadata={"application_domain": "robot_hand"},
        ),
        evidence(
            "shared-event",
            datetime(2026, 7, 10, 9, tzinfo=timezone.utc),
            "prototype_delivery",
            fact_id="fact-prototype",
        ),
    ]
    capped_template = deepcopy(module.get_industry_template("dexterous_hand"))
    capped_route = next(
        route
        for route in capped_template["technology_routes"]
        if route["route_id"] == "dexterous_axial_flux_motor"
    )
    capped_route["authenticity_ladder"]["AF1"]["max_pool"] = "C"

    capped = module.score_mapping(
        axial_mapping(),
        rows,
        trade_date=date(2026, 7, 11),
        node_score=80,
        industry_template=capped_template,
    )

    excluded_template = deepcopy(capped_template)
    excluded_route = next(
        route
        for route in excluded_template["technology_routes"]
        if route["route_id"] == "dexterous_axial_flux_motor"
    )
    excluded_route["authenticity_ladder"]["AF1"]["eligible"] = False
    excluded_route["authenticity_ladder"]["AF1"]["max_pool"] = None
    excluded = module.score_mapping(
        axial_mapping(),
        rows,
        trade_date=date(2026, 7, 11),
        node_score=80,
        industry_template=excluded_template,
    )

    assert capped["selection"]["pool_code"] == "C"
    assert excluded["selection"]["pool_code"] is None
    assert excluded["selection"]["eligibility_status"] == "excluded"
    assert excluded["selection"]["blocking_gate"].startswith(
        "route_stage_ineligible:"
    )


def test_score_mapping_uses_injected_af6_match_mode_and_cap():
    order = evidence(
        "order-event",
        datetime(2026, 7, 10, 9, tzinfo=timezone.utc),
        "order_award",
        fact_id="fact-order",
        metadata={"application_domain": "robot_hand"},
    )
    default = module.score_mapping(
        axial_mapping(),
        [order],
        trade_date=date(2026, 7, 11),
        node_score=80,
    )

    injected_template = deepcopy(module.get_industry_template("dexterous_hand"))
    route = next(
        item
        for item in injected_template["technology_routes"]
        if item["route_id"] == "dexterous_axial_flux_motor"
    )
    route["authenticity_ladder"]["AF6"]["fact_match_mode"] = "any"
    route["authenticity_ladder"]["AF6"]["max_pool"] = "D"
    injected = module.score_mapping(
        axial_mapping(),
        [order],
        trade_date=date(2026, 7, 11),
        node_score=80,
        industry_template=injected_template,
    )

    assert default["selection"]["eligibility_status"] == "excluded"
    route_gate = injected["selection"]["detail"]["pool_gates"]["route"]
    assert route_gate["level"] == "AF6"
    assert route_gate["max_pool_code"] == "D"
    assert route_gate["matched_fact_ids"] == ("fact-order",)
    assert injected["selection"]["pool_code"] == "D"


def test_score_mapping_never_lets_wider_route_cap_raise_evidence_cap():
    catalog = module.load_evidence_requirements()
    evidence_types = deepcopy(catalog.evidence_types)
    evidence_types["order_or_delivery"]["fact_types"] = ["disabled_order"]
    evidence_types["recognized_revenue"]["fact_types"] = ["disabled_revenue"]
    evidence_types["recognized_profit"]["fact_types"] = ["disabled_profit"]
    injected_catalog = replace(catalog, evidence_types=evidence_types)
    rows = [
        evidence(
            "shared-event",
            datetime(2026, 7, 10, 9, tzinfo=timezone.utc),
            "order_award",
            fact_id="fact-order",
            metadata={"application_domain": "robot_hand"},
        ),
        evidence(
            "shared-event",
            datetime(2026, 7, 10, 9, tzinfo=timezone.utc),
            "revenue_margin",
            fact_id="fact-revenue",
            metadata={
                "application_domain": "robot_hand",
                "revenue_confirmed": True,
            },
        ),
    ]

    result = module.score_mapping(
        axial_mapping(),
        rows,
        trade_date=date(2026, 7, 11),
        node_score=80,
        evidence_requirements=injected_catalog,
    )

    gates = result["selection"]["detail"]["pool_gates"]
    assert gates["evidence"]["level"] == "E1"
    assert gates["evidence"]["max_pool_code"] == "D"
    assert gates["route"]["level"] == "AF6"
    assert gates["route"]["max_pool_code"] == "A"
    assert gates["combined"]["max_pool_code"] == "D"
    assert result["selection"]["pool_code"] == "D"


def test_independent_axial_discovery_is_e1_but_af0_until_route_evidence():
    mapping = axial_mapping(
        l1_l8_path={
            "technology_route_id": "dexterous_axial_flux_motor",
            "discovery_fact_ids": ["pending-axis-1"],
        },
        evidence_ids=["source-evidence-must-not-be-inherited"],
    )

    result = module.score_mapping(
        mapping,
        [],
        trade_date=date(2026, 7, 11),
        node_score=None,
    )

    assert result["authenticity"]["evidence_level"] == "E1"
    assert result["selection"]["pool_code"] is None
    assert result["selection"]["eligibility_status"] == "excluded"
    assert result["selection"]["blocking_gate"] == "axis_flux_af0"
    assert result["evidence_ids"] == []


def test_traceable_candidate_is_e1_without_inheriting_source_mapping_evidence():
    mapping = base_mapping(
        evidence_ids=["source-fact-1"],
        l1_l8_path={"derived_from_mapping_id": "source-m1"},
    )

    result = module.score_mapping(
        mapping,
        [],
        trade_date=date(2026, 7, 11),
        node_score=None,
    )

    assert result["authenticity"]["evidence_level"] == "E1"
    assert result["selection"]["pool_code"] == "D"
    assert result["evidence_ids"] == []


def test_tag_status_and_source_evidence_ids_without_provenance_remain_e0():
    mapping = base_mapping(
        l1_l8_path={},
        evidence_ids=["source-fact-1"],
    )

    result = module.score_mapping(
        mapping,
        [],
        trade_date=date(2026, 7, 11),
        node_score=None,
    )

    assert result["authenticity"]["evidence_level"] == "E0"
    assert result["selection"]["eligibility_status"] == "excluded"
    assert result["selection"]["blocking_gate"] == "evidence_e0"


def test_company_claim_can_support_lower_catalog_level_but_not_e4():
    prototype = evidence(
        "claim-prototype",
        datetime(2026, 7, 10, 9, tzinfo=timezone.utc),
        "prototype_delivery",
        fact_nature="company_claim",
        source_level="mid",
    )
    claimed_order = evidence(
        "claim-order",
        datetime(2026, 7, 10, 9, tzinfo=timezone.utc),
        "order_award",
        fact_nature="company_claim",
        source_level="strong",
    )

    prototype_result = module.score_mapping(
        base_mapping(),
        [prototype],
        trade_date=date(2026, 7, 11),
        node_score=70,
    )
    order_result = module.score_mapping(
        base_mapping(),
        [claimed_order],
        trade_date=date(2026, 7, 11),
        node_score=70,
    )

    assert prototype_result["authenticity"]["evidence_level"] == "E2"
    assert order_result["authenticity"]["evidence_level"] == "E1"


@pytest.mark.parametrize(
    "mapping",
    [
        axial_mapping(technology_route_id="unknown_route"),
        axial_mapping(
            technology_route_id="dexterous_axial_flux_motor",
            l1_l8_path={
                "derived_from_mapping_id": "source-axis",
                "technology_route_id": "dexterous_hollow_cup_screw",
            },
        ),
    ],
    ids=["unknown", "conflict"],
)
def test_unknown_or_conflicting_route_is_excluded_not_unrestricted(mapping):
    result = module.score_mapping(
        mapping,
        [],
        trade_date=date(2026, 7, 11),
        node_score=None,
    )

    assert result["selection"]["pool_code"] is None
    assert result["selection"]["eligibility_status"] == "excluded"
    assert result["selection"]["blocking_gate"] == "unresolved_route"


def test_axial_tag_without_explicit_or_provenance_route_resolves_from_template():
    mapping = axial_mapping(
        technology_route_id=None,
        l1_l8_path={"derived_from_mapping_id": "source-axis"},
    )
    row = evidence(
        "automotive-revenue",
        datetime(2026, 7, 10, 9, tzinfo=timezone.utc),
        "revenue_margin",
        metadata={
            "application_domain": "automotive",
            "revenue_confirmed": True,
            "profit_confirmed": True,
        },
    )

    result = module.score_mapping(
        mapping,
        [row],
        trade_date=date(2026, 7, 11),
        node_score=80,
    )

    assert result["selection"]["eligibility_status"] == "excluded"
    assert result["selection"]["blocking_gate"] == "axis_flux_af0"


@pytest.mark.parametrize(
    "unsafe_fields",
    [
        {"stage_review_status": "pending_review"},
        {"source_event_review_status": "pending_review"},
        {"source_event_reviewer": None},
        {"source_event_reviewer": "   "},
        {"source_event_review_note": None},
        {"source_event_review_note": "   "},
        {"source_event_reviewed_at": None},
        {"source_event_reviewed_at": "not-a-timestamp"},
        {"source_event_reviewed_at": datetime(2026, 7, 10, 10)},
        {
            "source_event_reviewed_at": datetime(
                2026,
                7,
                12,
                10,
                tzinfo=timezone.utc,
            )
        },
        {"source_event_date": None},
        {"source_event_date": "not-a-date"},
        {"source_event_date": date(2026, 7, 12)},
        {"stage_created_at": None},
        {"stage_created_at": datetime(2026, 7, 12, 10)},
        {"source_event_created_at": None},
        {"source_event_created_at": datetime(2026, 7, 12, 10)},
    ],
    ids=[
        "stage-pending",
        "event-pending",
        "missing-reviewer",
        "blank-reviewer",
        "missing-note",
        "blank-note",
        "missing-reviewed-at",
        "invalid-reviewed-at",
        "naive-reviewed-at",
        "future-review",
        "missing-event-date",
        "invalid-event-date",
        "future-event",
        "missing-stage-created",
        "future-stage-created",
        "missing-source-event-created",
        "future-source-event-created",
    ],
)
def test_prepare_mapping_nulls_commercial_stage_without_full_audit_chain(
    unsafe_fields,
):
    prepared = module.prepare_mapping_for_score(
        repository_mapping_with_stage(**unsafe_fields),
        trade_date=date(2026, 7, 11),
    )

    assert prepared["commercial_stage"] is None
    assert "unaudited_commercial_stage" in prepared["data_limitations"]


def test_prepare_mapping_keeps_fully_audited_historical_stage():
    prepared = module.prepare_mapping_for_score(
        repository_mapping_with_stage(),
        trade_date=date(2026, 7, 11),
    )

    assert prepared["commercial_stage"] == "C5"
    assert "unaudited_commercial_stage" not in prepared["data_limitations"]


def test_selection_repository_writes_pool_gates_into_factor_detail():
    row = evidence(
        "automotive-revenue",
        datetime(2026, 7, 10, 9, tzinfo=timezone.utc),
        "revenue_margin",
        fact_id="fact-automotive-revenue",
        metadata={
            "application_domain": "automotive",
            "profit_confirmed": True,
        },
    )
    bundle = module.score_mapping(
        axial_mapping(),
        [row],
        trade_date=date(2026, 7, 11),
        node_score=80,
    )

    class CapturingCursor:
        def __init__(self):
            self.calls = []

        def execute(self, statement, params):
            self.calls.append((statement, params))

    cursor = CapturingCursor()
    module.SelectionRepository(lambda: None).upsert_score_bundle(cursor, bundle)

    _, params = next(
        call
        for call in cursor.calls
        if "INSERT INTO business_tag_selection_scores" in call[0]
    )
    factor_detail = params[13].adapted
    assert factor_detail["pool_gates"]["route"]["level"] == "AF0"
    assert factor_detail["pool_gates"]["combined"]["eligible"] is False
    assert factor_detail["pool_gate"] == factor_detail["pool_gates"]["combined"]
    assert factor_detail["blocking_gate"] == "axis_flux_af0"


class FakeRepository:
    def __init__(self, *, missing=None):
        self.missing = list(missing or [])
        self.upserts = []
        self.transitions = []
        self.context_calls = []

    def preflight(self, cur):
        return self.missing

    def fetch_mappings(self, cur, **kwargs):
        return [base_mapping()]

    def fetch_asof_evidence(self, cur, mapping_id, cutoff):
        return [
            evidence(
                "prototype",
                datetime(2026, 7, 10, 9, tzinfo=timezone.utc),
                "prototype_delivery",
            )
        ]

    def fetch_node_score(self, cur, **kwargs):
        return {"total_score": 70}

    def fetch_selection_context(self, cur, **kwargs):
        self.context_calls.append(dict(kwargs))
        return {
            "actual_progress_score": 70.0,
            "market_expectation_score": 50.0,
            "evidence_delta_score": 40.0,
            "claim_risk_penalty_score": 10.0,
            "expectation_gap_score": 60.0,
            "catalyst_score": 50.0,
            "risk_score": 20.0,
            "adjusted_price_reaction": 0.1,
            "selection_context_evidence_ids": ["context-1"],
            "selection_context_limitations": [],
        }

    def upsert_score_bundle(self, cur, bundle):
        self.upserts.append(bundle)

    def transition_pool(self, cur, bundle):
        self.transitions.append(bundle)
        return True


class FakeConnection:
    def __init__(self):
        self.cursor_value = object()
        self.commits = 0
        self.rollbacks = 0
        self.closes = 0
        self.cursor_calls = 0

    def cursor(self, **kwargs):
        self.cursor_calls += 1
        return FakeCursorContext(self.cursor_value)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closes += 1


def test_batch_caller_owned_connection_has_zero_transaction_side_effects():
    repository = FakeRepository()
    connection = FakeConnection()

    result = module.run_batch_score(
        pg_url="unused",
        chain_id="dexterous_hand",
        trade_date=date(2026, 7, 11),
        model_version="v2.0",
        dry_run=False,
        repository=repository,
        connection=connection,
    )

    assert result["written"] == 1
    assert connection.commits == 0
    assert connection.rollbacks == 0
    assert connection.closes == 0
    assert connection.cursor_calls == 1


def test_batch_accepts_falsey_caller_connection_without_invoking_factory():
    class FalseyConnection(FakeConnection):
        def __bool__(self):
            return False

    connection = FalseyConnection()
    factory_calls = []

    module.run_batch_score(
        pg_url="unused",
        chain_id="dexterous_hand",
        trade_date=date(2026, 7, 11),
        model_version="v2.0",
        dry_run=True,
        repository=FakeRepository(),
        connection=connection,
        connection_factory=lambda: factory_calls.append(True),
    )

    assert factory_calls == []
    assert connection.cursor_calls == 1
    assert connection.rollbacks == connection.closes == 0


def test_default_repository_is_bound_to_active_connection_without_second_open(
    monkeypatch,
):
    active = FakeConnection()
    created = []

    class BoundRepository(FakeRepository):
        def __init__(self, connection_factory):
            super().__init__()
            self.bound_connection = connection_factory()
            created.append(self)

    monkeypatch.setattr(module, "SelectionRepository", BoundRepository)

    module.run_batch_score(
        pg_url="unused",
        chain_id="dexterous_hand",
        trade_date=date(2026, 7, 11),
        model_version="v2.0",
        dry_run=True,
        connection=active,
    )

    assert len(created) == 1
    assert created[0].bound_connection is active
    assert active.cursor_calls == 1


def test_batch_caller_owned_dry_run_and_exception_do_not_rollback_or_close():
    dry_connection = FakeConnection()
    module.run_batch_score(
        pg_url="unused",
        chain_id="dexterous_hand",
        trade_date=date(2026, 7, 11),
        model_version="v2.0",
        dry_run=True,
        repository=FakeRepository(),
        connection=dry_connection,
    )
    assert dry_connection.rollbacks == 0
    assert dry_connection.closes == 0

    failing_connection = FakeConnection()
    with pytest.raises(module.MissingSelectionTables):
        module.run_batch_score(
            pg_url="unused",
            chain_id="dexterous_hand",
            trade_date=date(2026, 7, 11),
            model_version="v2.0",
            dry_run=False,
            repository=FakeRepository(missing=["daily_kline"]),
            connection=failing_connection,
        )
    assert failing_connection.commits == 0
    assert failing_connection.rollbacks == 0
    assert failing_connection.closes == 0


def test_batch_owned_connection_commit_rollback_close_contract():
    write_connection = FakeConnection()
    module.run_batch_score(
        pg_url="unused",
        chain_id="dexterous_hand",
        trade_date=date(2026, 7, 11),
        model_version="v2.0",
        dry_run=False,
        repository=FakeRepository(),
        connection_factory=lambda: write_connection,
    )
    assert (write_connection.commits, write_connection.rollbacks, write_connection.closes) == (
        1,
        0,
        1,
    )

    dry_connection = FakeConnection()
    module.run_batch_score(
        pg_url="unused",
        chain_id="dexterous_hand",
        trade_date=date(2026, 7, 11),
        model_version="v2.0",
        dry_run=True,
        repository=FakeRepository(),
        connection_factory=lambda: dry_connection,
    )
    assert (dry_connection.commits, dry_connection.rollbacks, dry_connection.closes) == (
        0,
        1,
        1,
    )

    failing_connection = FakeConnection()
    with pytest.raises(module.MissingSelectionTables):
        module.run_batch_score(
            pg_url="unused",
            chain_id="dexterous_hand",
            trade_date=date(2026, 7, 11),
            model_version="v2.0",
            dry_run=False,
            repository=FakeRepository(missing=["daily_kline"]),
            connection_factory=lambda: failing_connection,
        )
    assert (
        failing_connection.commits,
        failing_connection.rollbacks,
        failing_connection.closes,
    ) == (0, 1, 1)


def test_batch_zero_argument_factory_called_once():
    connection = FakeConnection()
    calls = []

    def factory():
        calls.append(True)
        return connection

    module.run_batch_score(
        pg_url="unused",
        chain_id="dexterous_hand",
        trade_date=date(2026, 7, 11),
        model_version="v2.0",
        dry_run=True,
        repository=FakeRepository(),
        connection_factory=factory,
    )

    assert len(calls) == 1


def test_batch_context_merge_is_allowlisted_does_not_mutate_mapping_or_task8_gate(
    monkeypatch,
):
    repository = FakeRepository()
    original = repository_mapping_with_stage(
        data_limitations=["mapping-limit"],
        pool_gate={"level": "E4"},
        blocking_gate="original-blocker",
    )
    before = deepcopy(original)
    repository.fetch_mappings = lambda cur, **kwargs: [original]
    repository.fetch_selection_context = lambda cur, **kwargs: {
        "expectation_gap_score": 61.0,
        "catalyst_score": 52.0,
        "risk_score": 18.0,
        "selection_context_evidence_ids": [None, "", True, "ctx-2", "ctx-1"],
        "selection_context_limitations": [None, False, "", "context-limit"],
        "commercial_stage": "C0",
        "pool_gate": {"level": "malicious"},
        "blocking_gate": None,
        "data_limitations": ["overwrite-attempt"],
    }
    captured = []

    def capture_score(mapping, evidence_rows, **kwargs):
        captured.append(dict(mapping))
        return {
            "mapping_id": mapping["mapping_id"],
            "code": mapping["code"],
            "trade_date": kwargs["trade_date"],
            "model_version": "v2.0",
            "selection": {
                "pool_code": "D",
                "detail": {"pool_gates": {"combined": {"level": "E4"}}},
                "blocking_gate": "original-blocker",
            },
            "evidence_ids": ["prototype"],
            "data_limitations": list(mapping.get("data_limitations") or []),
        }

    monkeypatch.setattr(module, "score_mapping", capture_score)
    result = module.run_batch_score(
        pg_url="unused",
        chain_id="dexterous_hand",
        trade_date=date(2026, 7, 11),
        model_version="v2.0",
        dry_run=True,
        repository=repository,
        connection_factory=FakeConnection,
    )

    assert original == before
    assert captured[0]["commercial_stage"] == "C5"
    assert captured[0]["pool_gate"] == {"level": "E4"}
    assert captured[0]["blocking_gate"] == "original-blocker"
    assert captured[0]["expectation_gap_score"] == 61.0
    assert captured[0]["catalyst_score"] == 52.0
    assert captured[0]["risk_score"] == 18.0
    assert captured[0]["data_limitations"] == ["mapping-limit"]
    bundle = result["results"][0]
    assert bundle["evidence_ids"] == ["ctx-1", "ctx-2", "prototype"]
    assert bundle["data_limitations"] == ["context-limit", "mapping-limit"]
    assert bundle["selection"]["detail"]["blocking_gate"] == "original-blocker"


def test_batch_fetches_context_once_per_mapping_and_persists_context_ids():
    repository = FakeRepository()
    connection = FakeConnection()

    module.run_batch_score(
        pg_url="unused",
        chain_id="dexterous_hand",
        trade_date=date(2026, 7, 11),
        model_version="v2.0",
        dry_run=False,
        repository=repository,
        connection=connection,
    )

    assert len(repository.context_calls) == 1
    assert repository.context_calls[0]["mapping_id"] == "m1"
    assert repository.upserts[0]["evidence_ids"] == ["context-1", "prototype"]
    detail = repository.upserts[0]["selection"]["detail"]
    assert detail["selection_context"]["actual_progress_score"] == 70.0
    assert detail["selection_context_evidence_ids"] == ["context-1"]
    assert detail["next_validation"] == {
        "event": None,
        "date": None,
        "actions": [],
    }


class FakeCursorContext:
    def __init__(self, cursor):
        self.cursor = cursor

    def __enter__(self):
        return self.cursor

    def __exit__(self, exc_type, exc, tb):
        return False


def test_batch_dry_run_scores_without_writing():
    repository = FakeRepository()
    connection = FakeConnection()

    result = module.run_batch_score(
        pg_url="postgresql://unused",
        chain_id="dexterous_hand",
        trade_date=date(2026, 7, 11),
        model_version="v2.0",
        dry_run=True,
        repository=repository,
        connection_factory=lambda: connection,
    )

    assert result["dry_run"] is True
    assert result["mapping_count"] == 1
    assert result["pool_counts"] == {"C": 1}
    assert repository.upserts == []
    assert repository.transitions == []
    assert connection.commits == 0
    assert result["results"][0]["data_limitations"] == [
        "unaudited_commercial_stage"
    ]


def test_batch_passes_prepared_stage_to_score_mapping(monkeypatch):
    repository = FakeRepository()
    unaudited = base_mapping(mapping_id="unaudited", commercial_stage="C5")
    audited = repository_mapping_with_stage(mapping_id="audited")
    repository.fetch_mappings = lambda cur, **kwargs: [unaudited, audited]
    connection = FakeConnection()
    captured = []

    def capture_score(mapping, evidence_rows, **kwargs):
        captured.append(dict(mapping))
        return {
            "mapping_id": mapping["mapping_id"],
            "code": mapping["code"],
            "selection": {"pool_code": "D"},
            "data_limitations": list(mapping.get("data_limitations") or []),
        }

    monkeypatch.setattr(module, "score_mapping", capture_score)

    module.run_batch_score(
        pg_url="postgresql://unused",
        chain_id="dexterous_hand",
        trade_date=date(2026, 7, 11),
        model_version="v2.0",
        dry_run=True,
        repository=repository,
        connection_factory=lambda: connection,
    )

    assert captured[0]["commercial_stage"] is None
    assert captured[0]["data_limitations"] == ["unaudited_commercial_stage"]
    assert captured[1]["commercial_stage"] == "C5"
    assert captured[1]["data_limitations"] == []


def test_batch_write_persists_scores_and_transition_in_one_commit():
    repository = FakeRepository()
    connection = FakeConnection()

    result = module.run_batch_score(
        pg_url="postgresql://unused",
        chain_id="dexterous_hand",
        trade_date=date(2026, 7, 11),
        model_version="v2.0",
        dry_run=False,
        repository=repository,
        connection_factory=lambda: connection,
    )

    assert result["written"] == 1
    assert result["transitions"] == 1
    assert len(repository.upserts) == 1
    assert len(repository.transitions) == 1
    assert connection.commits == 1
    assert "pool_gates" in repository.upserts[0]["selection"]["detail"]


def test_batch_preflight_lists_all_missing_tables():
    repository = FakeRepository(
        missing=["business_tag_selection_scores", "business_tag_pool_state"]
    )

    try:
        module.run_batch_score(
            pg_url="postgresql://unused",
            chain_id="dexterous_hand",
            trade_date=date(2026, 7, 11),
            model_version="v2.0",
            dry_run=True,
            repository=repository,
            connection_factory=FakeConnection,
        )
    except module.MissingSelectionTables as exc:
        assert exc.tables == [
            "business_tag_selection_scores",
            "business_tag_pool_state",
        ]
    else:
        raise AssertionError("missing tables must stop batch scoring")


def test_cli_requires_explicit_trade_date_and_prints_json(monkeypatch, capsys):
    captured = {}

    def fake_run_batch_score(**kwargs):
        captured.update(kwargs)
        return {"dry_run": kwargs["dry_run"], "mapping_count": 0}

    monkeypatch.setattr(module, "run_batch_score", fake_run_batch_score)

    exit_code = module.main(
        [
            "--chain-id",
            "dexterous_hand",
            "--trade-date",
            "2026-07-11",
            "--model-version",
            "v2.0",
            "--dry-run",
        ]
    )

    assert exit_code == 0
    assert captured["trade_date"] == date(2026, 7, 11)
    assert captured["dry_run"] is True
    assert '"mapping_count": 0' in capsys.readouterr().out
