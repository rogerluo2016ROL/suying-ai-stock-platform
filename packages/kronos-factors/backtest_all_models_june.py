#!/usr/bin/env python3
"""Backtest all screening models on June 2026 data.

Computes win rate and average return at 5d/10d/20d horizons.

Usage:
    cd packages/kronos-factors && python3 backtest_all_models_june.py
    cd packages/kronos-factors && python3 backtest_all_models_june.py --verbose
    cd packages/kronos-factors && python3 backtest_all_models_june.py --output /tmp/backtest_june.csv
"""
import argparse
import logging
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import psycopg2

# Add packages to path
_PACKAGES = str(Path(__file__).parent)
if _PACKAGES not in sys.path:
    sys.path.insert(0, _PACKAGES)

# Ensure KRONOS_PG_URL is set before importing engines (they auto-init on first use)
_PG_URL = os.environ.get("KRONOS_PG_URL", "postgresql://kronos:kronos@localhost:6432/kronos")
os.environ.setdefault("KRONOS_PG_URL", _PG_URL)

# Import baseline screening engines (daily-kline only, no intraday/minute data)
from kronos_factors.engine.modes import ShortModeEngine, ChokepointEngine
from kronos_factors.engine.bi_trend_launch import BiTrendLaunchEngine
from kronos_factors.engine.bi_trend_full_market import BiTrendFullMarketEngine
from kronos_factors.engine.supply_chain import SupplyChainEngine
from kronos_factors.engine.leader_afternoon import AfternoonLeaderEngine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

# Engine configurations - ONLY baseline models that use daily_kline (no intraday/minute data)
#
# Excluded: leader_scalp, leader_auction, leader_intraday, leader_afternoon, leader_closing
#   (这些模型依赖 stk_mins 分钟级数据，历史回测不可用)
#
MODES = [
    ("bi_trend_launch",          BiTrendLaunchEngine,          "毕师傅趋势"),
    ("bi_trend_full",            BiTrendFullMarketEngine,      "全市场趋势"),
    ("short",                     ShortModeEngine,              "多因子"),
    ("chokepoint",                ChokepointEngine,             "卡脖子"),
    ("supply_chain",              SupplyChainEngine,            "产业链共振"),
    ("leader_afternoon",          AfternoonLeaderEngine,        "秋神午后"),
]


def get_db(pg_url: str = None):
    """Get PostgreSQL connection."""
    url = pg_url or os.environ.get("KRONOS_PG_URL", "postgresql://kronos:kronos@localhost:6432/kronos")
    return psycopg2.connect(url)


