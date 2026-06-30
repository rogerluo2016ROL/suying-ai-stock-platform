import asyncio
import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import routes


def test_signal_contract_wraps_model_metadata_freshness_and_fallback():
    df = pd.DataFrame({"trade_date": ["2026-06-20", "2026-06-21"], "close": [210.0, 218.5]})

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
    assert result["data_freshness"]["as_of"] == "2026-06-21"
    assert result["fallback_reason"] is None


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


def test_trigger_sync_prefers_data_service_proxy(monkeypatch):
    def fake_proxy(table_key: str, days: int):
        return {"status": "ok", "table_key": table_key, "written": 12, "pg_written": 12}

    monkeypatch.setattr(routes, "_trigger_sync_via_data_service", fake_proxy)

    result = asyncio.run(routes.trigger_sync("daily_kline", 3))

    assert result["status"] == "ok"
    assert result["source"] == "data-service"
    assert result["table_key"] == "daily_kline"
    assert result["written"] == 12
