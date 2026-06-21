#!/usr/bin/env python3
"""毕师傅硬核科技 — V13 P2 智能卖出回测

卖出决策树 (优先级):
  1. 大盘熔断: 持仓期任一天涨跌比<20% → 清仓
  2. OBV趋势终结: OBV连续3日<MA10 + WR>70 → 卖出
  3. 时间止盈: 达最大持有天数 → 卖出
  4. 移动止盈: 从持仓最高点回撤>12% → 卖出
  5. [实盘] 分时VWAP: 连续3次破当日均线 → 卖出

Usage:
    KRONOS_PG_URL=postgresql://kronos:kronos@localhost:6432/kronos \
    python tools/backtest_smart_sell.py --month 2026-06
"""
import argparse, json, os, sys, time, numpy as np
from collections import defaultdict

_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for pkg in ["packages/kronos-factors", "packages/kronos-core", "packages/kronos-data"]:
    path = os.path.join(_PROJ, pkg)
    if os.path.isdir(path) and path not in sys.path:
        sys.path.insert(0, path)

def setup_db():
    pg_url = os.environ.get("KRONOS_PG_URL", "postgresql://kronos:kronos@localhost:6432/kronos")
    from kronos_factors.pg_adapter import create_pg_adapter
    from kronos_factors.scorer._db_stub import set_db_adapter, set_market_data_adapter
    adapter = create_pg_adapter(pg_url)
    set_db_adapter(adapter); set_market_data_adapter(adapter)
    return adapter


def get_market_breadth(db, trade_date):
    """获取当日涨跌比"""
    prev = db.execute("SELECT MAX(trade_date) as pd FROM daily_kline WHERE trade_date<?", (trade_date,)).fetchone()
    if not prev or not prev["pd"]: return 50
    pd = prev["pd"]
    br = db.execute(
        "SELECT SUM(CASE WHEN a.close>b.close THEN 1 ELSE 0 END) as up, "
        "SUM(CASE WHEN a.close<b.close THEN 1 ELSE 0 END) as down "
        "FROM daily_kline a JOIN daily_kline b ON a.code=b.code AND b.trade_date=? "
        "WHERE a.trade_date=?", (pd, trade_date)
    ).fetchone()
    if not br: return 50
    u, d = br["up"] or 0, br["down"] or 0
    return u / max(1, u + d) * 100


def calc_obv(closes, volumes):
    """计算OBV序列"""
    obv = np.zeros(len(closes))
    for i in range(1, len(closes)):
        if closes[i] > closes[i-1]:      obv[i] = obv[i-1] + volumes[i]
        elif closes[i] < closes[i-1]:    obv[i] = obv[i-1] - volumes[i]
        else:                             obv[i] = obv[i-1]
    return obv


def calc_wr(highs, lows, closes, period=14):
    """计算Williams %R (0-100, >60=超卖压缩)"""
    n = len(closes)
    wr = np.full(n, np.nan)
    for i in range(period-1, n):
        hh = np.max(highs[i-period+1:i+1]); ll = np.min(lows[i-period+1:i+1])
        if hh > ll: wr[i] = (closes[i] - ll) / (hh - ll) * 100
    return wr


