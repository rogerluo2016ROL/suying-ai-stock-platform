#!/usr/bin/env python3
"""可转债选股模型回测 — 历史评分 + 后续 N 日收益统计.

Usage:
    KRONOS_PG_URL="postgresql://..." python cb_backtest.py --mode cb_floor --days 30 --top-n 10
"""

import argparse, os, sys, time
from collections import defaultdict
from datetime import date, datetime, timedelta

# Ensure kronos-factors is importable
_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_PROJ, "packages", "kronos-factors"))

import psycopg2

PG_URL = os.environ.get("KRONOS_PG_URL", "postgresql://kronos:kronos@localhost:6432/kronos")


def get_trade_dates(conn, days_back: int) -> list[str]:
    """Get last N trading dates from cb_daily."""
    cur = conn.cursor()
    cur.execute(
        "SELECT DISTINCT trade_date FROM cb_daily "
        "WHERE trade_date >= %s ORDER BY trade_date DESC LIMIT %s",
        (date.today() - timedelta(days=days_back * 2), days_back),
    )
    return [str(r[0]) for r in cur.fetchall()]


def get_future_prices(conn, ts_code: str, base_date: str, days: int) -> dict:
    """Get cb_daily close prices for N days after base_date."""
    cur = conn.cursor()
    cur.execute(
        "SELECT trade_date, close FROM cb_daily "
        "WHERE ts_code = %s AND trade_date > %s "
        "ORDER BY trade_date LIMIT %s",
        (ts_code, base_date, days + 1),
    )
    rows = cur.fetchall()
    if not rows:
        return {}
    return {str(r[0]): float(r[1]) for r in rows if r[1]}


def run_backtest(mode: str, days_back: int = 30, top_n: int = 10):
    """Run historical backtest for a CB screening mode."""
    conn = psycopg2.connect(PG_URL)
    trade_dates = get_trade_dates(conn, days_back)

    print(f"回测模式: {mode}")
    print(f"回测天数: {len(trade_dates)} 个交易日")
    print(f"每期选债: Top {top_n}")
    print(f"{'='*80}")

    all_picks = []  # [(trade_date, code, name, score, grade)]
    returns_1d, returns_3d, returns_5d, returns_10d = [], [], [], []

    for td in trade_dates:
        if mode == "cb_floor":
            from kronos_factors.engine.cb_floor import CbFloorEngine
            engine = CbFloorEngine(pg_url=PG_URL)
        else:
            from kronos_factors.engine.cb_intraday import CbIntradayEngine
            engine = CbIntradayEngine(pg_url=PG_URL)

        picks = engine.run(trade_date=td, top_n=top_n)
        engine.close()

        if not picks:
            continue

        for p in picks:
            code = p["code"]
            name = p.get("name", code)
            score = p.get("total_score", 0)
            grade = p.get("grade", "C")
            entry_price = p.get("price")

            future_prices = get_future_prices(conn, code, td, 10)
            future_dates = sorted(future_prices.keys())

            # Calculate returns
            r1, r3, r5, r10 = None, None, None, None
            if entry_price and entry_price > 0:
                if len(future_dates) >= 1:
                    r1 = (future_prices[future_dates[0]] / entry_price - 1) * 100
                if len(future_dates) >= 3:
                    r3 = (future_prices[future_dates[2]] / entry_price - 1) * 100
                if len(future_dates) >= 5:
                    r5 = (future_prices[future_dates[4]] / entry_price - 1) * 100
                if len(future_dates) >= 10:
                    r10 = (future_prices[future_dates[min(9, len(future_dates)-1)]] / entry_price - 1) * 100

            all_picks.append({
                "date": td, "code": code, "name": name,
                "score": score, "grade": grade, "entry_price": entry_price,
                "r1": r1, "r3": r3, "r5": r5, "r10": r10,
            })

            if r1 is not None:
                returns_1d.append(r1)
            if r3 is not None:
                returns_3d.append(r3)
            if r5 is not None:
                returns_5d.append(r5)
            if r10 is not None:
                returns_10d.append(r10)

    conn.close()

    # ── Results ──
    print(f"\n{'='*80}")
    print(f"回测结果汇总")
    print(f"{'='*80}")
    print(f"总选债次数: {len(all_picks)}")
    print(f"有效交易日: {len([d for d in trade_dates if any(p['date']==d for p in all_picks)])}")

    def stats(name, values):
        if not values:
            return f"{name}: 无数据"
        avg = sum(values) / len(values)
        win_rate = sum(1 for v in values if v > 0) / len(values) * 100
        pos = [v for v in values if v > 0]
        neg = [v for v in values if v <= 0]
        return (f"{name}: 均值={avg:+.2f}%  胜率={win_rate:.1f}%  "
                f"最大={max(values):+.2f}%  最小={min(values):+.2f}%  "
                f"样本={len(values)}")

    print(stats("1日收益", returns_1d))
    print(stats("3日收益", returns_3d))
    print(stats("5日收益", returns_5d))
    print(stats("10日收益", returns_10d))

    # ── Grade breakdown ──
    print(f"\n{'─'*60}")
    print("按等级分布:")
    grade_stats = defaultdict(lambda: {"count": 0, "r1": [], "r3": [], "r5": []})
    for p in all_picks:
        g = grade_stats[p["grade"]]
        g["count"] += 1
        if p["r1"] is not None: g["r1"].append(p["r1"])
        if p["r3"] is not None: g["r3"].append(p["r3"])
        if p["r5"] is not None: g["r5"].append(p["r5"])

    for g in ["S", "A", "B", "C"]:
        if g not in grade_stats:
            continue
        gs = grade_stats[g]
        r1_avg = sum(gs["r1"]) / len(gs["r1"]) if gs["r1"] else 0
        print(f"  {g}级: {gs['count']}只  1日均值={r1_avg:+.2f}%  "
              f"3日均值={(sum(gs['r3'])/len(gs['r3']) if gs['r3'] else 0):+.2f}%")

    # ── Top picks detail ──
    print(f"\n{'─'*60}")
    print("最近一期选债明细:")
    last_date = max(p["date"] for p in all_picks) if all_picks else ""
    last_picks = [p for p in all_picks if p["date"] == last_date]
    for i, p in enumerate(last_picks[:top_n], 1):
        r1_str = f"{p['r1']:+.2f}%" if p['r1'] is not None else "N/A"
        r3_str = f"{p['r3']:+.2f}%" if p['r3'] is not None else "N/A"
        print(f"  {i}. {p['name']}({p['code']})  "
              f"入场:{p['entry_price']}  得分:{p['score']}  {p['grade']}  "
              f"1日:{r1_str}  3日:{r3_str}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CB screening backtest")
    parser.add_argument("--mode", choices=["cb_floor", "cb_intraday"], default="cb_floor")
    parser.add_argument("--days", type=int, default=20, help="回测天数")
    parser.add_argument("--top-n", type=int, default=10)
    args = parser.parse_args()

    run_backtest(args.mode, args.days, args.top_n)
