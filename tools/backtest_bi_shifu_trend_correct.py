#!/usr/bin/env python3
"""
毕师傅趋势战法 v2.0 正确回测 — 按设计文档交易规则

交易规则 (来自 docs/screener/bi-shifu-trend-rules.md):
  T日 (信号日):    收盘确认信号
  T+1日 (买入日):  开盘等权买入 (1/N)
  T+2日 (卖出日):  收盘全部卖出
  止损:            T+1/T+2 任意时刻日内最低价触及止损线即卖出

日收益率 = 各股收益率的算术平均
累积收益 = Π(1 + 日收益率)
"""

import sys, os, time, json
from collections import defaultdict
from datetime import datetime

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'packages/kronos-factors'))
os.environ.setdefault('KRONOS_PG_URL', 'postgresql://kronos:kronos@localhost:6432/kronos')

from kronos_factors.engine.bi_shifu_trend import BiShifuTrendEngine
from kronos_factors.scorer._db_stub import _get_db

TOP_N = 20

# ── 获取所有交易日 ──
with _get_db(readonly=True) as db:
    date_rows = db.execute("""
        SELECT DISTINCT trade_date FROM daily_kline
        WHERE trade_date >= '2026-01-01' AND trade_date <= '2026-07-08'
        ORDER BY trade_date
    """).fetchall()
    ALL_DATES = sorted([str(r['trade_date'])[:10] for r in date_rows])
    print(f"📅 交易日: {len(ALL_DATES)} 天 ({ALL_DATES[0]} ~ {ALL_DATES[-1]})")

    # 预取所有K线 (需要 open/high/low/close 用于 T+1/T+2 交易模拟)
    print("📊 预取K线...")
    fwd_rows = db.execute("""
        SELECT code, trade_date, open, high, low, close
        FROM daily_kline
        WHERE trade_date >= '2026-01-01' AND trade_date <= '2026-07-15'
        ORDER BY code, trade_date
    """).fetchall()

# {code: {date: {open, high, low, close}}}
fwd_bars: dict[str, dict[str, dict]] = defaultdict(dict)
for r in fwd_rows:
    d = str(r['trade_date'])[:10]
    fwd_bars[r['code']][d] = {
        'open': float(r['open']),
        'high': float(r['high']),
        'low': float(r['low']),
        'close': float(r['close']),
    }

date_index = {d: i for i, d in enumerate(ALL_DATES)}


def get_bar(code: str, date: str) -> dict | None:
    return fwd_bars.get(code, {}).get(date)


def forward_date(from_date: str, offset: int) -> str | None:
    idx = date_index.get(from_date)
    if idx is None:
        return None
    target = idx + offset
    if target >= len(ALL_DATES):
        return None
    return ALL_DATES[target]


# ── 逐日回测 (按交易规则) ──
print("🚀 逐日选股 + T+1开盘买 / T+2收盘卖...")
engine = BiShifuTrendEngine()

daily_results: list[dict] = []       # 每日记录
all_trades: list[dict] = []          # 每笔交易

t_total = time.time()

