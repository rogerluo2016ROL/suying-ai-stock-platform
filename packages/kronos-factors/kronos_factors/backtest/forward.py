#!/usr/bin/env python3
"""Forward backtest: rolling-window screening → validate future returns.

Eliminates hindsight bias by simulating what would have happened if we
ran the screening on historical dates and held the picks forward.

Usage:
    cd Kronos && python tools/forward_backtest.py --mode all --window 3
"""

import argparse, json, os, sys, time
from datetime import datetime, timedelta
from collections import defaultdict

import numpy as np
import pandas as pd

from kronos_factors.scorer._db_stub import _get_db, _get_market_data


def run_backtest(mode="all", windows=3, top_n=30, forward_days=60):
    """Rolling window forward backtest.

    For each window:
    1. Use K-line data up to `cutoff_date` to score stocks
    2. Select top_n picks
    3. Check actual returns from cutoff_date to cutoff_date + forward_days
    """
    with _get_db(readonly=True) as db:
        # Get available date range
        max_date = db.execute("SELECT MAX(trade_date) FROM daily_kline").fetchone()[0]
        min_date = db.execute("SELECT MIN(trade_date) FROM daily_kline WHERE code LIKE '000%' OR code LIKE '600%'").fetchone()[0]

    max_dt = datetime.strptime(max_date, "%Y-%m-%d")
    # Use recent 2 years for meaningful backtest windows
    min_dt = max(datetime.strptime("2024-01-01", "%Y-%m-%d"),
                 datetime.strptime(min_date, "%Y-%m-%d"))
    available_months = (max_dt.year - min_dt.year) * 12 + (max_dt.month - min_dt.month)
    step = max(2, available_months // (windows + 1))
    print(f"数据范围: {min_date} ~ {max_date} ({available_months} 月)")
    print(f"回测窗口: {windows} 个, 每步间隔 ~{step} 月")
    print(f"前向验证周期: {forward_days} 天\n")

    results_summary = []
    current = max_dt - timedelta(days=forward_days + 30)

    for w in range(windows):
        cutoff = current - timedelta(days=w * step * 30)
        cutoff_str = cutoff.strftime("%Y-%m-%d")
        future_str = (cutoff + timedelta(days=forward_days)).strftime("%Y-%m-%d")

        print(f"{'='*50}")
        print(f"  Window {w+1}/{windows}: 选股日={cutoff_str} → 验证日={future_str}")
        print(f"{'='*50}")

        # P1: Use full screening engine instead of simplified scoring
        # P1: Use full screening engine (all stocks, multi-factor, ICIR-weighted)
        from kronos_factors.scorer.screening_scorers import run_screening
        print(f"  Running full screening engine (SHORT mode, P0+P1 ICIR-weighted)...")
        try:
            result = run_screening(mode="short", top_n=top_n * 5, method="linear")
            all_scores = result.get('all_scores', []) if isinstance(result, dict) else result
            if not all_scores and isinstance(result, list):
                all_scores = result
            print(f"  Engine returned {len(all_scores)} picks")
        except Exception as e:
            print(f"  ⚠️ Full engine failed ({e}), falling back to simplified")
            all_scores = []

        picks = []
        for s in all_scores:
            if len(picks) >= top_n * 3:
                break
            code = s['code']
            try:
                df = _get_market_data().get_kline_df(code, lookback=400)
                if df is None or len(df) < 60:
                    continue
                ts_col = 'timestamps' if 'timestamps' in df.columns else 'trade_date'
                df_future = df[df[ts_col] > cutoff_str]
                if len(df_future) < 20:
                    continue

                # Always use K-line at cutoff (engine gives current price, not historical)
                df_hist = df[df[ts_col] <= cutoff_str].copy()
                if len(df_hist) < 60:
                    continue
                price_at_cutoff = float(df_hist['close'].values[-1])

                future_closes = df_future['close'].values
                forward_ret = (future_closes[-1] / price_at_cutoff - 1) * 100
                fwd_days_actual = len(future_closes)

                picks.append({
                    'code': code, 'price': round(price_at_cutoff, 2),
                    'score': round(s.get('score', 0), 1),
                    'forward_ret': round(forward_ret, 1),
                    'fwd_days': fwd_days_actual,
                    'grade': s.get('grade', '?'),
                })
            except:
                pass

        picks.sort(key=lambda x: -x['score'])
        top = picks[:top_n]

        if not top:
            print("  ❌ No picks found")
            continue

        fwd_rets = [p['forward_ret'] for p in top]
        hits = sum(1 for r in fwd_rets if r > 0)
        avg_ret = np.mean(fwd_rets)
        median_ret = np.median(fwd_rets)

        print(f"  Top {top_n}: 均值收益 {avg_ret:+.1f}%  中位数 {median_ret:+.1f}%  胜率 {hits}/{len(top)} ({hits/len(top)*100:.0f}%)")
        print(f"  最佳: {top[0]['code']} {top[0]['forward_ret']:+.1f}%  最差: {top[-1]['code']} {top[-1]['forward_ret']:+.1f}%")

        # IC analysis
        scores = np.array([p['score'] for p in top])
        if np.std(scores) > 0 and np.std(fwd_rets) > 0:
            ic = np.corrcoef(scores, fwd_rets)[0, 1]
            print(f"  IC: {ic:+.4f}")

        results_summary.append({
            'window': w+1, 'cutoff': cutoff_str, 'future': future_str,
            'avg_ret': round(avg_ret, 1), 'median_ret': round(median_ret, 1),
            'hit_rate': round(hits/len(top)*100, 1),
            'top5_avg': round(np.mean(fwd_rets[:5]), 1),
            'worst': round(min(fwd_rets), 1)
        })

    # Summary
    print(f"\n{'='*60}")
    print(f"  前向回测总结 ({mode}模式)")
    print(f"{'='*60}")
    print(f"{'Window':<8} {'日期':<14} {'均值':>8} {'中位数':>8} {'胜率':>7} {'Top5均值':>9}")
    print(f"{'-'*55}")
    for r in results_summary:
        print(f"  {r['window']:<6} {r['cutoff']:<14} {r['avg_ret']:>+7.1f}% {r['median_ret']:>+7.1f}% {r['hit_rate']:>6.1f}% {r['top5_avg']:>+8.1f}%")

    if results_summary:
        avg_across = np.mean([r['avg_ret'] for r in results_summary])
        avg_hit = np.mean([r['hit_rate'] for r in results_summary])
        print(f"\n  跨窗口平均: 收益 {avg_across:+.1f}%  胜率 {avg_hit:.0f}%")
        if avg_hit > 55:
            print(f"  ✅ 模型有正向预测能力")
        else:
            print(f"  ⚠️ 模型预测能力待验证（胜率≈50%为随机）")

    out_path = f"outputs/forward_backtest_{mode}_{datetime.now().strftime('%Y%m%d-%H%M')}.json"
    with open(out_path, 'w') as f:
        json.dump(results_summary, f, ensure_ascii=False, indent=2)
    print(f"\nSaved: {out_path}")
    return results_summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Forward backtest")
    parser.add_argument("--mode", default="all", choices=["short","long","all","simple"])
    parser.add_argument("--windows", type=int, default=3, help="Number of rolling windows")
    parser.add_argument("--top-n", type=int, default=30)
    parser.add_argument("--forward-days", type=int, default=60)
    args = parser.parse_args()
    os.chdir(_PROJ)
    run_backtest(mode=args.mode, windows=args.windows, top_n=args.top_n, forward_days=args.forward_days)
