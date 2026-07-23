"""Contracts for V2 research profile and dexterous-hand template."""

from copy import deepcopy

import pytest

from kronos_factors.engine.chain_deconstruct import build_industry_template_tree
from kronos_factors.engine.industry_chain_evidence_requirements import (
    load_evidence_requirements,
)
from kronos_factors.engine.industry_chain_templates import (
    get_business_evidence_requirement,
    get_industry_template,
    load_selection_v2_profile,
    load_template_catalog,
    validate_industry_evidence_coverage,
    validate_selection_v2_profile,
)


EXPECTED_LAYERS = [
    "demand",
    "task",
    "core_product",
    "foundation",
    "integration",
    "supporting",
    "infrastructure",
    "commercialization",
]

EXPECTED_DEXTEROUS_EVIDENCE_REQUIREMENTS = [
    {
        "requirement_id": "dexterous_whole_hand",
        "business_keywords": ["灵巧手", "机器人末端"],
        "node_id": "dexterous_hand_core_product",
        "technology_route_id": None,
        "aliases": ["机器人手", "仿生手", "多指灵巧手", "机器人末端"],
        "product_terms": ["灵巧手", "机器人手", "多指手", "末端执行器"],
        "scene_terms": ["机器人", "具身智能", "人形机器人"],
        "negative_examples": ["普通夹爪"],
        "require_product_and_scene": False,
        "required_evidence_type_ids": [
            "product_or_prototype",
            "customer_validation",
            "order_or_delivery",
            "recognized_revenue",
            "recognized_profit",
        ],
        "next_validation_action": "核验整手规格、客户和交付",
        "independent_discovery": False,
    },
    {
        "requirement_id": "dexterous_micro_actuator",
        "business_keywords": ["微型执行器"],
        "node_id": "dexterous_hand_integration",
        "technology_route_id": None,
        "aliases": ["微型驱动器", "微型线性执行器"],
        "product_terms": ["微型执行器", "微型驱动器"],
        "scene_terms": ["灵巧手", "机器人手指", "机器人关节"],
        "negative_examples": ["汽车执行器"],
        "require_product_and_scene": True,
        "required_evidence_type_ids": [
            "product_or_prototype",
            "customer_validation",
            "order_or_delivery",
            "recognized_revenue",
        ],
        "next_validation_action": "核验机器人安装位置和客户测试",
        "independent_discovery": False,
    },
    {
        "requirement_id": "dexterous_hollow_cup_motor",
        "business_keywords": ["空心杯电机"],
        "node_id": "dexterous_hand_foundation",
        "technology_route_id": "dexterous_hollow_cup_screw",
        "aliases": ["空杯电机", "无铁芯电机"],
        "product_terms": ["空心杯电机", "空杯电机", "无铁芯电机"],
        "scene_terms": ["灵巧手", "机器人手指", "末端执行器"],
        "negative_examples": ["消费电子震动马达"],
        "require_product_and_scene": True,
        "required_evidence_type_ids": [
            "business_presence",
            "product_or_prototype",
            "customer_validation",
            "order_or_delivery",
            "recognized_revenue",
            "recognized_profit",
        ],
        "next_validation_action": "核验灵巧手规格、送样和量产收入",
        "independent_discovery": False,
    },
    {
        "requirement_id": "dexterous_frameless_motor",
        "business_keywords": ["无框电机"],
        "node_id": "dexterous_hand_foundation",
        "technology_route_id": "dexterous_frameless_low_ratio",
        "aliases": ["力矩电机", "无框力矩电机"],
        "product_terms": ["无框电机", "无框力矩电机"],
        "scene_terms": ["灵巧手", "机器人关节", "机器人腕部"],
        "negative_examples": ["通用工业伺服"],
        "require_product_and_scene": True,
        "required_evidence_type_ids": [
            "business_presence",
            "product_or_prototype",
            "customer_validation",
            "order_or_delivery",
            "recognized_revenue",
        ],
        "next_validation_action": "核验机器人尺寸参数和装机位置",
        "independent_discovery": False,
    },
    {
        "requirement_id": "dexterous_axial_flux_motor",
        "business_keywords": ["轴向磁通电机"],
        "node_id": "dexterous_hand_foundation",
        "technology_route_id": "dexterous_axial_flux_motor",
        "aliases": ["盘式电机", "轴向磁场电机"],
        "product_terms": ["轴向磁通电机", "轴向磁场电机", "盘式电机"],
        "scene_terms": ["灵巧手", "机器人手指", "机器人关节", "机器人腕部"],
        "negative_examples": ["汽车驱动电机", "轮毂电机", "航空推进电机"],
        "require_product_and_scene": True,
        "required_evidence_type_ids": [
            "business_presence",
            "product_or_prototype",
            "customer_validation",
            "order_or_delivery",
            "recognized_revenue",
        ],
        "next_validation_action": "核验机器人规格、装机、客户验证和收入",
        "independent_discovery": True,
    },
    {
        "requirement_id": "dexterous_micro_screw",
        "business_keywords": ["微型丝杠"],
        "node_id": "dexterous_hand_foundation",
        "technology_route_id": "dexterous_hollow_cup_screw",
        "aliases": ["微型滚珠丝杠", "行星滚柱丝杠"],
        "product_terms": ["微型丝杠", "微型滚珠丝杠", "微型行星滚柱丝杠"],
        "scene_terms": ["灵巧手", "机器人手指", "微型执行器"],
        "negative_examples": ["机床丝杠"],
        "require_product_and_scene": True,
        "required_evidence_type_ids": [
            "business_presence",
            "product_or_prototype",
            "customer_validation",
            "order_or_delivery",
            "recognized_revenue",
        ],
        "next_validation_action": "核验尺寸、负载、送样和交付",
        "independent_discovery": False,
    },
    {
        "requirement_id": "dexterous_tactile_sensor",
        "business_keywords": ["触觉传感器"],
        "node_id": "dexterous_hand_foundation",
        "technology_route_id": "dexterous_tactile_sensing",
        "aliases": ["电子皮肤", "阵列触觉"],
        "product_terms": ["触觉传感器", "电子皮肤", "触觉阵列"],
        "scene_terms": ["灵巧手", "机器人手指", "机器人末端"],
        "negative_examples": ["气体传感器"],
        "require_product_and_scene": True,
        "required_evidence_type_ids": [
            "business_presence",
            "product_or_prototype",
            "customer_validation",
            "order_or_delivery",
            "recognized_revenue",
        ],
        "next_validation_action": "核验阵列参数、装机和客户测试",
        "independent_discovery": False,
    },
    {
        "requirement_id": "dexterous_force_sensor",
        "business_keywords": ["力传感器"],
        "node_id": "dexterous_hand_foundation",
        "technology_route_id": "dexterous_tactile_sensing",
        "aliases": ["六维力传感器", "指尖力传感器"],
        "product_terms": ["力传感器", "六维力传感器", "指尖力传感器"],
        "scene_terms": ["灵巧手", "机器人手指", "机器人腕部"],
        "negative_examples": ["称重传感器"],
        "require_product_and_scene": True,
        "required_evidence_type_ids": [
            "business_presence",
            "product_or_prototype",
            "customer_validation",
            "order_or_delivery",
            "recognized_revenue",
        ],
        "next_validation_action": "核验量程精度、安装位置和客户验证",
        "independent_discovery": False,
    },
    {
        "requirement_id": "dexterous_tendon",
        "business_keywords": ["腱绳"],
        "node_id": "dexterous_hand_integration",
        "technology_route_id": "dexterous_tendon_drive",
        "aliases": ["腱驱动", "人工肌腱", "柔性腱绳"],
        "product_terms": ["腱绳", "人工肌腱", "柔性腱绳"],
        "scene_terms": ["灵巧手", "机器人手指", "腱驱动机器人"],
        "negative_examples": ["普通钢丝绳"],
        "require_product_and_scene": True,
        "required_evidence_type_ids": [
            "business_presence",
            "product_or_prototype",
            "customer_validation",
            "order_or_delivery",
            "recognized_revenue",
        ],
        "next_validation_action": "核验材料寿命、装机和交付",
        "independent_discovery": False,
    },
]

