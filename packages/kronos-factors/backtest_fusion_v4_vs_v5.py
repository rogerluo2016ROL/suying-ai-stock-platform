#!/usr/bin/env python3
"""Backtest V4.0 merge_picks vs V5.0 WeightedFusionEngine on June 2026.

Compares consensus fusion quality between two versions:
  - V4.0: simple count-based voting (merge_picks)
  - V5.0: dynamic weighted fusion + sector heatmap

Usage:
    cd packages/kronos-factors && python3 backtest_fusion_v4_vs_v5.py
    cd packages/kronos-factors && python3 backtest_fusion_v4_vs_v5.py --end 2026-06-26
"""
import argparse
import logging
import os
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import psycopg2

_PACKAGES = str(Path(__file__).parent)
if _PACKAGES not in sys.path:
    sys.path.insert(0, _PACKAGES)

_PG_URL = os.environ.get("KRONOS_PG_URL", "postgresql://kronos:kronos@localhost:6432/kronos")
os.environ.setdefault("KRONOS_PG_URL", _PG_URL)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# ── Engine imports ──
from kronos_factors.engine.leader_scalp import LeaderScalpEngine
from kronos_factors.engine.bi_trend_launch import BiTrendLaunchEngine
from kronos_factors.engine.modes import ShortModeEngine
from kronos_factors.engine.supply_chain import SupplyChainEngine

# ── V5.0 imports ──
from kronos_factors.engine.weighted_fusion import WeightedFusionEngine
from kronos_factors.engine.sector_heatmap import SectorHeatmapEngine

# ── Engines to run ──
ENGINES = [
    ("leader_scalp",    LeaderScalpEngine,     "龙头短线"),
    ("bi_trend_launch", BiTrendLaunchEngine,   "毕师傅趋势"),
    ("short",           ShortModeEngine,       "多因子"),
    ("supply_chain",    SupplyChainEngine,     "产业链共振"),
]


def get_db(pg_url: str = None):
    url = pg_url or _PG_URL
    return psycopg2.connect(url)


def get_trading_days(pg_url: str, start: str, end: str) -> List[str]:
    conn = get_db(pg_url)
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT DISTINCT trade_date::text FROM daily_kline
            WHERE trade_date >= %s AND trade_date <= %s ORDER BY trade_date
        """, (start, end))
        return [r[0] for r in cur.fetchall()]
    finally:
        conn.close()


def detect_market_env(pg_url: str, trade_date: str) -> str:
    """Auto-detect market environment from breadth and change."""
    conn = get_db(pg_url)
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT
                COUNT(*) FILTER (WHERE change_pct > 0)::float / NULLIF(COUNT(*), 0) AS breadth,
                AVG(change_pct) AS avg_change
            FROM daily_kline WHERE trade_date = %s
        """, (trade_date,))
        row = cur.fetchone()
        breadth = float(row[0]) if row and row[0] else 0.5
        avg_change = float(row[1]) if row and row[1] else 0

        if breadth >= 0.55 and avg_change > 1.0:
            return "bull"
        elif breadth < 0.35 or avg_change < -2.0:
            return "bear"
        else:
            return "neutral"
    finally:
        conn.close()


