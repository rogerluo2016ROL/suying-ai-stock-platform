"""supply_chain 样本外验证框架 + 门禁 (P5).

真前向验证 SupplyChainEngine: 在历史 cutoff 用 trade_date 让 engine 用历史数据打分,
算 forward return 的 IC, train/test 切分 + 显著性检验 + 基线对照, 输出 PASS/FAIL 门禁.

防过拟合 (bi_trend 教训): test 期禁止调参, 仅评估. 复用 backtest/engine.py 的
compute_ic / _get_trading_day, 复用 supply_chain_ic.compute_dimension_ic 拿 composite IC.
"""

import logging
import numpy as np
from scipy import stats

from kronos_factors.backtest.engine import compute_ic, _get_trading_day
from kronos_factors.backtest.supply_chain_ic import _resolve_trading_day, month_end_cutoffs, DIMS
from kronos_factors.scorer._db_stub import _get_db

logger = logging.getLogger("kronos-factors.supply_chain_validation")


def _forward_returns(codes, cutoff_td, horizon):
    """算 codes 在 [cutoff_td, cutoff_td+horizon] 的 forward return.

    Returns: (returns: np.ndarray[np.float64 with nan], future_td: str).
    """
    with _get_db(readonly=True) as db:
        future_td = _get_trading_day(db, cutoff_td, horizon)
        if not future_td:
            return np.full(len(codes), np.nan), ""
        close_c = {r["code"]: float(r["close"]) for r in db.execute(
            "SELECT code, close FROM daily_kline WHERE trade_date = ?", (cutoff_td,)).fetchall()}
        close_f = {r["code"]: float(r["close"]) for r in db.execute(
            "SELECT code, close FROM daily_kline WHERE trade_date = ?", (future_td,)).fetchall()}
    ret = np.full(len(codes), np.nan)
    for i, c in enumerate(codes):
        c0, c1 = close_c.get(c), close_f.get(c)
        if c0 and c1 and c0 > 0:
            ret[i] = c1 / c0 - 1
    return ret, future_td


def _ic_bootstrap(scores, returns, n_seeds=5, sample_size=300, seed_base=0):
    """对 (scores, returns) 做 bootstrap 估 IC 均值/std (防单次抽样侥幸).

    有放回抽 min(sample_size, n_valid) 个样本算 IC, 重复 n_seeds 次取均值/std.
    """
    valid = ~(np.isnan(scores) | np.isnan(returns))
    s, r = scores[valid], returns[valid]
    n = len(s)
    if n < 10:
        return 0.0, 0.0, []
    ics = []
    for k in range(n_seeds):
        rng = np.random.RandomState(seed_base + k)
        idx = rng.choice(n, size=min(sample_size, n), replace=True)
        ics.append(compute_ic(s[idx], r[idx])["ic"])
    return float(np.mean(ics)), float(np.std(ics)), [round(x, 4) for x in ics]


def _run_period(engine_cls, weights, cutoffs, horizon, n_seeds, sample_size, seed_base=0):
    """对一个时期 (train/test) 的 cutoffs 跑真前向验证, 返回 IC 序列统计.

    Returns: {"mean_ic", "std_ic", "icir", "p_value", "seed_std", "n_cutoffs",
              "ic_series", "per_cutoff": [...]}
    """
    ic_series = []
    per_cutoff = []
    for cutoff in cutoffs:
        engine = engine_cls(weights=weights) if weights else engine_cls()
        result = engine.run(trade_date=cutoff, top_n=5000)
        picks = result.picks
        if not picks:
            continue
        codes = [p["code"] for p in picks]
        scores = np.array([float(p.get("total_score", 0)) for p in picks], dtype=np.float64)
        with _get_db(readonly=True) as db:
            cutoff_td = _resolve_trading_day(db, cutoff)
        if not cutoff_td:
            continue
        rets, future_td = _forward_returns(codes, cutoff_td, horizon)
        mean_ic, seed_std, _ = _ic_bootstrap(scores, rets, n_seeds, sample_size, seed_base)
        if np.isnan(mean_ic):
            continue
        ic_series.append(mean_ic)
        per_cutoff.append({"cutoff": cutoff, "cutoff_td": cutoff_td, "future_td": future_td,
                           "mean_ic": round(mean_ic, 4), "seed_std": round(seed_std, 4),
                           "n_picks": len(picks), "n_valid": int((~np.isnan(rets)).sum())})

    if not ic_series:
        return {"mean_ic": 0, "std_ic": 0, "icir": 0, "p_value": 1.0,
                "seed_std": 0, "n_cutoffs": 0, "ic_series": [], "per_cutoff": []}
    arr = np.array(ic_series)
    mean_ic = float(np.mean(arr))
    std_ic = float(np.std(arr)) or 1e-9
    # 单样本 t 检验: H0 mean_ic=0; 单边 p (mean_ic>0 显著)
    t_stat, p_two = stats.ttest_1samp(arr, 0)
    p_one = p_two / 2 if t_stat > 0 else 1 - p_two / 2
    return {"mean_ic": round(mean_ic, 4), "std_ic": round(std_ic, 4),
            "icir": round(mean_ic / std_ic, 4), "p_value": round(float(p_one), 4),
            "seed_std": round(float(np.mean([pc["seed_std"] for pc in per_cutoff])), 4),
            "n_cutoffs": len(ic_series), "ic_series": [round(x, 4) for x in ic_series],
            "per_cutoff": per_cutoff}


