from datetime import datetime, timezone
import json

import pytest

from app import order_store


class _FakeResult:
    def __init__(self, *, row=None, scalar_value=None, rows=None):
        self._row = row
        self._scalar_value = scalar_value
        self._rows = rows or []

    def fetchone(self):
        return self._row

    def scalar(self):
        return self._scalar_value

    def fetchall(self):
        return self._rows


class _FakeDb:
    def __init__(self):
        self.calls = []

    async def execute(self, statement, params=None):
        sql = str(statement)
        params = params or {}
        self.calls.append((sql, params))
        if "INSERT INTO trade_orders" in sql:
            return _FakeResult(row=(301,))
        if "SELECT COUNT(*) FROM trade_orders" in sql:
            return _FakeResult(scalar_value=1)
        return _FakeResult(
            rows=[
                (
                    301,
                    "ORD-1",
                    "tenant-alpha",
                    "7",
                    "paper-u7",
                    "paper",
                    "300750",
                    "BUY",
                    218.5,
                    100,
                    "FILLED",
                    "CTX-1",
                    "CAND-1",
                    "PLAN-1",
                    {"visibility": "private", "data_scope": "account"},
                    {"verdict_id": "RV-1"},
                    datetime(2026, 6, 27, 10, 30, tzinfo=timezone.utc),
                )
            ]
        )


@pytest.mark.asyncio
async def test_record_order_persists_platform_scope_and_lineage():
    db = _FakeDb()

    row_id = await order_store.record(
        db,
        order_id="ORD-1",
        tenant_id="tenant-alpha",
        owner_user_id="7",
        account_id="paper-u7",
        trade_mode="paper",
        code="300750",
        direction="BUY",
        price=218.5,
        volume=100,
        status="FILLED",
        decision_context_id="CTX-1",
        candidate_id="CAND-1",
        plan_id="PLAN-1",
        order_scope={"visibility": "private", "data_scope": "account"},
        risk_verdict={"verdict_id": "RV-1"},
    )

    sql, params = db.calls[0]
    assert row_id == 301
    assert "INSERT INTO trade_orders" in sql
    assert params["tenant_id"] == "tenant-alpha"
    assert params["account_id"] == "paper-u7"
    assert params["decision_context_id"] == "CTX-1"
    assert json.loads(params["risk_verdict"])["verdict_id"] == "RV-1"


@pytest.mark.asyncio
async def test_query_orders_filters_by_platform_scope():
    db = _FakeDb()

    result = await order_store.query(
        db,
        tenant_id="tenant-alpha",
        account_id="paper-u7",
        page=1,
        page_size=20,
    )

    count_sql, count_params = db.calls[0]
    assert "tenant_id = :tenant_id" in count_sql
    assert "account_id = :account_id" in count_sql
    assert count_params["tenant_id"] == "tenant-alpha"
    assert result["total"] == 1
    assert result["orders"][0]["order_id"] == "ORD-1"
    assert result["orders"][0]["decision_context_id"] == "CTX-1"
    assert result["orders"][0]["risk_verdict"]["verdict_id"] == "RV-1"
