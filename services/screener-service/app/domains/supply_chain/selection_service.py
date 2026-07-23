"""Application service for persisted supply-chain selection V2 results."""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Mapping
from datetime import date, datetime, timezone, tzinfo
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit, urlunsplit
from zoneinfo import ZoneInfo

from kronos_factors.scorer.supply_chain_selection_v2 import aggregate_stock_mappings

from app.domains.supply_chain.models import SelectionBatchCalculateRequest
from app.domains.supply_chain.repository import connect
from app.domains.supply_chain.selection_repository import SelectionRepository


MODEL_VERSION = "v2.0"
DEFAULT_DSN = "postgresql://kronos:kronos@localhost:6432/kronos"
SELECTION_SCORE_FIELDS = (
    "benefit_score",
    "expectation_gap_score",
    "catalyst_score",
    "risk_score",
    "confidence_score",
    "opportunity_score",
)
# Kept as an import-compatible alias for older callers.
FIVE_SELECTION_SCORES = SELECTION_SCORE_FIELDS

_SHANGHAI = ZoneInfo("Asia/Shanghai")
_SENSITIVE_KEY_MARKERS = (
    "api_key",
    "token",
    "secret",
    "password",
    "authorization",
    "cookie",
    "credential",
    "dsn",
    "metadata",
    "review_note",
)
_AS_OF_FIELDS = (
    "publish_time",
    "published_at",
    "source_publish_time",
    "reviewed_at",
    "created_at",
    "event_date",
    "claim_date",
    "as_of_date",
)
_CURRENT_POOL_STATE_FIELDS = frozenset(
    {"pool_state_status", "next_validation_event", "next_validation_date"}
)
_EVIDENCE_FIELDS = frozenset(
    {
        "evidence_id",
        "fact_id",
        "event_id",
        "monitor_id",
        "document_id",
        "source_doc_id",
        "kind",
        "status",
        "fact_type",
        "fact_nature",
        "event_type",
        "source_level",
        "source_name",
        "publish_time",
        "published_at",
        "reviewed_at",
        "reviewer",
        "event_date",
        "claim_date",
        "expected_date",
        "confidence",
    }
)
_GAP_FIELDS = frozenset(
    {
        "requirement_id",
        "requirement_type",
        "evidence_type",
        "tag_id",
        "label",
        "description",
        "status",
        "reason",
        "evidence_ids",
        "missing_fields",
        "next_action",
        "as_of_date",
    }
)


def _repository() -> SelectionRepository:
    return SelectionRepository(connect)


def _validate_model_version(model_version: str) -> None:
    if model_version != MODEL_VERSION:
        raise ValueError(f"model_version must be {MODEL_VERSION}")


def _as_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value if item is not None]
    return [str(value)]


def _is_sensitive_key(key: Any) -> bool:
    normalized = str(key).casefold().replace("-", "_")
    return any(marker in normalized for marker in _SENSITIVE_KEY_MARKERS)


def _is_url_key(key: Any) -> bool:
    normalized = str(key).casefold().replace("-", "_")
    return normalized in {
        "url",
        "uri",
        "href",
        "link",
        "urls",
        "uris",
        "links",
    } or normalized.endswith(
        ("_url", "_uri", "_href", "_link", "_urls", "_uris", "_links")
    )


def _sanitize_url(value: str, *, force: bool = False) -> str:
    try:
        parsed = urlsplit(value)
    except ValueError:
        return value
    if not force and not parsed.scheme and not parsed.netloc:
        return value

    # API explanations expose the stable resource location only. Userinfo,
    # signed query parameters and fragments are deliberately never returned.
    netloc = parsed.netloc.rsplit("@", 1)[-1]
    return urlunsplit((parsed.scheme, netloc, parsed.path, "", ""))


def _sanitize_value(value: Any, *, url_context: bool = False) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _sanitize_value(
                item,
                url_context=url_context or _is_url_key(key),
            )
            for key, item in value.items()
            if not _is_sensitive_key(key)
        }
    if isinstance(value, (list, tuple, set)):
        return [_sanitize_value(item, url_context=url_context) for item in value]
    if isinstance(value, str):
        return _sanitize_url(value, force=url_context)
    return value


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError):
            return {}
        if isinstance(parsed, Mapping):
            return dict(parsed)
    return {}


def _is_on_or_before(
    value: Any,
    trade_date: date,
    *,
    naive_timezone: tzinfo = _SHANGHAI,
) -> bool:
    if value in (None, ""):
        return True
    parsed: date | datetime
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = value
    elif isinstance(value, str):
        text = value.strip()
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            try:
                parsed = date.fromisoformat(text)
            except ValueError:
                return False
    else:
        return False
    if isinstance(parsed, datetime):
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=naive_timezone)
        parsed_date = parsed.astimezone(_SHANGHAI).date()
    else:
        parsed_date = parsed
    return parsed_date <= trade_date


