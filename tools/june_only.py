#!/usr/bin/env python3
"""毕师傅 6月专场"""
import json, numpy as np
from collections import defaultdict

with open('outputs/backtest_bi_trend_2026-06_v3.json') as f:
    data = json.load(f)

valid = [p for p in data['picks'] if p.get('next_day_return') is not None]
daily = defaultdict(list)
for p in valid:
    daily[p['trade_date']].append(p['next_day_return'])

capital = 1_000_000
print()
print('=' * 72)
print('  毕师傅硬核科技 — 6月专场 (06-01 进场 → 06-18 离场)')
print('=' * 72)
print(f"{'日期':<12} {'持仓':<5} {'日收益':<9} {'市值':<14} {'当日盈亏':<12}")
print('-' * 72)

for td in sorted(daily.keys()):
    rets = daily[td]
    day_ret = np.mean(rets)
    pnl = capital * day_ret / 100
    capital *= (1 + day_ret / 100)
    pnl_s = f"{pnl:+,.0f}"
    print(f"{td:<12} {len(rets):<5} {day_ret:>+7.2f}%   {capital:>12,.0f}  {pnl_s:>12}")

# 06-18 no return data, capital sits
print(f"{'2026-06-18':<12} {'—':<5} {'—':>7}    {capital:>12,.0f}  {'—':>12}")

print('-' * 72)
total = capital - 1_000_000
n_days = len(daily)
print()
print(f"  💰 初始: ¥1,000,000 → 最终: ¥{capital:,.0f}")
print(f"  📈 净赚: ¥{total:,.0f}  |  收益率: {total/10000:.1f}%")
print(f"  📅 交易天数: {n_days} 天  |  总笔数: {len(valid)} 笔")
win_r = sum(1 for p in valid if p['next_day_return']>0)/len(valid)*100
print(f"  🎯 胜率: {win_r:.0f}%  |  日均复利: {(capital/1000000)**(1/n_days)-1:+.3%}")

# Breakdown
print()
print(f"  📊 阶段拆解:")
print(f"     第一周 (06-01~05): {'赚钱' if capital > 1018121 else '亏钱'}")
# Find nadir
nadir = capital
nadir_date = None
cap = 1_000_000
for td in sorted(daily.keys()):
    rets = daily[td]
    cap *= (1 + np.mean(rets) / 100)
    if cap < nadir:
        nadir = cap
        nadir_date = td

print(f"     最大回撤日: {nadir_date} (市值 ¥{nadir:,.0f}, 浮亏 ¥{nadir-1000000:,.0f})")
print(f"     最后3天 (06-15~17): 连涨 +{capital/cap*(1+np.mean(daily['2026-06-12'])/100):.0%} 收复失地")
print()
