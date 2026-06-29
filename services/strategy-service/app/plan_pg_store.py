"""PostgreSQL-backed Strategy Plan persistence.

The existing in-memory PlanStore remains the fallback used by current routes.
This module provides the durable store contract used by the platform migration
and can be wired into routes once the service-level DB dependency is enabled.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.plan_store import Plan

TABLE_STRATEGY_PLANS = "strategy_plans"


async def record(db: AsyncSession, *, plan: Plan) -> int | None:
    now = datetime.now(timezone.utc)
    result = await db.execute(
        text(
            f"""
            INSERT INTO {TABLE_STRATEGY_PLANS}
                (plan_id, name, status, model_name, capital, max_positions,
                 single_max_pct, tenant_id, owner_user_id, account_id,
                 visibility, data_scope, picks, created_at, updated_at)
            VALUES
                (:plan_id, :name, :status, :model_name, :capital, :max_positions,
                 :single_max_pct, :tenant_id, :owner_user_id, :account_id,
                 :visibility, :data_scope, CAST(:picks AS jsonb),
                 :created_at, :updated_at)
            ON CONFLICT (plan_id) DO UPDATE SET
                name = EXCLUDED.name,
                status = EXCLUDED.status,
                model_name = EXCLUDED.model_name,
                capital = EXCLUDED.capital,
                max_positions = EXCLUDED.max_positions,
                single_max_pct = EXCLUDED.single_max_pct,
                tenant_id = EXCLUDED.tenant_id,
                owner_user_id = EXCLUDED.owner_user_id,
                account_id = EXCLUDED.account_id,
                visibility = EXCLUDED.visibility,
                data_scope = EXCLUDED.data_scope,
                picks = EXCLUDED.picks,
                updated_at = EXCLUDED.updated_at
            RETURNING id
            """
        ),
        {
            "plan_id": plan.id,
            "name": plan.name,
            "status": plan.status,
            "model_name": plan.model_name,
            "capital": plan.capital,
            "max_positions": plan.max_positions,
            "single_max_pct": plan.single_max_pct,
            "tenant_id": plan.tenant_id,
            "owner_user_id": plan.owner_user_id,
            "account_id": plan.account_id,
            "visibility": plan.visibility,
            "data_scope": plan.data_scope,
            "picks": json.dumps(plan.picks, ensure_ascii=False),
            "created_at": plan.created_at or now,
            "updated_at": now,
        },
    )
    row = result.fetchone()
    return row[0] if row else None


async def query(
    db: AsyncSession,
    *,
    tenant_id: str | None = None,
    owner_user_id: str | None = None,
    account_id: str | None = None,
    plan_id: str | None = None,
    status: str | None = None,
    page: int = 1,
    page_size: int = 50,
) -> dict[str, Any]:
    page_size = min(page_size, 200)
    offset = (page - 1) * page_size

    where_clauses = ["1=1"]
    params: dict[str, Any] = {}
    if tenant_id is not None:
        where_clauses.append("(visibility = 'public' OR tenant_id = :tenant_id)")
        params["tenant_id"] = tenant_id
    if owner_user_id is not None:
        where_clauses.append("(visibility IN ('public', 'tenant_shared') OR owner_user_id = :owner_user_id)")
        params["owner_user_id"] = owner_user_id
    if account_id is not None:
        where_clauses.append("(data_scope != 'account' OR account_id IS NULL OR account_id = :account_id)")
        params["account_id"] = account_id
    if plan_id is not None:
        where_clauses.append("plan_id = :plan_id")
        params["plan_id"] = plan_id
    if status is not None:
        where_clauses.append("status = :status")
        params["status"] = status

    where_sql = " AND ".join(where_clauses)
    count_result = await db.execute(
        text(f"SELECT COUNT(*) FROM {TABLE_STRATEGY_PLANS} WHERE {where_sql}"),
        params,
    )
    total = count_result.scalar() or 0

    params["limit"] = page_size
    params["offset"] = offset
    rows_result = await db.execute(
        text(
            f"""
            SELECT id, plan_id, name, status, model_name, capital, max_positions,
                   single_max_pct, tenant_id, owner_user_id, account_id,
                   visibility, data_scope, picks, created_at, updated_at
            FROM {TABLE_STRATEGY_PLANS}
            WHERE {where_sql}
            ORDER BY updated_at DESC
            LIMIT :limit OFFSET :offset
            """
        ),
        params,
    )

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "plans": [_row_to_record(row) for row in rows_result.fetchall()],
    }


def _json(value: Any, default: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    return json.loads(value or json.dumps(default, ensure_ascii=False))


def _iso(value: Any) -> str | None:
    return value.isoformat() if hasattr(value, "isoformat") else value


def _row_to_record(row: Any) -> dict[str, Any]:
    return {
        "id": row[1],
        "row_id": row[0],
        "name": row[2],
        "status": row[3],
        "model_name": row[4],
        "capital": float(row[5]) if row[5] is not None else None,
        "max_positions": row[6],
        "single_max_pct": float(row[7]) if row[7] is not None else None,
        "tenant_id": row[8],
        "owner_user_id": row[9],
        "account_id": row[10],
        "visibility": row[11],
        "data_scope": row[12],
        "picks": _json(row[13], []),
        "picks_count": len(_json(row[13], [])),
        "created_at": _iso(row[14]),
        "updated_at": _iso(row[15]),
    }
