import asyncio
import re
import sys
import urllib.request
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import routes


def test_signal_contract_wraps_model_metadata_freshness_and_fallback():
    today = pd.Timestamp.now().normalize()
    df = pd.DataFrame({"trade_date": [(today - pd.Timedelta(days=1)).strftime("%Y-%m-%d"), today.strftime("%Y-%m-%d")], "close": [210.0, 218.5]})

    result = routes._with_signal_contract(
        {"code": "300750", "signal": {"level": "BUY", "score": 72.0}},
        mode="analyze",
        data=df,
        fallback_reason=None,
    )

    assert result["model_metadata"] == {
        "name": "signal-six-dimension-v2",
        "version": "signal-v2.0",
        "provider": "signal-service",
        "inference_mode": "analyze",
    }
    assert result["data_freshness"]["status"] == "fresh"
    assert result["data_freshness"]["as_of"] == today.strftime("%Y-%m-%d")
    assert result["fallback_reason"] is None


def test_missing_kronos_is_unavailable_not_neutral():
    body = routes._combine_signal_dimensions({
        "kronos": None, "technical": 72.0, "money_flow": 65.0,
        "fundamental": 61.0, "event_risk": 70.0, "market": 58.0,
    })
    assert "kronos" in body["unavailable_dimensions"]
    assert body["dimensions"]["kronos"] is None
    assert body["coverage"] < 1.0
    assert body["result_status"] == "insufficient_data"


def test_signal_data_freshness_accepts_trade_date_dict():
    result = routes._signal_data_freshness({"trade_date": "2026-06-29"}, "PG daily_kline")

    assert result["as_of"] == "2026-06-29"
    assert result["source"] == "PG daily_kline"


def test_signal_levels_endpoint_includes_contract_fields():
    result = asyncio.run(routes.signal_levels())

    assert result["model_metadata"]["name"] == "signal-six-dimension-v2"
    assert result["data_freshness"]["source"] == "signal.rules"
    assert result["fallback_reason"] is None


def test_dashboard_market_sentiment_sql_computes_missing_change_pct_from_previous_close():
    sql = routes._dashboard_market_sentiment_sql()

    assert re.search(r"COALESCE\(\s*d\.change_pct", sql)
    assert "prev.close" in sql
    assert "WHERE d.trade_date = (SELECT trade_date FROM latest)" in sql
    assert "SELECT MAX(trade_date) FROM daily_kline WHERE change_pct IS NOT NULL" not in sql


def test_dashboard_auction_sql_returns_trade_date_for_freshness_badge():
    sql = routes._dashboard_auction_sql()

    assert "ad.trade_date" in sql


def test_dashboard_row_change_pct_accepts_pg_adapter_alias():
    assert routes._dashboard_row_change_pct({"pct_chg": "-3.21"}) == -3.21
    assert routes._dashboard_row_change_pct({"change_pct": "2.34"}) == 2.34
    assert routes._dashboard_row_change_pct({}) == 0.0

def test_legacy_dashboard_and_data_routes_are_explicitly_deprecated():
    from app.main import app
    from fastapi.testclient import TestClient
    paths = {route.path for route in app.routes}
    assert "/api/v1/dashboard/summary" in paths
    assert "/api/v1/data/status" in paths
    assert app.state.deprecated_route_prefixes["/api/v1/dashboard"] == "screener-service"
    assert app.state.deprecated_route_prefixes["/api/v1/data"] == "data-service"
    response = TestClient(app).get("/api/v1/data/status")
    assert response.headers["Deprecation"] == "true"
    assert response.headers["X-Deprecated-Route"] == "true"
    assert response.headers["X-Route-Owner"] == "data-service"


def test_dashboard_alert_sql_computes_missing_change_pct_from_previous_close():
    vol_sql = routes._dashboard_volume_alerts_sql()
    limit_sql = routes._dashboard_limit_alerts_sql()

    assert "WHERE change_pct IS NOT NULL" not in vol_sql
    assert "WHERE change_pct IS NOT NULL" not in limit_sql
    assert "prev.close" in vol_sql
    assert "prev.close" in limit_sql


