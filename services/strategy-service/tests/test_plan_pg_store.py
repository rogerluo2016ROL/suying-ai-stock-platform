from datetime import datetime, timezone
import json

import pytest

from app import plan_pg_store
from app.plan_store import Plan


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
        if "INSERT INTO strategy_plans" in sql:
            return _FakeResult(row=(501,))
        if "SELECT COUNT(*) FROM strategy_plans" in sql:
            return _FakeResult(scalar_value=1)
        return _FakeResult(
            rows=[
                (
                    501,
                    "PLAN-1",
                    "趋势方案",
                    "draft",
                    "kronos",
                    1_000_000,
                    5,
                    0.2,
                    "tenant-alpha",
                    "7",
                    "paper-u7",
                    "private",
                    "account",
                    [{"candidate_id": "CAND-1", "code": "300750"}],
                    datetime(2026, 6, 28, 10, 0, tzinfo=timezone.utc),
                    datetime(2026, 6, 28, 10, 1, tzinfo=timezone.utc),
                )
            ]
        )


@pytest.mark.asyncio
async def test_record_plan_persists_scope_and_candidate_snapshot():
    db = _FakeDb()
    plan = Plan(
        id="PLAN-1",
        name="趋势方案",
        status="draft",
        picks=[{"candidate_id": "CAND-1", "code": "300750"}],
        model_name="kronos",
        tenant_id="tenant-alpha",
        owner_user_id="7",
        account_id="paper-u7",
        visibility="private",
        data_scope="account",
    )

    row_id = await plan_pg_store.record(db, plan=plan)

    sql, params = db.calls[0]
    assert row_id == 501
    assert "INSERT INTO strategy_plans" in sql
    assert "ON CONFLICT (plan_id) DO UPDATE" in sql
    assert params["tenant_id"] == "tenant-alpha"
    assert params["account_id"] == "paper-u7"
    assert json.loads(params["picks"])[0]["candidate_id"] == "CAND-1"


@pytest.mark.asyncio
async def test_query_plans_filters_private_scope():
    db = _FakeDb()

    result = await plan_pg_store.query(
        db,
        tenant_id="tenant-alpha",
        owner_user_id="7",
        account_id="paper-u7",
        page=1,
        page_size=20,
    )

    count_sql, count_params = db.calls[0]
    assert "visibility = 'public' OR tenant_id = :tenant_id" in count_sql
    assert "owner_user_id = :owner_user_id" in count_sql
    assert "account_id = :account_id" in count_sql
    assert count_params["tenant_id"] == "tenant-alpha"
    assert result["total"] == 1
    assert result["plans"][0]["id"] == "PLAN-1"
    assert result["plans"][0]["picks"][0]["candidate_id"] == "CAND-1"
