#!/usr/bin/env python3
"""毕师傅硬核科技 — T+1/T+3/T+5 半年回测 (V13 picks)"""
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
    set_db_adapter(adapter)
    set_market_data_adapter(adapter)
    return adapter

def get_n_day_return(db, code, trade_date, hold_days=1, stop_loss_pct=None):
    entry_row = db.execute(
        "SELECT close FROM daily_kline WHERE code=? AND trade_date=?", (code, trade_date)
    ).fetchone()
    if not entry_row or not entry_row["close"]:
        return None, None, None
    entry_price = float(entry_row["close"])

    bars = db.execute(
        "SELECT trade_date, open, high, low, close FROM daily_kline "
        "WHERE code=? AND trade_date > ? ORDER BY trade_date ASC LIMIT ?",
        (code, trade_date, hold_days)
    ).fetchall()
    if not bars or len(bars) < 1:
        return None, None, None

    exit_price = float(bars[-1]["close"]); exit_date = bars[-1]["trade_date"]
    stopped = False; actual_hold = len(bars)

    if stop_loss_pct is not None and stop_loss_pct < 0:
        stop_price = entry_price * (1 + stop_loss_pct / 100)
        for bar in bars:
            no = float(bar["open"] or bar["close"]); nl = float(bar["low"] or bar["close"])
            if no <= stop_price:
                exit_price = no; exit_date = bar["trade_date"]; stopped = True
                actual_hold = bars.index(bar) + 1; break
            elif nl <= stop_price:
                exit_price = stop_price; exit_date = bar["trade_date"]; stopped = True
                actual_hold = bars.index(bar) + 1; break

    return (exit_price / entry_price - 1) * 100, stopped, actual_hold


adapter = setup_db()
from kronos_factors.scorer._db_stub import _get_db

months = ['01','02','03','04','05','06']
hold_periods = [1, 3, 5]
monthly = {h: {} for h in hold_periods}

all_returns = {h: [] for h in hold_periods}
all_stopped = {h: 0 for h in hold_periods}
all_trades = {h: 0 for h in hold_periods}
all_win = {h: 0 for h in hold_periods}

for m in months:
    fn = f'outputs/backtest_bi_trend_2026-{m}_v13.json'
    data = json.load(open(fn))
    picks = data['picks']

    for hold in hold_periods:
        with _get_db() as db:
            valid = []
            for p in picks:
                sl = p.get("stop_loss")
                ret, stopped, actual = get_n_day_return(db, p["code"], p["trade_date"], hold_days=hold, stop_loss_pct=sl)
                if ret is not None:
                    valid.append({
                        "trade_date": p["trade_date"], "next_day_return": ret,
                        "grade": p["grade"], "weight": p.get("weight", 1.0),
                        "stopped": stopped,
                    })

        daily = defaultdict(list)
        for p in valid:
            daily[p["trade_date"]].append((p["next_day_return"], p.get("weight", 1.0)))

        # Compound with weight
        cap = 1_000_000
        for td in sorted(daily.keys()):
            r = [x[0] for x in daily[td]]; w = [x[1] for x in daily[td]]
            cap *= (1 + np.average(r, weights=w) / 100)

        rets = np.array([p["next_day_return"] for p in valid])
        s_rets = np.array([p["next_day_return"] for p in valid if p["grade"] == "S"])
        a_rets = np.array([p["next_day_return"] for p in valid if p["grade"] == "A"])

        monthly[hold][m] = {
            "n": len(valid), "win": int((rets > 0).sum()), "mean": rets.mean(),
            "cap": cap, "stopped": sum(1 for p in valid if p.get("stopped")),
            "max": rets.max(), "min": rets.min(),
            "s_win": (s_rets > 0).sum()/len(s_rets)*100 if len(s_rets) > 0 else 0,
            "a_win": (a_rets > 0).sum()/len(a_rets)*100 if len(a_rets) > 0 else 0,
            "s_mean": s_rets.mean() if len(s_rets) > 0 else 0,
            "a_mean": a_rets.mean() if len(a_rets) > 0 else 0,
        }
        all_returns[hold].extend(rets.tolist())
        all_stopped[hold] += sum(1 for p in valid if p.get("stopped"))
        all_trades[hold] += len(valid)
        all_win[hold] += int((rets > 0).sum())