AXIAL_APPLICATION_DOMAINS = [
    "dexterous_hand",
    "robot_hand",
    "robot_joint",
    "robot_wrist",
]

EXPECTED_AXIAL_FACT_TYPES = {
    "AF0": [],
    "AF1": ["patent_standard", "prototype_delivery"],
    "AF2": ["product_spec"],
    "AF3": ["prototype_delivery"],
    "AF4": ["customer_validation"],
    "AF5": ["small_batch_delivery"],
    "AF6": ["order_award", "revenue_margin"],
}

EXPECTED_AXIAL_METADATA = {
    "AF0": [],
    "AF1": ["legal_status", "legal_status_date"],
    "AF2": ["application_domain"],
    "AF3": ["application_domain", "installation_position"],
    "AF4": ["application_domain"],
    "AF5": ["application_domain"],
    "AF6": ["application_domain", "revenue_confirmed"],
}

EXPECTED_AXIAL_MATCH_MODES = {
    "AF0": "none",
    "AF1": "any",
    "AF2": "any",
    "AF3": "any",
    "AF4": "any",
    "AF5": "any",
    "AF6": "all",
}


def _axial_route(template):
    return next(
        route
        for route in template["technology_routes"]
        if route["route_id"] == "dexterous_axial_flux_motor"
    )


