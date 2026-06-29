from datetime import datetime, timezone
import json

import pytest

from app import candidate_pool_store


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
        if "INSERT INTO candidate_pools" in sql:
            return _FakeResult(row=(401,))
        if "SELECT COUNT(*) FROM candidate_pools" in sql:
            return _FakeResult(scalar_value=1)
        return _FakeResult(
            rows=[
                (
                    401,
                    "POOL-1",
                    "tenant-alpha",
                    "7",
                    "paper-u7",
                    "private",
                    "account",
                    "screener",
                    "leader_auction",
                    "开盘候选池",
                    [{"candidate_id": "CAND-leader_auction-300750", "code": "300750"}],
                    {"trade_date": "2026-06-28"},
                    datetime(2026, 6, 28, 9, 25, tzinfo=timezone.utc),
                    datetime(2026, 6, 28, 9, 25, tzinfo=timezone.utc),
                )
            ]
        )


@pytest.mark.asyncio
async def test_record_candidate_pool_persists_scope_and_snapshot():
    db = _FakeDb()

    row_id = await candidate_pool_store.record(
        db,
        pool_id="POOL-1",
        tenant_id="tenant-alpha",
        owner_user_id="7",
        account_id="paper-u7",
        source_module="screener",
        source_mode="leader_auction",
        name="开盘候选池",
        candidates=[{"candidate_id": "CAND-leader_auction-300750", "code": "300750"}],
        metadata={"trade_date": "2026-06-28"},
    )

    sql, params = db.calls[0]
    assert row_id == 401
    assert "INSERT INTO candidate_pools" in sql
    assert params["tenant_id"] == "tenant-alpha"
    assert params["account_id"] == "paper-u7"
    assert json.loads(params["candidates"])[0]["candidate_id"] == "CAND-leader_auction-300750"
    assert json.loads(params["metadata"])["trade_date"] == "2026-06-28"


@pytest.mark.asyncio
async def test_query_candidate_pools_filters_private_scope_and_lineage():
    db = _FakeDb()

    result = await candidate_pool_store.query(
        db,
        tenant_id="tenant-alpha",
        owner_user_id="7",
        account_id="paper-u7",
        source_module="screener",
        source_mode="leader_auction",
        page=1,
        page_size=20,
    )

    count_sql, count_params = db.calls[0]
    assert "visibility = 'public' OR tenant_id = :tenant_id" in count_sql
    assert "owner_user_id = :owner_user_id" in count_sql
    assert "account_id = :account_id" in count_sql
    assert "source_module = :source_module" in count_sql
    assert count_params["owner_user_id"] == "7"
    assert result["total"] == 1
    assert result["records"][0]["pool_id"] == "POOL-1"
    assert result["records"][0]["candidates"][0]["candidate_id"] == "CAND-leader_auction-300750"