for day_i, trade_date in enumerate(ALL_DATES):
    picks = engine.run(top_n=TOP_N, trade_date=trade_date)

    if not picks:
        daily_results.append({
            'date': trade_date,
            'n_signals': 0,
            'n_trades': 0,
            'daily_return': 0,
            'cum_return': 0,
        })
        if day_i % 20 == 0:
            print(f"  [{day_i+1}/{len(ALL_DATES)}] {trade_date} → 0 signals")
        continue

    t1_date = forward_date(trade_date, 1)  # T+1 (买入日)
    t2_date = forward_date(trade_date, 2)  # T+2 (卖出日)

    if t1_date is None:
        daily_results.append({
            'date': trade_date,
            'n_signals': len(picks),
            'n_trades': 0,
            'daily_return': 0,
            'cum_return': 0,
        })
        continue

    trade_returns = []

    for p in picks:
        code = p['code']
        signal_close = float(p['close'])
        entry_price_expected = float(p['entry_price'])  # close * 1.01
        stop_loss = float(p['stop_loss'])
        dyn_stop_pct = float(p['stop_loss_pct']) / 100  # e.g. 0.08

        # Get T+1 bar (entry day)
        bar_t1 = get_bar(code, t1_date)
        if bar_t1 is None:
            continue

        # Buy at T+1 open
        buy_price = bar_t1['open']
        if buy_price <= 0:
            continue

        # Recalculate stop loss based on actual buy price
        actual_stop = buy_price * (1 - dyn_stop_pct)

        # Check T+1 intraday stop
        if bar_t1['low'] <= actual_stop:
            sell_price = actual_stop
            sell_date = t1_date
            stop_reason = 't1_stop'
        else:
            # Check T+2
            if t2_date is None:
                continue  # no T+2 data, skip
            bar_t2 = get_bar(code, t2_date)
            if bar_t2 is None:
                continue

            if bar_t2['low'] <= actual_stop:
                sell_price = actual_stop
                sell_date = t2_date
                stop_reason = 't2_stop'
            else:
                sell_price = bar_t2['close']  # T+2 close
                sell_date = t2_date
                stop_reason = 'normal'

        ret = (sell_price - buy_price) / buy_price

        trade_returns.append(ret)
        all_trades.append({
            'signal_date': trade_date,
            'code': code,
            'name': p['name'],
            'score': p['score'],
            'grade': p['grade'],
            'signal_close': signal_close,
            'buy_date': t1_date,
            'buy_price': round(buy_price, 2),
            'sell_date': sell_date,
            'sell_price': round(sell_price, 2),
            'return': round(ret * 100, 2),
            'stop_reason': stop_reason,
            'month': trade_date[:7],
        })

    n_trades = len(trade_returns)
    daily_ret = np.mean(trade_returns) if trade_returns else 0

    daily_results.append({
        'date': trade_date,
        'n_signals': len(picks),
        'n_trades': n_trades,
        'daily_return': daily_ret,
    })

    if day_i % 20 == 0:
        eta = (time.time() - t_total) / max(day_i, 1) * (len(ALL_DATES) - day_i)
        print(f"  [{day_i+1}/{len(ALL_DATES)}] {trade_date} → {len(picks)} signals, "
              f"{n_trades} trades, ret={daily_ret*100:+.2f}% "
              f"(剩余 ~{eta/60:.0f}min)")

# ── 计算累积收益 ──
cum = 1.0
cum_series = []
for dr in daily_results:
    cum *= (1 + dr['daily_return'])
    dr['cum_return'] = (cum - 1) * 100
    cum_series.append(dr['cum_return'])

elapsed_min = (time.time() - t_total) / 60

# ── 汇总 ──
print("\n" + "=" * 80)
print("     毕师傅趋势战法 v2.0 回测报告 (按设计文档交易规则)")
print("=" * 80)
print(f"  回测区间: {ALL_DATES[0]} ~ {ALL_DATES[-1]}")
print(f"  交易规则: T日信号 → T+1开盘买入 → T+2收盘卖出 (2日持仓)")
print(f"  止损:     日内最低价触及买入价×(1-止损%)即卖出")
print(f"  仓位:     同日N信号等权, 日收益=算术平均")
print()

# 整体统计
all_rets = [t['return'] for t in all_trades]
n_trades = len(all_trades)
n_win = sum(1 for r in all_rets if r > 0)
win_rate = n_win / n_trades * 100 if n_trades else 0
avg_ret = np.mean(all_rets) if all_rets else 0
med_ret = np.median(all_rets) if all_rets else 0

