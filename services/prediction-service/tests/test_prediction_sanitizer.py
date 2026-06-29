import sys
from types import SimpleNamespace
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.modules["app.main"] = SimpleNamespace(_model_loaded=False, _predictor=None)

from app.routes import _sanitize_prediction_df


def test_sanitize_prediction_df_repairs_ohlc_and_limits_step_jumps():
    raw = pd.DataFrame(
        [
            {"open": 100.0, "high": 90.0, "low": 120.0, "close": 160.0},
            {"open": 10.0, "high": 11.0, "low": 9.0, "close": 8.0},
        ],
    )

    result = _sanitize_prediction_df(raw, current_price=100.0, max_step_pct=0.15)

    previous_close = 100.0
    for _, row in result.iterrows():
        assert row["high"] >= max(row["open"], row["close"])
        assert row["low"] <= min(row["open"], row["close"])
        assert abs(row["close"] / previous_close - 1) <= 0.150001
        previous_close = row["close"]


def test_sanitize_prediction_df_preserves_step_limit_after_display_rounding():
    raw = pd.DataFrame(
        [
            {"open": 432.8, "high": 450.0, "low": 300.0, "close": 300.0},
        ],
    )

    result = _sanitize_prediction_df(raw, current_price=432.8)
    rounded_close = round(float(result["close"].iloc[0]), 2)

    assert abs(rounded_close / 432.8 - 1) <= 0.120001


def test_sanitize_prediction_df_uses_display_close_for_next_step_limit():
    raw = pd.DataFrame(
        [
            {"open": 391.28, "high": 391.28, "low": 200.0, "close": 200.0},
            {"open": 500.0, "high": 500.0, "low": 300.0, "close": 500.0},
        ],
    )

    result = _sanitize_prediction_df(raw, current_price=391.28)
    rounded = [
        {"close": round(float(row["close"]), 2)}
        for _, row in result.iterrows()
    ]

    previous_close = 391.28
    for row in rounded:
        assert abs(row["close"] / previous_close - 1) <= 0.120001
        previous_close = row["close"]
