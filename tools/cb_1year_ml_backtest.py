#!/usr/bin/env python3
"""1年期完整回测 — 引擎选股 + ML重排 + 日内收益, 严格按照CbIntradayEngine V5模型"""
import sys, os, json, time
import numpy as np
import psycopg2

_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_PROJ, 'packages', 'kronos-factors'))
sys.path.insert(0, _PROJ)

from kronos_factors.engine.cb_intraday import CbIntradayEngine
import pickle

PG = os.environ.get('KRONOS_PG_URL', 'postgresql://kronos:kronos@localhost:6432/kronos')

def main():
    t_total = time.time()

    # ── Pre-load ML models (outside engine, for re-rank) ──
    print("Loading Ensemble models...", end=" ", flush=True)
    ml_models = {}
    for name in ['rf', 'lightgbm', 'catboost']:
        with open(os.path.join(_PROJ, 'outputs', f'cb_ml_{name}.pkl'), 'rb') as f:
            ml_models[name] = pickle.load(f)['model']
    print(f"OK ({time.time()-t_total:.1f}s)")

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
    print(f"Trading days: {len(trade_dates)}")

    # Pre-fetch cb_daily for return calculation
    cur.execute("SELECT ts_code, trade_date, open, close FROM cb_daily WHERE trade_date >= '2025-06-12'")
    cb_ohlc = {}
    for r in cur.fetchall():
        cb_ohlc[(r[0], str(r[1]))] = (r[2], r[3])
    conn.close()

    # ── Main loop ──
    all_picks = []
    errors = 0
    t0 = time.time()

    for ti, td in enumerate(trade_dates):
        if ti % 20 == 0:
            print(f"  {ti}/{len(trade_dates)} {td} ({len(all_picks)}p, {time.time()-t0:.0f}s, {errors}e)", flush=True)

        try:
            # Step 1: Engine picks (linear scoring, no internal ML)
            engine = CbIntradayEngine(pg_url=PG)
            picks = engine.run(trade_date=td, top_n=30, use_ml=False)
            engine.close()
            if not picks:
                continue

            # Step 2: ML re-rank + threshold
            for p in picks:
                d = p.get('details', {})
                p['ml_score'] = ml_score(d, p.get('premium_rate'), p.get('yesterday_pct'), p.get('cb_amount_wan'))

            picks = [p for p in picks if p.get('ml_score', 0) >= 1.0]
            picks.sort(key=lambda x: x.get('ml_score', 0), reverse=True)
            picks = picks[:10]

            # Step 3: Calculate intraday returns
            for p in picks:
                ohlc = cb_ohlc.get((p['code'], td), (None, None))
                cb_open, cb_close = ohlc
                ret = (cb_close - cb_open) / cb_open * 100 if cb_open and cb_close and cb_open > 0 else None

                all_picks.append({
                    'date': td, 'code': p['code'], 'name': p.get('name', ''),
                    'stk_code': p.get('stk_code', ''), 'grade': p.get('grade', 'B'),
                    'sector': p.get('sector', ''), 'premium_rate': p.get('premium_rate'),
                    'yesterday_pct': p.get('yesterday_pct'), 'cb_amount_wan': p.get('cb_amount_wan'),
                    'ml_score': p['ml_score'], 'total_score': p.get('total_score', 0),
                    'intraday_return': round(ret, 2) if ret else None,
                    **{f'{k}_score': v for k, v in p.get('details', {}).items()},
                })
        except Exception as e:
            errors += 1
            if errors <= 3:
                print(f"  Error {td}: {e}", flush=True)
            continue

    # ── Results ──
    elapsed = time.time() - t0
    valid = [p for p in all_picks if p['intraday_return'] is not None]
    rets = [p['intraday_return'] for p in valid]

    print(f"\n{'='*60}")
    print(f"完成: {len(all_picks)} picks, {len(valid)} valid, {len(valid)//10} days")
    print(f"Mean intraday: {np.mean(rets):+.2f}%  Win: {sum(1 for r in rets if r>0)/len(rets)*100:.1f}%")
    print(f"Best: {max(rets):+.2f}%  Worst: {min(rets):+.2f}%  Errors: {errors}")
    print(f"Total time: {elapsed:.0f}s")

    with open('/tmp/cb_picks_1year.json', 'w') as f:
        json.dump(all_picks, f, ensure_ascii=False, default=str)

if __name__ == '__main__':
    main()
