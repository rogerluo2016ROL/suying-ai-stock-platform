"""数据表预览端点测试 — 数据库层全部 mock，不依赖真实 PG。

认证由 conftest 的 autouse fixture 统一绕过（dependency_overrides）。
"""

import pytest
from fastapi.testclient import TestClient

from app import inventory


@pytest.fixture
def client():
    from app.main import app

    return TestClient(app)


def _fake_preview(table: str, limit: int) -> dict:
    return {
        "table": table,
        "columns": [
            {"name": "ts_code", "type": "text"},
            {"name": "trade_date", "type": "date"},
            {"name": "close", "type": "numeric"},
        ],
        "rows": [
            {"ts_code": "000001.SZ", "trade_date": "2026-08-05", "close": 10.5},
            {"ts_code": "600000.SH", "trade_date": "2026-08-05", "close": 8.2},
        ],
        "limit": limit,
        "total": 2,
    }


def test_preview_whitelisted_table_returns_columns_and_rows(client, monkeypatch):
    monkeypatch.setattr(inventory, "table_preview", _fake_preview)
    resp = client.get("/api/v1/data/tables/stocks/preview?limit=2")
    assert resp.status_code == 200
    body = resp.json()
    assert body["table"] == "stocks"
    assert body["limit"] == 2
    assert body["total"] == 2
    assert [c["name"] for c in body["columns"]] == ["ts_code", "trade_date", "close"]
    assert len(body["rows"]) == 2


def test_preview_default_limit_is_50(client, monkeypatch):
    monkeypatch.setattr(inventory, "table_preview", _fake_preview)
    resp = client.get("/api/v1/data/tables/daily_kline/preview")
    assert resp.status_code == 200
    assert resp.json()["limit"] == 50


def test_preview_unknown_table_returns_404(client, monkeypatch):
    def _must_not_be_called(table, limit):  # pragma: no cover
        raise AssertionError("database layer must not be reached for unknown tables")

    monkeypatch.setattr(inventory, "table_preview", _must_not_be_called)
    resp = client.get("/api/v1/data/tables/not_a_table/preview")
    assert resp.status_code == 404


def test_preview_malicious_table_name_rejected_without_sql(client, monkeypatch):
    def _must_not_be_called(table, limit):  # pragma: no cover
        raise AssertionError("拼接 SQL 风险: database layer reached with %r" % table)

    monkeypatch.setattr(inventory, "table_preview", _must_not_be_called)
    resp = client.get("/api/v1/data/tables/stocks; DROP TABLE stocks/preview")
    assert 400 <= resp.status_code < 500
    assert resp.status_code == 404


@pytest.mark.parametrize("limit", ["0", "501", "abc"])
def test_preview_invalid_limit_returns_4xx(client, monkeypatch, limit):
    def _must_not_be_called(table, limit_):  # pragma: no cover
        raise AssertionError("database layer must not be reached for invalid limit")

    monkeypatch.setattr(inventory, "table_preview", _must_not_be_called)
    resp = client.get(f"/api/v1/data/tables/stocks/preview?limit={limit}")
    assert resp.status_code == 422


def test_preview_db_failure_returns_500(client, monkeypatch):
    def _boom(table, limit):
        raise RuntimeError("pg down")

    monkeypatch.setattr(inventory, "table_preview", _boom)
    resp = client.get("/api/v1/data/tables/stocks/preview")
    assert resp.status_code == 500
