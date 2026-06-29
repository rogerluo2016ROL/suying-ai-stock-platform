"""RiskVerdict persistence for pre-trade risk decisions.

This table is intentionally separate from ``audit_logs``: audit remains the
immutable event trail, while RiskVerdict is the query surface for order review,
risk dashboards, and backtest/replay lineage.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("trade-service.risk_verdict_store")

TABLE_RISK_VERDICTS = "risk_verdicts"
VALID_RESULTS = frozenset({"pass", "warn", "reject", "manual_review"})
VALID_TRADE_MODES = frozenset({"paper", "live"})


async def record(
    db: AsyncSession,
    *,
    verdict: dict[str, Any],
    order_id: str | None = None,
    symbol: str | None = None,
) -> int:
    """Persist one risk verdict and return the inserted row id."""
    result_value = str(verdict.get("result") or "")
    if result_value not in VALID_RESULTS:
        raise ValueError(f"Unknown risk verdict result: {result_value!r}")

    trade_mode = str(verdict.get("trade_mode") or "")
    if trade_mode not in VALID_TRADE_MODES:
        raise ValueError(f"Unknown trade mode: {trade_mode!r}")

    payload = json.dumps(verdict, ensure_ascii=False)
    resolved_symbol = (symbol or verdict.get("symbol") or "").upper() or None
    resolved_order_id = order_id or verdict.get("order_id")

    inserted = await db.execute(
        text(
            f"""
            INSERT INTO {TABLE_RISK_VERDICTS}
                (verdict_id, tenant_id, owner_user_id, account_id, result,
                 scope, trade_mode, symbol, order_id, plan_id, candidate_id,
                 decision_context_id, details, created_at)
            VALUES
                (:verdict_id, :tenant_id, :owner_user_id, :account_id, :result,
                 :scope, :trade_mode, :symbol, :order_id, :plan_id, :candidate_id,
                 :decision_context_id, CAST(:details AS jsonb), :created_at)
            RETURNING id
            """
        ),
        {
            "verdict_id": verdict.get("verdict_id"),
            "tenant_id": verdict.get("tenant_id"),
            "owner_user_id": verdict.get("owner_user_id"),
            "account_id": verdict.get("account_id"),
            "result": result_value,
            "scope": verdict.get("scope") or "order",
            "trade_mode": trade_mode,
            "symbol": resolved_symbol,
            "order_id": resolved_order_id,
            "plan_id": verdict.get("plan_id"),
            "candidate_id": verdict.get("candidate_id"),
            "decision_context_id": verdict.get("decision_context_id"),
            "details": payload,
            "created_at": datetime.now(timezone.utc),
        },
    )
    row = inserted.fetchone()
    risk_verdict_id = row[0] if row else -1
    logger.debug("RiskVerdict #%d: %s %s", risk_verdict_id, result_value, resolved_symbol)
    return risk_verdict_id


async def query(
    db: AsyncSession,
    *,
    tenant_id: str | None = None,
    account_id: str | None = None,
    result: str | None = None,
    trade_mode: str | None = None,
    symbol: str | None = None,
    decision_context_id: str | None = None,
    order_id: str | None = None,
    plan_id: str | None = None,
    candidate_id: str | None = None,
    page: int = 1,
    page_size: int = 50,
) -> dict[str, Any]:
    """Query persisted risk verdicts with platform-scope filters."""
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
    if result is not None:
        if result not in VALID_RESULTS:
            raise ValueError(f"Unknown risk verdict result: {result!r}")
        where_clauses.append("result = :result")
        params["result"] = result
    if trade_mode is not None:
        if trade_mode not in VALID_TRADE_MODES:
            raise ValueError(f"Unknown trade mode: {trade_mode!r}")
        where_clauses.append("trade_mode = :trade_mode")
        params["trade_mode"] = trade_mode
    if symbol is not None:
        where_clauses.append("symbol = :symbol")
        params["symbol"] = symbol.upper()
    if decision_context_id is not None:
        where_clauses.append("decision_context_id = :decision_context_id")
        params["decision_context_id"] = decision_context_id
    if order_id is not None:
        where_clauses.append("order_id = :order_id")
        params["order_id"] = order_id
    if plan_id is not None:
        where_clauses.append("plan_id = :plan_id")
        params["plan_id"] = plan_id
    if candidate_id is not None:
        where_clauses.append("candidate_id = :candidate_id")
        params["candidate_id"] = candidate_id

    where_sql = " AND ".join(where_clauses)

    count_result = await db.execute(
        text(f"SELECT COUNT(*) FROM {TABLE_RISK_VERDICTS} WHERE {where_sql}"),
        params,
    )
    total = count_result.scalar() or 0

    params["limit"] = page_size
    params["offset"] = offset
    rows_result = await db.execute(
        text(
            f"""
            SELECT id, verdict_id, tenant_id, owner_user_id, account_id, result,
                   scope, trade_mode, symbol, order_id, plan_id, candidate_id,
                   decision_context_id, details, created_at
            FROM {TABLE_RISK_VERDICTS}
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
    details = row[13] if isinstance(row[13], dict) else json.loads(row[13] or "{}")
    return {
        "id": row[0],
        "verdict_id": row[1],
        "tenant_id": row[2],
        "owner_user_id": row[3],
        "account_id": row[4],
        "result": row[5],
        "scope": row[6],
        "trade_mode": row[7],
        "symbol": row[8],
        "order_id": row[9],
        "plan_id": row[10],
        "candidate_id": row[11],
        "decision_context_id": row[12],
        "details": details,
        "created_at": row[14].isoformat() if row[14] else None,
    }
