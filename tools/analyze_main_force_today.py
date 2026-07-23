#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""分析个股「今日主力是否在出货」。

数据来源（项目已落库 / Tushare 实时）：
  1. moneyflow  —— 大单/超大单/中单/小单买卖额 + net_mf_amount(主力净额)，日级(T 日盘后)
  2. daily_kline / daily_basic —— 价、涨跌幅、换手率、量比
  3. tushare realtime_tick —— 盘中逐笔(主买/主卖/中性)，盘中实时(当日有效)

判定维度（多信号交叉，非单一指标）：
  - 量价背离：当日收涨但主力净流出(出货典型特征)
  - 连续净流出：近 N 日主力净流出天数 + 累计净流出额
  - 大单/超大单方向：大资金分项净额
  - 散户接盘：小单净流入(主力把筹码派发给散户)
  - 盘中实时：主卖额 > 主买额 + 大单主动卖出

用法: python tools/analyze_main_force_today.py 002432 300795
环境: export TUSHARE_TOKEN=...  KRONOS_PG_URL 默认 localhost:6432/kronos
"""
import sys, os, psycopg2
import tushare as ts

ts.set_token(os.environ.get("TUSHARE_TOKEN", ""))
PG_URL = os.environ.get("KRONOS_PG_URL", "postgresql://kronos:kronos@localhost:6432/kronos")
W = 10_000.0  # 元 → 万元


def _ts_code(code: str) -> str:
    code = str(code)
    if code.startswith(("6", "5")):
        return code + ".SH"
    if code.startswith(("4", "8", "9")):
        return code + ".BJ"
    return code + ".SZ"


def hist_rows(code: str, n: int = 25):
    """近 n 个交易日：价/涨跌/换手/量比/主力分项净额。返回正序列表。"""
    conn = psycopg2.connect(PG_URL)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT m.trade_date, k.close, k.change_pct, b.turnover_rate_f AS turnover_rate, b.volume_ratio,
               m.net_mf_amount,
               m.buy_lg_amount  - m.sell_lg_amount  AS net_lg,
               m.buy_elg_amount - m.sell_elg_amount AS net_elg,
               m.buy_md_amount  - m.sell_md_amount  AS net_md,
               m.buy_sm_amount  - m.sell_sm_amount  AS net_sm,
               k.amount
        FROM moneyflow m
        JOIN daily_kline k ON m.code = k.code AND m.trade_date = k.trade_date
        LEFT JOIN daily_basic b ON m.code = b.code AND m.trade_date = b.trade_date
        WHERE m.code = %s
        ORDER BY m.trade_date DESC LIMIT %s
        """,
        (code, n),
    )
    rows = cur.fetchall()[::-1]
    conn.close()
    return rows


def realtime(code: str) -> dict:
    """盘中逐笔 → 主买/主卖/净额 + 大单主动方向。盘中才有效，盘后/历史日返回空。"""
    try:
        df = ts.realtime_tick(ts_code=_ts_code(code))
    except Exception as e:
        return {"err": str(e)[:120]}
    if df is None or len(df) == 0:
        return {"err": "empty (盘后或非交易日?)"}
    df = df[df["AMOUNT"].apply(lambda x: isinstance(x, (int, float)))]
    buy = df[df["TYPE"] == "买盘"]
    sell = df[df["TYPE"] == "卖盘"]
    mid = df[df["TYPE"] == "中性盘"]
    big = df[df["AMOUNT"] >= 500_000]  # 单笔≥50万视为大单逐笔
    big_buy, big_sell = big[big["TYPE"] == "买盘"], big[big["TYPE"] == "卖盘"]
    last_price = float(df["PRICE"].iloc[-1])
    return {
        "ticks": int(len(df)),
        "last_price": last_price,
        "buy_amt": float(buy["AMOUNT"].sum()),
        "sell_amt": float(sell["AMOUNT"].sum()),
        "mid_amt": float(mid["AMOUNT"].sum()),
        "net_amt": float(buy["AMOUNT"].sum() - sell["AMOUNT"].sum()),
        "buy_n": int(len(buy)),
        "sell_n": int(len(sell)),
        "big_buy_n": int(len(big_buy)),
        "big_sell_n": int(len(big_sell)),
        "big_buy_amt": float(big_buy["AMOUNT"].sum()),
        "big_sell_amt": float(big_sell["AMOUNT"].sum()),
    }