def test_signal_live_sql_uses_latest_close_and_computed_change_pct():
    sql = routes._signal_live_sql()

    assert "SELECT MAX(trade_date) FROM daily_kline WHERE change_pct IS NOT NULL" not in sql
    assert "prev.close" in sql
    assert "ORDER BY ABS(change_pct) DESC" in sql


def test_default_sync_schedules_cover_sync_map():
    schedules = routes._default_sync_schedules()

    by_key = {item["table_key"]: item for item in schedules}
    assert set(routes._SYNC_MAP).issubset(by_key)
    assert by_key["daily_kline"]["days_back"] == 30
    assert by_key["daily_kline"]["enabled"] is True
    assert by_key["stk_auction_o"]["daily_at"] == "09:30"
    assert by_key["rt_sw_k"]["interval_minutes"] == 5


def test_data_status_date_columns_match_real_pg_tables():
    assert routes.DATA_STATUS_DATE_COLUMNS["financial_balance"] == ("end_date",)
    assert routes.DATA_STATUS_DATE_COLUMNS["stock_news_tushare"] == ("pub_time",)
    assert routes.DATA_STATUS_DATE_COLUMNS["research_reports_tushare"] == ("pub_date",)
    assert routes.DATA_STATUS_DATE_COLUMNS["broker_recommend"] == ("month",)
    assert routes.DATA_STATUS_DATE_COLUMNS["dividend_data"] == ("ex_date",)


def test_data_status_sources_use_tushare_report_table():
    source_keys = {item["key"] for item in routes._DATA_SOURCES}

    assert "research_reports_tushare" in source_keys
    assert "research_reports" not in source_keys
    assert routes._SYNC_MAP["research_reports_tushare"] == ("research_report", 30, "研究报告")


def test_sync_map_covers_service_side_data_sources():
    assert routes._SYNC_MAP["stocks"] == ("stocks", 30, "股票列表")
    assert routes._SYNC_MAP["stk_factor_pro"] == ("stk_factor_pro", 7, "技术因子")


def test_data_service_proxy_routes_stocks_to_dedicated_endpoint(monkeypatch):
    calls = []

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b'{"status":"ok","table_key":"stocks","pg_written":1}'

    def fake_urlopen(req, timeout):
        calls.append((req.full_url, req.get_method(), timeout))
        return FakeResponse()

    monkeypatch.setenv("DATA_SERVICE_URL", "http://data-service/api/v1/data")
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    result = routes._trigger_sync_via_data_service("stocks", 30)

    assert result["status"] == "ok"
    assert calls == [("http://data-service/api/v1/data/sync/stocks", "POST", 300)]


def test_trigger_sync_prefers_data_service_proxy(monkeypatch):
    def fake_proxy(table_key: str, days: int):
        return {"status": "ok", "table_key": table_key, "written": 12, "pg_written": 12}

    monkeypatch.setattr(routes, "_trigger_sync_via_data_service", fake_proxy)

    result = asyncio.run(routes.trigger_sync("daily_kline", 3))

    assert result["status"] == "ok"
    assert result["source"] == "data-service"
    assert result["table_key"] == "daily_kline"
    assert result["written"] == 12


def test_dashboard_summary_runs_all_collectors_concurrently(monkeypatch):
    """Regression (B1): dashboard_summary 并行化后仍须调用全部 10 个采集器并写入各自 key。

    采集器定义在 app.routers.dashboard 模块内（dashboard_summary 按模块全局名引用），
    故须 patch dashboard 模块而非 routes 兼容层。
    """
    from app.routers import dashboard as dash

    collector_names = [
        "_collect_market_sentiment", "_collect_signal_stocks", "_collect_limit_stocks",
        "_collect_watchlist", "_collect_alert_signals", "_collect_auction_intent",
        "_collect_market_regime_v2", "_collect_trading_calendar", "_collect_risk_interact",
        "_collect_policy_news_monetary",
    ]
    called = []

    def make(name):
        def _fn(result):
            called.append(name)
            result[name] = name
        return _fn

    for name in collector_names:
        monkeypatch.setattr(dash, name, make(name))

    result = asyncio.run(dash.dashboard_summary(user={}))

    assert sorted(called) == sorted(collector_names), \
        f"未调用全部采集器: {set(collector_names) - set(called)}"
    for name in collector_names:
        assert result[name] == name, f"{name} 未写入结果"
