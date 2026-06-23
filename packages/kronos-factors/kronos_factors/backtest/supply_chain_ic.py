"""supply_chain 因子 IC 校准 (P4).

在历史 cutoff 时点真前向运行 SupplyChainEngine, 取 5 因子分值 (moat/growth/profit/rating/
consensus) 与 forward return 算 IC/ICIR, 用 ICIR 归一化校准权重.

防过拟合: 仅在 train 期校准, test 期禁止调参 (P5 验证). 复用 backtest/engine.py 的
compute_ic / _get_trading_day / HORIZONS, 不污染 5-factor 回测.
"""

import json
import logging
from pathlib import Path

import numpy as np

from kronos_factors.backtest.engine import compute_ic, _get_trading_day, HORIZONS
from kronos_factors.scorer._db_stub import _get_db

logger = logging.getLogger("kronos-factors.supply_chain_ic")

DIMS = ["moat", "growth", "profit", "rating", "consensus"]


def _resolve_trading_day(db, calendar_date: str) -> str:
    """calendar_date (如月末) → 不超过该日的最近交易日."""
    row = db.execute(
        "SELECT MAX(trade_date) as d FROM daily_kline WHERE trade_date <= ?",
        (calendar_date,),
    ).fetchone()
    return (row.get("d") if isinstance(row, dict) else row[0]) if row else ""


def compute_dimension_ic(engine, cutoff_date: str, horizon: int = 20) -> dict:
    """在 cutoff_date 真前向运行 engine, 算 5 因子 + composite 的 IC.

    Args:
        engine: SupplyChainEngine 实例 (用其当前 weights 打分).
        cutoff_date: 历史时点 (YYYY-MM-DD, 通常月末).
        horizon: forward return 周期 (交易日).

    Returns:
        {dim: {ic, rank_ic, hit_rate, n}, "composite": {...}, "cutoff", "future_td", "n_valid"}
        失败返回 {}.
    """
    result = engine.run(trade_date=cutoff_date, top_n=5000)
    picks = result.picks
    if not picks:
        return {}
    codes = [p["code"] for p in picks]
    dim_scores = {d: np.array([float(p.get(f"{d}_score", 0)) for p in picks], dtype=np.float64) for d in DIMS}
    composite = np.array([float(p.get("total_score", 0)) for p in picks], dtype=np.float64)

    with _get_db(readonly=True) as db:
        cutoff_td = _resolve_trading_day(db, cutoff_date)
        if not cutoff_td:
            return {}
        future_td = _get_trading_day(db, cutoff_td, horizon)
        if not future_td:
            return {}
        # 批量取 cutoff / future 两日的收盘价 (整表扫该交易日, 一次查询)
        close_cutoff = {r["code"]: float(r["close"]) for r in db.execute(
            "SELECT code, close FROM daily_kline WHERE trade_date = ?", (cutoff_td,)
        ).fetchall()}
        close_future = {r["code"]: float(r["close"]) for r in db.execute(
            "SELECT code, close FROM daily_kline WHERE trade_date = ?", (future_td,)
        ).fetchall()}

    returns = np.full(len(codes), np.nan)
    for i, c in enumerate(codes):
        c0 = close_cutoff.get(c); c1 = close_future.get(c)
        if c0 and c1 and c0 > 0:
            returns[i] = c1 / c0 - 1

    out = {d: compute_ic(dim_scores[d], returns) for d in DIMS}
    out["composite"] = compute_ic(composite, returns)
    out["cutoff"] = cutoff_td
    out["future_td"] = future_td
    out["n_valid"] = int((~np.isnan(returns)).sum())
    out["n_picks"] = len(picks)
    return out


