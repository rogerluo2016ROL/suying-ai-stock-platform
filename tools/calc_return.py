#!/usr/bin/env python3
"""计算毕师傅硬核科技 100万入场到6月18日的实际收益"""
import json, numpy as np
from collections import defaultdict

months = ['01','02','03','04','05','06']
all_picks = []

for m in months:
    fn = f'outputs/backtest_bi_trend_2026-{m}.json'
    if m == '06':
        fn = 'outputs/backtest_bi_trend_2026-06_v3.json'
    try:
        with open(fn) as f:
            data = json.load(f)
            all_picks.extend(data['picks'])
    except Exception as e:
        print(f"⚠️ 加载{m}月失败: {e}")

# Remove pending
valid = [p for p in all_picks if p.get('next_day_return') is not None]

# Group by trade_date
daily = defaultdict(list)
for p in valid:
    daily[p['trade_date']].append(p['next_day_return'])

# Sort dates
all_dates = sorted(daily.keys())

# Compound: 100万 start
capital = 1_000_000
daily_records = []

# Get all trading dates to fill gaps (熔断 days = 0%)
# Build full date range from min to max
from datetime import datetime, timedelta

# Actually, we just iterate through the sorted dates we have.
# Gaps between trade_dates where there are picks are fine — capital sits
# But we need to handle weekends/holidays correctly.
# Simplification: compound only on days with picks, capital idle otherwise.

print()
print('=' * 90)
print(f'  毕师傅硬核科技 — 100万模拟实盘 (2026-01-05 → 2026-06-18)')
print('=' * 90)
print(f"{'日期':<12} {'持仓数':<6} {'日收益':<10} {'市值':<14} {'当日盈亏':<12}")
print('-' * 90)

total_trades = 0
win_days = 0
lose_days = 0

for td in all_dates:
    rets = daily[td]
    n = len(rets)
    day_ret = np.mean(rets)  # equal weight
    pnl = capital * day_ret / 100
    capital *= (1 + day_ret / 100)

    daily_records.append({
        'date': td, 'n': n, 'day_ret': day_ret,
        'capital': capital, 'pnl': pnl
    })

    total_trades += n
    if day_ret > 0:
        win_days += 1
    elif day_ret < 0:
        lose_days += 1

    pnl_str = f"+{pnl:,.0f}" if pnl >= 0 else f"{pnl:,.0f}"
    print(f"{td:<12} {n:<6} {day_ret:>+7.2f}%   ¥{capital:>12,.0f}  {pnl_str:>12}")

print('-' * 90)
final = capital
total_return = (final - 1_000_000) / 1_000_000 * 100
total_pnl = final - 1_000_000

print(f"\n  📊 模拟实盘结果")
print(f"  {'初始资金:':<16} ¥1,000,000")
print(f"  {'最终市值:':<16} ¥{final:,.0f}")
print(f"  {'总收益:':<16} +{total_pnl:,.0f} ({total_return:+.1f}%)")
print(f"  {'交易天数:':<16} {len(all_dates)}天  (其中⬆{win_days}天 ⬇{lose_days}天)")
print(f"  {'总交易笔数:':<16} {total_trades}笔")
print(f"  {'日均仓位:':<16} {total_trades/len(all_dates):.1f}只")

# Monthly breakdown
print(f"\n  📅 逐月资金曲线")
prev = 1_000_000
for m in months:
    m_dates = [td for td in all_dates if td.startswith(f'2026-{m}')]
    if not m_dates:
        continue
    m_end = [d for d in daily_records if d['date'] in m_dates][-1]
    m_pnl = m_end['capital'] - prev
    m_ret = m_pnl / prev * 100
    m_trades = sum(d['n'] for d in daily_records if d['date'] in m_dates)
    print(f"  {m}月: ¥{prev:,.0f} → ¥{m_end['capital']:,.0f}  {m_ret:+.1f}% ({m_trades}笔/{len(m_dates)}天)")
    prev = m_end['capital']

print()
print(f"  🏆 最终结论: 100万 → ¥{final:,.0f}, 盈利 ¥{total_pnl:,.0f} ({total_return:+.1f}%)")
print()
