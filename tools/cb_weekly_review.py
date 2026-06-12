#!/usr/bin/env python3
"""最近一周选股回测 + 分析 + 改善建议"""
import sys, os, pickle, numpy as np
from collections import defaultdict

_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_PROJ, 'packages', 'kronos-factors'))
sys.path.insert(0, _PROJ)
import psycopg2
from kronos_factors.engine.cb_intraday import CbIntradayEngine
from tools.cb_intraday_exit import *
from tools.cb_backtest_intraday import (load_stock_mins, get_cb_open_and_stock, get_stock_atr_pct)

PG = os.environ.get('KRONOS_PG_URL', 'postgresql://kronos:kronos@localhost:6432/kronos')

def main():
    conn = psycopg2.connect(PG)
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT trade_date FROM cb_daily ORDER BY trade_date DESC LIMIT 7")
    trade_dates = sorted(str(r[0]) for r in cur.fetchall())
    cur.close()

    print(f'回测区间: {trade_dates[0]} ~ {trade_dates[-1]} ({len(trade_dates)}天)')
    print(f'优化: ML≥1.0 | 板块Top10 | 下跌日半仓 | VWAP预警')

    # Pre-fetch market index for down-day detection
    market_map = {}
    cur = conn.cursor()
    for td in trade_dates:
        try:
            cur.execute("SELECT change_pct FROM index_daily WHERE code='000001' AND trade_date=%s", (td,))
            row = cur.fetchone()
            market_map[td] = float(row[0]) if row and row[0] else 0
        except: market_map[td] = 0
    cur.close()

    # Opt 3: filter trades from market-down days
    skipped_ml = 0
    skipped_market = 0

    # Load ensemble
    models = {}
    for name in ['rf','lightgbm','catboost']:
        with open(f'outputs/cb_ml_{name}.pkl','rb') as f:
            models[name] = pickle.load(f)['model']
    def ensemble_predict(X):
        return np.mean([m.predict(X) for m in models.values()], axis=0)

    all_trades = []
    day_stats = defaultdict(lambda: {'returns':[], 'tp':0, 'ts':0, 'kdj':0, 'sl':0, 'close':0})

    for td in trade_dates:
        engine = CbIntradayEngine(pg_url=PG)
        picks = engine.run(trade_date=td, top_n=30)
        engine.close()
        if not picks: continue

        # ML re-rank
        for p in picks:
            d = p.get('details',{})
            X = np.array([[d.get('sector_score',50), d.get('premium_score',50),
                d.get('momentum_score',50), d.get('liquidity_score',50),
                d.get('rev_bonus',0), d.get('call_penalty',0),
                p.get('premium_rate') or 0, p.get('yesterday_pct') or 0,
                p.get('cb_amount_wan') or 0, 0, 0]], dtype=np.float32)
            p['ml_score'] = float(ensemble_predict(X)[0])
        picks.sort(key=lambda x: x.get('ml_score',0), reverse=True)

        # Opt 1: ML score threshold
        picks = [p for p in picks if p.get('ml_score',0) >= 1.0]
        skipped_ml += (30 - len(picks)) if len(picks) < 30 else 0

        # Opt 3: Market down day → halve positions
        mkt = market_map.get(td, 0)
        effective_top_n = 15 if (mkt is None or mkt > -0.5) else max(5, 15 // 2)
        if effective_top_n < 15:
            skipped_market += (15 - effective_top_n)

        picks = picks[:effective_top_n]

        for p in picks:
            try:
                pi = get_cb_open_and_stock(conn, p['code'], p['stk_code'], td)
                cb_open = pi['cb_open']; stock_open = pi['stock_open']
            except:
                try: conn.rollback()
                except: pass
                continue
            if not cb_open or cb_open <= 0: continue

            bars = load_stock_mins(conn, p['stk_code'], td)
            # Opt 4: VWAP early warning — skip if first 6 bars avg < VWAP
            if len(bars) < 10: continue
            if not check_entry_quality(bars, min_bars=6): continue

            atr_pct = get_stock_atr_pct(conn, p['stk_code'], td)
            try: conn.rollback()
            except: pass
            tp_target = adaptive_take_profit_target(atr_pct)

            tp = find_take_profit(bars, cb_open, stock_open or 0, tp_target, 3) if stock_open else None
            ts = find_trailing_stop(bars, 2.0, 6)
            sl = find_stop_loss(bars, 45, 6, 0.5)
            ei = find_exit_info(bars)
            if ei['signal'] and ei['signal']['kdj_j'] <= 95: ei['signal'] = None

            if tp: sig = tp
            elif ts: sig = ts
            elif sl: sig = sl
            else: sig = ei['signal']

            if sig:
                cb_exit = estimate_cb_exit_price(cb_open, stock_open or 0, sig['close'], p.get('premium_rate'))
                ret = (cb_exit - cb_open) / cb_open * 100
                em = sig.get('type','signal')
                if em == 'take_profit': day_stats[td]['tp'] += 1
                elif em == 'trailing_stop': day_stats[td]['ts'] += 1
                elif em == 'stop_loss': day_stats[td]['sl'] += 1
                else: day_stats[td]['kdj'] += 1
            else:
                cur2 = conn.cursor()
                cur2.execute('SELECT close FROM cb_daily WHERE ts_code=%s AND trade_date=%s',(p['code'],td))
                row = cur2.fetchone(); cur2.close()
                cb_exit = float(row[0]) if row and row[0] else cb_open
                ret = (cb_exit - cb_open) / cb_open * 100
                em = 'close'
                day_stats[td]['close'] += 1

            day_stats[td]['returns'].append(ret)
            all_trades.append({
                'date': td, 'code': p['code'], 'name': p.get('name',''),
                'stk_code': p['stk_code'], 'grade': p.get('grade','B'),
                'sector': p.get('sector',''), 'premium_rate': p.get('premium_rate'),
                'ml_score': p.get('ml_score',0), 'yesterday_pct': p.get('yesterday_pct'),
                'cb_amount_wan': p.get('cb_amount_wan'),
                'cb_open': round(cb_open,2), 'cb_exit': round(cb_exit,2),
                'intraday_return': round(ret,2), 'exit_method': em,
                'atr_pct': atr_pct, 'tp_target': tp_target,
                'hold_min': sig['bar_index']*5 if sig else 240,
            })

    conn.close()

    # ── Output ──
    print(f'\n{"="*90}')
    print(f'日度汇总')
    print(f'{"="*90}')
    print(f'{"日期":<12} {"交易":<5} {"止盈":<5} {"回撤":<5} {"KDJ":<5} {"收盘":<5} {"均值":<8} {"胜率":<6}')
    print(f'{"-"*60}')
    for td in trade_dates:
        ds = day_stats[td]
        n = len(ds['returns'])
        if n == 0: continue
        avg = np.mean(ds['returns'])
        win = sum(1 for r in ds['returns'] if r>0) / n * 100
        mkt_str = f' 大盘{market_map.get(td,0):+.1f}%' if market_map.get(td) else ''
        print(f'{td:<12} {n:<5} {ds["tp"]:<5} {ds["ts"]:<5} {ds["kdj"]:<5} {ds["close"]:<5} {avg:+.2f}%   {win:.0f}%{mkt_str}')

    # ── Trade detail ──
    print(f'\n{"="*110}')
    print(f'逐笔交易')
    print(f'{"="*110}')
    for t in sorted(all_trades, key=lambda x: (x['date'], -x['ml_score'])):
        yp = f'{t["yesterday_pct"]:+.1f}' if t['yesterday_pct'] else 'N/A'
        pr = f'{t["premium_rate"]:.1f}' if t['premium_rate'] else 'N/A'
        sec = (t['sector'] or '')[:8]
        print(f'{t["date"]} {t["name"]:<10} {t["stk_code"]:<7} {sec:<8} yp={yp:<6} pr={pr:<6} '
              f'in={t["cb_open"]:<8} out={t["cb_exit"]:<8} ret={t["intraday_return"]:+.2f}% '
              f'{t["exit_method"]:<12} {t["grade"]:<3} ml={t["ml_score"]:.1f}')

    # ── Summary ──
    all_rets = [t['intraday_return'] for t in all_trades]
    print(f'\n{"="*90}')
    print(f'汇总: {len(all_trades)}笔 | mean={np.mean(all_rets):+.2f}% | win={sum(1 for r in all_rets if r>0)/len(all_rets)*100:.0f}%')
    print(f'  过滤: ML阈值={skipped_ml}笔 | 下跌日={skipped_market}笔')
    print(f'  最佳: {max(all_rets):+.2f}% | 最差: {min(all_rets):+.2f}%')

    gs = defaultdict(list)
    for t in all_trades: gs[t['grade']].append(t['intraday_return'])
    for g in ['A','B','C']:
        if g in gs:
            print(f'  {g}级: {len(gs[g])}笔 mean={np.mean(gs[g]):+.2f}% win={sum(1 for r in gs[g] if r>0)/len(gs[g])*100:.0f}%')

    for em, label in [('take_profit','止盈'),('trailing_stop','回撤止损'),('close','收盘')]:
        rets = [t['intraday_return'] for t in all_trades if t['exit_method']==em]
        if rets:
            print(f'  {label}: {len(rets)}笔 mean={np.mean(rets):+.2f}%')

    # ── Improvement suggestions ──
    print(f'\n{"="*90}')
    print(f'改善建议')
    print(f'{"="*90}')

    # Find patterns in losing trades
    losers = [t for t in all_trades if t['intraday_return'] < 0]
    winners = [t for t in all_trades if t['intraday_return'] > 0]

    if losers:
        avg_prem_l = np.mean([abs(t['premium_rate'] or 0) for t in losers])
        avg_prem_w = np.mean([abs(t['premium_rate'] or 0) for t in winners])
        avg_atr_l = np.mean([t['atr_pct'] or 0 for t in losers])
        avg_atr_w = np.mean([t['atr_pct'] or 0 for t in winners])
        avg_ml_l = np.mean([t['ml_score'] for t in losers])
        avg_ml_w = np.mean([t['ml_score'] for t in winners])

        print(f'  亏损交易({len(losers)}笔)特征:')
        print(f'    均溢价率: {avg_prem_l:.1f}% (盈利: {avg_prem_w:.1f}%)')
        print(f'    均ATR: {avg_atr_l:.2f}% (盈利: {avg_atr_w:.2f}%)')
        print(f'    均ML分: {avg_ml_l:.2f} (盈利: {avg_ml_w:.2f})')

        # Sector analysis
        from collections import Counter
        lose_sectors = Counter(t['sector'] for t in losers)
        win_sectors = Counter(t['sector'] for t in winners)
        print(f'  亏损集中板块: {lose_sectors.most_common(3)}')
        print(f'  盈利集中板块: {win_sectors.most_common(3)}')

    # Exit efficiency
    tp_trades = [t for t in all_trades if t['exit_method'] == 'take_profit']
    ts_trades = [t for t in all_trades if t['exit_method'] == 'trailing_stop']
    if tp_trades:
        print(f'  止盈平均持仓: {np.mean([t["hold_min"] for t in tp_trades]):.0f}min')
    if ts_trades:
        print(f'  止损平均持仓: {np.mean([t["hold_min"] for t in ts_trades]):.0f}min')

    print(f'\n  建议:')
    if losers:
        # Check if high premium is killing returns
        if avg_prem_l > avg_prem_w * 1.3:
            print(f'  1. 溢价率过滤: 亏损交易溢价率偏高({avg_prem_l:.1f}% vs {avg_prem_w:.1f}%), 建议溢价>50%不入')
        if avg_atr_l < avg_atr_w * 0.7:
            print(f'  2. ATR下限: 亏损交易波动率偏低({avg_atr_l:.2f}% vs {avg_atr_w:.2f}%), 建议ATR<1.5%不入')
        if avg_ml_l < avg_ml_w * 0.5:
            print(f'  3. ML阈值: 亏损交易ML分偏低({avg_ml_l:.2f} vs {avg_ml_w:.2f}), 建议ML<0.5不入')

if __name__ == '__main__':
    main()
