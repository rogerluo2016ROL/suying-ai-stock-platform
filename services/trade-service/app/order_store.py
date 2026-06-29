"""Persisted trade order ledger for platform-scoped order queries."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("trade-service.order_store")

TABLE_TRADE_ORDERS = "trade_orders"


async def record(
    db: AsyncSession,
    *,
    order_id: str,
    tenant_id: str,
    owner_user_id: str | None,
    account_id: str | None,
    trade_mode: str,
    code: str,
    direction: str,
    price: float | None,
    volume: int,
    status: str,
    decision_context_id: str | None = None,
    candidate_id: str | None = None,
    plan_id: str | None = None,
    order_scope: dict[str, Any] | None = None,
    risk_verdict: dict[str, Any] | None = None,
) -> int | None:
    """Persist one order snapshot; duplicate order ids are ignored."""
    result = await db.execute(
        text(
            f"""
            INSERT INTO {TABLE_TRADE_ORDERS}
                (order_id, tenant_id, owner_user_id, account_id, trade_mode,
                 code, direction, price, volume, status, decision_context_id,
                 candidate_id, plan_id, order_scope, risk_verdict, created_at)
            VALUES
                (:order_id, :tenant_id, :owner_user_id, :account_id, :trade_mode,
                 :code, :direction, :price, :volume, :status, :decision_context_id,
                 :candidate_id, :plan_id, CAST(:order_scope AS jsonb),
                 CAST(:risk_verdict AS jsonb), :created_at)
            ON CONFLICT (order_id) DO NOTHING
            RETURNING id
            """
        ),
        {
            "order_id": order_id,
            "tenant_id": tenant_id,
            "owner_user_id": owner_user_id,
            "account_id": account_id,
            "trade_mode": trade_mode,
            "code": code.upper(),
            "direction": direction.upper(),
            "price": price,
            "volume": volume,
            "status": status,
            "decision_context_id": decision_context_id,
            "candidate_id": candidate_id,
            "plan_id": plan_id,
            "order_scope": json.dumps(order_scope or {}, ensure_ascii=False),
            "risk_verdict": json.dumps(risk_verdict or {}, ensure_ascii=False),
            "created_at": datetime.now(timezone.utc),
        },
    )
    row = result.fetchone()
    order_row_id = row[0] if row else None
    logger.debug("TradeOrder #%s: %s", order_row_id, order_id)
    return order_row_id


async def query(
    db: AsyncSession,
    *,
    tenant_id: str | None = None,
    account_id: str | None = None,
    trade_mode: str | None = None,
    code: str | None = None,
    page: int = 1,
    page_size: int = 50,
) -> dict[str, Any]:
    """Query order ledger records by platform scope."""
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
    if trade_mode is not None:
        where_clauses.append("trade_mode = :trade_mode")
        params["trade_mode"] = trade_mode
    if code is not None:
        where_clauses.append("code = :code")
        params["code"] = code.upper()

    where_sql = " AND ".join(where_clauses)
    count_result = await db.execute(
        text(f"SELECT COUNT(*) FROM {TABLE_TRADE_ORDERS} WHERE {where_sql}"),
        params,
    )
    total = count_result.scalar() or 0

    params["limit"] = page_size
    params["offset"] = offset
    rows_result = await db.execute(
        text(
            f"""
            SELECT id, order_id, tenant_id, owner_user_id, account_id, trade_mode,
                   code, direction, price, volume, status, decision_context_id,
                   candidate_id, plan_id, order_scope, risk_verdict, created_at
            FROM {TABLE_TRADE_ORDERS}
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
        "orders": [_row_to_record(row) for row in rows_result.fetchall()],
    }


def _row_to_record(row: Any) -> dict[str, Any]:
    order_scope = row[14] if isinstance(row[14], dict) else json.loads(row[14] or "{}")
    risk_verdict = row[15] if isinstance(row[15], dict) else json.loads(row[15] or "{}")
    return {
        "id": row[0],
        "order_id": row[1],
        "tenant_id": row[2],
        "owner_user_id": row[3],
        "account_id": row[4],
        "trade_mode": row[5],
        "code": row[6],
        "direction": row[7],
        "price": row[8],
        "volume": row[9],
        "status": row[10],
        "decision_context_id": row[11],
        "candidate_id": row[12],
        "plan_id": row[13],
        "order_scope": order_scope,
        "risk_verdict": risk_verdict,
        "created_at": row[16].isoformat() if row[16] else None,
    }
