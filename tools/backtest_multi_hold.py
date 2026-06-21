#!/usr/bin/env python3
"""毕师傅硬核科技 — T+1/T+3/T+5/T+10 多持仓周期回测对比"""
import json, os, sys, numpy as np
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
    if adapter is None:
        raise RuntimeError(f"无法连接数据库: {pg_url}")
    set_db_adapter(adapter)
    set_market_data_adapter(adapter)
    return adapter

def get_n_day_return(db, code, trade_date, hold_days=1, stop_loss_pct=None):
    """T日收盘买入, 持有N天后收盘卖出 (含止损).

    止损逻辑: 持仓期间任一天触及止损价即退出。
    """
    entry_row = db.execute(
        "SELECT close FROM daily_kline WHERE code=? AND trade_date=?",
        (code, trade_date)
    ).fetchone()
    if not entry_row or not entry_row["close"]:
        return None, None, None
    entry_price = float(entry_row["close"])

    # Get next N trading day bars
    bars = db.execute(
        "SELECT trade_date, open, high, low, close FROM daily_kline "
        "WHERE code=? AND trade_date > ? ORDER BY trade_date ASC LIMIT ?",
        (code, trade_date, hold_days)
    ).fetchall()

    if not bars or len(bars) < 1:
        return None, None, None

    exit_price = float(bars[-1]["close"])
    exit_date = bars[-1]["trade_date"]
    stopped = False
    actual_hold = len(bars)

    if stop_loss_pct is not None and stop_loss_pct < 0:
        stop_price = entry_price * (1 + stop_loss_pct / 100)
        for bar in bars:
            next_open = float(bar["open"] or bar["close"])
            next_low = float(bar["low"] or bar["close"])
            # Gap down → exit at open
            if next_open <= stop_price:
                exit_price = next_open
                exit_date = bar["trade_date"]
                stopped = True
                actual_hold = bars.index(bar) + 1
                break
            # Intraday stop hit → exit at stop price
            elif next_low <= stop_price:
                exit_price = stop_price
                exit_date = bar["trade_date"]
                stopped = True
                actual_hold = bars.index(bar) + 1
                break

    ret = (exit_price / entry_price - 1) * 100
    return ret, stopped, actual_hold


adapter = setup_db()
from kronos_factors.scorer._db_stub import _get_db

# Load V13 June picks
with open('outputs/backtest_bi_trend_2026-06_v13.json') as f:
    data = json.load(f)

# All picks (including pending)
all_picks = data['picks']

hold_periods = [1, 3, 5, 10]
results = {}

for hold in hold_periods:
    with _get_db() as db:
        valid = []
        for p in all_picks:
            sl = p.get("stop_loss")  # from V13 hold advice
            ret, stopped, actual = get_n_day_return(db, p["code"], p["trade_date"], hold_days=hold, stop_loss_pct=sl)
            if ret is not None:
                valid.append({
                    **p,
                    "next_day_return": ret,
                    "stopped": stopped,
                    "actual_hold": actual,
                })

    daily = defaultdict(list)
    for p in valid:
        w = p.get("weight", 1.0)
        daily[p["trade_date"]].append((p["next_day_return"], w))

    rets = np.array([p["next_day_return"] for p in valid])
    win = (rets > 0).sum(); total = len(rets)
    stopped_n = sum(1 for p in valid if p.get("stopped"))

    # Compound
    cap = 1_000_000
    for td in sorted(daily.keys()):
        r = [x[0] for x in daily[td]]; w = [x[1] for x in daily[td]]
        cap *= (1 + np.average(r, weights=w) / 100)

    # Grade split
    s_rets = np.array([p["next_day_return"] for p in valid if p["grade"] == "S"])
    a_rets = np.array([p["next_day_return"] for p in valid if p["grade"] == "A"])

    results[hold] = {
        "total": total, "win": win, "mean": rets.mean(),
        "median": np.median(rets), "std": rets.std(),
        "max": rets.max(), "min": rets.min(),
        "stopped": stopped_n, "cap": cap,
        "s_win": (s_rets > 0).sum()/len(s_rets)*100 if len(s_rets) > 0 else 0,
        "a_win": (a_rets > 0).sum()/len(a_rets)*100 if len(a_rets) > 0 else 0,
        "s_mean": s_rets.mean() if len(s_rets) > 0 else 0,
        "a_mean": a_rets.mean() if len(a_rets) > 0 else 0,
    }

# ── Print comparison ──
print()
print("=" * 110)
print("  毕师傅硬核科技 — T+1 / T+3 / T+5 / T+10 持仓周期对比 (2026年6月)")
print("=" * 110)
print(f"{'指标':<20} {'T+1':<22} {'T+3':<22} {'T+5':<22} {'T+10':<22}")
print("-" * 110)

rows = [
    ("有效笔数", "total", "d"),
    ("胜率", "win", "pct"),
    ("均值收益", "mean", "pct2"),
    ("中位数收益", "median", "pct2"),
    ("标准差", "std", "pct2"),
    ("最大盈利", "max", "pct2"),
    ("最大亏损", "min", "pct2"),
    ("止损触发", "stopped", "d"),
    ("100万复利终值", "cap", "money"),
]

for label, key, fmt in rows:
    line = f"  {label:<18}"
    for hold in hold_periods:
        val = results[hold][key]
        if fmt == "d":
            line += f" {int(val):<21}"
        elif fmt == "pct":
            line += f" {val/val*100:.1f}%".ljust(22) if key == "win" else ""  # placeholder
            if key == "win":
                t = results[hold]["total"]
                line += f" {val}/{t}={val/t*100:.1f}%".ljust(21)
        elif fmt == "pct2":
            line += f" {val:>+7.2f}%".ljust(21)
        elif fmt == "money":
            line += f" ¥{val:,.0f}".ljust(21)
    print(line)

# Win rate row (special)
line = f"  {'胜率':<18}"
for hold in hold_periods:
    r = results[hold]
    line += f" {r['win']}/{r['total']}={r['win']/r['total']*100:.1f}%".ljust(21)
print(line)

# Grade breakdown
print()
print(f"  📊 评级维度:")
print(f"  {'评级':<6} {'T+1胜率':<10} {'T+1均值':<10} {'T+3胜率':<10} {'T+3均值':<10} {'T+5胜率':<10} {'T+5均值':<10} {'T+10胜率':<10} {'T+10均值':<10}")
print(f"  {'-'*86}")
for grade in ["S", "A"]:
    line = f"  {grade:<6}"
    for hold in hold_periods:
        r = results[hold]
        if grade == "S":
            line += f" {r['s_win']:.1f}%".ljust(9) + f" {r['s_mean']:>+6.2f}%".ljust(10)
        else:
            line += f" {r['a_win']:.1f}%".ljust(9) + f" {r['a_mean']:>+6.2f}%".ljust(10)
    print(line)

# Best hold period
best = max(results.items(), key=lambda x: x[1]["cap"])
print()
print(f"  🏆 最优持仓周期: T+{best[0]} (¥{best[1]['cap']:,.0f}, +{(best[1]['cap']-1000000)/10000:.1f}%)")
print()
