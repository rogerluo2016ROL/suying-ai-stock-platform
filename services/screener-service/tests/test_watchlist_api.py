"""Tests for watchlist REST endpoints (POST/GET/DELETE /api/v1/screener/watchlist).

Scope isolation contract:
  - account A adds a stock → account B cannot see/remove it (private scope)
  - visibility=public → cross-account visible
  - scope 全部从认证头注入，请求体不携带明文 scope
"""

import os
import sys
from datetime import datetime, timezone

import pytest
from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "packages", "kronos-factors"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.routers import screener as screener_router
from app.routers.screener import router


def _client(db=None):
    app = FastAPI()
    app.include_router(router)
    if db is not None:
        async def _override_get_db():
            yield db
        app.dependency_overrides[screener_router.get_db] = _override_get_db
    else:
        async def _override_get_db_none():
            yield None
        app.dependency_overrides[screener_router.get_db] = _override_get_db_none
    return TestClient(app)


# ── In-memory PG stub mirroring watchlist scope semantics ──

_COLS = [
    "id", "tenant_id", "owner_user_id", "account_id", "visibility", "data_scope",
    "code", "name", "notes", "sort_order", "added_at", "updated_at", "metadata",
]


class _StubRow:
    def __init__(self, rec: dict):
        self._values = [rec.get(c) for c in _COLS]

    def __getitem__(self, idx):
        return self._values[idx]

    def __iter__(self):
        return iter(self._values)


class _ExecResult:
    def __init__(self, *, scalar_value=None, rows=None, row=None):
        self._scalar = scalar_value
        self._rows = rows or []
        self._row = row

    def scalar(self):
        return self._scalar

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._row


class _StubDb:
    """Captures INSERT / SELECT / DELETE on watchlist with scope filtering."""

    def __init__(self):
        self.rows: list[dict] = []
        self._seq = 0
        self.committed = False

    async def execute(self, statement, params=None):
        sql = str(statement)
        params = params or {}

        if "INSERT INTO watchlist" in sql:
            self._seq += 1
            import json as _json
            rec = {
                "id": 2000 + self._seq,
                "tenant_id": params["tenant_id"],
                "owner_user_id": params["owner_user_id"],
                "account_id": params["account_id"],
                "visibility": params["visibility"],
                "data_scope": params["data_scope"],
                "code": params["code"],
                "name": params["name"],
                "notes": params["notes"],
                "sort_order": params["sort_order"],
                "added_at": datetime(2026, 7, 3, 9, 25, tzinfo=timezone.utc),
                "updated_at": datetime(2026, 7, 3, 9, 25, tzinfo=timezone.utc),
                "metadata": _json.loads(params["metadata"]) if isinstance(params["metadata"], str) else (params["metadata"] or {}),
            }
            # UPSERT on (code, scope) — replace existing
            existing = next(
                (r for r in self.rows if r["code"] == rec["code"]
                 and r.get("tenant_id") == rec["tenant_id"]
                 and (r.get("owner_user_id") or "") == (rec.get("owner_user_id") or "")
                 and (r.get("account_id") or "") == (rec.get("account_id") or "")),
                None,
            )
            if existing:
                rec["id"] = existing["id"]
                self.rows.remove(existing)
            self.rows.append(rec)
            return _ExecResult(row=_StubRow(rec))

        if "SELECT COUNT(*) FROM watchlist" in sql:
            return _ExecResult(scalar_value=len(self._filtered(params, where_from=params)))

        if "SELECT id, tenant_id, owner_user_id" in sql or "DELETE FROM watchlist" in sql:
            filtered = self._filtered(params, where_from=params)
            if "DELETE FROM watchlist" in sql:
                # Actually remove the matched rows, return one id per deleted row.
                for r in filtered:
                    self.rows.remove(r)
                return _ExecResult(rows=[_StubRow(r) for r in filtered])
            limit = params.get("limit")
            offset = params.get("offset", 0)
            if limit is not None:
                filtered = filtered[offset:offset + limit]
            else:
                filtered = filtered[offset:]
            return _ExecResult(rows=[_StubRow(r) for r in filtered])

        return _ExecResult()

    def _filtered(self, params: dict, where_from: dict) -> list[dict]:
        """Replicate watchlist_store._scope_where + code/row_id filters."""
        out = []
        for r in self.rows:
            if "tenant_id" in params:
                if not (r["visibility"] == "public" or r["tenant_id"] == params["tenant_id"]):
                    continue
            if "owner_user_id" in params:
                if not (r["visibility"] in ("public", "tenant_shared") or r["owner_user_id"] == params["owner_user_id"]):
                    continue
            if "account_id" in params:
                if not (r["data_scope"] != "account" or r["account_id"] is None or r["account_id"] == params["account_id"]):
                    continue
            if "code" in params and r["code"] != params["code"]:
                continue
            if "row_id" in params and r["id"] != params["row_id"]:
                continue
            out.append(r)
        out.sort(key=lambda x: (x["sort_order"], -x["added_at"].timestamp()))
        return out

    async def commit(self):
        self.committed = True

    async def rollback(self):
        pass