def _visible_as_of(item: Mapping[str, Any], trade_date: date) -> bool:
    return all(
        _is_on_or_before(
            item.get(field),
            trade_date,
            naive_timezone=(
                timezone.utc if field in {"created_at", "reviewed_at"} else _SHANGHAI
            ),
        )
        for field in _AS_OF_FIELDS
        if item.get(field) not in (None, "")
    )


def _mapping_records(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, (list, tuple)):
        return []
    return [dict(item) for item in value if isinstance(item, Mapping)]


def _record_sort_key(item: Mapping[str, Any]) -> tuple[str, ...]:
    return tuple(
        str(item.get(field) or "")
        for field in ("evidence_id", "fact_id", "event_id", "monitor_id")
    )


def _safe_evidence_records(
    value: Any,
    *,
    bucket: str,
    trade_date: date,
) -> list[dict[str, Any]]:
    safe: list[dict[str, Any]] = []
    for item in _mapping_records(value):
        if not _visible_as_of(item, trade_date):
            continue
        raw_status = str(
            item.get("status")
            or item.get("validation_status")
            or item.get("review_status")
            or ""
        ).casefold()
        if bucket == "approved":
            if raw_status not in {"approved", "confirmed"}:
                continue
            has_publish_time = any(
                item.get(field) not in (None, "")
                for field in (
                    "publish_time",
                    "published_at",
                    "source_publish_time",
                    "event_date",
                    "claim_date",
                )
            )
            if not has_publish_time or item.get("reviewed_at") in (None, ""):
                continue
        rendered = {
            key: item[key]
            for key in _EVIDENCE_FIELDS
            if key in item and item[key] is not None
        }
        if bucket == "approved":
            rendered["status"] = "approved"
            if "evidence_id" not in rendered:
                rendered["evidence_id"] = next(
                    (
                        str(item[key])
                        for key in ("fact_id", "event_id", "monitor_id")
                        if item.get(key) is not None
                    ),
                    "",
                )
        elif bucket == "pending":
            rendered["status"] = "pending"
        else:
            rendered["status"] = (
                "contradicted" if raw_status == "contradicted" else "rejected"
            )
        safe.append(_sanitize_value(rendered))
    return sorted(safe, key=_record_sort_key)


def _explanation_index(value: Any) -> dict[str, dict[str, Any]]:
    buckets = ("approved_evidence", "pending_facts", "rejected_facts")
    if isinstance(value, Mapping):
        if any(bucket in value for bucket in buckets):
            mapping_id = str(value.get("mapping_id") or "")
            return {mapping_id: dict(value)}
        return {
            str(mapping_id): dict(item)
            for mapping_id, item in value.items()
            if isinstance(item, Mapping)
        }

    indexed: dict[str, dict[str, Any]] = {}
    for item in _mapping_records(value):
        mapping_id = str(item.get("mapping_id") or "")
        target = indexed.setdefault(mapping_id, {bucket: [] for bucket in buckets})
        if any(bucket in item for bucket in buckets):
            for bucket in buckets:
                target[bucket].extend(_mapping_records(item.get(bucket)))
            continue
        bucket = str(item.get("bucket") or item.get("category") or "")
        if bucket not in buckets:
            status = str(
                item.get("status")
                or item.get("validation_status")
                or item.get("review_status")
                or ""
            ).casefold()
            if status in {"approved", "confirmed", "verified"}:
                bucket = "approved_evidence"
            elif status in {"rejected", "contradicted"}:
                bucket = "rejected_facts"
            else:
                bucket = "pending_facts"
        target[bucket].append(item)
    return indexed


def _evidence_gaps_as_of(
    mapping: Mapping[str, Any],
    *,
    trade_date: date,
) -> tuple[list[dict[str, Any]], bool]:
    path = _as_dict(mapping.get("l1_l8_path"))
    snapshot_date = (
        path.get("evidence_gaps_as_of_date")
        or mapping.get("evidence_gaps_as_of_date")
    )
    if snapshot_date not in (None, "") and not _is_on_or_before(
        snapshot_date, trade_date
    ):
        return [], True
    raw_gaps = path.get("evidence_gaps", mapping.get("evidence_gaps"))
    gaps = []
    for item in _mapping_records(raw_gaps):
        if not _visible_as_of(item, trade_date):
            continue
        rendered = {
            key: item[key]
            for key in _GAP_FIELDS
            if key in item and item[key] is not None
        }
        gaps.append(_sanitize_value(rendered))
    return sorted(
        gaps,
        key=lambda item: (
            str(item.get("requirement_id") or ""),
            str(item.get("status") or ""),
            str(item.get("next_action") or ""),
        ),
    ), False


