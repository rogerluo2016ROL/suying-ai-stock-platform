#!/usr/bin/env python3
"""1年期ML回测 — 纯SQL+Python, 绕开引擎"""
import sys, os, pickle, json, numpy as np, psycopg2, time
from collections import defaultdict

PG = os.environ.get('KRONOS_PG_URL', 'postgresql://kronos:kronos@localhost:6432/kronos')

def score_sector(gap, n):
    if gap >= 4: s = 100
    elif gap >= 2: s = 85 + (gap-2)*7.5
    elif gap >= 1: s = 70 + (gap-1)*15
    elif gap >= 0.5: s = 55 + (gap-0.5)*30
    else: s = 40 + gap*30
    return min(100, s + min(10, (n-3)*1.5))

def score_premium(p):
    if p is None: return 50
    if p <= -10: return 100
    elif p <= -5: return 95 + p*0.5
    elif p <= 0: return 85 + p*2
    elif p <= 15: return 85 - p*2.5
    elif p <= 30: return 47.5 - (p-15)*1.5
    elif p <= 60: return 25 - (p-30)*0.7
    return max(5, 4 - p*0.05)

def score_momentum(p):
    if p is None: return 50
    if 1 <= p <= 5: return 80 + (p-1)*5
    elif 0 <= p < 1: return 55 + p*25
    elif 5 < p <= 8: return 80 - (p-5)*5
    elif p > 8: return 50
    elif -1 <= p < 0: return 40 + (p+1)*15
    elif -3 <= p < -1: return 25 + (p+3)*7.5
    return max(5, 20 + p*1.0)

def score_liquidity(amt):
    if amt is None or amt <= 0: return 20
    w = amt / 1e4
    if w >= 5000: return 100
    elif w >= 1000: return 80 + (w-1000)/4000*20
    elif w >= 500: return 65 + (w-500)/500*15
    elif w >= 100: return 40 + (w-100)/400*25
    elif w >= 50: return 20 + (w-50)/50*20
    return max(5, w*0.4)