# ── POST /watchlist ──

def test_post_adds_stock_returns_record():
    db = _StubDb()
    r = _client(db).post(
        "/api/v1/screener/watchlist",
        headers={"X-Tenant-Id": "t", "X-Owner-User-Id": "7", "X-Trade-Account-Id": "paper-u7"},
        json={"code": "300750", "name": "宁德时代", "notes": "看突破", "sort_order": 1},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    rec = body["record"]
    assert rec["code"] == "300750"
    assert rec["name"] == "宁德时代"
    assert rec["id"] is not None
    assert rec["added_at"] is not None
    assert body.get("fallback_reason") is None
    assert db.committed is True


def test_post_db_unavailable_returns_fallback():
    r = _client().post(
        "/api/v1/screener/watchlist",
        headers={"X-Tenant-Id": "t", "X-Owner-User-Id": "1", "X-Trade-Account-Id": "a1"},
        json={"code": "600519"},
    )
    body = r.json()
    assert body["fallback_reason"] == "db_session_unavailable"
    assert body["record"] is None


def test_post_body_has_no_plaintext_scope_fields():
    """AC-②: scope 绝不出现在请求体 schema（只有 Header 注入）。"""
    model = screener_router.WatchlistAddRequest.model_json_schema()
    props = set(model.get("properties", {}).keys())
    forbidden = {"tenant_id", "owner_user_id", "account_id"}
    assert not (props & forbidden), f"scope fields leaked into request body: {props & forbidden}"


# ── GET /watchlist ──

def test_get_returns_records_for_current_scope():
    db = _StubDb()
    c = _client(db)
    c.post("/api/v1/screener/watchlist",
           headers={"X-Tenant-Id": "t", "X-Owner-User-Id": "A", "X-Trade-Account-Id": "accA"},
           json={"code": "300750", "name": "A1"})
    c.post("/api/v1/screener/watchlist",
           headers={"X-Tenant-Id": "t", "X-Owner-User-Id": "B", "X-Trade-Account-Id": "accB"},
           json={"code": "600519", "name": "B1"})

    r = c.get("/api/v1/screener/watchlist",
              headers={"X-Tenant-Id": "t", "X-Owner-User-Id": "A", "X-Trade-Account-Id": "accA"})
    body = r.json()
    assert body["total"] == 1
    assert body["records"][0]["code"] == "300750"
    assert body.get("empty_state") is None


def test_get_scope_isolation_account_a_invisible_to_account_b():
    """AC-⑤: 账户 A 加的 → 账户 B 查不到（private/account 隔离）。"""
    db = _StubDb()
    c = _client(db)
    c.post("/api/v1/screener/watchlist",
           headers={"X-Tenant-Id": "t", "X-Owner-User-Id": "A", "X-Trade-Account-Id": "accA"},
           json={"code": "300750", "visibility": "private", "data_scope": "account"})

    r = c.get("/api/v1/screener/watchlist",
              headers={"X-Tenant-Id": "t", "X-Owner-User-Id": "B", "X-Trade-Account-Id": "accB"})
    body = r.json()
    assert body["total"] == 0
    assert body["records"] == []
    assert body["empty_state"]["hint"] == "no_visible_stocks"


def test_get_public_visibility_cross_account_visible():
    """AC-⑤: visibility=public 跨账户可见。"""
    db = _StubDb()
    c = _client(db)
    c.post("/api/v1/screener/watchlist",
           headers={"X-Tenant-Id": "t", "X-Owner-User-Id": "A", "X-Trade-Account-Id": "accA"},
           json={"code": "300750", "visibility": "public", "data_scope": "public"})

    r = c.get("/api/v1/screener/watchlist",
              headers={"X-Tenant-Id": "t", "X-Owner-User-Id": "B", "X-Trade-Account-Id": "accB"})
    body = r.json()
    assert body["total"] == 1
    assert body["records"][0]["visibility"] == "public"


def test_get_db_unavailable_returns_empty_with_fallback():
    r = _client().get("/api/v1/screener/watchlist")
    body = r.json()
    assert body["total"] == 0
    assert body["fallback_reason"] == "db_session_unavailable"
    assert body["empty_state"]["hint"] == "db_session_unavailable"


# ── DELETE /watchlist ──

def test_delete_by_code_removes_for_own_scope():
    db = _StubDb()
    c = _client(db)
    add = c.post("/api/v1/screener/watchlist",
                 headers={"X-Tenant-Id": "t", "X-Owner-User-Id": "A", "X-Trade-Account-Id": "accA"},
                 json={"code": "300750"})
    assert add.json()["record"] is not None

    r = c.delete("/api/v1/screener/watchlist?code=300750",
                 headers={"X-Tenant-Id": "t", "X-Owner-User-Id": "A", "X-Trade-Account-Id": "accA"})
    body = r.json()
    assert body["deleted"] == 1


def test_delete_by_code_blocked_for_other_scope():
    """AC-④: scope 校验归属——账户 A 加的，账户 B 删不掉（deleted=0）。"""
    db = _StubDb()
    c = _client(db)
    c.post("/api/v1/screener/watchlist",
           headers={"X-Tenant-Id": "t", "X-Owner-User-Id": "A", "X-Trade-Account-Id": "accA"},
           json={"code": "300750", "visibility": "private", "data_scope": "account"})

    r = c.delete("/api/v1/screener/watchlist?code=300750",
                 headers={"X-Tenant-Id": "t", "X-Owner-User-Id": "B", "X-Trade-Account-Id": "accB"})
    body = r.json()
    assert body["deleted"] == 0

    # stock still there for A
    r2 = c.get("/api/v1/screener/watchlist",
               headers={"X-Tenant-Id": "t", "X-Owner-User-Id": "A", "X-Trade-Account-Id": "accA"})
    assert r2.json()["total"] == 1


def test_delete_requires_code_or_id():
    db = _StubDb()
    r = _client(db).delete("/api/v1/screener/watchlist",
                           headers={"X-Tenant-Id": "t", "X-Owner-User-Id": "A", "X-Trade-Account-Id": "accA"})
    assert r.status_code == 400
    assert "code 或 id" in r.json()["detail"]


def test_delete_db_unavailable_returns_fallback():
    r = _client().delete("/api/v1/screener/watchlist?code=300750")
    body = r.json()
    assert body["deleted"] == 0
    assert body["fallback_reason"] == "db_session_unavailable"


# ── OpenAPI contract (orval-friendly) ──

def test_endpoints_declare_response_model_and_operation_id():
    op_ids = {getattr(r, "operation_id", None) for r in router.routes}
    assert "add_watchlist" in op_ids
    assert "list_watchlist" in op_ids
    assert "remove_watchlist" in op_ids

    add_route = next(r for r in router.routes if getattr(r, "operation_id", None) == "add_watchlist")
    list_route = next(r for r in router.routes if getattr(r, "operation_id", None) == "list_watchlist")
    del_route = next(r for r in router.routes if getattr(r, "operation_id", None) == "remove_watchlist")
    assert add_route.response_model is screener_router.WatchlistAddResponse
    assert list_route.response_model is screener_router.WatchlistQueryResponse
    assert del_route.response_model is screener_router.WatchlistDeleteResponse
