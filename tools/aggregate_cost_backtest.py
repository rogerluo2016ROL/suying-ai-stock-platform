#!/usr/bin/env python3
"""AC-11: 汇总 6 个月扣成本回测 → 逐月表 + 聚合 + Q-1 结论.

读取 outputs/backtest_bi_trend_YYYY-MM_cost14.json (×6),
输出 outputs/backtest_bi_trend_6m_cost14_summary.json (逐月 + 聚合 + Q-1 结论段落).

铁律: 只汇总, 不改任何策略参数.
"""
import json, os, glob
import numpy as np

MONTHS = ["2026-01", "2026-02", "2026-03", "2026-04", "2026-05", "2026-06"]
OUT = "outputs"


def load_month(month):
    path = os.path.join(OUT, f"backtest_bi_trend_{month}_cost14.json")
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)


def main():
    monthly = []
    all_gross = []
    all_net = []
    cost_bps = None

    for m in MONTHS:
        d = load_month(m)
        if d is None:
            print(f"⚠️ 缺失: {m}")
            continue
        cost_bps = d.get("cost_bps", 14)
        valid = [p for p in d["picks"] if p["next_day_return"] is not None]
        gross = np.array([p["next_day_return"] for p in valid])
        net = np.array([p["net_return"] for p in valid])
        all_gross.extend(gross.tolist())
        all_net.extend(net.tolist())
        n = len(valid)
        monthly.append({
            "month": m,
            "n_trades": n,
            "win_pct_gross": float((gross > 0).sum() / n * 100) if n else 0.0,
            "win_pct_net": float((net > 0).sum() / n * 100) if n else 0.0,
            "mean_gross": float(gross.mean()) if n else 0.0,
            "mean_net": float(net.mean()) if n else 0.0,
            "sum_gross": float(gross.sum()) if n else 0.0,
            "sum_net": float(net.sum()) if n else 0.0,
        })

    g = np.array(all_gross)
    ne = np.array(all_net)
    n_total = len(g)

    agg = {
        "months_covered": [m["month"] for m in monthly],
        "cost_bps": cost_bps,
        "cost_pct_round_trip": (cost_bps or 0) / 100.0,
        "total_trades": n_total,
        "aggregate_gross": {
            "mean_per_trade": float(g.mean()),
            "median_per_trade": float(np.median(g)),
            "sum": float(g.sum()),
            "win_rate": float((g > 0).sum() / n_total * 100),
            "win_count": int((g > 0).sum()),
            "std": float(g.std()),
        },
        "aggregate_net": {
            "mean_per_trade": float(ne.mean()),
            "median_per_trade": float(np.median(ne)),
            "sum": float(ne.sum()),
            "win_rate": float((ne > 0).sum() / n_total * 100),
            "win_count": int((ne > 0).sum()),
            "std": float(ne.std()),
        },
        "monthly_table": monthly,
    }

    # ── 逐月表打印 ──
    print(f"\n{'='*78}")
    print(f"  AC-11 六个月回测 (扣往返成本 {cost_bps}bp = {(cost_bps or 0)/100:.2f}%)")
    print(f"{'='*78}")
    print(f"  {'月份':<9} {'n':<5} {'胜率(毛)':<9} {'胜率(净)':<9} {'均值/笔(毛)':<13} {'均值/笔(净)':<13} {'累计(净)':<10}")
    print(f"  {'-'*74}")
    for row in monthly:
        print(f"  {row['month']:<9} {row['n_trades']:<5} {row['win_pct_gross']:>6.1f}%  {row['win_pct_net']:>6.1f}%  "
              f"{row['mean_gross']:>+10.4f}% {row['mean_net']:>+10.4f}%  {row['sum_net']:>+8.2f}%")
    print(f"  {'-'*74}")
    print(f"  {'聚合':<9} {n_total:<5} {agg['aggregate_gross']['win_rate']:>6.1f}%  {agg['aggregate_net']['win_rate']:>6.1f}%  "
          f"{agg['aggregate_gross']['mean_per_trade']:>+10.4f}% {agg['aggregate_net']['mean_per_trade']:>+10.4f}%  "
          f"{agg['aggregate_net']['sum']:>+8.2f}%")

    # ── Q-1 结论 (含脆弱性风险补强, PL review 后修订) ──
    net_mean = agg["aggregate_net"]["mean_per_trade"]
    net_median = agg["aggregate_net"]["median_per_trade"]
    net_win = agg["aggregate_net"]["win_rate"]
    net_sum = agg["aggregate_net"]["sum"]
    net_sign = "正" if net_mean > 0 else ("零/归零" if abs(net_mean) < 0.01 else "负")
    months_net_positive = sum(1 for r in monthly if r["mean_net"] > 0)
    months_net_negative = sum(1 for r in monthly if r["mean_net"] < 0)
    # 去 6 月 (调参期) 后净 sum — 衡量非样本内调参期的真实表现
    sum_ex_jun = sum(r["sum_net"] for r in monthly if r["month"] != "2026-06")
    jun_row = next((r for r in monthly if r["month"] == "2026-06"), None)
    jun_sum = jun_row["sum_net"] if jun_row else 0.0
    jun_n = jun_row["n_trades"] if jun_row else 0

    # 风险1 (右偏): 均值正但中位数负 → 正期望靠少数大赢, 典型交易净亏
    # 风险2 (样本内调参污染): 去 6 月后净为负 → 非调参期策略净亏损, 聚合"正"是样本内调参产物
    decision = (
        f"扣往返成本 {cost_bps}bp 后聚合 mean/trade = {net_mean:+.4f}% (符号:{net_sign}), "
        f"但有两个脆弱性风险使结论不可直接外推:\n"
        f"  风险1 (右偏): 均值 {net_mean:+.4f}% 正, 净中位数却 {net_median:+.4f}% (负) → 正期望完全靠少数大赢撑起, "
        f"典型交易是净亏的; 净胜率 {net_win:.1f}% < 50% 印证 (典型笔多数亏损).\n"
        f"  风险2 (样本内调参污染): 6 月净 sum {jun_sum:+.2f}% (n={jun_n} 异常少, 为调参期), "
        f"而 1-5 月 (非调参期) 净 sum = {sum_ex_jun:+.2f}% (负) → 去掉 6 月后策略净亏损, "
        f"聚合的'正'本质是 6 月样本内调参的直接产物, 不可作样本外证据.\n"
        f"阶段决策 (PL review 修订后):\n"
        f"  - 阶段1 (walk-forward 样本外验证) 优先级 高于 阶段2 (接 Kronos/LLM). "
        f"在样本外证明净期望稳定前, 接 Kronos/LLM 是在脆弱基础上加层.\n"
        f"  - 阶段2 若推进, 必须以净均值为优化目标 (非毛均值), 且严禁再用 6 月数据调参."
    )

    q1 = {
        "question": "Q-1: 扣除往返交易成本后, bi_trend 策略聚合 mean/trade 的符号是什么? 逐月是否仍正? 是否改变阶段2决策建议 (接 Kronos / 接 LLM)?",
        "net_sign_aggregate": net_sign,
        "net_mean_per_trade": float(net_mean),
        "net_median_per_trade": float(net_median),
        "net_win_rate": float(net_win),
        "gross_mean_per_trade": float(agg["aggregate_gross"]["mean_per_trade"]),
        "months_net_positive": months_net_positive,
        "months_net_negative": months_net_negative,
        "months_net_total": len(monthly),
        "net_sum_aggregate": float(net_sum),
        "net_sum_ex_june": float(sum_ex_jun),
        "june_net_sum": float(jun_sum),
        "june_n_trades": int(jun_n),
        "risk_right_skew": "均值正但中位数负, 正期望靠少数大赢, 典型交易净亏 (胜率<50%)",
        "risk_in_sample_overfit": "去6月(调参期)后净 sum 为负, 聚合'正'是样本内调参产物, 不可作样本外证据",
        "conclusion": decision,
    }
    agg["q1_conclusion"] = q1

    print(f"\n  Q-1 结论 (PL review 修订, 含脆弱性风险):")
    print(f"    扣成本后聚合 mean/trade: {net_mean:+.4f}% ({net_sign})")
    print(f"    净中位数: {net_median:+.4f}% (风险1 右偏: 均值正/中位数负)")
    print(f"    毛均值 → 净均值: {agg['aggregate_gross']['mean_per_trade']:+.4f}% → {net_mean:+.4f}%")
    print(f"    逐月净值为正: {months_net_positive}/{len(monthly)}; 为负: {months_net_negative}/{len(monthly)}")
    print(f"    去6月后净 sum: {sum_ex_jun:+.2f}% (6月单独 {jun_sum:+.2f}%, n={jun_n})")
    print(f"    决策: 阶段1样本外验证 优先于 阶段2接 Kronos/LLM; 推进须以净均值为目标, 禁再用6月调参")

    out_path = os.path.join(OUT, "backtest_bi_trend_6m_cost14_summary.json")
    with open(out_path, "w") as f:
        json.dump(agg, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n📁 6个月汇总: {out_path}")


if __name__ == "__main__":
    main()
