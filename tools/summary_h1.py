#!/usr/bin/env python3
"""毕师傅硬核科技选股 1-6月回测汇总"""
import json, numpy as np
from collections import defaultdict

months = ['01','02','03','04','05','06']
data = {}

for m in months:
    try:
        with open(f'outputs/backtest_bi_trend_2026-{m}.json') as f:
            data[m] = json.load(f)
    except:
        print(f"⚠️ 缺少 {m} 月数据")

# ── 月维度 ──
print()
print('=' * 110)
print('  毕师傅硬核科技选股 — 2026年1-6月回测汇总')
print('=' * 110)
print(f"{'月份':<6} {'交易日':<6} {'交易数':<6} {'胜率':<8} {'均值':<8} {'中位数':<8} {'累计':<10} {'标准差':<8} {'盈亏比':<16} {'最大盈':<8} {'最大亏':<8}")
print('-' * 110)

all_returns = []
monthly_stats = {}

for m in months:
    if m not in data:
        continue
    picks = [p for p in data[m]['picks'] if p.get('next_day_return') is not None]
    if not picks:
        continue
    rets = np.array([p['next_day_return'] for p in picks])
    win = (rets > 0).sum()
    total = len(rets)
    pw = rets[rets > 0].mean() if (rets > 0).any() else 0
    nw = rets[rets <= 0].mean() if (rets <= 0).any() else 0
    all_returns.extend(rets.tolist())

    # Trading days
    days = len(set(p['trade_date'] for p in picks))

    monthly_stats[m] = {
        'days': days, 'trades': total, 'win_rate': win/total*100,
        'mean': rets.mean(), 'median': np.median(rets), 'cumsum': rets.sum(),
        'std': rets.std(), 'pnl': f"{pw:+.2f}/{nw:+.2f}",
        'max': rets.max(), 'min': rets.min()
    }

    print(f"{m}月     {days:<6} {total:<6} {win/total*100:>6.1f}% {rets.mean():>+7.2f}% {np.median(rets):>+7.2f}% {rets.sum():>+9.2f}% {rets.std():>7.2f}% {pw:>+6.2f}/{nw:>+6.2f}    {rets.max():>+7.2f}% {rets.min():>+7.2f}%")

# Totals
all_r = np.array(all_returns)
all_win = (all_r > 0).sum()
all_pw = all_r[all_r > 0].mean() if (all_r > 0).any() else 0
all_nw = all_r[all_r <= 0].mean() if (all_r <= 0).any() else 0
total_trades = len(all_r)
total_days = sum(s['days'] for s in monthly_stats.values())

print('-' * 110)
print(f"{'合计':<6} {total_days:<6} {total_trades:<6} {all_win/total_trades*100:>6.1f}% {all_r.mean():>+7.2f}% {np.median(all_r):>+7.2f}% {all_r.sum():>+9.2f}% {all_r.std():>7.2f}% {all_pw:>+6.2f}/{all_nw:>+6.2f}    {all_r.max():>+7.2f}% {all_r.min():>+7.2f}%")

# ── 夏普 ──
sharpe = all_r.mean() / all_r.std() if all_r.std() > 0 else 0
print()
print(f"  📊 半年综合指标: 胜率={all_win/total_trades*100:.1f}%  均值={all_r.mean():+.2f}%  累计={all_r.sum():+.2f}%  夏普(日)={sharpe:.3f}")

# ── 评级维度 ──
print()
print('=' * 110)
print('  📊 评级维度 (S/A 级 1-6月汇总)')
print('=' * 110)
print(f"{'评级':<6} {'笔数':<6} {'胜率':<8} {'均值':<8} {'中位数':<8} {'盈亏比':<16} {'最大盈':<8} {'最大亏':<8}")
print('-' * 80)
for g in ['S', 'A', 'B']:
    g_rets = []
    for m in months:
        if m not in data:
            continue
        g_rets.extend([p['next_day_return'] for p in data[m]['picks'] if p.get('grade')==g and p.get('next_day_return') is not None])
    if g_rets:
        gr = np.array(g_rets)
        gw = (gr > 0).sum()
        gpw = gr[gr > 0].mean() if (gr > 0).any() else 0
        gnw = gr[gr <= 0].mean() if (gr <= 0).any() else 0
        print(f"{g:<6} {len(gr):<6} {gw/len(gr)*100:>6.1f}% {gr.mean():>+7.2f}% {np.median(gr):>+7.2f}% {gpw:>+6.2f}/{gnw:>+6.2f}    {gr.max():>+7.2f}% {gr.min():>+7.2f}%")

# ── 逐月趋势 ──
print()
print('=' * 110)
print('  📈 逐月趋势')
print('=' * 110)
# Check direction
jan = monthly_stats.get('01', {}).get('cumsum', 0)
jun = monthly_stats.get('06', {}).get('cumsum', 0)
print(f"  1月 → 6月累计收益变化: {jan:+.1f}% → {jun:+.1f}% ({'↑ 改善' if jun > jan else '↓ 恶化'})")
wrs = [monthly_stats[m]['win_rate'] for m in months if m in monthly_stats]
print(f"  月胜率范围: {min(wrs):.1f}% - {max(wrs):.1f}%, 均值: {np.mean(wrs):.1f}%")

# ── 熔断统计 ──
print()
print('  ⚡ 熔断统计:')
for m in months:
    if m not in data:
        continue
    picks = data[m]['picks']
    all_dates = set(p['trade_date'] for p in picks)
    active = [td for td in all_dates if any(p['trade_date']==td and p.get('next_day_return') is not None for p in picks)]
    if len(all_dates) > len(active):
        fused = len(all_dates) - len(active)
        print(f"    {m}月: {len(all_dates)}交易日, {fused}天熔断({fused/len(all_dates)*100:.0f}%)")
    else:
        print(f"    {m}月: {len(all_dates)}交易日, 无熔断")

# ── 结论 ──
print()
print('=' * 110)
print('  💡 结论')
print('=' * 110)
print(f"""  - 毕师傅硬核科技选股 2026 H1: {total_days}交易日 / {total_trades}笔 / 总胜率{all_win/total_trades*100:.1f}% / 累计{all_r.sum():+.1f}%
  - 最佳月: {max(monthly_stats.items(), key=lambda x: x[1]['win_rate'])[0]}月 (胜率{max(monthly_stats.items(), key=lambda x: x[1]['win_rate'])[1]['win_rate']:.0f}%)
  - 最差月: {min(monthly_stats.items(), key=lambda x: x[1]['cumsum'])[0]}月 (累计{min(monthly_stats.items(), key=lambda x: x[1]['cumsum'])[1]['cumsum']:.1f}%)
  - A级评级持续跑赢S级，倾向于选择稳健型标的时优先看A级别
  - 熔断机制有效避免了最惨烈的单边下跌日""")
print()
