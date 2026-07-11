"""Load and validate industry-chain templates and selection profiles."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


TEMPLATE_CONFIG_NAME = "industry_chain_templates.json"
SELECTION_V2_CONFIG_NAME = "industry_chain_selection_v2.json"

EXPECTED_DIMENSIONS = [
    "function_value",
    "technology_route",
    "physical_bom",
    "value_pool",
    "competition_moat",
    "supply_demand_cycle",
    "evidence_validation",
    "market_expectation",
]

EXPECTED_FLOW_TYPES = [
    "product_flow",
    "value_flow",
    "technology_flow",
    "data_flow",
]

WEIGHT_GROUPS = (
    "node",
    "authenticity",
    "growth",
    "profit",
    "moat",
    "operating",
    "benefit",
    "opportunity",
)


def _config_candidates(filename: str) -> list[Path]:
    package_root = Path(__file__).resolve().parents[2]
    in_package_root = Path(__file__).resolve().parents[1]
    return [
        package_root / "configs" / filename,
        in_package_root / "configs" / filename,
    ]


def _resolve_config_path(filename: str, path: str | Path | None) -> Path:
    candidates = [Path(path)] if path else _config_candidates(filename)
    return next((candidate for candidate in candidates if candidate.exists()), candidates[0])


def load_template_catalog(path: str | Path | None = None) -> dict[str, Any]:
    target = _resolve_config_path(TEMPLATE_CONFIG_NAME, path)
    data = json.loads(target.read_text(encoding="utf-8"))
    data.setdefault("templates", [])
    return data


def get_industry_template(
    template_id: str,
    *,
    path: str | Path | None = None,
) -> dict[str, Any]:
    for template in load_template_catalog(path).get("templates", []):
        if str(template.get("template_id") or "") == template_id:
            return template
    raise ValueError(f"unknown industry template: {template_id}")


def validate_industry_evidence_coverage(template, requirements) -> None:
    rows = list(template.get("evidence_requirements") or [])
    ids = [str(row.get("requirement_id") or "") for row in rows]
    if not rows or any(not item for item in ids) or len(ids) != len(set(ids)):
        raise ValueError("industry evidence requirement ids must be non-empty and unique")
    known_types = set(requirements.evidence_types)
    route_ids = {
        str(route.get("route_id")) for route in template.get("technology_routes") or []
    }
    keyword_matches: dict[str, int] = {}
    for row in rows:
        if not set(row.get("required_evidence_type_ids") or []).issubset(known_types):
            raise ValueError(f"unknown evidence type in {row['requirement_id']}")
        if not row.get("product_terms"):
            raise ValueError(f"missing product terms in {row['requirement_id']}")
        if row.get("require_product_and_scene") and not row.get("scene_terms"):
            raise ValueError(f"missing scene terms in {row['requirement_id']}")
        if not row.get("next_validation_action"):
            raise ValueError(f"missing next action in {row['requirement_id']}")
        route_id = row.get("technology_route_id")
        if route_id and route_id not in route_ids:
            raise ValueError(f"unknown technology route: {route_id}")
        for keyword in row.get("business_keywords") or []:
            keyword_matches[str(keyword)] = keyword_matches.get(str(keyword), 0) + 1
    expected = template.get("candidate_mapping_rules", {}).get(
        "required_business_keywords", []
    )
    invalid = [
        keyword for keyword in expected if keyword_matches.get(str(keyword), 0) != 1
    ]
    if invalid:
        raise ValueError(
            "candidate keywords require exactly one evidence coverage: "
            + ", ".join(invalid)
        )


def get_business_evidence_requirement(template, keyword: str) -> dict:
    matches = [
        dict(row)
        for row in template.get("evidence_requirements") or []
        if keyword in (row.get("business_keywords") or [])
    ]
    if len(matches) != 1:
        raise ValueError(f"business keyword must resolve once: {keyword}")
    return matches[0]


def load_selection_v2_profile(path: str | Path | None = None) -> dict[str, Any]:
    target = _resolve_config_path(SELECTION_V2_CONFIG_NAME, path)
    return json.loads(target.read_text(encoding="utf-8"))


def validate_selection_v2_profile(profile: dict[str, Any]) -> None:
    if profile.get("dimensions") != EXPECTED_DIMENSIONS:
        raise ValueError("selection v2 dimensions are invalid")
    if profile.get("flow_types") != EXPECTED_FLOW_TYPES:
        raise ValueError("selection v2 flow types are invalid")

    weights = profile.get("weights") or {}
    for group in WEIGHT_GROUPS:
        configured = weights.get(group)
        if not isinstance(configured, dict) or not configured:
            raise ValueError(f"weights.{group} must be a non-empty object")
        numeric_values = [float(value) for value in configured.values()]
        if any(value < 0 or value > 1 for value in numeric_values):
            raise ValueError(f"weights.{group} values must be between 0 and 1")
        total = sum(numeric_values)
        if abs(total - 1.0) > 1e-9:
            raise ValueError(f"weights.{group} must sum to 1.0, got {total}")

    risk_penalty = weights.get("risk_penalty")
    if risk_penalty is None or not 0 <= float(risk_penalty) <= 1:
        raise ValueError("weights.risk_penalty must be between 0 and 1")

    thresholds = profile.get("pool_thresholds") or {}
    if tuple(thresholds) != ("A", "B", "C", "D"):
        raise ValueError("pool_thresholds must define A, B, C and D in order")
