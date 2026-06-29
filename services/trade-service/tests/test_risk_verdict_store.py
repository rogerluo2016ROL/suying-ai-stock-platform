from datetime import datetime, timezone
import json

import pytest

from app import risk_verdict_store


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
        if "INSERT INTO risk_verdicts" in sql:
            return _FakeResult(row=(101,))
        if "SELECT COUNT(*) FROM risk_verdicts" in sql:
            return _FakeResult(scalar_value=1)
        return _FakeResult(
            rows=[
                (
                    101,
                    "RV-test",
                    "tenant-alpha",
                    "7",
                    "paper-u7",
                    "pass",
                    "order",
                    "paper",
                    "300750",
                    "ORD-1",
                    "PLAN-1",
                    "CAND-1",
                    "CTX-1",
                    {"risk_check": {"checks": []}},
                    datetime(2026, 6, 27, 9, 30, tzinfo=timezone.utc),
                )
            ]
        )


@pytest.mark.asyncio
async def test_record_risk_verdict_persists_queryable_order_context():
    db = _FakeDb()
    verdict = {
        "verdict_id": "RV-test",
        "tenant_id": "tenant-alpha",
        "owner_user_id": "7",
        "account_id": "paper-u7",
        "result": "pass",
        "scope": "order",
        "trade_mode": "paper",
        "symbol": "300750",
        "decision_context_id": "CTX-1",
        "candidate_id": "CAND-1",
        "plan_id": "PLAN-1",
        "risk_check": {"checks": []},
    }

    row_id = await risk_verdict_store.record(
        db,
        verdict=verdict,
        order_id="ORD-1",
        symbol="300750",
    )

    sql, params = db.calls[0]
    assert row_id == 101
    assert "INSERT INTO risk_verdicts" in sql
    assert params["verdict_id"] == "RV-test"
    assert params["tenant_id"] == "tenant-alpha"
    assert params["account_id"] == "paper-u7"
    assert params["order_id"] == "ORD-1"
    assert json.loads(params["details"])["risk_check"]["checks"] == []


@pytest.mark.asyncio
async def test_query_risk_verdicts_filters_by_platform_scope_and_lineage():
    db = _FakeDb()

    result = await risk_verdict_store.query(
        db,
        tenant_id="tenant-alpha",
        account_id="paper-u7",
        result="pass",
        symbol="300750",
        page=1,
        page_size=20,
    )

    count_sql, count_params = db.calls[0]
    assert "tenant_id = :tenant_id" in count_sql
    assert "account_id = :account_id" in count_sql
    assert "result = :result" in count_sql
    assert "symbol = :symbol" in count_sql
    assert count_params["tenant_id"] == "tenant-alpha"
    assert result["total"] == 1
    assert result["records"][0]["verdict_id"] == "RV-test"
    assert result["records"][0]["decision_context_id"] == "CTX-1"
    assert result["records"][0]["details"]["risk_check"]["checks"] == []


@pytest.mark.asyncio
async def test_query_risk_verdicts_filters_by_lineage_ids():
    db = _FakeDb()

    await risk_verdict_store.query(
        db,
        tenant_id="tenant-alpha",
        account_id="paper-u7",
        decision_context_id="CTX-1",
        order_id="ORD-1",
        plan_id="PLAN-1",
        candidate_id="CAND-1",
    )

    count_sql, count_params = db.calls[0]
    assert "decision_context_id = :decision_context_id" in count_sql
    assert "order_id = :order_id" in count_sql
    assert "plan_id = :plan_id" in count_sql
    assert "candidate_id = :candidate_id" in count_sql
    assert count_params["decision_context_id"] == "CTX-1"
    assert count_params["order_id"] == "ORD-1"
    assert count_params["plan_id"] == "PLAN-1"
    assert count_params["candidate_id"] == "CAND-1"