def _ordered_union(values):
    result = []
    for value in values:
        if value not in result:
            result.append(value)
    return result


def _add_extra_canonical_keyword(template):
    template["evidence_requirements"][0]["business_keywords"].append("机器人夹爪")


def _replace_node_with_unknown_node(template):
    template["evidence_requirements"][0]["node_id"] = "dexterous_hand_unknown"


def _enable_second_independent_discovery(template):
    template["evidence_requirements"][0]["independent_discovery"] = True


def _replace_af6_rank_with_negative_value(template):
    _axial_route(template)["authenticity_ladder"]["AF6"]["rank"] = -1


def _replace_af2_fact_type_with_unknown_value(template):
    rule = _axial_route(template)["authenticity_ladder"]["AF2"]
    rule["required_fact_types"][0] = "unknown_route_fact"
    if rule.get("fact_requirements"):
        rule["fact_requirements"][0]["fact_type"] = "unknown_route_fact"


def _remove_automotive_policy(template):
    _axial_route(template).pop("application_domain_policy", None)


def _replace_first_requirement_with_string(template):
    template["evidence_requirements"][0] = "not-an-object"


def _drift_flattened_af1_metadata(template):
    _axial_route(template)["authenticity_ladder"]["AF1"]["required_metadata"] = []


def _replace_af4_pool_with_list(template):
    _axial_route(template)["authenticity_ladder"]["AF4"]["max_pool"] = ["B"]


def _replace_af1_match_mode_with_list(template):
    _axial_route(template)["authenticity_ladder"]["AF1"]["fact_match_mode"] = [
        "any"
    ]


def _replace_af1_match_mode_with_all(template):
    _axial_route(template)["authenticity_ladder"]["AF1"]["fact_match_mode"] = "all"


def _replace_af6_match_mode_with_any(template):
    _axial_route(template)["authenticity_ladder"]["AF6"]["fact_match_mode"] = "any"


def _raise_af1_pool_cap_to_c(template):
    _axial_route(template)["authenticity_ladder"]["AF1"]["max_pool"] = "C"


def _remove_patent_legal_status_date_everywhere(template):
    axial = _axial_route(template)
    axial["route_fact_contracts"]["patent_standard"]["required_metadata"].remove(
        "legal_status_date"
    )
    af1 = axial["authenticity_ladder"]["AF1"]
    af1["fact_requirements"][0]["required_metadata"].remove("legal_status_date")
    af1["required_metadata"].remove("legal_status_date")


def _replace_af1_prototype_with_product_spec(template):
    af1 = _axial_route(template)["authenticity_ladder"]["AF1"]
    af1["fact_requirements"][1]["fact_type"] = "product_spec"
    af1["required_fact_types"][1] = "product_spec"


def _replace_af6_order_with_small_batch_delivery(template):
    af6 = _axial_route(template)["authenticity_ladder"]["AF6"]
    af6["fact_requirements"][0]["fact_type"] = "small_batch_delivery"
    af6["required_fact_types"][0] = "small_batch_delivery"