def analyze(code: str, name: str):
    rows = hist_rows(code, 25)
    if not rows:
        print(f"\n[{code} {name}] 无 moneyflow 历史数据")
        return
    print(f"\n{'='*78}\n【{code} {name}】  日级资金流(最新交易日={rows[-1][0]})  {'='*(78-30-len(name)*2)}")
    print(f"{'日期':12} {'收':>8} {'涨跌%':>7} {'换手f%':>7} {'量比':>5} "
          f"{'主力净(亿)':>11} {'大单净(亿)':>11} {'超大单净(亿)':>13} {'小单净(亿)':>11}")
    for d, close, pct, turn, vr, nmf, nlg, nelg, nmd, nsm, amt in rows[-15:]:
        nmf = nmf or 0; nlg = nlg or 0; nelg = nelg or 0; nsm = nsm or 0
        def f(x):
            return f"{x/W:+.0f}" if x is not None else "—"
        print(f"{str(d):12} {close:>8.2f} {(pct or 0):>+7.2f} {(turn or 0):>6.2f} "
              f"{(vr or 0):>5.2f} {f(nmf):>11} {f(nlg):>11} {f(nelg):>13} {f(nsm):>11}")

    # 近 5 日统计 (moneyflow 字段单位=万元, /1e4→亿元; kline.amount 单位=千元, /1e7→亿元)
    last5 = rows[-5:]
    main_net5 = sum((r[5] or 0) for r in last5)
    out_days = sum(1 for r in last5 if (r[5] or 0) < 0)
    lg_net5 = sum((r[6] or 0) for r in last5)
    elg_net5 = sum((r[7] or 0) for r in last5)
    sm_net5 = sum((r[9] or 0) for r in last5)
    amt5 = sum((r[10] or 0) for r in last5)
    div_days = sum(1 for r in last5 if (r[2] or 0) > 0 and (r[5] or 0) < 0)  # 涨但主力流出
    avg_turn = sum((r[3] or 0) for r in last5) / len(last5)
    main5_yi = main_net5 / 1e4
    amt5_yi = amt5 / 1e5  # 千元→亿元 (1千元=1e3元, 1亿=1e8元 → /1e5)
    main_ratio = abs(main5_yi) / amt5_yi * 100 if amt5_yi else 0
    print(f"\n  [近5日统计]")
    print(f"    主力净累计: {main5_yi:+.2f}亿 (占5日成交额 {main_ratio:.1f}%)  |  净流出天数: {out_days}/5  |  量价背离(涨但主力流出): {div_days}/5")
    print(f"    大单净: {lg_net5/1e4:+.2f}亿  |  超大单净: {elg_net5/1e4:+.2f}亿  |  小单净(散户): {sm_net5/1e4:+.2f}亿  |  5日成交额: {amt5_yi:.1f}亿")
    print(f"    平均换手率(自由流通 turnover_rate_f): {avg_turn:.2f}%")

    # 盘中实时
    rt = realtime(code)
    if "err" in rt:
        print(f"\n  [盘中实时] 取不到: {rt['err']}")
        rt_summary = None
    else:
        prev_close = rows[-1][1]  # 最新交易日收盘=昨收
        chg = (rt["last_price"] / prev_close - 1) * 100 if prev_close else 0
        print(f"\n  [盘中实时逐笔] 当前价 {rt['last_price']:.2f} (vs 昨收 {prev_close:.2f}, {chg:+.2f}%)")
        print(f"    笔数: 买{rt['buy_n']} / 卖{rt['sell_n']}  ({'卖压' if rt['sell_n']>rt['buy_n']*1.5 else '买偏' if rt['buy_n']>rt['sell_n']*1.5 else '均衡'})")
        print(f"    金额: 主买 {rt['buy_amt']/1e8:.3f}亿 / 主卖 {rt['sell_amt']/1e8:.3f}亿 / 净 {rt['net_amt']/1e8:+.3f}亿")
        print(f"    大单(≥50万): 主动买 {rt['big_buy_n']}笔 {rt['big_buy_amt']/1e8:.3f}亿 | 主动卖 {rt['big_sell_n']}笔 {rt['big_sell_amt']/1e8:.3f}亿")
        rt_summary = rt

    # —— 综合判定 (正分=出货倾向; 盘中主力净买入作反向减分, 修小盘股假阳性) ——
    score = 0
    reasons = []
    if main5_yi < 0 and main_ratio >= 5:
        score += 3; reasons.append(f"近5日主力净流出{main5_yi:.1f}亿(占成交{main_ratio:.0f}%,显著)")
    elif main5_yi < 0:
        score += 1; reasons.append(f"近5日主力净流出{main5_yi:.1f}亿(占成交{main_ratio:.0f}%,轻微)")
    if out_days >= 4:
        score += 1; reasons.append(f"5日中{out_days}日主力净流出")
    if div_days >= 2:
        score += 1; reasons.append(f"{div_days}次量价背离(涨但主力走)")
    if lg_net5 < 0 and elg_net5 < 0:
        score += 1; reasons.append("大单+超大单双双向净流出")
    if sm_net5 > 0 and main_net5 < 0:
        score += 1; reasons.append("散户小单接盘(主力→散户)")
    if rt_summary:
        if rt_summary["net_amt"] < 0:
            score += 2; reasons.append(f"盘中主力净流出{rt_summary['net_amt']/1e8:.2f}亿")
            if rt_summary["big_sell_amt"] > rt_summary["big_buy_amt"] * 1.2:
                score += 1; reasons.append("盘中大单主动卖出占优")
        else:
            score -= 3; reasons.append(f"⚠盘中主力净流入{rt_summary['net_amt']/1e8:+.2f}亿(反向,买入倾向)")
            if rt_summary["big_buy_amt"] > rt_summary["big_sell_amt"] * 1.2:
                score -= 1; reasons.append("盘中大单主动买入占优")

    if score >= 5:
        verdict = "🔴 主力出货信号明确"
    elif score >= 3:
        verdict = "🟠 偏向出货 / 高位分歧"
    elif score >= 1:
        verdict = "🟡 有出货迹象但不强烈"
    elif score <= -2:
        verdict = "🟢 未现出货(主力偏买入/吸筹)"
    else:
        verdict = "⚪ 信号中性"
    print(f"\n  ▶ 判定: {verdict}  (得分 {score})")
    for r in reasons:
        print(f"     · {r}")


if __name__ == "__main__":
    targets = sys.argv[1:]
    if not targets:
        targets = ["002432", "300795"]
    names = {"002432": "九安医疗", "300795": "米奥会展"}
    for c in targets:
        analyze(c, names.get(c, c))
