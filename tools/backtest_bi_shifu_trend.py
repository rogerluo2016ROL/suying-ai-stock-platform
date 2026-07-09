#!/usr/bin/env python3
"""
毕师傅趋势战法 v2.0 全量回测 (2026全年逐日)

输出:
  - 每月胜率 & 平均收益率
  - 整体胜率 & 累计收益率
  - 按持仓天数的分层统计 (1d/3d/5d/10d/20d)
"""

import sys, os, time, json
from collections import defaultdict
from datetime import datetime

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'packages/kronos-factors'))
os.environ.setdefault('KRONOS_PG_URL', 'postgresql://kronos:kronos@localhost:6432/kronos')

from kronos_factors.engine.bi_shifu_trend import BiShifuTrendEngine
from kronos_factors.scorer._db_stub import _get_db

# ── 配置 ──
HORIZONS = [1, 3, 5, 10, 20]  # 持仓天数
TOP_N = 20

# ── 获取所有交易日 ──
with _get_db(readonly=True) as db:
    date_rows = db.execute("""
        SELECT DISTINCT trade_date FROM daily_kline
        WHERE trade_date >= '2026-01-01' AND trade_date <= '2026-07-08'
        ORDER BY trade_date
    """).fetchall()
    ALL_DATES = sorted([str(r['trade_date'])[:10] for r in date_rows])
    print(f"📅 2026年交易日: {len(ALL_DATES)} 天 ({ALL_DATES[0]} ~ {ALL_DATES[-1]})")

    # 预取所有K线的收盘价用于前向收益计算
    print("📊 预取K线数据...")
    fwd_rows = db.execute("""
        SELECT code, trade_date, close FROM daily_kline
        WHERE trade_date >= '2026-01-01' AND trade_date <= '2026-08-01'
        ORDER BY code, trade_date
    """).fetchall()

# 构建 {code: {date: close}} 字典
fwd_prices: dict[str, dict[str, float]] = defaultdict(dict)
for r in fwd_rows:
    d = str(r['trade_date'])[:10]
    fwd_prices[r['code']][d] = float(r['close'])

# ── 日期映射: 找到 date_index → N天后日期 ──
date_index = {d: i for i, d in enumerate(ALL_DATES)}


def forward_close(code: str, from_date: str, days: int) -> float | None:
    """返回 from_date 之后 days 个交易日的收盘价"""
    idx = date_index.get(from_date)
    if idx is None:
        return None
    target_idx = idx + days
    if target_idx >= len(ALL_DATES):
        return None
    target_date = ALL_DATES[target_idx]
    return fwd_prices.get(code, {}).get(target_date)


# ── 逐日回测 ──
print("🚀 开始逐日选股...")
engine = BiShifuTrendEngine()

all_picks: list[dict] = []           # 所有选股记录
daily_stats: list[dict] = []         # 每日统计
monthly_agg: dict[str, list] = defaultdict(list)  # 月度聚合

t_total = time.time()
total_scanned = 0

for day_i, trade_date in enumerate(ALL_DATES):
    t0 = time.time()
    picks = engine.run(top_n=TOP_N, trade_date=trade_date)
    elapsed = time.time() - t0
    total_scanned += 1

    if day_i % 20 == 0:
        eta = (time.time() - t_total) / max(day_i, 1) * (len(ALL_DATES) - day_i)
        print(f"  [{day_i+1}/{len(ALL_DATES)}] {trade_date} → {len(picks)} picks "
              f"({elapsed:.1f}s, 剩余约 {eta/60:.0f}min)")

    month_key = trade_date[:7]  # '2026-01'

    for p in picks:
        code = p['code']
        entry_price = float(p['close'])

        # 计算前向收益
        fwd_returns = {}
        for h in HORIZONS:
            fc = forward_close(code, trade_date, h)
            if fc and entry_price > 0:
                fwd_returns[f'r{h}d'] = round((fc - entry_price) / entry_price * 100, 2)
            else:
                fwd_returns[f'r{h}d'] = np.nan

        p['_fwd'] = fwd_returns
        all_picks.append(p)

        # 月度聚合
        monthly_agg[month_key].append(fwd_returns.get('r5d', np.nan))

    # 日统计
    r1d_list = [p['_fwd']['r1d'] for p in picks if not np.isnan(p['_fwd']['r1d'])]
    daily_stats.append({
        'date': trade_date,
        'picks': len(picks),
        'win_rate_1d': sum(1 for r in r1d_list if r > 0) / len(r1d_list) * 100 if r1d_list else 0,
        'avg_return_1d': np.mean(r1d_list) if r1d_list else 0,
    })

# ── 汇总统计 ──
print("\n" + "=" * 80)
print("                    毕师傅趋势战法 v2.0 回测报告")
print("=" * 80)
print(f"  回测区间: {ALL_DATES[0]} ~ {ALL_DATES[-1]} ({len(ALL_DATES)} 个交易日)")
print(f"  总选股次数: {len(all_picks)} (日均 {len(all_picks)/max(1,len(ALL_DATES)):.1f} 只)")
print()

# 按持仓天数统计
print("┌" + "─" * 78 + "┐")
print("│ 持仓天数 │  样本数 │  胜率(%) │ 平均收益(%) │ 中位收益(%) │ 最大收益(%) │ 最小收益(%) │")
print("├" + "─" * 78 + "┤")

