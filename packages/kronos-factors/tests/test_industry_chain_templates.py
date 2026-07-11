"""Contracts for V2 research profile and dexterous-hand template."""

import pytest

from kronos_factors.engine.chain_deconstruct import build_industry_template_tree
from kronos_factors.engine.industry_chain_templates import (
    get_industry_template,
    load_selection_v2_profile,
    load_template_catalog,
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
