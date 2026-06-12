#!/usr/bin/env python3
"""Profile intraday screening performance — identify slow queries."""
import os, sys, time, io, contextlib

_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for pkg in ["packages/kronos-factors", "packages/kronos-core", "packages/kronos-data"]:
    path = os.path.join(_PROJ, pkg)
    if os.path.isdir(path) and path not in sys.path:
        sys.path.insert(0, path)

from kronos_factors.pg_adapter import create_pg_adapter
from kronos_factors.scorer._db_stub import set_db_adapter
set_db_adapter(create_pg_adapter("postgresql://kronos:kronos@localhost:6432/kronos"))
from kronos_factors.scorer._db_stub import _get_db

TRADE_DATE = "2026-06-12"
TIME_SLOT = "13:55"

with _get_db() as db:
    # ── Phase 1: Bulk loads ──
    print("=" * 60)
    print("  Phase 1: Bulk Data Loading")
    print("=" * 60)

    t0 = time.time()
    from kronos_factors.engine.leader_intraday import get_intraday_snapshot
    snap = get_intraday_snapshot(db, TRADE_DATE, TIME_SLOT)
    t1 = time.time()
    print(f"  snapshot:         {len(snap):>5} stocks in {t1-t0:.1f}s")

    from kronos_factors.engine.leader_intraday import get_pre_close_map
    pre = get_pre_close_map(db, TRADE_DATE)
    t2 = time.time()
    print(f"  pre_close:        {len(pre):>5} stocks in {t2-t1:.1f}s")

    from kronos_factors.engine.leader_intraday import get_intraday_limit_status
    lim = get_intraday_limit_status(db, TRADE_DATE)
    t3 = time.time()
    print(f"  limit_status:     {len(lim):>5} stocks in {t3-t2:.1f}s")

    stocks = db.execute(
        "SELECT code, name, industry FROM stocks WHERE is_st=0 "
        "AND name NOT LIKE '%ST%' AND (float_mv IS NULL OR float_mv >= 20)"
    ).fetchall()
    t4 = time.time()
    print(f"  stock universe:   {len(stocks):>5} stocks in {t4-t3:.1f}s")

    qualifying = [r for r in stocks if r["code"] in snap and r["code"] in pre]
    print(f"  qualifying:       {len(qualifying):>5} stocks")
    print(f"  Phase 1 total:    {t4-t0:.1f}s\n")

    # ── Phase 2: Per-stock query timing ──
    print("=" * 60)
    print("  Phase 2: Per-Stock Query Breakdown")
    print("=" * 60)

    from kronos_factors.engine.leader_intraday import (
        get_baseline_stats, get_recent_volume_surge, get_kline_data,
        get_cumulative_amount, get_day_range, get_adjusted_completion,
        get_sector_index, get_shanghai_index, get_sector_climax_penalty,
    )

    # Test on 50 random stocks to measure averages
    import random
    random.seed(42)
    test_stocks = random.sample(qualifying, min(50, len(qualifying)))

    timings = {
        "baseline_stats": [],
        "volume_surge": [],
        "kline_data_60d": [],
        "cumulative_amount": [],
        "day_range": [],
        "sector_index_THS": [],
        "peer_count": [],
        "intra_rank": [],
        "climax_penalty": [],
    }

    for r in test_stocks:
        code = r["code"]
        ind = r["industry"] or "其他"
        gain_14 = (snap[code]["close"] / pre[code] - 1) * 100 if pre[code] > 0 else 5

        t = time.time()
        get_baseline_stats(db, code, TRADE_DATE)
        timings["baseline_stats"].append(time.time() - t)

        t = time.time()
        get_recent_volume_surge(db, code, TRADE_DATE, TIME_SLOT)
        timings["volume_surge"].append(time.time() - t)

        t = time.time()
        get_kline_data(db, code, TRADE_DATE, 60)
        timings["kline_data_60d"].append(time.time() - t)

        t = time.time()
        get_cumulative_amount(db, code, TRADE_DATE, TIME_SLOT)
        timings["cumulative_amount"].append(time.time() - t)

        t = time.time()
        get_day_range(db, code, TRADE_DATE, TIME_SLOT)
        timings["day_range"].append(time.time() - t)

        t = time.time()
        get_sector_index(db, ind, TRADE_DATE, code)
        timings["sector_index_THS"].append(time.time() - t)

        # peer_count query
        t = time.time()
        db.execute(
            "SELECT COUNT(DISTINCT SUBSTR(m.ts_code,1,6)) as cnt "
            "FROM stk_mins m JOIN stocks s ON s.code=SUBSTR(m.ts_code,1,6) "
            "JOIN stk_limit l ON s.code=l.code AND l.trade_date=? "
            "WHERE m.trade_time LIKE ? AND m.freq='5min' AND s.industry=? "
            "AND l.pre_close>0 AND (m.close/l.pre_close-1)*100>=5",
            (TRADE_DATE, f"{TRADE_DATE} {TIME_SLOT}%", ind)
        ).fetchone()
        timings["peer_count"].append(time.time() - t)

        # intra_rank query
        t = time.time()
        db.execute(
            "SELECT COUNT(*) as higher FROM stk_mins m "
            "JOIN stocks s ON s.code=SUBSTR(m.ts_code,1,6) "
            "JOIN stk_limit l ON s.code=l.code AND l.trade_date=? "
            "WHERE m.trade_time LIKE ? AND m.freq='5min' AND s.industry=? "
            "AND l.pre_close>0 AND (m.close/l.pre_close-1)*100 > ?",
            (TRADE_DATE, f"{TRADE_DATE} {TIME_SLOT}%", ind, gain_14)
        ).fetchone()
        timings["intra_rank"].append(time.time() - t)

        t = time.time()
        get_sector_climax_penalty(db, ind, TRADE_DATE)
        timings["climax_penalty"].append(time.time() - t)

    # Print summary
    import numpy as np
    total_per_stock = 0
    for name, times in timings.items():
        avg = np.mean(times) * 1000
        total_per_stock += avg
        print(f"  {name:<20} avg={avg:>6.1f}ms")

    avg_total = total_per_stock
    print(f"  {'─' * 40}")
    print(f"  {'TOTAL per stock':<20} avg={avg_total:>6.1f}ms")
    print(f"  Estimated total: {len(qualifying)} stocks x {avg_total:.0f}ms = {len(qualifying) * avg_total / 1000:.0f}s")
    print(f"  DB round-trips:   {len(qualifying)} stocks x ~9 queries = ~{len(qualifying) * 9}")

    # ── Phase 3: Identify bulk pre-compute opportunities ──
    print(f"\n{'=' * 60}")
    print("  Phase 3: Optimization Opportunities")
    print("=" * 60)
    print(f"  1. peer_count + intra_rank: same query pattern, 2x per stock")
    print(f"     → Pre-compute by industry at bulk load phase (1 query per industry)")
    print(f"  2. kline_data_60d: reads 60 rows per stock from daily_kline")
    print(f"     → Pre-fetch with single JOIN query for all stocks")
    print(f"  3. sector_index_THS: psycopg2 raw query per stock")
    print(f"     → Cache by industry (already partially cached for climax)")
    print(f"  4. baseline/volume/cumulative/day_range: 4 separate stk_mins queries")
    print(f"     → Merge into single stk_mins aggregation query per stock")