def get_future_returns(pg_url: str, trade_date: str, codes: list[str], horizon: int) -> dict:
    """Calculate forward returns. Returns dict[code, pct_return]."""
    if not codes:
        return {}

    conn = get_db(pg_url)
    try:
        cur = conn.cursor()
        placeholders = ",".join(["%s"] * len(codes))

        cur.execute(f"""
            SELECT code, close FROM daily_kline
            WHERE code IN ({placeholders}) AND trade_date = %s
        """, codes + [trade_date])
        entry_prices = {r[0]: float(r[1]) for r in cur.fetchall() if r[1] is not None}

        if not entry_prices:
            return {}

        target_date = (datetime.strptime(trade_date, '%Y-%m-%d') + timedelta(days=horizon)).strftime('%Y-%m-%d')
        cur.execute("""
            SELECT MAX(trade_date::text) FROM daily_kline
            WHERE trade_date >= %s AND trade_date <= %s
        """, (target_date, (datetime.strptime(target_date, '%Y-%m-%d') + timedelta(days=10)).strftime('%Y-%m-%d')))
        row = cur.fetchone()
        if not row or not row[0]:
            # Fallback to last available
            cur.execute("SELECT MAX(trade_date::text) FROM daily_kline")
            row = cur.fetchone()
        if not row or not row[0]:
            return {}
        exit_date = row[0]
        if exit_date == trade_date:
            return {}

        cur.execute(f"""
            SELECT code, close FROM daily_kline
            WHERE code IN ({placeholders}) AND trade_date = %s
        """, codes + [exit_date])
        exit_prices = {r[0]: float(r[1]) for r in cur.fetchall() if r[1] is not None}

        returns = {}
        for code in codes:
            entry = entry_prices.get(code)
            exit_p = exit_prices.get(code)
            if entry and entry > 0 and exit_p is not None:
                returns[code] = (exit_p - entry) / entry * 100
        return returns
    finally:
        conn.close()


# ── V4.0 merge_picks (replicated from orchestrator) ──
def merge_picks_v4(strategy_results: dict, top_n: int = 30) -> list[dict]:
    """V4.0 simple consensus: count-based voting with fixed boosts."""
    stock_scores = defaultdict(lambda: {"score": 0, "count": 0, "strategies": [], "data": {}})

    for mode, picks in strategy_results.items():
        if not picks or not isinstance(picks, list):
            continue
        for p in picks:
            code = p.get("code", "")
            if not code:
                continue
            s = stock_scores[code]
            s["count"] += 1
            s["strategies"].append(mode)
            p_score = p.get("total_score", p.get("score", 50))
            if p_score > s["score"]:
                s["score"] = p_score
                s["data"] = p
            boost = 10 if mode == "leader_scalp" else 5
            s["score"] += boost

    ranked = sorted(stock_scores.items(),
                    key=lambda x: (x[1]["count"], x[1]["score"]), reverse=True)

    result = []
    for code, info in ranked[:top_n]:
        entry = {**info["data"], "consensus_count": info["count"],
                 "consensus_strategies": info["strategies"]}
        result.append(entry)
    return result


# ── V5.0 fusion ──
_fusion_engine = None
_heatmap_engine = None


def get_fusion_v5():
    global _fusion_engine
    if _fusion_engine is None:
        _fusion_engine = WeightedFusionEngine()
    return _fusion_engine


def get_heatmap():
    global _heatmap_engine
    if _heatmap_engine is None:
        _heatmap_engine = SectorHeatmapEngine()
    return _heatmap_engine


def merge_picks_v5(strategy_results: dict, trade_date: str, market_env: str, top_n: int = 30) -> tuple:
    """V5.0 weighted fusion + sector heatmap."""
    hot_sectors = None
    try:
        hm = get_heatmap()
        hot_sectors = hm.get_hot_sectors(trade_date, min_hit_rate=0.6)
    except Exception as e:
        logger.debug("Sector heatmap skipped: %s", e)

    try:
        fe = get_fusion_v5()
        result = fe.run(
            strategy_results=strategy_results,
            market_env=market_env,
            hot_sectors=hot_sectors,
            top_n=top_n,
        )
        return result.picks
    except Exception as e:
        logger.warning("V5.0 fusion failed: %s, falling back to V4.0", e)
        return merge_picks_v4(strategy_results, top_n)


def run_engine(engine_cls, top_n: int, trade_date: str) -> list[dict]:
    """Run one engine and normalize to list[dict]."""
    engine = engine_cls()
    result = engine.run(top_n=top_n, trade_date=trade_date)
    if isinstance(result, list):
        return result
    if hasattr(result, 'picks'):
        return result.picks
    if hasattr(result, 'results'):
        return result.results
    if isinstance(result, dict) and 'picks' in result:
        return result['picks']
    return []


