#!/usr/bin/env python3
"""拥挤度→回撤预警 回测: 验证"高拥挤 → 未来回撤"是否统计显著.

语义区别 (为何独立成脚本, 不改 tools/walk_forward.py):
  - walk_forward 评估 "选股 picks 的未来收益" (选股语义)
  - 本脚本评估 "拥挤预警后的未来最大回撤命中率" (预警有效性语义)
两者评估目标不同, 强塞 walk_forward 的 picks/收益框架会扭曲. 但本脚本对齐
walk_forward 的 M01 时序纪律 (策略文件 commit 日期 guard, 防样本外调参泄露),
通过 --strict-timeline 复用同一护栏.

方向纪律 (cerebrum): 拥挤度是"极端反转"型因子 —— 预期高拥挤组未来回撤 > 低拥挤组,
IC(crowding_score, 未来回撤) 应为负. 判定有效必须看分组方向, 不能只看命中率.

用法:
  KRONOS_PG_URL=postgresql://kronos:kronos@localhost:6432/kronos \
  .venv/bin/python tools/backtest_crowding_warning.py \
      --start 2024-01 --end 2026-06 --train-cutoff 2025-12 \
      --board 688 --strict-timeline
"""
import argparse, json, os, sys
import numpy as np
import pandas as pd

_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_PROJ, "packages", "kronos-factors"))
sys.path.insert(0, os.path.join(_PROJ, "tools"))

from kronos_factors.scorer.crowding_drawdown import (  # noqa: E402
    HIGH_THRESHOLD, MEDIUM_THRESHOLD, RET20_EXTREME_PCTL,
)


def setup_db():
    pg_url = os.environ.get("KRONOS_PG_URL", "postgresql://kronos:kronos@localhost:6432/kronos")
    from kronos_factors.pg_adapter import create_pg_adapter
    from kronos_factors.scorer._db_stub import set_db_adapter, set_market_data_adapter
    adapter = create_pg_adapter(pg_url)
    set_db_adapter(adapter); set_market_data_adapter(adapter)
    return adapter


def load_universe(db, board):
    if board == "688":
        rows = db.execute("SELECT code FROM stocks WHERE board='科创板' AND is_st=0").fetchall()
    else:
        rows = db.execute("SELECT code FROM stocks WHERE is_st=0").fetchall()
    return [r["code"] for r in rows]


def load_panel(db, codes, start_date, end_date, lookback):
    """批量预取候选池在 [start-lookback, end] 的 basic/kline/moneyflow, 合并排序."""
    pad = pd.Timedelta(days=int(lookback * 1.6))
    s = (pd.Timestamp(start_date) - pad).strftime("%Y-%m-%d")
    basic = db.execute(
        "SELECT code, trade_date, turnover_rate_f, volume_ratio, pb FROM daily_basic "
        "WHERE trade_date BETWEEN ? AND ?", (s, end_date)).fetchall()
    kline = db.execute(
        "SELECT code, trade_date, amount, close FROM daily_kline "
        "WHERE trade_date BETWEEN ? AND ?", (s, end_date)).fetchall()
    mf = db.execute(
        "SELECT code, trade_date, net_mf_amount FROM moneyflow "
        "WHERE trade_date BETWEEN ? AND ?", (s, end_date)).fetchall()
    bdf, kdf, mdf = pd.DataFrame(basic), pd.DataFrame(kline), pd.DataFrame(mf)
    for d in (bdf, kdf, mdf):
        d["trade_date"] = pd.to_datetime(d["trade_date"])
    df = (bdf.merge(kdf, on=["code", "trade_date"], how="outer")
            .merge(mdf, on=["code", "trade_date"], how="outer"))
    df = df[df["code"].isin(codes)].sort_values(["code", "trade_date"]).reset_index(drop=True)
    return df


