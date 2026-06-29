"""CandidatePool persistence for platform-scoped candidate snapshots."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

TABLE_CANDIDATE_POOLS = "candidate_pools"


async def record(
    db: AsyncSession,
    *,
    pool_id: str,
    tenant_id: str,
    owner_user_id: str | None,
    account_id: str | None,
    source_module: str,
    source_mode: str,
    name: str,
    candidates: list[dict[str, Any]],
    metadata: dict[str, Any] | None = None,
    visibility: str = "private",
    data_scope: str = "account",
) -> int | None:
    result = await db.execute(
        text(
            f"""
            INSERT INTO {TABLE_CANDIDATE_POOLS}
                (pool_id, tenant_id, owner_user_id, account_id, visibility,
                 data_scope, source_module, source_mode, name, candidates,
                 metadata, created_at, updated_at)
            VALUES
                (:pool_id, :tenant_id, :owner_user_id, :account_id, :visibility,
                 :data_scope, :source_module, :source_mode, :name,
                 CAST(:candidates AS jsonb), CAST(:metadata AS jsonb),
                 :created_at, :updated_at)
            ON CONFLICT (pool_id) DO UPDATE SET
                tenant_id = EXCLUDED.tenant_id,
                owner_user_id = EXCLUDED.owner_user_id,
                account_id = EXCLUDED.account_id,
                visibility = EXCLUDED.visibility,
                data_scope = EXCLUDED.data_scope,
                source_module = EXCLUDED.source_module,
                source_mode = EXCLUDED.source_mode,
                name = EXCLUDED.name,
                candidates = EXCLUDED.candidates,
                metadata = EXCLUDED.metadata,
                updated_at = EXCLUDED.updated_at
            RETURNING id
            """
        ),
        {
            "pool_id": pool_id,
            "tenant_id": tenant_id,
            "owner_user_id": owner_user_id,
            "account_id": account_id,
            "visibility": visibility,
            "data_scope": data_scope,
            "source_module": source_module,
            "source_mode": source_mode,
            "name": name,
            "candidates": json.dumps(candidates, ensure_ascii=False),
            "metadata": json.dumps(metadata or {}, ensure_ascii=False),
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
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
    pool_id: str | None = None,
    source_module: str | None = None,
    source_mode: str | None = None,
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
    if pool_id is not None:
        where_clauses.append("pool_id = :pool_id")
        params["pool_id"] = pool_id
    if source_module is not None:
        where_clauses.append("source_module = :source_module")
        params["source_module"] = source_module
    if source_mode is not None:
        where_clauses.append("source_mode = :source_mode")
        params["source_mode"] = source_mode

    where_sql = " AND ".join(where_clauses)
    count_result = await db.execute(
        text(f"SELECT COUNT(*) FROM {TABLE_CANDIDATE_POOLS} WHERE {where_sql}"),
        params,
    )
    total = count_result.scalar() or 0

    params["limit"] = page_size
    params["offset"] = offset
    rows_result = await db.execute(
        text(
            f"""
            SELECT id, pool_id, tenant_id, owner_user_id, account_id,
                   visibility, data_scope, source_module, source_mode, name,
                   candidates, metadata, created_at, updated_at
            FROM {TABLE_CANDIDATE_POOLS}
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
        "records": [_row_to_record(row) for row in rows_result.fetchall()],
    }


def _json(value: Any, default: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    return json.loads(value or json.dumps(default, ensure_ascii=False))


def _iso(value: Any) -> str | None:
    return value.isoformat() if hasattr(value, "isoformat") else value


def _row_to_record(row: Any) -> dict[str, Any]:
    return {
        "id": row[0],
        "pool_id": row[1],
        "tenant_id": row[2],
        "owner_user_id": row[3],
        "account_id": row[4],
        "visibility": row[5],
        "data_scope": row[6],
        "source_module": row[7],
        "source_mode": row[8],
        "name": row[9],
        "candidates": _json(row[10], []),
        "metadata": _json(row[11], {}),
        "created_at": _iso(row[12]),
        "updated_at": _iso(row[13]),
    }
