import numpy as np

from kronos_factors.engine.bi_shifu_trend import (
    _ma,
    _obv,
    _compare_daily_to_minute,
    _minute_row_to_daily_unit,
    _should_repair_with_minute,
)


def test_minute_aggregate_converts_to_daily_units():
    row = {
        "code": "603110",
        "trade_date": "2026-07-14",
        "open": 22.95,
        "high": 24.50,
        "low": 21.91,
        "close": 24.15,
        "volume": 30_851_635,
        "amount": 710_803_084,
        "bars": 43,
    }

    converted = _minute_row_to_daily_unit(row)

    assert converted["volume"] == 308_516.35
    assert converted["amount"] == 710_803.084
    assert converted["data_source"] == "stk_mins_aggregated_daily_unit"


def test_daily_and_minute_compare_uses_official_units():
    daily = {
        "close": 24.15,
        "volume": 332_644.35,
        "amount": 766_185.211,
    }
    minute = {
        "close": 24.15,
        "volume": 30_851_635,
        "amount": 710_803_084,
    }

    result = _compare_daily_to_minute(daily, minute)

    assert result["status"] == "ok"
    assert result["volume_ratio_daily_to_minute"] == 1.0782
    assert result["amount_ratio_daily_to_minute"] == 1.0779


def test_repair_only_for_unit_scale_mismatch():
    ordinary_source_gap = {
        "status": "mismatch",
        "volume_ratio_daily_to_minute": 1.20,
        "amount_ratio_daily_to_minute": 1.16,
        "close_abs_diff": 0,
    }
    unit_scale_gap = {
        "status": "mismatch",
        "volume_ratio_daily_to_minute": 94.27,
        "amount_ratio_daily_to_minute": 942.36,
        "close_abs_diff": 0.09,
    }

    assert _should_repair_with_minute(ordinary_source_gap) is False
    assert _should_repair_with_minute(unit_scale_gap) is True


def test_raw_minute_units_inflate_volume_and_obv_signal():
    close = np.array([20.0, 20.2, 20.4, 20.8, 21.0, 22.79, 24.15])
    official_volume = np.array([100_000, 110_000, 120_000, 130_000, 140_000, 252_153.8, 332_644.35])
    raw_minute_volume = official_volume.copy()
    raw_minute_volume[-1] = 30_851_635

    official_vol_ratio = official_volume[-1] / _ma(official_volume, 5)[-1]
    raw_vol_ratio = raw_minute_volume[-1] / _ma(raw_minute_volume, 5)[-1]
    official_obv_ratio = _obv(close, official_volume)[-1] / _ma(_obv(close, official_volume), 5)[-1]
    raw_obv_ratio = _obv(close, raw_minute_volume)[-1] / _ma(_obv(close, raw_minute_volume), 5)[-1]

    assert raw_vol_ratio > official_vol_ratio
    assert raw_obv_ratio > official_obv_ratio
