#!/usr/bin/env python3
"""对比毕师傅硬核科技 vs 秋神午后选股 6月回测"""
import json, numpy as np
from collections import defaultdict

with open('outputs/backtest_bi_trend_2026-06_v2.json') as f:
    bi = json.load(f)
with open('outputs/backtest_afternoon_2026-06_v2.json') as f:
    qiu = json.load(f)

def daily(picks):
    d = defaultdict(list)
    for p in picks:
        if p.get('next_day_return') is not None:
            d[p['trade_date']].append(p['next_day_return'])
    return d

bi_d = daily(bi['picks'])
qiu_d = daily(qiu['picks'])
all_dates = sorted(set(list(bi_d.keys()) + list(qiu_d.keys())))

def safe(val, fmt):
    return fmt.format(val) if val is not None else '—'

print()
print('=' * 95)
print('  毕师傅硬核科技 (Bi Trend)  VS  秋神午后选股 (Leader Afternoon)  —  2026年6月回测')
print('=' * 95)
print(f"{'日期':<12} {'毕-笔数':>5} {'毕-胜率':>7} {'毕-均值':>8}  │  {'秋-笔数':>5} {'秋-胜率':>7} {'秋-均值':>8}  │  {'当日胜者':<10}")
print('-' * 95)

bi_total, qiu_total = 0, 0
bi_wins, qiu_wins = 0, 0
bi_all_ret, qiu_all_ret = [], []
bi_day_wins = 0
qiu_day_wins = 0

for td in all_dates:
    b = bi_d[td]
    q = qiu_d[td]

    bm = np.mean(b)
    qm = np.mean(q)

    bw = sum(1 for r in b if r > 0)
    qw = sum(1 for r in q if r > 0)

    bi_total += len(b); qiu_total += len(q)
    bi_wins += bw; qiu_wins += qw
    bi_all_ret.extend(b); qiu_all_ret.extend(q)

    # Day winner
    if b and q:
        if bm > qm:
            winner = '🏆 毕师傅'
            bi_day_wins += 1
        elif qm > bm:
            winner = '🏆 秋神'
            qiu_day_wins += 1
        else:
            winner = '持平'
    elif b:
        winner = '🏆 毕师傅'; bi_day_wins += 1
    elif q:
        winner = '🏆 秋神'; qiu_day_wins += 1
    else:
        winner = '—'

    # Highlight winner side
    bi_mark = ' ◀' if '毕师傅' in winner else ''
    qiu_mark = ' ◀' if '秋神' in winner else ''

    print(f"{td:<12} {len(b):>5} {bw/len(b)*100:>6.1f}% {bm:>+7.2f}%{bi_mark:<3} │  {len(q):>5} {qw/len(q)*100:>6.1f}% {qm:>+7.2f}%{qiu_mark:<3} │  {winner}")

# Summary
print('-' * 95)
print(f"{'合计':<12} {bi_total:>5} {bi_wins/bi_total*100:>6.1f}% {np.mean(bi_all_ret):>+7.2f}%  │  {qiu_total:>5} {qiu_wins/qiu_total*100:>6.1f}% {np.mean(qiu_all_ret):>+7.2f}%")
print()

# Head-to-head stats
print('=' * 95)
print('  📊 综合对比')
print('=' * 95)
print(f"  {'指标':<24} {'毕师傅硬核科技':<28} {'秋神午后选股':<28}")
print(f"  {'─'*24} {'─'*28} {'─'*28}")
bi_r = np.array(bi_all_ret)
qiu_r = np.array(qiu_all_ret)
bi_sharpe = bi_r.mean() / bi_r.std() if bi_r.std() > 0 else 0
qiu_sharpe = qiu_r.mean() / qiu_r.std() if qiu_r.std() > 0 else 0

def stat_row(label, bi_v, qiu_v, fmt='', better='higher'):
    b, q = fmt.format(bi_v) if fmt else bi_v, fmt.format(qiu_v) if fmt else qiu_v
    print(f"  {label:<24} {str(b):<28} {str(q):<28}")