def _run_baseline(baseline, cutoffs, horizon, n_seeds, sample_size, seed_base=1000):
    """基线对照. random: 随机置换 score (IC 应≈0). chokepoint: 跑 ChokepointEngine 同期."""
    if baseline == "chokepoint":
        try:
            from kronos_factors.engine.modes import ChokepointEngine
            return _run_period(ChokepointEngine, None, cutoffs, horizon, n_seeds, sample_size, seed_base)
        except Exception as e:
            logger.warning("chokepoint baseline 失败: %s", e)
            baseline = "random"
    # random: 用 supply_chain 的 picks 但随机置换 score
    from kronos_factors.engine.supply_chain import SupplyChainEngine
    ic_series = []
    for cutoff in cutoffs:
        engine = SupplyChainEngine()
        picks = engine.run(trade_date=cutoff, top_n=5000).picks
        if not picks:
            continue
        codes = [p["code"] for p in picks]
        with _get_db(readonly=True) as db:
            cutoff_td = _resolve_trading_day(db, cutoff)
        if not cutoff_td:
            continue
        rets, _ = _forward_returns(codes, cutoff_td, horizon)
        rng = np.random.RandomState(seed_base + hash(cutoff) % 1000)
        shuffled = rng.permutation(np.array([float(p.get("total_score", 0)) for p in picks]))
        mean_ic, _, _ = _ic_bootstrap(shuffled, rets, n_seeds, sample_size, 0)
        if not np.isnan(mean_ic):
            ic_series.append(mean_ic)
    if not ic_series:
        return {"mean_ic": 0, "n_cutoffs": 0}
    arr = np.array(ic_series)
    return {"mean_ic": round(float(np.mean(arr)), 4), "std_ic": round(float(np.std(arr)), 4),
            "n_cutoffs": len(ic_series)}


def run_supply_chain_oos_validation(
    engine_cls, weights=None,
    train_start="2020-03-31", train_end="2023-12-31",
    test_start="2024-01-31", test_end="2026-06-30",
    horizon=20, n_seeds=5, sample_size=300, baseline="random",
) -> dict:
    """样本外验证主入口.

    Args:
        engine_cls: SupplyChainEngine 类.
        weights: 校准权重 (P4 产出). None=默认权重.
        train/test 区间: 月末 cutoff 范围 (受 broker 2020起/financial 约束).
        horizon: forward return 周期 (交易日).
        n_seeds: bootstrap 次数 (防单次抽样侥幸).
        sample_size: bootstrap 每次抽样数.
        baseline: "random" (IC应≈0) / "chokepoint" (现有模型基准).

    Returns: {"train": {...}, "test": {...}, "baseline": {...}, "verdict": "PASS"/"FAIL",
              "criteria": {...}, "config": {...}}
    """
    model_version = "supply_chain_bom_v4" if engine_cls.__name__ == "SupplyChainEngine" else engine_cls.__name__
    train_cutoffs = month_end_cutoffs(train_start, train_end)
    test_cutoffs = month_end_cutoffs(test_start, test_end)
    logger.info("OOS 验证: train %d cutoffs, test %d cutoffs, horizon=%d, baseline=%s",
                len(train_cutoffs), len(test_cutoffs), horizon, baseline)

    print(f"→ 训练期 {len(train_cutoffs)} 个 cutoff ({train_start}~{train_end})...", flush=True)
    train = _run_period(engine_cls, weights, train_cutoffs, horizon, n_seeds, sample_size, seed_base=0)
    print(f"  train: mean_ic={train['mean_ic']:+.4f} ICIR={train['icir']:+.4f} "
          f"p={train['p_value']:.4f} n={train['n_cutoffs']}", flush=True)

    print(f"→ 测试期 {len(test_cutoffs)} 个 cutoff ({test_start}~{test_end})...", flush=True)
    test = _run_period(engine_cls, weights, test_cutoffs, horizon, n_seeds, sample_size, seed_base=5000)
    print(f"  test:  mean_ic={test['mean_ic']:+.4f} ICIR={test['icir']:+.4f} "
          f"p={test['p_value']:.4f} n={test['n_cutoffs']}", flush=True)

    print(f"→ 基线 {baseline}...", flush=True)
    base = _run_baseline(baseline, test_cutoffs, horizon, n_seeds, sample_size)
    print(f"  baseline: mean_ic={base['mean_ic']:+.4f} n={base.get('n_cutoffs', 0)}", flush=True)

    # 门禁判定 (verdict=PASS 当且仅当 4 条全满足)
    c1 = test["mean_ic"] > 0
    c2 = test["p_value"] < 0.05
    c3 = test["mean_ic"] > base["mean_ic"] + 0.02
    c4 = test["seed_std"] < 0.03
    verdict = "PASS" if all([c1, c2, c3, c4]) else "FAIL"

    return {
        "model_version": model_version,
        "verdict": verdict,
        "criteria": {
            "test_mean_ic_positive": c1, "test_p_lt_0.05": c2,
            "beats_baseline_by_0.02": c3, "seed_std_lt_0.03": c4,
        },
        "train": train, "test": test, "baseline": base,
        "config": {"weights": weights, "horizon": horizon, "n_seeds": n_seeds,
                   "sample_size": sample_size, "baseline": baseline,
                   "model_version": model_version,
                   "train_range": [train_start, train_end], "test_range": [test_start, test_end]},
    }
