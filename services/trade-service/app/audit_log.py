"""AuditLog — append-only audit trail for all trading operations.

Design (per ADR-002 Decision 4):
- ``audit_logs`` table: INSERT-only, no UPDATE/DELETE allowed (enforced by DB trigger).
- ``record()`` writes an audit entry.
- ``query()`` provides read-only filtered access.

The module accepts a SQLAlchemy async session, making it backend-agnostic.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Select, text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("trade-service.audit_log")

# ── Table name ─────────────────────────────────────────────────────────
TABLE_AUDIT_LOGS = "audit_logs"

# ── Valid event types ──────────────────────────────────────────────────
VALID_ACTIONS = frozenset({
    "PLACE_ORDER",
    "CANCEL_ORDER",
    "MODE_SWITCH",
    "BROKER_CONNECT",
    "BROKER_DISCONNECT",
    "RISK_REJECT",
    "CIRCUIT_BREAKER",
    "POSITION_SYNC",
})


async def record(
    db: AsyncSession,
    *,
    user_id: int | None = None,
    action: str,
    mode: str,
    details: dict[str, Any] | None = None,
    symbol: str | None = None,
    order_id: str | None = None,
    client_ip: str | None = None,
) -> int:
    """Insert an immutable audit log entry.

    Args:
        db: An active async SQLAlchemy session.
        user_id: Operator user ID (None = system action).
        action: One of ``VALID_ACTIONS``.
        mode: ``"paper"`` or ``"live"``.
        details: Arbitrary JSON-serialisable context (request, response, risk results).
        symbol: Related stock code (optional).
        order_id: Related order ID (optional).
        client_ip: Source IP address (optional).

    Returns:
        The ``id`` of the newly inserted row.

    Raises:
        ValueError: If ``action`` is not a recognised event type.
    """
    if action not in VALID_ACTIONS:
        raise ValueError(
            f"Unknown audit action: {action!r}. Must be one of {sorted(VALID_ACTIONS)}"
        )

    payload = json.dumps(details or {}, ensure_ascii=False)

    result = await db.execute(
        text(
            f"""
            INSERT INTO {TABLE_AUDIT_LOGS}
                (user_id, action, mode, details, symbol, order_id, client_ip, created_at)
            VALUES
                (:user_id, :action, :mode, CAST(:details AS jsonb),
                 :symbol, :order_id, :client_ip, :created_at)
            RETURNING id
            """
        ),
        {
            "user_id": user_id,
            "action": action,
            "mode": mode,
            "details": payload,
            "symbol": symbol,
            "order_id": order_id,
            "client_ip": client_ip,
            "created_at": datetime.now(timezone.utc),
        },
    )
    row = result.fetchone()
    audit_id = row[0] if row else -1
    logger.debug("Audit #%d: %s by user=%s mode=%s", audit_id, action, user_id, mode)
    return audit_id


async def query(
    db: AsyncSession,
    *,
    user_id: int | None = None,
    action: str | None = None,
    mode: str | None = None,
    symbol: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    page: int = 1,
    page_size: int = 50,
) -> dict[str, Any]:
    """Read-only audit log query with pagination.

    Args:
        db: Active async session.
        user_id: Filter by operator.
        action: Filter by action type.
        mode: Filter by trade mode (paper/live).
        symbol: Filter by stock code.
        start: Start of time range (inclusive).
        end: End of time range (inclusive).
        page: 1-based page number.
        page_size: Records per page (max 200).

    Returns:
        Dict with ``total``, ``page``, ``page_size``, ``records``.
    """
    page_size = min(page_size, 200)
    offset = (page - 1) * page_size

    where_clauses = ["1=1"]
    params: dict[str, Any] = {}

    if user_id is not None:
        where_clauses.append("user_id = :user_id")
        params["user_id"] = user_id
    if action is not None:
        where_clauses.append("action = :action")
        params["action"] = action
    if mode is not None:
        where_clauses.append("mode = :mode")
        params["mode"] = mode
    if symbol is not None:
        where_clauses.append("symbol = :symbol")
        params["symbol"] = symbol
    if start is not None:
        where_clauses.append("created_at >= :start")
        params["start"] = start
    if end is not None:
        where_clauses.append("created_at <= :end")
        params["end"] = end

    where_sql = " AND ".join(where_clauses)

    # Count
    count_result = await db.execute(
        text(f"SELECT COUNT(*) FROM {TABLE_AUDIT_LOGS} WHERE {where_sql}"),
        params,
    )
    total = count_result.scalar() or 0

    # Fetch
    params["limit"] = page_size
    params["offset"] = offset
    rows_result = await db.execute(
        text(
            f"""
            SELECT id, user_id, action, mode, details, symbol, order_id,
                   client_ip, created_at
            FROM {TABLE_AUDIT_LOGS}
            WHERE {where_sql}
            ORDER BY created_at DESC
            LIMIT :limit OFFSET :offset
            """
        ),
        params,
    )

    records: list[dict[str, Any]] = []
    for row in rows_result.fetchall():
        records.append({
            "id": row[0],
            "user_id": row[1],
            "action": row[2],
            "mode": row[3],
            "details": row[4] if isinstance(row[4], dict) else json.loads(row[4] or "{}"),
            "symbol": row[5],
            "order_id": row[6],
            "client_ip": row[7],
            "created_at": row[8].isoformat() if row[8] else None,
        })

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "records": records,
    }
