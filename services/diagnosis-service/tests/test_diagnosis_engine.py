import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import config
from app import diagnosis_engine
from app.diagnosis_engine import _get_kronos_prediction, _score_fundamental


class _Result:
    def __init__(self, row):
        self._row = row

    def fetchone(self):
        return self._row


class _FakeDb:
    def __init__(self):
        self.statements = []

    async def execute(self, statement, params=None):
        sql = str(statement)
        self.statements.append(sql)
        if "financial_indicator" in sql:
            return _Result(None)
        if "daily_basic" in sql:
            assert "pe_ttm" not in sql
            return _Result((18.5, 3.2, 8500.0))
        if "fina_audit" in sql:
            return _Result(None)
        raise AssertionError(f"unexpected SQL: {sql}")


def test_score_fundamental_daily_basic_fallback_matches_current_schema():
    result = asyncio.run(_score_fundamental("300750", _FakeDb()))

    assert result.status == "available"
    assert result.details["pe"] == 18.5


def test_get_kronos_prediction_calls_current_prediction_fast_endpoint(monkeypatch):
    captured = {}

    async def fake_http_json(url, headers, timeout, method="GET"):
        captured["url"] = url
        captured["method"] = method
        return {
            "pred_return_pct": 4.2,
            "pred_last_close": 242.3,
            "model_metadata": {
                "name": "Kronos-mini",
                "version": "kronos-mini",
                "checkpoint_status": "base_public",
            },
            "data_freshness": {
                "status": "fresh",
                "as_of": "2026-06-21",
                "source": "postgresql.daily_kline",
                "quality_score": 96,
            },
            "fallback_reason": None,
            "pred_trajectory": [
                {"day": 1, "low": 210.0},
                {"day": 2, "low": 205.0},
            ],
            "current_price": 218.5,
        }

    diagnosis_engine._kronos_cache.clear()
    monkeypatch.setattr(config, "KRONOS_PREDICTION_URL", "http://prediction-service:8002/api/v1/prediction")
    monkeypatch.setattr(diagnosis_engine, "_http_get_json", fake_http_json)

    result = asyncio.run(_get_kronos_prediction("300750", auth_token="token", force_refresh=True))

    assert captured == {
        "url": "http://prediction-service:8002/api/v1/prediction/300750/fast?pred_days=10",
        "method": "POST",
    }
    assert result["pred_return_pct"] == 4.2
    assert result["pred_30d_close"] == 242.3
    assert result["max_drawdown_pct"] == round((205.0 / 218.5 - 1) * 100, 2)
    assert result["model_metadata"]["name"] == "Kronos-mini"
    assert result["data_freshness"]["status"] == "fresh"
    assert result["fallback_reason"] is None


def test_diagnosis_report_has_default_new_ui_contract_fields():
    from app.schemas import DiagnosisReport, RecommendationGrade

    report = DiagnosisReport(
        code="300750",
        overall_score=72.5,
        grade="B",
        recommendation=RecommendationGrade.BUY,
        recommendation_reason="技术面表现突出。",
        dimensions={},
        key_levels={"support": 200.0, "resistance": 240.0, "stop_loss": 190.0},
    )

    assert report.model_metadata["diagnosis_model"] == "five-dimension-weighted-v2"
    assert report.data_freshness["status"] == "unknown"
    assert report.fallback_reason is None


def test_default_kronos_prediction_url_uses_compose_host_inside_container(monkeypatch):
    monkeypatch.delenv("KRONOS_PREDICTION_URL", raising=False)
    monkeypatch.setattr(config.os.path, "exists", lambda path: path == "/.dockerenv")

    assert (
        config._default_kronos_prediction_url()
        == "http://prediction-service:8002/api/v1/prediction"
    )
