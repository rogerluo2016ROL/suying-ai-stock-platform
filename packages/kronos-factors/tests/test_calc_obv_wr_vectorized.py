"""M13: calc_obv / calc_wr 向量化数值一致性单测.

对照原 Python for-loop 实现（reference 实现 inline 在此 test），断言向量化版本
对随机/边界输入数值一致。原实现见 audit-model-2026-06-22.md §M13。
"""
import numpy as np
import pytest

from kronos_factors.engine.bi_trend_launch import calc_obv, calc_wr


# ---- Reference: 原 O(N²) for-loop 实现（数值基准，禁止改） ----
def _ref_calc_obv(closes, volumes):
    obv = np.zeros(len(closes))
    for i in range(1, len(closes)):
        if closes[i] > closes[i - 1]:
            obv[i] = obv[i - 1] + volumes[i]
        elif closes[i] < closes[i - 1]:
            obv[i] = obv[i - 1] - volumes[i]
        else:
            obv[i] = obv[i - 1]
    return obv


def _ref_calc_wr(highs, lows, closes, period=14):
    wr = np.full(len(closes), np.nan)
    for i in range(period - 1, len(closes)):
        hh = np.max(highs[i - period + 1:i + 1])
        ll = np.min(lows[i - period + 1:i + 1])
        if hh - ll > 0:
            wr[i] = (closes[i] - ll) / (hh - ll) * 100
        else:
            wr[i] = 50
    return wr


# ---- calc_obv ----
def test_calc_obv_matches_reference_random():
    rng = np.random.default_rng(42)
    closes = rng.uniform(1, 100, 500)
    volumes = rng.uniform(1e3, 1e7, 500)
    got = calc_obv(closes, volumes)
    ref = _ref_calc_obv(closes, volumes)
    np.testing.assert_allclose(got, ref, rtol=0, atol=1e-6)


def test_calc_obv_first_element_zero():
    closes = np.array([10.0, 11, 9, 9, 12])
    volumes = np.array([100.0, 200, 300, 400, 500])
    got = calc_obv(closes, volumes)
    assert got[0] == 0.0
    # i=1: 11>10 up   -> obv[0]+vol[1] = 0+200 = 200
    # i=2: 9<11 down  -> obv[1]-vol[2] = 200-300 = -100
    # i=3: 9==9 flat  -> obv[2] = -100
    # i=4: 12>9 up    -> obv[3]+vol[4] = -100+500 = 400
    np.testing.assert_allclose(got, [0, 200, -100, -100, 400], rtol=0, atol=1e-6)


def test_calc_obv_empty_and_single():
    empty = calc_obv(np.array([]), np.array([]))
    assert len(empty) == 0
    single = calc_obv(np.array([5.0]), np.array([1.0]))
    assert single[0] == 0.0


def test_calc_obv_all_flat():
    closes = np.full(50, 10.0)
    volumes = np.full(50, 100.0)
    got = calc_obv(closes, volumes)
    np.testing.assert_allclose(got, np.zeros(50), rtol=0, atol=1e-6)


# ---- calc_wr ----
def test_calc_wr_matches_reference_random():
    rng = np.random.default_rng(7)
    n = 300
    highs = rng.uniform(1, 100, n)
    lows = rng.uniform(0, highs)  # low <= high
    closes = rng.uniform(lows, highs)
    for period in [5, 14, 20]:
        got = calc_wr(highs, lows, closes, period=period)
        ref = _ref_calc_wr(highs, lows, closes, period=period)
        # NaN positions must match
        nan_mask = np.isnan(ref)
        assert np.array_equal(np.isnan(got), nan_mask)
        np.testing.assert_allclose(got[~nan_mask], ref[~nan_mask], rtol=0, atol=1e-6)


def test_calc_wr_first_period_minus_one_are_nan():
    closes = np.arange(100, dtype=float)
    highs = closes + 1
    lows = closes - 1
    got = calc_wr(highs, lows, closes, period=14)
    assert np.all(np.isnan(got[:13]))
    assert not np.isnan(got[13])


def test_calc_wr_flat_range_returns_50():
    # hh == ll -> wr = 50
    closes = np.full(50, 10.0)
    highs = np.full(50, 10.0)
    lows = np.full(50, 10.0)
    got = calc_wr(highs, lows, closes, period=5)
    valid = got[~np.isnan(got)]
    np.testing.assert_allclose(valid, np.full(len(valid), 50.0), rtol=0, atol=1e-6)
