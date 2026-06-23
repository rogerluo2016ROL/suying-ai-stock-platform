#!/usr/bin/env python3
"""毕师傅 bi_trend OOS 归因诊断 (V13 选股逻辑优化 · 第1步).

目的
----
walk-forward 样本外 (2024-01~2025-12, 24 月, 冻结参数) 夏普 ≈ -3.18, 月均 -1.16%,
24 月仅 3 月为正. 退出结构: hold_to_maturity 52.7% / trailing_stop 42.8% / take_profit 0.7%.
疑似 "trailing 在震荡市反复锁小亏 + TP 够不着" 的不对称退出伤害.

本脚本做 **纯诊断归因**, 不改任何策略源码 / 不动 params (守 walk_forward 铁律):
  - 每个 OOS 月每个交易日只跑一次选股 (瓶颈), 缓存 pick 列表.
  - 对同一批 pick 用 simulate_position 直接换 4 种退出配置重模拟 (同一批 bars, 仅退出不同).
  - 横向对比各臂的月均 net / sharpe-like / 胜率 / 退出原因, 定位最大杠杆点.

对照臂 (全部用冻结默认 hold=5, tp=15, sl=-10, weight=1.0, cost=14bp, 与 -3.18 基线口径一致):
  baseline        : trailing ON  + TP 15 + SL -10       (复现基线)
  no_trailing     : trailing OFF + TP 15 + SL -10       (trailing 单独贡献)
  no_tp           : trailing ON  + TP 关 + SL -10       (TP 是否封死上涨端)
  hold_hardstop   : trailing OFF + TP 关 + SL -10       (纯入场质量: 买持+灾难止损)

regime 分档: 按 SH(000001) 月度涨跌幅把 24 月分 bull/flat/bear, 看正收益是否只来自反弹月.

⚠️ 诊断性跑批: 选股用 HEAD 引擎 (携带样本内调参), 不可作样本外结论, 仅用于归因定位.
   基线臂数值应接近 (但不严格等于) frozen walk_forward, 因 pick 集合来自 HEAD 而非 frozen checkout.

Usage:
    KRONOS_PG_URL=postgresql://kronos:kronos@localhost:6432/kronos \
    python tools/walk_forward_attribution.py --start 2024-01 --end 2025-12 \
        --cost-bps 14 --cache outputs/wf_attr_picks.json \
        --export outputs/wf_attribution_2024-2025.json
"""
import argparse
import json
import os
import sys
import time
from collections import defaultdict

import numpy as np

_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for pkg in ["packages/kronos-factors", "packages/kronos-core", "packages/kronos-data"]:
    path = os.path.join(_PROJ, pkg)
    if os.path.isdir(path) and path not in sys.path:
        sys.path.insert(0, path)
_TOOLS = os.path.join(_PROJ, "tools")
if os.path.isdir(_TOOLS) and _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)

from backtest_bi_trend import (  # noqa: E402
    setup_db, get_trading_days, run_backtest_day,
    get_adjusted_bars, simulate_position,
)


# ── 冻结默认参数 (与 walk_forward --frozen 一致, V5.9 调参前) ──
FROZEN = {"hold_days": 5, "tp": 15.0, "sl": -10.0, "weight": 1.0}

# 对照臂: (tp_pct, stop_loss_pct, trailing_active_pct)  trailing_active=1e9 ≡ 关闭 trailing
ARMS = {
    "baseline":      (FROZEN["tp"], FROZEN["sl"], 5.0),
    "no_trailing":   (FROZEN["tp"], FROZEN["sl"], 1e9),
    "no_tp":         (None,         FROZEN["sl"], 5.0),
    "hold_hardstop": (None,         FROZEN["sl"], 1e9),
}


def month_iter(start, end):
    """YYYY-MM 字符串迭代 [start, end]."""
    sy, sm = map(int, start.split("-"))
    ey, em = map(int, end.split("-"))
    out, y, m = [], sy, sm
    while (y, m) <= (ey, em):
        out.append(f"{y:04d}-{m:02d}")
        m += 1
        if m > 12:
            m, y = 1, y + 1
    return out


