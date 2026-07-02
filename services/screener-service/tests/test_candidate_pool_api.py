"""Tests for candidate-pool REST endpoints (POST/GET /api/v1/screener/candidate-pool).

Scope isolation contract:
  - account A writes → account B cannot read it (private scope)
  - public visibility → cross-account readable
  - scope 全部从认证头注入，请求体不携带明文 scope
"""

import os
import sys
from datetime import datetime, timezone

import pytest

# Mock heavy optional deps so importing the router is cheap and deterministic.
from unittest.mock import MagicMock

for mod in ("openai", "tenacity"):
    if mod not in sys.modules:
        mock = type(sys)("mock_" + mod)
        if mod == "openai":
            mock.APIConnectionError = Exception
            mock.APIStatusError = Exception
            mock.AsyncOpenAI = MagicMock
            mock.OpenAI = MagicMock
        else:
            mock.retry = lambda *a, **k: (lambda f: f)
            mock.retry_if_exception_type = lambda *a, **k: None
            mock.stop_after_attempt = lambda *a, **k: None
            mock.wait_exponential = lambda *a, **k: None
        sys.modules[mod] = mock

from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "packages", "kronos-factors"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.routers import screener as screener_router
from app.routers.screener import router


def _client(db=None):
    """Create test client. If db is provided, override get_db to return it."""
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


# ── In-memory PG stub: emulates candidate_pools table with scope semantics ──

class _StubRow:
    """Mimics the 14-column select row shape used by candidate_pool_store._row_to_record.

    Supports both positional indexing (row[0..13]) and fetchall() iteration.
    """

    _COLUMNS = [
        "id", "pool_id", "tenant_id", "owner_user_id", "account_id",
        "visibility", "data_scope", "source_module", "source_mode", "name",
        "candidates", "metadata", "created_at", "updated_at",
    ]

    def __init__(self, rec: dict):
        self._values = [rec[c] for c in self._COLUMNS]

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
    """Captures INSERT/SELECT/COUNT against candidate_pools with scope filtering.

    Mirrors the visibility rules in candidate_pool_store.query so endpoint-level
    scope assertions reflect real filtering behavior.
    """

    def __init__(self):
        self.rows: list[dict] = []  # persisted records
        self._seq = 0
        self.committed = False

    async def execute(self, statement, params=None):
        sql = str(statement)
        params = params or {}

        if "INSERT INTO candidate_pools" in sql:
            self._seq += 1
            import json as _json
            rec = {
                "id": 1000 + self._seq,
                "pool_id": params["pool_id"],
                "tenant_id": params["tenant_id"],
                "owner_user_id": params["owner_user_id"],
                "account_id": params["account_id"],
                "visibility": params["visibility"],
                "data_scope": params["data_scope"],
                "source_module": params["source_module"],
                "source_mode": params["source_mode"],
                "name": params["name"],
                "candidates": _json.loads(params["candidates"]) if isinstance(params["candidates"], str) else params["candidates"],
                "metadata": _json.loads(params["metadata"]) if isinstance(params["metadata"], str) else params["metadata"],
                "created_at": datetime(2026, 7, 2, 9, 25, tzinfo=timezone.utc),
                "updated_at": datetime(2026, 7, 2, 9, 25, tzinfo=timezone.utc),
            }
            # UPSERT semantics: replace if same pool_id
            existing = next((r for r in self.rows if r["pool_id"] == rec["pool_id"]), None)
            if existing:
                rec["id"] = existing["id"]
                self.rows.remove(existing)
            self.rows.append(rec)
            return _ExecResult(row=(rec["id"],))

        if "SELECT created_at FROM candidate_pools WHERE id" in sql:
            rid = params.get("id")
            rec = next((r for r in self.rows if r["id"] == rid), None)
            return _ExecResult(scalar_value=rec["created_at"] if rec else None)

        if "SELECT COUNT(*) FROM candidate_pools" in sql:
            return _ExecResult(scalar_value=len(self._filtered(params)))

        if "SELECT id, pool_id" in sql:
            filtered = self._filtered(params)
            limit = params.get("limit")
            offset = params.get("offset", 0)
            if limit is not None:
                filtered = filtered[offset:offset + limit]
            else:
                filtered = filtered[offset:]
            return _ExecResult(rows=[_StubRow(r) for r in filtered])

        return _ExecResult()

    def _filtered(self, params: dict) -> list[dict]:
        """Replicate candidate_pool_store.query WHERE clauses for scope semantics."""
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
            if "pool_id" in params and r["pool_id"] != params["pool_id"]:
                continue
            if "source_module" in params and r["source_module"] != params["source_module"]:
                continue
            if "source_mode" in params and r["source_mode"] != params["source_mode"]:
                continue
            out.append(r)
        out.sort(key=lambda x: x["updated_at"], reverse=True)
        return out

    async def commit(self):
        self.committed = True

    async def rollback(self):
        pass


