#!/usr/bin/env python3
"""今日选股 + 详细理由"""
import sys,os,pickle,numpy as np,psycopg2
_PROJ=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0,os.path.join(_PROJ,'packages','kronos-factors'));sys.path.insert(0,_PROJ)
from kronos_factors.engine.cb_intraday import CbIntradayEngine

PG=os.environ.get('KRONOS_PG_URL','postgresql://kronos:kronos@localhost:6432/kronos')

ml_models={}
for n in ['rf','lightgbm','catboost']:
    with open(os.path.join(_PROJ,'outputs',f'cb_ml_{n}.pkl'),'rb') as f:
        ml_models[n]=pickle.load(f)['model']

trade_date = sys.argv[1] if len(sys.argv)>1 else '2026-06-12'

engine=CbIntradayEngine(pg_url=PG)
raw=engine.run(trade_date=trade_date,top_n=30,use_ml=False)
engine.close()

if not raw: print("No picks!"); exit()

# Fetch market context first (needed for dynamic threshold)
conn=psycopg2.connect(PG);cur=conn.cursor()
cur.execute("SELECT change_pct FROM index_daily WHERE code='000001' AND trade_date=%s",(trade_date,))
mkt=cur.fetchone()
mkt_str=f"上证 {float(mkt[0]):+.2f}%" if mkt and mkt[0] else "N/A"
conn.close()

# ML re-rank
for p in raw:
    d=p.get('details',{})
    X=np.array([[d.get('sector_score',50),d.get('premium_score',50),d.get('momentum_score',50),
        d.get('liquidity_score',50),d.get('rev_bonus',0),d.get('call_penalty',0),
        p.get('premium_rate') or 0,p.get('yesterday_pct') or 0,p.get('cb_amount_wan') or 0,0,0]],dtype=np.float32)
    p['_ml']=float(np.mean([m.predict(X)[0] for m in ml_models.values()]))

# Dynamic threshold: bull=1.5, normal=2.0, bear=3.0
ml_th=2.0
if mkt and mkt[0] is not None:
    mkt_val=float(mkt[0])
    if mkt_val < -1.0: ml_th=3.0
    elif mkt_val > 0.5: ml_th=1.5

picks=[p for p in raw if p.get('_ml',0)>=ml_th]
picks.sort(key=lambda x: x.get('_ml',0),reverse=True)
picks=picks[:15]

print(f"""
╔══════════════════════════════════════════════════════════════════════════════════╗
║  匪爷可转债日内竞价选债 V6.2 | 选股日: {trade_date} | {mkt_str}
╠══════════════════════════════════════════════════════════════════════════════════╣
║  ML阈值: {ml_th} | 候选: {len(raw)}只 -> ML过滤后: {len(picks)}只
╚══════════════════════════════════════════════════════════════════════════════════╝""")

print(f"{'#':<3} {'转债':<10} {'正股':<7} {'板块':<12} {'溢价%':<7} {'昨涨%':<7} {'成交万':<7} {'ML分':<6} {'等级':<3} {'选债理由'}")
print(f"{'-'*110}")

for i,p in enumerate(picks,1):
    d=p.get('details',{})
    sec=(p.get('sector','') or '')[:12]
    pr=f"{p.get('premium_rate'):.1f}" if p.get('premium_rate') else 'N/A'
    yp=f"{p.get('yesterday_pct'):+.1f}" if p.get('yesterday_pct') else 'N/A'
    amt=p.get('cb_amount_wan') or 'N/A'
    reasons=[]
    pr_val=p.get('premium_rate')
    if pr_val is not None and pr_val<0: reasons.append('折价')
    elif pr_val is not None and pr_val<10: reasons.append('低溢价')
    if d.get('liquidity_score',0)>45: reasons.append('高流动性')
    if d.get('momentum_score',0)>80: reasons.append('强动量')
    if d.get('sector_score',0)>70: reasons.append('竞价板块强')
    if d.get('rev_bonus',0)>0: reasons.append('下修催化')
    if not reasons: reasons.append('综合ML高分')
    print(f"{i:<3} {p['name']:<10} {p.get('stk_code',''):<7} {sec:<12} {pr:<7} {yp:<7} {str(amt):<7} {p['_ml']:<6.1f} {p.get('grade','B'):<3} {','.join(reasons)}")

if not picks:
    print("  ML未选出合格标的 - 今日竞价无强势板块或市场环境不佳")

print(f"\n{'-'*110}")
print("因子明细: s=板块 p=溢价率 m=动量 l=流动性 rev=下修 call=强赎")
for i,p in enumerate(picks[:15],1):
    d=p.get('details',{})
    print(f"  {i}. {p['name']:<10} s={d.get('sector_score',50):.0f} p={d.get('premium_score',50):.0f} m={d.get('momentum_score',50):.0f} l={d.get('liquidity_score',50):.0f}  rev={d.get('rev_bonus',0):.0f}  call={d.get('call_penalty',0):.0f}")

print(f"""
出场规则: 1.自适应止盈(2~5%) 2.回撤-2%止损 3.KDJ_J>95+VWAP上方 4.14:30尾盘平仓
仓位建议: A级15% B级10% C级5%  止损: 单日亏3%停/连3笔停
""")
