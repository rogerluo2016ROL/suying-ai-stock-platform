#!/usr/bin/env python3
"""匪爷竞价选债 — 因子权重网格搜索.

基于历史数据的日内开→高收益, 搜索 (w_concept, w_premium, w_gap) 最优组合.
Usage: python tools/grid_search_weights.py --days 5 --top-n 15
"""
import argparse, os, sys, numpy as np
from collections import defaultdict

_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_PROJ, 'packages', 'kronos-factors'))

import psycopg2
from kronos_factors.engine.cb_auction import CbAuctionEngine

PG = os.environ.get('KRONOS_PG_URL', 'postgresql://kronos:kronos@localhost:6432/kronos')


def get_trade_dates(conn, days_back):
    cur = conn.cursor()
    cur.execute(f"""
        SELECT DISTINCT d.trade_date FROM cb_daily d
        WHERE d.trade_date >= CURRENT_DATE - INTERVAL '{days_back} days'
        ORDER BY d.trade_date DESC
    """)
    return [str(r[0]) for r in cur.fetchall()]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--days', type=int, default=10)
    parser.add_argument('--top-n', type=int, default=15)
    args = parser.parse_args()

    conn = psycopg2.connect(PG)
    dates = get_trade_dates(conn, args.days)
    print(f"回测日期: {len(dates)} 天 ({dates[-1]} ~ {dates[0]})")

    # ── 收集所有选股 + 实际收益 ──
    all_candidates = []  # [{date, code, concept_score, premium_score, gap_score, high_ret, close_ret, grade}]

    for td in dates:
        engine = CbAuctionEngine(pg_url=PG)
        picks = engine.run(trade_date=td, top_n=args.top_n)
        engine.close()

        for p in picks:
            cur = conn.cursor()
            cur.execute("SELECT open, high, close FROM cb_daily WHERE ts_code=%s AND trade_date=%s",
                        (p['code'], td))
            row = cur.fetchone(); cur.close(); conn.rollback()
            if not row or not row[0]: continue

            o, h, c = float(row[0]), float(row[1]), float(row[2])
            d = p['details']
            all_candidates.append({
                "date": td, "code": p['code'], "name": p['name'],
                "concept_score": d['concept_score'],
                "premium_score": d['premium_score'],
                "gap_score": d['gap_score'],
                "grade": p['grade'],
                "high_ret": round((h - o) / o * 100, 2),
                "close_ret": round((c - o) / o * 100, 2),
            })

    conn.close()

    if len(all_candidates) < 30:
        print(f"数据不足: {len(all_candidates)} 条, 需要 >=30")
        return

    print(f"候选样本: {len(all_candidates)} 条")

    # ── 网格搜索 ──
    combos = []
    for wc in range(20, 55, 5):
        for wp in range(20, 55, 5):
            wg = 100 - wc - wp
            if 5 <= wg <= 35:
                combos.append((wc / 100.0, wp / 100.0, wg / 100.0))

    print(f"权重组合: {len(combos)} 组")

    best_high = {"mean": -999, "win": 0, "w": None}
    best_close = {"mean": -999, "win": 0, "w": None}
    results = []

    for wc, wp, wg in combos:
        date_scores = defaultdict(list)
        for c in all_candidates:
            new_score = c["concept_score"] * wc + c["premium_score"] * wp + c["gap_score"] * wg
            date_scores[c["date"]].append((new_score, c))

        high_rets, close_rets = [], []
        for td, items in date_scores.items():
            items.sort(key=lambda x: x[0], reverse=True)
            top_k = items[:args.top_n]
            for _, c in top_k:
                high_rets.append(c["high_ret"])
                close_rets.append(c["close_ret"])

        if len(high_rets) >= 20:
            r = {
                "wc": int(wc * 100), "wp": int(wp * 100), "wg": int(wg * 100),
                "high_mean": np.mean(high_rets), "high_win": sum(1 for v in high_rets if v > 0) / len(high_rets) * 100,
                "close_mean": np.mean(close_rets), "close_win": sum(1 for v in close_rets if v > 0) / len(close_rets) * 100,
                "n": len(high_rets),
            }
            results.append(r)

            if r["high_mean"] > best_high["mean"]:
                best_high = {"mean": r["high_mean"], "win": r["high_win"], "w": (wc, wp, wg)}
            if r["close_mean"] > best_close["mean"]:
                best_close = {"mean": r["close_mean"], "win": r["close_win"], "w": (wc, wp, wg)}

    # ── 输出 ──
    results.sort(key=lambda x: x["high_mean"], reverse=True)

    print(f"\n{'='*80}")
    print(f"🏆 最优权重 (卖在最高)")
    print(f"   概念{int(best_high['w'][0]*100)}% 溢价{int(best_high['w'][1]*100)}% 竞价{int(best_high['w'][2]*100)}%")
    print(f"   均值{best_high['mean']:+.2f}% 胜率{best_high['win']:.0f}%")

    print(f"\n🏆 最优权重 (持有到收盘)")
    print(f"   概念{int(best_close['w'][0]*100)}% 溢价{int(best_close['w'][1]*100)}% 竞价{int(best_close['w'][2]*100)}%")
    print(f"   均值{best_close['mean']:+.2f}% 胜率{best_close['win']:.0f}%")

    print(f"\n{'='*80}")
    print(f"Top 10 (按卖最高):")
    print(f"{'概念%':>5} {'溢价%':>5} {'竞价%':>5} {'高均值%':>8} {'高胜率%':>7} {'收均值%':>8} {'收胜率%':>7} {'n':>5}")
    for r in results[:10]:
        print(f"{r['wc']:>5} {r['wp']:>5} {r['wg']:>5} {r['high_mean']:>8.2f} {r['high_win']:>7.0f} {r['close_mean']:>8.2f} {r['close_win']:>7.0f} {r['n']:>5}")

    # 当前权重对比
    current = next((r for r in results if r['wc'] == 40 and r['wp'] == 40 and r['wg'] == 20), None)
    if current:
        print(f"\n当前权重(40/40/20): 高均值{current['high_mean']:+.2f}% 高胜率{current['high_win']:.0f}% 收均值{current['close_mean']:+.2f}%")


if __name__ == '__main__':
    main()
