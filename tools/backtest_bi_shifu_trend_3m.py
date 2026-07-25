#!/usr/bin/env python3
"""
毕师傅趋势战法 v2.1 最近三个月逐日回测

输出:
  - 每月胜率 & 平均收益率 (1d/3d/5d/10d/20d)
  - 整体胜率 & 收益率
  - 每日选股明细 JSON (outputs/backtests/bi_shifu_trend_3m_detail.json)
"""

import sys, os, time, json
from collections import defaultdict
from datetime import datetime

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'packages/kronos-factors'))
os.environ.setdefault('KRONOS_PG_URL', 'postgresql://kronos:kronos@localhost:6432/kronos')

from kronos_factors.engine.bi_shifu_trend import BiShifuTrendEngine
from kronos_factors.scorer._db_stub import _get_db

HORIZONS = [1, 3, 5, 10, 20]
TOP_N = 20
N_DAYS = 63  # 约三个月交易日

with _get_db(readonly=True) as db:
    date_rows = db.execute("""
        SELECT DISTINCT trade_date FROM daily_kline
        ORDER BY trade_date DESC LIMIT %s
    """ % (N_DAYS + 25)).fetchall()  # 多取25天覆盖20日前向窗口
    ALL_DATES = sorted([str(r['trade_date'])[:10] for r in date_rows])
    BT_DATES = ALL_DATES[-N_DAYS:]  # 回测窗口(最后63个交易日)
    print(f"回测窗口: {BT_DATES[0]} ~ {BT_DATES[-1]} ({len(BT_DATES)} 个交易日)")

    fwd_rows = db.execute("""
        SELECT code, trade_date, close FROM daily_kline
        WHERE trade_date >= '%s' ORDER BY code, trade_date
    """ % BT_DATES[0]).fetchall()

fwd_prices: dict[str, dict[str, float]] = defaultdict(dict)
for r in fwd_rows:
    fwd_prices[r['code']][str(r['trade_date'])[:10]] = float(r['close'])

date_index = {d: i for i, d in enumerate(ALL_DATES)}


def forward_close(code: str, from_date: str, days: int) -> float | None:
    idx = date_index.get(from_date)
    if idx is None or idx + days >= len(ALL_DATES):
        return None
    return fwd_prices.get(code, {}).get(ALL_DATES[idx + days])


print("开始逐日选股...")
engine = BiShifuTrendEngine()
all_picks: list[dict] = []
daily_detail: dict[str, list] = {}
t_total = time.time()

for day_i, trade_date in enumerate(BT_DATES):
    t0 = time.time()
    picks = engine.run(top_n=TOP_N, trade_date=trade_date)
    if day_i % 10 == 0:
        eta = (time.time() - t_total) / max(day_i, 1) * (len(BT_DATES) - day_i)
        print(f"  [{day_i+1}/{len(BT_DATES)}] {trade_date} → {len(picks)} picks ({time.time()-t0:.1f}s, ETA {eta/60:.0f}min)")

    day_list = []
    for p in picks:
        code = p['code']
        entry = float(p.get('close') or p.get('price') or 0)
        fwd = {}
        for h in HORIZONS:
            fc = forward_close(code, trade_date, h)
            fwd[f'r{h}d'] = round((fc - entry) / entry * 100, 2) if fc and entry > 0 else None
        rec = {
            'date': trade_date, 'code': code, 'name': p.get('name', ''),
            'close': entry, 'score': p.get('score'), 'grade': p.get('grade'),
            'vol_ratio': p.get('vol_ratio'), **fwd,
        }
        all_picks.append(rec)
        day_list.append(rec)
    daily_detail[trade_date] = day_list

# ── 汇总 ──
def stats(vals):
    vals = [v for v in vals if v is not None]
    if not vals:
        return {'n': 0, 'win_rate': None, 'avg': None, 'median': None}
    return {
        'n': len(vals),
        'win_rate': round(sum(1 for v in vals if v > 0) / len(vals) * 100, 1),
        'avg': round(float(np.mean(vals)), 2),
        'median': round(float(np.median(vals)), 2),
    }

print("\n" + "=" * 90)
print("毕师傅趋势战法 v2.1 三个月回测报告")
print("=" * 90)
print(f"区间: {BT_DATES[0]} ~ {BT_DATES[-1]}  总选股: {len(all_picks)} (日均 {len(all_picks)/len(BT_DATES):.1f})")

monthly: dict[str, list] = defaultdict(list)
for p in all_picks:
    monthly[p['date'][:7]].append(p)

report = {'window': [BT_DATES[0], BT_DATES[-1]], 'top_n': TOP_N, 'total_picks': len(all_picks)}
for m in sorted(monthly):
    picks_m = monthly[m]
    line = f"\n【{m}】 选股 {len(picks_m)} 只次"
    print(line)
    mstats = {}
    for h in HORIZONS:
        s = stats([p[f'r{h}d'] for p in picks_m])
        mstats[f'r{h}d'] = s
        if s['n']:
            print(f"  {h:>2}日持仓: 胜率 {s['win_rate']:>5}%  平均 {s['avg']:>6}%  中位 {s['median']:>6}%  (n={s['n']})")
    report[m] = mstats

print("\n【整体】")
overall = {}
for h in HORIZONS:
    s = stats([p[f'r{h}d'] for p in all_picks])
    overall[f'r{h}d'] = s
    if s['n']:
        print(f"  {h:>2}日持仓: 胜率 {s['win_rate']:>5}%  平均 {s['avg']:>6}%  中位 {s['median']:>6}%  (n={s['n']})")
report['overall'] = overall

out_dir = os.path.join(os.path.dirname(__file__), '..', 'outputs', 'backtests')
os.makedirs(out_dir, exist_ok=True)
out_path = os.path.join(out_dir, 'bi_shifu_trend_3m_detail.json')
with open(out_path, 'w', encoding='utf-8') as f:
    json.dump({'report': report, 'daily': daily_detail}, f, ensure_ascii=False, indent=1)
print(f"\n明细已写入: {out_path}")
