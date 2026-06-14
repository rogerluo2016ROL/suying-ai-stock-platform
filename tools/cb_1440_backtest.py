#!/usr/bin/env python3
"""14:40 盘中选债回测 — 分时板块替代竞价, 入场14:40 → 收盘出场"""
import sys, os, json, time, pickle
import numpy as np
import psycopg2
from collections import defaultdict

_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_PROJ, 'packages', 'kronos-factors'))
sys.path.insert(0, _PROJ)
from kronos_factors.engine.cb_intraday import CbIntradayEngine

PG = os.environ.get('KRONOS_PG_URL', 'postgresql://kronos:kronos@localhost:6432/kronos')

t_total = time.time()

# Load ML models
print("Loading Ensemble...", end=" ", flush=True)
ml_models = {}
for name in ['rf', 'lightgbm', 'catboost']:
    with open(os.path.join(_PROJ, 'outputs', f'cb_ml_{name}.pkl'), 'rb') as f:
        ml_models[name] = pickle.load(f)['model']
print("OK")

def ml_score(details, premium_rate, yesterday_pct, cb_amount_wan):
    X = np.array([[details.get('sector_score',50), details.get('premium_score',50),
        details.get('momentum_score',50), details.get('liquidity_score',50),
        details.get('rev_bonus',0), details.get('call_penalty',0),
        premium_rate or 0, yesterday_pct or 0, cb_amount_wan or 0, 0, 0]], dtype=np.float32)
    return float(np.mean([m.predict(X)[0] for m in ml_models.values()]))

# Get trading days with stk_mins data
conn = psycopg2.connect(PG)
cur = conn.cursor()
cur.execute("""
    SELECT DISTINCT DATE(trade_time) FROM stk_mins
    WHERE freq='5min' AND DATE(trade_time) >= '2026-03-13'
    ORDER BY 1
""")
trade_dates = [str(r[0]) for r in cur.fetchall() if str(r[0]) >= '2026-03-13']
print(f"Trading days: {len(trade_dates)}")

# Pre-fetch cb_daily
cur.execute("SELECT ts_code, trade_date, close FROM cb_daily WHERE trade_date >= '2026-03-13'")
cb_close_lookup = {}
for r in cur.fetchall():
    cb_close_lookup[(r[0], str(r[1]))] = r[2]

# Pre-fetch cb_basic
cur.execute("SELECT ts_code, bond_short_name, stk_code, conv_price FROM cb_basic")
cb_info = {}
for r in cur.fetchall():
    cb_info[r[0]] = {'name': r[1], 'stk_code': r[2].split('.')[0] if r[2] and '.' in str(r[2]) else str(r[2] or ''), 'conv_price': r[3]}

# Pre-fetch cb_concept (concept→CBs)
cur.execute("SELECT ts_code, concept FROM cb_concept")
concept_cbs = defaultdict(set)
for r in cur.fetchall():
    concept_cbs[r[0]].add(r[1])

# Pre-fetch yesterday stock pct
cur.execute("SELECT code, trade_date, change_pct FROM daily_kline WHERE trade_date >= '2026-03-12'")
ypct_raw = defaultdict(list)
for r in cur.fetchall():
    ypct_raw[r[0]].append((str(r[1]), r[2]))
yesterday_pct_map = {}
for code, rows in ypct_raw.items():
    for i, (td, pct) in enumerate(rows):
        if i+1 < len(rows) and rows[i+1][1] is not None:
            yesterday_pct_map[(code, td)] = rows[i+1][1]

conn.close()
print(f"Data loaded ({time.time()-t_total:.0f}s)")

# ── 14:40 model logic ──
def score_premium(p):
    if p is None: return 50
    if p <= -10: return 100
    elif p <= -5: return 95+(p+10)*1.0
    elif p <= 0: return 85+p*2.0
    elif p <= 20: return 85-p*3.0
    elif p <= 50: return 25-(p-20)*0.7
    return max(1, 4-(p-50)*0.05)

