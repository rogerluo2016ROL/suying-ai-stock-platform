from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

EVIDENCE_REQUIREMENTS_CONFIG_NAME = "industry_chain_evidence_requirements.json"
EXPECTED_LEVELS = tuple(f"E{i}" for i in range(7))
EXPECTED_SOURCE_LEVEL_RANK = {"weak": 1, "mid": 2, "strong": 3}
EXPECTED_EVIDENCE_LEVELS = {
    "E0": {"rank": 0, "meaning": "untraceable_signal", "max_pool": None, "eligible": False},
    "E1": {"rank": 1, "meaning": "business_presence", "max_pool": "D", "eligible": True},
    "E2": {"rank": 2, "meaning": "product_or_prototype", "max_pool": "C", "eligible": True},
    "E3": {"rank": 3, "meaning": "customer_validation", "max_pool": "B", "eligible": True},
    "E4": {"rank": 4, "meaning": "order_or_delivery", "max_pool": "A", "eligible": True},
    "E5": {"rank": 5, "meaning": "recognized_revenue", "max_pool": "A", "eligible": True},
    "E6": {"rank": 6, "meaning": "recognized_profit", "max_pool": "A", "eligible": True},
}
EXPECTED_EVIDENCE_TYPES = {
    "business_presence": {
        "level": "E1",
        "fact_types": ["business_presence"],
        "metadata_flags": [],
        "minimum_source_level": "mid",
        "allowed_fact_natures": ["confirmed_fact", "company_claim"],
        "score_fields": [],
        "expiry_policy": None,
        "search_terms": [],
        "default_next_action": "核验相关产品或样机",
    },
    "product_or_prototype": {
        "level": "E2",
        "fact_types": ["product_spec", "prototype_delivery"],
        "metadata_flags": [],
        "minimum_source_level": "mid",
        "allowed_fact_natures": ["confirmed_fact", "company_claim"],
        "score_fields": ["product_evidence_score"],
        "expiry_policy": None,
        "search_terms": ["产品", "样机", "样品", "规格"],
        "default_next_action": "核验客户送样或测试",
    },
    "customer_validation": {
        "level": "E3",
        "fact_types": ["customer_validation"],
        "metadata_flags": [],
        "minimum_source_level": "mid",
        "allowed_fact_natures": ["confirmed_fact", "company_claim"],
        "score_fields": ["customer_evidence_score"],
        "expiry_policy": "customer_test",
        "search_terms": ["送样", "验证", "测试", "定点"],
        "default_next_action": "核验订单或交付",
    },
    "order_or_delivery": {
        "level": "E4",
        "fact_types": ["order_award", "small_batch_delivery"],
        "metadata_flags": [],
        "minimum_source_level": "strong",
        "allowed_fact_natures": ["confirmed_fact"],
        "score_fields": ["order_revenue_evidence_score", "order_certainty_score"],
        "expiry_policy": None,
        "search_terms": ["订单", "中标", "合同", "交付"],
        "default_next_action": "核验收入确认",
    },
    "recognized_revenue": {
        "level": "E5",
        "fact_types": ["revenue_margin"],
        "metadata_flags": ["revenue_confirmed"],
        "minimum_source_level": "strong",
        "allowed_fact_natures": ["confirmed_fact"],
        "score_fields": ["revenue_exposure_score"],
        "expiry_policy": "financial_revenue",
        "search_terms": ["相关收入", "营业收入", "收入占比"],
        "default_next_action": "核验相关利润",
    },
    "recognized_profit": {
        "level": "E6",
        "fact_types": ["revenue_margin"],
        "metadata_flags": ["profit_confirmed"],
        "minimum_source_level": "strong",
        "allowed_fact_natures": ["confirmed_fact"],
        "score_fields": ["profit_elasticity_score"],
        "expiry_policy": "financial_revenue",
        "search_terms": ["毛利", "利润贡献", "分部利润"],
        "default_next_action": "复核利润持续性",
    },
}
EXPECTED_FRESHNESS_POLICIES = {
    "interactive_answer": 90,
    "customer_sample": 180,
    "customer_test": 180,
    "nomination": 365,
    "financial_revenue": 180,
}
EXPECTED_CATALOG = {
    "version": "v1.0",
    "source_level_rank": EXPECTED_SOURCE_LEVEL_RANK,
    "evidence_levels": EXPECTED_EVIDENCE_LEVELS,
    "evidence_types": EXPECTED_EVIDENCE_TYPES,
    "freshness_policies": EXPECTED_FRESHNESS_POLICIES,
}


