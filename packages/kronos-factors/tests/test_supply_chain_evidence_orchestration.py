from copy import deepcopy
from datetime import date, datetime, timedelta

import pytest

from kronos_factors.engine.industry_chain_templates import get_industry_template
from kronos_factors.engine.supply_chain_evidence_orchestration import (
    EvidenceRunRequest,
    build_node_dimension_updates,
    derive_axial_flux_stage,
    discover_candidate_documents,
    plan_evidence_gaps,
    propose_independent_candidates,
)


AS_OF_DATE = date(2026, 7, 9)


def axial_flux_requirement():
    template = get_industry_template("dexterous_hand")
    return next(
        requirement
        for requirement in template["evidence_requirements"]
        if requirement["requirement_id"] == "dexterous_axial_flux_motor"
    )


def axial_flux_route():
    template = get_industry_template("dexterous_hand")
    return next(
        route
        for route in template["technology_routes"]
        if route["route_id"] == "dexterous_axial_flux_motor"
    )


def axis_document(doc_id: str, company_code: str):
    return {
        "doc_id": doc_id,
        "company_code": company_code,
        "source_level": "strong",
        "publish_time": "2026-06-30T10:00:00+08:00",
        "text": "机器人腕部轴向磁通电机，额定扭矩2Nm",
    }


def evidence_request(**overrides):
    values = {
        "chain_id": "dexterous_hand",
        "as_of_date": AS_OF_DATE,
        "mode": "dry-run",
        "source_policy": "local-first",
    }
    values.update(overrides)
    return EvidenceRunRequest(**values)


def test_product_without_robot_scene_cannot_create_mapping():
    matches = discover_candidate_documents(
        documents=[{"doc_id": "d1", "text": "公司生产空心杯电机，用于消费电子"}],
        requirement={
            "requirement_id": "dexterous_hollow_cup_motor",
            "product_terms": ["空心杯电机"],
            "scene_terms": ["灵巧手", "机器人手指"],
            "negative_examples": ["消费电子"],
        },
    )

    assert matches[0].eligible_for_mapping is False


def test_discovery_requires_canonical_product_terms_not_aliases():
    matches = discover_candidate_documents(
        documents=[{"doc_id": "d-alias", "text": "机器人腕部使用盘式驱动器"}],
        requirement={
            "requirement_id": "dexterous_axial_flux_motor",
            "aliases": ["盘式驱动器"],
            "product_terms": ["轴向磁通电机"],
            "scene_terms": ["机器人腕部"],
            "negative_examples": [],
        },
    )

    assert matches[0].product_hits == ()
    assert matches[0].eligible_for_mapping is False


def test_whole_hand_requirement_can_explicitly_waive_separate_scene_hit():
    matches = discover_candidate_documents(
        documents=[{"doc_id": "d-hand", "text": "公司发布新一代多指灵巧手"}],
        requirement={
            "requirement_id": "dexterous_whole_hand",
            "product_terms": ["灵巧手"],
            "scene_terms": ["机器人"],
            "negative_examples": [],
            "require_product_and_scene": False,
        },
    )

    assert matches[0].eligible_for_mapping is True


def test_gap_planner_separates_two_mappings_for_same_company():
    facts = [
        {
            "fact_id": "fact-force",
            "mapping_id": "force",
            "fact_type": "product_spec",
            "validation_status": "confirmed",
            "publish_time": datetime(2026, 7, 1),
        },
    ]

    gaps = plan_evidence_gaps(
        mapping_ids=("force", "tactile"),
        requirement_ids=("product_or_prototype",),
        facts=facts,
        as_of_date=AS_OF_DATE,
        freshness_policies={},
    )

    assert {(gap.mapping_id, gap.status) for gap in gaps} == {
        ("force", "satisfied"),
        ("tactile", "missing"),
    }


@pytest.mark.parametrize(
    ("fact", "expected_status"),
    [
        (
            {
                "fact_id": "pending-product",
                "mapping_id": "m1",
                "fact_type": "product_spec",
                "validation_status": "pending",
                "publish_time": datetime(2026, 7, 1),
            },
            "pending_review",
        ),
        (
            {
                "fact_id": "company-product",
                "mapping_id": "m1",
                "fact_type": "product_spec",
                "validation_status": "confirmed",
                "fact_scope": "company",
                "publish_time": datetime(2026, 7, 1),
            },
            "proxy",
        ),
        (
            {
                "fact_id": "contradicted-product",
                "mapping_id": "m1",
                "fact_type": "product_spec",
                "validation_status": "confirmed",
                "publish_time": datetime(2026, 7, 1),
                "metadata": {"contradicted": True},
            },
            "contradicted",
        ),
    ],
)
def test_gap_planner_distinguishes_review_proxy_and_contradiction(
    fact,
    expected_status,
):
    gaps = plan_evidence_gaps(
        mapping_ids=("m1",),
        requirement_ids=("product_or_prototype",),
        facts=[fact],
        as_of_date=AS_OF_DATE,
        freshness_policies={},
    )

    assert gaps[0].status == expected_status
    assert gaps[0].evidence_ids == (fact["fact_id"],)


