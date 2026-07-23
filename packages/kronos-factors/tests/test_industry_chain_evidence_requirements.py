import json
import re
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


UNEXPECTED_EVIDENCE_TYPE = {
    "level": "E1",
    "fact_types": ["unexpected_fact"],
    "metadata_flags": [],
    "minimum_source_level": "mid",
    "allowed_fact_natures": ["confirmed_fact"],
    "score_fields": [],
    "expiry_policy": None,
    "search_terms": [],
    "default_next_action": "unexpected",
}

CONTRACT_DRIFT_CASES = [
    ("version", "delete", None),
    ("unexpected", "set", True),
    ("version", "set", 1),
    ("source_level_rank.weak", "set", 99),
    ("evidence_levels.E0.rank", "set", False),
    ("evidence_levels.E0.eligible", "set", 0),
    ("evidence_levels.E1.max_pool", "set", "A"),
    ("evidence_levels.E2.meaning", "set", "customer_validation"),
    ("freshness_policies.customer_sample", "delete", None),
    ("freshness_policies.interactive_answer", "set", 1),
    ("freshness_policies.customer_test", "set", True),
    ("evidence_types.business_presence", "delete", None),
    ("evidence_types.unexpected", "set", UNEXPECTED_EVIDENCE_TYPE),
    ("evidence_types.business_presence.allowed_fact_natures", "delete", None),
    ("evidence_types.business_presence.score_fields", "set", "unexpected"),
    ("evidence_types.recognized_revenue.metadata_flags", "set", ["profit_confirmed"]),
]


def _mutate_path(data, path, operation, value):
    parts = path.split(".")
    target = data
    for part in parts[:-1]:
        target = target[part]
    if operation == "delete":
        del target[parts[-1]]
    else:
        target[parts[-1]] = deepcopy(value)


@pytest.mark.parametrize(
    ("path", "operation", "value"),
    CONTRACT_DRIFT_CASES,
    ids=[f"{operation}-{path}" for path, operation, _ in CONTRACT_DRIFT_CASES],
)
def test_catalog_rejects_contract_drift_with_field_path(path, operation, value):
    broken = deepcopy(load_evidence_requirements().raw)
    _mutate_path(broken, path, operation, value)

    with pytest.raises(ValueError, match=re.escape(path)):
        validate_evidence_requirements(broken)


@pytest.mark.parametrize(
    "field",
    [
        "level",
        "fact_types",
        "metadata_flags",
        "minimum_source_level",
        "allowed_fact_natures",
        "score_fields",
        "expiry_policy",
        "search_terms",
        "default_next_action",
    ],
)
def test_catalog_requires_every_evidence_type_rule_field(field):
    broken = deepcopy(load_evidence_requirements().raw)
    path = f"evidence_types.business_presence.{field}"
    _mutate_path(broken, path, "delete", None)

    with pytest.raises(ValueError, match=re.escape(path)):
        validate_evidence_requirements(broken)


def test_loader_reports_missing_contract_field_as_value_error(tmp_path):
    broken = deepcopy(load_evidence_requirements().raw)
    del broken["version"]
    path = tmp_path / "broken-evidence-requirements.json"
    path.write_text(json.dumps(broken, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ValueError, match="version"):
        load_evidence_requirements(path)


def test_catalog_fields_and_raw_are_deeply_isolated():
    catalog = load_evidence_requirements()

    catalog.evidence_levels["E1"]["max_pool"] = "A"
    assert catalog.raw["evidence_levels"]["E1"]["max_pool"] == "D"

    catalog.raw["evidence_types"]["business_presence"]["fact_types"].append("mutated")
    assert catalog.evidence_types["business_presence"]["fact_types"] == ["business_presence"]