def _shrink_af2_application_domains(template):
    af2 = _axial_route(template)["authenticity_ladder"]["AF2"]
    af2["fact_requirements"][0]["required_application_domains"] = ["robot_hand"]
    af2["required_application_domains"] = ["robot_hand"]


def test_selection_v2_profile_weights_and_pool_thresholds():
    profile = load_selection_v2_profile()

    validate_selection_v2_profile(profile)
    assert sum(profile["weights"]["node"].values()) == pytest.approx(1.0)
    assert sum(profile["weights"]["benefit"].values()) == pytest.approx(1.0)
    assert sum(profile["weights"]["opportunity"].values()) == pytest.approx(1.0)
    assert profile["pool_thresholds"]["A"]["min_evidence_level"] == "E4"
    assert profile["evidence_expiry_days"]["customer_sample"] == 180


def test_selection_v2_profile_rejects_weight_drift():
    profile = load_selection_v2_profile()
    profile["weights"]["node"]["demand_certainty"] = 0.21

    with pytest.raises(ValueError, match="weights.node must sum to 1.0"):
        validate_selection_v2_profile(profile)


def test_selection_v2_profile_rejects_negative_weight_even_when_sum_is_one():
    profile = load_selection_v2_profile()
    profile["weights"]["node"]["demand_certainty"] = -0.1
    profile["weights"]["node"]["value_pool_score"] = 0.45

    with pytest.raises(ValueError, match="weights.node values must be between 0 and 1"):
        validate_selection_v2_profile(profile)


def test_template_catalog_lookup_is_explicit():
    catalog = load_template_catalog()

    assert catalog["templates"]
    with pytest.raises(ValueError, match="unknown industry template"):
        get_industry_template("not-a-template")


def test_dexterous_hand_template_has_eight_layers_and_axial_flux_route():
    template = get_industry_template("dexterous_hand")

    assert [layer["layer_id"] for layer in template["layers"]] == EXPECTED_LAYERS
    axial = next(
        route
        for route in template["technology_routes"]
        if route["route_id"] == "dexterous_axial_flux_motor"
    )
    assert axial["node_id"] == "dexterous_hand_foundation"
    assert axial["authenticity_ladder"]["AF0"]["max_pool"] is None
    assert axial["authenticity_ladder"]["AF4"]["max_pool"] == "B"
    assert axial["authenticity_ladder"]["AF5"]["max_pool"] == "A"
    assert axial["performance_metrics"]["continuous_torque"] is None
    assert axial["performance_metrics"]["temperature_rise"] is None


def test_dexterous_hand_candidate_rules_never_claim_verified_supply():
    template = get_industry_template("dexterous_hand")
    rules = template["candidate_mapping_rules"]

    assert rules["derived_status"] == "candidate"
    assert rules["derived_confidence_cap"] == 0.35
    assert rules["requires_original_evidence"] is True


def test_dexterous_candidate_keywords_have_one_requirement_each():
    template = get_industry_template("dexterous_hand")
    validate_industry_evidence_coverage(template, load_evidence_requirements())

    keywords = template["candidate_mapping_rules"]["required_business_keywords"]
    matches = [get_business_evidence_requirement(template, keyword) for keyword in keywords]
    assert all(matches)
    assert len(matches) == len(keywords)


def test_dexterous_evidence_requirements_match_the_audited_search_contract():
    template = get_industry_template("dexterous_hand")

    assert template["evidence_requirements"] == EXPECTED_DEXTEROUS_EVIDENCE_REQUIREMENTS
    assert [
        row["requirement_id"]
        for row in template["evidence_requirements"]
        if row["independent_discovery"]
    ] == ["dexterous_axial_flux_motor"]


def test_aliases_expand_search_but_do_not_count_as_business_facts():
    template = get_industry_template("dexterous_hand")

    with pytest.raises(ValueError, match="business keyword must resolve once"):
        get_business_evidence_requirement(template, "机器人手")