def _pool_gate_from_detail(
    mapping: Mapping[str, Any], factor_detail: Mapping[str, Any]
) -> Any:
    if factor_detail.get("pool_gate") is not None:
        return factor_detail.get("pool_gate")
    gates = factor_detail.get("pool_gates")
    if isinstance(gates, Mapping):
        return gates.get("combined")
    return mapping.get("pool_gate")


def _row_limitations(row: dict[str, Any]) -> list[str]:
    mapping_id = str(row.get("mapping_id") or row.get("primary_mapping_id") or "unknown")
    limitations = _as_string_list(row.get("data_limitations"))
    for field in SELECTION_SCORE_FIELDS:
        if row.get(field) is None:
            limitations.append(f"missing_{field}:{mapping_id}")
    if row.get("mapping_status") in {"candidate", "pending_review", "weak_evidence"}:
        limitations.append(f"mapping_not_verified:{mapping_id}")
    if row.get("authenticity_review_status") not in {None, "approved"}:
        limitations.append(f"authenticity_score_pending_review:{mapping_id}")
    return sorted(set(limitations))


def _collect_limitations(rows: list[dict[str, Any]]) -> list[str]:
    return sorted({item for row in rows for item in _row_limitations(row)})


def list_selection_candidates(
    *,
    chain_id: str,
    trade_date: date,
    pool: str | None,
    model_version: str,
    limit: int,
    offset: int,
    repository: SelectionRepository | None = None,
) -> dict[str, Any]:
    _validate_model_version(model_version)
    repo = repository or _repository()
    rows = repo.fetch_candidate_rows(
        chain_id=chain_id,
        trade_date=trade_date,
        pool=pool,
        model_version=model_version,
        limit=limit,
        offset=offset,
    )
    items = aggregate_stock_mappings(rows)
    for item in items:
        related = [item, *_as_mapping_list(item.get("secondary_mappings"))]
        item["data_limitations"] = _collect_limitations(related)
        item["secondary_mappings"] = [
            {
                key: value
                for key, value in secondary.items()
                if key not in _CURRENT_POOL_STATE_FIELDS
            }
            for secondary in _as_mapping_list(item.get("secondary_mappings"))
        ]
        sanitized = _sanitize_value(item)
        item.clear()
        item.update(sanitized)
    return {
        "chain_id": chain_id,
        "trade_date": trade_date.isoformat(),
        "model_version": model_version,
        "items": items,
        "data_limitations": _collect_limitations(rows),
    }


def _as_mapping_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]


