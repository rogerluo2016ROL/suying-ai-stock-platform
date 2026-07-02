#!/usr/bin/env python3
"""机构活跃度因子 — 月频 IC + 分组多空回测。

验收标准 (项目惯例, 参考 bi_trend 回测):
  - Rank IC 均值 > 0.03 且 ICIR > 0.5 → 因子有弱信号
  - ICIR > 1.0 → 强信号
  - Top组 - Bottom组年化多空 > 10% → 分组有效
  - IC 胜率 > 55% → 稳定

独立因子验证, 不接入午后选股 (用户要求)。

Usage:
    KRONOS_PG_URL=postgresql://kronos:kronos@localhost:6432/kronos \\
    python tools/backtest_institutional_activity.py --months 36 --horizon 20
"""
import argparse, os, sys
import psycopg2
import pandas as pd
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from institutional_activity_top import calc_top  # 复用因子计算


def _conn():
    return psycopg2.connect(os.environ.get("KRONOS_PG_URL", "postgresql://kronos:kronos@localhost:6432/kronos"))


def month_end_trade_dates(conn, n_months):
    """近 n_months 个月的月末交易日 (按 natural month 去重取最后交易日)."""
    df = pd.read_sql("SELECT DISTINCT trade_date FROM daily_kline ORDER BY trade_date", conn)
    df["ym"] = pd.to_datetime(df["trade_date"]).dt.to_period("M")
    me = df.groupby("ym")["trade_date"].max().reset_index()
    me = me.sort_values("trade_date").tail(n_months)
    return me["trade_date"].tolist()


def fwd_returns(conn, dates, horizon):
    """每个日期的全市场 horizon 交易日前瞻收益. 返回 {date: {code: ret}}."""
    all_dates = pd.read_sql("SELECT DISTINCT trade_date FROM daily_kline ORDER BY trade_date", conn)["trade_date"].tolist()
    dt_idx = {d: i for i, d in enumerate(all_dates)}
    out = {}
    for d in dates:
        i = dt_idx.get(d)
        if i is None or i + horizon >= len(all_dates):
            continue  # 前瞻不足, 跳过
        d_fwd = all_dates[i + horizon]
        df = pd.read_sql(
            f"""SELECT a.code, (b.close/a.close - 1) ret FROM daily_kline a
                JOIN daily_kline b ON a.code=b.code AND b.trade_date='{d_fwd}'
                WHERE a.trade_date='{d}'""", conn)
        out[d] = dict(zip(df["code"].astype(str), df["ret"]))
    return out


def rank_ic(scores: dict, rets: dict):
    """Spearman Rank IC: 两个 dict 的共同 code 做 rank 相关."""
    common = sorted(set(scores) & set(rets))
    if len(common) < 30:
        return None
    s = pd.Series([scores[c] for c in common]).rank()
    r = pd.Series([rets[c] for c in common]).rank()
    return float(s.corr(r))


