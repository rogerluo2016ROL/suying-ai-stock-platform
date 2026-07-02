"""Watchlist persistence for platform-scoped self-selected stocks.

Mirrors candidate_pool_store's scope-filtering model so the REST layer can stay
thin: tenant_id / owner_user_id / account_id / visibility / data_scope flow
through every call and the WHERE clauses here enforce the same private /
tenant_shared / public visibility matrix.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

try:
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession
except ModuleNotFoundError:
    AsyncSession = Any  # type: ignore[misc,assignment]

    def text(sql: str) -> str:  # type: ignore[no-redef]
        return sql


TABLE_WATCHLIST = "watchlist"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _scope_where(
    *,
    tenant_id: str | None,
    owner_user_id: str | None,
    account_id: str | None,
) -> tuple[str, dict[str, Any]]:
    """Build the visibility-aware scope filter used by list() and remove().

    Mirrors candidate_pool_store.query semantics:
      - tenant_id set   → visibility='public' OR same tenant
      - owner_user_id   → visibility IN ('public','tenant_shared') OR same owner
      - account_id      → data_scope != 'account' OR account_id IS NULL OR same account
    """
    clauses = ["1=1"]
    params: dict[str, Any] = {}
    if tenant_id is not None:
        clauses.append("(visibility = 'public' OR tenant_id = :tenant_id)")
        params["tenant_id"] = tenant_id
    if owner_user_id is not None:
        clauses.append(
            "(visibility IN ('public', 'tenant_shared') OR owner_user_id = :owner_user_id)"
        )
        params["owner_user_id"] = owner_user_id
    if account_id is not None:
        clauses.append(
            "(data_scope != 'account' OR account_id IS NULL OR account_id = :account_id)"
        )
        params["account_id"] = account_id
    return " AND ".join(clauses), params


async def add(
    db: AsyncSession,
    *,
    tenant_id: str,
    owner_user_id: str | None,
    account_id: str | None,
    code: str,
    name: str | None = None,
    notes: str | None = None,
    sort_order: int = 0,
    metadata: dict[str, Any] | None = None,
    visibility: str = "private",
    data_scope: str = "account",
) -> dict[str, Any]:
    """Add a watchlist row for the given scope + code, or update if it exists.

    Re-adding an existing (scope, code) stock updates name/notes/sort_order/
    metadata/visibility/data_scope in place rather than creating a duplicate.
    Existing-row detection uses an exact scope match (read-then-write); the
    unique index on (code, account_id) guards account-scope concurrency.
    """
    now = _now()
    existing = await find_one(
        db,
        tenant_id=tenant_id,
        owner_user_id=owner_user_id,
        account_id=account_id,
        code=code,
    )
    if existing is not None:
        await db.execute(
            text(
                f"""
                UPDATE {TABLE_WATCHLIST} SET
                    name = :name,
                    notes = :notes,
                    sort_order = :sort_order,
                    metadata = CAST(:metadata AS jsonb),
                    visibility = :visibility,
                    data_scope = :data_scope,
                    updated_at = :updated_at
                WHERE id = :row_id
                """
            ),
            {
                "row_id": existing["id"],
                "name": name,
                "notes": notes,
                "sort_order": sort_order,
                "metadata": json.dumps(metadata or {}, ensure_ascii=False),
                "visibility": visibility,
                "data_scope": data_scope,
                "updated_at": now,
            },
        )
        # Re-read the updated row to return canonical shape.
        return await find_one(
            db,
            tenant_id=tenant_id,
            owner_user_id=owner_user_id,
            account_id=account_id,
            code=code,
        ) or existing

    result = await db.execute(
        text(
            f"""
            INSERT INTO {TABLE_WATCHLIST}
                (tenant_id, owner_user_id, account_id, visibility, data_scope,
                 code, name, notes, sort_order, metadata, added_at, updated_at)
            VALUES
                (:tenant_id, :owner_user_id, :account_id, :visibility, :data_scope,
                 :code, :name, :notes, :sort_order,
                 CAST(:metadata AS jsonb), :added_at, :updated_at)
            RETURNING id, tenant_id, owner_user_id, account_id, visibility, data_scope,
                      code, name, notes, sort_order, added_at, updated_at, metadata
            """
        ),
        {
            "tenant_id": tenant_id,
            "owner_user_id": owner_user_id,
            "account_id": account_id,
            "visibility": visibility,
            "data_scope": data_scope,
            "code": code,
            "name": name,
            "notes": notes,
            "sort_order": sort_order,
            "metadata": json.dumps(metadata or {}, ensure_ascii=False),
            "added_at": now,
            "updated_at": now,
        },
    )
    row = result.fetchone()
    return _row_to_record(row)


async def query(
    db: AsyncSession,
    *,
    tenant_id: str | None = None,
    owner_user_id: str | None = None,
    account_id: str | None = None,
    code: str | None = None,
    page: int = 1,
    page_size: int = 100,
) -> dict[str, Any]:
    """Page through watchlist rows visible to the given scope."""
    page_size = min(page_size, 500)
    offset = (page - 1) * page_size

    where_sql, params = _scope_where(
        tenant_id=tenant_id, owner_user_id=owner_user_id, account_id=account_id
    )
    if code is not None:
        where_sql += " AND code = :code"
        params["code"] = code

    count_result = await db.execute(
        text(f"SELECT COUNT(*) FROM {TABLE_WATCHLIST} WHERE {where_sql}"),
        params,
    )
    total = count_result.scalar() or 0

    params["limit"] = page_size
    params["offset"] = offset
    rows_result = await db.execute(
        text(
            f"""
            SELECT id, tenant_id, owner_user_id, account_id, visibility, data_scope,
                   code, name, notes, sort_order, added_at, updated_at, metadata
            FROM {TABLE_WATCHLIST}
            WHERE {where_sql}
            ORDER BY sort_order ASC, added_at DESC
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