def _mapping_explanation(
    mapping: dict[str, Any],
    *,
    explanation: Mapping[str, Any],
    trade_date: date,
) -> dict[str, Any]:
    mapping_id = str(mapping.get("mapping_id") or "unknown")
    factor_detail = _as_dict(mapping.get("factor_detail"))
    gaps, future_gap_snapshot = _evidence_gaps_as_of(
        mapping, trade_date=trade_date
    )
    approved_evidence = _safe_evidence_records(
        explanation.get("approved_evidence"),
        bucket="approved",
        trade_date=trade_date,
    )
    pending_facts = _safe_evidence_records(
        explanation.get("pending_facts"),
        bucket="pending",
        trade_date=trade_date,
    )
    rejected_facts = _safe_evidence_records(
        explanation.get("rejected_facts"),
        bucket="rejected",
        trade_date=trade_date,
    )

    score_components = {
        "authenticity": _sanitize_value(
            _as_dict(mapping.get("authenticity_detail"))
        ),
        "operating_quality": _sanitize_value(
            _as_dict(mapping.get("operating_quality_detail"))
        ),
        "benefit": _sanitize_value(_as_dict(mapping.get("benefit_detail"))),
        "selection": _sanitize_value(factor_detail),
    }
    missing_score_inputs = [
        field for field in SELECTION_SCORE_FIELDS if mapping.get(field) is None
    ]
    pool_gate = _pool_gate_from_detail(mapping, factor_detail)
    blocking_gate = factor_detail.get(
        "blocking_gate", mapping.get("blocking_gate")
    )
    has_persisted_next_validation = "next_validation" in factor_detail or any(
        key in factor_detail
        for key in ("next_validation_event", "next_validation_date")
    )
    persisted_next = _as_dict(factor_detail.get("next_validation"))
    persisted_event = persisted_next.get(
        "event", factor_detail.get("next_validation_event")
    )
    persisted_date = persisted_next.get(
        "date", factor_detail.get("next_validation_date")
    )
    actions = sorted(
        {
            *(
                str(gap["next_action"])
                for gap in gaps
                if gap.get("next_action") not in (None, "")
            ),
            *(
                str(action)
                for action in _as_string_list(persisted_next.get("actions"))
                if action
            ),
        }
    )
    next_validation = {
        "event": persisted_event if has_persisted_next_validation else None,
        "date": persisted_date if has_persisted_next_validation else None,
        "actions": actions,
    }

    limitations = set(_row_limitations(mapping))
    if pool_gate is None:
        limitations.add(f"missing_pool_gate:{mapping_id}")
    if future_gap_snapshot:
        limitations.add(f"future_evidence_gap_snapshot:{mapping_id}")
    if not has_persisted_next_validation:
        limitations.add(f"unverifiable_historical_pool_state:{mapping_id}")

    safe_mapping = dict(mapping)
    safe_path = _as_dict(safe_mapping.get("l1_l8_path"))
    safe_path.pop("evidence_gaps", None)
    safe_path.pop("evidence_gaps_as_of_date", None)
    if "l1_l8_path" in safe_mapping:
        safe_mapping["l1_l8_path"] = safe_path
    safe_mapping.pop("evidence_gaps", None)
    safe_mapping.pop("evidence_gaps_as_of_date", None)
    for field in _CURRENT_POOL_STATE_FIELDS:
        safe_mapping.pop(field, None)

    rendered = {
        **safe_mapping,
        "approved_evidence": approved_evidence,
        "pending_facts": pending_facts,
        "rejected_facts": rejected_facts,
        "evidence_gaps": gaps,
        "score_components": score_components,
        "missing_score_inputs": missing_score_inputs,
        "pool_gate": _sanitize_value(pool_gate),
        "blocking_gate": _sanitize_value(blocking_gate),
        "next_validation": _sanitize_value(next_validation),
        "data_limitations": sorted(limitations),
    }
    return _sanitize_value(rendered)


def get_stock_selection_detail(
    *,
    code: str,
    chain_id: str,
    trade_date: date,
    model_version: str,
    repository: SelectionRepository | None = None,
) -> dict[str, Any]:
    _validate_model_version(model_version)
    repo = repository or _repository()
    raw_mappings = repo.fetch_stock_detail_rows(
        code=code,
        chain_id=chain_id,
        trade_date=trade_date,
        model_version=model_version,
    )
    raw_transitions = repo.fetch_transition_rows(
        code=code,
        chain_id=chain_id,
        trade_date=trade_date,
    )
    fetch_explanation = getattr(repo, "fetch_stock_explanation_rows", None)
    explanation_rows = (
        fetch_explanation(
            code=code,
            chain_id=chain_id,
            trade_date=trade_date,
        )
        if callable(fetch_explanation)
        else {}
    )
    explanations = _explanation_index(explanation_rows)
    mappings = [
        _mapping_explanation(
            dict(mapping),
            explanation=explanations.get(str(mapping.get("mapping_id") or ""), {}),
            trade_date=trade_date,
        )
        for mapping in raw_mappings
    ]
    transitions = [
        _sanitize_value(dict(item))
        for item in raw_transitions
        if isinstance(item, Mapping)
        and _is_on_or_before(item.get("transition_date"), trade_date)
        and _visible_as_of(item, trade_date)
    ]
    return {
        "code": code,
        "chain_id": chain_id,
        "trade_date": trade_date.isoformat(),
        "model_version": model_version,
        "mappings": mappings,
        "transitions": transitions,
        "data_limitations": _collect_limitations(mappings),
    }


def _batch_runner() -> Callable[..., dict[str, Any]]:
    project_root = Path(__file__).resolve().parents[5]
    tools_root = project_root / "tools"
    if not tools_root.is_dir():
        raise RuntimeError("supply-chain scoring tool is not installed")
    if str(tools_root) not in sys.path:
        sys.path.insert(0, str(tools_root))
    from score_supply_chain_selection_v2 import run_batch_score

    return run_batch_score


def batch_calculate_selection(
    request: SelectionBatchCalculateRequest,
    *,
    runner: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    _validate_model_version(request.model_version)
    execute = runner or _batch_runner()
    return execute(
        pg_url=os.environ.get("KRONOS_PG_URL", DEFAULT_DSN),
        chain_id=request.chain_id,
        trade_date=request.trade_date,
        model_version=request.model_version,
        dry_run=request.dry_run,
        mapping_ids=request.mapping_ids or None,
    )