def collect_picks(db, months, top_n, cache_path):
    """跑选股, 缓存 pick 元数据 (code/trade_date/grade/weight). 复用缓存跳过选股."""
    if cache_path and os.path.exists(cache_path):
        with open(cache_path) as f:
            cached = json.load(f)
        if cached.get("months") == months and cached.get("top_n") == top_n:
            print(f"📦 复用缓存 pick 列表: {cache_path} ({sum(len(v) for v in cached['picks'].values())} picks)")
            return cached["picks"]
        print(f"⚠️ 缓存月份/top_n 不匹配, 重新跑选股")

    picks_by_month = {m: [] for m in months}
    total = 0
    for mi, month in enumerate(months):
        tds = get_trading_days(db, month)
        if not tds:
            continue
        mcount = 0
        for i, td in enumerate(tds):
            try:
                r = run_backtest_day(db, td, top_n=top_n)
            except Exception as e:
                print(f"  {td} 选股失败: {e}")
                continue
            for s in r.get("top_picks", []):
                picks_by_month[month].append({
                    "code": s["code"], "trade_date": td,
                    "grade": s.get("grade"), "weight": s.get("weight", 1.0),
                })
                mcount += 1
        total += mcount
        print(f"  [{mi+1}/{len(months)}] {month}: {len(tds)} 交易日, {mcount} picks")
    print(f"  选股完成: 共 {total} picks")
    if cache_path:
        with open(cache_path, "w") as f:
            json.dump({"months": months, "top_n": top_n, "picks": picks_by_month}, f)
        print(f"  缓存已写: {cache_path}")
    return picks_by_month


def simulate_arm(bars, tp_pct, sl_pct, trailing_active, hold_days, cost_bps):
    """对一组 bars 跑单臂模拟, 返回 (net_return, exit_reason) 或 None."""
    if len(bars) < 2:
        return None
    res = simulate_position(
        bars, signal_idx=0, hold_days=hold_days,
        tp_pct=tp_pct, stop_loss_pct=sl_pct,
        trailing_active_pct=trailing_active, trailing_drawdown_pct=None,
    )
    if res is None:
        return None
    return res["gross_return"] - cost_bps / 100.0, res["exit_reason"]


def sh_monthly_return(db, month):
    """SH(000001) 月度涨跌幅 %: 月末收盘 / 月初前一交易日收盘 - 1."""
    tds = get_trading_days(db, month)
    if not tds:
        return None
    first, last = tds[0], tds[-1]
    # 月初基准: 取 first 当日 close (若要前一交易日更精确, 但月初当日 close 足够分档)
    rows = db.execute(
        "SELECT trade_date, close FROM index_daily WHERE code='000001' "
        "AND trade_date >= ? ORDER BY trade_date ASC LIMIT ?",
        (first, len(tds) + 2),
    ).fetchall()
    closes = [r["close"] for r in rows if r["close"]]
    if len(closes) < 2:
        return None
    # 用月内首尾交易日 close
    return (closes[-1] / closes[0] - 1) * 100


def regime_bucket(sh_ret):
    if sh_ret is None:
        return "unknown"
    if sh_ret <= -2.0:
        return "bear"
    if sh_ret >= 2.0:
        return "bull"
    return "flat"


