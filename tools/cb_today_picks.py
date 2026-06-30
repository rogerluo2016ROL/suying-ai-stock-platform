#!/usr/bin/env python3
"""今日选股 + 详细理由"""
import argparse, sys,os,pickle,numpy as np,psycopg2
_PROJ=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0,os.path.join(_PROJ,'packages','kronos-factors'));sys.path.insert(0,_PROJ)
from kronos_factors.engine.cb_intraday import CbIntradayEngine

PG=os.environ.get('KRONOS_PG_URL','postgresql://kronos:kronos@localhost:6432/kronos')


def _format_reason(p):
    reasons = []
    if p.get("price_gap") is not None:
        reasons.append(f"价差{p['price_gap']:.2f}元")
    if p.get("premium_rate") is not None:
        reasons.append(f"溢价率{p['premium_rate']:.2f}%")
    if p.get("route") in ("A低溢价题材", "A+B共振"):
        reasons.append("低溢价题材路线")
    if p.get("route") in ("B下修事件", "A+B共振"):
        reasons.append("下修事件路线")
    if p.get("maturity_days_left") is not None:
        reasons.append(f"剩余{p['maturity_days_left']}天")
    return " / ".join(reasons) if reasons else "底价安全垫候选"


def _format_risk(p):
    risks = list(p.get("risk_flags") or [])
    missing = p.get("missing_fields") or []
    if "ownership_nature" in missing:
        risks.append("控股属性缺失")
    if "rating" in missing:
        risks.append("评级字段缺失")
    if "maturity_call_price" in missing:
        risks.append("到期赎回价使用代理值")
    return " / ".join(dict.fromkeys(risks)) if risks else "无显著字段风险"


def print_cb_floor_picks(trade_date=None, top_n=20):
    from kronos_factors.engine.cb_floor import CbFloorEngine

    engine = CbFloorEngine(pg_url=PG)
    try:
        picks = engine.run(trade_date=trade_date, top_n=top_n)
    finally:
        engine.close()

    if not picks:
        print("No cb_floor picks: 当前没有满足底价安全垫门槛的转债")
        return

    date_label = trade_date or "latest"
    print(f"""
╔══════════════════════════════════════════════════════════════════════════════════╗
║  可转债底价安全垫选债 | 选债日: {date_label} | Top {top_n}
╚══════════════════════════════════════════════════════════════════════════════════╝""")

    route_order = ("A+B共振", "A低溢价题材", "B下修事件", "底价观察")
    for route in route_order:
        group = [p for p in picks if p.get("route") == route]
        if not group:
            continue
        print(f"\n[{route}]")
        print(f"{'#':<3} {'转债':<10} {'价格':<8} {'价差':<8} {'溢价%':<8} {'剩余天':<8} {'质押%':<8} {'A线':<6} {'B线':<6} {'总分':<6} {'等级':<3}")
        print("-" * 108)
        for i, p in enumerate(group, 1):
            print(
                f"{i:<3} {p.get('name', p.get('code','')):<10} "
                f"{str(p.get('price')):<8} {str(p.get('price_gap')):<8} "
                f"{str(p.get('premium_rate')):<8} {str(p.get('maturity_days_left')):<8} "
                f"{str(p.get('pledge_total_ratio')):<8} {p.get('route_a_score',0):<6} "
                f"{p.get('route_b_score',0):<6} {p.get('total_score',0):<6} {p.get('grade',''):<3}"
            )
            print(f"    入选原因: {_format_reason(p)}")
            print(f"    风险提示: {_format_risk(p)}")


if "--mode" in sys.argv:
    parser = argparse.ArgumentParser(description="CB today picks")
    parser.add_argument("date", nargs="?", default=None, help="Trade date YYYY-MM-DD")
    parser.add_argument("--mode", choices=["cb_floor", "cb_intraday"], default="cb_intraday")
    parser.add_argument("--top-n", type=int, default=20)
    args = parser.parse_args()
    if args.mode == "cb_floor":
        print_cb_floor_picks(args.date, args.top_n)
        sys.exit(0)

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
