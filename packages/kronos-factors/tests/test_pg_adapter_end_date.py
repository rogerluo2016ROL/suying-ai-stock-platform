"""Unit tests for M03 (audit-model-2026-06-22): pg_adapter end_date 时间泄漏修复.

验证 get_kline / get_kline_df 的 end_date 参数确实把 SQL 限制在
`trade_date <= end_date`, 不再返回"当下最近 N 天"——否则历史回测会用
未来 K 线算历史因子, IC 不可信.

用 fake cursor 捕获实际下发的 SQL + params, 不依赖真实 PG.
"""
import sys
import types


def _make_fake_pg_adapter(captured):
    """构造一个 _PgAdapter, 但 _get_conn 返回的 conn 用 fake cursor 记录 SQL."""
    from kronos_factors import pg_adapter as mod

    class _FakeCursor:
        def __init__(self):
            self.description = [
                ("trade_date",), ("open",), ("high",), ("low",),
                ("close",), ("volume",), ("amount",),
            ]
        def execute(self, sql, params=None):
            captured["sql"] = sql
            captured["params"] = params
            # 返回 3 行模拟数据, 让 get_kline 能构造 DataFrame
            captured["rows"] = [
                ("2024-01-03", 10.0, 10.5, 9.8, 10.2, 1000, 10000),
                ("2024-01-02", 10.0, 10.5, 9.8, 10.1, 1000, 10000),
                ("2024-01-01", 10.0, 10.5, 9.8, 10.0, 1000, 10000),
            ]
        def fetchall(self):
            return captured["rows"]

    class _FakeConn:
        autocommit = True
        def cursor(self):
            return _FakeCursor()

    adapter = mod._PgAdapter.__new__(mod._PgAdapter)
    adapter.pg_url = "fake"
    adapter._get_conn = lambda: _FakeConn()
    adapter._put_conn = lambda conn: None
    return adapter


def test_get_kline_with_end_date_filters_sql():
    """M03: 传 end_date 时 SQL 含 WHERE trade_date<=%s 且 end_date 在 params."""
    captured = {}
    adapter = _make_fake_pg_adapter(captured)
    adapter.get_kline("000001", lookback=400, end_date="2020-06-30")
    assert "trade_date<=%s" in captured["sql"], captured["sql"]
    # params 应含 code 与 end_date
    assert "000001" in captured["params"]
    assert "2020-06-30" in captured["params"], captured["params"]


def test_get_kline_without_end_date_preserves_old_behavior():
    """M03: 不传 end_date 时 SQL 无 end_date 过滤 (兼容 live screening)."""
    captured = {}
    adapter = _make_fake_pg_adapter(captured)
    adapter.get_kline("000001", lookback=400)
    assert "trade_date<=%s" not in captured["sql"], captured["sql"]
    assert captured["params"] == ("000001", 400), captured["params"]


def test_get_kline_df_propagates_end_date():
    """M03: get_kline_df 把 end_date 透传给 get_kline (MarketDataAdapter 接口)."""
    captured = {}
    adapter = _make_fake_pg_adapter(captured)
    adapter.get_kline_df("000001", lookback=400, end_date="2020-06-30")
    assert "trade_date<=%s" in captured["sql"], captured["sql"]
    assert "2020-06-30" in captured["params"], captured["params"]
