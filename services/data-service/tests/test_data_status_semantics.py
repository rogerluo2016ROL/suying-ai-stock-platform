def test_inventory_rows_are_table_counts_not_last_job_writes():
    from app import inventory
    inventory.count_table = lambda table: 8642399
    result = inventory.inventory()
    assert result["tables"]["daily_kline"]["rows"] == 8642399
    assert result["tables"]["daily_kline"]["rows"] != 5200