def smart_sell_exit(db, code, entry_date, entry_price, max_hold, stop_loss_pct, hist_closes, hist_highs, hist_lows, hist_volumes):
    """智能卖出: 逐日检查, 返回 (exit_price, exit_date, exit_reason, hold_days)

    hist_*: 历史K线数据(含entry_date及之前的数据), 用于计算OBV/WR
    """
    # Fetch holding period bars
    bars = db.execute(
        "SELECT trade_date, open, high, low, close FROM daily_kline "
        "WHERE code=? AND trade_date > ? ORDER BY trade_date ASC LIMIT ?",
        (code, entry_date, max_hold)
    ).fetchall()
    if not bars: return None, None, None, 0

    highest_close = entry_price
    exit_price = None; exit_date = None; exit_reason = "time"; actual_hold = len(bars)

    for day_i, bar in enumerate(bars):
        td = bar["trade_date"]
        op = float(bar["open"] or bar["close"])
        hi = float(bar["high"] or bar["close"])
        lo = float(bar["low"] or bar["close"])
        cl = float(bar["close"])

        # ── 硬止损 (跳空/盘中) ──
        if stop_loss_pct is not None and stop_loss_pct < 0:
            stop_price = entry_price * (1 + stop_loss_pct/100)
            if op <= stop_price:
                exit_price = op; exit_date = td; exit_reason = "stop_gap"
                actual_hold = day_i + 1; break
            elif lo <= stop_price:
                exit_price = stop_price; exit_date = td; exit_reason = "stop_intra"
                actual_hold = day_i + 1; break

        # ── 1. 大盘熔断卖出 (护利模式) ──
        # 崩盘时保护已有利润，不割肉 (割肉交给止损)
        breadth = get_market_breadth(db, td)
        if breadth < 18 and cl > entry_price:
            exit_price = cl; exit_date = td; exit_reason = "crash_profit_lock"
            actual_hold = day_i + 1; break

        # ── 2. OBV趋势终结: 连续3日<MA10 + WR>70 ──
        # Extend history with today's bar to compute latest OBV
        ext_closes = np.append(hist_closes, cl)
        ext_vols = np.append(hist_volumes, float(bar.get("volume", 0) or 0))
        obv = calc_obv(ext_closes, ext_vols)
        if len(obv) >= 14:
            obv_ma10 = np.convolve(obv, np.ones(10)/10, mode='valid')
            # Check if OBV below MA10 for last 3 days
            obv_below = 0
            for check_i in range(min(3, len(obv_ma10))):
                oi = len(obv) - 1 - check_i
                mi = oi - 10 + 1
                if mi >= 0 and obv[oi] < obv_ma10[mi]:
                    obv_below += 1
            # Current WR
            ext_highs = np.append(hist_highs, hi)
            ext_lows = np.append(hist_lows, lo)
            wr_arr = calc_wr(ext_highs, ext_lows, ext_closes, 14)
            wr_now = wr_arr[-1] if not np.isnan(wr_arr[-1]) else 50

            if obv_below >= 3 and wr_now > 70:
                exit_price = cl; exit_date = td; exit_reason = "obv_reversal"
                actual_hold = day_i + 1; break

        # ── 3. 时间止盈: 最后一天强制卖出 (处理在循环后) ──
        # (implicit: if we reach here on last day, time exit)

        # ── 4. 移动止盈 ──
        if cl > highest_close:
            highest_close = cl
        if highest_close > entry_price:
            drawdown = (cl - highest_close) / highest_close * 100
            if drawdown < -12:
                exit_price = cl; exit_date = td; exit_reason = "trailing_stop"
                actual_hold = day_i + 1; break

    # No early exit → exit at the last bar
    if exit_price is None:
        exit_price = float(bars[-1]["close"])
        exit_date = bars[-1]["trade_date"]
        actual_hold = len(bars)
        exit_reason = "time"

    return exit_price, exit_date, exit_reason, actual_hold


def get_trading_days(db, month_prefix):
    y, m = month_prefix.split("-"); nm = int(m)+1; ny = int(y)
    if nm > 12: nm = 1; ny += 1
    rows = db.execute(
        "SELECT DISTINCT trade_date FROM daily_kline "
        "WHERE trade_date>=? AND trade_date<? ORDER BY trade_date",
        (f"{y}-{m}-01", f"{ny}-{nm:02d}-01")
    ).fetchall()
    return [r["trade_date"] for r in rows]


