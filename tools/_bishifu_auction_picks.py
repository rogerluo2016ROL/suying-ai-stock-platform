#!/usr/bin/env python3
"""毕师傅硬核科技选股(日线T) + 竞价涨幅过滤(竞价日A)."""
import os, sys
sys.path.insert(0, 'packages/kronos-factors')
from kronos_factors.pg_adapter import create_pg_adapter
from kronos_factors.scorer._db_stub import set_db_adapter, set_market_data_adapter
from kronos_factors.engine.bi_trend_launch import run_bi_screening

SCREEN_TD = sys.argv[1] if len(sys.argv) > 1 else '2026-06-24'  # 日线选股日
AUC_TD    = sys.argv[2] if len(sys.argv) > 2 else '2026-06-25'  # 竞价确认日
TOP_N     = int(sys.argv[3]) if len(sys.argv) > 3 else 50
AUC_MIN   = 5.0

pg = os.environ['KRONOS_PG_URL']
db = create_pg_adapter(pg)
set_db_adapter(db); set_market_data_adapter(db)

print(f"📅 选股日线: {SCREEN_TD} | 竞价确认: {AUC_TD} | top_n={TOP_N}")
top, all_scores, mkt = run_bi_screening(db, SCREEN_TD, top_n=TOP_N)
print(f"市场环境: {mkt.get('regime','?')} | 模型推荐 {len(top)} 只 / 全市场打分 {len(all_scores)} 只\n")

auc = {}
for r in db.execute(
    "SELECT code, open AS px, close AS pre, ((open/NULLIF(close,0))-1)*100 AS chg, amount "
    "FROM stk_auction_o WHERE trade_date=? AND open>0 AND close>0", (AUC_TD,)).fetchall():
    auc[r['code']] = (float(r['chg']), float(r['px']), float(r['amount']))

def show(picks, label):
    hits = sorted([(s, auc[s['code']]) for s in picks
                   if s.get('code') in auc and auc[s['code']][0] > AUC_MIN],
                  key=lambda x: -x[1][0])
    print(f"=== {label}: 竞价涨幅>{AUC_MIN}% 共 {len(hits)} 只 ===")
    if not hits: print("  (无)\n"); return
    print(f"  {'代码':<9}{'名称':<8}{'行业':<10}{'评级':<5}{'分':>4}{'信号':<11}{'竞价涨幅':>9}{'竞价额万':>9}")
    for s, a in hits:
        print(f"  {s['code']:<9}{(s.get('name') or '')[:6]:<8}{(s.get('industry') or '')[:8]:<10}"
              f"{s.get('grade',''):<5}{s.get('total_score',''):>4}{s.get('signal',''):<11}{a[0]:>8.2f}%{a[2]/1e4:>8.0f}")
    print()

show(top, "模型推荐池")
show(all_scores, "全市场打分池")

print("=== 模型推荐池全部明细(含竞价涨幅) ===")
print(f"  {'代码':<9}{'名称':<8}{'评级':<5}{'分':>4}{'竞价涨幅':>9}")
for s in top:
    a = auc.get(s['code'])
    chg = f"{a[0]:+.2f}%" if a else "无竞价"
    print(f"  {s['code']:<9}{(s.get('name') or '')[:6]:<8}{s.get('grade',''):<5}{s.get('total_score',''):>4}{chg:>9}")
