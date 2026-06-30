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


def parse_forward_days(raw: str | int | list[int] | tuple[int, ...]) -> list[int]:
    """Parse CLI forward day list, e.g. '5,10,20'."""
    if isinstance(raw, (list, tuple)):
        return [int(x) for x in raw if int(x) > 0]
    if isinstance(raw, int):
        return [raw] if raw > 0 else []
    days = []
    for part in str(raw).split(","):
        part = part.strip()
        if not part:
            continue
        value = int(part)
        if value <= 0:
            raise ValueError("--forward-days must contain positive integers")
        days.append(value)
    return sorted(set(days))


def horizon_label(days: int) -> str:
    return {5: "1周", 10: "2周", 20: "4周"}.get(days, f"{days}日")


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


def run_backtest(mode: str, days_back: int = 30, top_n: int = 10, forward_days=None):
    """Run historical backtest for a CB screening mode."""
    horizons = parse_forward_days(forward_days or [5, 10, 20])
    conn = psycopg2.connect(PG_URL)
    trade_dates = get_trade_dates(conn, days_back)

    print(f"回测模式: {mode}")
    print(f"回测天数: {len(trade_dates)} 个交易日")
    print(f"每期选债: Top {top_n}")
    print(f"收益周期: {', '.join(horizon_label(h) for h in horizons)}")
    print(f"{'='*80}")

    all_picks = []  # [(trade_date, code, name, score, grade)]
    returns_by_horizon = {h: [] for h in horizons}

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
            route = p.get("route", p.get("combined_route", "未分组"))
            entry_price = p.get("price")

            future_prices = get_future_prices(conn, code, td, max(horizons))
            future_dates = sorted(future_prices.keys())

            returns = {}
            if entry_price and entry_price > 0:
                for h in horizons:
                    if len(future_dates) >= h:
                        returns[h] = (future_prices[future_dates[h - 1]] / entry_price - 1) * 100
                    else:
                        returns[h] = None

            all_picks.append({
                "date": td, "code": code, "name": name,
                "score": score, "grade": grade, "route": route,
                "entry_price": entry_price,
                "returns": returns,
            })

            for h, value in returns.items():
                if value is not None:
                    returns_by_horizon[h].append(value)

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

    for h in horizons:
        print(stats(f"{horizon_label(h)}收益", returns_by_horizon[h]))

    # ── Grade breakdown ──
    print(f"\n{'─'*60}")
    print("按等级分布:")
    grade_stats = defaultdict(lambda: {"count": 0, **{f"r{h}": [] for h in horizons}})
    for p in all_picks:
        g = grade_stats[p["grade"]]
        g["count"] += 1
        for h in horizons:
            value = p["returns"].get(h)
            if value is not None:
                g[f"r{h}"].append(value)

    for g in ["S", "A", "B", "C"]:
        if g not in grade_stats:
            continue
        gs = grade_stats[g]
        parts = []
        for h in horizons:
            values = gs[f"r{h}"]
            avg = sum(values) / len(values) if values else 0
            parts.append(f"{horizon_label(h)}均值={avg:+.2f}%")
        print(f"  {g}级: {gs['count']}只  " + "  ".join(parts))

    # ── Route breakdown ──
    print(f"\n{'─'*60}")
    print("按路线分布:")
    route_stats = defaultdict(lambda: {"count": 0, **{f"r{h}": [] for h in horizons}})
    for p in all_picks:
        rs = route_stats[p["route"]]
        rs["count"] += 1
        for h in horizons:
            value = p["returns"].get(h)
            if value is not None:
                rs[f"r{h}"].append(value)

    for route in ("A低溢价题材", "B下修事件", "A+B共振", "底价观察", "未分组"):
        if route not in route_stats:
            continue
        rs = route_stats[route]
        parts = []
        for h in horizons:
            values = rs[f"r{h}"]
            if values:
                avg = sum(values) / len(values)
                hit = sum(1 for v in values if v > 0) / len(values) * 100
                parts.append(f"{horizon_label(h)}={avg:+.2f}%/胜率{hit:.1f}%")
            else:
                parts.append(f"{horizon_label(h)}=无数据")
        print(f"  {route}: {rs['count']}只  " + "  ".join(parts))

    # ── Top picks detail ──
    print(f"\n{'─'*60}")
    print("最近一期选债明细:")
    last_date = max(p["date"] for p in all_picks) if all_picks else ""
    last_picks = [p for p in all_picks if p["date"] == last_date]
    for i, p in enumerate(last_picks[:top_n], 1):
        ret_parts = []
        for h in horizons:
            value = p["returns"].get(h)
            ret_parts.append(f"{horizon_label(h)}:{value:+.2f}%" if value is not None else f"{horizon_label(h)}:N/A")
        print(f"  {i}. {p['name']}({p['code']})  "
              f"入场:{p['entry_price']}  得分:{p['score']}  {p['grade']}  "
              f"路线:{p['route']}  {'  '.join(ret_parts)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CB screening backtest")
    parser.add_argument("--mode", choices=["cb_floor", "cb_intraday"], default="cb_floor")
    parser.add_argument("--days", type=int, default=20, help="回测天数")
    parser.add_argument("--top-n", type=int, default=10)
    parser.add_argument("--forward-days", default="5,10,20", help="收益观察周期, 例如 5,10,20")
    args = parser.parse_args()

    run_backtest(args.mode, args.days, args.top_n, args.forward_days)