def main():
    t_total = time.time()

    # Load ML models
    print("Loading ML models...", end=" ", flush=True)
    models = {}
    for name in ['rf','lightgbm','catboost']:
        with open(f'outputs/cb_ml_{name}.pkl','rb') as f:
            models[name] = pickle.load(f)['model']
    print("OK")

    conn = psycopg2.connect(PG)
    cur = conn.cursor()

    cur.execute("SELECT DISTINCT trade_date FROM stk_auction_o WHERE trade_date >= '2025-06-12' ORDER BY trade_date")
    trade_dates = [str(r[0]) for r in cur.fetchall()]
    print(f"Trading days: {len(trade_dates)}")

    # Pre-fetch all daily data
    print("Loading daily data...", end=" ", flush=True)
    cur.execute("""
        SELECT d.ts_code, d.trade_date, d.open, d.close, d.cb_over_rate, d.amount,
               k.change_pct as stock_pct
        FROM cb_daily d
        LEFT JOIN daily_kline k ON SPLIT_PART(d.ts_code,'.',1)=k.code AND k.trade_date=d.trade_date
        WHERE d.trade_date >= '2025-06-12'
    """)
    daily_data = {}
    for r in cur.fetchall():
        daily_data[(r[0], str(r[1]))] = {
            'open': r[2], 'close': r[3], 'premium': r[4], 'amount': r[5], 'stock_pct': r[6]}
    print(f"{len(daily_data)} records")

    # Sector strength per date
    print("Loading sector data...", end=" ", flush=True)
    cur.execute("""
        SELECT ao.trade_date, s.industry,
               AVG((ao.open-ao.close)/NULLIF(ao.close,0)*100), COUNT(*)
        FROM stk_auction_o ao JOIN stocks s ON ao.code=s.code
        WHERE ao.trade_date>='2025-06-12' AND ao.open>0 AND ao.close>0
          AND s.industry IS NOT NULL AND s.name NOT LIKE '%%ST%%'
        GROUP BY ao.trade_date, s.industry HAVING COUNT(*)>=3
    """)
    sector_strength = defaultdict(dict)
    for r in cur.fetchall():
        sector_strength[str(r[0])][r[1]] = {'gap': float(r[2]), 'n': r[3]}
    print(f"{len(sector_strength)} dates")

    # CB basic info
    cur.execute("SELECT ts_code, bond_short_name, stk_code, conv_price FROM cb_basic")
    cb_info = {}
    for r in cur.fetchall():
        cb_info[r[0]] = {'name': r[1], 'stk_code': r[2].split('.')[0] if r[2] and '.' in str(r[2]) else str(r[2] or ''), 'conv_price': r[3]}

    # Concept→CB mapping
    cur.execute("SELECT ts_code, concept FROM cb_concept")
    cb_concepts = defaultdict(set)
    for r in cur.fetchall():
        cb_concepts[r[0]].add(r[1])

    # Concept→Industry mapping
    cur.execute("""
        SELECT DISTINCT cc.concept, s.industry FROM cb_concept cc
        JOIN cb_basic cb ON cc.ts_code=cb.ts_code
        JOIN stocks s ON SPLIT_PART(cb.stk_code,'.',1)=s.code
    """)
    concept_to_industry = defaultdict(set)
    for r in cur.fetchall():
        concept_to_industry[r[0]].add(r[1])

    # Yesterday stock pct
    print("Loading yesterday data...", end=" ", flush=True)
    cur.execute("SELECT code, trade_date, change_pct FROM daily_kline WHERE trade_date>='2025-06-11'")
    ypct_raw = defaultdict(list)
    for r in cur.fetchall():
        ypct_raw[r[0]].append((str(r[1]), r[2]))
    yesterday_pct = {}
    for code, rows in ypct_raw.items():
        for i, (td, pct) in enumerate(rows):
            if i+1 < len(rows) and rows[i+1][1] is not None:
                yesterday_pct[(code, td)] = rows[i+1][1]
    print(f"{len(yesterday_pct)} records")

    conn.close()
    print(f"Data loaded in {time.time()-t_total:.0f}s\n")

    # ── Backtest loop ──
    all_picks = []
    t0 = time.time()
    for ti, td in enumerate(trade_dates):
        if ti % 50 == 0:
            print(f"  {ti}/{len(trade_dates)} {td} ({len(all_picks)}p, {time.time()-t0:.0f}s)", flush=True)

        sectors = sector_strength.get(td, {})
        if not sectors: continue

        top_sectors = sorted(sectors.items(),
            key=lambda x: score_sector(x[1]['gap'], x[1]['n']), reverse=True)[:10]
        strong_industries = {ind for ind, _ in top_sectors}
        sector_score_map = {ind: score_sector(info['gap'], info['n']) for ind, info in top_sectors}

        # Find CBs in strong industries
        strong_concepts = set()
        for ind in strong_industries:
            for concept, industries in concept_to_industry.items():
                if ind in industries:
                    strong_concepts.add(concept)

        if strong_concepts:
            candidates = set()
            sector_scores = {}
            for concept in strong_concepts:
                for cb_code in cb_concepts:
                    if concept in cb_concepts[cb_code]:
                        candidates.add(cb_code)
                        for ind in concept_to_industry.get(concept, set()):
                            if ind in sector_score_map:
                                sector_scores[cb_code] = max(sector_scores.get(cb_code, 0), sector_score_map[ind])
            candidates = list(candidates)
        else:
            candidates = list(cb_info.keys())
            sector_scores = {c: 50 for c in candidates}

        # Supplement with all CBs if too few
        if len(candidates) < 10:
            for c in cb_info:
                if c not in candidates:
                    candidates.append(c)
                    sector_scores[c] = 50
                    if len(candidates) >= 50: break

        # Score + ML re-rank
        scored = []
        for cb_code in candidates[:80]:
            info = cb_info.get(cb_code, {})
            dd = daily_data.get((cb_code, td), {})
            premium = dd.get('premium')
            amount = dd.get('amount')
            stk = info.get('stk_code', '')
            ypct = yesterday_pct.get((stk, td))

            sect = sector_scores.get(cb_code, 50)
            prem = score_premium(premium)
            mom = score_momentum(ypct)
            liq = score_liquidity(amount)
            total = sect*0.20 + prem*0.15 + mom*0.30 + liq*0.35

            scored.append({
                'code': cb_code, 'name': info.get('name', cb_code),
                'stk_code': stk, 'premium_rate': premium,
                'yesterday_pct': ypct, 'cb_amount_wan': round(amount/1e4, 0) if amount else None,
                'sector_score': sect, 'premium_score': prem,
                'momentum_score': mom, 'liquidity_score': liq,
                'total_score': round(total, 1),
                'grade': 'A' if total >= 60 else ('B' if total >= 45 else 'C'),
            })

        if not scored: continue

        # ML re-rank
        for p in scored:
            X = np.array([[p['sector_score'], p['premium_score'], p['momentum_score'],
                          p['liquidity_score'], 0, 0, p['premium_rate'] or 0,
                          p['yesterday_pct'] or 0, p['cb_amount_wan'] or 0, 0, 0]], dtype=np.float32)
            p['ml_score'] = float(np.mean([m.predict(X)[0] for m in models.values()]))

        scored = [p for p in scored if p['ml_score'] >= 1.0]
        scored.sort(key=lambda x: x['ml_score'], reverse=True)

        for p in scored[:10]:
            dd = daily_data.get((p['code'], td), {})
            o, c = dd.get('open'), dd.get('close')
            ret = (c - o) / o * 100 if o and c and o > 0 else None
            all_picks.append({**p, 'date': td, 'intraday_return': round(ret, 2) if ret else None})

    # ── Results ──
    elapsed = time.time() - t0
    valid = [p for p in all_picks if p['intraday_return'] is not None]
    rets = [p['intraday_return'] for p in valid]
    days = len(set(p['date'] for p in all_picks))

    print(f"\n{'='*60}")
    print(f"完成: {len(all_picks)} picks, {len(valid)} valid, {days} days ({elapsed:.0f}s)")
    print(f"Mean: {np.mean(rets):+.2f}%  Win: {sum(1 for r in rets if r>0)/len(rets)*100:.1f}%")
    print(f"Best: {max(rets):+.2f}%  Worst: {min(rets):+.2f}%")

    with open('/tmp/cb_picks_1year.json', 'w') as f:
        json.dump(all_picks, f, ensure_ascii=False, default=str)
    print("Saved /tmp/cb_picks_1year.json")

if __name__ == '__main__':
    main()