def test_axial_flux_ladder_is_monotonic_and_rejects_automotive_only():
    template = get_industry_template("dexterous_hand")
    axial = next(
        route
        for route in template["technology_routes"]
        if route["route_id"] == "dexterous_axial_flux_motor"
    )
    ladder = axial["authenticity_ladder"]

    assert list(ladder) == [f"AF{i}" for i in range(7)]
    assert [ladder[f"AF{i}"]["rank"] for i in range(7)] == list(range(7))
    assert [ladder[f"AF{i}"]["max_pool"] for i in range(7)] == [
        None,
        "D",
        "C",
        "C",
        "B",
        "A",
        "A",
    ]
    assert [ladder[f"AF{i}"]["eligible"] for i in range(7)] == [
        False,
        True,
        True,
        True,
        True,
        True,
        True,
    ]
    assert axial["excluded_application_domains"] == ["automotive"]
    requirement = get_business_evidence_requirement(template, "轴向磁通电机")
    assert requirement["independent_discovery"] is True


def test_axial_flux_ladder_has_explicit_fact_domain_and_metadata_contracts():
    template = get_industry_template("dexterous_hand")
    axial = next(
        route
        for route in template["technology_routes"]
        if route["route_id"] == "dexterous_axial_flux_motor"
    )

    for index in range(7):
        stage = f"AF{index}"
        rule = axial["authenticity_ladder"][stage]
        assert set(rule) == {
            "meaning",
            "rank",
            "max_pool",
            "eligible",
            "required_fact_types",
            "required_application_domains",
            "required_metadata",
            "fact_match_mode",
            "fact_requirements",
        }
        assert rule["required_fact_types"] == EXPECTED_AXIAL_FACT_TYPES[stage]
        assert rule["required_metadata"] == EXPECTED_AXIAL_METADATA[stage]
        assert rule["required_application_domains"] == (
            AXIAL_APPLICATION_DOMAINS if index >= 2 else []
        )


def test_axial_flux_predicates_encode_any_all_and_local_fact_contracts():
    template = get_industry_template("dexterous_hand")
    axial = _axial_route(template)
    ladder = axial["authenticity_ladder"]

    assert axial["flattened_requirements_projection"] == (
        "ordered_union_of_fact_requirements"
    )
    assert axial["route_fact_contracts"] == {
        "patent_standard": {
            "required_metadata": ["legal_status", "legal_status_date"],
            "metadata_value_constraints": {
                "legal_status": ["active", "granted"],
            },
        }
    }
    assert axial["application_domain_policy"] == {
        "evaluation_scope": "fact",
        "excluded_fact_handling": "cannot_satisfy_fact_requirement",
        "excluded_only_result": "no_stage_promotion",
        "allow_qualified_non_excluded_facts": True,
    }

    for stage, expected_mode in EXPECTED_AXIAL_MATCH_MODES.items():
        rule = ladder[stage]
        requirements = rule["fact_requirements"]
        assert rule["fact_match_mode"] == expected_mode
        assert rule["required_fact_types"] == _ordered_union(
            requirement["fact_type"] for requirement in requirements
        )
        assert rule["required_application_domains"] == _ordered_union(
            domain
            for requirement in requirements
            for domain in requirement["required_application_domains"]
        )
        assert rule["required_metadata"] == _ordered_union(
            metadata
            for requirement in requirements
            for metadata in requirement["required_metadata"]
        )

    af1 = ladder["AF1"]["fact_requirements"]
    assert [requirement["fact_type"] for requirement in af1] == [
        "patent_standard",
        "prototype_delivery",
    ]
    patent = af1[0]
    assert patent["required_metadata"] == ["legal_status", "legal_status_date"]
    assert patent["metadata_value_constraints"] == {
        "legal_status": ["active", "granted"]
    }

    for index in range(2, 7):
        assert all(
            requirement["required_application_domains"]
            == AXIAL_APPLICATION_DOMAINS
            for requirement in ladder[f"AF{index}"]["fact_requirements"]
        )

    af6 = ladder["AF6"]["fact_requirements"]
    assert [requirement["fact_type"] for requirement in af6] == [
        "order_award",
        "revenue_margin",
    ]
    assert "revenue_confirmed" not in af6[0]["required_metadata"]
    assert af6[1]["required_metadata"] == [
        "application_domain",
        "revenue_confirmed",
    ]
    assert af6[1]["metadata_value_constraints"] == {"revenue_confirmed": [True]}


