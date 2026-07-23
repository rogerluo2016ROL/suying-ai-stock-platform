#!/usr/bin/env python3
"""按信号日聚合毕师傅趋势战法回测 trades：每日胜率与等权平均净收益率。

输入：tools/backtest_bi_shifu_trend_1y.py 产出的 JSON（含 trades）。
口径：
  - 胜 = net_return_pct > 0（已扣 14bp 双边成本）。
  - 当日批次收益率 = 该信号日全部成交票 net_return_pct 的算术平均（等权）。
  - 累积净值 = Π(1 + 当日批次收益率)，未考虑 allocation 资金占用（纯策略线）。
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("input", nargs="?", default="outputs/bt_bishifu_3m_20260716.json")
    ap.add_argument("--csv", default="outputs/bt_bishifu_3m_daily.csv")
    args = ap.parse_args()

    data = json.loads(Path(args.input).read_text())
    summary = data.get("summary", {})
    trades = data.get("trades", [])

    by_day: dict[str, list[float]] = defaultdict(list)
    for t in trades:
        by_day[t["signal_date"]].append(float(t["net_return_pct"]))

    rows = []
    for d in sorted(by_day):
        rs = by_day[d]
        wins = sum(1 for r in rs if r > 0)
        rows.append({
            "signal_date": d,
            "month": d[:7],
            "n": len(rs),
            "wins": wins,
            "win_rate_pct": round(wins / len(rs) * 100, 1),
            "mean_ret_pct": round(float(np.mean(rs)), 3),
            "median_ret_pct": round(float(np.median(rs)), 3),
            "max_ret_pct": round(float(np.max(rs)), 2),
            "min_ret_pct": round(float(np.min(rs)), 2),
        })

    # 累积净值（按信号日等权批次收益连乘）
    equity = 1.0
    for r in rows:
        equity *= (1.0 + r["mean_ret_pct"] / 100.0)
        r["cum_equity"] = round(equity, 4)

    # 月度汇总
    monthly: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        monthly[r["month"]].append(r)
    month_rows = []
    for m in sorted(monthly):
        ms = monthly[m]
        all_ret = [x for r in ms for x in by_day[r["signal_date"]]]
        mw = sum(1 for x in all_ret if x > 0)
        month_rows.append({
            "month": m,
            "signal_days": len(ms),
            "trades": len(all_ret),
            "win_rate_pct": round(mw / len(all_ret) * 100, 1),
            "avg_trade_pct": round(float(np.mean(all_ret)), 3),
            "month_mean_pct": round(float(np.mean([r["mean_ret_pct"] for r in ms])), 3),
        })

    # 整体
    all_ret = [float(t["net_return_pct"]) for t in trades]
    gw = sum(1 for r in all_ret if r > 0)
    overall = {
        "signal_days": len(by_day),
        "trades": len(all_ret),
        "win_rate_pct": round(gw / len(all_ret) * 100, 2) if all_ret else 0.0,
        "avg_trade_pct": round(float(np.mean(all_ret)), 3) if all_ret else 0.0,
        "median_trade_pct": round(float(np.median(all_ret)), 3) if all_ret else 0.0,
        "cum_equity_equal_weight": round(equity, 4),
        "strategy_total_return_pct": round((equity - 1) * 100, 2),
    }

    # 输出 CSV（每日明细）
    csv_path = Path(args.csv)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w") as f:
        f.write("signal_date,n,wins,win_rate_pct,mean_ret_pct,median_ret_pct,max_ret_pct,min_ret_pct,cum_equity\n")
        for r in rows:
            f.write(f"{r['signal_date']},{r['n']},{r['wins']},{r['win_rate_pct']},"
                    f"{r['mean_ret_pct']},{r['median_ret_pct']},{r['max_ret_pct']},{r['min_ret_pct']},{r['cum_equity']}\n")

    # 控制台打印
    print("=" * 70)
    print("整体（最近三个月，按信号日等权）")
    print("=" * 70)
    print(json.dumps(overall, ensure_ascii=False, indent=2))
    print(f"\n资金曲线口径 summary（脚本自带，含 50% allocation 资金管理）:")
    for k in ("signal_date_range", "total_trades", "win_rate_pct", "avg_trade_return_pct",
              "total_return_pct", "max_drawdown_pct"):
        if k in summary:
            print(f"  {k}: {summary[k]}")

    print("\n" + "=" * 70)
    print("月度汇总")
    print("=" * 70)
    print(f"{'月份':<10}{'信号日':>6}{'笔数':>6}{'胜率%':>8}{'单笔均%':>9}{'日均%':>8}")
    for m in month_rows:
        print(f"{m['month']:<10}{m['signal_days']:>6}{m['trades']:>6}{m['win_rate_pct']:>8}"
              f"{m['avg_trade_pct']:>9}{m['month_mean_pct']:>8}")

    print("\n" + "=" * 70)
    print("每日明细（按信号日）")
    print("=" * 70)
    print(f"{'信号日':<12}{'只数':>5}{'胜':>4}{'胜率%':>7}{'均收%':>9}{'中位%':>9}{'最大%':>9}{'最小%':>9}{'累积净值':>10}")
    for r in rows:
        print(f"{r['signal_date']:<12}{r['n']:>5}{r['wins']:>4}{r['win_rate_pct']:>7}"
              f"{r['mean_ret_pct']:>9}{r['median_ret_pct']:>9}{r['max_ret_pct']:>9}"
              f"{r['min_ret_pct']:>9}{r['cum_equity']:>10}")

    print(f"\n每日明细 CSV: {csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
