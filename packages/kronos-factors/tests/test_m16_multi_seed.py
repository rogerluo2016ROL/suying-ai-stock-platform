"""M16: run_historical_backtest 多 seed 平均 IC 单测（AC-4）.

audit-model-2026-06-22 §M16：random.seed(42) 写死使每次跑都抽同一批股票，
IC 被这批样本绑架。修复：多 seed (≥5) 各跑一遍取 IC 均值 ± std.

测试分两层：
1. 契约：run_historical_backtest 签名含 n_seeds，默认 ≥5；输出含 seed_std_ic。
2. 行为：_aggregate_multi_seed 纯函数——多 seed 的 IC 均值/std 计算正确。
"""
import inspect

import numpy as np

from kronos_factors.backtest.engine import (
    run_historical_backtest,
    _aggregate_multi_seed,
)


def test_signature_has_n_seeds_default_ge_5():
    sig = inspect.signature(run_historical_backtest)
    assert "n_seeds" in sig.parameters, (
        "run_historical_backtest 必须接受 n_seeds 参数（M16: 多 seed 平均 IC）"
    )
    default = sig.parameters["n_seeds"].default
    assert default >= 5, f"n_seeds 默认值应 ≥5（M16），实际 default={default}"


def test_aggregate_multi_seed_basic():
    """两 model × 三 seed 的 IC 均值/std 计算."""
    seed_mean_ics = {
        "ModelA": [0.10, 0.12, 0.08],   # mean 0.10, std ~0.0163
        "ModelB": [0.05, 0.05, 0.05],   # mean 0.05, std 0
    }
    out = _aggregate_multi_seed(seed_mean_ics)
    assert set(out.keys()) == {"ModelA", "ModelB"}
    np.testing.assert_allclose(out["ModelA"]["seed_mean_ic"], 0.10, rtol=1e-9)
    np.testing.assert_allclose(out["ModelB"]["seed_mean_ic"], 0.05, rtol=1e-9)
    # std of [0.10,0.12,0.08] (population) = sqrt(((0)^2+(0.02)^2+(-0.02)^2)/3)
    expected_std_a = float(np.std([0.10, 0.12, 0.08]))
    np.testing.assert_allclose(out["ModelA"]["seed_std_ic"], expected_std_a, rtol=1e-9)
    assert abs(out["ModelB"]["seed_std_ic"]) < 1e-12  # identical seeds → ~0 (float noise)


def test_aggregate_multi_seed_icir_uses_seed_std():
    """seed_icir = seed_mean / seed_std, seed_std=0 时记 0（防除零）."""
    seed_mean_ics = {"M": [0.10, 0.10, 0.10]}  # std 0
    out = _aggregate_multi_seed(seed_mean_ics)
    assert out["M"]["seed_icir"] == 0.0

    seed_mean_ics2 = {"M": [0.06, 0.10, 0.14]}  # mean 0.10, std 0.0327
    out2 = _aggregate_multi_seed(seed_mean_ics2)
    expected = 0.10 / float(np.std([0.06, 0.10, 0.14]))
    np.testing.assert_allclose(out2["M"]["seed_icir"], expected, rtol=1e-9)


def test_aggregate_multi_seed_n_seeds_field():
    out = _aggregate_multi_seed({"M": [0.1, 0.2, 0.15, 0.12, 0.18]})
    assert out["M"]["n_seeds"] == 5