def backtest_one_day(pg_url: str, trade_date: str, top_n: int) -> dict:
    """Run engines → fuse V4 + V5 → compute returns."""
    t0 = time.time()

    # Step 1: Run all engines in parallel
    strategy_results = {}
    with ThreadPoolExecutor(max_workers=len(ENGINES)) as pool:
        futures = {
            pool.submit(run_engine, cls, top_n, trade_date): mode
            for mode, cls, desc in ENGINES
        }
        for f in futures:
            mode = futures[f]
            try:
                strategy_results[mode] = f.result()
            except Exception as e:
                logger.warning("  %s failed: %s", mode, e)
                strategy_results[mode] = []

    # Step 2: Detect market environment
    market_env = detect_market_env(pg_url, trade_date)

    # Step 3: V4.0 fusion
    consensus_v4 = merge_picks_v4(strategy_results, top_n)

    # Step 4: V5.0 fusion
    consensus_v5 = merge_picks_v5(strategy_results, trade_date, market_env, top_n)

    # Step 5: Compute forward returns
    codes_v4 = [p.get("code", "") for p in consensus_v4 if p.get("code")]
    codes_v5 = [p.get("code", "") for p in consensus_v5 if p.get("code")]

    ret_v4_5d = get_future_returns(pg_url, trade_date, codes_v4, 5)
    ret_v4_10d = get_future_returns(pg_url, trade_date, codes_v4, 10)
    ret_v4_20d = get_future_returns(pg_url, trade_date, codes_v4, 20)

    ret_v5_5d = get_future_returns(pg_url, trade_date, codes_v5, 5)
    ret_v5_10d = get_future_returns(pg_url, trade_date, codes_v5, 10)
    ret_v5_20d = get_future_returns(pg_url, trade_date, codes_v5, 20)

    elapsed = time.time() - t0
    logger.info("  Day %s: env=%s, V4=%d picks, V5=%d picks (%.1fs)",
                trade_date, market_env, len(codes_v4), len(codes_v5), elapsed)

    return {
        "trade_date": trade_date,
        "market_env": market_env,
        "v4": {"n_picks": len(codes_v4), "returns_5d": ret_v4_5d,
               "returns_10d": ret_v4_10d, "returns_20d": ret_v4_20d},
        "v5": {"n_picks": len(codes_v5), "returns_5d": ret_v5_5d,
               "returns_10d": ret_v5_10d, "returns_20d": ret_v5_20d},
    }


def aggregate(day_results: list[dict], label: str) -> dict:
    """Aggregate returns across all days."""
    all_5d, all_10d, all_20d = [], [], []
    n_picks_total, days_with_picks = 0, 0

    for r in day_results:
        data = r[label]
        if data["n_picks"] == 0:
            continue
        days_with_picks += 1
        n_picks_total += data["n_picks"]
        for v in data["returns_5d"].values():
            if v is not None:
                all_5d.append(v)
        for v in data["returns_10d"].values():
            if v is not None:
                all_10d.append(v)
        for v in data["returns_20d"].values():
            if v is not None:
                all_20d.append(v)

    def stats(vals):
        if not vals:
            return {"mean": 0, "median": 0, "wr": 0, "std": 0, "n": 0}
        return {
            "mean": float(np.mean(vals)),
            "median": float(np.median(vals)),
            "wr": sum(1 for v in vals if v > 0) / len(vals),
            "std": float(np.std(vals)),
            "n": len(vals),
        }

    return {
        "days_with_picks": days_with_picks,
        "n_picks_total": n_picks_total,
        "5d": stats(all_5d),
        "10d": stats(all_10d),
        "20d": stats(all_20d),
    }


