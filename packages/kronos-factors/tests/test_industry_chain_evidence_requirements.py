from copy import deepcopy

import pytest

from kronos_factors.engine.industry_chain_evidence_requirements import (
    get_evidence_level_rule,
    load_evidence_requirements,
    validate_evidence_requirements,
)


def test_catalog_defines_monotonic_e0_to_e6_and_pool_caps():
    catalog = load_evidence_requirements()
    validate_evidence_requirements(catalog)

    assert list(catalog.evidence_levels) == [f"E{i}" for i in range(7)]
    assert [catalog.evidence_levels[f"E{i}"]["rank"] for i in range(7)] == list(range(7))
    assert [catalog.evidence_levels[f"E{i}"]["max_pool"] for i in range(7)] == [
        None, "D", "C", "B", "A", "A", "A"
    ]


def test_e4_to_e6_require_strong_confirmed_facts():
    catalog = load_evidence_requirements()

    for level in ("E4", "E5", "E6"):
        rule = get_evidence_level_rule(level, requirements=catalog)
        assert rule["minimum_source_level"] == "strong"
        assert rule["allowed_fact_natures"] == ["confirmed_fact"]


def test_catalog_rejects_non_positive_expiry_days():
    catalog = load_evidence_requirements()
    broken = deepcopy(catalog.raw)
    broken["freshness_policies"]["customer_sample"] = 0

    with pytest.raises(ValueError, match="freshness_policies.customer_sample"):
        validate_evidence_requirements(broken)
