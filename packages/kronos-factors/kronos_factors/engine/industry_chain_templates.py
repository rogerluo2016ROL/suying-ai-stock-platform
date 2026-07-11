"""Load and validate industry-chain templates and selection profiles."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from copy import deepcopy
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

AF_LEVELS = tuple(f"AF{i}" for i in range(7))
AF_POOL_ORDER = {None: 0, "D": 1, "C": 2, "B": 3, "A": 4}
DEXTEROUS_PATENT_CONTRACT = {
    "required_metadata": ["legal_status", "legal_status_date"],
    "metadata_value_constraints": {"legal_status": ["active", "granted"]},
}
DEXTEROUS_ROBOT_APPLICATION_DOMAINS = [
    "dexterous_hand",
    "robot_hand",
    "robot_joint",
    "robot_wrist",
]
DEXTEROUS_AXIAL_STAGE_CONTRACTS = {
    "AF0": {
        "max_pool": None,
        "eligible": False,
        "fact_match_mode": "none",
        "fact_requirements": [],
    },
    "AF1": {
        "max_pool": "D",
        "eligible": True,
        "fact_match_mode": "any",
        "fact_requirements": [
            {
                "fact_type": "patent_standard",
                "required_application_domains": [],
                "required_metadata": ["legal_status", "legal_status_date"],
                "metadata_value_constraints": {
                    "legal_status": ["active", "granted"]
                },
            },
            {
                "fact_type": "prototype_delivery",
                "required_application_domains": [],
                "required_metadata": [],
                "metadata_value_constraints": {},
            },
        ],
    },
    "AF2": {
        "max_pool": "C",
        "eligible": True,
        "fact_match_mode": "any",
        "fact_requirements": [
            {
                "fact_type": "product_spec",
                "required_application_domains": DEXTEROUS_ROBOT_APPLICATION_DOMAINS,
                "required_metadata": ["application_domain"],
                "metadata_value_constraints": {},
            }
        ],
    },
    "AF3": {
        "max_pool": "C",
        "eligible": True,
        "fact_match_mode": "any",
        "fact_requirements": [
            {
                "fact_type": "prototype_delivery",
                "required_application_domains": DEXTEROUS_ROBOT_APPLICATION_DOMAINS,
                "required_metadata": ["application_domain", "installation_position"],
                "metadata_value_constraints": {},
            }
        ],
    },
    "AF4": {
        "max_pool": "B",
        "eligible": True,
        "fact_match_mode": "any",
        "fact_requirements": [
            {
                "fact_type": "customer_validation",
                "required_application_domains": DEXTEROUS_ROBOT_APPLICATION_DOMAINS,
                "required_metadata": ["application_domain"],
                "metadata_value_constraints": {},
            }
        ],
    },
    "AF5": {
        "max_pool": "A",
        "eligible": True,
        "fact_match_mode": "any",
        "fact_requirements": [
            {
                "fact_type": "small_batch_delivery",
                "required_application_domains": DEXTEROUS_ROBOT_APPLICATION_DOMAINS,
                "required_metadata": ["application_domain"],
                "metadata_value_constraints": {},
            }
        ],
    },
    "AF6": {
        "max_pool": "A",
        "eligible": True,
        "fact_match_mode": "all",
        "fact_requirements": [
            {
                "fact_type": "order_award",
                "required_application_domains": DEXTEROUS_ROBOT_APPLICATION_DOMAINS,
                "required_metadata": ["application_domain"],
                "metadata_value_constraints": {},
            },
            {
                "fact_type": "revenue_margin",
                "required_application_domains": DEXTEROUS_ROBOT_APPLICATION_DOMAINS,
                "required_metadata": ["application_domain", "revenue_confirmed"],
                "metadata_value_constraints": {"revenue_confirmed": [True]},
            },
        ],
    },
}
AF_RULE_FIELDS = {
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
FACT_REQUIREMENT_FIELDS = {
    "fact_type",
    "required_application_domains",
    "required_metadata",
    "metadata_value_constraints",
}
ROUTE_FACT_CONTRACT_FIELDS = {
    "required_metadata",
    "metadata_value_constraints",
}
APPLICATION_DOMAIN_POLICY = {
    "evaluation_scope": "fact",
    "excluded_fact_handling": "cannot_satisfy_fact_requirement",
    "excluded_only_result": "no_stage_promotion",
    "allow_qualified_non_excluded_facts": True,
}


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


def _validation_error(path: str, message: str) -> None:
    raise ValueError(f"{path}: {message}")


def _require_mapping(value: Any, path: str) -> Mapping[Any, Any]:
    if not isinstance(value, Mapping):
        _validation_error(path, f"expected object, got {type(value).__name__}")
    return value


def _require_list(value: Any, path: str) -> list[Any]:
    if type(value) is not list:
        _validation_error(path, f"expected list, got {type(value).__name__}")
    return value


def _require_non_empty_string(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _validation_error(path, "expected non-empty string")
    return value


def _require_bool(value: Any, path: str) -> bool:
    if type(value) is not bool:
        _validation_error(path, f"expected bool, got {type(value).__name__}")
    return value


def _require_string_list(
    value: Any,
    path: str,
    *,
    allow_empty: bool = True,
) -> list[str]:
    items = _require_list(value, path)
    if not allow_empty and not items:
        _validation_error(path, "must not be empty")
    result: list[str] = []
    for index, item in enumerate(items):
        result.append(_require_non_empty_string(item, f"{path}[{index}]"))
    if len(result) != len(set(result)):
        _validation_error(path, "items must be unique")
    return result


def _require_exact_fields(
    value: Mapping[Any, Any],
    expected: set[str],
    path: str,
) -> None:
    actual = set(value)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        _validation_error(path, f"fields mismatch; missing={missing}, extra={extra}")


def _validate_metadata_value_constraints(
    value: Any,
    path: str,
    *,
    required_metadata: list[str],
) -> dict[str, list[Any]]:
    constraints = _require_mapping(value, path)
    result: dict[str, list[Any]] = {}
    for field, allowed_value in constraints.items():
        field_name = _require_non_empty_string(field, path)
        if field_name not in required_metadata:
            _validation_error(
                f"{path}.{field_name}",
                "constraint field must be listed in required_metadata",
            )
        allowed = _require_list(allowed_value, f"{path}.{field_name}")
        if not allowed:
            _validation_error(f"{path}.{field_name}", "allowed values must not be empty")
        for index, item in enumerate(allowed):
            if item is None or isinstance(item, (Mapping, list)):
                _validation_error(
                    f"{path}.{field_name}[{index}]",
                    "expected JSON scalar",
                )
        result[field_name] = list(allowed)
    return result


def _ordered_union(values) -> list[str]:
    result: list[str] = []
    for value in values:
        if value not in result:
            result.append(value)
    return result


def _validate_route_ladder(
    route: Mapping[Any, Any],
    *,
    path: str,
    global_fact_types: set[str],
) -> None:
    ladder_value = route.get("authenticity_ladder")
    if ladder_value is None:
        return
    is_dexterous_axial = route.get("route_id") == "dexterous_axial_flux_motor"
    ladder = _require_mapping(ladder_value, f"{path}.authenticity_ladder")
    if tuple(ladder) != AF_LEVELS:
        _validation_error(
            f"{path}.authenticity_ladder",
            "must define AF0 through AF6 in order",
        )

    if route.get("flattened_requirements_projection") != (
        "ordered_union_of_fact_requirements"
    ):
        _validation_error(
            f"{path}.flattened_requirements_projection",
            "must be ordered_union_of_fact_requirements",
        )

    excluded_domains = _require_string_list(
        route.get("excluded_application_domains"),
        f"{path}.excluded_application_domains",
        allow_empty=False,
    )
    if "automotive" not in excluded_domains:
        _validation_error(
            f"{path}.excluded_application_domains",
            "must include automotive",
        )
    policy = _require_mapping(
        route.get("application_domain_policy"),
        f"{path}.application_domain_policy",
    )
    _require_exact_fields(
        policy,
        set(APPLICATION_DOMAIN_POLICY),
        f"{path}.application_domain_policy",
    )
    for field, expected in APPLICATION_DOMAIN_POLICY.items():
        if policy.get(field) != expected:
            _validation_error(
                f"{path}.application_domain_policy.{field}",
                f"expected {expected!r}",
            )

    local_contract_values = _require_mapping(
        route.get("route_fact_contracts"),
        f"{path}.route_fact_contracts",
    )
    local_contracts: dict[str, dict[str, Any]] = {}
    for raw_fact_type, raw_contract in local_contract_values.items():
        fact_type = _require_non_empty_string(
            raw_fact_type,
            f"{path}.route_fact_contracts",
        )
        contract_path = f"{path}.route_fact_contracts.{fact_type}"
        contract = _require_mapping(raw_contract, contract_path)
        _require_exact_fields(contract, ROUTE_FACT_CONTRACT_FIELDS, contract_path)
        if fact_type in global_fact_types:
            _validation_error(
                contract_path,
                "route-local fact type must not duplicate the global catalog",
            )
        required_metadata = _require_string_list(
            contract.get("required_metadata"),
            f"{contract_path}.required_metadata",
            allow_empty=False,
        )
        constraints = _validate_metadata_value_constraints(
            contract.get("metadata_value_constraints"),
            f"{contract_path}.metadata_value_constraints",
            required_metadata=required_metadata,
        )
        local_contracts[fact_type] = {
            "required_metadata": required_metadata,
            "metadata_value_constraints": constraints,
        }

    if is_dexterous_axial:
        patent_contract_path = f"{path}.route_fact_contracts.patent_standard"
        patent_contract = local_contracts.get("patent_standard")
        if patent_contract is None:
            _validation_error(patent_contract_path, "required route-local fact contract")
        if patent_contract["required_metadata"] != DEXTEROUS_PATENT_CONTRACT[
            "required_metadata"
        ]:
            _validation_error(
                f"{patent_contract_path}.required_metadata",
                "must require legal_status and legal_status_date",
            )
        if patent_contract[
            "metadata_value_constraints"
        ] != DEXTEROUS_PATENT_CONTRACT["metadata_value_constraints"]:
            _validation_error(
                f"{patent_contract_path}.metadata_value_constraints",
                "legal_status must allow only active or granted",
            )

    known_fact_types = global_fact_types | set(local_contracts)
    used_local_fact_types: set[str] = set()
    previous_pool_rank = -1
    for index, stage in enumerate(AF_LEVELS):
        rule_path = f"{path}.authenticity_ladder.{stage}"
        rule = _require_mapping(ladder.get(stage), rule_path)
        _require_exact_fields(rule, AF_RULE_FIELDS, rule_path)
        _require_non_empty_string(rule.get("meaning"), f"{rule_path}.meaning")

        rank = rule.get("rank")
        if type(rank) is not int or rank != index:
            _validation_error(f"{rule_path}.rank", f"expected {index}")

        pool = rule.get("max_pool")
        if pool is not None and (
            not isinstance(pool, str) or pool not in AF_POOL_ORDER
        ):
            _validation_error(
                f"{rule_path}.max_pool",
                "expected null, D, C, B or A",
            )
        pool_rank = AF_POOL_ORDER[pool]
        if pool_rank < previous_pool_rank:
            _validation_error(f"{rule_path}.max_pool", "pool cap must be monotonic")
        previous_pool_rank = pool_rank

        eligible = _require_bool(rule.get("eligible"), f"{rule_path}.eligible")
        if eligible is not (pool is not None):
            _validation_error(
                f"{rule_path}.eligible",
                "must be false only when max_pool is null",
            )

        match_mode = rule.get("fact_match_mode")
        if not isinstance(match_mode, str) or match_mode not in {
            "none",
            "any",
            "all",
        }:
            _validation_error(
                f"{rule_path}.fact_match_mode",
                "expected none, any or all",
            )
        requirement_values = _require_list(
            rule.get("fact_requirements"),
            f"{rule_path}.fact_requirements",
        )
        if match_mode == "none" and requirement_values:
            _validation_error(
                f"{rule_path}.fact_requirements",
                "must be empty when fact_match_mode is none",
            )
        if match_mode != "none" and not requirement_values:
            _validation_error(
                f"{rule_path}.fact_requirements",
                "must not be empty when facts are required",
            )

        projected_fact_types: list[str] = []
        projected_domains: list[str] = []
        projected_metadata: list[str] = []
        normalized_requirements: list[dict[str, Any]] = []
        for requirement_index, raw_requirement in enumerate(requirement_values):
            requirement_path = (
                f"{rule_path}.fact_requirements[{requirement_index}]"
            )
            requirement = _require_mapping(raw_requirement, requirement_path)
            _require_exact_fields(
                requirement,
                FACT_REQUIREMENT_FIELDS,
                requirement_path,
            )
            fact_type = _require_non_empty_string(
                requirement.get("fact_type"),
                f"{requirement_path}.fact_type",
            )
            if fact_type not in known_fact_types:
                _validation_error(
                    f"{requirement_path}.fact_type",
                    f"unknown fact type: {fact_type}",
                )
            domains = _require_string_list(
                requirement.get("required_application_domains"),
                f"{requirement_path}.required_application_domains",
            )
            metadata = _require_string_list(
                requirement.get("required_metadata"),
                f"{requirement_path}.required_metadata",
            )
            constraints = _validate_metadata_value_constraints(
                requirement.get("metadata_value_constraints"),
                f"{requirement_path}.metadata_value_constraints",
                required_metadata=metadata,
            )
            if index >= 2 and not domains:
                _validation_error(
                    f"{requirement_path}.required_application_domains",
                    "AF2 through AF6 require explicit application domains",
                )
            if domains and "application_domain" not in metadata:
                _validation_error(
                    f"{requirement_path}.required_metadata",
                    "application_domain is required when domains are constrained",
                )
            overlap = sorted(set(domains) & set(excluded_domains))
            if overlap:
                _validation_error(
                    f"{requirement_path}.required_application_domains",
                    "excluded domains cannot satisfy a fact requirement: "
                    + ", ".join(overlap),
                )
            if fact_type in local_contracts:
                used_local_fact_types.add(fact_type)
                contract = local_contracts[fact_type]
                if metadata != contract["required_metadata"]:
                    _validation_error(
                        f"{requirement_path}.required_metadata",
                        "must match the route-local fact contract",
                    )
                if constraints != contract["metadata_value_constraints"]:
                    _validation_error(
                        f"{requirement_path}.metadata_value_constraints",
                        "must match the route-local fact contract",
                    )
            projected_fact_types.append(fact_type)
            projected_domains.extend(domains)
            projected_metadata.extend(metadata)
            normalized_requirements.append(
                {
                    "fact_type": fact_type,
                    "required_application_domains": domains,
                    "required_metadata": metadata,
                    "metadata_value_constraints": constraints,
                }
            )

        flattened = {
            "required_fact_types": _ordered_union(projected_fact_types),
            "required_application_domains": _ordered_union(projected_domains),
            "required_metadata": _ordered_union(projected_metadata),
        }
        for field, projected in flattened.items():
            actual = _require_string_list(rule.get(field), f"{rule_path}.{field}")
            if actual != projected:
                _validation_error(
                    f"{rule_path}.{field}",
                    "must equal the ordered union of fact_requirements",
                )

        if is_dexterous_axial:
            expected_contract = DEXTEROUS_AXIAL_STAGE_CONTRACTS[stage]
            for field, actual in (
                ("max_pool", pool),
                ("eligible", eligible),
                ("fact_match_mode", match_mode),
            ):
                expected = expected_contract[field]
                if actual != expected:
                    _validation_error(
                        f"{rule_path}.{field}",
                        f"expected {expected!r}",
                    )
            expected_requirements = expected_contract["fact_requirements"]
            if len(normalized_requirements) != len(expected_requirements):
                _validation_error(
                    f"{rule_path}.fact_requirements",
                    f"expected {len(expected_requirements)} conditions",
                )
            for requirement_index, (actual, expected) in enumerate(
                zip(normalized_requirements, expected_requirements)
            ):
                for field in (
                    "fact_type",
                    "required_application_domains",
                    "required_metadata",
                    "metadata_value_constraints",
                ):
                    if actual[field] != expected[field]:
                        _validation_error(
                            f"{rule_path}.fact_requirements[{requirement_index}].{field}",
                            f"expected {expected[field]!r}",
                        )

    unused_contracts = sorted(set(local_contracts) - used_local_fact_types)
    if unused_contracts:
        _validation_error(
            f"{path}.route_fact_contracts",
            "unused route-local fact contracts: " + ", ".join(unused_contracts),
        )


def validate_industry_evidence_coverage(template, requirements) -> None:
    template_value = _require_mapping(template, "template")
    template_id = _require_non_empty_string(
        template_value.get("template_id"),
        "template.template_id",
    )
    evidence_types = _require_mapping(
        getattr(requirements, "evidence_types", None),
        "requirements.evidence_types",
    )
    known_evidence_types = {
        _require_non_empty_string(key, "requirements.evidence_types")
        for key in evidence_types
    }
    global_fact_types: set[str] = set()
    for evidence_type, raw_rule in evidence_types.items():
        rule_path = f"requirements.evidence_types.{evidence_type}"
        rule = _require_mapping(raw_rule, rule_path)
        global_fact_types.update(
            _require_string_list(
                rule.get("fact_types"),
                f"{rule_path}.fact_types",
                allow_empty=False,
            )
        )

    layer_values = _require_list(template_value.get("layers"), "template.layers")
    valid_node_ids: set[str] = set()
    for index, raw_layer in enumerate(layer_values):
        layer_path = f"template.layers[{index}]"
        layer = _require_mapping(raw_layer, layer_path)
        layer_id = _require_non_empty_string(
            layer.get("layer_id"),
            f"{layer_path}.layer_id",
        )
        node_id = f"{template_id}_{layer_id}"
        if node_id in valid_node_ids:
            _validation_error(f"{layer_path}.layer_id", "derived node id must be unique")
        valid_node_ids.add(node_id)

    route_values = _require_list(
        template_value.get("technology_routes"),
        "template.technology_routes",
    )
    route_ids: set[str] = set()
    routes: list[tuple[Mapping[Any, Any], str]] = []
    for index, raw_route in enumerate(route_values):
        route_path = f"template.technology_routes[{index}]"
        route = _require_mapping(raw_route, route_path)
        route_id = _require_non_empty_string(
            route.get("route_id"),
            f"{route_path}.route_id",
        )
        if route_id in route_ids:
            _validation_error(f"{route_path}.route_id", "must be unique")
        route_ids.add(route_id)
        routes.append((route, route_path))

    row_values = _require_list(
        template_value.get("evidence_requirements"),
        "template.evidence_requirements",
    )
    if not row_values:
        _validation_error("template.evidence_requirements", "must not be empty")
    requirement_ids: set[str] = set()
    keyword_values: list[str] = []
    independent_ids: list[str] = []
    for index, raw_row in enumerate(row_values):
        row_path = f"template.evidence_requirements[{index}]"
        row = _require_mapping(raw_row, row_path)
        requirement_id = _require_non_empty_string(
            row.get("requirement_id"),
            f"{row_path}.requirement_id",
        )
        if requirement_id in requirement_ids:
            _validation_error(f"{row_path}.requirement_id", "must be unique")
        requirement_ids.add(requirement_id)

        keyword_values.extend(
            _require_string_list(
                row.get("business_keywords"),
                f"{row_path}.business_keywords",
                allow_empty=False,
            )
        )
        _require_string_list(row.get("aliases"), f"{row_path}.aliases")
        _require_string_list(
            row.get("negative_examples"),
            f"{row_path}.negative_examples",
        )
        _require_string_list(
            row.get("product_terms"),
            f"{row_path}.product_terms",
            allow_empty=False,
        )
        scene_terms = _require_string_list(
            row.get("scene_terms"),
            f"{row_path}.scene_terms",
        )
        require_product_and_scene = _require_bool(
            row.get("require_product_and_scene"),
            f"{row_path}.require_product_and_scene",
        )
        if require_product_and_scene and not scene_terms:
            _validation_error(
                f"{row_path}.scene_terms",
                "must not be empty when product and scene are both required",
            )

        node_id = _require_non_empty_string(
            row.get("node_id"),
            f"{row_path}.node_id",
        )
        if node_id not in valid_node_ids:
            _validation_error(f"{row_path}.node_id", f"unknown node: {node_id}")
        route_id = row.get("technology_route_id")
        if route_id is not None:
            route_id = _require_non_empty_string(
                route_id,
                f"{row_path}.technology_route_id",
            )
            if route_id not in route_ids:
                _validation_error(
                    f"{row_path}.technology_route_id",
                    f"unknown technology route: {route_id}",
                )

        required_types = _require_string_list(
            row.get("required_evidence_type_ids"),
            f"{row_path}.required_evidence_type_ids",
            allow_empty=False,
        )
        for type_index, evidence_type in enumerate(required_types):
            if evidence_type not in known_evidence_types:
                _validation_error(
                    f"{row_path}.required_evidence_type_ids[{type_index}]",
                    f"unknown evidence type: {evidence_type}",
                )
        _require_non_empty_string(
            row.get("next_validation_action"),
            f"{row_path}.next_validation_action",
        )
        independent = _require_bool(
            row.get("independent_discovery"),
            f"{row_path}.independent_discovery",
        )
        if independent:
            independent_ids.append(requirement_id)
            if (
                template_id == "dexterous_hand"
                and requirement_id != "dexterous_axial_flux_motor"
            ):
                _validation_error(
                    f"{row_path}.independent_discovery",
                    "only dexterous_axial_flux_motor may enable independent discovery",
                )

    candidate_rules = _require_mapping(
        template_value.get("candidate_mapping_rules"),
        "template.candidate_mapping_rules",
    )
    expected_keywords = _require_string_list(
        candidate_rules.get("required_business_keywords"),
        "template.candidate_mapping_rules.required_business_keywords",
        allow_empty=False,
    )
    actual_counter = Counter(keyword_values)
    expected_counter = Counter(expected_keywords)
    if any(count != 1 for count in expected_counter.values()):
        _validation_error(
            "template.candidate_mapping_rules.required_business_keywords",
            "canonical keywords must be unique",
        )
    if actual_counter != expected_counter or any(
        count != 1 for count in actual_counter.values()
    ):
        missing = list((expected_counter - actual_counter).elements())
        extra = list((actual_counter - expected_counter).elements())
        _validation_error(
            "template.evidence_requirements.business_keywords",
            f"must match canonical keywords exactly; missing={missing}, extra={extra}",
        )
    if template_id == "dexterous_hand" and independent_ids != [
        "dexterous_axial_flux_motor"
    ]:
        _validation_error(
            "template.evidence_requirements.independent_discovery",
            "dexterous axial flux must be the only independent requirement",
        )

    for route, route_path in routes:
        _validate_route_ladder(
            route,
            path=route_path,
            global_fact_types=global_fact_types,
        )


def get_business_evidence_requirement(template, keyword: str) -> dict:
    matches = [
        dict(row)
        for row in template.get("evidence_requirements") or []
        if keyword in (row.get("business_keywords") or [])
    ]
    if len(matches) != 1:
        raise ValueError(f"business keyword must resolve once: {keyword}")
    return deepcopy(matches[0])


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