def main():
    parser = argparse.ArgumentParser(description="毕师傅智能卖出回测")
    parser.add_argument("--month", default="2026-06")
    parser.add_argument("--top-n", type=int, default=20)
    parser.add_argument("--max-hold", type=int, default=5, help="最大持有天数")
    args = parser.parse_args()

    adapter = setup_db()
    from kronos_factors.scorer._db_stub import _get_db
    from kronos_factors.engine.bi_trend_launch import run_bi_screening

    with _get_db() as db:
        trading_days = get_trading_days(db, args.month)
        print(f"📅 {args.month} 交易日: {len(trading_days)} 天")

    results = []
    for i, td in enumerate(trading_days):
        t0 = time.time()
        print(f"[{i+1}/{len(trading_days)}] {td} ...", end=" ", flush=True)
        try:
            with _get_db() as db:
                r = run_bi_screening(db, td, top_n=args.top_n)
            elapsed = time.time() - t0
            top_n = len(r[0])
            grades = f"S={sum(1 for s in r[0] if s['grade']=='S')} A={sum(1 for s in r[0] if s['grade']=='A')}"
            print(f"✅ {top_n}只 {grades} {elapsed:.1f}s")
            results.append({"trade_date": td, "top_picks": r[0], "market_info": r[2]})
        except Exception as e:
            print(f"❌ {time.time()-t0:.1f}s - {e}")

    # ── Smart Sell Analysis ──
    with _get_db() as db:
        all_trades = []
        for r in results:
            td = r["trade_date"]
            for s in r["top_picks"]:
                code = s["code"]; grade = s["grade"]
                # V13 P2: 动态持仓周期 — 熊市缩短，牛市延长
                regime = r.get("market_info", {}).get("regime", "neutral")
                if regime in ("weak", "recovery", "bear"):
                    actual_max_hold = 3  # 熊市T+3快速进出
                elif regime == "bull":
                    actual_max_hold = 7  # 牛市让利润奔跑
                else:
                    actual_max_hold = s.get("hold_days", 5)
                sl = s.get("stop_loss")

                # Get entry price
                entry = db.execute("SELECT close FROM daily_kline WHERE code=? AND trade_date=?", (code, td)).fetchone()
                if not entry or not entry["close"]: continue
                entry_price = float(entry["close"])

                # Get history for OBV/WR calc (60 days before entry)
                hist = db.execute(
                    "SELECT close,high,low,volume FROM daily_kline WHERE code=? AND trade_date<=? ORDER BY trade_date ASC",
                    (code, td)
                ).fetchall()
                if len(hist) < 40: continue
                hist_closes = np.array([float(r["close"]) for r in hist])
                hist_highs = np.array([float(r["high"]) for r in hist])
                hist_lows = np.array([float(r["low"]) for r in hist])
                hist_volumes = np.array([float(r["volume"]) for r in hist])

                exit_price, exit_date, reason, actual_hold = smart_sell_exit(
                    db, code, td, entry_price, actual_max_hold, sl,
                    hist_closes, hist_highs, hist_lows, hist_volumes
                )
                if exit_price is None: continue

                ret = (exit_price / entry_price - 1) * 100
                all_trades.append({
                    "trade_date": td, "code": code, "name": s["name"],
                    "grade": grade, "signal": s["signal"],
                    "max_hold": actual_max_hold, "actual_hold": actual_hold,
                    "exit_reason": reason, "next_day_return": ret,
                    "entry_price": entry_price, "exit_price": exit_price,
                    "exit_date": exit_date, "weight": s.get("weight", 1.0),
                })

    rets = np.array([t["next_day_return"] for t in all_trades])
    win = (rets > 0).sum(); total = len(rets)

    # Reasons breakdown
    reason_counts = defaultdict(lambda: {"n": 0, "ret": []})
    for t in all_trades:
        reason_counts[t["exit_reason"]]["n"] += 1
        reason_counts[t["exit_reason"]]["ret"].append(t["next_day_return"])

    # Compound
    daily = defaultdict(list)
    for t in all_trades:
        daily[t["trade_date"]].append((t["next_day_return"], t["weight"]))
    cap = 1_000_000
    for td in sorted(daily.keys()):
        r = [x[0] for x in daily[td]]; w = [x[1] for x in daily[td]]
        cap *= (1 + np.average(r, weights=w)/100)

    print(f"\n{'='*80}")
    print(f"  智能卖出回测 — {args.month} (max_hold=T+{args.max_hold})")
    print(f"{'='*80}")
    print(f"  总交易: {total}笔 | 胜率: {win/total*100:.1f}% | 均值: {rets.mean():+.2f}%")
    print(f"  最大盈: {rets.max():+.2f}% | 最大亏: {rets.min():+.2f}% | 累计: {rets.sum():+.2f}%")
    print(f"  100万复利: ¥{cap:,.0f} (+{(cap-1000000)/10000:.1f}%)")

    print(f"\n  📊 卖出原因分布:")
    for reason, data in sorted(reason_counts.items(), key=lambda x: -x[1]["n"]):
        rr = np.array(data["ret"])
        rw = (rr > 0).sum()
        print(f"    {reason:<16} {data['n']:>3}笔  胜率{rw/len(rr)*100:>5.1f}%  均值{rr.mean():>+6.2f}%")

    print(f"\n  📊 评级维度:")
    for g in ["S", "A"]:
        gr = [t for t in all_trades if t["grade"]==g]
        if gr:
            rr = np.array([t["next_day_return"] for t in gr])
            rw = (rr > 0).sum()
            print(f"    {g}级: {len(gr)}笔  胜率{rw/len(gr)*100:.0f}%  均值{rr.mean():+.2f}%  持有={np.mean([t['actual_hold'] for t in gr]):.1f}天")

    # Export
    export = f"outputs/backtest_smart_sell_{args.month}.json"
    json.dump({"month": args.month, "max_hold": args.max_hold, "trades": all_trades,
               "summary": {"total": total, "win_rate": f"{win/total*100:.1f}%", "mean": f"{rets.mean():+.2f}%",
                           "compound": f"¥{cap:,.0f}"}}, open(export, 'w'), ensure_ascii=False, indent=2, default=str)
    print(f"\n📁 {export}")


if __name__ == "__main__":
    main()
