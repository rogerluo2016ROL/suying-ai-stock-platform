def test_inventory_rows_are_table_counts_not_last_job_writes():
    from app import inventory
    inventory.count_table = lambda table: 8642399
    result = inventory.inventory()
    assert result["tables"]["daily_kline"]["rows"] == 8642399
    assert result["tables"]["daily_kline"]["rows"] != 5200

def test_readiness_reports_false_when_tushare_is_unconfigured(monkeypatch):
    from app.routers import data
    monkeypatch.setattr(data, "_build_readiness_status", lambda: {
        "ready": False, "components": {"tushare_configured": False}
    })
    import asyncio
    result = asyncio.run(data.data_readiness())
    assert result["ready"] is False