def test_gap_planner_ignores_future_and_unaudited_facts():
    gaps = plan_evidence_gaps(
        mapping_ids=("m1",),
        requirement_ids=("product_or_prototype",),
        facts=[
            {
                "fact_id": "future",
                "mapping_id": "m1",
                "fact_type": "product_spec",
                "validation_status": "confirmed",
                "publish_time": datetime(2026, 7, 10),
            },
            {
                "fact_id": "unaudited",
                "mapping_id": "m1",
                "fact_type": "product_spec",
                "publish_time": datetime(2026, 7, 1),
            },
        ],
        as_of_date=AS_OF_DATE,
        freshness_policies={},
    )

    assert gaps[0].status == "missing"
    assert gaps[0].evidence_ids == ()


def test_pending_contradiction_stays_pending_until_reviewed():
    gaps = plan_evidence_gaps(
        mapping_ids=("m1",),
        requirement_ids=("product_or_prototype",),
        facts=[
            {
                "fact_id": "pending-contradiction",
                "mapping_id": "m1",
                "fact_type": "product_spec",
                "validation_status": "pending",
                "publish_time": datetime(2026, 7, 1),
                "metadata": {"contradicted": True},
            },
        ],
        as_of_date=AS_OF_DATE,
        freshness_policies={},
    )

    assert gaps[0].status == "pending_review"


def test_gap_planner_expires_facts_by_requirement_policy():
    gaps = plan_evidence_gaps(
        mapping_ids=("m1",),
        requirement_ids=("customer_validation",),
        facts=[
            {
                "fact_id": "old-test",
                "mapping_id": "m1",
                "fact_type": "customer_validation",
                "validation_status": "confirmed",
                "publish_time": datetime.combine(
                    AS_OF_DATE - timedelta(days=181),
                    datetime.min.time(),
                ),
            },
        ],
        as_of_date=AS_OF_DATE,
        freshness_policies={"customer_test": 180},
    )

    assert gaps[0].status == "stale"
    assert gaps[0].evidence_ids == ("old-test",)


def test_gap_planner_enforces_metadata_flags_from_global_catalog():
    common = {
        "mapping_id": "m1",
        "fact_type": "revenue_margin",
        "validation_status": "confirmed",
        "publish_time": datetime(2026, 7, 1),
    }
    gaps = plan_evidence_gaps(
        mapping_ids=("m1",),
        requirement_ids=("recognized_revenue",),
        facts=[
            {"fact_id": "not-confirmed", **common, "metadata": {}},
            {
                "fact_id": "confirmed-revenue",
                **common,
                "metadata": {"revenue_confirmed": True},
            },
        ],
        as_of_date=AS_OF_DATE,
        freshness_policies={},
    )

    assert gaps[0].status == "satisfied"
    assert gaps[0].evidence_ids == ("confirmed-revenue",)


def test_automotive_axial_flux_stays_af0():
    stage = derive_axial_flux_stage(
        [
            {
                "fact_type": "product_spec",
                "validation_status": "confirmed",
                "metadata": {"application_domain": "automotive"},
            },
        ]
    )

    assert stage == "AF0"


def test_unaudited_and_pending_axial_flux_facts_never_promote_stage():
    facts = [
        {
            "fact_type": "prototype_delivery",
            "metadata": {},
        },
        {
            "fact_type": "product_spec",
            "validation_status": "pending",
            "metadata": {"application_domain": "robot_wrist"},
        },
    ]

    assert derive_axial_flux_stage(facts) == "AF0"


def test_axial_flux_af1_honors_patent_metadata_and_any_mode():
    invalid_patent = {
        "fact_type": "patent_standard",
        "validation_status": "confirmed",
        "metadata": {"legal_status": "active"},
    }
    valid_patent = {
        "fact_type": "patent_standard",
        "validation_status": "confirmed",
        "metadata": {
            "legal_status": "granted",
            "legal_status_date": "2026-06-30",
        },
    }

    assert derive_axial_flux_stage([invalid_patent]) == "AF0"
    assert derive_axial_flux_stage([valid_patent]) == "AF1"


def test_axial_flux_af6_requires_every_configured_clause():
    order = {
        "fact_type": "order_award",
        "validation_status": "confirmed",
        "metadata": {"application_domain": "robot_hand"},
    }
    revenue = {
        "fact_type": "revenue_margin",
        "validation_status": "confirmed",
        "metadata": {
            "application_domain": "robot_hand",
            "revenue_confirmed": True,
        },
    }

    assert derive_axial_flux_stage([order]) == "AF0"
    assert derive_axial_flux_stage([order, revenue]) == "AF6"