def print_comparison(v4_stats: dict, v5_stats: dict):
    """Print side-by-side comparison table."""
    header = (
        f"{'指标':<16} {'V4.0 简单投票':>16} {'V5.0 加权融合':>16} {'提升':>10}"
    )
    print("\n" + "=" * len(header))
    print("  V4.0 vs V5.0 融合层回测对比 (2026年6月)")
    print("=" * len(header))
    print(header)
    print("-" * len(header))

    for horizon, h_label in [("5d", "5日"), ("10d", "10日"), ("20d", "20日")]:
        v4 = v4_stats[horizon]
        v5 = v5_stats[horizon]
        delta_mean = v5["mean"] - v4["mean"]
        delta_median = v5["median"] - v4["median"]
        delta_wr = v5["wr"] - v4["wr"]

        print(f"\n  ── {h_label}收益 ──")
        print(f"  {'平均收益':<14} {v4['mean']:>+15.2f}% {v5['mean']:>+15.2f}% {delta_mean:>+9.2f}pp")
        print(f"  {'中位收益':<14} {v4['median']:>+15.2f}% {v5['median']:>+15.2f}% {delta_median:>+9.2f}pp")
        print(f"  {'胜率':<14} {v4['wr']:>15.1%} {v5['wr']:>15.1%} {delta_wr:>+9.1%}")
        print(f"  {'波动率':<14} {v4['std']:>15.2f} {v5['std']:>15.2f} {'':>10}")
        print(f"  {'样本数':<14} {v4['n']:>15d} {v5['n']:>15d} {'':>10}")

    print(f"\n  ── 覆盖 ──")
    print(f"  {'选股天数':<14} {v4_stats['days_with_picks']:>15d} {v5_stats['days_with_picks']:>15d}")
    print(f"  {'选股总数':<14} {v4_stats['n_picks_total']:>15d} {v5_stats['n_picks_total']:>15d}")

    # Verdict
    print("\n" + "=" * len(header))
    improvements = []
    for h in ["5d", "10d", "20d"]:
        if v5_stats[h]["mean"] > v4_stats[h]["mean"]:
            improvements.append(f"{h}均值 +{v5_stats[h]['mean']-v4_stats[h]['mean']:.2f}pp")
        if v5_stats[h]["median"] > v4_stats[h]["median"]:
            improvements.append(f"{h}中位 +{v5_stats[h]['median']-v4_stats[h]['median']:.2f}pp")
        if v5_stats[h]["wr"] > v4_stats[h]["wr"]:
            improvements.append(f"{h}胜率 +{(v5_stats[h]['wr']-v4_stats[h]['wr'])*100:.1f}pp")

    if improvements:
        print(f"  ✅ V5.0 提升项: {', '.join(improvements)}")
    else:
        print(f"  ❌ V5.0 未见提升，需排查融合逻辑")
    print("=" * len(header))


def main():
    parser = argparse.ArgumentParser(description="Backtest V4.0 vs V5.0 fusion")
    parser.add_argument("--start", default="2026-06-01")
    parser.add_argument("--end", default="2026-06-26")
    parser.add_argument("--top-n", type=int, default=30)
    args = parser.parse_args()

    pg_url = _PG_URL

    trading_days = get_trading_days(pg_url, args.start, args.end)
    logger.info("Found %d trading days: %s ... %s",
                len(trading_days), trading_days[0] if trading_days else "N/A",
                trading_days[-1] if trading_days else "N/A")

    if not trading_days:
        logger.error("No trading days found")
        sys.exit(1)

    day_results = []
    t0 = time.time()

    for day_idx, trade_date in enumerate(trading_days):
        logger.info("--- Day %d/%d: %s ---", day_idx + 1, len(trading_days), trade_date)
        try:
            result = backtest_one_day(pg_url, trade_date, args.top_n)
            day_results.append(result)
        except Exception as e:
            logger.warning("Day %s failed: %s", trade_date, e)

    elapsed = time.time() - t0
    logger.info("Backtest completed in %.0fs", elapsed)

    v4_stats = aggregate(day_results, "v4")
    v5_stats = aggregate(day_results, "v5")
    print_comparison(v4_stats, v5_stats)


if __name__ == "__main__":
    main()
