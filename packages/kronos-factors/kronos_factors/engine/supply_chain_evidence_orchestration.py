"""Pure candidate-discovery and evidence-gap planning helpers."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
import hashlib
import math
from typing import Any, Literal

from .industry_chain_evidence_requirements import load_evidence_requirements
from .industry_chain_templates import get_industry_template


RunMode = Literal["dry-run", "collect", "score", "full"]
SourcePolicy = Literal["local-first", "official-gap"]
GapStatus = Literal[
    "satisfied",
    "pending_review",
    "missing",
    "proxy",
    "contradicted",
    "stale",
]

_RUN_MODES = {"dry-run", "collect", "score", "full"}
_SOURCE_POLICIES = {"local-first", "official-gap"}
_SOURCE_LIMIT_KEYS = {
    "discovery",
    "official_discovery_documents",
    "official_discovery_companies",
    "official_pages_per_company",
    "mapped_official_tasks",
    "mapped_cninfo_documents_per_task",
}


@dataclass(frozen=True)
class EvidenceRunRequest:
    chain_id: str
    as_of_date: date
    mode: RunMode
    source_policy: SourcePolicy
    mapping_ids: tuple[str, ...] = ()
    company_codes: tuple[str, ...] = ()
    source_limits: Mapping[str, int] = field(default_factory=dict)
    allow_score: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.chain_id, str) or not self.chain_id.strip():
            raise ValueError("chain_id must be a non-empty string")
        if type(self.as_of_date) is not date:
            raise ValueError("as_of_date must be a date")
        if self.mode not in _RUN_MODES:
            raise ValueError(f"invalid mode: {self.mode}")
        if self.source_policy not in _SOURCE_POLICIES:
            raise ValueError(f"invalid source_policy: {self.source_policy}")
        if type(self.allow_score) is not bool:
            raise ValueError("allow_score must be a boolean")
        self._validate_scope("mapping_ids", self.mapping_ids)
        self._validate_scope("company_codes", self.company_codes)
        if self.mapping_ids and self.company_codes:
            raise ValueError("mapping_ids and company_codes are mutually exclusive")
        if not isinstance(self.source_limits, Mapping):
            raise ValueError("source_limits must be a mapping")
        limits = dict(self.source_limits)
        for key, value in limits.items():
            if (
                key not in _SOURCE_LIMIT_KEYS
                or isinstance(value, bool)
                or not isinstance(value, int)
                or value <= 0
            ):
                raise ValueError(f"invalid source limit: {key}")
        object.__setattr__(self, "source_limits", limits)

    @staticmethod
    def _validate_scope(name: str, values: object) -> None:
        if type(values) is not tuple:
            raise ValueError(f"{name} must be a tuple")
        if any(not isinstance(value, str) or not value.strip() for value in values):
            raise ValueError(f"{name} must contain non-empty strings")
        if len(values) != len(set(values)):
            raise ValueError(f"{name} must not contain duplicates")


@dataclass(frozen=True)
class RequirementMatch:
    requirement_id: str
    product_hits: tuple[str, ...]
    scene_hits: tuple[str, ...]
    excluded_hits: tuple[str, ...]
    eligible_for_mapping: bool
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class CandidateMappingProposal:
    mapping_id: str
    company_code: str
    chain_id: str
    node_id: str
    tag_name: str
    technology_route_id: str | None
    status: Literal["candidate"]
    confidence: float
    evidence_ids: tuple[str, ...]
    provenance: Mapping[str, Any]


@dataclass(frozen=True)
class DiscoveryHit:
    doc_id: str
    company_code: str
    requirement_id: str
    product_hits: tuple[str, ...]
    scene_hits: tuple[str, ...]
    excluded_hits: tuple[str, ...]
    source_level: str
    publish_time: datetime | None
    eligible_for_mapping: bool
    validation_status: Literal["pending"]
    proposal: CandidateMappingProposal | None


@dataclass(frozen=True)
class EvidenceGap:
    mapping_id: str
    requirement_id: str
    status: GapStatus
    evidence_ids: tuple[str, ...]
    next_action: str
    reasons: tuple[str, ...]
    product_terms: tuple[str, ...] = ()
    scene_terms: tuple[str, ...] = ()
    negative_examples: tuple[str, ...] = ()
    require_product_and_scene: bool = True


@dataclass(frozen=True)
class NodeDimensionUpdate:
    node_id: str
    dimension_id: str
    as_of_date: date
    status: Literal["known", "proxy", "contradicted"]
    score: float | None
    evidence_ids: tuple[str, ...]


def _terms(value: object) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return ()
    result: list[str] = []
    for item in value:
        if isinstance(item, str) and item and item not in result:
            result.append(item)
    return tuple(result)


def _document_text(document: Mapping[str, Any]) -> str:
    return " ".join(
        value
        for key in ("title", "text", "content", "body", "original_quote")
        if isinstance((value := document.get(key)), str)
    )


def _hits(text: str, terms: tuple[str, ...]) -> tuple[str, ...]:
    normalized = text.casefold()
    return tuple(term for term in terms if term.casefold() in normalized)


def discover_candidate_documents(
    documents: Sequence[Mapping[str, Any]],
    requirement: Mapping[str, Any],
) -> list[RequirementMatch]:
    """Match canonical product and scene terms without promoting evidence."""

    requirement_id = str(requirement.get("requirement_id") or "")
    if not requirement_id:
        raise ValueError("requirement_id must be a non-empty string")
    product_terms = _terms(requirement.get("product_terms"))
    scene_terms = _terms(requirement.get("scene_terms"))
    negative_examples = _terms(requirement.get("negative_examples"))
    require_scene = requirement.get("require_product_and_scene", True) is not False
    results: list[RequirementMatch] = []
    for document in documents:
        text = _document_text(document)
        product_hits = _hits(text, product_terms)
        scene_hits = _hits(text, scene_terms)
        excluded_hits = _hits(text, negative_examples)
        reasons: list[str] = []
        if not product_hits:
            reasons.append("missing_product_term")
        if require_scene and not scene_hits:
            reasons.append("missing_scene_term")
        if excluded_hits:
            reasons.append("excluded_context")
        results.append(
            RequirementMatch(
                requirement_id=requirement_id,
                product_hits=product_hits,
                scene_hits=scene_hits,
                excluded_hits=excluded_hits,
                eligible_for_mapping=not reasons,
                reasons=tuple(reasons),
            )
        )
    return results


def _parse_datetime(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if type(value) is date:
        return datetime.combine(value, datetime.min.time())
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def _infer_chain_id(requirement: Mapping[str, Any]) -> str:
    configured = requirement.get("chain_id")
    if isinstance(configured, str) and configured.strip():
        return configured.strip()
    node_id = str(requirement.get("node_id") or "")
    for suffix in (
        "_commercialization",
        "_infrastructure",
        "_core_product",
        "_integration",
        "_foundation",
        "_supporting",
        "_demand",
        "_task",
    ):
        if node_id.endswith(suffix):
            return node_id[: -len(suffix)]
    raise ValueError("requirement must define a resolvable chain_id")


def _mapping_id(chain_id: str, company_code: str, requirement_id: str) -> str:
    signature = "\x1f".join((chain_id, company_code, requirement_id)).encode("utf-8")
    return "candidate_" + hashlib.sha256(signature).hexdigest()


def _document_fact_ids(document: Mapping[str, Any]) -> tuple[str, ...]:
    values: list[object] = []
    for key in ("discovery_fact_ids", "fact_ids"):
        raw = document.get(key)
        if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes)):
            values.extend(raw)
    if document.get("fact_id") is not None:
        values.append(document["fact_id"])
    return tuple(
        dict.fromkeys(str(value) for value in values if str(value or "").strip())
    )


def _document_domains(document: Mapping[str, Any]) -> set[str]:
    metadata = document.get("metadata")
    metadata = metadata if isinstance(metadata, Mapping) else {}
    raw = document.get("application_domain", metadata.get("application_domain"))
    if isinstance(raw, str):
        return {raw.casefold()}
    if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes)):
        return {str(value).casefold() for value in raw if str(value).strip()}
    return set()


def propose_independent_candidates(
    documents: Sequence[Mapping[str, Any]],
    requirement: Mapping[str, Any],
    as_of_date: date,
) -> list[DiscoveryHit]:
    """Create pending, auditable candidate leads for an independent requirement."""

    if requirement.get("independent_discovery") is not True:
        return []
    if type(as_of_date) is not date:
        raise ValueError("as_of_date must be a date")
    requirement_id = str(requirement.get("requirement_id") or "")
    if not requirement_id:
        raise ValueError("requirement_id must be a non-empty string")
    chain_id = _infer_chain_id(requirement)
    route_value = requirement.get("technology_route_id")
    technology_route_id = str(route_value) if route_value is not None else None
    node_id = str(requirement.get("node_id") or "")
    business_keywords = _terms(requirement.get("business_keywords"))
    product_terms = _terms(requirement.get("product_terms"))
    tag_name = (business_keywords or product_terms or (requirement_id,))[0]
    textual_matches = discover_candidate_documents(documents, requirement)
    records: list[dict[str, Any]] = []

    for document, match in zip(documents, textual_matches):
        doc_id = str(document.get("doc_id") or "")
        company_code = str(document.get("company_code") or "")
        source_level = str(document.get("source_level") or "").casefold()
        publish_time = _parse_datetime(document.get("publish_time"))
        source_eligible = source_level in {"mid", "strong"}
        cutoff_eligible = publish_time is not None and publish_time.date() <= as_of_date
        domain_eligible = True
        if technology_route_id == "dexterous_axial_flux_motor":
            domain_eligible = not bool(
                _document_domains(document)
                & {"automotive", "wheel_hub", "wheel-hub", "aviation", "aerospace"}
            )
        eligible = bool(
            match.eligible_for_mapping
            and source_eligible
            and cutoff_eligible
            and domain_eligible
            and doc_id
            and company_code
        )
        records.append(
            {
                "document": document,
                "doc_id": doc_id,
                "company_code": company_code,
                "source_level": source_level,
                "publish_time": publish_time,
                "match": match,
                "eligible": eligible,
            }
        )

    grouped_paths: dict[tuple[str, str, str], dict[str, list[str]]] = {}
    for record in records:
        if not record["eligible"]:
            continue
        key = (chain_id, record["company_code"], requirement_id)
        path = grouped_paths.setdefault(key, {"doc_ids": [], "fact_ids": []})
        path["doc_ids"].append(record["doc_id"])
        path["fact_ids"].extend(_document_fact_ids(record["document"]))

    results: list[DiscoveryHit] = []
    for record in records:
        proposal: CandidateMappingProposal | None = None
        if record["eligible"]:
            key = (chain_id, record["company_code"], requirement_id)
            grouped = grouped_paths[key]
            l1_l8_path = {
                "requirement_id": requirement_id,
                "technology_route_id": technology_route_id,
                "discovery_doc_ids": sorted(set(grouped["doc_ids"])),
                "discovery_fact_ids": sorted(set(grouped["fact_ids"])),
            }
            provenance = {
                "source": "independent_discovery",
                **l1_l8_path,
                "l1_l8_path": dict(l1_l8_path),
            }
            confidence = 0.35 if record["source_level"] == "strong" else 0.30
            proposal = CandidateMappingProposal(
                mapping_id=_mapping_id(*key),
                company_code=record["company_code"],
                chain_id=chain_id,
                node_id=node_id,
                tag_name=tag_name,
                technology_route_id=technology_route_id,
                status="candidate",
                confidence=confidence,
                evidence_ids=(),
                provenance=provenance,
            )
        match = record["match"]
        results.append(
            DiscoveryHit(
                doc_id=record["doc_id"],
                company_code=record["company_code"],
                requirement_id=requirement_id,
                product_hits=match.product_hits,
                scene_hits=match.scene_hits,
                excluded_hits=match.excluded_hits,
                source_level=record["source_level"],
                publish_time=record["publish_time"],
                eligible_for_mapping=record["eligible"],
                validation_status="pending",
                proposal=proposal,
            )
        )
    return results


def _metadata(fact: Mapping[str, Any]) -> Mapping[str, Any]:
    value = fact.get("metadata")
    return value if isinstance(value, Mapping) else {}


def _fact_value(fact: Mapping[str, Any], key: str) -> object:
    metadata = _metadata(fact)
    return metadata[key] if key in metadata else fact.get(key)


def _is_contradicted(fact: Mapping[str, Any]) -> bool:
    return bool(
        fact.get("validation_status") == "contradicted"
        or fact.get("fact_nature") == "contradicted"
        or fact.get("status") == "contradicted"
        or fact.get("contradicted") is True
        or _metadata(fact).get("contradicted") is True
    )


def _is_company_scope(fact: Mapping[str, Any]) -> bool:
    scope = (
        fact.get("fact_scope")
        or fact.get("scope")
        or _metadata(fact).get("fact_scope")
        or _metadata(fact).get("scope")
    )
    return str(scope or "").casefold() in {"company", "company_level"}


def _fact_matches_catalog_rule(
    fact: Mapping[str, Any],
    rule: Mapping[str, Any],
    source_level_rank: Mapping[str, int],
) -> bool:
    if str(fact.get("fact_type") or "") not in set(rule.get("fact_types") or []):
        return False
    for flag in rule.get("metadata_flags") or []:
        if _fact_value(fact, str(flag)) is not True:
            return False
    source_level = fact.get("source_level")
    if source_level is not None:
        actual_rank = source_level_rank.get(str(source_level).casefold(), 0)
        required_rank = source_level_rank.get(
            str(rule.get("minimum_source_level") or "").casefold(),
            0,
        )
        if actual_rank < required_rank:
            return False
    fact_nature = fact.get("fact_nature")
    if fact_nature is not None and fact_nature not in set(
        rule.get("allowed_fact_natures") or []
    ):
        return False
    return True


def _fact_id_tuple(facts: Sequence[Mapping[str, Any]]) -> tuple[str, ...]:
    values = [str(fact.get("fact_id") or "") for fact in facts]
    return tuple(dict.fromkeys(value for value in values if value))


def plan_evidence_gaps(
    mapping_ids: Sequence[str],
    requirement_ids: Sequence[str],
    facts: Sequence[Mapping[str, Any]],
    as_of_date: date,
    freshness_policies: Mapping[str, int],
) -> list[EvidenceGap]:
    """Return one isolated status for every mapping/requirement pair."""

    if type(as_of_date) is not date:
        raise ValueError("as_of_date must be a date")
    if not isinstance(freshness_policies, Mapping):
        raise ValueError("freshness_policies must be a mapping")
    for name, days in freshness_policies.items():
        if isinstance(days, bool) or not isinstance(days, int) or days <= 0:
            raise ValueError(f"invalid freshness policy: {name}")

    catalog = load_evidence_requirements()
    policies = {**catalog.freshness_policies, **dict(freshness_policies)}
    results: list[EvidenceGap] = []
    for mapping_id in mapping_ids:
        for requirement_id in requirement_ids:
            if requirement_id not in catalog.evidence_types:
                raise ValueError(f"unknown evidence requirement: {requirement_id}")
            rule = catalog.evidence_types[requirement_id]
            matching: list[Mapping[str, Any]] = []
            for fact in facts:
                if str(fact.get("mapping_id") or "") != str(mapping_id):
                    continue
                published = _parse_datetime(
                    fact.get("publish_time")
                    or fact.get("event_time")
                    or fact.get("created_at")
                )
                if published is not None and published.date() > as_of_date:
                    continue
                if _fact_matches_catalog_rule(fact, rule, catalog.source_level_rank):
                    matching.append(fact)

            buckets: dict[str, list[Mapping[str, Any]]] = {
                "satisfied": [],
                "pending_review": [],
                "proxy": [],
                "contradicted": [],
                "stale": [],
            }
            expiry_policy = rule.get("expiry_policy")
            expiry_days = policies.get(str(expiry_policy)) if expiry_policy else None
            for fact in matching:
                validation_status = str(fact.get("validation_status") or "").casefold()
                if validation_status in {"pending", "pending_review"}:
                    buckets["pending_review"].append(fact)
                    continue
                if validation_status == "contradicted":
                    buckets["contradicted"].append(fact)
                    continue
                if validation_status not in {"approved", "confirmed"}:
                    continue
                if _is_contradicted(fact):
                    buckets["contradicted"].append(fact)
                    continue
                published = _parse_datetime(
                    fact.get("publish_time")
                    or fact.get("event_time")
                    or fact.get("created_at")
                )
                if (
                    expiry_days is not None
                    and published is not None
                    and (as_of_date - published.date()).days > expiry_days
                ):
                    buckets["stale"].append(fact)
                elif _is_company_scope(fact):
                    buckets["proxy"].append(fact)
                else:
                    buckets["satisfied"].append(fact)

            status: GapStatus
            selected: list[Mapping[str, Any]]
            reasons: tuple[str, ...]
            if buckets["contradicted"]:
                status, selected = "contradicted", buckets["contradicted"]
                reasons = ("reviewed_evidence_is_contradicted",)
            elif buckets["satisfied"]:
                status, selected = "satisfied", buckets["satisfied"]
                reasons = ("approved_mapping_evidence_satisfies_requirement",)
            elif buckets["pending_review"]:
                status, selected = "pending_review", buckets["pending_review"]
                reasons = ("matching_evidence_requires_review",)
            elif buckets["proxy"]:
                status, selected = "proxy", buckets["proxy"]
                reasons = ("only_company_level_proxy_evidence",)
            elif buckets["stale"]:
                status, selected = "stale", buckets["stale"]
                reasons = ("approved_evidence_exceeds_freshness_policy",)
            else:
                status, selected = "missing", []
                reasons = ("no_eligible_mapping_evidence",)

            if status == "satisfied":
                next_action = "none"
            elif status == "pending_review":
                next_action = "review_pending_evidence"
            else:
                next_action = str(rule.get("default_next_action") or "collect_evidence")
            results.append(
                EvidenceGap(
                    mapping_id=str(mapping_id),
                    requirement_id=str(requirement_id),
                    status=status,
                    evidence_ids=_fact_id_tuple(selected),
                    next_action=next_action,
                    reasons=reasons,
                )
            )
    return results


def _documented_scoring_method(fact: Mapping[str, Any]) -> bool:
    method = (
        fact.get("scoring_method")
        or fact.get("score_method")
        or _metadata(fact).get("scoring_method")
        or _metadata(fact).get("score_method")
    )
    return bool(
        (isinstance(method, str) and method.strip())
        or (isinstance(method, Mapping) and method)
    )


def _numeric_score(fact: Mapping[str, Any], dimension_id: str) -> float | None:
    candidates: list[object] = []
    for container in (fact.get("dimension_scores"), _metadata(fact).get("dimension_scores")):
        if isinstance(container, Mapping) and dimension_id in container:
            candidates.append(container[dimension_id])
    candidates.extend((fact.get("score"), _metadata(fact).get("score")))
    for value in candidates:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        result = float(value)
        if math.isfinite(result):
            return result
    return None


def build_node_dimension_updates(
    facts: Sequence[Mapping[str, Any]],
    node_id: str,
    as_of_date: date,
) -> list[NodeDimensionUpdate]:
    """Project reviewed facts onto only their explicitly named dimensions."""

    if not isinstance(node_id, str) or not node_id.strip():
        raise ValueError("node_id must be a non-empty string")
    if type(as_of_date) is not date:
        raise ValueError("as_of_date must be a date")
    status_rank = {"proxy": 0, "known": 1, "contradicted": 2}
    order: list[str] = []
    accumulated: dict[str, dict[str, Any]] = {}
    for fact in facts:
        if str(fact.get("validation_status") or "").casefold() not in {
            "approved",
            "confirmed",
        }:
            continue
        dimension_ids = _terms(_metadata(fact).get("dimension_ids"))
        if not dimension_ids:
            continue
        status: Literal["known", "proxy", "contradicted"]
        if _is_contradicted(fact):
            status = "contradicted"
        elif _is_company_scope(fact) or _metadata(fact).get("proxy") is True:
            status = "proxy"
        else:
            status = "known"
        fact_id = str(fact.get("fact_id") or "")
        for dimension_id in dimension_ids:
            score = _numeric_score(fact, dimension_id)
            if status == "proxy" and not _documented_scoring_method(fact):
                score = None
            if dimension_id not in accumulated:
                order.append(dimension_id)
                accumulated[dimension_id] = {
                    "status": status,
                    "score": score,
                    "evidence_ids": [],
                }
            current = accumulated[dimension_id]
            if status_rank[status] > status_rank[current["status"]]:
                current["status"] = status
                current["score"] = score
            elif status == current["status"] and current["score"] is None:
                current["score"] = score
            if fact_id and fact_id not in current["evidence_ids"]:
                current["evidence_ids"].append(fact_id)
    return [
        NodeDimensionUpdate(
            node_id=node_id,
            dimension_id=dimension_id,
            as_of_date=as_of_date,
            status=accumulated[dimension_id]["status"],
            score=accumulated[dimension_id]["score"],
            evidence_ids=tuple(accumulated[dimension_id]["evidence_ids"]),
        )
        for dimension_id in order
    ]


def _default_axial_flux_route() -> Mapping[str, Any]:
    template = get_industry_template("dexterous_hand")
    for route in template.get("technology_routes") or []:
        if route.get("route_id") == "dexterous_axial_flux_motor":
            return route
    raise ValueError("dexterous axial-flux route is not configured")


def _values(value: object) -> tuple[object, ...]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return tuple(value)
    return (value,)


def _same_json_scalar(left: object, right: object) -> bool:
    return type(left) is type(right) and left == right


def _metadata_contract_matches(
    fact: Mapping[str, Any],
    contract: Mapping[str, Any],
) -> bool:
    for field_name in contract.get("required_metadata") or []:
        value = _fact_value(fact, str(field_name))
        if value is None or value == "" or value == []:
            return False
    constraints = contract.get("metadata_value_constraints") or {}
    if not isinstance(constraints, Mapping):
        return False
    for field_name, allowed_values in constraints.items():
        actual_values = _values(_fact_value(fact, str(field_name)))
        allowed = _values(allowed_values)
        if not any(
            _same_json_scalar(actual, expected)
            for actual in actual_values
            for expected in allowed
        ):
            return False
    return True


def _fact_domains(fact: Mapping[str, Any]) -> set[str]:
    return {
        str(value).casefold()
        for value in _values(_fact_value(fact, "application_domain"))
        if value is not None and str(value).strip()
    }


def _fact_satisfies_route_clause(
    fact: Mapping[str, Any],
    clause: Mapping[str, Any],
    route: Mapping[str, Any],
) -> bool:
    fact_type = str(clause.get("fact_type") or "")
    if str(fact.get("fact_type") or "") != fact_type:
        return False
    fact_domains = _fact_domains(fact)
    excluded = {
        str(value).casefold()
        for value in route.get("excluded_application_domains") or []
    }
    if fact_domains & excluded:
        return False
    required_domains = {
        str(value).casefold()
        for value in clause.get("required_application_domains") or []
    }
    if required_domains and not (fact_domains & required_domains):
        return False
    if not _metadata_contract_matches(fact, clause):
        return False
    route_contracts = route.get("route_fact_contracts") or {}
    if not isinstance(route_contracts, Mapping):
        return False
    local_contract = route_contracts.get(fact_type)
    if local_contract is not None:
        if not isinstance(local_contract, Mapping):
            return False
        if not _metadata_contract_matches(fact, local_contract):
            return False
    return True


def derive_axial_flux_stage(
    facts: Sequence[Mapping[str, Any]],
    route: Mapping[str, Any] | None = None,
) -> str:
    """Interpret the configured AF ladder using reviewed facts only."""

    configured_route = route or _default_axial_flux_route()
    ladder = configured_route.get("authenticity_ladder")
    if not isinstance(ladder, Mapping) or not ladder:
        raise ValueError("route authenticity_ladder must be a non-empty mapping")
    ordered = sorted(
        ladder.items(),
        key=lambda item: int(item[1].get("rank", -1)),
        reverse=True,
    )
    baseline = min(
        ladder.items(),
        key=lambda item: int(item[1].get("rank", -1)),
    )[0]
    reviewed_facts = [
        fact
        for fact in facts
        if str(fact.get("validation_status") or "").casefold()
        in {"approved", "confirmed"}
    ]
    for stage, raw_rule in ordered:
        if not isinstance(raw_rule, Mapping):
            raise ValueError(f"invalid route stage: {stage}")
        mode = raw_rule.get("fact_match_mode")
        if mode == "none":
            continue
        if mode not in {"any", "all"}:
            raise ValueError(f"invalid fact_match_mode for {stage}: {mode}")
        clauses = raw_rule.get("fact_requirements")
        if not isinstance(clauses, Sequence) or isinstance(clauses, (str, bytes)):
            raise ValueError(f"invalid fact_requirements for {stage}")
        matches = [
            any(
                _fact_satisfies_route_clause(fact, clause, configured_route)
                for fact in reviewed_facts
            )
            for clause in clauses
            if isinstance(clause, Mapping)
        ]
        if len(matches) != len(clauses):
            raise ValueError(f"invalid fact requirement clause for {stage}")
        if (mode == "any" and any(matches)) or (mode == "all" and all(matches)):
            return str(stage)
    return str(baseline)
