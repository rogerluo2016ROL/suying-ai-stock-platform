"""PostgreSQL boundary for supply-chain evidence orchestration."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, time, timedelta
import hashlib
import json
import os
import re
from typing import Any, Callable
from zoneinfo import ZoneInfo

from psycopg2.extras import RealDictCursor

from kronos_factors.engine.industry_chain_templates import (
    get_business_evidence_requirement,
    get_industry_template,
)
from kronos_factors.engine.supply_chain_evidence_orchestration import (
    CandidateMappingProposal,
    EvidenceGap,
)


def connect():
    import psycopg2

    return psycopg2.connect(
        os.environ.get(
            "KRONOS_PG_URL",
            "postgresql://kronos:kronos@localhost:6432/kronos",
        ),
        connect_timeout=5,
    )


def thaw_json(value: Any) -> Any:
    """Turn deeply frozen Task-5 values into ordinary JSON containers."""

    if isinstance(value, Mapping):
        return {str(key): thaw_json(item) for key, item in value.items()}
    if isinstance(value, (tuple, list, set, frozenset)):
        return [thaw_json(item) for item in value]
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def _json(value: Any) -> str:
    return json.dumps(thaw_json(value), ensure_ascii=False, sort_keys=True)


def _json_value(value: Any, default: Any) -> Any:
    if value is None:
        return thaw_json(default)
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return thaw_json(default)
    return thaw_json(value)


def _normalize_text(value: object) -> str:
    return " ".join(str(value or "").replace("\u3000", " ").split())


def _stable_id(prefix: str, *parts: object) -> str:
    payload = "\x1f".join(_normalize_text(part) for part in parts).encode("utf-8")
    return f"{prefix}-" + hashlib.sha256(payload).hexdigest()[:24]


def _row(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    return dict(value) if isinstance(value, Mapping) else None


def _mapping_status(existing: str, incoming: str) -> str:
    rank = {
        "candidate": 1,
        "weak_evidence": 2,
        "pending_review": 3,
        "verified": 4,
        "rejected": 4,
    }
    return existing if rank.get(existing, 0) >= rank.get(incoming, 0) else incoming


def _merge_ids(*values: object) -> list[str]:
    result: list[str] = []
    for value in values:
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
            for item in value:
                text = str(item or "").strip()
                if text and text not in result:
                    result.append(text)
    return result


def _merge_candidate_proposals_by_mapping(
    proposals: Sequence[CandidateMappingProposal],
) -> list[CandidateMappingProposal]:
    """Merge lineage for one structural mapping, failing closed on conflicts."""

    grouped: dict[str, CandidateMappingProposal] = {}
    structural_fields = (
        "company_code",
        "chain_id",
        "node_id",
        "tag_name",
        "technology_route_id",
    )
    lineage_fields = (
        "discovery_doc_ids",
        "discovery_fact_ids",
        "collection_job_ids",
    )
    for proposal in proposals:
        current = grouped.get(proposal.mapping_id)
        if current is None:
            grouped[proposal.mapping_id] = proposal
            continue
        conflicts = [
            field
            for field in structural_fields
            if getattr(current, field) != getattr(proposal, field)
        ]
        current_provenance = thaw_json(current.provenance or {})
        incoming_provenance = thaw_json(proposal.provenance or {})
        for field in ("requirement_id", "technology_route_id"):
            left = current_provenance.get(field)
            right = incoming_provenance.get(field)
            if left and right and left != right:
                conflicts.append(f"provenance.{field}")
        if conflicts:
            raise ValueError(
                f"candidate proposal conflict for {proposal.mapping_id}: "
                + ", ".join(conflicts)
            )
        merged_provenance = dict(current_provenance)
        for field in lineage_fields:
            merged_provenance[field] = _merge_ids(
                current_provenance.get(field), incoming_provenance.get(field)
            )
        current_path = _json_value(current_provenance.get("l1_l8_path"), {})
        incoming_path = _json_value(incoming_provenance.get("l1_l8_path"), {})
        merged_path = dict(current_path)
        for field in ("requirement_id", "technology_route_id"):
            left = current_path.get(field)
            right = incoming_path.get(field)
            if left and right and left != right:
                raise ValueError(
                    f"candidate proposal conflict for {proposal.mapping_id}: "
                    f"l1_l8_path.{field}"
                )
            if not left and right:
                merged_path[field] = right
        for field in lineage_fields:
            merged_path[field] = _merge_ids(
                current_path.get(field), incoming_path.get(field)
            )
        if merged_path:
            merged_provenance["l1_l8_path"] = merged_path
        grouped[proposal.mapping_id] = replace(
            current,
            confidence=max(current.confidence, proposal.confidence),
            evidence_ids=tuple(_merge_ids(current.evidence_ids, proposal.evidence_ids)),
            provenance=merged_provenance,
        )
    return list(grouped.values())


def _fact_type(requirement_id: str) -> str:
    return {
        "business_presence": "business_presence",
        "product_or_prototype": "product_spec",
        "customer_validation": "customer_validation",
        "order_or_delivery": "order_award",
        "recognized_revenue": "revenue_margin",
        "recognized_profit": "revenue_margin",
    }.get(requirement_id, "product_spec")


def _sanitize_fact_metadata(metadata: object) -> dict[str, Any]:
    clean = thaw_json(metadata) if isinstance(metadata, Mapping) else {}
    for key in (
        "review_normalization",
        "revenue_confirmed",
        "profit_confirmed",
    ):
        clean.pop(key, None)
    return clean


def _sanitize_error_text(value: object) -> str:
    message = str(value or "")[:4000]
    message = re.sub(
        r"(?i)([a-z][a-z0-9+.-]*://)[^/@\s]+:[^/@\s]+@",
        r"\1<redacted>@",
        message,
    )
    pattern = re.compile(
        r"(?i)(?P<prefix>[\"']?(?:authorization|cookie|x-api-key|api[_-]?key|"
        r"token|password|passwd|secret|client_secret)[\"']?\s*[:=]\s*)"
        r"(?P<value>\"[^\"]*\"|'[^']*'|(?:bearer\s+)?[^,;\}\]\n&]+)"
    )
    message = pattern.sub(
        lambda match: f"{match.group('prefix')}<redacted>", message
    )
    message = re.sub(
        r"(?i)(bearer)\s+(?:\"[^\"]*\"|'[^']*'|[^\s,;\}\]&]+)",
        r"\1 <redacted>",
        message,
    )
    return message[:500]


_SHANGHAI = ZoneInfo("Asia/Shanghai")


def _as_of_aware_upper_bound(value: date | datetime) -> datetime:
    if isinstance(value, datetime):
        return (
            value.replace(tzinfo=_SHANGHAI)
            if value.tzinfo is None
            else value.astimezone(_SHANGHAI)
        )
    if isinstance(value, date):
        return datetime.combine(
            value + timedelta(days=1), time.min, tzinfo=_SHANGHAI
        )
    raise ValueError("as_of cutoff must be a date or datetime")


def _as_of_upper_bound(value: date | datetime) -> datetime:
    """Return a Shanghai wall-clock cutoff for TIMESTAMP WITHOUT TIME ZONE."""

    return _as_of_aware_upper_bound(value).replace(tzinfo=None)


def _as_of_audit_upper_bound(value: date | datetime) -> datetime:
    """Return a UTC wall-clock cutoff for DB-generated audit TIMESTAMP columns."""

    return _as_of_aware_upper_bound(value).astimezone(UTC).replace(tzinfo=None)


def _shanghai_date(value: object) -> date | None:
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


@dataclass(frozen=True)
class PendingDocumentOutcome:
    doc_id: str
    fact_id: str
    event_id: str | None
    mapping_id: str
    requirement_id: str
    validation_status: str
    review_status: str
    fact_metadata: dict[str, Any]


@dataclass(frozen=True)
class DiscoveryPersistenceOutcome:
    doc_id: str
    fact_id: str
    fact_mapping_id: None
    validation_status: str
    proposal: CandidateMappingProposal | None


@dataclass(frozen=True)
class MappingRecord:
    mapping_id: str
    company_code: str
    business_segment_id: str | None
    node_id: str | None
    theme_id: str | None
    chain_id: str
    tag_name: str
    status: str
    confidence: float
    evidence_ids: tuple[str, ...]
    provenance: dict[str, Any]


class EvidenceOrchestrationRepository:
    """Explicit-mapping repository; company codes are never used to infer mappings."""

    LOCAL_SOURCE_BY_TABLE = {
        "announcements": "cninfo_announcement",
        "ts_raw_anns_d": "cninfo_announcement",
        "interact_qa": "exchange_interact_qa",
        "research_reports_tushare": "broker_expectation_local",
        "patent_events": "patent_public_platform",
        "stock_profiles": "local_stock_profile",
        "fina_mainbz": "local_business_segment",
        "raw_evidence_documents": None,
    }
    SOURCE_CATALOG = {
        "cninfo_announcement": ("巨潮/交易所公告全文", "announcement", "strong", True),
        "exchange_interact_qa": ("互动易/上证e互动", "interact_qa", "mid", True),
        "broker_expectation_local": ("本地研报/盈利预测表", "broker_report", "mid", False),
        "patent_public_platform": ("国家知识产权/专利平台", "patent", "strong", True),
        "local_stock_profile": ("本地公司档案", "company_profile", "mid", False),
        "local_business_segment": ("本地主营业务构成", "business_segment", "strong", False),
    }

    def __init__(self, connection_factory: Callable[[], Any] = connect):
        self.connection_factory = connection_factory
        self.unresolved_technology_routes: list[str] = []

    @contextmanager
    def _cursor(self, *, write: bool, connection: Any | None = None):
        owned = connection is None
        active_connection = connection or self.connection_factory()
        try:
            try:
                cursor = active_connection.cursor(cursor_factory=RealDictCursor)
            except TypeError:
                cursor = active_connection.cursor()
            manager = cursor if hasattr(cursor, "__enter__") else None
            active = manager.__enter__() if manager is not None else cursor
            try:
                yield active
                if write and owned:
                    active_connection.commit()
            except Exception:
                rollback = getattr(active_connection, "rollback", None)
                if owned and callable(rollback):
                    rollback()
                raise
            finally:
                if manager is not None:
                    manager.__exit__(None, None, None)
                else:
                    close_cursor = getattr(cursor, "close", None)
                    if callable(close_cursor):
                        close_cursor()
        finally:
            close = getattr(active_connection, "close", None)
            if owned and callable(close):
                close()

    @classmethod
    def _ensure_source_catalog(
        cls, cur, source_id: str, source_level: str, metadata: Mapping[str, Any]
    ) -> None:
        name, source_type, configured_level, is_official = cls.SOURCE_CATALOG.get(
            source_id,
            (source_id, str(metadata.get("origin_table") or "local_document"), source_level, False),
        )
        level = configured_level if configured_level in {"strong", "mid", "weak"} else source_level
        reliability = {"strong": 0.9, "mid": 0.7, "weak": 0.4}.get(level, 0.4)
        confidence_cap = {"strong": 0.95, "mid": 0.75, "weak": 0.45}.get(level, 0.45)
        cur.execute(
            """
            INSERT INTO evidence_source_catalog (
                source_id, source_name, source_type, source_level,
                source_reliability_score, confidence_cap, is_official,
                is_third_party_estimate, is_market_sentiment,
                requires_cross_validation, license_status, update_frequency,
                crawl_method, enabled, metadata
            ) VALUES (
                %s, %s, %s, %s,
                %s, %s, %s,
                FALSE, FALSE,
                %s, 'available', 'local',
                'existing_table', TRUE, %s::jsonb
            )
            ON CONFLICT (source_id) DO NOTHING
            """,
            (
                source_id,
                name,
                source_type,
                level,
                reliability,
                confidence_cap,
                is_official,
                level != "strong",
                _json({"origin_table": metadata.get("origin_table")}),
            ),
        )

    @classmethod
    def _insert_raw_document(cls, cur, document, metadata: dict[str, Any]) -> None:
        cls._ensure_source_catalog(
            cur, str(document.source_id), str(document.source_level), metadata
        )
        cur.execute(
            """
            INSERT INTO raw_evidence_documents (
                doc_id, source_id, source_type, source_level, company_code,
                company_name, title, publish_time, url, content_text,
                content_hash, doc_status, license_status, doc_type, metadata
            ) VALUES (
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s, 'active', 'unknown', %s, %s::jsonb
            )
            ON CONFLICT (doc_id) DO UPDATE SET
                company_code = COALESCE(raw_evidence_documents.company_code, EXCLUDED.company_code),
                company_name = COALESCE(raw_evidence_documents.company_name, EXCLUDED.company_name),
                publish_time = COALESCE(raw_evidence_documents.publish_time, EXCLUDED.publish_time),
                metadata = EXCLUDED.metadata || raw_evidence_documents.metadata,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                document.doc_id,
                document.source_id,
                document.doc_type or document.source_id,
                document.source_level,
                document.company_code,
                document.company_name,
                document.title,
                document.publish_time,
                document.url,
                document.content_text,
                document.content_hash,
                document.doc_type,
                _json(metadata),
            ),
        )

    def persist_pending_document(
        self,
        *,
        document,
        mapping_id: str,
        requirement_id: str,
        job_id: str,
        as_of_date: date,
        connection: Any | None = None,
    ) -> PendingDocumentOutcome:
        if not mapping_id or not requirement_id:
            raise ValueError("mapping_id and requirement_id are required")
        raw_metadata = thaw_json(document.metadata or {})
        fact_metadata = _sanitize_fact_metadata(raw_metadata)
        fact_metadata["collection_job_id"] = job_id
        # Collection bookkeeping is not source metadata and should not leak into
        # the public round-trip view returned to callers.
        returned_metadata = {
            key: value for key, value in fact_metadata.items() if key != "collection_job_id"
        }
        quote = _normalize_text(document.content_text)[:500]
        publish_date = str(document.publish_time or "")[:10]
        fact_id = _stable_id(
            "FACT",
            document.doc_id,
            mapping_id,
            requirement_id,
            publish_date,
            quote,
        )
        event_id = _stable_id("EV", fact_id, mapping_id)
        confidence = {"strong": 0.8, "mid": 0.6, "weak": 0.35}.get(
            str(document.source_level), 0.0
        )
        with self._cursor(write=True, connection=connection) as cur:
            self._insert_raw_document(cur, document, raw_metadata)
            cur.execute(
                """
                INSERT INTO business_tag_evidence_events (
                    event_id, mapping_id, code, event_date, source_type,
                    source_id, title, excerpt, original_url, evidence_type,
                    impact_dimensions, confidence, review_status, review_note
                ) VALUES (
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    '[]'::jsonb, %s, 'pending_review', NULL
                )
                ON CONFLICT (event_id) DO UPDATE SET
                    title = EXCLUDED.title,
                    excerpt = EXCLUDED.excerpt,
                    original_url = COALESCE(business_tag_evidence_events.original_url, EXCLUDED.original_url)
                """,
                (
                    event_id,
                    mapping_id,
                    document.company_code or "",
                    publish_date or None,
                    document.doc_type or document.source_id,
                    document.source_id,
                    document.title,
                    quote,
                    document.url,
                    _fact_type(requirement_id),
                    confidence,
                ),
            )
            cur.execute(
                """
                INSERT INTO evidence_extracted_facts (
                    fact_id, doc_id, mapping_id, company_code, fact_type,
                    fact_nature, original_quote, source_level, confidence,
                    confidence_cap, validation_status, evidence_event_id, metadata
                ) VALUES (
                    %s, %s, %s, %s, %s,
                    'company_claim', %s, %s, %s,
                    %s, 'pending', %s, %s::jsonb
                )
                ON CONFLICT (fact_id) DO UPDATE SET
                    metadata = (EXCLUDED.metadata - 'review_normalization'
                        - 'revenue_confirmed' - 'profit_confirmed')
                        || evidence_extracted_facts.metadata,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    fact_id,
                    document.doc_id,
                    mapping_id,
                    document.company_code or "",
                    _fact_type(requirement_id),
                    quote,
                    document.source_level,
                    confidence,
                    {"strong": 0.95, "mid": 0.75, "weak": 0.45}.get(
                        str(document.source_level), 0.0
                    ),
                    event_id,
                    _json(fact_metadata),
                ),
            )
        return PendingDocumentOutcome(
            doc_id=document.doc_id,
            fact_id=fact_id,
            event_id=event_id,
            mapping_id=mapping_id,
            requirement_id=requirement_id,
            validation_status="pending",
            review_status="pending_review",
            fact_metadata=returned_metadata,
        )

    def persist_discovery_hit(
        self, hit, *, job_id: str, connection: Any | None = None
    ) -> DiscoveryPersistenceOutcome:
        quote = _normalize_text(
            " ".join((*hit.product_hits, *hit.scene_hits, *hit.excluded_hits))
        )
        publish_day = _shanghai_date(hit.publish_time)
        publish_date = publish_day.isoformat() if publish_day else ""
        fact_id = _stable_id(
            "FACT",
            hit.doc_id,
            "unmapped",
            hit.requirement_id,
            publish_date,
            quote,
        )
        proposal_payload = thaw_json(hit.proposal.provenance) if hit.proposal else None
        metadata = {
            "collection_job_id": job_id,
            "collection_job_ids": [job_id],
            "requirement_id": hit.requirement_id,
            "product_hits": list(hit.product_hits),
            "scene_hits": list(hit.scene_hits),
            "excluded_hits": list(hit.excluded_hits),
            "candidate_proposal": {
                "mapping_id": hit.proposal.mapping_id,
                "company_code": hit.proposal.company_code,
                "chain_id": hit.proposal.chain_id,
                "node_id": hit.proposal.node_id,
                "tag_name": hit.proposal.tag_name,
                "technology_route_id": hit.proposal.technology_route_id,
                "status": hit.proposal.status,
                "confidence": hit.proposal.confidence,
                "evidence_ids": list(hit.proposal.evidence_ids),
                "provenance": proposal_payload,
            }
            if hit.proposal
            else None,
        }
        content_hash = hashlib.sha256(str(hit.doc_id).encode("utf-8")).hexdigest()
        with self._cursor(write=True, connection=connection) as cur:
            cur.execute(
                """
                INSERT INTO raw_evidence_documents (
                    doc_id, source_id, source_type, source_level, company_code,
                    title, publish_time, content_text, content_hash, doc_status,
                    license_status, doc_type, metadata
                ) VALUES (
                    %s, NULL, 'official_discovery', %s, %s,
                    %s, %s, %s, %s, 'active',
                    'unknown', 'announcement_pdf', %s::jsonb
                )
                ON CONFLICT (doc_id) DO NOTHING
                """,
                (
                    hit.doc_id,
                    hit.source_level,
                    hit.company_code,
                    f"Discovery evidence {hit.doc_id}",
                    hit.publish_time,
                    quote,
                    content_hash,
                    _json(metadata),
                ),
            )
            cur.execute(
                """
                INSERT INTO evidence_extracted_facts (
                    fact_id, doc_id, mapping_id, company_code, fact_type,
                    fact_nature, original_quote, source_level, confidence,
                    validation_status, evidence_event_id, metadata
                ) VALUES (
                    %s, %s, %s, %s, 'product_spec',
                    'company_claim', %s, %s, %s,
                    'pending', NULL, %s::jsonb
                )
                ON CONFLICT (fact_id) DO UPDATE SET
                    metadata = jsonb_set(
                        (EXCLUDED.metadata - 'collection_job_id' - 'collection_job_ids')
                            || evidence_extracted_facts.metadata,
                        '{collection_job_ids}',
                        COALESCE((
                            SELECT jsonb_agg(job_id ORDER BY job_id)
                            FROM (
                                SELECT DISTINCT job_id
                                FROM jsonb_array_elements_text(
                                    COALESCE(
                                        evidence_extracted_facts.metadata -> 'collection_job_ids',
                                        '[]'::jsonb
                                    )
                                    || CASE
                                        WHEN evidence_extracted_facts.metadata ->> 'collection_job_id' IS NULL
                                        THEN '[]'::jsonb
                                        ELSE jsonb_build_array(
                                            evidence_extracted_facts.metadata ->> 'collection_job_id'
                                        )
                                    END
                                    || COALESCE(
                                        EXCLUDED.metadata -> 'collection_job_ids',
                                        '[]'::jsonb
                                    )
                                ) AS job_id
                            ) AS unique_jobs
                        ), '[]'::jsonb),
                        true
                    ),
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    fact_id,
                    hit.doc_id,
                    None,
                    hit.company_code,
                    quote,
                    hit.source_level,
                    0.35 if hit.source_level == "strong" else 0.3,
                    _json(metadata),
                ),
            )
        return DiscoveryPersistenceOutcome(
            doc_id=hit.doc_id,
            fact_id=fact_id,
            fact_mapping_id=None,
            validation_status="pending",
            proposal=hit.proposal,
        )

    def upsert_candidate_mapping(
        self,
        proposal: CandidateMappingProposal,
        *,
        connection: Any | None = None,
    ) -> MappingRecord:
        incoming = thaw_json(proposal.provenance)
        nested = incoming.get("l1_l8_path")
        if isinstance(nested, Mapping):
            for key, value in nested.items():
                incoming.setdefault(str(key), thaw_json(value))
        incoming.setdefault("technology_route_id", proposal.technology_route_id)
        with self._cursor(write=True, connection=connection) as cur:
            cur.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                (proposal.mapping_id,),
            )
            cur.execute(
                """
                SELECT mapping_id, code, business_segment_id, node_id, theme_id,
                       chain_id, tag_name, l1_l8_path, confidence, status, evidence_ids
                FROM business_tag_mapping
                WHERE mapping_id = %s
                FOR UPDATE
                """,
                (proposal.mapping_id,),
            )
            existing = _row(cur.fetchone()) or {}
            previous = _json_value(existing.get("l1_l8_path"), {})
            if not isinstance(previous, dict):
                previous = {"legacy_l1_l8_path": previous}
            previous_nested = previous.get("l1_l8_path")
            previous_nested = (
                previous_nested if isinstance(previous_nested, Mapping) else {}
            )
            incoming_nested = incoming.get("l1_l8_path")
            incoming_nested = (
                incoming_nested if isinstance(incoming_nested, Mapping) else {}
            )
            merged = dict(previous)
            for key, value in incoming.items():
                if key not in merged or merged[key] in (None, "", [], {}):
                    merged[key] = value
            for key in ("discovery_doc_ids", "discovery_fact_ids"):
                merged[key] = _merge_ids(
                    previous.get(key),
                    previous_nested.get(key),
                    incoming.get(key),
                    incoming_nested.get(key),
                )
            nested_merged = merged.get("l1_l8_path")
            if not isinstance(nested_merged, dict):
                nested_merged = {}
            for key in ("requirement_id", "technology_route_id"):
                if merged.get(key) is not None:
                    nested_merged.setdefault(key, merged[key])
            for key in ("discovery_doc_ids", "discovery_fact_ids"):
                nested_merged[key] = list(merged[key])
            merged["l1_l8_path"] = nested_merged

            status = str(existing.get("status") or proposal.status)
            confidence = max(
                float(existing.get("confidence") or 0.0), float(proposal.confidence)
            )
            existing_evidence = _json_value(existing.get("evidence_ids"), [])
            evidence_ids = tuple(
                str(item)
                for item in (
                    existing_evidence if existing_evidence else proposal.evidence_ids
                )
            )
            company_code = str(existing.get("code") or proposal.company_code)
            business_segment_id = existing.get("business_segment_id")
            node_id = existing.get("node_id") or proposal.node_id
            theme_id = existing.get("theme_id")
            chain_id = str(existing.get("chain_id") or proposal.chain_id)
            tag_name = str(existing.get("tag_name") or proposal.tag_name)
            cur.execute(
                """
                INSERT INTO business_tag_mapping (
                    mapping_id, code, business_segment_id, node_id, theme_id,
                    chain_id, tag_name, l1_l8_path, confidence, status, evidence_ids
                ) VALUES (
                    %s, %s, %s, %s, %s,
                    %s, %s, %s::jsonb, %s, %s, %s::jsonb
                )
                ON CONFLICT (mapping_id) DO UPDATE SET
                    business_segment_id = COALESCE(business_tag_mapping.business_segment_id, EXCLUDED.business_segment_id),
                    node_id = COALESCE(business_tag_mapping.node_id, EXCLUDED.node_id),
                    theme_id = COALESCE(business_tag_mapping.theme_id, EXCLUDED.theme_id),
                    chain_id = COALESCE(business_tag_mapping.chain_id, EXCLUDED.chain_id),
                    l1_l8_path = EXCLUDED.l1_l8_path,
                    confidence = GREATEST(business_tag_mapping.confidence, EXCLUDED.confidence),
                    status = business_tag_mapping.status,
                    evidence_ids = CASE
                        WHEN jsonb_array_length(business_tag_mapping.evidence_ids) > 0
                        THEN business_tag_mapping.evidence_ids
                        ELSE EXCLUDED.evidence_ids
                    END,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    proposal.mapping_id,
                    company_code,
                    business_segment_id,
                    node_id,
                    theme_id,
                    chain_id,
                    tag_name,
                    _json(merged),
                    confidence,
                    status,
                    _json(evidence_ids),
                ),
            )
        return MappingRecord(
            mapping_id=proposal.mapping_id,
            company_code=company_code,
            business_segment_id=business_segment_id,
            node_id=node_id,
            theme_id=theme_id,
            chain_id=chain_id,
            tag_name=tag_name,
            status=status,
            confidence=confidence,
            evidence_ids=evidence_ids,
            provenance=merged,
        )

    def fetch_mappings(
        self,
        chain_id: str,
        mapping_ids: tuple[str, ...],
        company_codes: tuple[str, ...],
        *,
        connection: Any | None = None,
    ) -> list[dict[str, Any]]:
        clauses = ["b.chain_id = %s", "b.status <> 'rejected'"]
        params: list[Any] = [chain_id]
        if mapping_ids:
            clauses.append("b.mapping_id = ANY(%s)")
            params.append(list(mapping_ids))
        if company_codes:
            clauses.append("split_part(b.code, '.', 1) = ANY(%s)")
            params.append([str(code).split(".", 1)[0] for code in company_codes])
        with self._cursor(write=False, connection=connection) as cur:
            cur.execute(
                f"""
                SELECT b.mapping_id, b.code, b.business_segment_id, b.node_id,
                       b.theme_id, b.chain_id, b.tag_name, b.l1_l8_path,
                       b.confidence, b.status, b.evidence_ids
                FROM business_tag_mapping b
                WHERE {' AND '.join(clauses)}
                ORDER BY b.code, b.mapping_id
                """,
                tuple(params),
            )
            rows = [dict(item) for item in cur.fetchall()]

        self.unresolved_technology_routes = []
        result: list[dict[str, Any]] = []
        for row in rows:
            provenance = _json_value(row.get("l1_l8_path"), {})
            if not isinstance(provenance, dict):
                provenance = {}
            nested = provenance.get("l1_l8_path")
            nested = nested if isinstance(nested, dict) else {}
            requirement_id = provenance.get("requirement_id") or nested.get(
                "requirement_id"
            )
            route_key_present = (
                "technology_route_id" in provenance
                or "technology_route_id" in nested
            )
            route_id = (
                provenance.get("technology_route_id")
                if "technology_route_id" in provenance
                else nested.get("technology_route_id")
            )
            try:
                template = get_industry_template(chain_id)
                if requirement_id:
                    matches = [
                        item
                        for item in template.get("evidence_requirements") or []
                        if item.get("requirement_id") == requirement_id
                    ]
                    if len(matches) != 1:
                        raise ValueError("requirement must resolve once")
                    requirement = matches[0]
                else:
                    requirement = get_business_evidence_requirement(
                        template, str(row.get("tag_name") or "")
                    )
                requirement_id = requirement.get("requirement_id")
                expected_route = requirement.get("technology_route_id")
                if expected_route:
                    if route_key_present and route_id != expected_route:
                        raise ValueError("stored technology route is unresolved")
                    route_id = expected_route
                elif route_key_present and route_id not in (None, ""):
                    raise ValueError("unexpected technology route")
                else:
                    route_id = None
            except (KeyError, ValueError):
                self.unresolved_technology_routes.append(str(row["mapping_id"]))
                continue
            enriched = dict(row)
            enriched["l1_l8_path"] = provenance
            enriched["requirement_id"] = requirement_id
            enriched["technology_route_id"] = route_id
            result.append(enriched)
        return result

    def start_job(self, request, *, connection: Any | None = None) -> str:
        limits = thaw_json(request.source_limits)
        request_payload = {
            "chain_id": request.chain_id,
            "as_of_date": request.as_of_date.isoformat(),
            "mode": request.mode,
            "source_policy": request.source_policy,
            "mapping_ids": list(request.mapping_ids),
            "company_codes": list(request.company_codes),
            "source_limits": limits,
            "allow_score": request.allow_score,
        }
        job_id = _stable_id("JOB", _json(request_payload))
        with self._cursor(write=True, connection=connection) as cur:
            cur.execute(
                """
                INSERT INTO evidence_collection_jobs (
                    job_id, source_id, job_type, scope_type, scope_payload,
                    status, started_at, metadata
                ) VALUES (
                    %s, NULL, %s, 'supply_chain', %s::jsonb,
                    'running', CURRENT_TIMESTAMP, %s::jsonb
                )
                ON CONFLICT (job_id) DO UPDATE SET
                    status = 'running',
                    started_at = CURRENT_TIMESTAMP,
                    finished_at = NULL,
                    error_message = NULL,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    job_id,
                    "dry_run" if request.mode == "dry-run" else "manual",
                    _json(request_payload),
                    _json({"source_limits": limits}),
                ),
            )
        return job_id

    def finish_job(
        self, job_id: str, result: Any, *, connection: Any | None = None
    ) -> None:
        status = str(
            result.get("status") if isinstance(result, Mapping) else result.status
        )
        if status == "empty":
            status = "success"
        documents = (
            result.get("documents", ()) if isinstance(result, Mapping) else result.documents
        )
        failed = (
            result.get("failed_tasks", ())
            if isinstance(result, Mapping)
            else result.failed_tasks
        )
        errors = (
            result.get("errors", ()) if isinstance(result, Mapping) else result.errors
        )
        sanitized = "; ".join(_sanitize_error_text(value) for value in errors) or None
        with self._cursor(write=True, connection=connection) as cur:
            cur.execute(
                """
                UPDATE evidence_collection_jobs
                SET status = %s,
                    finished_at = CURRENT_TIMESTAMP,
                    fetched_count = %s,
                    inserted_count = %s,
                    failed_count = %s,
                    error_message = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE job_id = %s
                """,
                (
                    status,
                    len(documents),
                    len(documents),
                    len(failed),
                    sanitized,
                    job_id,
                ),
            )

    def persist_raw_document(
        self, document, *, job_id: str, connection: Any | None = None
    ) -> str:
        metadata = thaw_json(document.metadata or {})
        metadata["collection_job_id"] = job_id
        with self._cursor(write=True, connection=connection) as cur:
            self._insert_raw_document(cur, document, metadata)
        return document.doc_id

    def fetch_independent_discovery_requirements(
        self, chain_id: str, *, connection: Any | None = None
    ) -> list[dict[str, Any]]:
        del connection
        template = get_industry_template(chain_id)
        return [
            thaw_json(requirement)
            for requirement in template.get("evidence_requirements") or []
            if requirement.get("independent_discovery") is True
        ]

    def fetch_candidate_universe(
        self,
        as_of_date: date | datetime,
        requirement: Mapping[str, Any],
        company_codes: tuple[str, ...],
        limit: int,
        *,
        connection: Any | None = None,
    ) -> list[dict[str, Any]]:
        if limit <= 0:
            return []
        source_wall_cutoff = _as_of_upper_bound(as_of_date)
        audit_utc_cutoff = _as_of_audit_upper_bound(as_of_date)
        cutoff_day = _shanghai_date(as_of_date)
        if cutoff_day is None:
            raise ValueError("as_of cutoff must resolve to a Shanghai date")
        clauses = [
            "publish_time IS NOT NULL",
            "publish_time < %s",
            "created_at < %s",
        ]
        params: list[Any] = [source_wall_cutoff, audit_utc_cutoff]
        if company_codes:
            clauses.append("split_part(company_code, '.', 1) = ANY(%s)")
            params.append([str(code).split(".", 1)[0] for code in company_codes])
        params.append(max(limit * 5, limit))
        with self._cursor(write=False, connection=connection) as cur:
            cur.execute(
                f"""
                SELECT doc_id, company_code, source_level, title, content_text,
                       publish_time, created_at, metadata
                FROM raw_evidence_documents
                WHERE {' AND '.join(clauses)}
                ORDER BY publish_time DESC, doc_id
                LIMIT %s
                """,
                tuple(params),
            )
            rows = [dict(row) for row in cur.fetchall()]
        products = tuple(requirement.get("product_terms") or ())
        scenes = tuple(requirement.get("scene_terms") or ())
        negatives = tuple(requirement.get("negative_examples") or ())
        require_scene = requirement.get("require_product_and_scene", True) is True
        selected: list[dict[str, Any]] = []
        for row in rows:
            published_date = _shanghai_date(row.get("publish_time"))
            if published_date is None or published_date > cutoff_day:
                continue
            text = f"{row.get('title') or ''} {row.get('content_text') or ''}".casefold()
            product_hits = [term for term in products if str(term).casefold() in text]
            scene_hits = [term for term in scenes if str(term).casefold() in text]
            excluded_hits = [term for term in negatives if str(term).casefold() in text]
            if not product_hits or (require_scene and not scene_hits) or excluded_hits:
                continue
            record = dict(row)
            record["metadata"] = _json_value(row.get("metadata"), {})
            selected.append(record)
            if len(selected) >= limit:
                break
        return selected

    def fetch_discovery_seed_companies(
        self,
        as_of_date: date,
        requirement: Mapping[str, Any],
        limit: int,
        *,
        connection: Any | None = None,
    ) -> list[str]:
        terms = _merge_ids(
            requirement.get("business_keywords"),
            requirement.get("product_terms"),
        )
        if not terms or limit <= 0:
            return []
        probes = [f"%{term}%" for term in terms]
        audit_utc_cutoff = _as_of_audit_upper_bound(as_of_date)
        with self._cursor(write=False, connection=connection) as cur:
            cur.execute(
                """
                SELECT code
                FROM stock_profiles
                WHERE concat_ws(' ', main_business, business_scope, introduction)
                      ILIKE ANY(%s)
                  AND updated_at IS NOT NULL
                  AND updated_at < %s
                ORDER BY code
                LIMIT %s
                """,
                (probes, audit_utc_cutoff, limit),
            )
            rows = cur.fetchall()
        return list(
            dict.fromkeys(
                str(dict(row).get("code") or "").split(".", 1)[0]
                for row in rows
                if str(dict(row).get("code") or "").strip()
            )
        )

    def list_candidate_proposals(
        self, job_id: str, *, connection: Any | None = None
    ) -> list[CandidateMappingProposal]:
        with self._cursor(write=False, connection=connection) as cur:
            cur.execute(
                """
                SELECT metadata
                FROM evidence_extracted_facts
                WHERE mapping_id IS NULL
                  AND (
                      metadata -> 'collection_job_ids' ? %s
                      OR metadata ->> 'collection_job_id' = %s
                  )
                  AND metadata ? 'candidate_proposal'
                ORDER BY fact_id
                """,
                (job_id, job_id),
            )
            rows = cur.fetchall()
        proposals: list[CandidateMappingProposal] = []
        for row in rows:
            metadata = _json_value(dict(row).get("metadata"), {})
            payload = metadata.get("candidate_proposal") if isinstance(metadata, dict) else None
            if not isinstance(payload, dict) or not payload.get("mapping_id"):
                continue
            mapping_id = str(payload["mapping_id"])
            provenance = _json_value(payload.get("provenance"), {})
            job_ids = _merge_ids(
                provenance.get("collection_job_ids"),
                metadata.get("collection_job_ids"),
                (metadata.get("collection_job_id"),),
            )
            provenance["collection_job_ids"] = job_ids
            path = _json_value(provenance.get("l1_l8_path"), {})
            path["collection_job_ids"] = _merge_ids(
                path.get("collection_job_ids"), job_ids
            )
            provenance["l1_l8_path"] = path
            proposals.append(
                CandidateMappingProposal(
                    mapping_id=mapping_id,
                    company_code=str(payload.get("company_code") or ""),
                    chain_id=str(payload.get("chain_id") or ""),
                    node_id=str(payload.get("node_id") or ""),
                    tag_name=str(payload.get("tag_name") or ""),
                    technology_route_id=payload.get("technology_route_id"),
                    status="candidate",
                    confidence=float(payload.get("confidence") or 0.0),
                    evidence_ids=tuple(payload.get("evidence_ids") or ()),
                    provenance=provenance,
                )
            )
        return _merge_candidate_proposals_by_mapping(proposals)

    def fetch_asof_facts(
        self,
        mapping_ids: tuple[str, ...],
        cutoff: date | datetime,
        *,
        connection: Any | None = None,
    ) -> list[dict[str, Any]]:
        if not mapping_ids:
            return []
        source_wall_cutoff = _as_of_upper_bound(cutoff)
        audit_utc_cutoff = _as_of_audit_upper_bound(cutoff)
        aware_cutoff = _as_of_aware_upper_bound(cutoff)
        with self._cursor(write=False, connection=connection) as cur:
            cur.execute(
                """
                SELECT f.*, d.publish_time, d.title, d.url
                FROM evidence_extracted_facts f
                JOIN raw_evidence_documents d ON d.doc_id = f.doc_id
                WHERE f.mapping_id = ANY(%s)
                  AND d.publish_time IS NOT NULL
                  AND d.publish_time < %s
                  AND f.created_at < %s
                  AND (f.reviewed_at IS NULL OR f.reviewed_at < %s)
                ORDER BY d.publish_time, f.fact_id
                """,
                (
                    list(mapping_ids),
                    source_wall_cutoff,
                    audit_utc_cutoff,
                    aware_cutoff,
                ),
            )
            rows = [dict(row) for row in cur.fetchall()]
        for row in rows:
            row["metadata"] = _json_value(row.get("metadata"), {})
        return rows

    def fetch_gap_rows(
        self, mapping_ids: tuple[str, ...], *, connection: Any | None = None
    ) -> list[EvidenceGap]:
        if not mapping_ids:
            return []
        with self._cursor(write=False, connection=connection) as cur:
            cur.execute(
                """
                SELECT b.mapping_id, b.l1_l8_path
                FROM business_tag_mapping b
                WHERE b.mapping_id = ANY(%s)
                ORDER BY b.mapping_id
                """,
                (list(mapping_ids),),
            )
            rows = cur.fetchall()
        result: list[EvidenceGap] = []
        for row in rows:
            payload = _json_value(dict(row).get("l1_l8_path"), {})
            gaps = payload.get("evidence_gaps", []) if isinstance(payload, dict) else []
            for gap in gaps:
                if not isinstance(gap, Mapping):
                    continue
                result.append(
                    EvidenceGap(
                        mapping_id=str(gap.get("mapping_id") or dict(row)["mapping_id"]),
                        requirement_id=str(gap.get("requirement_id") or ""),
                        status=str(gap.get("status") or "missing"),
                        evidence_ids=tuple(gap.get("evidence_ids") or ()),
                        next_action=str(gap.get("next_action") or ""),
                        reasons=tuple(gap.get("reasons") or ()),
                        product_terms=tuple(gap.get("product_terms") or ()),
                        scene_terms=tuple(gap.get("scene_terms") or ()),
                        negative_examples=tuple(gap.get("negative_examples") or ()),
                        require_product_and_scene=gap.get(
                            "require_product_and_scene", True
                        )
                        is True,
                    )
                )
        return result

    def upsert_gap_rows(
        self,
        gaps: Sequence[EvidenceGap],
        as_of_date: date,
        *,
        connection: Any | None = None,
    ) -> int:
        grouped: dict[str, list[dict[str, Any]]] = {}
        for gap in gaps:
            grouped.setdefault(gap.mapping_id, []).append(thaw_json(gap.__dict__))
        if not grouped:
            return 0
        with self._cursor(write=True, connection=connection) as cur:
            for mapping_id, values in grouped.items():
                cur.execute(
                    """
                    UPDATE business_tag_mapping
                    SET l1_l8_path = jsonb_set(
                            jsonb_set(
                                CASE WHEN jsonb_typeof(l1_l8_path) = 'object'
                                     THEN l1_l8_path ELSE '{}'::jsonb END,
                                '{evidence_gaps}', %s::jsonb, true
                            ),
                            '{evidence_gaps_as_of_date}', to_jsonb(%s::text), true
                        ),
                        updated_at = CURRENT_TIMESTAMP
                    WHERE mapping_id = %s
                      AND COALESCE(
                            NULLIF(l1_l8_path ->> 'evidence_gaps_as_of_date', '')::date,
                            DATE '0001-01-01'
                          ) <= %s::date
                    """,
                    (
                        _json(values),
                        as_of_date.isoformat(),
                        mapping_id,
                        as_of_date.isoformat(),
                    ),
                )
        return len(gaps)

    def upsert_node_dimension_updates(
        self,
        updates: Sequence[Any],
        as_of_date: date,
        *,
        connection: Any | None = None,
    ) -> int:
        if not updates:
            return 0
        with self._cursor(write=True, connection=connection) as cur:
            for update in updates:
                record_date = update.as_of_date or as_of_date
                record_id = _stable_id(
                    "DIM", update.node_id, update.dimension_id, record_date
                )
                cur.execute(
                    """
                    INSERT INTO supply_chain_node_dimensions (
                        dimension_record_id, node_id, dimension_id, as_of_date,
                        status, score, coverage_ratio, payload, evidence_ids,
                        review_status
                    ) VALUES (
                        %s, %s, %s, %s,
                        %s, %s, %s, '{}'::jsonb, %s::jsonb,
                        'pending_review'
                    )
                    ON CONFLICT (node_id, dimension_id, as_of_date) DO UPDATE SET
                        status = EXCLUDED.status,
                        score = EXCLUDED.score,
                        coverage_ratio = EXCLUDED.coverage_ratio,
                        evidence_ids = EXCLUDED.evidence_ids,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE supply_chain_node_dimensions.review_status NOT IN ('approved','rejected')
                    """,
                    (
                        record_id,
                        update.node_id,
                        update.dimension_id,
                        record_date,
                        update.status,
                        update.score,
                        1.0 if update.score is not None else 0.0,
                        _json(update.evidence_ids),
                    ),
                )
        return len(updates)

    def fetch_local_documents(
        self,
        task: Any,
        as_of_date: date | datetime,
        *,
        connection: Any | None = None,
    ):
        """Read bounded local evidence sources for one explicit mapping task."""

        from supply_chain_data_collection_center import RawDocument

        canonical_tables = (
            "raw_evidence_documents",
            "stock_profiles",
            "fina_mainbz",
            "announcements",
            "ts_raw_anns_d",
            "interact_qa",
            "research_reports_tushare",
            "patent_events",
        )
        source_wall_cutoff = _as_of_upper_bound(as_of_date)
        audit_utc_cutoff = _as_of_audit_upper_bound(as_of_date)
        cutoff_day = _shanghai_date(as_of_date)
        if cutoff_day is None:
            raise ValueError("as_of cutoff must resolve to a Shanghai date")
        with self._cursor(write=False, connection=connection) as cur:
            cur.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name = ANY(%s)
                """,
                (list(canonical_tables),),
            )
            present = {
                str(dict(row).get("table_name") or "") for row in cur.fetchall()
            }
            records: list[RawDocument] = []
            code = str(task.company_code).split(".", 1)[0]
            event_start = date(cutoff_day.year - 3, 1, 1)
            if "raw_evidence_documents" in present:
                cur.execute(
                    """
                    SELECT doc_id, source_id, source_level, title, content_text,
                           url, company_code, company_name, publish_time,
                           created_at, doc_type, metadata
                    FROM raw_evidence_documents
                    WHERE split_part(company_code, '.', 1) = %s
                      AND (publish_time IS NULL OR publish_time < %s)
                      AND created_at < %s
                    ORDER BY publish_time DESC NULLS LAST, doc_id
                    LIMIT 200
                    """,
                    (code, source_wall_cutoff, audit_utc_cutoff),
                )
                for raw in cur.fetchall():
                    row = dict(raw)
                    records.append(
                        RawDocument(
                            source_id=str(row.get("source_id") or "local_raw"),
                            source_level=str(row.get("source_level") or "mid"),
                            title=str(row.get("title") or "本地证据"),
                            content_text=str(row.get("content_text") or ""),
                            url=row.get("url"),
                            company_code=str(row.get("company_code") or code),
                            company_name=row.get("company_name"),
                            publish_time=(
                                row["publish_time"].isoformat()
                                if isinstance(row.get("publish_time"), (date, datetime))
                                else row.get("publish_time")
                            ),
                            doc_type=str(row.get("doc_type") or "announcement"),
                            metadata={
                                **_json_value(row.get("metadata"), {}),
                                "origin_table": "raw_evidence_documents",
                            },
                        )
                    )
            if "stock_profiles" in present:
                cur.execute(
                    """
                    SELECT code, full_name, main_business, business_scope,
                           introduction, website, updated_at
                    FROM stock_profiles
                    WHERE split_part(code, '.', 1) = %s
                      AND updated_at IS NOT NULL
                      AND updated_at < %s
                    LIMIT 1
                    """,
                    (code, audit_utc_cutoff),
                )
                for raw in cur.fetchall():
                    row = dict(raw)
                    updated_day = _shanghai_date(row.get("updated_at"))
                    if updated_day is None or updated_day > cutoff_day:
                        continue
                    records.append(
                        RawDocument(
                            source_id="local_stock_profile",
                            source_level="mid",
                            title=f"{row.get('full_name') or code} 公司业务概况",
                            content_text=" ".join(
                                str(row.get(key) or "")
                                for key in (
                                    "main_business",
                                    "business_scope",
                                    "introduction",
                                )
                            ),
                            url=row.get("website"),
                            company_code=code,
                            company_name=row.get("full_name"),
                            publish_time=None,
                            doc_type="company_profile",
                            metadata={
                                "updated_at": thaw_json(row.get("updated_at")),
                                "origin_table": "stock_profiles",
                            },
                        )
                    )
            if "fina_mainbz" in present:
                cur.execute(
                    """
                    SELECT code, end_date, biz_item, biz_income, biz_ratio, biz_type
                    FROM fina_mainbz
                    WHERE split_part(code, '.', 1) = %s
                      AND end_date <= %s
                    ORDER BY end_date DESC, biz_item
                    LIMIT 100
                    """,
                    (code, cutoff_day),
                )
                for raw in cur.fetchall():
                    row = dict(raw)
                    records.append(
                        RawDocument(
                            source_id="local_business_segment",
                            source_level="strong",
                            title=str(row.get("biz_item") or "主营业务构成"),
                            content_text=(
                                f"业务 {row.get('biz_item') or ''} "
                                f"收入 {row.get('biz_income')} 占比 {row.get('biz_ratio')}"
                            ),
                            company_code=code,
                            publish_time=(
                                row["end_date"].isoformat()
                                if isinstance(row.get("end_date"), (date, datetime))
                                else str(row.get("end_date") or "") or None
                            ),
                            doc_type="company_profile",
                            metadata={
                                "biz_item": row.get("biz_item"),
                                "biz_income": row.get("biz_income"),
                                "biz_ratio": row.get("biz_ratio"),
                                "biz_type": row.get("biz_type"),
                                "origin_table": "fina_mainbz",
                            },
                        )
                    )
            if "announcements" in present:
                cur.execute(
                    """
                    SELECT code, ann_date, title, ann_type, content
                    FROM announcements
                    WHERE split_part(code, '.', 1) = %s
                      AND ann_date BETWEEN %s AND %s
                    ORDER BY ann_date DESC, title
                    LIMIT 100
                    """,
                    (code, event_start, cutoff_day),
                )
                for raw in cur.fetchall():
                    row = dict(raw)
                    records.append(
                        RawDocument(
                            source_id="cninfo_announcement",
                            source_level="strong",
                            title=str(row.get("title") or "公司公告"),
                            content_text=str(row.get("content") or row.get("title") or ""),
                            company_code=code,
                            publish_time=(
                                row["ann_date"].isoformat()
                                if isinstance(row.get("ann_date"), (date, datetime))
                                else str(row.get("ann_date") or "") or None
                            ),
                            doc_type="announcement",
                            metadata={
                                "announcement_type": row.get("ann_type"),
                                "origin_table": "announcements",
                            },
                        )
                    )
            if "ts_raw_anns_d" in present:
                cur.execute(
                    """
                    SELECT split_part(ts_code, '.', 1) AS code, ann_date, title, url
                    FROM ts_raw_anns_d
                    WHERE split_part(ts_code, '.', 1) = %s
                      AND ann_date BETWEEN %s AND %s
                    ORDER BY ann_date DESC, title
                    LIMIT 100
                    """,
                    (
                        code,
                        event_start.strftime("%Y%m%d"),
                        cutoff_day.strftime("%Y%m%d"),
                    ),
                )
                for raw in cur.fetchall():
                    row = dict(raw)
                    raw_date = str(row.get("ann_date") or "")
                    if len(raw_date) >= 8 and raw_date[:8].isdigit():
                        raw_date = f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:8]}"
                    records.append(
                        RawDocument(
                            source_id="cninfo_announcement",
                            source_level="strong",
                            title=str(row.get("title") or "巨潮公告"),
                            content_text=str(row.get("title") or ""),
                            url=row.get("url"),
                            company_code=code,
                            publish_time=raw_date or None,
                            doc_type="announcement",
                            metadata={"origin_table": "ts_raw_anns_d"},
                        )
                    )
            if "interact_qa" in present:
                cur.execute(
                    """
                    SELECT id, code, pub_date, pub_time, question, answer, source
                    FROM interact_qa
                    WHERE split_part(code, '.', 1) = %s
                      AND pub_date BETWEEN %s AND %s
                    ORDER BY pub_date DESC, id
                    LIMIT 100
                    """,
                    (code, event_start, cutoff_day),
                )
                for raw in cur.fetchall():
                    row = dict(raw)
                    published = row.get("pub_date")
                    if isinstance(published, datetime):
                        published = published.date()
                    if not isinstance(published, date) or published < event_start:
                        continue
                    records.append(
                        RawDocument(
                            source_id="exchange_interact_qa",
                            source_level="mid",
                            title=str(row.get("question") or "互动问答"),
                            content_text=f"{row.get('question') or ''} {row.get('answer') or ''}",
                            company_code=code,
                            publish_time=published.isoformat(),
                            doc_type="interactive_qa",
                            metadata={
                                "source": row.get("source"),
                                "row_id": row.get("id"),
                                "origin_table": "interact_qa",
                            },
                        )
                    )
            if "research_reports_tushare" in present:
                cur.execute(
                    """
                    SELECT code, pub_date, title, broker, rating, target_price,
                           report_type, author, name
                    FROM research_reports_tushare
                    WHERE split_part(code, '.', 1) = %s
                      AND pub_date BETWEEN %s AND %s
                    ORDER BY pub_date DESC, title
                    LIMIT 100
                    """,
                    (code, event_start, cutoff_day),
                )
                for raw in cur.fetchall():
                    row = dict(raw)
                    published = row.get("pub_date")
                    records.append(
                        RawDocument(
                            source_id="broker_expectation_local",
                            source_level="mid",
                            title=str(row.get("title") or "研究报告"),
                            content_text=" ".join(
                                str(row.get(key) or "")
                                for key in ("title", "broker", "rating", "report_type")
                            ),
                            company_code=code,
                            company_name=row.get("name"),
                            publish_time=(
                                published.isoformat()
                                if isinstance(published, (date, datetime))
                                else str(published or "") or None
                            ),
                            doc_type="research_report",
                            metadata={
                                "broker": row.get("broker"),
                                "rating": row.get("rating"),
                                "target_price": row.get("target_price"),
                                "author": row.get("author"),
                                "origin_table": "research_reports_tushare",
                            },
                        )
                    )
            if "patent_events" in present:
                cur.execute(
                    """
                    SELECT event_id, company_code, company_name, publication_number,
                           patent_title, patent_abstract, applicant, application_date,
                           publication_date, grant_date, patent_status, created_at,
                           metadata
                    FROM patent_events
                    WHERE split_part(company_code, '.', 1) = %s
                      AND (
                          COALESCE(publication_date, application_date) IS NULL
                          OR COALESCE(publication_date, application_date) <= %s
                      )
                      AND created_at < %s
                    ORDER BY COALESCE(publication_date, application_date) DESC NULLS LAST,
                             event_id
                    LIMIT 100
                    """,
                    (code, cutoff_day, audit_utc_cutoff),
                )
                for raw in cur.fetchall():
                    row = dict(raw)
                    published = row.get("publication_date") or row.get("application_date")
                    metadata = _json_value(row.get("metadata"), {})
                    metadata.update(
                        {
                            "publication_number": row.get("publication_number"),
                            "legal_status": row.get("patent_status"),
                            "legal_status_date": thaw_json(
                                metadata.get("legal_status_date")
                                or row.get("grant_date")
                            ),
                            "origin_table": "patent_events",
                        }
                    )
                    records.append(
                        RawDocument(
                            source_id="patent_public_platform",
                            source_level="strong",
                            title=str(row.get("patent_title") or "专利"),
                            content_text=str(row.get("patent_abstract") or ""),
                            company_code=code,
                            company_name=row.get("company_name"),
                            publish_time=(
                                published.isoformat()
                                if isinstance(published, (date, datetime))
                                else str(published or "") or None
                            ),
                            doc_type="patent",
                            metadata=metadata,
                        )
                    )

        queries = tuple(str(value).casefold() for value in task.queries if value)
        filtered: list[RawDocument] = []
        for document in records:
            published_date = _shanghai_date(document.publish_time)
            if document.doc_type in {
                "announcement",
                "announcement_pdf",
                "interactive_qa",
                "research_report",
                "investor_relations_event",
            } and published_date is not None and not (
                event_start <= published_date <= cutoff_day
            ):
                continue
            text = f"{document.title} {document.content_text}".casefold()
            if queries and not any(query in text for query in queries):
                continue
            filtered.append(document)
        deduplicated = list({document.doc_id: document for document in filtered}.values())
        errors = tuple(
            f"missing_local_source:{table}"
            for table in canonical_tables
            if table not in present
        )
        return deduplicated, errors
