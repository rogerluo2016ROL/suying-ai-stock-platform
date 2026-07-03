#!/usr/bin/env python3
"""跑毕师傅硬核科技选股 + 推送飞书群（AI 投研分析）。

用法:
  KRONOS_PG_URL=postgresql://... FEISHU_APP_ID=... FEISHU_APP_SECRET=... FEISHU_CHAT_ID=oc_xxx \
    .venv/bin/python tools/send_bishifu_feishu.py [SCREEN_TD] [AUC_TD] [TOP_N]

默认: SCREEN_TD=2026-07-01 AUC_TD=2026-07-02 TOP_N=30
飞书 env 未配时只输出选股结果不推送（降级）。
"""
import os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 自动 load .env（不依赖 python-dotenv，secret 不入命令行/transcript）
_ENV_FILE = os.path.join(ROOT, '.env')
if os.path.exists(_ENV_FILE):
    for _line in open(_ENV_FILE, encoding='utf-8'):
        _line = _line.strip()
        if _line and not _line.startswith('#') and '=' in _line:
            _k, _v = _line.split('=', 1)
            os.environ.setdefault(_k.strip(), _v.strip())

sys.path.insert(0, os.path.join(ROOT, 'packages', 'kronos-factors'))
sys.path.insert(0, os.path.join(ROOT, 'services', 'alert-service'))

from kronos_factors.pg_adapter import create_pg_adapter
from kronos_factors.scorer._db_stub import set_db_adapter, set_market_data_adapter
from kronos_factors.engine.bi_trend_launch import run_bi_screening
from app import feishu_notifier

SCREEN_TD = sys.argv[1] if len(sys.argv) > 1 else '2026-07-01'
AUC_TD = sys.argv[2] if len(sys.argv) > 2 else '2026-07-02'
TOP_N = int(sys.argv[3]) if len(sys.argv) > 3 else 30
AUC_MIN = 5.0  # 竞价涨幅强确认门槛

pg = os.environ['KRONOS_PG_URL']
db = create_pg_adapter(pg)
set_db_adapter(db); set_market_data_adapter(db)

print(f"📅 选股日线: {SCREEN_TD} | 竞价确认: {AUC_TD} | top_n={TOP_N}")
top, all_scores, mkt = run_bi_screening(db, SCREEN_TD, top_n=TOP_N)
regime = mkt.get('regime', '?')
print(f"市场环境: {regime} | 模型推荐 {len(top)} 只 / 全市场打分 {len(all_scores)} 只\n")

# 竞价数据
auc = {}
for r in db.execute(
    "SELECT code, ((open/NULLIF(close,0))-1)*100 AS chg, amount "
    "FROM stk_auction_o WHERE trade_date=? AND open>0 AND close>0", (AUC_TD,)).fetchall():
    auc[r['code']] = (float(r['chg']), float(r['amount']))

# 强竞价确认（>5%）
strong = sorted([(s, auc[s['code']]) for s in top if s.get('code') in auc and auc[s['code']][0] > AUC_MIN],
                key=lambda x: -x[1][0])

# 控制台明细
print(f"=== 模型推荐池全部明细 (竞价涨幅) ===")
print(f"  {'代码':<9}{'名称':<8}{'评级':<5}{'分':>4}{'竞价涨幅':>9}")
for s in top:
    a = auc.get(s['code'])
    chg = f"{a[0]:+.2f}%" if a else "无竞价"
    print(f"  {s['code']:<9}{(s.get('name') or '')[:6]:<8}{s.get('grade',''):<5}{s.get('total_score',''):>4}{chg:>9}")
print(f"\n=== 竞价强确认 (>{AUC_MIN}%): {len(strong)} 只 ===")
for s, a in strong[:10]:
    print(f"  {s['code']} {s.get('name','')} {s.get('grade','')} 竞价{a[0]:+.2f}%")

# 推飞书
if not feishu_notifier.is_enabled():
    print("\n⚠️ 飞书未启用（FEISHU_APP_ID/APP_SECRET/CHAT_ID 未配），选股结果仅控制台输出。")
    print("   配齐 env 后重跑本脚本即自动推送飞书群。")
    sys.exit(0)

# 构造卡片内容
lines = [f"市场环境: {regime} | 推荐 {len(top)} 只 | 全市场打分 {len(all_scores)} 只", ""]
lines.append("【模型推荐池 Top10】")
for s in top[:10]:
    a = auc.get(s['code'])
    chg = f"竞价{a[0]:+.2f}%" if a else "无竞价"
    lines.append(f"  {s.get('grade','')} {s['code']} {(s.get('name') or '')[:6]} 分{s.get('total_score','')} {chg}")
if strong:
    lines.append("")
    lines.append(f"【竞价强确认 >{AUC_MIN}% 共{len(strong)}只】")
    for s, a in strong[:5]:
        lines.append(f"  {s['code']} {(s.get('name') or '')[:6]} 竞价{a[0]:+.2f}%")
message = "\n".join(lines)

ok, msg = feishu_notifier.send_alert_card(
    level="important" if len(top) >= 5 else "info",
    title=f"毕师傅硬核科技选股 {SCREEN_TD}",
    message=message,
    extra={"选股日": SCREEN_TD, "竞价确认日": AUC_TD, "推荐数": len(top), "强确认数": len(strong)},
)
print(f"\n飞书推送: success={ok} msg={msg}")