def score_afternoon_momentum(bars_1440, stock_open):
    """Afternoon sector strength: use 14:40 bar close vs open as proxy"""
    if not stock_open or stock_open <= 0: return 50
    ret = (bars_1440['close'] - stock_open) / stock_open * 100
    if ret >= 3: return 90
    elif ret >= 1: return 70+(ret-1)*10
    elif ret >= 0: return 55+ret*15
    elif ret >= -1: return 40+(ret+1)*15
    elif ret >= -3: return 20+(ret+3)*10
    return max(5, 20+ret*2)

def score_momentum_v6(p):
    if p is None: return 50
    if p > 5: return 0
    if -3 <= p <= -1: return 85+(p+3)*7.5
    if -1 < p < 0: return 70+(p+1)*15
    if 0 <= p <= 3: return 55+p*5
    if 3 < p <= 5: return 40+(5-p)*7.5
    return max(10, 30+(p+3)*3)

def score_liquidity(amt):
    if amt is None or amt <= 0: return 20
    w = amt/1e4
    if w >= 5000: return 100
    elif w >= 1000: return 80+(w-1000)/4000*20
    elif w >= 500: return 65+(w-500)/500*15
    elif w >= 100: return 40+(w-100)/400*25
    elif w >= 50: return 20+(w-50)/50*20
    return max(5, w*0.4)

# ── Main loop: 14:40 rule-based scoring ──
all_trades = []
errors = 0
t0 = time.time()
conn = psycopg2.connect(PG)

for ti, td in enumerate(trade_dates):
    if ti % 10 == 0:
        print(f"  {ti}/{len(trade_dates)} {td} ({len(all_trades)}t, {time.time()-t0:.0f}s)", flush=True)

    try:
        cur = conn.cursor()

        # Get 14:40 bar + day VWAP + day range
        cur.execute("""
            SELECT code,
                   MAX(CASE WHEN trade_time::time <= '14:45' THEN close END) as close_1440,
                   SUM(amount) / NULLIF(SUM(volume), 0) as vwap,
                   MAX(high) as day_high, MIN(low) as day_low,
                   SUM(CASE WHEN trade_time::time >= '14:00' THEN amount ELSE 0 END) as late_amount,
                   SUM(CASE WHEN trade_time::time < '14:00' THEN amount ELSE 0 END) as early_amount
            FROM stk_mins
            WHERE DATE(trade_time) = %s AND freq = '5min'
            GROUP BY code
        """, (td,))
        stock_1440 = {}
        for r in cur.fetchall():
            if r[1] and r[1] > 0:
                stock_1440[r[0]] = {
                    'close': float(r[1]), 'vwap': float(r[2] or 0),
                    'high': float(r[3] or 0), 'low': float(r[4] or 0),
                    'late_vol': float(r[5] or 0), 'early_vol': float(r[6] or 0),
                }

        cur.execute("SELECT ts_code, close, cb_over_rate, amount, open FROM cb_daily WHERE trade_date = %s", (td,))
        cb_today = {r[0]: {'close': r[1], 'premium': r[2], 'amount': r[3], 'open': r[4]} for r in cur.fetchall()}

        try: conn.rollback()
        except: pass

        if not stock_1440: continue

        # Get stock opens
        cur.execute("SELECT code, open FROM daily_kline WHERE trade_date = %s", (td,))
        stock_opens = {r[0]: float(r[1] or 0) for r in cur.fetchall()}

        # ── Strategy A: Momentum ──  ── Strategy B: Reversal ──
        candidates_a, candidates_b = [], []
        for cb_code, info in cb_info.items():
            stk = info['stk_code']
            s1440 = stock_1440.get(stk)
            stock_open = stock_opens.get(stk, 0)
            if not s1440 or stock_open <= 0: continue

            cb_day = cb_today.get(cb_code, {})
            premium = cb_day.get('premium')
            ypct = yesterday_pct_map.get((stk, td))
            if premium and premium > 80: continue
            if ypct and ypct > 5: continue

            intraday_ret = (s1440['close'] - stock_open) / stock_open * 100
            vol_ratio = s1440['late_vol'] / s1440['early_vol'] if s1440['early_vol'] > 0 else 0

            # A: Momentum — up >1.5%, afternoon volume > normal
            if intraday_ret > 1.5 and vol_ratio > 0.15:
                score_a = min(100, 50 + intraday_ret * 8 + vol_ratio * 25)
                candidates_a.append({'code': cb_code, 'name': info['name'], 'stk_code': stk,
                    'premium_rate': premium, 'intraday_ret': round(intraday_ret, 2),
                    'vol_ratio': round(vol_ratio, 2), 'score': round(score_a, 1), 'strategy': 'momentum'})

            # B: Reversal — down -1~-4%, low premium
            if -4 <= intraday_ret <= -1 and (premium is None or premium < 30):
                score_b = min(100, 60 + abs(intraday_ret) * 12)
                candidates_b.append({'code': cb_code, 'name': info['name'], 'stk_code': stk,
                    'premium_rate': premium, 'intraday_ret': round(intraday_ret, 2),
                    'score': round(score_b, 1), 'strategy': 'reversal'})

        candidates_a.sort(key=lambda x: x['score'], reverse=True)
        candidates_b.sort(key=lambda x: x['score'], reverse=True)
        candidates = candidates_a[:5] + candidates_b[:5]

        for c in candidates:
            cb_close = cb_close_lookup.get((c['code'], td))
            cb_day = cb_today.get(c['code'], {})
            cb_open = cb_day.get('open')
            ret = None
            if cb_open and cb_close and cb_open > 0 and cb_close > 0:
                ir = c.get('intraday_ret', 0) or 0
                cb_entry = cb_open * (1 + ir / 100 * 0.85)
                if cb_entry > 0:
                    ret = (cb_close - cb_entry) / cb_entry * 100

            all_trades.append({
                'date': td, 'code': c['code'], 'name': c['name'],
                'stk_code': c['stk_code'], 'strategy': c['strategy'],
                'score': c['score'], 'intraday_ret_1440': c.get('intraday_ret', 0),
                'premium_rate': c['premium_rate'],
                'intraday_return': round(ret, 2) if ret is not None else None,
            })
    except Exception as e:
        errors += 1
        if errors <= 3: print(f"  E@{td}: {e}", flush=True)
        try: conn.rollback()
        except: pass
        continue