def test_axial_flux_interpreter_uses_optional_route_match_mode():
    route = deepcopy(axial_flux_route())
    route["authenticity_ladder"]["AF1"]["fact_match_mode"] = "all"
    patent = {
        "fact_type": "patent_standard",
        "validation_status": "confirmed",
        "metadata": {
            "legal_status": "active",
            "legal_status_date": "2026-06-30",
        },
    }

    assert derive_axial_flux_stage([patent], route=route) == "AF0"


@pytest.mark.parametrize(
    ("expected_stage", "facts"),
    [
        ("AF0", []),
        (
            "AF1",
            [
                {
                    "fact_type": "prototype_delivery",
                    "validation_status": "confirmed",
                    "metadata": {},
                },
            ],
        ),
        (
            "AF2",
            [
                {
                    "fact_type": "product_spec",
                    "validation_status": "confirmed",
                    "metadata": {"application_domain": "robot_hand"},
                },
            ],
        ),
        (
            "AF3",
            [
                {
                    "fact_type": "prototype_delivery",
                    "validation_status": "confirmed",
                    "metadata": {
                        "application_domain": "robot_wrist",
                        "installation_position": "wrist",
                    },
                },
            ],
        ),
        (
            "AF4",
            [
                {
                    "fact_type": "customer_validation",
                    "validation_status": "confirmed",
                    "metadata": {"application_domain": "robot_joint"},
                },
            ],
        ),
        (
            "AF5",
            [
                {
                    "fact_type": "small_batch_delivery",
                    "validation_status": "confirmed",
                    "metadata": {"application_domain": "dexterous_hand"},
                },
            ],
        ),
        (
            "AF6",
            [
                {
                    "fact_type": "order_award",
                    "validation_status": "confirmed",
                    "metadata": {"application_domain": "robot_hand"},
                },
                {
                    "fact_type": "revenue_margin",
                    "validation_status": "confirmed",
                    "metadata": {
                        "application_domain": "robot_hand",
                        "revenue_confirmed": True,
                    },
                },
            ],
        ),
    ],
)
def test_axial_flux_returns_every_configured_stage(expected_stage, facts):
    assert derive_axial_flux_stage(facts) == expected_stage


def test_axial_flux_exclusion_is_fact_local_not_a_batch_wide_veto():
    facts = [
        {
            "fact_type": "product_spec",
            "validation_status": "confirmed",
            "metadata": {"application_domain": "automotive"},
        },
        {
            "fact_type": "product_spec",
            "validation_status": "confirmed",
            "metadata": {"application_domain": "robot_wrist"},
        },
    ]

    assert derive_axial_flux_stage(facts) == "AF2"


def test_independent_axial_flux_hit_becomes_auditable_candidate_not_approved_evidence():
    hits = propose_independent_candidates(
        documents=[axis_document("d-axis-1", "688001")],
        requirement=axial_flux_requirement(),
        as_of_date=AS_OF_DATE,
    )

    assert hits[0].eligible_for_mapping is True
    assert hits[0].validation_status == "pending"
    assert hits[0].proposal.status == "candidate"
    assert hits[0].proposal.evidence_ids == ()
    assert hits[0].proposal.technology_route_id == "dexterous_axial_flux_motor"


def test_independent_discovery_enforces_source_cutoff_and_negative_context():
    weak = {**axis_document("weak", "688001"), "source_level": "weak"}
    future = {
        **axis_document("future", "688002"),
        "publish_time": "2026-07-10T00:00:00+08:00",
    }
    automotive = {
        **axis_document("automotive", "688003"),
        "text": "机器人腕部轴向磁通电机，仅用于汽车驱动电机",
    }

    hits = propose_independent_candidates(
        documents=[weak, future, automotive],
        requirement=axial_flux_requirement(),
        as_of_date=AS_OF_DATE,
    )

    assert [hit.doc_id for hit in hits] == ["weak", "future", "automotive"]
    assert all(hit.eligible_for_mapping is False for hit in hits)
    assert all(hit.proposal is None for hit in hits)


def test_non_independent_requirement_does_not_emit_discovery_hits():
    requirement = deepcopy(axial_flux_requirement())
    requirement["independent_discovery"] = False

    assert propose_independent_candidates(
        documents=[axis_document("d1", "688001")],
        requirement=requirement,
        as_of_date=AS_OF_DATE,
    ) == []