def calibrate_weights(train_cutoffs: list, method: str = "icir", horizon: int = 20,
                      engine_cls=None) -> dict:
    """在 train 期 cutoffs 上算各因子 IC/ICIR, 归一化为权重.

    Args:
        train_cutoffs: 训练期 cutoff 日期列表 (YYYY-MM-DD).
        method: "icir" (权重=正ICIR/和) 或 "abs_ic_mean" (权重=|mean_ic|/和).
        horizon: forward return 周期.
        engine_cls: SupplyChainEngine 类 (默认权重测 IC).

    Returns:
        {"weights": {...}, "dim_stats": {dim: {mean_ic,std_ic,icir,hit_rate,n}},
         "train_cutoffs", "method", "horizon"}
    """
    if engine_cls is None:
        from kronos_factors.engine.supply_chain import SupplyChainEngine as engine_cls

    dim_ics = {d: [] for d in DIMS}
    composite_ics = []
    used = 0
    for cutoff in train_cutoffs:
        engine = engine_cls()  # 默认权重测 IC (校准基准)
        ic = compute_dimension_ic(engine, cutoff, horizon)
        if not ic or ic.get("n_valid", 0) < 10:
            continue
        used += 1
        for d in DIMS:
            dim_ics[d].append(ic[d]["ic"])
        composite_ics.append(ic["composite"]["ic"])

    if used == 0:
        logger.warning("calibrate_weights: 无有效 cutoff, 返回默认权重")
        from kronos_factors.engine.supply_chain import SupplyChainEngine
        return {"weights": dict(SupplyChainEngine.DEFAULT_WEIGHTS), "dim_stats": {}, "used_cutoffs": 0}

    dim_stats = {}
    raw = {}
    for d in DIMS:
        arr = np.array(dim_ics[d])
        mean_ic = float(np.mean(arr))
        std_ic = float(np.std(arr)) or 1e-9
        icir = mean_ic / std_ic
        dim_stats[d] = {"mean_ic": round(mean_ic, 4), "std_ic": round(std_ic, 4),
                        "icir": round(icir, 4), "hit_rate": round(float(np.mean(arr > 0)), 3), "n": used}
        if method == "icir":
            raw[d] = max(0.0, icir)
        else:  # abs_ic_mean
            raw[d] = abs(mean_ic)

    total = sum(raw.values())
    if total <= 0:
        logger.warning("calibrate_weights: 所选因子 ICIR/IC 均<=0, 退回默认权重")
        from kronos_factors.engine.supply_chain import SupplyChainEngine
        return {"weights": dict(SupplyChainEngine.DEFAULT_WEIGHTS), "dim_stats": dim_stats, "used_cutoffs": used}
    weights = {d: round(raw[d] / total, 4) for d in DIMS}

    logger.info("calibrate_weights: %d cutoffs, method=%s, weights=%s", used, method, weights)
    return {"weights": weights, "dim_stats": dim_stats,
            "composite_mean_ic": round(float(np.mean(composite_ics)), 4) if composite_ics else 0,
            "used_cutoffs": used, "method": method, "horizon": horizon,
            "train_cutoffs": train_cutoffs}


def month_end_cutoffs(start: str, end: str) -> list:
    """生成 [start, end] 区间每月末日期 (YYYY-MM-DD)."""
    import datetime
    sy, sm = int(start[:4]), int(start[5:7])
    ey, em = int(end[:4]), int(end[5:7])
    out = []
    y, m = sy, sm
    while (y, m) <= (ey, em):
        # 月末: 下月1号 - 1天
        nm, ny = m + 1, y
        if nm > 12:
            nm, ny = 1, y + 1
        last = datetime.date(ny, nm, 1) - datetime.timedelta(days=1)
        out.append(last.strftime("%Y-%m-%d"))
        m += 1
        if m > 12:
            m, y = 1, y + 1
    return out


if __name__ == "__main__":
    # CLI: 校准 train 期权重, 输出 JSON
    import argparse
    ap = argparse.ArgumentParser(description="supply_chain 权重 IC 校准 (P4)")
    ap.add_argument("--train-start", default="2020-03-31")
    ap.add_argument("--train-end", default="2023-12-31")
    ap.add_argument("--horizon", type=int, default=20)
    ap.add_argument("--method", default="icir", choices=["icir", "abs_ic_mean"])
    ap.add_argument("--out", default="calibrated_weights.json")
    args = ap.parse_args()

    cutoffs = month_end_cutoffs(args.train_start, args.train_end)
    print(f"Train cutoffs: {len(cutoffs)} 个 ({cutoffs[0]} ~ {cutoffs[-1]})")
    res = calibrate_weights(cutoffs, method=args.method, horizon=args.horizon)
    print("\n=== 因子 IC 统计 ===")
    for d, s in res.get("dim_stats", {}).items():
        print(f"  {d:10s} mean_ic={s['mean_ic']:+.4f} std={s['std_ic']:.4f} ICIR={s['icir']:+.4f} hit={s['hit_rate']:.2f} n={s['n']}")
    print(f"\ncomposite mean_ic (默认权重): {res.get('composite_mean_ic', 0):+.4f}")
    print(f"\n=== 校准权重 (method={args.method}) ===")
    for d, w in res["weights"].items():
        print(f"  {d:10s} {w:.4f}")
    print(f"  权重和: {sum(res['weights'].values()):.4f}")
    out_path = Path(args.out)
    out_path.write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n已写入 {out_path.resolve()}")
