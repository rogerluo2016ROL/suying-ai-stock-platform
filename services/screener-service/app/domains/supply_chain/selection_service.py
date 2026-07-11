"""Application service for persisted supply-chain selection V2 results."""

from __future__ import annotations

import os
import sys
from datetime import date
from pathlib import Path
from typing import Any, Callable

from kronos_factors.scorer.supply_chain_selection_v2 import aggregate_stock_mappings

from app.domains.supply_chain.models import SelectionBatchCalculateRequest
from app.domains.supply_chain.repository import connect
from app.domains.supply_chain.selection_repository import SelectionRepository


MODEL_VERSION = "v2.0"
DEFAULT_DSN = "postgresql://kronos:kronos@localhost:6432/kronos"
FIVE_SELECTION_SCORES = (
    "benefit_score",
    "expectation_gap_score",
    "risk_score",
    "confidence_score",
    "opportunity_score",
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


def _row_limitations(row: dict[str, Any]) -> list[str]:
    mapping_id = str(row.get("mapping_id") or row.get("primary_mapping_id") or "unknown")
    limitations = _as_string_list(row.get("data_limitations"))
    for field in FIVE_SELECTION_SCORES:
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
    mappings = repo.fetch_stock_detail_rows(
        code=code,
        chain_id=chain_id,
        trade_date=trade_date,
        model_version=model_version,
    )
    transitions = repo.fetch_transition_rows(
        code=code,
        chain_id=chain_id,
        trade_date=trade_date,
    )
    for mapping in mappings:
        mapping["data_limitations"] = _row_limitations(mapping)
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