def get_trading_days(pg_url: str, start: str, end: str) -> List[str]:
    """Get sorted list of trading dates in [start, end]."""
    conn = get_db(pg_url)
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT DISTINCT trade_date::text
            FROM daily_kline
            WHERE trade_date >= %s AND trade_date <= %s
            ORDER BY trade_date
        """, (start, end))
        return [r[0] for r in cur.fetchall()]
    finally:
        conn.close()


def get_future_returns(pg_url: str, trade_date: str, codes: list[str], horizon: int) -> dict[str, float]:
    """Calculate forward return for each stock at given horizon (days).

    Forward return = (close_price_N_days_later - close_price_on_trade_date) / close_price_on_trade_date * 100

    Uses the NEXT available trading day >= trade_date + horizon days.
    """
    if not codes:
        return {}

    conn = get_db(pg_url)
    try:
        cur = conn.cursor()
        placeholders = ",".join(["%s"] * len(codes))

        # Find entry close price on trade_date
        cur.execute(f"""
            SELECT code, close FROM daily_kline
            WHERE code IN ({placeholders}) AND trade_date = %s
        """, codes + [trade_date])
        entry_prices = {r[0]: float(r[1]) for r in cur.fetchall() if r[1] is not None}

        if not entry_prices:
            return {}

        # Find the target trading date (N calendar days after, pick closest available)
        target_date = (datetime.strptime(trade_date, '%Y-%m-%d') + timedelta(days=horizon)).strftime('%Y-%m-%d')
        cur.execute("""
            SELECT MAX(trade_date::text) FROM daily_kline
            WHERE trade_date >= %s AND trade_date <= %s
        """, (target_date, (datetime.strptime(target_date, '%Y-%m-%d') + timedelta(days=10)).strftime('%Y-%m-%d')))
        row = cur.fetchone()
        if not row or not row[0]:
            # Fallback: use the latest available trading day (for dates near data end)
            cur.execute("SELECT MAX(trade_date::text) FROM daily_kline")
            row = cur.fetchone()
        if not row or not row[0]:
            return {}
        exit_date = row[0]
        # Skip if exit_date equals trade_date (no forward data at all)
        if exit_date == trade_date:
            return {}

        # Get exit close prices
        cur.execute(f"""
            SELECT code, close FROM daily_kline
            WHERE code IN ({placeholders}) AND trade_date = %s
        """, codes + [exit_date])
        exit_prices = {r[0]: float(r[1]) for r in cur.fetchall() if r[1] is not None}

        # Calculate returns
        returns = {}
        for code in codes:
            entry = entry_prices.get(code)
            exit_p = exit_prices.get(code)
            if entry and entry > 0 and exit_p is not None:
                returns[code] = (exit_p - entry) / entry * 100
            else:
                returns[code] = None

        return returns
    finally:
        conn.close()


def check_limit_up(pg_url: str, trade_date: str, codes: list[str]) -> set[str]:
    """Check which stocks hit limit_up on given date.

    Note: limit_list_d uses ts_code (e.g., '600105.SH'), while engine picks
    use bare 6-digit code. Match by stripping the exchange suffix from ts_code.
    """
    if not codes:
        return set()

    conn = get_db(pg_url)
    try:
        cur = conn.cursor()
        placeholders = ",".join(["%s"] * len(codes))
        # Match bare codes against LEFT(ts_code, 6) to handle .SH/.SZ/.BJ suffixes
        cur.execute(f"""
            SELECT DISTINCT LEFT(ts_code, 6) AS code FROM limit_list_d
            WHERE LEFT(ts_code, 6) IN ({placeholders}) AND trade_date = %s
        """, codes + [trade_date.replace("-", "")])
        return {r[0] for r in cur.fetchall()}
    finally:
        conn.close()


def run_engine(engine_cls, top_n: int, trade_date: str) -> list[dict]:
    """Run a screening engine and normalize results."""
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


def backtest_one_day(
    pg_url: str,
    mode: str,
    engine_cls,
    trade_date: str,
    next_trade_date: str | None,
) -> dict:
    """Run backtest for one mode on one day.

    Returns dict with keys: mode, trade_date, n_picks, returns_5d, returns_10d, returns_20d,
                            next_day_limit_ups, pick_codes
    """
    try:
        picks = run_engine(engine_cls, top_n=30, trade_date=trade_date)
        if not picks:
            return {"mode": mode, "trade_date": trade_date, "n_picks": 0, "pick_codes": []}

        pick_codes = []
        for p in picks:
            code = p.get("code", "")
            if code:
                pick_codes.append(code)

        # Calculate forward returns
        ret_5d = get_future_returns(pg_url, trade_date, pick_codes, horizon=5)
        ret_10d = get_future_returns(pg_url, trade_date, pick_codes, horizon=10)
        ret_20d = get_future_returns(pg_url, trade_date, pick_codes, horizon=20)

        # Next day limit ups
        limit_ups = set()
        if next_trade_date:
            limit_ups = check_limit_up(pg_url, next_trade_date, pick_codes)

        return {
            "mode": mode,
            "trade_date": trade_date,
            "n_picks": len(pick_codes),
            "returns_5d": ret_5d,
            "returns_10d": ret_10d,
            "returns_20d": ret_20d,
            "next_day_limit_ups": limit_ups,
            "pick_codes": pick_codes,
        }
    except Exception as e:
        logger.warning(f"  {mode} on {trade_date} failed: {e}")
        return {"mode": mode, "trade_date": trade_date, "n_picks": 0, "pick_codes": [], "error": str(e)}


def aggregate_stats(all_results: list[dict]) -> list[dict]:
    """Aggregate per-mode statistics from raw results."""
    by_mode = {}
    for r in all_results:
        mode = r["mode"]
        if mode not in by_mode:
            by_mode[mode] = {"returns_5d": [], "returns_10d": [], "returns_20d": [],
                             "n_picks_total": 0, "days_run": 0, "limit_ups": [], "pick_codes_all": []}
        if r["n_picks"] == 0:
            continue
        by_mode[mode]["days_run"] += 1
        by_mode[mode]["n_picks_total"] += r["n_picks"]

        for code, ret in (r.get("returns_5d") or {}).items():
            if ret is not None:
                by_mode[mode]["returns_5d"].append(ret)
        for code, ret in (r.get("returns_10d") or {}).items():
            if ret is not None:
                by_mode[mode]["returns_10d"].append(ret)
        for code, ret in (r.get("returns_20d") or {}).items():
            if ret is not None:
                by_mode[mode]["returns_20d"].append(ret)

        by_mode[mode]["limit_ups"].extend(r.get("next_day_limit_ups", set()))
        by_mode[mode]["pick_codes_all"].extend(r.get("pick_codes", []))

    stats = []
    for mode, data in by_mode.items():
        n = len(data["returns_5d"])
        if n == 0:
            continue

        def safe_mean(vals):
            return float(np.mean(vals)) if vals else 0.0

        def safe_std(vals):
            return float(np.std(vals)) if vals else 0.0

        def win_rate(vals):
            return sum(1 for v in vals if v > 0) / len(vals) if vals else 0.0

        def max_drawdown(vals):
            if len(vals) < 2:
                return 0.0
            cummax = np.maximum.accumulate(vals)
            drawdowns = (vals - cummax) / np.maximum(cummax, 1e-9)
            return float(np.min(drawdowns))

        # Per-stock cumulative return approximation
        stats.append({
            "mode": mode,
            "n_days": data["days_run"],
            "n_picks": data["n_picks_total"],
            "avg_return_5d": safe_mean(data["returns_5d"]),
            "avg_return_10d": safe_mean(data["returns_10d"]),
            "avg_return_20d": safe_mean(data["returns_20d"]),
            "std_return_5d": safe_std(data["returns_5d"]),
            "std_return_10d": safe_std(data["returns_10d"]),
            "std_return_20d": safe_std(data["returns_20d"]),
            "win_rate_5d": win_rate(data["returns_5d"]),
            "win_rate_10d": win_rate(data["returns_10d"]),
            "win_rate_20d": win_rate(data["returns_20d"]),
            "max_drawdown_5d": max_drawdown(data["returns_5d"]),
            "max_drawdown_10d": max_drawdown(data["returns_10d"]),
            "max_drawdown_20d": max_drawdown(data["returns_20d"]),
            "median_return_5d": float(np.median(data["returns_5d"])),
            "median_return_10d": float(np.median(data["returns_10d"])),
            "median_return_20d": float(np.median(data["returns_20d"])),
            "positive_days_5d": sum(1 for v in data["returns_5d"] if v > 0),
        })

    return sorted(stats, key=lambda x: x["avg_return_5d"], reverse=True)


def print_table(stats: list[dict], mode_desc_map: dict[str, str]):
    """Print formatted results table."""
    header = (
        f"{'模式':<16} {'N天':>4} {'N股':>5} "
        f"{'5日平均':>8} {'5日中位':>8} {'5日胜率':>7} {'5日波动':>7} "
        f"{'10日平均':>8} {'10日中位':>8} {'10日胜率':>7} {'10日波动':>7} "
        f"{'20日平均':>8} {'20日中位':>8} {'20日胜率':>7}"
    )
    print("=" * len(header))
    print("2026年6月 选股模型回测结果")
    print("=" * len(header))
    print(header)
    print("-" * len(header))

    for s in stats:
        mode = s["mode"]
        desc = mode_desc_map.get(mode, mode)
        print(
            f"{desc:<14} {s['n_days']:>4} {s['n_picks']:>5} "
            f"{s['avg_return_5d']:>+7.2f}% {s['median_return_5d']:>+7.2f}% {s['win_rate_5d']:>6.1%} {s['std_return_5d']:>6.2f} "
            f"{s['avg_return_10d']:>+7.2f}% {s['median_return_10d']:>+7.2f}% {s['win_rate_10d']:>6.1%} {s['std_return_10d']:>6.2f} "
            f"{s['avg_return_20d']:>+7.2f}% {s['median_return_20d']:>+7.2f}% {s['win_rate_20d']:>6.1%}"
        )

    print("-" * len(header))

    # Summary
    if stats:
        avg_wr_5d = np.mean([s["win_rate_5d"] for s in stats])
        avg_ret_5d = np.mean([s["avg_return_5d"] for s in stats])
        best = stats[0]
        worst = stats[-1]
        print(f"\nSummary:")
        print(f"  Average 5-day win rate across all models: {avg_wr_5d:.1%}")
        print(f"  Average 5-day return across all models:   {avg_ret_5d:+.2f}%")
        print(f"  Best model (5d):  {mode_desc_map.get(best['mode'], best['mode'])}  "
              f"avg={best['avg_return_5d']:+.2f}%, WR={best['win_rate_5d']:.1%}")
        print(f"  Worst model (5d): {mode_desc_map.get(worst['mode'], worst['mode'])}  "
              f"avg={worst['avg_return_5d']:+.2f}%, WR={worst['win_rate_5d']:.1%}")

        # Models with positive median return
        positive_median = [s for s in stats if s["median_return_5d"] > 0]
        print(f"  Models with positive median 5d return: {len(positive_median)}/{len(stats)}")
        for s in positive_median:
            print(f"    + {mode_desc_map.get(s['mode'], s['mode'])}: median={s['median_return_5d']:+.2f}%")


def save_csv(stats: list[dict], mode_desc_map: dict[str, str], output_path: str):
    """Save results to CSV."""
    with open(output_path, 'w', encoding='utf-8-sig') as f:
        f.write("模式代码,模式名称,回测天数,选股总数,"
                "5日平均收益,5日中位收益,5日胜率,5日波动率,5日最大回撤,"
                "10日平均收益,10日中位收益,10日胜率,10日波动率,10日最大回撤,"
                "20日平均收益,20日中位收益,20日胜率,20日波动率,20日最大回撤\n")
        for s in stats:
            desc = mode_desc_map.get(s["mode"], s["mode"])
            f.write(f"{s['mode']},{desc},"
                    f"{s['n_days']},{s['n_picks']},"
                    f"{s['avg_return_5d']:.4f},{s['median_return_5d']:.4f},{s['win_rate_5d']:.4f},{s['std_return_5d']:.4f},{s['max_drawdown_5d']:.4f},"
                    f"{s['avg_return_10d']:.4f},{s['median_return_10d']:.4f},{s['win_rate_10d']:.4f},{s['std_return_10d']:.4f},{s['max_drawdown_10d']:.4f},"
                    f"{s['avg_return_20d']:.4f},{s['median_return_20d']:.4f},{s['win_rate_20d']:.4f},{s['std_return_20d']:.4f},{s['max_drawdown_20d']:.4f}\n")
    print(f"\nResults saved to: {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Backtest all screening models on June 2026 data")
    parser.add_argument("--start", default="2026-06-01", help="Start date (default: 2026-06-01)")
    parser.add_argument("--end", default="2026-06-29", help="End date (default: 2026-06-29)")
    parser.add_argument("--pg-url", default=None, help="PostgreSQL URL")
    parser.add_argument("--output", default="backtest_june_2026.csv", help="Output CSV path")
    parser.add_argument("--verbose", action="store_true", help="Verbose logging")
    parser.add_argument("--top-n", type=int, default=30, help="Top N picks per mode per day")
    parser.add_argument("--modes", nargs="*", default=None,
                        help="Specific modes to test (default: all)")
    args = parser.parse_args()

    if args.verbose:
        logger.setLevel(logging.DEBUG)

    pg_url = args.pg_url or os.environ.get("KRONOS_PG_URL", "postgresql://kronos:kronos@localhost:6432/kronos")

    # Filter modes
    modes = MODES
    if args.modes:
        mode_names = {m[0] for m in MODES}
        requested = set(args.modes)
        unknown = requested - mode_names
        if unknown:
            logger.warning(f"Unknown modes: {unknown}, available: {mode_names}")
        modes = [m for m in MODES if m[0] in requested]

    # Get trading days
    logger.info(f"Fetching trading days from {args.start} to {args.end}")
    trading_days = get_trading_days(pg_url, args.start, args.end)
    if not trading_days:
        logger.error("No trading days found in date range")
        sys.exit(1)

    logger.info(f"Found {len(trading_days)} trading days: {trading_days}")

    # Build next-day map
    next_day_map = {}
    for i in range(len(trading_days) - 1):
        next_day_map[trading_days[i]] = trading_days[i + 1]

    # Mode description map
    mode_desc_map = {m[0]: m[2] for m in MODES}

    # Run backtest
    all_results = []
    t0 = time.time()

    for day_idx, trade_date in enumerate(trading_days):
        next_date = next_day_map.get(trade_date)
        logger.info(f"\n--- Day {day_idx + 1}/{len(trading_days)}: {trade_date} ---")

        for mode, engine_cls, desc in modes:
            logger.info(f"  Running {desc} ({mode})...")
            result = backtest_one_day(pg_url, mode, engine_cls, trade_date, next_date)
            all_results.append(result)

            if result.get("n_picks", 0) > 0:
                n_with_ret = sum(1 for v in (result.get("returns_5d") or {}).values() if v is not None)
                logger.info(f"    {desc}: {result['n_picks']} picks, {n_with_ret} with 5d return")
                if result.get("next_day_limit_ups"):
                    logger.info(f"    Next day limit ups: {len(result['next_day_limit_ups'])} of {result['n_picks']}")

    elapsed = time.time() - t0
    logger.info(f"\nBacktest completed in {elapsed:.0f}s ({elapsed / max(len(all_results), 1):.1f}s per run)")

    # Aggregate and display
    stats = aggregate_stats(all_results)
    print_table(stats, mode_desc_map)
    save_csv(stats, mode_desc_map, args.output)


if __name__ == "__main__":
    main()
