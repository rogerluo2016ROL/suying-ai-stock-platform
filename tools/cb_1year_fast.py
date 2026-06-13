#!/usr/bin/env python3
"""1年期ML回测 — 单引擎实例复用, 内存优化"""
import sys, os, json, time, pickle
import numpy as np
import psycopg2

_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_PROJ, 'packages', 'kronos-factors'))
sys.path.insert(0, _PROJ)
from kronos_factors.engine.cb_intraday import CbIntradayEngine

PG = os.environ.get('KRONOS_PG_URL', 'postgresql://kronos:kronos@localhost:6432/kronos')

t_total = time.time()

# ── Pre-load ML models ──
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

# ── Get trading days ──
conn = psycopg2.connect(PG)
cur = conn.cursor()
cur.execute("SELECT DISTINCT trade_date FROM stk_auction_o WHERE trade_date >= '2025-06-12' ORDER BY trade_date")
trade_dates = [str(r[0]) for r in cur.fetchall()]

# Pre-fetch cb_daily for returns
cur.execute("SELECT ts_code, trade_date, open, close FROM cb_daily WHERE trade_date >= '2025-06-12'")
cb_ohlc = {}
for r in cur.fetchall():
    cb_ohlc[(r[0], str(r[1]))] = (r[2], r[3])
conn.close()

print(f"Dates: {len(trade_dates)}, cb_daily: {len(cb_ohlc)} records")

# ── Main loop (reuse engine) ──
engine = CbIntradayEngine(pg_url=PG)
all_picks = []
errors = 0
t0 = time.time()

for ti, td in enumerate(trade_dates):
    if ti % 25 == 0:
        elapsed = time.time() - t0
        eta = elapsed / max(ti, 1) * (len(trade_dates) - ti)
        print(f"  {ti}/{len(trade_dates)} {td} ({len(all_picks)}p, {elapsed:.0f}s, ETA {eta:.0f}s)", flush=True)

    try:
        picks = engine.run(trade_date=td, top_n=30, use_ml=False)
        if not picks: continue

        for p in picks:
            d = p.get('details', {})
            p['_ml'] = ml_score(d, p.get('premium_rate'), p.get('yesterday_pct'), p.get('cb_amount_wan'))

        picks = [p for p in picks if p.get('_ml', 0) >= 2.0]
        picks.sort(key=lambda x: x.get('_ml', 0), reverse=True)
        picks = picks[:10]

        for p in picks:
            o, c = cb_ohlc.get((p['code'], td), (None, None))
            ret = (c - o) / o * 100 if o and c and o > 0 else None
            d = p.get('details', {})
            all_picks.append({
                'date': td, 'code': p['code'], 'name': p.get('name', ''),
                'stk_code': p.get('stk_code', ''), 'grade': p.get('grade', 'B'),
                'sector': p.get('sector', ''), 'premium_rate': p.get('premium_rate'),
                'yesterday_pct': p.get('yesterday_pct'), 'cb_amount_wan': p.get('cb_amount_wan'),
                'ml_score': round(p['_ml'], 2), 'total_score': p.get('total_score', 0),
                'intraday_return': round(ret, 2) if ret else None,
                'sector_score': d.get('sector_score', 50), 'premium_score': d.get('premium_score', 50),
                'momentum_score': d.get('momentum_score', 50), 'liquidity_score': d.get('liquidity_score', 50),
                'rev_bonus': d.get('rev_bonus', 0),
            })
    except Exception as e:
        errors += 1
        if errors <= 3: print(f"  E@{td}: {e}", flush=True)
        try: engine.close()
        except: pass
        engine = CbIntradayEngine(pg_url=PG)  # reconnect
        continue

engine.close()

# ── Results ──
valid = [p for p in all_picks if p['intraday_return'] is not None]
rets = [p['intraday_return'] for p in valid]
elapsed = time.time() - t0

print(f"\nDone: {len(all_picks)}p, {len(valid)} valid, {len(set(p['date'] for p in all_picks))} days, {elapsed:.0f}s")
print(f"Mean: {np.mean(rets):+.2f}%  Win: {sum(1 for r in rets if r>0)/len(rets)*100:.1f}%  Err: {errors}")

with open('/tmp/cb_picks_1year.json', 'w') as f:
    json.dump(all_picks, f, ensure_ascii=False, default=str)
print("Saved /tmp/cb_picks_1year.json")