print(f"  总交易: {n_trades} 笔 | 胜率: {win_rate:.1f}% | 均收益: {avg_ret:+.2f}% | 中位: {med_ret:+.2f}%")
print(f"  最大单笔: {np.max(all_rets):+.2f}% | 最小单笔: {np.min(all_rets):+.2f}% | 标准差: {np.std(all_rets):.2f}%")
print(f"  累积收益: {cum_series[-1]:+.2f}%")
print(f"  有信号日: {sum(1 for d in daily_results if d['n_signals']>0)}/{len(daily_results)}")
print()

# 按月统计
print("┌" + "─" * 70 + "┐")
print("│   月份   │ 交易数 │  胜率(%) │ 均收益(%) │ 中位(%) │ 月累积(%) │")
print("├" + "─" * 70 + "┤")

monthly = defaultdict(list)
for t in all_trades:
    monthly[t['month']].append(t['return'])

for month in sorted(monthly.keys()):
    rets = monthly[month]
    n = len(rets)
    wr = sum(1 for r in rets if r > 0) / n * 100
    avg = np.mean(rets)
    med = np.median(rets)
    cum_m = ((np.array(rets) / 100 + 1).prod() - 1) * 100
    print(f"│ {month}  │  {n:5d} │    {wr:5.1f}  │    {avg:+6.2f}  │  {med:+6.2f}  │   {cum_m:+7.2f}  │")

print("└" + "─" * 70 + "┘")
print()

# 止损统计
stop_trades = [t for t in all_trades if t['stop_reason'] != 'normal']
print(f"  止损触发: {len(stop_trades)}/{n_trades} ({len(stop_trades)/n_trades*100:.1f}%)")
if stop_trades:
    stop_rets = [t['return'] for t in stop_trades]
    print(f"  止损交易均收益: {np.mean(stop_rets):+.2f}%")

normal_trades = [t for t in all_trades if t['stop_reason'] == 'normal']
if normal_trades:
    normal_rets = [t['return'] for t in normal_trades]
    print(f"  正常交易均收益: {np.mean(normal_rets):+.2f}%")

# 按评级统计
print()
print("  按评级:")
for grade in ['S', 'A', 'B', 'C']:
    g_trades = [t for t in all_trades if t['grade'] == grade]
    if g_trades:
        g_rets = [t['return'] for t in g_trades]
        g_wr = sum(1 for r in g_rets if r > 0) / len(g_rets) * 100
        print(f"    {grade}: {len(g_trades)}笔, 胜率{g_wr:.1f}%, 均收益{np.mean(g_rets):+.2f}%")

# ── 保存 ──
out_path = f"outputs/backtest_bi_shifu_trend_correct_{datetime.now().strftime('%Y%m%d-%H%M')}.json"
os.makedirs('outputs', exist_ok=True)
with open(out_path, 'w') as f:
    json.dump({
        'method': 'T+1 open buy, T+2 close sell, intraday stop loss',
        'summary': {
            'date_range': f'{ALL_DATES[0]} ~ {ALL_DATES[-1]}',
            'total_days': len(ALL_DATES),
            'total_trades': n_trades,
            'win_rate': round(win_rate, 1),
            'avg_return': round(avg_ret, 2),
            'median_return': round(med_ret, 2),
            'cumulative_return': round(cum_series[-1], 2),
            'max_return': round(np.max(all_rets) if all_rets else 0, 2),
            'min_return': round(np.min(all_rets) if all_rets else 0, 2),
            'std': round(np.std(all_rets) if all_rets else 0, 2),
            'stop_triggered': len(stop_trades),
            'monthly': {m: {
                'n': len(rets),
                'win_rate': round(sum(1 for r in rets if r > 0) / len(rets) * 100, 1),
                'avg_return': round(np.mean(rets), 2),
                'cum_return': round(((np.array(rets)/100+1).prod()-1)*100, 2),
            } for m, rets in monthly.items()},
        },
        'trades': all_trades,
        'daily': daily_results,
    }, f, ensure_ascii=False, indent=2, default=str)

print(f"\n📁 详细结果: {out_path}")
print(f"⏱️  总耗时: {elapsed_min:.1f} min")
