from datetime import datetime, timezone
import json

import pytest

from app import decision_context_store


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
        if "INSERT INTO decision_contexts" in sql:
            return _FakeResult(row=(201,))
        if "SELECT COUNT(*) FROM decision_contexts" in sql:
            return _FakeResult(scalar_value=1)
        return _FakeResult(
            rows=[
                (
                    201,
                    "CTX-PLAN-1-trend-300750",
                    "tenant-alpha",
                    "7",
                    "paper-u7",
                    "order",
                    "300750",
                    "PLAN-1",
                    "CAND-1",
                    "manual_order",
                    {"entry": "strategy-pick"},
                    datetime(2026, 6, 27, 10, 0, tzinfo=timezone.utc),
                )
            ]
        )


@pytest.mark.asyncio
async def test_record_once_persists_decision_context_snapshot():
    db = _FakeDb()

    row_id = await decision_context_store.record_once(
        db,
        decision_context_id="CTX-PLAN-1-trend-300750",
        tenant_id="tenant-alpha",
        owner_user_id="7",
        account_id="paper-u7",
        source_type="order",
        symbol="300750",
        plan_id="PLAN-1",
        candidate_id="CAND-1",
        intent="manual_order",
        payload={"entry": "strategy-pick"},
    )

    sql, params = db.calls[0]
    assert row_id == 201
    assert "INSERT INTO decision_contexts" in sql
    assert "ON CONFLICT (decision_context_id) DO NOTHING" in sql
    assert params["tenant_id"] == "tenant-alpha"
    assert json.loads(params["payload"])["entry"] == "strategy-pick"


@pytest.mark.asyncio
async def test_query_decision_contexts_filters_by_platform_scope():
    db = _FakeDb()

    result = await decision_context_store.query(
        db,
        tenant_id="tenant-alpha",
        account_id="paper-u7",
        decision_context_id="CTX-PLAN-1-trend-300750",
        page=1,
        page_size=20,
    )

    count_sql, count_params = db.calls[0]
    assert "tenant_id = :tenant_id" in count_sql
    assert "account_id = :account_id" in count_sql
    assert "decision_context_id = :decision_context_id" in count_sql
    assert count_params["account_id"] == "paper-u7"
    assert result["total"] == 1
    assert result["records"][0]["decision_context_id"] == "CTX-PLAN-1-trend-300750"
    assert result["records"][0]["payload"]["entry"] == "strategy-pick"