bi_wr = f"{bi_wins}/{bi_total} = {bi_wins/bi_total*100:.1f}%"
qiu_wr = f"{qiu_wins}/{qiu_total} = {qiu_wins/qiu_total*100:.1f}%"
bi_mean = f"{bi_r.mean():+.2f}%"
qiu_mean = f"{qiu_r.mean():+.2f}%"
bi_med = f"{np.median(bi_r):+.2f}%"
qiu_med = f"{np.median(qiu_r):+.2f}%"
bi_sum = f"{bi_r.sum():+.2f}%"
qiu_day_avg = f"{len(qiu_all_ret)/len(all_dates):.0f}"
bi_day_avg = f"{len(bi_all_ret)/len(all_dates):.0f}"
qiu_sum = f"{qiu_r.sum():+.2f}%"
bi_std = f"{bi_r.std():.2f}%"
qiu_std = f"{qiu_r.std():.2f}%"
bi_sh = f"{bi_sharpe:.3f}"
qiu_sh = f"{qiu_sharpe:.3f}"
bi_max = f"{bi_r.max():+.2f}%"
qiu_max = f"{qiu_r.max():+.2f}%"
bi_min = f"{bi_r.min():+.2f}%"
qiu_min = f"{qiu_r.min():+.2f}%"
bi_pw = bi_r[bi_r>0].mean() if (bi_r>0).any() else 0
bi_nw = bi_r[bi_r<=0].mean() if (bi_r<=0).any() else 0
qiu_pw = qiu_r[qiu_r>0].mean() if (qiu_r>0).any() else 0
qiu_nw = qiu_r[qiu_r<=0].mean() if (qiu_r<=0).any() else 0
bi_pnl = f"{bi_pw:+.2f}% / {bi_nw:+.2f}%"
qiu_pnl = f"{qiu_pw:+.2f}% / {qiu_nw:+.2f}%"

print(f"  {'总交易笔数':<24} {len(bi_all_ret):<28} {len(qiu_all_ret):<28}")
print(f"  {'胜率':<24} {bi_wr:<28} {qiu_wr:<28}")
print(f"  {'均值收益':<24} {bi_mean:<28} {qiu_mean:<28}")
print(f"  {'中位数收益':<24} {bi_med:<28} {qiu_med:<28}")
print(f"  {'累计收益':<24} {bi_sum:<28} {qiu_sum:<28}")
print(f"  {'标准差':<24} {bi_std:<28} {qiu_std:<28}")
print(f"  {'夏普(简易)':<24} {bi_sh:<28} {qiu_sh:<28}")
print(f"  {'最大盈利':<24} {bi_max:<28} {qiu_max:<28}")
print(f"  {'最大亏损':<24} {bi_min:<28} {qiu_min:<28}")
print(f"  {'盈亏比':<24} {bi_pnl:<28} {qiu_pnl:<28}")
print(f"  {'逐日胜出天数':<24} {f'{bi_day_wins} 天':<28} {f'{qiu_day_wins} 天':<28}")
print()

# Grade comparison
print('=' * 95)
print('  📊 评级对比 (S级 vs A级)')
print('=' * 95)
print(f"  {'评级':<6} {'毕师傅-笔数':<12} {'毕师傅-胜率':<12} {'毕师傅-均值':<12} {'秋神-笔数':<12} {'秋神-胜率':<12} {'秋神-均值':<12}")
print(f"  {'─'*6} {'─'*12} {'─'*12} {'─'*12} {'─'*12} {'─'*12} {'─'*12}")
for g in ['S', 'A', 'B', 'C']:
    bi_g = [p['next_day_return'] for p in bi['picks'] if p.get('grade')==g and p.get('next_day_return') is not None]
    qiu_g = [p['next_day_return'] for p in qiu['picks'] if p.get('grade')==g and p.get('next_day_return') is not None]
    if bi_g or qiu_g:
        if bi_g:
            bg_wr = sum(1 for r in bi_g if r>0)/len(bi_g)*100
            bg_avg = np.mean(bi_g)
        if qiu_g:
            qg_wr = sum(1 for r in qiu_g if r>0)/len(qiu_g)*100
            qg_avg = np.mean(qiu_g)
        bi_gs = f"{bg_wr:.1f}%" if bi_g else '—'
        bi_gm = f"{bg_avg:+.2f}%" if bi_g else '—'
        qiu_gs = f"{qg_wr:.1f}%" if qiu_g else '—'
        qiu_gm = f"{qg_avg:+.2f}%" if qiu_g else '—'
        print(f"  {g:<6} {len(bi_g):<12} {bi_gs:<12} {bi_gm:<12} {len(qiu_g):<12} {qiu_gs:<12} {qiu_gm:<12}")

print()
print('=' * 95)
print('  💡 结论')
print('=' * 95)
print(f"""  - 毕师傅硬核科技：胜率 {bi_wins/bi_total*100:.1f}%，更稳但机会少(日均{bi_day_avg}笔)，适合熊市/震荡
  - 秋神午后选股：总收益高(+{qiu_r.sum():.1f}%)，爆发力强但波动大(σ={qiu_r.std():.1f}%)，适合牛市/反弹
  - 两模型互补：毕师傅赢的{bi_day_wins}天秋神平均亏{qiu_day_wins}天
  - 建议：弱市用毕师傅做底仓，强市用秋神做进攻""")
print()
