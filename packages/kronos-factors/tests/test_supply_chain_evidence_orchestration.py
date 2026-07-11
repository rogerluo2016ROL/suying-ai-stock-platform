from copy import deepcopy
from datetime import date, datetime, timedelta

import pytest

from kronos_factors.engine import supply_chain_evidence_orchestration as orchestration
from kronos_factors.engine.industry_chain_templates import get_industry_template
from kronos_factors.engine.supply_chain_evidence_orchestration import (
    CandidateMappingProposal,
    EvidenceRunRequest,
    build_node_dimension_updates,
    derive_axial_flux_stage,
    discover_candidate_documents,
    plan_evidence_gaps,
    propose_independent_candidates,
)


AS_OF_DATE = date(2026, 7, 9)


def reviewed_fact(**overrides):
    fact = {
        "validation_status": "confirmed",
        "reviewer": "reviewer-1",
        "review_note": "已核对原始证据",
        "reviewed_at": datetime(2026, 7, 2, 10, 0),
        "publish_time": datetime(2026, 7, 1, 9, 0),
        "source_level": "strong",
        "fact_nature": "confirmed_fact",
        "metadata": {},
    }
    fact.update(overrides)
    return fact


def axial_fact(fact_type, metadata=None, **overrides):
    return reviewed_fact(
        fact_type=fact_type,
        metadata=metadata or {},
        **overrides,
    )


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
        reviewed_fact(
            fact_id="fact-force",
            mapping_id="force",
            fact_type="product_spec",
        ),
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
            reviewed_fact(
                fact_id="pending-product",
                mapping_id="m1",
                fact_type="product_spec",
                validation_status="pending",
                fact_nature="company_claim",
            ),
            "pending_review",
        ),
        (
            reviewed_fact(
                fact_id="company-product",
                mapping_id="m1",
                fact_type="product_spec",
                fact_scope="company",
            ),
            "proxy",
        ),
        (
            reviewed_fact(
                fact_id="contradicted-product",
                mapping_id="m1",
                fact_type="product_spec",
                metadata={"contradicted": True},
            ),
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
            reviewed_fact(
                fact_id="future",
                mapping_id="m1",
                fact_type="product_spec",
                publish_time=datetime(2026, 7, 10),
            ),
            {
                "fact_id": "unaudited",
                "mapping_id": "m1",
                "fact_type": "product_spec",
                "publish_time": datetime(2026, 7, 1),
                "source_level": "strong",
                "fact_nature": "confirmed_fact",
                "metadata": {},
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
            reviewed_fact(
                fact_id="pending-contradiction",
                mapping_id="m1",
                fact_type="product_spec",
                validation_status="pending",
                fact_nature="company_claim",
                metadata={"contradicted": True},
            ),
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
            reviewed_fact(
                fact_id="old-test",
                mapping_id="m1",
                fact_type="customer_validation",
                publish_time=datetime.combine(
                    AS_OF_DATE - timedelta(days=181),
                    datetime.min.time(),
                ),
            ),
        ],
        as_of_date=AS_OF_DATE,
        freshness_policies={"customer_test": 180},
    )

    assert gaps[0].status == "stale"
    assert gaps[0].evidence_ids == ("old-test",)


def test_gap_planner_enforces_metadata_flags_from_global_catalog():
    common = reviewed_fact(mapping_id="m1", fact_type="revenue_margin")
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
            axial_fact(
                "product_spec",
                {"application_domain": "automotive"},
            ),
        ]
    )

    assert stage == "AF0"


def test_unaudited_and_pending_axial_flux_facts_never_promote_stage():
    facts = [
        {
            "fact_type": "prototype_delivery",
            "publish_time": datetime(2026, 7, 1),
            "metadata": {},
        },
        axial_fact(
            "product_spec",
            {"application_domain": "robot_wrist"},
            validation_status="pending",
        ),
    ]

    assert derive_axial_flux_stage(facts) == "AF0"


def test_axial_flux_af1_honors_patent_metadata_and_any_mode():
    invalid_patent = axial_fact("patent_standard", {"legal_status": "active"})
    valid_patent = axial_fact(
        "patent_standard",
        {
            "legal_status": "granted",
            "legal_status_date": "2026-06-30",
        },
    )

    assert derive_axial_flux_stage([invalid_patent]) == "AF0"
    assert derive_axial_flux_stage([valid_patent]) == "AF1"