def summarize_arm(monthly_results):
    """monthly_results: {month: [(net, reason), ...]} -> 聚合统计."""
    monthly_net = []
    all_reasons = defaultdict(int)
    all_net = []
    per_month_mean = {}
    for month, trades in monthly_results.items():
        if not trades:
            per_month_mean[month] = None
            continue
        nets = [t[0] for t in trades]
        wmean = float(np.mean(nets))  # weight=1.0 → 加权=等权
        per_month_mean[month] = wmean
        monthly_net.append(wmean)
        all_net.extend(nets)
        for _, r in trades:
            all_reasons[r] += 1
    arr = np.array(monthly_net) if monthly_net else np.array([])
    sharpe = (arr.mean() / arr.std(ddof=1) * np.sqrt(12)) if len(arr) > 1 and arr.std(ddof=1) > 0 else float("nan")
    all_arr = np.array(all_net) if all_net else np.array([])
    tot_exits = sum(all_reasons.values()) or 1
    return {
        "n_months": len(monthly_net),
        "monthly_net_mean": float(arr.mean()) if len(arr) else float("nan"),
        "monthly_net_std": float(arr.std(ddof=1)) if len(arr) > 1 else float("nan"),
        "sharpe_like": float(sharpe),
        "pos_months": int((arr > 0).sum()) if len(arr) else 0,
        "trade_mean": float(all_arr.mean()) if len(all_arr) else float("nan"),
        "trade_winrate": float((all_arr > 0).mean() * 100) if len(all_arr) else float("nan"),
        "exit_reasons": {k: v for k, v in all_reasons.items()},
        "exit_pct": {k: round(v / tot_exits * 100, 1) for k, v in all_reasons.items()},
        "per_month_mean": per_month_mean,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2024-01")
    ap.add_argument("--end", default="2025-12")
    ap.add_argument("--top-n", type=int, default=20)
    ap.add_argument("--cost-bps", type=float, default=14.0)
    ap.add_argument("--cache", default="outputs/wf_attr_picks.json")
    ap.add_argument("--export", default=None)
    args = ap.parse_args()

    months = month_iter(args.start, args.end)
    print(f"📅 归因诊断 OOS: {args.start} ~ {args.end} ({len(months)} 月)")
    print(f"   冻结参数: hold={FROZEN['hold_days']} tp={FROZEN['tp']} sl={FROZEN['sl']} weight={FROZEN['weight']} cost={args.cost_bps}bp")
    print(f"   对照臂: {list(ARMS.keys())}")
    print(f"   ⚠️ 诊断性跑批 (HEAD 引擎), 不可作样本外结论\n")

    db = setup_db()

    # 1) 选股 + 缓存
    picks_by_month = collect_picks(db, months, args.top_n, args.cache)

    # 2) 每月 SH 月度涨跌 (regime)
    sh_by_month = {m: sh_monthly_return(db, m) for m in months}

    # 3) 对每个 pick 取一次 bars, 4 臂重模拟
    arm_monthly = {a: {m: [] for m in months} for a in ARMS}
    t0 = time.time()
    npicks = 0
    for month in months:
        for p in picks_by_month.get(month, []):
            bars = get_adjusted_bars(db, p["code"], p["trade_date"], max_hold_days=FROZEN["hold_days"])
            if len(bars) < 2:
                continue
            npicks += 1
            for aname, (tp, sl, tactive) in ARMS.items():
                r = simulate_arm(bars, tp, sl, tactive, FROZEN["hold_days"], args.cost_bps)
                if r is not None:
                    arm_monthly[aname][month].append(r)
    print(f"\n  重模拟完成: {npicks} picks × 4 臂, {time.time()-t0:.0f}s\n")

    # 4) 聚合 + 输出
    summary = {a: summarize_arm(arm_monthly[a]) for a in ARMS}

    print("=" * 92)
    print(f"  {'臂':<16} {'月均net%':>9} {'sharpe':>8} {'正月/总':>8} {'笔均net%':>9} {'胜率%':>6} {'trailing%':>9} {'TP%':>5} {'hold%':>6}")
    print("-" * 92)
    for a in ARMS:
        s = summary[a]
        print(f"  {a:<16} {s['monthly_net_mean']:>+9.3f} {s['sharpe_like']:>+8.2f} "
              f"{s['pos_months']:>4}/{s['n_months']:<3} {s['trade_mean']:>+9.3f} "
              f"{s['trade_winrate']:>6.1f} {s['exit_pct'].get('trailing_stop',0):>9.1f} "
              f"{s['exit_pct'].get('take_profit',0):>5.1f} {s['exit_pct'].get('hold_to_maturity',0):>6.1f}")
    print("=" * 92)

    # 归因增量 (相对 baseline)
    base = summary["baseline"]["monthly_net_mean"]
    print("\n  归因增量 (相对 baseline 月均 net):")
    for a in ARMS:
        if a == "baseline":
            continue
        delta = summary[a]["monthly_net_mean"] - base
        print(f"    {a:<16} {delta:+.3f}%/月  ({'改善' if delta > 0 else '恶化' if delta < 0 else '持平'})")

    # 5) regime 分档 (baseline 臂)
    print("\n  regime 分档 (baseline 臂, 按 SH 月度涨跌):")
    print(f"  {'regime':<8} {'月数':>4} {'月均net%':>9} {'正月数':>6} {'笔胜率%':>7}")
    by_reg = defaultdict(list)
    for m in months:
        b = regime_bucket(sh_by_month[m])
        nm = summary["baseline"]["per_month_mean"].get(m)
        if nm is not None:
            by_reg[b].append((m, nm))
    for b in ["bull", "flat", "bear", "unknown"]:
        if not by_reg[b]:
            continue
        nets = [x[1] for x in by_reg[b]]
        pos = sum(1 for n in nets if n > 0)
        print(f"  {b:<8} {len(by_reg[b]):>4} {np.mean(nets):>+9.3f} {pos:>6} "
              f"{summary['baseline']['trade_winrate']:>7.1f}")
    print("  (注: 笔胜率为全样本, 非该 regime 内)")

    if args.export:
        out = {
            "design": {"frozen": FROZEN, "cost_bps": args.cost_bps, "arms": {a: list(v) for a, v in ARMS.items()},
                       "range": [args.start, args.end], "engine": "HEAD (diagnostic, not OOS-valid)"},
            "arms": summary,
            "sh_monthly": sh_by_month,
            "regime": {m: regime_bucket(sh_by_month[m]) for m in months},
        }
        with open(args.export, "w") as f:
            json.dump(out, f, indent=2, default=str)
        print(f"\n  导出: {args.export}")


if __name__ == "__main__":
    main()
