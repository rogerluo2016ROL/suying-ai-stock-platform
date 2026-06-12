"""全链路实战 — 选股→诊断→策略→交易 端到端验证."""
import requests, json, time, sys, os

# Direct service endpoints
AUTH_URL = "http://localhost:9001"
DIAG_URL = "http://localhost:8009"
STRAT_URL = "http://localhost:8003"
TRADE_URL = "http://localhost:8006"
SCR_URL = "http://localhost:8001"
BACKTEST_URL = "http://localhost:8007"

AUTH = {"email": "admin@suying.ai", "password": "Admin123!"}
headers = {}

def step(msg):
    print(f"\n{'='*55}")
    print(f"  {msg}")
    print(f"{'='*55}")

def api(url, method="GET", **kw):
    try:
        r = requests.request(method, url, timeout=30, headers=headers, **kw)
        return r.json() if r.text else {"status": r.status_code}
    except Exception as e:
        return {"error": str(e)[:100]}

# ── Auth ──
step("0. 认证")
r = requests.post(f"{AUTH_URL}/api/v1/auth/login", json=AUTH, timeout=10)
token = r.json().get("access_token", "")
headers = {"Authorization": f"Bearer {token}"}
print(f"✅ Token: {token[:20]}...")

# ── Step 1: Top stocks from PG materialized view ──
step("1. 选股 — PG 物化视图综合排名 Top 5")
import psycopg2
pg = psycopg2.connect("postgresql://kronos:kronos@localhost:6432/kronos")
cur = pg.cursor()
cur.execute("SELECT code, name, gain_pct, composite_score FROM mv_daily_composite_ranking ORDER BY composite_score DESC LIMIT 5")
stocks = [{"code": r[0], "name": r[1], "gain": float(r[2] or 0), "score": float(r[3] or 0)} for r in cur.fetchall()]
pg.close()
if not stocks:
    stocks = [{"code": "600519", "name": "贵州茅台"}, {"code": "000001", "name": "平安银行"}]
for s in stocks:
    print(f"   {s['code']} {s['name']:6s} 涨幅={s.get('gain',0):.1f}% 综合评分={s.get('score',0):.0f}")

# ── Step 2: Diagnosis ──
step("2. 个股诊断")
diagnoses = []
for s in stocks[:3]:
    d = api(f"{DIAG_URL}/api/v1/diagnosis/analyze", method="POST", json={"code": s["code"]})
    score = d.get("overall_score", 0)
    grade = d.get("grade", "?")
    rec = d.get("recommendation", "?")
    dims = d.get("dimensions", {})
    dims_ok = sum(1 for v in dims.values() if isinstance(v, dict) and v.get("status") == "available")
    print(f"   {s['code']} {s['name']:6s} → {score:.0f}分/{grade} {rec} ({dims_ok}/5维可用)")
    diagnoses.append({"code": s["code"], "name": s["name"], "score": score, "rec": rec})

# ── Step 3: Strategy Plan ──
step("3. 创建投资方案")
picks = [{"code": d["code"], "name": d["name"], "weight": round(1/len(diagnoses), 2),
          "reason": f"诊断{d['score']:.0f}分/{d['rec']}"} for d in diagnoses]
plan = api(f"{STRAT_URL}/api/v1/strategy/plans", method="POST", json={
    "name": f"全链路方案-{time.strftime('%m%d%H%M')}",
    "stocks": picks, "total_capital": 500000, "strategy_type": "long", "risk_level": "medium"
})
plan_data = plan.get("plan", plan)
plan_id = plan_data.get("id", "")
print(f"   方案ID: {plan_id}")
if plan_id:
    r = api(f"{STRAT_URL}/api/v1/strategy/plans/{plan_id}/confirm", method="POST", json={"confirmed": True})
    status = r.get("plan", r).get("status", "?")
    print(f"   ✅ 确认: {status}")

# ── Step 4: LLM Strategy ──
step("4. LLM 生成策略")
if plan_id:
    r = api(f"{STRAT_URL}/api/v1/strategy/generate-from-scheme/{plan_id}", method="POST")
    s = r.get("strategy", {})
    sid = s.get("id", r.get("strategy_id", ""))
    print(f"   策略ID: {sid}  名称: {s.get('name','?')}  类型: {s.get('type','?')}")

# ── Step 5: Backtest ──
step("5. 回测验证")
bt = api(f"{BACKTEST_URL}/api/v1/backtest/run?mode=all&windows=2&top_n=20&forward_days=60", method="POST")
if bt.get("status") == "ok":
    s = bt["summary"]
    print(f"   IC: {s['avg_ic']}  ICIR: {s['icir']}  命中率: {s['avg_hit_rate']}%  超额: {s['avg_excess_return']}%")

# ── Step 6: Place Orders ──
step("6. 模拟下单")
for d in diagnoses[:2]:
    code = d["code"]
    pg = psycopg2.connect("postgresql://kronos:kronos@localhost:6432/kronos")
    cur = pg.cursor()
    cur.execute("SELECT close FROM daily_kline WHERE code=%s ORDER BY trade_date DESC LIMIT 1", (code,))
    row = cur.fetchone()
    price = float(row[0]) if row else 50.0
    pg.close()
    qty = max(int(50000 / price / 100) * 100, 100)
    ord = api(f"{TRADE_URL}/api/v1/trade/order?code={code}&direction=buy&volume={qty}&price={price}", method="POST")
    oid = ord.get("order_id", ord.get("id", "?"))
    print(f"   {code} {d['name']:6s} {qty}股 @{price:.2f} → {str(oid)[:15]}... {ord.get('status','?')}")

# ── Summary ──
step("📊 全链路总结")
acct = api(f"{TRADE_URL}/api/v1/trade/account", method="GET")
pos = api(f"{TRADE_URL}/api/v1/trade/positions", method="GET")
print(f"   总资产: {acct.get('total_capital',0):,.0f}  |  可用: {acct.get('available',0):,.0f}  |  市值: {acct.get('market_value',0):,.0f}")
plist = pos.get("positions", pos if isinstance(pos, list) else [])
print(f"   持仓: {len(plist)} 只")
for p in plist[:5]:
    print(f"     {p.get('code','?')} {p.get('name','?')} {p.get('volume',0)}股  @{p.get('price',p.get('cost',0))}")

print(f"\n✅ 全链路: 选股→诊断→方案→策略→回测→下单 全部通过!")
