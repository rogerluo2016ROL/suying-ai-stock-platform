"""Basic unit tests for factor scoring functions."""

import numpy as np
import pandas as pd
import pytest

# Test: can we import the package?
def test_import_package():
    import kronos_factors
    assert kronos_factors.__version__ == "0.1.0"


# Test: five_factor with valid data
def test_five_factor_valid():
    from kronos_factors.scorer import score_five_factor

    # Build 60-day mock K-line data
    np.random.seed(42)
    n = 60
    close = 100 + np.cumsum(np.random.randn(n) * 0.5)
    df = pd.DataFrame({
        "open": close - 0.1,
        "high": close + 0.2,
        "low": close - 0.2,
        "close": close,
        "volume": np.random.randint(1e7, 5e8, n),
        "amount": np.random.randint(1e8, 5e9, n),
    })
    result = score_five_factor(df)
    assert "score" in result
    assert "grade" in result
    assert 0 <= result["score"] <= 25
    assert result["grade"] in ("S", "A", "B", "C")


# Test: five_factor with too little data
def test_five_factor_insufficient():
    from kronos_factors.scorer import score_five_factor

    df = pd.DataFrame({
        "open": [10], "high": [10.5], "low": [9.5],
        "close": [10.2], "volume": [1e6], "amount": [1e7],
    })
    result = score_five_factor(df)
    assert result["score"] == 0
    assert result["grade"] == "C"


# Test: money_flow scorer
def test_money_flow():
    from kronos_factors.scorer import score_money_flow

    np.random.seed(42)
    n = 30
    close = 50 + np.cumsum(np.random.randn(n) * 0.3)
    df = pd.DataFrame({
        "open": close - 0.05, "high": close + 0.15,
        "low": close - 0.15, "close": close,
        "volume": np.random.randint(1e7, 3e8, n),
        "amount": np.random.randint(1e8, 3e9, n),
    })
    result = score_money_flow(df)
    assert "score" in result
    assert "signal" in result
    assert 0 <= result["score"] <= 10


# Test: trend_strength scorer
def test_trend_strength():
    from kronos_factors.scorer import score_trend_strength

    np.random.seed(42)
    n = 30
    close = 50 + np.cumsum(np.random.randn(n) * 0.3)
    df = pd.DataFrame({
        "open": close - 0.05, "high": close + 0.15,
        "low": close - 0.15, "close": close,
        "volume": np.random.randint(1e7, 3e8, n),
        "amount": np.random.randint(1e8, 3e9, n),
    })
    result = score_trend_strength(df)
    assert "score" in result
    assert "adx" in result
    assert 0 <= result["score"] <= 10


# Test: liquidity scorer
def test_liquidity():
    from kronos_factors.scorer import score_liquidity

    np.random.seed(42)
    n = 20
    close = 50 + np.cumsum(np.random.randn(n) * 0.2)
    df = pd.DataFrame({
        "open": close - 0.05, "high": close + 0.15,
        "low": close - 0.15, "close": close,
        "volume": np.random.randint(1e7, 3e8, n),
        "amount": np.random.randint(1e8, 3e9, n),
    })
    result = score_liquidity(df)
    assert "score" in result
    assert 0 <= result["score"] <= 10


# Test: StrategyEngine base class
def test_strategy_engine_abc():
    from kronos_factors.base import StrategyEngine, ScreeningResult
    assert ScreeningResult is not None


# Test: mode engines can be instantiated (without DB)
def test_mode_engine_instantiation():
    from kronos_factors.engine.modes import (
        ChokepointEngine, ShortModeEngine, LongModeEngine, AllModeEngine,
    )
    for engine_cls in [ChokepointEngine, ShortModeEngine, LongModeEngine, AllModeEngine]:
        engine = engine_cls()
        assert engine.mode in ("chokepoint", "short", "long", "all")
        weights = engine.get_factor_weights()
        assert isinstance(weights, dict)
        assert sum(weights.values()) > 0
