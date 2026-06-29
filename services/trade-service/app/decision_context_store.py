"""DecisionContext persistence for order lineage snapshots."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("trade-service.decision_context_store")

TABLE_DECISION_CONTEXTS = "decision_contexts"


async def record_once(
    db: AsyncSession,
    *,
    decision_context_id: str,
    tenant_id: str,
    owner_user_id: str | None,
    account_id: str | None,
    source_type: str,
    symbol: str | None = None,
    plan_id: str | None = None,
    candidate_id: str | None = None,
    intent: str = "manual_order",
    payload: dict[str, Any] | None = None,
) -> int | None:
    """Insert a context snapshot once; repeated ids are ignored."""
    serialized = json.dumps(payload or {}, ensure_ascii=False)
    result = await db.execute(
        text(
            f"""
            INSERT INTO {TABLE_DECISION_CONTEXTS}
                (decision_context_id, tenant_id, owner_user_id, account_id,
                 source_type, symbol, plan_id, candidate_id, intent, payload, created_at)
            VALUES
                (:decision_context_id, :tenant_id, :owner_user_id, :account_id,
                 :source_type, :symbol, :plan_id, :candidate_id, :intent,
                 CAST(:payload AS jsonb), :created_at)
            ON CONFLICT (decision_context_id) DO NOTHING
            RETURNING id
            """
        ),
        {
            "decision_context_id": decision_context_id,
            "tenant_id": tenant_id,
            "owner_user_id": owner_user_id,
            "account_id": account_id,
            "source_type": source_type,
            "symbol": symbol.upper() if symbol else None,
            "plan_id": plan_id,
            "candidate_id": candidate_id,
            "intent": intent,
            "payload": serialized,
            "created_at": datetime.now(timezone.utc),
        },
    )
    row = result.fetchone()
    context_row_id = row[0] if row else None
    logger.debug("DecisionContext #%s: %s", context_row_id, decision_context_id)
    return context_row_id


async def query(
    db: AsyncSession,
    *,
    tenant_id: str | None = None,
    account_id: str | None = None,
    decision_context_id: str | None = None,
    symbol: str | None = None,
    plan_id: str | None = None,
    candidate_id: str | None = None,
    page: int = 1,
    page_size: int = 50,
) -> dict[str, Any]:
    """Query persisted decision contexts by platform scope and lineage ids."""
    page_size = min(page_size, 200)
    offset = (page - 1) * page_size

    where_clauses = ["1=1"]
    params: dict[str, Any] = {}
    if tenant_id is not None:
        where_clauses.append("tenant_id = :tenant_id")
        params["tenant_id"] = tenant_id
    if account_id is not None:
        where_clauses.append("account_id = :account_id")
        params["account_id"] = account_id
    if decision_context_id is not None:
        where_clauses.append("decision_context_id = :decision_context_id")
        params["decision_context_id"] = decision_context_id
    if symbol is not None:
        where_clauses.append("symbol = :symbol")
        params["symbol"] = symbol.upper()
    if plan_id is not None:
        where_clauses.append("plan_id = :plan_id")
        params["plan_id"] = plan_id
    if candidate_id is not None:
        where_clauses.append("candidate_id = :candidate_id")
        params["candidate_id"] = candidate_id

    where_sql = " AND ".join(where_clauses)
    count_result = await db.execute(
        text(f"SELECT COUNT(*) FROM {TABLE_DECISION_CONTEXTS} WHERE {where_sql}"),
        params,
    )
    total = count_result.scalar() or 0

    params["limit"] = page_size
    params["offset"] = offset
    rows_result = await db.execute(
        text(
            f"""
            SELECT id, decision_context_id, tenant_id, owner_user_id, account_id,
                   source_type, symbol, plan_id, candidate_id, intent, payload,
                   created_at
            FROM {TABLE_DECISION_CONTEXTS}
            WHERE {where_sql}
            ORDER BY created_at DESC
            LIMIT :limit OFFSET :offset
            """
        ),
        params,
    )

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "records": [_row_to_record(row) for row in rows_result.fetchall()],
    }


def _row_to_record(row: Any) -> dict[str, Any]:
    payload = row[10] if isinstance(row[10], dict) else json.loads(row[10] or "{}")
    return {
        "id": row[0],
        "decision_context_id": row[1],
        "tenant_id": row[2],
        "owner_user_id": row[3],
        "account_id": row[4],
        "source_type": row[5],
        "symbol": row[6],
        "plan_id": row[7],
        "candidate_id": row[8],
        "intent": row[9],
        "payload": payload,
        "created_at": row[11].isoformat() if row[11] else None,
    }
