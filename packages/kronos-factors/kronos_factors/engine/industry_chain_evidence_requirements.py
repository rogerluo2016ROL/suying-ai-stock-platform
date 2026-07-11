from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

EVIDENCE_REQUIREMENTS_CONFIG_NAME = "industry_chain_evidence_requirements.json"
EXPECTED_LEVELS = tuple(f"E{i}" for i in range(7))
ALLOWED_POOLS = {None, "A", "B", "C", "D"}
ALLOWED_SOURCE_LEVELS = {"weak", "mid", "strong"}


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
    raw = dict(data)
    return EvidenceRequirementCatalog(
        version=str(raw["version"]),
        source_level_rank=dict(raw["source_level_rank"]),
        evidence_levels=dict(raw["evidence_levels"]),
        evidence_types=dict(raw["evidence_types"]),
        freshness_policies=dict(raw["freshness_policies"]),
        raw=raw,
    )


def load_evidence_requirements(path: str | Path | None = None) -> EvidenceRequirementCatalog:
    result = _catalog(json.loads(_config_path(path).read_text(encoding="utf-8")))
    validate_evidence_requirements(result)
    return result


def validate_evidence_requirements(
    requirements: Mapping[str, Any] | EvidenceRequirementCatalog,
    *,
    selection_profile: Mapping[str, Any] | None = None,
) -> None:
    data = requirements.raw if isinstance(requirements, EvidenceRequirementCatalog) else dict(requirements)
    levels = data.get("evidence_levels") or {}
    if tuple(levels) != EXPECTED_LEVELS:
        raise ValueError("evidence_levels must define E0 through E6 in order")
    for rank, level in enumerate(EXPECTED_LEVELS):
        rule = levels[level]
        if int(rule.get("rank", -1)) != rank:
            raise ValueError(f"evidence_levels.{level}.rank must be {rank}")
        if rule.get("max_pool") not in ALLOWED_POOLS:
            raise ValueError(f"evidence_levels.{level}.max_pool is invalid")
    for name, days in (data.get("freshness_policies") or {}).items():
        if not isinstance(days, int) or days <= 0:
            raise ValueError(f"freshness_policies.{name} must be a positive integer")
    seen_fact_signatures: set[tuple[str, tuple[str, ...]]] = set()
    for type_id, rule in (data.get("evidence_types") or {}).items():
        if rule.get("level") not in levels:
            raise ValueError(f"evidence_types.{type_id}.level is invalid")
        if rule.get("minimum_source_level") not in ALLOWED_SOURCE_LEVELS:
            raise ValueError(f"evidence_types.{type_id}.minimum_source_level is invalid")
        policy = rule.get("expiry_policy")
        if policy is not None and policy not in data.get("freshness_policies", {}):
            raise ValueError(f"evidence_types.{type_id}.expiry_policy is invalid")
        fact_types = [str(item) for item in rule.get("fact_types") or []]
        flags = tuple(sorted(str(item) for item in rule.get("metadata_flags") or []))
        signatures = {(fact_type, flags) for fact_type in fact_types}
        duplicates = seen_fact_signatures.intersection(signatures)
        if duplicates:
            raise ValueError(f"fact signatures must map once: {sorted(duplicates)}")
        seen_fact_signatures.update(signatures)
        score_fields = rule.get("score_fields") or []
        if any(not isinstance(item, str) or not item for item in score_fields):
            raise ValueError(f"evidence_types.{type_id}.score_fields is invalid")
    for level in ("E4", "E5", "E6"):
        rules = [item for item in data["evidence_types"].values() if item["level"] == level]
        if not rules or any(
            item["minimum_source_level"] != "strong"
            or item["allowed_fact_natures"] != ["confirmed_fact"]
            for item in rules
        ):
            raise ValueError(f"{level} requires strong confirmed facts")
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