def quantile_group_ret(scores: dict, rets: dict, n_groups=5):
    """按因子分 n_groups 组, 返回各组平均收益 (Top组=index 0)."""
    common = sorted(set(scores) & set(rets))
    if len(common) < n_groups * 10:
        return None
    df = pd.DataFrame({"s": [scores[c] for c in common], "r": [rets[c] for c in common]}, index=common)
    df = df.sort_values("s", ascending=False)  # 高分在前
    df["g"] = pd.qcut(df["s"].rank(method="first"), n_groups, labels=False)  # 0=最高
    g = df.groupby("g")["r"].mean()
    return [g.get(i, np.nan) for i in range(n_groups)]  # [Top...Bottom]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--months", type=int, default=36)
    ap.add_argument("--horizon", type=int, default=20, help="前瞻交易日 (约1月)")
    args = ap.parse_args()

    conn = _conn()
    print(f"机构活跃度因子 IC 回测: 近{args.months}月, 前瞻{args.horizon}交易日\n")
    dates = month_end_trade_dates(conn, args.months)
    print(f"月末交易日: {dates[0]} → {dates[-1]} ({len(dates)}个)")

    rets_all = fwd_returns(conn, dates, args.horizon)
    valid_dates = [d for d in dates if d in rets_all]
    print(f"有效 (前瞻收益可得): {len(valid_dates)}个\n")

    ics, top_rets, bot_rets, ls_rets = [], [], [], []
    print(f"{'月末':<12}{'RankIC':>8}{'Top组':>9}{'Bot组':>9}{'多空':>9}{'样本':>7}")
    print("-" * 60)
    for d in valid_dates:
        top = calc_top(end_date=d, top_n=9999, conn=conn)  # 全市场截面综合分
        scores = dict(zip(top.index.astype(str), top["综合分"]))
        rets = rets_all[d]
        ic = rank_ic(scores, rets)
        if ic is None:
            continue
        gs = quantile_group_ret(scores, rets, 5)
        top_r = gs[0] if gs else np.nan
        bot_r = gs[-1] if gs else np.nan
        ls = top_r - bot_r if gs else np.nan
        ics.append(ic)
        if gs:
            top_rets.append(top_r); bot_rets.append(bot_r); ls_rets.append(ls)
        print(f"{str(d):<12}{ic:>+8.3f}{top_r:>9.3f}{bot_r:>9.3f}{ls:>9.3f}{len(set(scores)&set(rets)):>7}")

    if not ics:
        print("\n❌ 无有效 IC 样本"); conn.close(); return
    ics = np.array(ics)
    print(f"\n{'='*60}")
    print(f"  汇总 ({len(ics)}个月样本, {args.horizon}交易日前瞻)")
    print(f"{'='*60}")
    print(f"  Rank IC 均值     : {ics.mean():+.4f}")
    print(f"  Rank IC 标准差   : {ics.std():.4f}")
    print(f"  ICIR (均值/标准差): {ics.mean()/ics.std():+.3f}  {'✅强' if abs(ics.mean())/ics.std()>1 else '✅中' if abs(ics.mean())/ics.std()>0.5 else '❌弱'}")
    print(f"  IC 胜率 (IC>0)   : {(ics>0).mean()*100:.1f}%  {'✅' if (ics>0).mean()>0.55 else '❌'}")
    if ls_rets:
        ls = np.array(ls_rets)
        ann = ls.mean() / args.horizon * 243  # 年化 (按交易日)
        print(f"  Top组平均收益    : {np.mean(top_rets)*100:+.2f}%")
        print(f"  Bot组平均收益    : {np.mean(bot_rets)*100:+.2f}%")
        print(f"  多空 (Top-Bot)   : {ls.mean()*100:+.2f}% (月均) | 年化 {ann*100:+.1f}%")
    print(f"\n  判定: ", end="")
    icir = abs(ics.mean())/ics.std()
    ls_mean = np.mean(ls_rets) if ls_rets else 0
    if icir > 0.5 and (ics > 0).mean() > 0.55 and ls_mean > 0:
        print("✅ 因子可单边做多Top (IC正+多空正), 建议扩展10年+样本外验证")
    elif icir > 0.5 and (ics > 0).mean() > 0.55 and ls_mean <= 0:
        print(f"⚠️ IC正但Top组追高回落(极端值反转, 多空{ls_mean*100:+.1f}%), 不能单边做多Top")
        print("     → 因子有信息量但非线性: 适合作组合/共振/剔除因子, 不适合单独选股Top")
        print("     → Bot组(低机构活跃)收益高, 需查是否可交易(流动性/幸存者偏差)")
    elif icir > 0.3:
        print("⚠️ 信号弱, 可能需调权重/窗口, 慎用")
    else:
        print("❌ 因子无显著 alpha (IC 接近 0 或不稳定), 建议放弃或根本重设")
    conn.close()


if __name__ == "__main__":
    main()
