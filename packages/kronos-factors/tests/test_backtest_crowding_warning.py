#!/usr/bin/env python3
"""backtest_crowding_warning 关键逻辑单测 (future_drawdown / summarize, 不依赖 PG)."""
import sys, os
import numpy as np
import pandas as pd

_PROJ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(_PROJ, "tools"))
sys.path.insert(0, os.path.join(_PROJ, "packages", "kronos-factors"))

from backtest_crowding_warning import future_drawdown_series, summarize


def test_future_drawdown_basic():
    close = pd.Series([100.0, 110.0, 90.0, 95.0, 80.0])
    dd = future_drawdown_series(close, K=2)
    assert abs(dd.iloc[0] - (-0.10)) < 1e-9      # window[100,110,90] min=90 → -10%
    assert abs(dd.iloc[1] - (90.0 / 110.0 - 1)) < 1e-9
    assert abs(dd.iloc[2] - (80.0 / 90.0 - 1)) < 1e-9
    assert np.isnan(dd.iloc[3]) and np.isnan(dd.iloc[4])  # 末端不足 K 日


def test_future_drawdown_all_up():
    close = pd.Series([10.0, 11.0, 12.0, 13.0, 14.0])
    dd = future_drawdown_series(close, K=2)
    # 全涨, 未来无回撤 → dd >= 0
    assert dd.iloc[0] >= -1e-9
    assert dd.iloc[1] >= -1e-9


def test_summarize_high_crowding_drops_more():
    # 构造: high 组未来回撤大, low 组小; train/test 各 40 行 (>30 触发 IC 计算)
    n = 20
    df = pd.DataFrame({
        "trade_date": pd.to_datetime(["2025-06-01"] * (2 * n) + ["2026-03-01"] * (2 * n)),
        "code": ["A"] * (4 * n),
        "level": ["high"] * n + ["low"] * n + ["high"] * n + ["low"] * n,
        "ci_score": [0.95] * n + [0.30] * n + [0.93] * n + [0.35] * n,
        "future_dd_5": [-0.10] * n + [-0.01] * n + [-0.09] * n + [-0.02] * n,
    })
    r = summarize(df, "2025-12", [5], -0.05)
    train = r["train"]["horizon_5d"]
    assert train["high"]["hit_rate"] == 1.0   # high 组都 < -5%
    assert train["low"]["hit_rate"] == 0.0    # low 组都没 < -5%
    assert "ic" in train and train["ic"] < 0   # 高拥挤→大回撤, 负相关
    test = r["test"]["horizon_5d"]
    assert test["high"]["hit_rate"] == 1.0


def test_summarize_baseline():
    df = pd.DataFrame({
        "trade_date": pd.to_datetime(["2025-01-01"] * 4),
        "code": ["A"] * 4,
        "level": ["high", "low", "high", "low"],
        "ci_score": [0.9, 0.3, 0.85, 0.4],
        "future_dd_10": [-0.06, -0.01, -0.04, -0.02],
    })
    r = summarize(df, "2025-12", [10], -0.05)
    train = r["train"]["horizon_10d"]
    # baseline = 全样本 < -5% 的比例 = 1/4
    assert abs(train["baseline_hit_rate"] - 0.25) < 1e-9


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