def test_axial_flux_af6_requires_every_configured_clause():
    order = axial_fact("order_award", {"application_domain": "robot_hand"})
    revenue = axial_fact(
        "revenue_margin",
        {
            "application_domain": "robot_hand",
            "revenue_confirmed": True,
        },
    )

    assert derive_axial_flux_stage([order]) == "AF0"
    assert derive_axial_flux_stage([order, revenue]) == "AF6"


def test_axial_flux_interpreter_uses_optional_route_match_mode():
    route = deepcopy(axial_flux_route())
    route["authenticity_ladder"]["AF1"]["fact_match_mode"] = "all"
    patent = axial_fact(
        "patent_standard",
        {
            "legal_status": "active",
            "legal_status_date": "2026-06-30",
        },
    )

    assert derive_axial_flux_stage([patent], route=route) == "AF0"


@pytest.mark.parametrize(
    ("expected_stage", "facts"),
    [
        ("AF0", []),
        (
            "AF1",
            [
                axial_fact("prototype_delivery"),
            ],
        ),
        (
            "AF2",
            [
                axial_fact("product_spec", {"application_domain": "robot_hand"}),
            ],
        ),
        (
            "AF3",
            [
                axial_fact(
                    "prototype_delivery",
                    {
                        "application_domain": "robot_wrist",
                        "installation_position": "wrist",
                    },
                ),
            ],
        ),
        (
            "AF4",
            [
                axial_fact(
                    "customer_validation",
                    {"application_domain": "robot_joint"},
                ),
            ],
        ),
        (
            "AF5",
            [
                axial_fact(
                    "small_batch_delivery",
                    {"application_domain": "dexterous_hand"},
                ),
            ],
        ),
        (
            "AF6",
            [
                axial_fact("order_award", {"application_domain": "robot_hand"}),
                axial_fact(
                    "revenue_margin",
                    {
                        "application_domain": "robot_hand",
                        "revenue_confirmed": True,
                    },
                ),
            ],
        ),
    ],
)
def test_axial_flux_returns_every_configured_stage(expected_stage, facts):
    assert derive_axial_flux_stage(facts) == expected_stage


