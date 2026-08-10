"""Sentiment endpoints + scoring pure-function tests.

端点测试走 TestClient + conftest 的 auth override; 无 PG 时端点应降级到
mock/推导兜底仍返回 200 与完整字段。评分逻辑为纯函数, 直接边界断言。
"""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import sentiment
from app.sentiment import (
    ALERT_THRESHOLDS,
    DIMENSION_DEFS,
    build_alerts,
    combine_dimensions,
    derive_daily_score,
    level_label,
    score_to_level,
)


@pytest.fixture(scope="module")
def client():
    from app.main import app
    return TestClient(app)


# ── 端点: sentiment-index ──

def test_sentiment_index_returns_contract_fields(client):
    resp = client.get("/api/v1/signal/sentiment-index")
    assert resp.status_code == 200
    body = resp.json()

    for key in ("score", "label", "level", "change", "dimensions",
                "sector_sentiment", "limit_stats", "operation_hint", "data_source"):
        assert key in body, f"missing field: {key}"

    assert 0 <= body["score"] <= 100
    assert body["label"] in ("极牛", "偏牛", "中性", "偏熊", "极熊", "黑天鹅")
    assert set(body["dimensions"].keys()) == set(DIMENSION_DEFS.keys())
    for dim in body["dimensions"].values():
        assert "score" in dim and "label" in dim and "weight" in dim
        if dim["score"] is not None:
            assert 0 <= dim["score"] <= 100

    limit_stats = body["limit_stats"]
    for key in ("up_count", "down_count", "blow_count", "blow_rate",
                "up_count_trend", "down_count_trend", "up_stocks", "down_stocks"):
        assert key in limit_stats, f"limit_stats missing: {key}"
    assert isinstance(body["sector_sentiment"], list)
    assert isinstance(body["operation_hint"], str) and body["operation_hint"]


def test_sentiment_index_sector_shape_when_present(client):
    body = client.get("/api/v1/signal/sentiment-index").json()
    for sector in body["sector_sentiment"]:
        assert {"sector", "score", "up_pct", "avg_chg"} <= set(sector.keys())
        assert 0 <= sector["score"] <= 100


# ── 端点: sentiment-history ──

def test_sentiment_history_returns_series(client):
    resp = client.get("/api/v1/signal/sentiment-history?days=30")
    assert resp.status_code == 200
    body = resp.json()

    assert body["days"] == 30
    assert body["count"] == len(body["history"]) > 0
    for point in body["history"]:
        assert {"date", "score", "label"} <= set(point.keys())
        assert 0 <= point["score"] <= 100


def test_sentiment_history_days_default_and_max(client):
    assert client.get("/api/v1/signal/sentiment-history").status_code == 200
    assert client.get("/api/v1/signal/sentiment-history?days=120").status_code == 200


@pytest.mark.parametrize("days", [0, -1, 121, 999])
def test_sentiment_history_days_out_of_range_4xx(client, days):
    resp = client.get(f"/api/v1/signal/sentiment-history?days={days}")
    assert 400 <= resp.status_code < 500


# ── 端点: sentiment-alerts ──

def test_sentiment_alerts_returns_three_rule_types(client):
    resp = client.get("/api/v1/signal/sentiment-alerts")
    assert resp.status_code == 200
    body = resp.json()

    assert body["thresholds"] == ALERT_THRESHOLDS
    alerts = {a["type"]: a for a in body["alerts"]}
    assert set(alerts) == {"overheat", "ice_point", "sharp_reversal"}
    for alert in alerts.values():
        for key in ("level", "message", "triggered", "threshold",
                    "current_value", "time"):
            assert key in alert, f"alert missing: {key}"
        assert alert["level"] in ("warning", "danger", "info")


# ── 纯函数: 等级分档 ──

def test_score_to_level_thresholds():
    assert score_to_level(85) == "BULL"
    assert score_to_level(80) == "BULL"
    assert score_to_level(60) == "NEUTRAL_BULL"
    assert score_to_level(40) == "NEUTRAL"
    assert score_to_level(20) == "NEUTRAL_BEAR"
    assert score_to_level(0) == "BEAR"
    # 风险维度 <20 强制黑天鹅
    assert score_to_level(90, risk_score=10) == "BLACK_SWAN"
    assert level_label("BEAR") == "极熊"
    assert level_label("BULL") == "极牛"


# ── 纯函数: 八维合成 ──

def test_combine_dimensions_all_high_and_all_low():
    assert combine_dimensions({k: 95.0 for k in DIMENSION_DEFS}) == pytest.approx(95.0)
    assert combine_dimensions({k: 5.0 for k in DIMENSION_DEFS}) == pytest.approx(5.0)
    assert combine_dimensions({k: None for k in DIMENSION_DEFS}) is None


def test_combine_dimensions_skips_missing_and_renormalizes():
    partial = {k: None for k in DIMENSION_DEFS}
    partial["trend"] = 80.0  # 唯一可用维度 → 总分即 80
    assert combine_dimensions(partial) == pytest.approx(80.0)


# ── 纯函数: 单日推导边界 ──

def test_derive_daily_score_all_down_is_ice_point():
    score = derive_daily_score(avg_chg=-9.8, up_count=0, down_count=3800,
                               total=3800, limit_up=0, limit_down=500)
    assert 0 <= score < 20
    assert score_to_level(score) == "BEAR"
    assert level_label(score_to_level(score)) == "极熊"


def test_derive_daily_score_all_up_is_overheat():
    score = derive_daily_score(avg_chg=9.5, up_count=3800, down_count=0,
                               total=3800, limit_up=400, limit_down=0)
    assert 80 < score <= 100
    assert score_to_level(score) == "BULL"
    assert level_label(score_to_level(score)) == "极牛"


def test_derive_daily_score_clamps_extremes():
    assert derive_daily_score(avg_chg=100, up_count=1, down_count=0, total=1) <= 100
    assert derive_daily_score(avg_chg=-100, up_count=0, down_count=1, total=1) >= 0


# ── 纯函数: 预警规则 ──

def test_build_alerts_trigger_states():
    overheat = {a["type"]: a for a in build_alerts(score=85, change=2)}
    assert overheat["overheat"]["triggered"] is True
    assert overheat["overheat"]["level"] == "danger"
    assert overheat["ice_point"]["triggered"] is False
    assert overheat["ice_point"]["level"] == "info"

    ice = {a["type"]: a for a in build_alerts(score=15, change=-22)}
    assert ice["ice_point"]["triggered"] is True
    assert ice["sharp_reversal"]["triggered"] is True

    calm = {a["type"]: a for a in build_alerts(score=50, change=3)}
    assert all(not a["triggered"] for a in calm.values())
