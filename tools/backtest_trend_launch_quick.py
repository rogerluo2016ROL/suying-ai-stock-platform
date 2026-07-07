#!/usr/bin/env python3
"""TrendLaunch Quick Backtest — 2024-2026, strict walk-forward."""
import os, sys, time, json
from collections import defaultdict
import numpy as np
import psycopg2

_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_PROJ, "packages/kronos-factors"))
from kronos_factors.engine.supply_chain_trend import TrendLaunchEngine

ALL_CHAINS = [
    '半导体', '华为韬定律_先进封装', '光通信', '存储芯片', '华为终端', 'EDA工业软件',
    'AI算力', '机器人', '新能源', '新能源车', '创新药',
    '高端制造', '国防军工', '消费升级', '周期资源',
]

CHAIN_INDUSTRIES = {
    '半导体': ['半导体', '元器件', 'IT设备'],
    '华为韬定律_先进封装': ['半导体', '元器件', '通信设备', 'IT设备'],
    '光通信': ['通信设备', '元器件'],
    '存储芯片': ['半导体', '元器件'],
    '华为终端': ['元器件', '通信设备', '半导体'],
    'EDA工业软件': ['半导体', '软件服务'],
    'AI算力': ['IT设备', '软件服务', '互联网', '通信设备'],
    '机器人': ['机械基件', '专用机械', '电器仪表'],
    '新能源': ['电气设备', '新型电力', '矿物制品'],
    '新能源车': ['汽车配件', '汽车整车', '电气设备'],
    '创新药': ['化学制药', '生物制药', '医疗保健'],
    '高端制造': ['专用机械', '运输设备', '机械基件'],
    '国防军工': ['航空', '船舶', '军工'],
    '消费升级': ['食品饮料', '家用电器', '家居用品'],
    '周期资源': ['化工原料', '钢铁', '煤炭开采', '有色金属', '仓储物流'],
}

pg_url = os.environ.get("KRONOS_PG_URL", "postgresql://kronos:kronos@localhost:6432/kronos")
pg = psycopg2.connect(pg_url, connect_timeout=10)
cur = pg.cursor()

# Get month-end dates
cur.execute("SELECT DISTINCT trade_date FROM daily_kline WHERE trade_date >= '2023-10-01' AND trade_date <= '2026-07-07' ORDER BY trade_date")
all_dates = [str(r[0]) for r in cur.fetchall()]
months = {}
for d in all_dates:
    months[d[:7]] = d
month_dates = sorted(months.values())
print(f"回测月份: {len(month_dates)} ({month_dates[0]} ~ {month_dates[-1]})")

def chain_monthly_return(chain_name, month_date):
    """Equal-weight chain return for a month."""
    inds = CHAIN_INDUSTRIES.get(chain_name, [])
    if not inds:
        return 0.0
    like = " OR ".join(["s.industry LIKE %s"] * len(inds))
    params = [f"%{i}%" for i in inds]
    cur.execute(f"SELECT DISTINCT s.code FROM stocks s WHERE s.is_st=0 AND ({like})", params)
    codes = [r[0] for r in cur.fetchall()]
    if not codes:
        return 0.0

    # Get month open/close
    cur.execute("SELECT MIN(trade_date) FROM daily_kline WHERE trade_date >= %s AND trade_date <= %s",
                (month_date[:7]+"-01", month_date))
    fd = cur.fetchone()[0]
    p = ",".join(["%s"]*len(codes))
    cur.execute(f"SELECT code, close FROM daily_kline WHERE trade_date=%s AND code IN ({p})",
                [str(fd)] + codes)
    opens = {r[0]: float(r[1]) for r in cur.fetchall()}
    cur.execute(f"SELECT code, close FROM daily_kline WHERE trade_date=%s AND code IN ({p})",
                [month_date] + codes)
    closes = {r[0]: float(r[1]) for r in cur.fetchall()}
    rets = [(closes[c]-opens[c])/opens[c] for c in codes if c in opens and c in closes and opens[c]>0]
    return np.mean(rets) if rets else 0.0