# ── POST /candidate-pool ──

def test_post_records_pool_and_returns_pool_id():
    db = _StubDb()

    r = _client(db).post(
        "/api/v1/screener/candidate-pool",
        headers={
            "X-Tenant-Id": "tenant-alpha",
            "X-Owner-User-Id": "7",
            "X-Trade-Account-Id": "paper-u7",
        },
        json={
            "source_module": "screener",
            "source_mode": "leader_auction",
            "name": "开盘候选池",
            "candidates": [{"candidate_id": "CAND-leader_auction-300750", "code": "300750"}],
            "candidate_pool_metadata": {"trade_date": "2026-07-02", "top_n": 20},
            "visibility": "private",
            "data_scope": "account",
            "trade_date": "2026-07-02",
            "time_slot": "09:25",
        },
    )

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pool_id"] == "POOL-leader_auction-2026-07-02-0925-paper-u7"
    assert body["id"] is not None
    assert body["created_at"] is not None
    assert body.get("fallback_reason") is None
    assert db.committed is True


def test_post_db_unavailable_returns_fallback():
    r = _client().post(
        "/api/v1/screener/candidate-pool",
        headers={"X-Tenant-Id": "t1", "X-Owner-User-Id": "1", "X-Trade-Account-Id": "a1"},
        json={"source_module": "screener", "source_mode": "bi_trend", "name": "x"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["fallback_reason"] == "db_session_unavailable"
    assert body["pool_id"] == ""


def test_post_body_has_no_plaintext_scope_fields():
    """AC-3: scope 绝不出现在请求体 schema（只有 Header 注入）。"""
    model = screener_router.CandidatePoolRecordRequest.model_json_schema()
    props = set(model.get("properties", {}).keys())
    forbidden = {"tenant_id", "owner_user_id", "account_id"}
    assert not (props & forbidden), f"scope fields leaked into request body: {props & forbidden}"


# ── GET /candidate-pool ──

def test_get_returns_records_for_current_scope():
    db = _StubDb()

    # seed two pools: account A private, account B private (same db stub)
    _client(db).post(
        "/api/v1/screener/candidate-pool",
        headers={"X-Tenant-Id": "t", "X-Owner-User-Id": "A", "X-Trade-Account-Id": "accA"},
        json={"source_module": "screener", "source_mode": "m1", "name": "A的池",
              "trade_date": "2026-07-02", "time_slot": "09:25"},
    )
    _client(db).post(
        "/api/v1/screener/candidate-pool",
        headers={"X-Tenant-Id": "t", "X-Owner-User-Id": "B", "X-Trade-Account-Id": "accB"},
        json={"source_module": "screener", "source_mode": "m2", "name": "B的池",
              "trade_date": "2026-07-02", "time_slot": "09:30"},
    )

    # A 查询 → 只能看到自己的池
    r = _client(db).get(
        "/api/v1/screener/candidate-pool",
        headers={"X-Tenant-Id": "t", "X-Owner-User-Id": "A", "X-Trade-Account-Id": "accA"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["records"][0]["source_mode"] == "m1"
    assert body.get("empty_state") is None


def test_get_scope_isolation_account_a_invisible_to_account_b():
    """AC-5: 账户 A 写入 → 账户 B 查询读不到（private/account 隔离）。"""
    db = _StubDb()

    _client(db).post(
        "/api/v1/screener/candidate-pool",
        headers={"X-Tenant-Id": "t", "X-Owner-User-Id": "A", "X-Trade-Account-Id": "accA"},
        json={"source_module": "screener", "source_mode": "m1", "name": "A私有池",
              "visibility": "private", "data_scope": "account",
              "trade_date": "2026-07-02", "time_slot": "09:25"},
    )

    # 账户 B 查询 → 读不到 A 的 private pool
    r = _client(db).get(
        "/api/v1/screener/candidate-pool",
        headers={"X-Tenant-Id": "t", "X-Owner-User-Id": "B", "X-Trade-Account-Id": "accB"},
    )
    body = r.json()
    assert body["total"] == 0
    assert body["records"] == []
    assert body["empty_state"] is not None
    assert body["empty_state"]["hint"] == "no_visible_pools"


def test_get_public_visibility_cross_account_readable():
    """AC-5: public visibility 可跨账户读。"""
    db = _StubDb()

    _client(db).post(
        "/api/v1/screener/candidate-pool",
        headers={"X-Tenant-Id": "t", "X-Owner-User-Id": "A", "X-Trade-Account-Id": "accA"},
        json={"source_module": "screener", "source_mode": "m1", "name": "A公开池",
              "visibility": "public", "data_scope": "public",
              "trade_date": "2026-07-02", "time_slot": "09:25"},
    )

    # 账户 B 查询 → 可见 A 的 public pool
    r = _client(db).get(
        "/api/v1/screener/candidate-pool",
        headers={"X-Tenant-Id": "t", "X-Owner-User-Id": "B", "X-Trade-Account-Id": "accB"},
    )
    body = r.json()
    assert body["total"] == 1
    assert body["records"][0]["visibility"] == "public"


def test_get_db_unavailable_returns_empty_with_fallback():
    r = _client().get("/api/v1/screener/candidate-pool")
    body = r.json()
    assert body["total"] == 0
    assert body["records"] == []
    assert body["fallback_reason"] == "db_session_unavailable"
    assert body["empty_state"]["hint"] == "db_session_unavailable"


def test_get_filters_by_source_module_and_mode():
    db = _StubDb()

    _client(db).post(
        "/api/v1/screener/candidate-pool",
        headers={"X-Tenant-Id": "t", "X-Owner-User-Id": "A", "X-Trade-Account-Id": "accA"},
        json={"source_module": "screener", "source_mode": "leader_auction", "name": "n1",
              "trade_date": "2026-07-02", "time_slot": "09:25"},
    )
    _client(db).post(
        "/api/v1/screener/candidate-pool",
        headers={"X-Tenant-Id": "t", "X-Owner-User-Id": "A", "X-Trade-Account-Id": "accA"},
        json={"source_module": "strategy", "source_mode": "bi_trend", "name": "n2",
              "trade_date": "2026-07-02", "time_slot": "09:30"},
    )

    r = _client(db).get(
        "/api/v1/screener/candidate-pool?source_module=screener&source_mode=leader_auction",
        headers={"X-Tenant-Id": "t", "X-Owner-User-Id": "A", "X-Trade-Account-Id": "accA"},
    )
    body = r.json()
    assert body["total"] == 1
    assert body["records"][0]["source_module"] == "screener"
    assert body["records"][0]["source_mode"] == "leader_auction"


# ── OpenAPI contract (AC for frontend orval generation) ──

def test_endpoints_declare_response_model_and_operation_id():
    paths = {r.path: r for r in router.routes if hasattr(r, "path") and "candidate-pool" in r.path}
    assert "/api/v1/screener/candidate-pool" in paths

    post_route = next(r for r in router.routes if getattr(r, "operation_id", None) == "record_candidate_pool")
    get_route = next(r for r in router.routes if getattr(r, "operation_id", None) == "query_candidate_pool")
    assert post_route.response_model is screener_router.CandidatePoolRecordResponse
    assert get_route.response_model is screener_router.CandidatePoolQueryResponse
