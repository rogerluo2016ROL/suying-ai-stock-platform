from fastapi.testclient import TestClient

from app.main import app
from app import inventory


def test_inventory_rows_are_table_counts_not_last_job_writes(monkeypatch):
    monkeypatch.setattr(inventory, "count_table", lambda table: 8642399 if table == "daily_kline" else 0)
    body = TestClient(app).get("/api/v1/data/inventory").json()
    assert body["tables"]["daily_kline"]["rows"] == 8642399
    assert body["tables"]["daily_kline"]["rows"] != 5200


def test_status_remains_compatibility_summary():
    body = TestClient(app).get("/api/v1/data/status").json()
    assert "jobs" in body
    assert "pg_write_summary" in body
