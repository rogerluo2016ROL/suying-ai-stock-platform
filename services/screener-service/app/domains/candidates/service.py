"""Candidate-pool domain behavior independent of the legacy screening module."""

import logging
from datetime import datetime

from app import candidate_pool_store, watchlist_store
from app.domains.candidates.models import (
    CandidatePoolQueryResponse, CandidatePoolRecordResponse,
    WatchlistAddResponse, WatchlistDeleteResponse, WatchlistItemResponse, WatchlistQueryResponse,
)

logger = logging.getLogger("screener.candidates")


def resolve_candidate_pool_scope(*, data_scope: str, visibility: str, account_id: str | None, owner_user_id: str | None) -> tuple[str, str]:
    scope = data_scope or ("account" if (account_id or owner_user_id) else "public")
    resolved_visibility = "public" if scope == "public" else (
        visibility if visibility in ("private", "tenant_shared", "public") else "private"
    )
    return scope, resolved_visibility


def build_candidate_pool_id(*, source_mode: str, trade_date: str, time_slot: str, account_id: str | None, owner_user_id: str | None) -> str:
    scope_key = account_id or owner_user_id or "public"
    return f"POOL-{source_mode}-{trade_date}-{time_slot.replace(':', '')}-{scope_key}"


async def record_candidate_pool(*, db, payload, tenant_id: str | None, owner_user_id: str | None, account_id: str | None):
    if db is None:
        return CandidatePoolRecordResponse(pool_id="", fallback_reason="db_session_unavailable")
    scope, visibility = resolve_candidate_pool_scope(
        data_scope=payload.data_scope, visibility=payload.visibility,
        account_id=account_id, owner_user_id=owner_user_id,
    )
    trade_date = payload.trade_date or datetime.now().strftime("%Y-%m-%d")
    time_slot = payload.time_slot or datetime.now().strftime("%H:%M")
    pool_id = build_candidate_pool_id(
        source_mode=payload.source_mode, trade_date=trade_date, time_slot=time_slot,
        account_id=account_id, owner_user_id=owner_user_id,
    )
    try:
        row_id = await candidate_pool_store.record(
            db, pool_id=pool_id, tenant_id=tenant_id or "tenant-default",
            owner_user_id=owner_user_id, account_id=account_id,
            source_module=payload.source_module, source_mode=payload.source_mode,
            name=payload.name, candidates=payload.candidates,
            metadata=payload.candidate_pool_metadata, visibility=visibility, data_scope=scope,
        )
        await db.commit()
        created_at = None
        if row_id is not None:
            try:
                from sqlalchemy import text
                result = await db.execute(text("SELECT created_at FROM candidate_pools WHERE id = :id"), {"id": row_id})
                value = result.scalar()
                created_at = value.isoformat() if hasattr(value, "isoformat") else (str(value) if value is not None else None)
            except Exception:
                pass
        return CandidatePoolRecordResponse(pool_id=pool_id, id=row_id, created_at=created_at)
    except Exception as exc:
        try:
            await db.rollback()
        except Exception:
            pass
        logger.warning("candidate pool persistence failed: %s", exc)
        return CandidatePoolRecordResponse(pool_id=pool_id, fallback_reason=f"persist_failed: {exc}")


async def query_candidate_pool(*, db, tenant_id: str | None, owner_user_id: str | None, account_id: str | None, source_module: str | None, source_mode: str | None, page: int, page_size: int):
    if db is None:
        return CandidatePoolQueryResponse(total=0, page=page, page_size=page_size, records=[], empty_state={"hint": "db_session_unavailable", "suggestion": "稍后重试或联系管理员"}, fallback_reason="db_session_unavailable")
    try:
        result = await candidate_pool_store.query(
            db, tenant_id=tenant_id, owner_user_id=owner_user_id, account_id=account_id,
            source_module=source_module, source_mode=source_mode, page=page, page_size=page_size,
        )
        records = result.get("records", [])
        empty_state = None if records else {"hint": "no_visible_pools", "suggestion": "运行选股后自动落库，或检查平台 scope 是否正确"}
        return CandidatePoolQueryResponse(total=result.get("total", 0), page=result.get("page", page), page_size=result.get("page_size", page_size), records=records, empty_state=empty_state)
    except Exception as exc:
        logger.warning("candidate pool query failed: %s", exc)
        return CandidatePoolQueryResponse(total=0, page=page, page_size=page_size, records=[], empty_state={"hint": "query_failed", "suggestion": str(exc)}, fallback_reason=f"query_failed: {exc}")


async def add_watchlist(*, db, payload, tenant_id, owner_user_id, account_id):
    if db is None:
        return WatchlistAddResponse(fallback_reason="db_session_unavailable")
    scope, visibility = resolve_candidate_pool_scope(data_scope=payload.data_scope, visibility=payload.visibility, account_id=account_id, owner_user_id=owner_user_id)
    try:
        record = await watchlist_store.add(db, tenant_id=tenant_id or "tenant-default", owner_user_id=owner_user_id, account_id=account_id, code=payload.code, name=payload.name, notes=payload.notes, sort_order=payload.sort_order, metadata=payload.watchlist_metadata, visibility=visibility, data_scope=scope)
        await db.commit()
        return WatchlistAddResponse(record=WatchlistItemResponse(**record))
    except Exception as exc:
        try: await db.rollback()
        except Exception: pass
        return WatchlistAddResponse(fallback_reason=f"persist_failed: {exc}")


async def list_watchlist(*, db, code, page, page_size, tenant_id, owner_user_id, account_id):
    if db is None:
        return WatchlistQueryResponse(total=0, page=page, page_size=page_size, records=[], empty_state={"hint": "db_session_unavailable", "suggestion": "稍后重试或联系管理员"}, fallback_reason="db_session_unavailable")
    try:
        result = await watchlist_store.query(db, tenant_id=tenant_id, owner_user_id=owner_user_id, account_id=account_id, code=code, page=page, page_size=page_size)
        records = [WatchlistItemResponse(**row) for row in result.get("records", [])]
        empty_state = None if records else {"hint": "no_visible_stocks", "suggestion": "加入自选后重试，或检查平台 scope 是否正确"}
        return WatchlistQueryResponse(total=result.get("total", 0), page=result.get("page", page), page_size=result.get("page_size", page_size), records=records, empty_state=empty_state)
    except Exception as exc:
        return WatchlistQueryResponse(total=0, page=page, page_size=page_size, records=[], empty_state={"hint": "query_failed", "suggestion": str(exc)}, fallback_reason=f"query_failed: {exc}")


async def remove_watchlist(*, db, code, row_id, tenant_id, owner_user_id, account_id):
    if db is None:
        return WatchlistDeleteResponse(deleted=0, code=code, id=row_id, fallback_reason="db_session_unavailable")
    try:
        if row_id is not None:
            deleted = await watchlist_store.remove_by_id(db, tenant_id=tenant_id, owner_user_id=owner_user_id, account_id=account_id, row_id=row_id)
        else:
            deleted = await watchlist_store.remove_by_code(db, tenant_id=tenant_id, owner_user_id=owner_user_id, account_id=account_id, code=code)
        await db.commit()
        return WatchlistDeleteResponse(deleted=deleted, code=code, id=row_id)
    except Exception as exc:
        try: await db.rollback()
        except Exception: pass
        return WatchlistDeleteResponse(deleted=0, code=code, id=row_id, fallback_reason=f"remove_failed: {exc}")
