"""Scoped, local-first adapters for supply-chain evidence collection."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date, datetime
from typing import Any, Literal
from zoneinfo import ZoneInfo

from supply_chain_data_collection_center import (
    DocumentFetchError,
    RawDocument,
    sanitize_sensitive_text,
    shanghai_today,
)


EVENT_SOURCE_TYPES = {
    "announcement",
    "announcement_pdf",
    "interactive_qa",
    "research_report",
    "investor_relations_event",
}
STATIC_SOURCE_TYPES = {
    "official_product_page",
    "official_site_page",
    "company_profile",
    "patent",
}
_SHANGHAI = ZoneInfo("Asia/Shanghai")


def normalize_stock_code(value: object) -> str:
    return str(value or "").strip().split(".", 1)[0]


def sanitize_error(exc: Exception) -> str:
    """Return a bounded diagnostic without credentials or bearer tokens."""

    return f"{type(exc).__name__}: {sanitize_sensitive_text(exc)}"


def _parse_date(value: object) -> date | None:
    if isinstance(value, datetime):
        localized = (
            value.replace(tzinfo=_SHANGHAI)
            if value.tzinfo is None
            else value.astimezone(_SHANGHAI)
        )
        return localized.date()
    if isinstance(value, date):
        return value
    text = str(value or "").strip()
    if not text:
        return None
    if len(text) >= 8 and text[:8].isdigit():
        text = f"{text[:4]}-{text[4:6]}-{text[6:8]}"
    try:
        if len(text) <= 10:
            return date.fromisoformat(text[:10])
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        localized = (
            parsed.replace(tzinfo=_SHANGHAI)
            if parsed.tzinfo is None
            else parsed.astimezone(_SHANGHAI)
        )
        return localized.date()
    except ValueError:
        return None


def resolve_collection_window(
    source_type: str, as_of_date: date
) -> tuple[date | None, date]:
    if source_type in EVENT_SOURCE_TYPES:
        return date(as_of_date.year - 3, 1, 1), as_of_date
    if source_type in STATIC_SOURCE_TYPES:
        return None, as_of_date
    raise ValueError(f"unknown source window: {source_type}")


def current_support_status(document: RawDocument, as_of_date: date) -> str:
    metadata = document.metadata or {}
    if document.doc_type == "patent":
        legal_status = str(metadata.get("legal_status") or "").casefold()
        checked = _parse_date(metadata.get("legal_status_date"))
        if legal_status in {"active", "granted"}:
            if checked is None:
                return "pending_review"
            return "current" if checked <= as_of_date else "historical_only"
        if legal_status in {"expired", "revoked", "lapsed", "invalid"}:
            return "historical_only"
        return "pending_review"
    if document.doc_type in {"official_product_page", "official_site_page"}:
        checked = _parse_date(metadata.get("verified_current_date"))
        if (
            metadata.get("currently_offered") is True
            and checked is not None
            and checked <= as_of_date
        ):
            return "current"
        return "pending_review"
    start_date, _ = resolve_collection_window(
        document.doc_type or "announcement", as_of_date
    )
    published = _parse_date(document.publish_time)
    if published is None:
        return "pending_review"
    return (
        "current"
        if (start_date is None or published >= start_date) and published <= as_of_date
        else "historical_only"
    )


@dataclass(frozen=True)
class CollectionTask:
    mapping_id: str
    requirement_id: str
    company_code: str
    company_name: str
    queries: tuple[str, ...]
    product_terms: tuple[str, ...] = ()
    scene_terms: tuple[str, ...] = ()
    negative_examples: tuple[str, ...] = ()
    require_product_and_scene: bool = True


@dataclass(frozen=True)
class UnmappedDiscoveryTask:
    chain_id: str
    requirement_id: str
    product_terms: tuple[str, ...]
    scene_terms: tuple[str, ...]
    negative_examples: tuple[str, ...]
    require_product_and_scene: bool
    seed_company_codes: tuple[str, ...] = ()
    allowed_company_codes: tuple[str, ...] = ()


@dataclass(frozen=True)
class AdapterResult:
    documents: tuple[RawDocument, ...]
    failed_tasks: tuple[str, ...]
    errors: tuple[str, ...]
    status: Literal["success", "partial_success", "empty"]
    network_requests: int = 0


def _status(documents: Sequence[RawDocument], failed: Sequence[str], errors: Sequence[str]):
    if failed or errors:
        return "partial_success"
    return "success" if documents else "empty"


def _dedupe_documents(documents: Sequence[RawDocument]) -> tuple[RawDocument, ...]:
    return tuple({item.doc_id: item for item in documents}.values())


class LocalEvidenceAdapter:
    def __init__(self, repository):
        self.repository = repository

    def collect(self, tasks: list[CollectionTask], *, as_of_date: date) -> AdapterResult:
        documents: list[RawDocument] = []
        failed: list[str] = []
        errors: list[str] = []
        for task in tasks:
            task_key = f"{task.mapping_id}:{task.requirement_id}"
            try:
                payload = self.repository.fetch_local_documents(task, as_of_date)
                if isinstance(payload, AdapterResult):
                    documents.extend(payload.documents)
                    failed.extend(payload.failed_tasks)
                    errors.extend(payload.errors)
                elif (
                    isinstance(payload, tuple)
                    and len(payload) == 2
                    and isinstance(payload[1], (tuple, list))
                    and all(isinstance(item, str) for item in payload[1])
                ):
                    documents.extend(payload[0])
                    errors.extend(payload[1])
                else:
                    documents.extend(payload or ())
            except Exception as exc:  # adapter boundary: partial failure is data
                failed.append(task_key)
                errors.append(sanitize_error(exc))
        deduplicated = _dedupe_documents(documents)
        return AdapterResult(
            deduplicated,
            tuple(dict.fromkeys(failed)),
            tuple(errors),
            _status(deduplicated, failed, errors),
        )


def _metadata_dict(value: object) -> dict[str, Any]:
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, item in value.items():
            if isinstance(item, Mapping):
                result[str(key)] = _metadata_dict(item)
            elif isinstance(item, (tuple, list, set, frozenset)):
                result[str(key)] = [
                    _metadata_dict(part) if isinstance(part, Mapping) else part
                    for part in item
                ]
            else:
                result[str(key)] = item
        return result
    return {}


def _hits(text: str, terms: Sequence[str]) -> list[str]:
    folded = text.casefold()
    return [term for term in terms if term and term.casefold() in folded]


def _annotate_official_document(
    document: RawDocument,
    *,
    product_terms: Sequence[str],
    scene_terms: Sequence[str],
    negative_examples: Sequence[str],
    require_product_and_scene: bool,
    as_of_date: date,
) -> RawDocument:
    text = f"{document.title} {document.content_text}"
    product_hits = _hits(text, product_terms)
    scene_hits = _hits(text, scene_terms)
    excluded_hits = _hits(text, negative_examples)
    metadata = _metadata_dict(document.metadata)
    for reserved in (
        "review_normalization",
        "revenue_confirmed",
        "profit_confirmed",
        "currently_offered",
        "verified_current_date",
        "application_domain",
        "installation_position",
    ):
        metadata.pop(reserved, None)
    eligible = bool(
        product_hits
        and (scene_hits or not require_product_and_scene)
        and not excluded_hits
    )
    explicit_product_scene = bool(product_hits and scene_hits and not excluded_hits)
    metadata.update(
        {
            "product_hits": product_hits,
            "scene_hits": scene_hits,
            "excluded_hits": excluded_hits,
            "same_document_match": eligible,
        }
    )
    if explicit_product_scene:
        metadata["application_domain"] = list(scene_hits)
        metadata["installation_position"] = list(scene_hits)
    if document.doc_type in {"official_product_page", "official_site_page"} and eligible:
        metadata["currently_offered"] = True
        metadata["verified_current_date"] = as_of_date.isoformat()
    return replace(document, metadata=metadata)


class OfficialGapAdapter:
    def __init__(self, fetcher):
        self.fetcher = fetcher

    def collect(
        self,
        tasks: list[CollectionTask],
        *,
        as_of_date: date,
        source_limits: Mapping[str, int],
    ) -> AdapterResult:
        documents: list[RawDocument] = []
        failed: list[str] = []
        errors: list[str] = []
        requests = 0
        task_limit = int(source_limits.get("mapped_official_tasks", 100))
        if len(tasks) > task_limit:
            errors.append(f"source_limit_skipped_tasks:{len(tasks) - task_limit}")
        for task in tasks[:task_limit]:
            try:
                fetched, request_count = self.fetcher.fetch(
                    task,
                    as_of_date=as_of_date,
                    document_limit=int(
                        source_limits.get("mapped_cninfo_documents_per_task", 20)
                    ),
                    pages_per_company=int(
                        source_limits.get("official_pages_per_company", 2)
                    ),
                )
                documents.extend(fetched)
                requests += int(request_count)
            except Exception as exc:
                documents.extend(getattr(exc, "documents", ()) or ())
                requests += int(getattr(exc, "request_count", 0) or 0)
                failed.append(f"{task.mapping_id}:{task.requirement_id}")
                errors.append(sanitize_error(exc))
        deduplicated = _dedupe_documents(documents)
        return AdapterResult(
            deduplicated,
            tuple(failed),
            tuple(errors),
            _status(deduplicated, failed, errors),
            requests,
        )


class OfficialDiscoveryAdapter:
    def __init__(self, fetcher):
        self.fetcher = fetcher

    def collect(
        self,
        tasks: list[UnmappedDiscoveryTask],
        *,
        as_of_date: date,
        source_limits: Mapping[str, int],
    ) -> AdapterResult:
        documents: list[RawDocument] = []
        failed: list[str] = []
        errors: list[str] = []
        requests = 0
        for task in tasks:
            try:
                fetched, request_count = self.fetcher.fetch_unmapped(
                    task,
                    as_of_date=as_of_date,
                    document_limit=int(
                        source_limits.get("official_discovery_documents", 50)
                    ),
                    company_limit=int(
                        source_limits.get("official_discovery_companies", 20)
                    ),
                    pages_per_company=int(
                        source_limits.get("official_pages_per_company", 2)
                    ),
                )
                documents.extend(fetched)
                requests += int(request_count)
            except Exception as exc:
                documents.extend(getattr(exc, "documents", ()) or ())
                requests += int(getattr(exc, "request_count", 0) or 0)
                failed.append(f"{task.chain_id}:{task.requirement_id}")
                errors.append(sanitize_error(exc))
        deduplicated = _dedupe_documents(documents)
        return AdapterResult(
            deduplicated,
            tuple(failed),
            tuple(errors),
            _status(deduplicated, failed, errors),
            requests,
        )


class ScopedOfficialFetcher:
    def __init__(self, *, cninfo_fetch, ir_fetch):
        self.cninfo_fetch = cninfo_fetch
        self.ir_fetch = ir_fetch

    def fetch(
        self,
        task: CollectionTask,
        *,
        as_of_date: date,
        document_limit: int,
        pages_per_company: int,
    ) -> tuple[list[RawDocument], int]:
        event_start, _ = resolve_collection_window("announcement", as_of_date)
        product_start, _ = resolve_collection_window("official_product_page", as_of_date)
        try:
            cninfo_documents, cninfo_requests = self.cninfo_fetch(
                company_codes=(task.company_code,),
                as_of_date=as_of_date,
                start_date=event_start,
                limit=document_limit,
            )
        except Exception:
            raise
        cninfo_documents = list(cninfo_documents)[:document_limit]
        try:
            ir_documents, ir_requests = self.ir_fetch(
                company_codes=(task.company_code,),
                as_of_date=as_of_date,
                start_date=product_start,
                pages_per_company=pages_per_company,
            )
        except Exception as exc:
            raise DocumentFetchError(
                exc,
                request_count=int(cninfo_requests)
                + int(getattr(exc, "request_count", 0) or 0),
                documents=[
                    *cninfo_documents,
                    *(getattr(exc, "documents", ()) or ()),
                ],
                failed_count=int(getattr(exc, "failed_count", 1) or 1),
                skipped_count=int(getattr(exc, "skipped_count", 0) or 0),
            ) from exc
        queries = tuple(query.casefold() for query in task.queries if query)
        filtered: list[RawDocument] = []
        for item in [*cninfo_documents, *ir_documents]:
            text = f"{item.title} {item.content_text}".casefold()
            if normalize_stock_code(item.company_code) != normalize_stock_code(
                task.company_code
            ):
                continue
            if queries and not any(query in text for query in queries):
                continue
            filtered.append(
                _annotate_official_document(
                    item,
                    product_terms=task.product_terms,
                    scene_terms=task.scene_terms,
                    negative_examples=task.negative_examples,
                    require_product_and_scene=task.require_product_and_scene,
                    as_of_date=as_of_date,
                )
            )
        return list(_dedupe_documents(filtered)), int(cninfo_requests) + int(ir_requests)


class ScopedOfficialDiscoveryFetcher:
    def __init__(self, *, global_cninfo_fetch, ir_fetch):
        self.global_cninfo_fetch = global_cninfo_fetch
        self.ir_fetch = ir_fetch

    def fetch_unmapped(
        self,
        task: UnmappedDiscoveryTask,
        *,
        as_of_date: date,
        document_limit: int,
        company_limit: int,
        pages_per_company: int,
    ) -> tuple[list[RawDocument], int]:
        documents, requests = self.global_cninfo_fetch(
            product_terms=task.product_terms,
            scene_terms=task.scene_terms,
            require_product_and_scene=task.require_product_and_scene,
            allowed_company_codes=task.allowed_company_codes,
            as_of_date=as_of_date,
            limit=document_limit,
        )
        documents = list(documents)[:document_limit]
        allowed = {
            normalize_stock_code(code) for code in task.allowed_company_codes if code
        }
        if allowed:
            documents = [
                item
                for item in documents
                if normalize_stock_code(item.company_code) in allowed
            ]
        seeds = [
            code
            for code in task.seed_company_codes
            if not allowed or normalize_stock_code(code) in allowed
        ][:company_limit]
        if seeds:
            try:
                ir_documents, ir_requests = self.ir_fetch(
                    company_codes=tuple(seeds),
                    start_date=None,
                    as_of_date=as_of_date,
                    pages_per_company=pages_per_company,
                )
            except Exception as exc:
                raise DocumentFetchError(
                    exc,
                    request_count=int(requests)
                    + int(getattr(exc, "request_count", 0) or 0),
                    documents=[
                        *documents,
                        *(getattr(exc, "documents", ()) or ()),
                    ],
                    failed_count=int(getattr(exc, "failed_count", 1) or 1),
                    skipped_count=int(getattr(exc, "skipped_count", 0) or 0),
                ) from exc
            documents.extend(ir_documents)
            requests += int(ir_requests)
        annotated = [
            _annotate_official_document(
                item,
                product_terms=task.product_terms,
                scene_terms=task.scene_terms,
                negative_examples=task.negative_examples,
                require_product_and_scene=task.require_product_and_scene,
                as_of_date=as_of_date,
            )
            for item in documents
        ]
        return list(_dedupe_documents(annotated)), int(requests)


def collect_local_then_official(
    tasks: Sequence[CollectionTask],
    *,
    local,
    official,
    as_of_date: date | None = None,
    source_limits: Mapping[str, int] | None = None,
) -> AdapterResult:
    """Collect each explicit mapping locally and send only misses to official sources."""

    cutoff = as_of_date or shanghai_today()
    documents: list[RawDocument] = []
    failed: list[str] = []
    errors: list[str] = []
    misses: list[CollectionTask] = []
    requests = 0
    for task in tasks:
        result = local.collect([task], as_of_date=cutoff)
        documents.extend(result.documents)
        failed.extend(result.failed_tasks)
        errors.extend(result.errors)
        if not result.documents:
            misses.append(task)
    if misses:
        result = official.collect(
            misses,
            as_of_date=cutoff,
            source_limits=source_limits or {},
        )
        documents.extend(result.documents)
        failed.extend(result.failed_tasks)
        errors.extend(result.errors)
        requests += result.network_requests
    deduplicated = _dedupe_documents(documents)
    return AdapterResult(
        deduplicated,
        tuple(dict.fromkeys(failed)),
        tuple(errors),
        _status(deduplicated, failed, errors),
        requests,
    )


def persist_adapter_result(
    result: AdapterResult,
    *,
    repository,
    task: CollectionTask,
    job_id: str,
    as_of_date: date,
) -> tuple[Any, ...]:
    """Persist documents for one explicit task while retaining history safely."""

    outcomes: list[Any] = []
    for document in result.documents:
        support_status = current_support_status(document, as_of_date)
        metadata = _metadata_dict(document.metadata)
        metadata["current_support_status"] = support_status
        prepared = replace(document, metadata=metadata)
        if support_status == "historical_only":
            outcomes.append(
                repository.persist_raw_document(prepared, job_id=job_id)
            )
            continue
        outcomes.append(
            repository.persist_pending_document(
                document=prepared,
                mapping_id=task.mapping_id,
                requirement_id=task.requirement_id,
                job_id=job_id,
                as_of_date=as_of_date,
            )
        )
    return tuple(outcomes)