def _rolling_pct(s, N):
    """时序滚动分位 (pandas>=2.0 Rolling.rank). 口径 rank/N, 与 crowding_drawdown
    的 (rank-1)/(N-1) 有 ~1/N 偏差 (N=250 可忽略, 阈值 0.8/0.9 不受影响)."""
    return s.rolling(N, min_periods=max(20, N // 2)).rank(pct=True)


def add_crowding(panel, lookback):
    """向量化: 加 6 成分时序分位 + ci_score + level."""
    g = panel.groupby("code", group_keys=False)
    for col, dst in [("turnover_rate_f", "turnover_pct"), ("amount", "amount_pct"),
                     ("volume_ratio", "vol_ratio_pct"), ("pb", "pb_pct"),
                     ("net_mf_amount", "main_flow_pct")]:
        panel[dst] = g[col].transform(lambda s, N=lookback: _rolling_pct(s, N))
    panel["ret20"] = g["close"].transform(lambda s: s.pct_change(20))
    panel["ret20_pct"] = g["ret20"].transform(lambda s, N=lookback: _rolling_pct(s, N))

    cols = ["turnover_pct", "amount_pct", "vol_ratio_pct", "pb_pct", "ret20_pct", "main_flow_pct"]
    panel["ci_score"] = panel[cols].mean(axis=1, skipna=True)
    valid_cnt = panel[cols].notna().sum(axis=1)
    panel.loc[valid_cnt < 3, "ci_score"] = np.nan  # 至少3成分, 否则无效

    panel["level"] = "low"
    panel.loc[panel["ci_score"] > MEDIUM_THRESHOLD, "level"] = "medium"
    panel.loc[panel["ci_score"] > HIGH_THRESHOLD, "level"] = "high"
    panel.loc[panel["ret20_pct"] > RET20_EXTREME_PCTL, "level"] = "high"  # 急涨直接 high
    panel.loc[panel["ci_score"].isna(), "level"] = "low"
    return panel


def future_drawdown_series(close, K):
    """单股 close 序列 → 未来 K 日最大回撤序列 (负值, 当日为基点)."""
    arr = close.to_numpy(dtype=float)
    n = len(arr)
    out = np.full(n, np.nan)
    for t in range(n - K):
        base = arr[t]
        if base > 0 and not np.isnan(base):
            w = arr[t:t + K + 1]
            out[t] = np.nanmin(w) / base - 1
    return pd.Series(out, index=close.index)


def add_future_drawdowns(panel, horizons):
    for K in horizons:
        panel[f"future_dd_{K}"] = panel.groupby("code", group_keys=False)["close"].transform(
            lambda s, K=K: future_drawdown_series(s, K))
    return panel


def summarize(panel, train_cutoff, horizons, dd_threshold):
    """分 train/test, 按 level 分组: 命中率/平均回撤/IC."""
    cutoff_ts = pd.Timestamp(train_cutoff)
    out = {}
    for split, sub in [("train", panel[panel["trade_date"] <= cutoff_ts]),
                       ("test", panel[panel["trade_date"] > cutoff_ts])]:
        split_out = {}
        for K in horizons:
            col = f"future_dd_{K}"
            d = sub.dropna(subset=[col, "level"])
            res = {"n": int(len(d))}
            for lvl in ("high", "medium", "low"):
                dd = d[d["level"] == lvl][col]
                if len(dd):
                    res[lvl] = {"n": int(len(dd)),
                                "hit_rate": float((dd < dd_threshold).mean()),
                                "avg_drawdown": float(dd.mean())}
            if len(d):
                res["baseline_hit_rate"] = float((d[col] < dd_threshold).mean())
            valid = d.dropna(subset=["ci_score", col])
            if len(valid) > 30:
                # IC: crowding_score vs 未来回撤. 负 = 有效 (高拥挤→大回撤)
                res["ic"] = float(valid["ci_score"].corr(valid[col]))
            split_out[f"horizon_{K}d"] = res
        out[split] = split_out
    return out


def _timeline_guard(strategy_path, train_cutoff, strict):
    """对齐 walk_forward M01: 复用其 _git_strategy_commit + _timeline_guard_decision."""
    try:
        from walk_forward import _git_strategy_commit, _timeline_guard_decision
    except Exception:
        return {"exit": False, "message": ""}
    info = _git_strategy_commit(strategy_path)
    # walk_forward 的 guard 用 start_month; 这里用 train_cutoff 作样本外起点
    guard = _timeline_guard_decision(info, train_cutoff, strict)
    print(f"📌 策略: {info.get('path')} commit {str(info.get('commit',''))[:12]} ({info.get('date')})")
    return guard


def main():
    p = argparse.ArgumentParser(description="拥挤度→回撤预警 回测")
    p.add_argument("--start", default="2024-01")
    p.add_argument("--end", default="2026-06")
    p.add_argument("--train-cutoff", default="2025-12", help="train/test 分界月 (样本外起点)")
    p.add_argument("--board", default="688", choices=["688", "all"])
    p.add_argument("--lookback", type=int, default=250)
    p.add_argument("--horizons", default="5,10,20")
    p.add_argument("--drawdown-threshold", type=float, default=-0.05, help="回撤阈值 (-0.05=-5%%)")
    p.add_argument("--strict-timeline", action="store_true", help="对齐 walk_forward M01 时序护栏")
    p.add_argument("--export", default=None)
    args = p.parse_args()

    horizons = [int(x) for x in args.horizons.split(",")]

    # M01 时序护栏 (crowding_drawdown.py 为策略文件)
    strat = os.path.join(_PROJ, "packages", "kronos-factors", "kronos_factors",
                         "scorer", "crowding_drawdown.py")
    guard = _timeline_guard(strat, args.train_cutoff, args.strict_timeline)
    if guard.get("exit"):
        print(guard["message"]); sys.exit(guard.get("code", 2))

    setup_db()
    from kronos_factors.scorer._db_stub import _get_db
    with _get_db() as db:
        codes = load_universe(db, args.board)
        print(f"候选池 ({args.board}): {len(codes)} 只")
        panel = load_panel(db, codes, args.start, args.end, args.lookback)
        print(f"面板: {len(panel)} 行, {panel['code'].nunique()} 只, "
              f"{panel['trade_date'].min().date()} ~ {panel['trade_date'].max().date()}")

    panel = add_crowding(panel, args.lookback)
    panel = add_future_drawdowns(panel, horizons)
    # 只保留回测区间内 (去掉 lookback padding 段)
    panel = panel[panel["trade_date"] >= pd.Timestamp(args.start)]

    result = summarize(panel, args.train_cutoff, horizons, args.drawdown_threshold)
    print(f"\n{'='*60}\n回测摘要 (回撤阈值 {args.drawdown_threshold:.0%})")
    for split in ("train", "test"):
        print(f"\n[{split.upper()}] <= {args.train_cutoff}" if split == "train"
              else f"\n[{split.upper()}] > {args.train_cutoff} (样本外)")
        for hkey, r in result[split].items():
            print(f"  {hkey}: n={r.get('n',0)} baseline命中={r.get('baseline_hit_rate',0):.1%} "
                  f"IC={r.get('ic','-')}")
            for lvl in ("high", "medium", "low"):
                if lvl in r:
                    print(f"    {lvl:6}: n={r[lvl]['n']:5} 命中={r[lvl]['hit_rate']:.1%} "
                          f"均回撤={r[lvl]['avg_drawdown']:.2%}")
    print(f"\n判定: 高拥挤组命中率 > 低拥挤组/基准 且 IC<0 → 信号有效 (方向: 回避/减仓)")

    if args.export:
        json.dump(result, open(args.export, "w"), ensure_ascii=False, indent=2, default=str)
        print(f"导出: {args.export}")


if __name__ == "__main__":
    main()