def test_axial_flux_exclusion_is_fact_local_not_a_batch_wide_veto():
    facts = [
        axial_fact("product_spec", {"application_domain": "automotive"}),
        axial_fact("product_spec", {"application_domain": "robot_wrist"}),
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


def test_independent_discovery_cutoff_uses_shanghai_calendar_date():
    before_cutoff = {
        **axis_document("before", "688001"),
        "publish_time": "2026-07-09T15:59:00+00:00",
    }
    after_cutoff = {
        **axis_document("after", "688002"),
        "publish_time": "2026-07-09T17:00:00+00:00",
    }

    hits = propose_independent_candidates(
        [before_cutoff, after_cutoff],
        requirement=axial_flux_requirement(),
        as_of_date=AS_OF_DATE,
    )

    assert [hit.eligible_for_mapping for hit in hits] == [True, False]


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
    assert paths[0]["discovery_doc_ids"] == ("d1", "d2")
    assert paths[0]["discovery_fact_ids"] == ("pending-f1", "pending-f2")


def test_only_approved_facts_update_node_dimensions():
    updates = build_node_dimension_updates(
        facts=[
            reviewed_fact(
                fact_id="pending-physical",
                validation_status="pending",
                metadata={"dimension_ids": ["physical_bom"]},
            ),
            reviewed_fact(
                fact_id="confirmed-validation",
                metadata={"dimension_ids": ["evidence_validation"]},
            ),
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
                "publish_time": datetime(2026, 7, 1),
                "metadata": {"dimension_ids": ["function_value"]},
            },
            reviewed_fact(
                fact_id="proxy-without-method",
                fact_scope="company",
                score=0.9,
                metadata={"dimension_ids": ["market_expectation"]},
            ),
            reviewed_fact(
                fact_id="proxy-with-method",
                fact_scope="company",
                score=0.4,
                metadata={
                    "dimension_ids": ["physical_bom"],
                    "scoring_method": "audited_method_v1",
                },
            ),
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
            reviewed_fact(
                fact_id="contradiction",
                metadata={
                    "dimension_ids": ["technology_route"],
                    "contradicted": True,
                },
            ),
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


def test_complete_review_gate_requires_audit_fields_and_historical_cutoff():
    valid = reviewed_fact()
    assert orchestration._is_fully_reviewed_fact(valid, AS_OF_DATE) is True

    for field in ("reviewer", "review_note", "reviewed_at"):
        incomplete = dict(valid)
        incomplete.pop(field)
        assert orchestration._is_fully_reviewed_fact(incomplete, AS_OF_DATE) is False

    future_review = {**valid, "reviewed_at": datetime(2026, 7, 10, 9, 0)}
    assert orchestration._is_fully_reviewed_fact(future_review, AS_OF_DATE) is False

    for field, value in (
        ("reviewer", "   "),
        ("review_note", ""),
        ("reviewed_at", "not-a-date"),
    ):
        assert orchestration._is_fully_reviewed_fact(
            {**valid, field: value},
            AS_OF_DATE,
        ) is False


@pytest.mark.parametrize("missing_field", ["reviewer", "review_note", "reviewed_at"])
def test_gap_confirmed_fact_without_complete_audit_stays_pending(missing_field):
    fact = reviewed_fact(
        fact_id="product",
        mapping_id="m1",
        fact_type="product_spec",
    )
    fact.pop(missing_field)

    gap = plan_evidence_gaps(
        mapping_ids=("m1",),
        requirement_ids=("product_or_prototype",),
        facts=[fact],
        as_of_date=AS_OF_DATE,
        freshness_policies={},
    )[0]
    assert gap.status == "pending_review"


def test_gap_fails_closed_for_catalog_fields_publish_time_and_top_level_flags():
    valid = reviewed_fact(
        fact_id="revenue",
        mapping_id="m1",
        fact_type="revenue_margin",
        metadata={"revenue_confirmed": True},
    )
    cases = []
    for field in ("source_level", "fact_nature"):
        broken = dict(valid)
        broken.pop(field)
        cases.append(broken)
    cases.extend(
        [
            {**valid, "source_level": "unknown"},
            {**valid, "source_level": "weak"},
            {**valid, "fact_nature": "unreviewed_claim"},
            {**valid, "publish_time": None, "created_at": datetime(2026, 7, 1)},
            {**valid, "publish_time": "not-a-date", "event_time": datetime(2026, 7, 1)},
            {
                **valid,
                "metadata": {},
                "revenue_confirmed": True,
            },
        ]
    )

    for fact in cases:
        gap = plan_evidence_gaps(
            mapping_ids=("m1",),
            requirement_ids=("recognized_revenue",),
            facts=[fact],
            as_of_date=AS_OF_DATE,
            freshness_policies={},
        )[0]
        assert gap.status == "missing"


def test_gap_review_after_as_of_is_not_historically_satisfied():
    fact = reviewed_fact(
        fact_id="product",
        mapping_id="m1",
        fact_type="product_spec",
        reviewed_at=datetime(2026, 7, 10, 9, 0),
    )

    gap = plan_evidence_gaps(
        mapping_ids=("m1",),
        requirement_ids=("product_or_prototype",),
        facts=[fact],
        as_of_date=AS_OF_DATE,
        freshness_policies={},
    )[0]
    assert gap.status == "pending_review"


def test_gap_uses_shanghai_date_for_utc_publish_and_review_cutoffs():
    published_next_shanghai_day = reviewed_fact(
        fact_id="late-publish",
        mapping_id="m1",
        fact_type="product_spec",
        publish_time="2026-07-09T17:00:00+00:00",
    )
    reviewed_next_shanghai_day = reviewed_fact(
        fact_id="late-review",
        mapping_id="m1",
        fact_type="product_spec",
        reviewed_at="2026-07-09T17:00:00+00:00",
    )

    gaps = plan_evidence_gaps(
        mapping_ids=("m1",),
        requirement_ids=("product_or_prototype",),
        facts=[published_next_shanghai_day, reviewed_next_shanghai_day],
        as_of_date=AS_OF_DATE,
        freshness_policies={},
    )

    assert gaps[0].status == "pending_review"
    assert gaps[0].evidence_ids == ("late-review",)


def test_dimensions_require_full_historical_review_and_publish_time():
    valid = reviewed_fact(
        fact_id="dimension",
        metadata={"dimension_ids": ["technology_route"]},
    )
    incomplete = dict(valid)
    incomplete.pop("review_note")
    future_review = {**valid, "reviewed_at": datetime(2026, 7, 10, 9, 0)}
    future_publish = {**valid, "publish_time": datetime(2026, 7, 10, 9, 0)}
    unknown_publish = {**valid, "publish_time": "not-a-date"}

    updates = build_node_dimension_updates(
        [incomplete, future_review, future_publish, unknown_publish],
        node_id="dexterous_hand_foundation",
        as_of_date=AS_OF_DATE,
    )
    assert updates == []


def test_dimensions_use_shanghai_date_for_utc_cutoffs():
    updates = build_node_dimension_updates(
        [
            reviewed_fact(
                fact_id="late-publish",
                publish_time="2026-07-09T17:00:00+00:00",
                metadata={"dimension_ids": ["technology_route"]},
            ),
            reviewed_fact(
                fact_id="late-review",
                reviewed_at="2026-07-09T17:00:00+00:00",
                metadata={"dimension_ids": ["technology_route"]},
            ),
        ],
        node_id="dexterous_hand_foundation",
        as_of_date=AS_OF_DATE,
    )

    assert updates == []


def test_af_metadata_and_review_gates_fail_closed_for_af2_and_af6():
    top_level_domain = reviewed_fact(
        fact_type="product_spec",
        metadata={},
        application_domain="robot_hand",
    )
    incomplete_af2 = reviewed_fact(
        fact_type="product_spec",
        metadata={"application_domain": "robot_hand"},
    )
    incomplete_af2.pop("reviewer")
    order = reviewed_fact(
        fact_type="order_award",
        metadata={"application_domain": "robot_hand"},
    )
    revenue = reviewed_fact(
        fact_type="revenue_margin",
        reviewed_at=datetime(2026, 7, 10, 9, 0),
        metadata={"application_domain": "robot_hand", "revenue_confirmed": True},
    )

    assert derive_axial_flux_stage([top_level_domain]) == "AF0"
    assert derive_axial_flux_stage([incomplete_af2]) == "AF0"
    assert derive_axial_flux_stage(
        [order, revenue],
        as_of_date=AS_OF_DATE,
    ) == "AF0"


def test_af_route_contract_and_value_constraints_ignore_top_level_metadata():
    patent = reviewed_fact(
        fact_type="patent_standard",
        metadata={},
        legal_status="active",
        legal_status_date="2026-07-01",
    )
    order = axial_fact("order_award", {"application_domain": "robot_hand"})
    revenue = reviewed_fact(
        fact_type="revenue_margin",
        metadata={"application_domain": "robot_hand"},
        revenue_confirmed=True,
    )

    assert derive_axial_flux_stage([patent]) == "AF0"
    assert derive_axial_flux_stage([order, revenue]) == "AF0"


def test_af_required_metadata_rejects_empty_collections():
    patent = axial_fact(
        "patent_standard",
        {"legal_status": "active", "legal_status_date": ()},
    )
    installed_prototype = axial_fact(
        "prototype_delivery",
        {
            "application_domain": "robot_wrist",
            "installation_position": (),
        },
    )

    assert derive_axial_flux_stage([patent]) == "AF0"
    assert derive_axial_flux_stage([installed_prototype]) == "AF1"


@pytest.mark.parametrize(
    "fact",
    [
        axial_fact("product_spec", {"application_domain": "robot_hand"}, publish_time=None),
        axial_fact(
            "product_spec",
            {"application_domain": "robot_hand"},
            publish_time="not-a-date",
        ),
        axial_fact(
            "product_spec",
            {"application_domain": "robot_hand"},
            publish_time=datetime(2026, 7, 10, 9, 0),
        ),
    ],
)
def test_af2_requires_valid_historical_publish_time(fact):
    assert derive_axial_flux_stage([fact], as_of_date=AS_OF_DATE) == "AF0"


def test_request_limits_and_proposal_provenance_are_recursively_frozen():
    limits = {"discovery": 1}
    request = evidence_request(source_limits=limits)
    limits["discovery"] = 99
    assert request.source_limits["discovery"] == 1
    with pytest.raises(TypeError):
        request.source_limits["discovery"] = 2

    raw = {"l1_l8_path": {"discovery_doc_ids": ["d1"]}}
    proposal = CandidateMappingProposal(
        mapping_id="m1",
        company_code="688001",
        chain_id="dexterous_hand",
        node_id="dexterous_hand_foundation",
        tag_name="轴向磁通电机",
        technology_route_id="dexterous_axial_flux_motor",
        status="candidate",
        confidence=0.35,
        evidence_ids=(),
        provenance=raw,
    )
    raw["l1_l8_path"]["discovery_doc_ids"].append("d2")
    assert proposal.provenance["l1_l8_path"]["discovery_doc_ids"] == ("d1",)
    with pytest.raises(TypeError):
        proposal.provenance["l1_l8_path"]["new"] = "blocked"