async def find_one(
    db: AsyncSession,
    *,
    tenant_id: str | None,
    owner_user_id: str | None,
    account_id: str | None,
    code: str,
) -> dict[str, Any] | None:
    """Return the single scope-visible watchlist row for `code`, or None."""
    where_sql, params = _scope_where(
        tenant_id=tenant_id, owner_user_id=owner_user_id, account_id=account_id
    )
    where_sql += " AND code = :code"
    params["code"] = code
    result = await db.execute(
        text(
            f"""
            SELECT id, tenant_id, owner_user_id, account_id, visibility, data_scope,
                   code, name, notes, sort_order, added_at, updated_at, metadata
            FROM {TABLE_WATCHLIST}
            WHERE {where_sql}
            LIMIT 1
            """
        ),
        params,
    )
    row = result.fetchone()
    return _row_to_record(row) if row else None


async def remove_by_id(
    db: AsyncSession,
    *,
    tenant_id: str | None,
    owner_user_id: str | None,
    account_id: str | None,
    row_id: int,
) -> int:
    """Delete a watchlist row by id, but only if it is visible to the scope.

    Returns the number of rows deleted (0 if not found or out of scope).
    """
    where_sql, params = _scope_where(
        tenant_id=tenant_id, owner_user_id=owner_user_id, account_id=account_id
    )
    where_sql += " AND id = :row_id"
    params["row_id"] = row_id
    result = await db.execute(
        text(f"DELETE FROM {TABLE_WATCHLIST} WHERE {where_sql} RETURNING id"),
        params,
    )
    return 1 if result.fetchone() else 0


async def remove_by_code(
    db: AsyncSession,
    *,
    tenant_id: str | None,
    owner_user_id: str | None,
    account_id: str | None,
    code: str,
) -> int:
    """Delete watchlist row(s) for `code` visible to the scope (scope-ownership guarded)."""
    where_sql, params = _scope_where(
        tenant_id=tenant_id, owner_user_id=owner_user_id, account_id=account_id
    )
    where_sql += " AND code = :code"
    params["code"] = code
    result = await db.execute(
        text(f"DELETE FROM {TABLE_WATCHLIST} WHERE {where_sql} RETURNING id"),
        params,
    )
    return len(result.fetchall())


def _json(value: Any, default: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    return json.loads(value or json.dumps(default, ensure_ascii=False))


def _iso(value: Any) -> str | None:
    return value.isoformat() if hasattr(value, "isoformat") else value


def _row_to_record(row: Any) -> dict[str, Any]:
    return {
        "id": row[0],
        "tenant_id": row[1],
        "owner_user_id": row[2],
        "account_id": row[3],
        "visibility": row[4],
        "data_scope": row[5],
        "code": row[6],
        "name": row[7],
        "notes": row[8],
        "sort_order": row[9],
        "added_at": _iso(row[10]),
        "updated_at": _iso(row[11]),
        "metadata": _json(row[12], {}),
    }