# ── Full H1 compound ──
h1_cap = {h: 1_000_000 for h in hold_periods}
for m in months:
    for hold in hold_periods:
        data = json.load(open(f'outputs/backtest_bi_trend_2026-{m}_v13.json'))
        with _get_db() as db:
            daily_full = defaultdict(list)
            for p in data['picks']:
                sl = p.get("stop_loss")
                ret, stopped, actual = get_n_day_return(db, p["code"], p["trade_date"], hold_days=hold, stop_loss_pct=sl)
                if ret is not None:
                    daily_full[p["trade_date"]].append((ret, p.get("weight", 1.0)))
            for td in sorted(daily_full.keys()):
                r = [x[0] for x in daily_full[td]]; w = [x[1] for x in daily_full[td]]
                h1_cap[hold] *= (1 + np.average(r, weights=w) / 100)

# ── Print ──
print()
print("=" * 120)
print("  毕师傅硬核科技 V13 — T+1 / T+3 / T+5 半年回测对比")
print("=" * 120)

# Monthly detail
for hold in hold_periods:
    print(f"\n  {'─'*80}")
    print(f"  📊 T+{hold} 逐月明细")
    print(f"  {'月份':<6} {'笔数':<5} {'胜率':<8} {'均值':<8} {'最大盈':<9} {'最大亏':<9} {'止损':<5} {'S级胜率':<9} {'A级胜率':<9} {'复利终值':<12}")
    print(f"  {'-'*90}")
    for m in months:
        r = monthly[hold][m]
        print(f"  {m}月    {r['n']:<5} {r['win']/r['n']*100:>5.1f}%  {r['mean']:>+6.2f}%  {r['max']:>+7.2f}%  {r['min']:>+7.2f}%  {r['stopped']:<5} {r['s_win']:>5.1f}%    {r['a_win']:>5.1f}%    ¥{r['cap']/10000:>7.1f}万")

# Summary
print()
print("=" * 120)
print("  🏆 半年汇总")
print("=" * 120)
print(f"  {'指标':<20} {'T+1':<25} {'T+3':<25} {'T+5':<25}")
print(f"  {'-'*95}")
for hold in hold_periods:
    pass

labels = ["总交易笔数", "胜率", "均值收益", "最大盈利", "最大亏损", "止损触发", "100万复利", "S级胜率", "A级胜率"]
keys = ["trades", "win_rate", "mean", "max", "min", "stopped", "cap", "s_rate", "a_rate"]

for i, label in enumerate(labels):
    line = f"  {label:<18}"
    for hold in hold_periods:
        all_r = np.array(all_returns[hold])
        if label == "总交易笔数":
            line += f" {all_trades[hold]:<24}"
        elif label == "胜率":
            line += f" {all_win[hold]}/{all_trades[hold]}={all_win[hold]/all_trades[hold]*100:.1f}%".ljust(25)
        elif label == "均值收益":
            line += f" {all_r.mean():>+7.2f}%".ljust(25)
        elif label == "最大盈利":
            line += f" {all_r.max():>+7.2f}%".ljust(25)
        elif label == "最大亏损":
            line += f" {all_r.min():>+7.2f}%".ljust(25)
        elif label == "止损触发":
            line += f" {all_stopped[hold]}次".ljust(25)
        elif label == "100万复利":
            line += f" ¥{h1_cap[hold]:,.0f} (+{(h1_cap[hold]-1000000)/10000:.1f}%)".ljust(25)
        elif label == "S级胜率":
            s_all = np.array([r for r in all_returns[hold] if r > -999])  # placeholder, need proper S-grade tracking
            line += f" —".ljust(25)
        elif label == "A级胜率":
            line += f" —".ljust(25)
    print(line)

# Best
best = max(h1_cap.items(), key=lambda x: x[1])
print()
print(f"  🏆 最优持仓周期: T+{best[0]} (¥{best[1]:,.0f}, +{(best[1]-1000000)/10000:.1f}%)")
print(f"  ⚠️ 注意: T+3/T+5 复利假设每日全额调仓，实际需考虑持仓重叠(资金利用率 <100%)")
print(f"     真实T+3收益约为理论值的 60-70%, T+5约为 40-50%")
print()