def test_multiple_documents_for_same_company_requirement_share_one_mapping():
    hits = propose_independent_candidates(
        documents=[axis_document("d1", "688001"), axis_document("d2", "688001")],
        requirement=axial_flux_requirement(),
        as_of_date=AS_OF_DATE,
    )

    assert len({hit.proposal.mapping_id for hit in hits}) == 1
    assert {hit.doc_id for hit in hits} == {"d1", "d2"}


def test_candidate_provenance_merges_deduplicated_document_and_fact_ids():
    documents = [
        {
            **axis_document("d2", "688001"),
            "fact_ids": ["pending-f2", "pending-f1"],
        },
        {
            **axis_document("d1", "688001"),
            "fact_id": "pending-f1",
        },
    ]

    hits = propose_independent_candidates(
        documents=documents,
        requirement=axial_flux_requirement(),
        as_of_date=AS_OF_DATE,
    )
    paths = [hit.proposal.provenance["l1_l8_path"] for hit in hits]

    assert paths[0] == paths[1]
    assert paths[0]["requirement_id"] == "dexterous_axial_flux_motor"
    assert paths[0]["technology_route_id"] == "dexterous_axial_flux_motor"
    assert paths[0]["discovery_doc_ids"] == ["d1", "d2"]
    assert paths[0]["discovery_fact_ids"] == ["pending-f1", "pending-f2"]


def test_only_approved_facts_update_node_dimensions():
    updates = build_node_dimension_updates(
        facts=[
            {
                "fact_id": "pending-physical",
                "validation_status": "pending",
                "metadata": {"dimension_ids": ["physical_bom"]},
            },
            {
                "fact_id": "confirmed-validation",
                "validation_status": "confirmed",
                "metadata": {"dimension_ids": ["evidence_validation"]},
            },
        ],
        node_id="dexterous_hand_foundation",
        as_of_date=AS_OF_DATE,
    )

    assert [item.dimension_id for item in updates] == ["evidence_validation"]
    assert updates[0].status == "known"


def test_node_dimension_updates_ignore_unaudited_facts_and_mark_proxy_scores():
    updates = build_node_dimension_updates(
        facts=[
            {
                "fact_id": "unaudited",
                "metadata": {"dimension_ids": ["function_value"]},
            },
            {
                "fact_id": "proxy-without-method",
                "validation_status": "confirmed",
                "fact_scope": "company",
                "score": 0.9,
                "metadata": {"dimension_ids": ["market_expectation"]},
            },
            {
                "fact_id": "proxy-with-method",
                "validation_status": "confirmed",
                "fact_scope": "company",
                "score": 0.4,
                "metadata": {
                    "dimension_ids": ["physical_bom"],
                    "scoring_method": "audited_method_v1",
                },
            },
        ],
        node_id="dexterous_hand_foundation",
        as_of_date=AS_OF_DATE,
    )

    by_dimension = {item.dimension_id: item for item in updates}
    assert set(by_dimension) == {"market_expectation", "physical_bom"}
    assert by_dimension["market_expectation"].status == "proxy"
    assert by_dimension["market_expectation"].score is None
    assert by_dimension["physical_bom"].status == "proxy"
    assert by_dimension["physical_bom"].score == 0.4


def test_confirmed_contradiction_updates_only_mentioned_dimension():
    updates = build_node_dimension_updates(
        facts=[
            {
                "fact_id": "contradiction",
                "validation_status": "confirmed",
                "metadata": {
                    "dimension_ids": ["technology_route"],
                    "contradicted": True,
                },
            },
        ],
        node_id="dexterous_hand_foundation",
        as_of_date=AS_OF_DATE,
    )

    assert [(item.dimension_id, item.status) for item in updates] == [
        ("technology_route", "contradicted"),
    ]


def test_source_limits_reject_unknown_non_positive_or_boolean_values():
    with pytest.raises(ValueError):
        evidence_request(source_limits={"official_discovery_documents": -1})
    with pytest.raises(ValueError):
        evidence_request(source_limits={"unknown_source": 10})
    with pytest.raises(ValueError):
        evidence_request(source_limits={"mapped_official_tasks": True})


def test_mapping_and_company_scopes_are_mutually_exclusive():
    with pytest.raises(ValueError, match="mapping_ids and company_codes"):
        evidence_request(mapping_ids=("m1",), company_codes=("688001",))


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"chain_id": ""}, "chain_id"),
        ({"as_of_date": "2026-07-09"}, "as_of_date"),
        ({"mode": "invalid"}, "mode"),
        ({"source_policy": "network-first"}, "source_policy"),
        ({"allow_score": 1}, "allow_score"),
        ({"mapping_ids": ("",)}, "mapping_ids"),
    ],
)
def test_evidence_request_strictly_validates_public_fields(overrides, message):
    with pytest.raises(ValueError, match=message):
        evidence_request(**overrides)
