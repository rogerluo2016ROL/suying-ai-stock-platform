"""Mode-safe orchestration for supply-chain evidence collection and scoring."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import date, datetime, time
from typing import Any
from zoneinfo import ZoneInfo

from kronos_factors.engine import supply_chain_evidence_orchestration as evidence_domain
from kronos_factors.engine.industry_chain_evidence_requirements import (
    load_evidence_requirements,
)
from kronos_factors.engine.industry_chain_templates import get_industry_template
from kronos_factors.engine.supply_chain_evidence_orchestration import (
    DiscoveryHit,
    EvidenceGap,
    EvidenceRunRequest,
    RunMode,
    build_node_dimension_updates,
    plan_evidence_gaps,
    propose_independent_candidates,
)
from supply_chain_evidence_adapters import (
    AdapterResult,
    CollectionTask,
    UnmappedDiscoveryTask,
    normalize_stock_code,
    persist_adapter_result,
    sanitize_error,
)


_SHANGHAI = ZoneInfo("Asia/Shanghai")
_COLLECTABLE_GAP_STATUSES = {"missing", "stale", "proxy"}


@dataclass(frozen=True)
class EvidenceRunResult:
    chain_id: str
    as_of_date: date
    mode: RunMode
    candidate_count: int
    requirement_count: int
    local_hits: int
    official_discovery_hits: int
    official_gap_hits: int
    inserted_documents: int
    duplicate_documents: int
    pending_facts: int
    approved_facts: int
    failed_tasks: tuple[str, ...]
    pool_counts: Mapping[str, int]
    pool_transitions: int
    writes: int
    network_requests: int
    data_limitations: tuple[str, ...]
    companies: tuple[Mapping[str, Any], ...]


@dataclass(frozen=True)
class _PersistenceSummary:
    inserted_documents: int = 0
    duplicate_documents: int = 0
    pending_facts: int = 0
    document_attempts: int = 0
    # Top-level repository mutation calls, never SQL affected-row counts.
    writes: int = 0
    limitations: tuple[str, ...] = ()
    records: tuple[Mapping[str, Any], ...] = ()


@dataclass
class _DocumentAttemptTracker:
    fetched: int = 0
    inserted: int = 0
    duplicate: int = 0

    def add(self, summary: _PersistenceSummary) -> None:
        self.fetched += summary.document_attempts
        self.inserted += summary.inserted_documents
        self.duplicate += summary.duplicate_documents


def _unique(values: Sequence[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(str(value) for value in values if str(value)))


def _value(value: object, name: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


def _as_dict(value: object) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if hasattr(value, "__dict__"):
        return dict(vars(value))
    raise TypeError(f"expected mapping-like value, got {type(value).__name__}")


def _mapping_code(value: Mapping[str, Any]) -> str:
    return normalize_stock_code(value.get("code") or value.get("company_code"))


def _mapping_id(value: Mapping[str, Any]) -> str:
    return str(value.get("mapping_id") or "")


def end_of_day_shanghai(value: date) -> datetime:
    if type(value) is not date:
        raise ValueError("value must be a date")
    return datetime.combine(value, time.max, tzinfo=_SHANGHAI)


def empty_adapter_result() -> AdapterResult:
    return AdapterResult((), (), (), "empty", 0)


def _scope_mappings(
    mappings: Sequence[Mapping[str, Any]], request: EvidenceRunRequest
) -> tuple[dict[str, Any], ...]:
    allowed_mapping_ids = set(request.mapping_ids)
    allowed_codes = {
        normalize_stock_code(code) for code in request.company_codes if code
    }
    result: dict[str, dict[str, Any]] = {}
    for raw in mappings:
        item = _as_dict(raw)
        mapping_id = _mapping_id(item)
        code = _mapping_code(item)
        if not mapping_id:
            continue
        if item.get("chain_id") not in (None, "", request.chain_id):
            continue
        if allowed_mapping_ids and mapping_id not in allowed_mapping_ids:
            continue
        if allowed_codes and code not in allowed_codes:
            continue
        item["code"] = code
        item.setdefault("company_code", code)
        result.setdefault(mapping_id, item)
    return tuple(result[key] for key in sorted(result))


def resolve_discovery_scope(
    request: EvidenceRunRequest, mappings: Sequence[Mapping[str, Any]]
) -> tuple[bool, tuple[str, ...]]:
    if request.company_codes:
        return True, tuple(
            sorted(
                {
                    normalize_stock_code(code)
                    for code in request.company_codes
                    if normalize_stock_code(code)
                }
            )
        )
    if request.mapping_ids:
        requested = set(request.mapping_ids)
        return True, tuple(
            sorted(
                {
                    _mapping_code(item)
                    for item in mappings
                    if _mapping_id(item) in requested and _mapping_code(item)
                }
            )
        )
    return False, ()


def _proposal_record(hit: DiscoveryHit) -> dict[str, Any] | None:
    proposal = hit.proposal
    if proposal is None or not hit.eligible_for_mapping:
        return None
    provenance = dict(proposal.provenance)
    requirement_id = str(
        provenance.get("requirement_id")
        or (provenance.get("l1_l8_path") or {}).get("requirement_id")
        or hit.requirement_id
    )
    return {
        "mapping_id": proposal.mapping_id,
        "code": normalize_stock_code(proposal.company_code),
        "company_code": normalize_stock_code(proposal.company_code),
        "company_name": "",
        "chain_id": proposal.chain_id,
        "node_id": proposal.node_id,
        "tag_name": proposal.tag_name,
        "technology_route_id": proposal.technology_route_id,
        "status": proposal.status,
        "confidence": proposal.confidence,
        "evidence_ids": tuple(proposal.evidence_ids),
        "requirement_id": requirement_id,
        "l1_l8_path": provenance,
    }


def _merge_same_mapping(
    current: dict[str, Any], incoming: Mapping[str, Any]
) -> dict[str, Any]:
    result = dict(current)
    for key, value in incoming.items():
        if key == "evidence_ids":
            result[key] = _unique(
                tuple(result.get(key) or ()) + tuple(value or ())
            )
        elif result.get(key) in (None, "", (), [], {}):
            result[key] = value
    return result


def build_candidates(
    mappings: Sequence[Mapping[str, Any]],
    discovery_hits: Sequence[DiscoveryHit],
    request: EvidenceRunRequest,
) -> tuple[Mapping[str, Any], ...]:
    """Merge by deterministic mapping_id; never merge evidence across mappings."""

    scoped_mappings = _scope_mappings(mappings, request)
    scope_active, allowed_codes = resolve_discovery_scope(request, scoped_mappings)
    allowed = set(allowed_codes)
    by_mapping: dict[str, dict[str, Any]] = {
        _mapping_id(item): dict(item) for item in scoped_mappings
    }
    for hit in discovery_hits:
        code = normalize_stock_code(hit.company_code)
        if scope_active and code not in allowed:
            continue
        record = _proposal_record(hit)
        if record is None:
            continue
        mapping_id = _mapping_id(record)
        if mapping_id in by_mapping:
            by_mapping[mapping_id] = _merge_same_mapping(
                by_mapping[mapping_id], record
            )
        else:
            by_mapping[mapping_id] = record
    return tuple(by_mapping[key] for key in sorted(by_mapping))


def _template_requirements(chain_id: str) -> dict[str, dict[str, Any]]:
    template = get_industry_template(chain_id)
    return {
        str(item["requirement_id"]): dict(item)
        for item in template.get("evidence_requirements") or ()
        if item.get("requirement_id")
    }


def _candidate_requirement_id(candidate: Mapping[str, Any]) -> str:
    if candidate.get("requirement_id"):
        return str(candidate["requirement_id"])
    path = candidate.get("l1_l8_path")
    if not isinstance(path, Mapping):
        return ""
    if path.get("requirement_id"):
        return str(path["requirement_id"])
    nested = path.get("l1_l8_path")
    return str(nested.get("requirement_id") or "") if isinstance(nested, Mapping) else ""


def _gap_requirements(
    candidate: Mapping[str, Any],
    definitions: Mapping[str, Mapping[str, Any]],
) -> tuple[tuple[str, ...], Mapping[str, Any]]:
    business_requirement_id = _candidate_requirement_id(candidate)
    definition = definitions.get(business_requirement_id, {})
    required = tuple(
        str(value)
        for value in (
            candidate.get("required_evidence_type_ids")
            or definition.get("required_evidence_type_ids")
            or ()
        )
        if str(value)
    )
    if not required and business_requirement_id in load_evidence_requirements().evidence_types:
        required = (business_requirement_id,)
    return _unique(required), definition


def plan_run_gaps(
    candidates: Sequence[Mapping[str, Any]],
    repository,
    request: EvidenceRunRequest,
) -> tuple[EvidenceGap, ...]:
    mapping_ids = tuple(_mapping_id(item) for item in candidates if _mapping_id(item))
    facts = repository.fetch_asof_facts(
        mapping_ids,
        cutoff=end_of_day_shanghai(request.as_of_date),
    )
    definitions = _template_requirements(request.chain_id)
    gaps: list[EvidenceGap] = []
    for candidate in candidates:
        mapping_id = _mapping_id(candidate)
        requirement_ids, definition = _gap_requirements(candidate, definitions)
        if not mapping_id:
            continue
        product_terms = tuple(
            definition.get("product_terms") or candidate.get("product_terms") or ()
        )
        scene_terms = tuple(
            definition.get("scene_terms") or candidate.get("scene_terms") or ()
        )
        negatives = tuple(
            definition.get("negative_examples")
            or candidate.get("negative_examples")
            or ()
        )
        require_scene = (
            definition.get(
                "require_product_and_scene",
                candidate.get("require_product_and_scene", True),
            )
            is True
        )
        for requirement_id in requirement_ids:
            planned = plan_evidence_gaps(
                mapping_ids=(mapping_id,),
                requirement_ids=(requirement_id,),
                facts=facts,
                as_of_date=request.as_of_date,
                freshness_policies={},
            )
            gaps.extend(
                replace(
                    gap,
                    product_terms=product_terms,
                    scene_terms=scene_terms,
                    negative_examples=negatives,
                    require_product_and_scene=require_scene,
                )
                for gap in planned
            )
    return tuple(gaps)


def build_collection_tasks(
    gaps: Sequence[EvidenceGap],
    candidates: Sequence[Mapping[str, Any]] = (),
) -> list[CollectionTask]:
    """Create isolated tasks for missing/stale/proxy gaps with grouped terms."""

    candidate_by_mapping = {
        _mapping_id(item): item for item in candidates if _mapping_id(item)
    }
    tasks: list[CollectionTask] = []
    for gap in gaps:
        if gap.status not in _COLLECTABLE_GAP_STATUSES:
            continue
        candidate = candidate_by_mapping.get(gap.mapping_id, {})
        product_terms = tuple(gap.product_terms)
        scene_terms = tuple(gap.scene_terms)
        queries = _unique(product_terms + scene_terms)
        tasks.append(
            CollectionTask(
                mapping_id=gap.mapping_id,
                requirement_id=gap.requirement_id,
                company_code=_mapping_code(candidate),
                company_name=str(candidate.get("company_name") or ""),
                queries=queries,
                product_terms=product_terms,
                scene_terms=scene_terms,
                negative_examples=tuple(gap.negative_examples),
                require_product_and_scene=gap.require_product_and_scene,
            )
        )
    return tasks


def build_unmapped_discovery_tasks(
    requirements: Sequence[Mapping[str, Any]],
    hits: Sequence[DiscoveryHit],
    repository,
    request: EvidenceRunRequest,
    mappings: Sequence[Mapping[str, Any]],
) -> list[UnmappedDiscoveryTask]:
    scope_active, allowed_codes = resolve_discovery_scope(request, mappings)
    allowed = set(allowed_codes)
    if scope_active and not allowed_codes:
        return []
    tasks: list[UnmappedDiscoveryTask] = []
    for requirement in requirements:
        requirement_id = str(requirement.get("requirement_id") or "")
        existing_codes = {
            normalize_stock_code(hit.company_code)
            for hit in hits
            if hit.eligible_for_mapping and hit.requirement_id == requirement_id
        }
        company_limit = int(
            request.source_limits.get("official_discovery_companies", 20)
        )
        if scope_active:
            raw_seeds = [
                code for code in allowed_codes if code not in existing_codes
            ][:company_limit]
        else:
            raw_seeds = repository.fetch_discovery_seed_companies(
                request.as_of_date,
                requirement,
                company_limit,
            )
        seeds: list[str] = []
        for value in raw_seeds:
            code = normalize_stock_code(value)
            if not code or code in existing_codes or code in seeds:
                continue
            if scope_active and code not in allowed:
                continue
            seeds.append(code)
        tasks.append(
            UnmappedDiscoveryTask(
                chain_id=request.chain_id,
                requirement_id=requirement_id,
                product_terms=tuple(requirement.get("product_terms") or ()),
                scene_terms=tuple(requirement.get("scene_terms") or ()),
                negative_examples=tuple(requirement.get("negative_examples") or ()),
                require_product_and_scene=bool(
                    requirement.get("require_product_and_scene", True)
                ),
                seed_company_codes=tuple(seeds),
                allowed_company_codes=allowed_codes,
            )
        )
    return tasks


def _document_record(document: object) -> dict[str, Any]:
    if isinstance(document, Mapping):
        record = dict(document)
        record.setdefault(
            "text",
            f"{record.get('title') or ''} {record.get('content_text') or ''}".strip(),
        )
        return record
    metadata = _value(document, "metadata", {})
    metadata = dict(metadata) if isinstance(metadata, Mapping) else {}
    return {
        "doc_id": str(_value(document, "doc_id", "")),
        "company_code": normalize_stock_code(_value(document, "company_code", "")),
        "company_name": str(_value(document, "company_name", "") or ""),
        "source_level": str(_value(document, "source_level", "") or ""),
        "publish_time": _value(document, "publish_time"),
        "title": str(_value(document, "title", "") or ""),
        "content_text": str(_value(document, "content_text", "") or ""),
        "text": f"{_value(document, 'title', '') or ''} {_value(document, 'content_text', '') or ''}".strip(),
        "metadata": metadata,
        "fact_ids": tuple(metadata.get("fact_ids") or ()),
    }


def _scope_discovery_documents(
    documents: Sequence[object],
    *,
    scope_active: bool,
    allowed_codes: Sequence[str],
) -> tuple[tuple[dict[str, Any], ...], int]:
    allowed = set(allowed_codes)
    selected: list[dict[str, Any]] = []
    filtered = 0
    for document in documents:
        record = _document_record(document)
        code = normalize_stock_code(record.get("company_code"))
        record["company_code"] = code
        if not code or (scope_active and code not in allowed):
            filtered += 1
            continue
        selected.append(record)
    return tuple(selected), filtered


def _scope_adapter_result_for_task(
    result: AdapterResult, task: CollectionTask
) -> tuple[AdapterResult, int]:
    expected = normalize_stock_code(task.company_code)
    selected = tuple(
        document
        for document in result.documents
        if expected
        and normalize_stock_code(_value(document, "company_code", "")) == expected
    )
    filtered = len(result.documents) - len(selected)
    status = "partial_success" if result.failed_tasks or result.errors else (
        "success" if selected else "empty"
    )
    return (
        AdapterResult(
            selected,
            tuple(result.failed_tasks),
            tuple(result.errors),
            status,
            int(result.network_requests),
        ),
        filtered,
    )


def _combine_adapter_results(
    results: Sequence[AdapterResult], *, extra_errors: Sequence[str] = ()
) -> AdapterResult:
    documents: dict[str, object] = {}
    failed: list[str] = []
    errors: list[str] = list(extra_errors)
    requests = 0
    for result in results:
        for document in result.documents:
            key = str(_value(document, "doc_id", "")) or repr(document)
            documents.setdefault(key, document)
        failed.extend(result.failed_tasks)
        errors.extend(result.errors)
        requests += int(result.network_requests)
    status = "partial_success" if failed or errors else (
        "success" if documents else "empty"
    )
    return AdapterResult(
        tuple(documents.values()),
        _unique(failed),
        tuple(errors),
        status,
        requests,
    )


def _summarize_outcomes(
    outcomes: Sequence[object],
    *,
    mapping_id: str | None = None,
    company_code: str | None = None,
) -> _PersistenceSummary:
    inserted = 0
    duplicate = 0
    pending = 0
    limitations: list[str] = []
    records: list[Mapping[str, Any]] = []
    for outcome in outcomes:
        inserted_flag = _value(outcome, "inserted", None)
        if inserted_flag is None:
            inserted_flag = _value(outcome, "was_inserted", None)
        duplicate_flag = _value(outcome, "duplicate", None)
        if duplicate_flag is None:
            duplicate_flag = _value(outcome, "was_duplicate", None)
        if inserted_flag is True:
            inserted += 1
        if duplicate_flag is True:
            duplicate += 1
        if inserted_flag is not True and duplicate_flag is not True:
            limitations.append(
                "persistence_outcome_does_not_expose_insert_duplicate_counts"
            )
        validation_status = str(_value(outcome, "validation_status", "") or "")
        if validation_status in {"pending", "pending_review"}:
            pending += 1
            fact_mapping_id = _value(outcome, "fact_mapping_id", "__missing__")
            records.append(
                {
                    "fact_id": str(_value(outcome, "fact_id", "") or ""),
                    "mapping_id": str(
                        _value(outcome, "mapping_id", mapping_id) or mapping_id or ""
                    ),
                    "company_code": normalize_stock_code(company_code),
                    "validation_status": validation_status,
                    "unmapped": fact_mapping_id is None,
                }
            )
    return _PersistenceSummary(
        inserted_documents=inserted,
        duplicate_documents=duplicate,
        pending_facts=pending,
        document_attempts=len(outcomes),
        writes=len(outcomes),
        limitations=_unique(limitations),
        records=tuple(records),
    )


def _merge_persistence(
    *summaries: _PersistenceSummary,
) -> _PersistenceSummary:
    return _PersistenceSummary(
        inserted_documents=sum(item.inserted_documents for item in summaries),
        duplicate_documents=sum(item.duplicate_documents for item in summaries),
        pending_facts=sum(item.pending_facts for item in summaries),
        document_attempts=sum(item.document_attempts for item in summaries),
        writes=sum(item.writes for item in summaries),
        limitations=_unique(
            tuple(value for item in summaries for value in item.limitations)
        ),
        records=tuple(value for item in summaries for value in item.records),
    )


def _run_and_persist_tasks(
    tasks: Sequence[CollectionTask],
    *,
    adapter,
    repository,
    job_id: str,
    request: EvidenceRunRequest,
    use_source_limits: bool,
    attempt_tracker: _DocumentAttemptTracker | None = None,
) -> tuple[AdapterResult, _PersistenceSummary, tuple[str, ...]]:
    selected_tasks = list(tasks)
    extra_errors: list[str] = []
    if use_source_limits:
        limit = int(request.source_limits.get("mapped_official_tasks", 100))
        if len(selected_tasks) > limit:
            extra_errors.append(
                f"source_limit_skipped_tasks:{len(selected_tasks) - limit}"
            )
            selected_tasks = selected_tasks[:limit]
    results: list[AdapterResult] = []
    persistence: list[_PersistenceSummary] = []
    limitations: list[str] = []
    for task in selected_tasks:
        if use_source_limits:
            raw_result = adapter.collect(
                [task],
                as_of_date=request.as_of_date,
                source_limits={**dict(request.source_limits), "mapped_official_tasks": 1},
            )
        else:
            raw_result = adapter.collect([task], as_of_date=request.as_of_date)
        scoped_result, filtered = _scope_adapter_result_for_task(raw_result, task)
        if filtered:
            limitations.append(f"scope_filtered_mapped_documents:{filtered}")
        results.append(scoped_result)
        for document in scoped_result.documents:
            outcomes = persist_adapter_result(
                AdapterResult((document,), (), (), "success", 0),
                repository=repository,
                task=task,
                job_id=job_id,
                as_of_date=request.as_of_date,
            )
            summary = _summarize_outcomes(
                outcomes,
                mapping_id=task.mapping_id,
                company_code=task.company_code,
            )
            persistence.append(summary)
            if attempt_tracker is not None:
                attempt_tracker.add(summary)
    return (
        _combine_adapter_results(results, extra_errors=extra_errors),
        _merge_persistence(*persistence),
        _unique(limitations),
    )


def replan_after_persist(
    candidates: Sequence[Mapping[str, Any]], repository, request: EvidenceRunRequest
) -> tuple[EvidenceGap, ...]:
    return plan_run_gaps(candidates, repository, request)


def _audited_facts(
    facts: Sequence[Mapping[str, Any]], as_of_date: date
) -> tuple[Mapping[str, Any], ...]:
    return tuple(
        fact
        for fact in facts
        if evidence_domain._is_fully_reviewed_fact(fact, as_of_date)
        and evidence_domain._formal_publish_time(fact, as_of_date) is not None
    )


def _unique_facts(
    facts: Sequence[Mapping[str, Any]],
) -> tuple[Mapping[str, Any], ...]:
    by_id: dict[str, Mapping[str, Any]] = {}
    for fact in facts:
        fact_id = str(fact.get("fact_id") or "")
        if fact_id:
            by_id[fact_id] = fact
    return tuple(by_id.values())


def _final_fact_counts(
    facts: Sequence[Mapping[str, Any]],
    persistence: _PersistenceSummary | None,
    as_of_date: date,
) -> tuple[int, int]:
    unique_facts = _unique_facts(facts)
    final_ids = {str(fact.get("fact_id") or "") for fact in unique_facts}
    approved = 0
    pending_ids: set[str] = set()
    for fact in unique_facts:
        fact_id = str(fact.get("fact_id") or "")
        validation = str(fact.get("validation_status") or "").casefold()
        if evidence_domain._is_fully_reviewed_fact(fact, as_of_date) and (
            evidence_domain._formal_publish_time(fact, as_of_date) is not None
        ):
            approved += 1
        elif validation in {"pending", "pending_review", "approved", "confirmed"}:
            pending_ids.add(fact_id)
    if persistence is not None:
        for record in persistence.records:
            fact_id = str(record.get("fact_id") or "")
            if (
                fact_id
                and fact_id not in final_ids
            ):
                pending_ids.add(fact_id)
    return approved, len(pending_ids)


def _fact_detail(fact: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "fact_id": str(fact.get("fact_id") or ""),
        "summary": str(
            fact.get("original_quote")
            or fact.get("fact_value")
            or fact.get("title")
            or fact.get("fact_type")
            or ""
        )[:300],
        "validation_status": str(fact.get("validation_status") or ""),
    }


def _initial_layers(candidate: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    raw = candidate.get("layers")
    if not isinstance(raw, Mapping):
        path = candidate.get("l1_l8_path")
        if isinstance(path, Mapping):
            raw = path.get("layers") or path.get("matrix")
    if not isinstance(raw, Mapping):
        return {}
    return {
        str(layer): {
            str(dimension): dict(cell) if isinstance(cell, Mapping) else cell
            for dimension, cell in dimensions.items()
        }
        for layer, dimensions in raw.items()
        if isinstance(dimensions, Mapping)
    }


def _company_details(
    candidates: Sequence[Mapping[str, Any]],
    gaps: Sequence[EvidenceGap],
    facts: Sequence[Mapping[str, Any]] = (),
    persistence: _PersistenceSummary | None = None,
    as_of_date: date | None = None,
) -> tuple[Mapping[str, Any], ...]:
    facts_by_mapping: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    unique_facts = _unique_facts(facts)
    final_fact_ids = {str(fact.get("fact_id") or "") for fact in unique_facts}
    for fact in unique_facts:
        facts_by_mapping[str(fact.get("mapping_id") or "")].append(fact)
    gaps_by_mapping: dict[str, list[EvidenceGap]] = defaultdict(list)
    for gap in gaps:
        gaps_by_mapping[gap.mapping_id].append(gap)
    pending_records: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    if persistence is not None:
        for record in persistence.records:
            pending_records[str(record.get("mapping_id") or "")].append(record)

    details: list[Mapping[str, Any]] = []
    for candidate in candidates:
        mapping_id = _mapping_id(candidate)
        approved: list[Mapping[str, Any]] = []
        pending: list[Mapping[str, Any]] = []
        rejected: list[Mapping[str, Any]] = []
        layers = _initial_layers(candidate)
        for fact in facts_by_mapping.get(mapping_id, []):
            validation = str(fact.get("validation_status") or "").casefold()
            if validation == "rejected":
                rejected.append(_fact_detail(fact))
                continue
            cutoff = as_of_date or date.max
            contradicted = evidence_domain._is_contradicted(fact)
            reviewed = evidence_domain._is_fully_reviewed_fact(fact, cutoff)
            if reviewed:
                approved.append(_fact_detail(fact))
                metadata = fact.get("metadata")
                metadata = metadata if isinstance(metadata, Mapping) else {}
                layer_id = str(fact.get("layer_id") or metadata.get("layer_id") or "")
                dimension_ids = metadata.get("dimension_ids")
                if layer_id and isinstance(dimension_ids, Sequence) and not isinstance(
                    dimension_ids, (str, bytes)
                ):
                    status = "contradicted" if contradicted else (
                        "proxy"
                        if evidence_domain._is_company_scope(fact)
                        or metadata.get("proxy") is True
                        else "known"
                    )
                    for dimension_id in dimension_ids:
                        dimension_id = str(dimension_id)
                        cell = layers.setdefault(layer_id, {}).get(dimension_id)
                        mutable = dict(cell) if isinstance(cell, Mapping) else {}
                        rank = {
                            "unknown": -1,
                            "proxy": 0,
                            "known": 1,
                            "contradicted": 2,
                        }
                        current_status = str(mutable.get("status") or "unknown")
                        if rank.get(status, -1) > rank.get(current_status, -1):
                            mutable["status"] = status
                        else:
                            mutable.setdefault("status", current_status)
                        evidence_ids = list(mutable.get("evidence_ids") or ())
                        fact_id = str(fact.get("fact_id") or "")
                        if fact_id and fact_id not in evidence_ids:
                            evidence_ids.append(fact_id)
                        mutable["evidence_ids"] = evidence_ids
                        layers[layer_id][dimension_id] = mutable
            else:
                pending.append(_fact_detail(fact))
        existing_pending_ids = {str(item.get("fact_id") or "") for item in pending}
        for record in pending_records.get(mapping_id, []):
            fact_id = str(record.get("fact_id") or "")
            if (
                fact_id
                and fact_id not in final_fact_ids
                and fact_id not in existing_pending_ids
            ):
                pending.append(
                    {
                        "fact_id": fact_id,
                        "summary": "新采集证据待审核",
                        "validation_status": "pending",
                    }
                )
                existing_pending_ids.add(fact_id)
        mapping_gaps = gaps_by_mapping.get(mapping_id, [])
        details.append(
            {
                "company_code": _mapping_code(candidate),
                "company_name": str(candidate.get("company_name") or ""),
                "mapping_id": mapping_id,
                "node_id": str(candidate.get("node_id") or ""),
                "tag_name": str(candidate.get("tag_name") or ""),
                "mapping_status": str(candidate.get("status") or ""),
                "approved": approved,
                "pending": pending,
                "rejected": rejected,
                "gaps": [
                    {
                        "requirement_id": gap.requirement_id,
                        "status": gap.status,
                        "evidence_ids": list(gap.evidence_ids),
                        "next_action": gap.next_action,
                    }
                    for gap in mapping_gaps
                ],
                "next_actions": list(
                    _unique(
                        tuple(
                            gap.next_action
                            for gap in mapping_gaps
                            if gap.next_action and gap.next_action != "none"
                        )
                    )
                ),
                "layers": layers,
            }
        )
    return tuple(details)


def build_result(
    request: EvidenceRunRequest,
    candidates: Sequence[Mapping[str, Any]],
    gaps: Sequence[EvidenceGap],
    *,
    writes: int = 0,
    network_requests: int = 0,
    data_limitations: Sequence[str] = (),
) -> EvidenceRunResult:
    return EvidenceRunResult(
        chain_id=request.chain_id,
        as_of_date=request.as_of_date,
        mode=request.mode,
        candidate_count=len(candidates),
        requirement_count=len(gaps),
        local_hits=0,
        official_discovery_hits=0,
        official_gap_hits=0,
        inserted_documents=0,
        duplicate_documents=0,
        pending_facts=0,
        approved_facts=0,
        failed_tasks=(),
        pool_counts={},
        pool_transitions=0,
        writes=writes,
        network_requests=network_requests,
        data_limitations=_unique(tuple(data_limitations)),
        companies=_company_details(
            candidates, gaps, as_of_date=request.as_of_date
        ),
    )


def build_empty_score_result(
    request: EvidenceRunRequest, *, reason: str
) -> EvidenceRunResult:
    return EvidenceRunResult(
        chain_id=request.chain_id,
        as_of_date=request.as_of_date,
        mode=request.mode,
        candidate_count=0,
        requirement_count=0,
        local_hits=0,
        official_discovery_hits=0,
        official_gap_hits=0,
        inserted_documents=0,
        duplicate_documents=0,
        pending_facts=0,
        approved_facts=0,
        failed_tasks=(),
        pool_counts={},
        pool_transitions=0,
        writes=0,
        network_requests=0,
        data_limitations=(reason,),
        companies=(),
    )


def _score_limitations(score_result: Mapping[str, Any]) -> tuple[str, ...]:
    values: list[str] = []
    for row in score_result.get("results") or ():
        if isinstance(row, Mapping):
            values.extend(str(item) for item in row.get("data_limitations") or ())
    return _unique(values)


def run_approved_score(
    request: EvidenceRunRequest, repository, score_runner
) -> EvidenceRunResult:
    raw_mappings = repository.fetch_mappings(
        request.chain_id,
        request.mapping_ids,
        request.company_codes,
    )
    scoped_mappings = _scope_mappings(raw_mappings, request)
    if not scoped_mappings:
        return build_empty_score_result(request, reason="no_scoped_mappings")
    scoped_mapping_ids = [_mapping_id(item) for item in scoped_mappings]
    facts = repository.fetch_asof_facts(
        tuple(scoped_mapping_ids),
        cutoff=end_of_day_shanghai(request.as_of_date),
    )
    audited = _audited_facts(facts, request.as_of_date)
    mapping_to_node = {
        _mapping_id(item): str(item.get("node_id") or "")
        for item in scoped_mappings
    }
    facts_by_node: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for fact in audited:
        node_id = mapping_to_node.get(str(fact.get("mapping_id") or ""), "")
        if node_id:
            facts_by_node[node_id].append(fact)
    updates = [
        update
        for node_id in sorted(facts_by_node)
        for update in build_node_dimension_updates(
            facts_by_node[node_id], node_id, request.as_of_date
        )
    ]
    dimension_writes = 0
    limitations: list[str] = []
    if updates:
        repository.upsert_node_dimension_updates(updates, request.as_of_date)
        dimension_writes = 1
    score_payload = score_runner(
        chain_id=request.chain_id,
        trade_date=request.as_of_date,
        mapping_ids=scoped_mapping_ids,
        dry_run=False,
    )
    score_result = dict(score_payload or {})
    gaps = plan_run_gaps(scoped_mappings, repository, request)
    scorer_writes = 1
    mapping_count = score_result.get("mapping_count", len(scoped_mappings))
    if not isinstance(mapping_count, int) or isinstance(mapping_count, bool):
        mapping_count = len(scoped_mappings)
    transitions = score_result.get("transitions", 0)
    if not isinstance(transitions, int) or isinstance(transitions, bool):
        transitions = 0
    approved_count, pending_count = _final_fact_counts(
        facts, None, request.as_of_date
    )
    return EvidenceRunResult(
        chain_id=request.chain_id,
        as_of_date=request.as_of_date,
        mode=request.mode,
        candidate_count=mapping_count,
        requirement_count=len(gaps),
        local_hits=0,
        official_discovery_hits=0,
        official_gap_hits=0,
        inserted_documents=0,
        duplicate_documents=0,
        pending_facts=pending_count,
        approved_facts=approved_count,
        failed_tasks=_unique(tuple(score_result.get("failed_tasks") or ())),
        pool_counts=dict(score_result.get("pool_counts") or {}),
        pool_transitions=transitions,
        writes=dimension_writes + scorer_writes,
        network_requests=0,
        data_limitations=_unique(
            tuple(limitations) + _score_limitations(score_result)
        ),
        companies=_company_details(
            scoped_mappings,
            gaps,
            facts,
            as_of_date=request.as_of_date,
        ),
    )


def build_result_from_runs(
    request: EvidenceRunRequest,
    candidates: Sequence[Mapping[str, Any]],
    gaps: Sequence[EvidenceGap],
    local_result: AdapterResult,
    official_discovery_result: AdapterResult,
    official_result: AdapterResult,
    persisted: _PersistenceSummary,
    score_result: EvidenceRunResult | None,
    *,
    facts: Sequence[Mapping[str, Any]] = (),
    data_limitations: Sequence[str] = (),
) -> EvidenceRunResult:
    adapters = (local_result, official_discovery_result, official_result)
    failed = _unique(
        tuple(value for result in adapters for value in result.failed_tasks)
    )
    adapter_limitations = tuple(
        f"adapter_error:{error}"
        for result in adapters
        for error in result.errors
    )
    score_limitations = score_result.data_limitations if score_result else ()
    approved_count, pending_count = _final_fact_counts(
        facts, persisted, request.as_of_date
    )
    return EvidenceRunResult(
        chain_id=request.chain_id,
        as_of_date=request.as_of_date,
        mode=request.mode,
        candidate_count=len(candidates),
        requirement_count=len(gaps),
        local_hits=len(local_result.documents),
        official_discovery_hits=len(official_discovery_result.documents),
        official_gap_hits=len(official_result.documents),
        inserted_documents=persisted.inserted_documents,
        duplicate_documents=persisted.duplicate_documents,
        pending_facts=pending_count,
        approved_facts=approved_count,
        failed_tasks=_unique(failed + (score_result.failed_tasks if score_result else ())),
        pool_counts=dict(score_result.pool_counts) if score_result else {},
        pool_transitions=score_result.pool_transitions if score_result else 0,
        writes=persisted.writes + (score_result.writes if score_result else 0),
        network_requests=sum(result.network_requests for result in adapters),
        data_limitations=_unique(
            tuple(data_limitations)
            + persisted.limitations
            + adapter_limitations
            + tuple(score_limitations)
        ),
        companies=_company_details(
            candidates,
            gaps,
            facts,
            persisted,
            request.as_of_date,
        ),
    )


def _finish_payload(
    *results: AdapterResult,
    status: str | None = None,
    errors: Sequence[str] = (),
    failed_tasks: Sequence[str] = (),
    fetched_count: int | None = None,
    inserted_count: int = 0,
    duplicate_count: int = 0,
) -> dict[str, Any]:
    combined = _combine_adapter_results(results)
    all_failed = _unique(tuple(combined.failed_tasks) + tuple(failed_tasks))
    resolved_status = status or (
        "partial_success"
        if all_failed or combined.errors or errors
        else "success"
    )
    return {
        "status": resolved_status,
        "documents": combined.documents,
        "failed_tasks": all_failed,
        "errors": tuple(combined.errors) + tuple(errors),
        "fetched_count": (
            len(combined.documents) if fetched_count is None else fetched_count
        ),
        "inserted_count": inserted_count,
        "duplicate_count": duplicate_count,
    }


def run_evidence_orchestration(
    request: EvidenceRunRequest,
    *,
    repository,
    local_adapter,
    official_discovery_adapter,
    official_adapter,
    score_runner,
) -> EvidenceRunResult:
    raw_mappings = repository.fetch_mappings(
        request.chain_id,
        request.mapping_ids,
        request.company_codes,
    )
    mappings = _scope_mappings(raw_mappings, request)
    if request.mode == "score":
        return run_approved_score(request, repository, score_runner)

    requirements = tuple(
        repository.fetch_independent_discovery_requirements(request.chain_id)
    )
    scope_active, discovery_codes = resolve_discovery_scope(request, mappings)
    discovery_hits: list[DiscoveryHit] = []
    if not (scope_active and not discovery_codes):
        for requirement in requirements:
            universe = repository.fetch_candidate_universe(
                request.as_of_date,
                requirement,
                discovery_codes,
                request.source_limits.get("discovery", 5000),
            )
            scoped_documents, _ = _scope_discovery_documents(
                universe,
                scope_active=scope_active,
                allowed_codes=discovery_codes,
            )
            discovery_hits.extend(
                propose_independent_candidates(
                    scoped_documents,
                    requirement=requirement,
                    as_of_date=request.as_of_date,
                )
            )
    candidates = build_candidates(mappings, tuple(discovery_hits), request)
    gaps = plan_run_gaps(candidates, repository, request)
    if request.mode == "dry-run":
        limitations = tuple(
            f"unresolved_technology_route:{mapping_id}"
            for mapping_id in getattr(repository, "unresolved_technology_routes", ())
        )
        return build_result(
            request,
            candidates,
            gaps,
            writes=0,
            network_requests=0,
            data_limitations=limitations,
        )

    job_id = repository.start_job(request)
    official_discovery_result = empty_adapter_result()
    local_result = empty_adapter_result()
    official_result = empty_adapter_result()
    persistence = _PersistenceSummary(writes=1)  # start_job
    attempt_tracker = _DocumentAttemptTracker()
    limitations: list[str] = []
    try:
        if request.source_policy == "official-gap":
            discovery_tasks = build_unmapped_discovery_tasks(
                requirements,
                tuple(discovery_hits),
                repository,
                request,
                mappings,
            )
            if discovery_tasks:
                raw_official_discovery = official_discovery_adapter.collect(
                    discovery_tasks,
                    as_of_date=request.as_of_date,
                    source_limits=request.source_limits,
                )
                scoped_documents, filtered = _scope_discovery_documents(
                    raw_official_discovery.documents,
                    scope_active=scope_active,
                    allowed_codes=discovery_codes,
                )
                if filtered:
                    limitations.append(
                        f"scope_filtered_official_discovery_documents:{filtered}"
                    )
                official_discovery_result = AdapterResult(
                    tuple(
                        document
                        for document in raw_official_discovery.documents
                        if normalize_stock_code(
                            _value(document, "company_code", "")
                        )
                        and (
                            not scope_active
                            or normalize_stock_code(
                                _value(document, "company_code", "")
                            )
                            in set(discovery_codes)
                        )
                    ),
                    tuple(raw_official_discovery.failed_tasks),
                    tuple(raw_official_discovery.errors),
                    raw_official_discovery.status,
                    raw_official_discovery.network_requests,
                )
                for requirement in requirements:
                    discovery_hits.extend(
                        propose_independent_candidates(
                            scoped_documents,
                            requirement=requirement,
                            as_of_date=request.as_of_date,
                        )
                    )

        allowed = set(discovery_codes)
        seen_hits: set[tuple[str, str, str]] = set()
        discovery_summaries: list[_PersistenceSummary] = []
        mapping_writes = 0
        for hit in discovery_hits:
            code = normalize_stock_code(hit.company_code)
            identity = (hit.doc_id, hit.requirement_id, code)
            if identity in seen_hits:
                continue
            seen_hits.add(identity)
            if scope_active and code not in allowed:
                continue
            outcome = repository.persist_discovery_hit(hit, job_id=job_id)
            proposal = _value(outcome, "proposal", None)
            discovery_summary = _summarize_outcomes(
                (outcome,),
                mapping_id=(
                    str(_value(proposal, "mapping_id", ""))
                    if proposal is not None
                    else None
                ),
                company_code=code,
            )
            discovery_summaries.append(discovery_summary)
            attempt_tracker.add(discovery_summary)
            if proposal is not None and (not scope_active or code in allowed):
                repository.upsert_candidate_mapping(proposal)
                mapping_writes += 1
        persistence = _merge_persistence(
            persistence,
            *discovery_summaries,
            _PersistenceSummary(writes=mapping_writes),
        )

        raw_mappings = repository.fetch_mappings(
            request.chain_id,
            request.mapping_ids,
            request.company_codes,
        )
        mappings = _scope_mappings(raw_mappings, request)
        candidates = build_candidates(mappings, (), request)
        gaps = plan_run_gaps(candidates, repository, request)
        tasks = build_collection_tasks(gaps, candidates)
        local_result, local_persistence, local_limitations = _run_and_persist_tasks(
            tasks,
            adapter=local_adapter,
            repository=repository,
            job_id=job_id,
            request=request,
            use_source_limits=False,
            attempt_tracker=attempt_tracker,
        )
        persistence = _merge_persistence(persistence, local_persistence)
        limitations.extend(local_limitations)

        remaining = replan_after_persist(candidates, repository, request)
        if request.source_policy == "official-gap":
            official_tasks = build_collection_tasks(remaining, candidates)
            if official_tasks:
                official_result, official_persistence, official_limitations = (
                    _run_and_persist_tasks(
                        official_tasks,
                        adapter=official_adapter,
                        repository=repository,
                        job_id=job_id,
                        request=request,
                        use_source_limits=True,
                        attempt_tracker=attempt_tracker,
                    )
                )
                persistence = _merge_persistence(
                    persistence, official_persistence
                )
                limitations.extend(official_limitations)

        score_result = None
        if request.mode == "full" and request.allow_score:
            score_result = run_approved_score(request, repository, score_runner)
        final_gaps = replan_after_persist(candidates, repository, request)
        final_facts = repository.fetch_asof_facts(
            tuple(_mapping_id(item) for item in candidates),
            cutoff=end_of_day_shanghai(request.as_of_date),
        )
        limitations.extend(
            f"unresolved_technology_route:{mapping_id}"
            for mapping_id in getattr(repository, "unresolved_technology_routes", ())
        )
        persistence = _merge_persistence(
            persistence, _PersistenceSummary(writes=1)  # finish_job
        )
        result = build_result_from_runs(
            request,
            candidates,
            final_gaps,
            local_result,
            official_discovery_result,
            official_result,
            persistence,
            score_result,
            facts=final_facts,
            data_limitations=limitations,
        )
        repository.finish_job(
            job_id,
            _finish_payload(
                local_result,
                official_discovery_result,
                official_result,
                failed_tasks=(score_result.failed_tasks if score_result else ()),
                fetched_count=attempt_tracker.fetched,
                inserted_count=result.inserted_documents,
                duplicate_count=result.duplicate_documents,
            ),
        )
        return result
    except Exception as exc:
        try:
            repository.finish_job(
                job_id,
                _finish_payload(
                    local_result,
                    official_discovery_result,
                    official_result,
                    status="failed",
                    errors=(sanitize_error(exc),),
                    fetched_count=attempt_tracker.fetched,
                    inserted_count=attempt_tracker.inserted,
                    duplicate_count=attempt_tracker.duplicate,
                ),
            )
        except Exception:
            pass
        raise


__all__ = [
    "EvidenceRunRequest",
    "EvidenceRunResult",
    "build_candidates",
    "build_collection_tasks",
    "build_empty_score_result",
    "build_result",
    "build_result_from_runs",
    "build_unmapped_discovery_tasks",
    "empty_adapter_result",
    "end_of_day_shanghai",
    "plan_run_gaps",
    "replan_after_persist",
    "resolve_discovery_scope",
    "run_approved_score",
    "run_evidence_orchestration",
]