def stock_next_return(code, entry_date):
    """Stock return from entry_date to the NEXT calendar month-end.

    NO data leakage: only uses data up to next_month_end.
    """
    cur.execute("SELECT close FROM daily_kline WHERE code=%s AND trade_date <= %s ORDER BY trade_date DESC LIMIT 1",
                (code, entry_date))
    r = cur.fetchone()
    if not r: return 0.0
    entry = float(r[0])

    # Compute next month's last calendar day
    from datetime import datetime, timedelta
    from calendar import monthrange
    dt = datetime.strptime(entry_date[:10], "%Y-%m-%d")
    if dt.month == 12:
        next_m_year, next_m_month = dt.year + 1, 1
    else:
        next_m_year, next_m_month = dt.year, dt.month + 1
    _, last_day = monthrange(next_m_year, next_m_month)
    next_m_end = f"{next_m_year}-{next_m_month:02d}-{last_day:02d}"

    cur.execute("SELECT MAX(trade_date) FROM daily_kline WHERE trade_date > %s AND trade_date <= %s",
                (entry_date, next_m_end))
    nr = cur.fetchone()
    if not nr or not nr[0]:
        # If no data in next month (e.g., current month is latest), return 0
        return 0.0
    next_date = str(nr[0])
    cur.execute("SELECT close FROM daily_kline WHERE code=%s AND trade_date=%s", (code, next_date))
    er = cur.fetchone()
    if not er: return 0.0
    ret = (float(er[0]) - entry) / entry if entry > 0 else 0.0
    return ret

# ── Backtest ──
engine = TrendLaunchEngine(momentum_window=3, min_chains=5, total_slots=15,
                            cross_chain_bonus=1.5, min_score=30)
monthly_returns = []
yearly = defaultdict(list)
all_trades = []

t0 = time.time()
MIN_PRE = 3
for i, md in enumerate(month_dates):
    # Build chain history
    for ch in ALL_CHAINS:
        ret = chain_monthly_return(ch, md)
        engine._chain_history[ch].append(ret)

    if i < MIN_PRE:
        continue

    # Run screening
    try:
        result = engine.run(top_n=15, min_score=30, trade_date=md)
        picks = result.picks if hasattr(result, 'picks') else result.get('picks', [])
    except Exception as e:
        print(f"  ⚠️ {md}: {e}")
        picks = []

    # Compute returns
    pick_rets = []
    for p in picks:
        ret = stock_next_return(p['code'], md)
        pick_rets.append(ret)
        all_trades.append({"date": md, "code": p['code'], "name": p['name'],
                           "score": p.get('total_score',0), "chain": p.get('chain',''), "ret": ret})

    month_ret = np.mean(pick_rets) if pick_rets else 0.0
    monthly_returns.append(month_ret)
    yearly[md[:4]].append(month_ret)

    if i <= MIN_PRE + 5 or i % 12 == 0 or i >= len(month_dates) - 3:
        active = [ch for ch in ALL_CHAINS if sum(1 for r in engine._chain_history[ch][-3:] if r > 0) >= 2]
        print(f"  {md}: {len(picks)}picks | {len(active)}chains | ret={month_ret:+.2%} | {time.time()-t0:.0f}s")

# ── Results ──
valid = [r for r in monthly_returns if r != 0]
n = len(valid)
cum = np.prod([1+r for r in valid])
avg = np.mean(valid)
std = np.std(valid) if len(valid) > 1 else 0.01
sharpe = avg / std * np.sqrt(12)
win_rate = sum(1 for r in valid if r > 0) / n
cum_series = np.cumprod([1+r for r in valid])
peak = np.maximum.accumulate(cum_series)
max_dd = min((cum_series - peak) / peak)

print(f"\n{'='*60}")
print(f"  TrendLaunch Walk-Forward (2024-2026)")
print(f"{'='*60}")
print(f"  月份: {n} | 月均: {avg:+.2%} | 累计: {cum-1:+.1%}")
print(f"  Sharpe: {sharpe:.2f} | 回撤: {max_dd:.1%} | 胜率: {win_rate:.1%}")
print(f"\n  逐年:")
for y in sorted(yearly.keys()):
    yr = yearly[y]
    yc = np.prod([1+r for r in yr]) - 1
    ya = np.mean(yr)
    yw = sum(1 for r in yr if r > 0) / len(yr)
    print(f"  {y}: {len(yr)}m | 月均{ya:+.1%} | 累计{yc:+.1%} | 胜率{yw:.0%}")

pg.close()
print(f"\n⏱️ 总耗时: {time.time()-t0:.0f}s")