conn.close()

# ── Results ──
valid = [t for t in all_trades if t['intraday_return'] is not None]
rets = [t['intraday_return'] for t in valid]
elapsed = time.time() - t0

print(f"\nDone: {len(all_trades)}t, {len(valid)} valid, {len(set(t['date'] for t in all_trades))}d, {elapsed:.0f}s")
print(f"Mean: {np.mean(rets):+.2f}%  Win: {sum(1 for r in rets if r>0)/len(rets)*100:.1f}%  Err: {errors}")

# Analysis
print(f"\n策略对比:")
for stype in ['momentum', 'reversal']:
    bt = [t for t in valid if t.get('strategy') == stype]
    if bt:
        r = [t['intraday_return'] for t in bt]
        print(f"  {stype}: {len(bt):>3}t  mean={np.mean(r):+.2f}%  win={sum(1 for x in r if x>0)/len(r)*100:.0f}%")

# Score bins
print(f"\nScore分段:")
for lo, hi in [(0,60),(60,70),(70,80),(80,100)]:
    b = [t for t in valid if lo <= t['score'] < hi]
    if b:
        r = [t['intraday_return'] for t in b]
        print(f"  [{lo}-{hi}): {len(b):>3}t  mean={np.mean(r):+.2f}%  win={sum(1 for x in r if x>0)/len(r)*100:.0f}%")

with open('/tmp/cb_1440_backtest.json', 'w') as f:
    json.dump(all_trades, f, ensure_ascii=False, default=str)
print(f"\nSaved")
