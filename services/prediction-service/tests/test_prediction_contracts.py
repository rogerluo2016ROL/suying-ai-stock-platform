import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.modules["app.main"] = SimpleNamespace(
    _model_loaded=False,
    _predictor=None,
    _model_checkpoint_status="not_loaded",
)

from app import routes


def test_model_metadata_exposes_checkpoint_and_inference_mode():
    meta = routes._model_metadata("single")

    assert meta["name"] == "Kronos-mini"
    assert meta["version"] == "kronos-mini"
    assert meta["inference_mode"] == "single"
    assert meta["checkpoint_status"] == "not_loaded"
    assert meta["loaded"] is False


def test_prediction_contract_adds_freshness_and_fallback_reason():
    payload = {"code": "300750", "current_price": 218.5}
    today = pd.Timestamp.now().normalize()
    x_ts = pd.Series([today - pd.Timedelta(days=1), today])

    result = routes._with_prediction_contract(
        payload,
        code="300750",
        mode="fast",
        x_ts=x_ts,
        used_baseline=True,
        data_source="postgresql.daily_kline",
    )

    assert result["model_metadata"]["inference_mode"] == "fast"
    assert result["data_freshness"] == {
        "status": "fresh",
        "as_of": today.strftime("%Y-%m-%d"),
        "source": "postgresql.daily_kline",
        "quality_score": 96,
    }
    assert result["fallback_reason"] == "model checkpoint unavailable; using baseline predictor"


def test_prediction_overview_endpoint_returns_page_contract():
    result = asyncio.run(routes.prediction_overview())

    assert result["page"]["module"] == "prediction"
    assert result["page"]["view"] == "overview"
    assert result["model_metadata"]["name"] == "Kronos-mini"
    assert [section["id"] for section in result["sections"]] == [
        "forecast-market",
        "model-health",
        "accuracy-backtest",
    ]