for h in HORIZONS:
    key = f'r{h}d'
    vals = [p['_fwd'][key] for p in all_picks if not np.isnan(p['_fwd'].get(key, np.nan))]
    if not vals:
        continue
    win = sum(1 for v in vals if v > 0) / len(vals) * 100
    avg = np.mean(vals)
    med = np.median(vals)
    mx = np.max(vals)
    mn = np.min(vals)
    print(f"│    {h:2d}天    │  {len(vals):5d} │   {win:5.1f}  │    {avg:+6.2f}   │    {med:+6.2f}   │   {mx:+6.2f}    │   {mn:+6.2f}    │")

print("└" + "─" * 78 + "┘")
print()

# 按月统计 (5日持仓)
print("┌" + "─" * 78 + "┐")
print("│   月份   │  选股数 │  有信号天数 │  胜率(5d%) │ 均收益(5d%) │ 中位(5d%) │ 累计(5d%) │")
print("├" + "─" * 78 + "┤")

monthly_summary = []
for month in sorted(monthly_agg.keys()):
    vals = [v for v in monthly_agg[month] if not np.isnan(v)]
    if not vals:
        continue
    days_with_signals = len(set(
        p['_fwd'].get('r5d') for p in all_picks
        if p.get('trade_date', '').startswith(month)
    ))
    win = sum(1 for v in vals if v > 0) / len(vals) * 100
    avg = np.mean(vals)
    med = np.median(vals)
    cum = ((np.array(vals) / 100 + 1).prod() - 1) * 100  # 每笔等权复利
    n_picks = len(vals)
    print(f"│ {month}  │  {n_picks:5d} │     {days_with_signals:3d}     │   {win:5.1f}   │    {avg:+7.2f}  │   {med:+7.2f}  │  {cum:+7.2f}  │")
    monthly_summary.append({'month': month, 'n': n_picks, 'win': win, 'avg': avg, 'cum': cum})

print("└" + "─" * 78 + "┘")
print()

# 整体统计
all_r5d = [p['_fwd']['r5d'] for p in all_picks if not np.isnan(p['_fwd'].get('r5d', np.nan))]
all_r1d = [p['_fwd']['r1d'] for p in all_picks if not np.isnan(p['_fwd'].get('r1d', np.nan))]

if all_r5d:
    cum_5d = ((np.array(all_r5d) / 100 + 1).prod() - 1) * 100
    win_5d = sum(1 for v in all_r5d if v > 0) / len(all_r5d) * 100
    print(f"  📊 整体 (5日持仓): 胜率 {win_5d:.1f}% | 均收益 {np.mean(all_r5d):+.2f}% | "
          f"中位 {np.median(all_r5d):+.2f}% | 累计复利 {cum_5d:+.2f}%")
    print(f"     最大单笔: {np.max(all_r5d):+.2f}% | 最小单笔: {np.min(all_r5d):+.2f}% | "
          f"标准差: {np.std(all_r5d):.2f}%")

if all_r1d:
    win_1d = sum(1 for v in all_r1d if v > 0) / len(all_r1d) * 100
    print(f"  📊 整体 (1日持仓): 胜率 {win_1d:.1f}% | 均收益 {np.mean(all_r1d):+.2f}% | "
          f"中位 {np.median(all_r1d):+.2f}%")

# 选股数量分布
pick_counts = [d['picks'] for d in daily_stats]
print(f"\n  📈 日选股数: 最多 {max(pick_counts)} | 最少 {min(pick_counts)} | "
      f"平均 {np.mean(pick_counts):.1f} | 零信号 {sum(1 for c in pick_counts if c==0)} 天")
print(f"  有信号交易日: {sum(1 for c in pick_counts if c>0)}/{len(pick_counts)} "
      f"({sum(1 for c in pick_counts if c>0)/len(pick_counts)*100:.0f}%)")

# ── 保存详细结果 ──
out_path = f"outputs/backtest_bi_shifu_trend_{datetime.now().strftime('%Y%m%d-%H%M')}.json"
os.makedirs('outputs', exist_ok=True)

# 清理不可序列化的字段
clean_picks = []
for p in all_picks:
    cp = {k: v for k, v in p.items() if not k.startswith('_')}
    fwd = p.get('_fwd', {})
    for k, v in fwd.items():
        cp[f'fwd_{k}'] = v
    clean_picks.append(cp)

with open(out_path, 'w') as f:
    json.dump({
        'summary': {
            'total_days': len(ALL_DATES),
            'date_range': f'{ALL_DATES[0]} ~ {ALL_DATES[-1]}',
            'total_picks': len(all_picks),
            'avg_picks_per_day': len(all_picks) / max(1, len(ALL_DATES)),
            'horizons': {f'{h}d': {
                'n': len([p for p in all_picks if not np.isnan(p['_fwd'].get(f'r{h}d', np.nan))]),
                'win_rate': sum(1 for p in all_picks if p['_fwd'].get(f'r{h}d', -999) > 0) / max(1, len([p for p in all_picks if not np.isnan(p['_fwd'].get(f'r{h}d', np.nan))])) * 100,
                'avg_return': float(np.nanmean([p['_fwd'].get(f'r{h}d', np.nan) for p in all_picks])),
                'median_return': float(np.nanmedian([p['_fwd'].get(f'r{h}d', np.nan) for p in all_picks])),
            } for h in HORIZONS},
            'monthly': monthly_summary,
        },
        'picks': clean_picks,
        'daily_stats': daily_stats,
    }, f, ensure_ascii=False, indent=2, default=str)

print(f"\n📁 详细结果已保存: {out_path}")
print(f"⏱️  总耗时: {(time.time() - t_total)/60:.1f} min")