@pytest.mark.parametrize(
    ("mutate", "expected_path"),
    [
        (
            _add_extra_canonical_keyword,
            "template.evidence_requirements.business_keywords",
        ),
        (
            _replace_node_with_unknown_node,
            "template.evidence_requirements[0].node_id",
        ),
        (
            _enable_second_independent_discovery,
            "template.evidence_requirements[0].independent_discovery",
        ),
        (
            _replace_af6_rank_with_negative_value,
            "template.technology_routes[2].authenticity_ladder.AF6.rank",
        ),
        (
            _replace_af2_fact_type_with_unknown_value,
            "template.technology_routes[2].authenticity_ladder.AF2.fact_requirements[0].fact_type",
        ),
        (
            _remove_automotive_policy,
            "template.technology_routes[2].application_domain_policy",
        ),
        (
            _replace_first_requirement_with_string,
            "template.evidence_requirements[0]",
        ),
        (
            _drift_flattened_af1_metadata,
            "template.technology_routes[2].authenticity_ladder.AF1.required_metadata",
        ),
        (
            _replace_af4_pool_with_list,
            "template.technology_routes[2].authenticity_ladder.AF4.max_pool",
        ),
        (
            _replace_af1_match_mode_with_list,
            "template.technology_routes[2].authenticity_ladder.AF1.fact_match_mode",
        ),
        (
            _replace_af1_match_mode_with_all,
            "template.technology_routes[2].authenticity_ladder.AF1.fact_match_mode",
        ),
        (
            _replace_af6_match_mode_with_any,
            "template.technology_routes[2].authenticity_ladder.AF6.fact_match_mode",
        ),
        (
            _raise_af1_pool_cap_to_c,
            "template.technology_routes[2].authenticity_ladder.AF1.max_pool",
        ),
        (
            _remove_patent_legal_status_date_everywhere,
            "template.technology_routes[2].route_fact_contracts.patent_standard.required_metadata",
        ),
        (
            _replace_af1_prototype_with_product_spec,
            "template.technology_routes[2].authenticity_ladder.AF1.fact_requirements[1].fact_type",
        ),
        (
            _replace_af6_order_with_small_batch_delivery,
            "template.technology_routes[2].authenticity_ladder.AF6.fact_requirements[0].fact_type",
        ),
        (
            _shrink_af2_application_domains,
            "template.technology_routes[2].authenticity_ladder.AF2.fact_requirements[0].required_application_domains",
        ),
    ],
    ids=[
        "extra-canonical-keyword",
        "unknown-node",
        "second-independent-discovery",
        "negative-af6-rank",
        "unknown-route-fact-type",
        "missing-automotive-policy",
        "bad-requirement-row-type",
        "flattened-predicate-drift",
        "bad-pool-type",
        "bad-match-mode-type",
        "af1-must-remain-any",
        "af6-must-remain-all",
        "af1-pool-cap-must-remain-d",
        "patent-contract-requires-legal-status-date",
        "af1-prototype-branch-must-not-change",
        "af6-order-branch-must-not-change",
        "af2-requires-all-robot-domains",
    ],
)
def test_industry_evidence_validation_rejects_review_mutations(
    mutate,
    expected_path,
):
    template = deepcopy(get_industry_template("dexterous_hand"))
    mutate(template)

    with pytest.raises(ValueError) as error:
        validate_industry_evidence_coverage(template, load_evidence_requirements())

    assert expected_path in str(error.value)


def test_business_evidence_requirement_is_deeply_isolated_from_template():
    template = get_industry_template("dexterous_hand")
    requirement = get_business_evidence_requirement(template, "轴向磁通电机")

    requirement["product_terms"].append("仅修改返回值")
    requirement["required_evidence_type_ids"].clear()

    original = get_business_evidence_requirement(template, "轴向磁通电机")
    assert "仅修改返回值" not in original["product_terms"]
    assert original["required_evidence_type_ids"]


def test_template_tree_exposes_v2_overlay_without_removing_legacy_fields():
    template = get_industry_template("dexterous_hand")

    tree = build_industry_template_tree(template)
    foundation = next(
        child for child in tree["children"] if child["layer_id"] == "foundation"
    )
    assert foundation["segments"]
    assert "evidence_chain" in foundation
    assert "research_dimensions" in foundation
    assert tree["technology_routes"]
    assert tree["transmission_edges"]
