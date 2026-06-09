"""Unit tests for strategy engines and scoring functions."""

import numpy as np
import pandas as pd


def _make_kline(n=60, seed=42):
    np.random.seed(seed)
    close = 100 + np.cumsum(np.random.randn(n) * 0.5)
    return pd.DataFrame({
        "open": close - 0.1, "high": close + 0.2, "low": close - 0.2,
        "close": close, "volume": np.random.randint(1e7, 5e8, n),
        "amount": np.random.randint(1e8, 5e9, n),
    })


def test_all_mode_engine_weights():
    from kronos_factors.engine.modes import AllModeEngine
    e = AllModeEngine()
    weights = e.get_factor_weights()
    assert e.mode == "all"
    assert abs(sum(weights.values()) - 0.2) < 0.05


def test_short_mode_engine_weights():
    from kronos_factors.engine.modes import ShortModeEngine
    e = ShortModeEngine()
    weights = e.get_factor_weights()
    assert e.mode == "short"
    assert weights["short_term"] == 0.30


def test_long_mode_engine_weights():
    from kronos_factors.engine.modes import LongModeEngine
    e = LongModeEngine()
    weights = e.get_factor_weights()
    assert e.mode == "long"
    assert weights["long_term_value"] == 0.40


def test_chokepoint_engine_weights():
    from kronos_factors.engine.modes import ChokepointEngine
    e = ChokepointEngine()
    assert e.mode == "chokepoint"


def test_score_five_factor_grade():
    from kronos_factors.scorer import score_five_factor
    df = _make_kline(60)
    result = score_five_factor(df)
    assert "grade" in result
    assert result["grade"] in ("S", "A", "B", "C")
    assert 0 <= result["score"] <= 25


def test_score_mean_reversion_range():
    from kronos_factors.scorer import score_mean_reversion
    df = _make_kline(30)
    result = score_mean_reversion(df)
    assert 0 <= result["score"] <= 10


def test_score_reversal_range():
    from kronos_factors.scorer import score_reversal
    df = _make_kline(30)
    result = score_reversal(df)
    assert 0 <= result["score"] <= 10


def test_score_trend_strength_adx():
    from kronos_factors.scorer import score_trend_strength
    df = _make_kline(30)
    result = score_trend_strength(df)
    assert "adx" in result


def test_score_liquidity_range():
    from kronos_factors.scorer import score_liquidity
    df = _make_kline(20)
    result = score_liquidity(df)
    assert 0 <= result["score"] <= 10


def test_screening_result_dataclass():
    from kronos_factors.base import ScreeningResult
    r = ScreeningResult(mode="test", picks=[], total_scored=100)
    assert r.mode == "test"
    assert r.total_scored == 100
    assert r.market_env == "NEUTRAL"


def test_backtest_result_dataclass():
    from kronos_factors.base import BacktestResult
    r = BacktestResult(strategy_id="test", start_date="2026-01-01", end_date="2026-06-01",
                       total_return=0.1, annual_return=0.15, sharpe_ratio=1.5,
                       max_drawdown=-0.2, win_rate=0.6, profit_loss_ratio=2.0)
    assert r.sharpe_ratio == 1.5


def test_pg_adapter_creation():
    from kronos_factors.pg_adapter import create_pg_adapter
    # Without PG URL, should return None
    adapter = create_pg_adapter("")
    assert adapter is None