@dataclass(frozen=True)
class EvidenceRequirementCatalog:
    version: str
    source_level_rank: dict[str, int]
    evidence_levels: dict[str, dict[str, Any]]
    evidence_types: dict[str, dict[str, Any]]
    freshness_policies: dict[str, int]
    raw: dict[str, Any]


def _config_path(path: str | Path | None) -> Path:
    if path is not None:
        return Path(path)
    return Path(__file__).resolve().parents[2] / "configs" / EVIDENCE_REQUIREMENTS_CONFIG_NAME


def _catalog(data: Mapping[str, Any]) -> EvidenceRequirementCatalog:
    raw = deepcopy(dict(data))
    return EvidenceRequirementCatalog(
        version=raw["version"],
        source_level_rank=deepcopy(raw["source_level_rank"]),
        evidence_levels=deepcopy(raw["evidence_levels"]),
        evidence_types=deepcopy(raw["evidence_types"]),
        freshness_policies=deepcopy(raw["freshness_policies"]),
        raw=raw,
    )


def load_evidence_requirements(path: str | Path | None = None) -> EvidenceRequirementCatalog:
    data = json.loads(_config_path(path).read_text(encoding="utf-8"))
    validate_evidence_requirements(data)
    return _catalog(data)


def _field_path(parent: str, child: object) -> str:
    return f"{parent}.{child}" if parent else str(child)


def _validate_exact_mapping(
    actual: Mapping[object, Any],
    expected: Mapping[object, Any],
    *,
    path: str,
) -> None:
    for key in expected:
        if key not in actual:
            missing_path = _field_path(path, key)
            raise ValueError(f"{missing_path}: missing field")
    for key in actual:
        if key not in expected:
            extra_path = _field_path(path, key)
            raise ValueError(f"{extra_path}: unexpected field")
    for key, expected_value in expected.items():
        field_path = _field_path(path, key)
        _validate_exact_value(actual[key], expected_value, path=field_path)


def _validate_exact_value(actual: Any, expected: Any, *, path: str) -> None:
    if isinstance(expected, Mapping):
        if not isinstance(actual, Mapping):
            raise ValueError(f"{path}: expected object, got {type(actual).__name__}")
        _validate_exact_mapping(actual, expected, path=path)
        return
    if isinstance(expected, list):
        if type(actual) is not list:
            raise ValueError(f"{path}: expected list, got {type(actual).__name__}")
        if len(actual) != len(expected):
            raise ValueError(f"{path}: expected {len(expected)} items, got {len(actual)}")
        for index, (actual_item, expected_item) in enumerate(zip(actual, expected)):
            _validate_exact_value(actual_item, expected_item, path=f"{path}[{index}]")
        return
    if type(actual) is not type(expected):
        raise ValueError(
            f"{path}: expected {type(expected).__name__}, got {type(actual).__name__}"
        )
    if actual != expected:
        raise ValueError(f"{path}: expected {expected!r}, got {actual!r}")


def validate_evidence_requirements(
    requirements: Mapping[str, Any] | EvidenceRequirementCatalog,
    *,
    selection_profile: Mapping[str, Any] | None = None,
) -> None:
    data = requirements.raw if isinstance(requirements, EvidenceRequirementCatalog) else requirements
    if not isinstance(data, Mapping):
        raise ValueError(f"catalog: expected object, got {type(data).__name__}")
    _validate_exact_mapping(data, EXPECTED_CATALOG, path="")
    levels = data["evidence_levels"]
    if tuple(levels) != EXPECTED_LEVELS:
        raise ValueError("evidence_levels: must define E0 through E6 in order")
    if selection_profile:
        for pool, threshold in selection_profile["pool_thresholds"].items():
            if threshold["min_evidence_level"] not in levels:
                raise ValueError(f"pool_thresholds.{pool}.min_evidence_level is unknown")


def get_evidence_level_rule(
    level: str,
    *,
    requirements: EvidenceRequirementCatalog | None = None,
    path: str | Path | None = None,
) -> dict[str, Any]:
    catalog = requirements or load_evidence_requirements(path)
    if level not in catalog.evidence_levels:
        raise ValueError(f"unknown evidence level: {level}")
    rule = dict(catalog.evidence_levels[level])
    matching = [item for item in catalog.evidence_types.values() if item["level"] == level]
    if matching:
        rule["minimum_source_level"] = matching[0]["minimum_source_level"]
        rule["allowed_fact_natures"] = list(matching[0]["allowed_fact_natures"])
    return rule
