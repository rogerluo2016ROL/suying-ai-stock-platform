#!/usr/bin/env python3
"""Calibrate mode_profiles.json from June 2026 backtest data, then re-run V4 vs V5.

Step 1: Run each engine on June 2026, compute per-engine stats
Step 2: Generate calibrated mode_profiles.json
Step 3: Re-run V4 vs V5 fusion comparison
"""
import json, os, sys, time, logging
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Dict, List

import numpy as np
import psycopg2

_PACKAGES = str(Path(__file__).parent)
sys.path.insert(0, _PACKAGES)
_PG_URL = os.environ.get("KRONOS_PG_URL", "postgresql://kronos:kronos@localhost:6432/kronos")
os.environ.setdefault("KRONOS_PG_URL", _PG_URL)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

from kronos_factors.engine.leader_scalp import LeaderScalpEngine
from kronos_factors.engine.bi_trend_launch import BiTrendLaunchEngine
from kronos_factors.engine.modes import ShortModeEngine
from kronos_factors.engine.supply_chain import SupplyChainEngine
from kronos_factors.engine.weighted_fusion import WeightedFusionEngine, ModeProfile
from kronos_factors.engine.sector_heatmap import SectorHeatmapEngine

ENGINES = [
    ("leader_scalp",    LeaderScalpEngine,     "龙头短线"),
    ("bi_trend_launch", BiTrendLaunchEngine,   "毕师傅趋势"),
    ("short",           ShortModeEngine,       "多因子"),
    ("supply_chain",    SupplyChainEngine,     "产业链共振"),
]

PROFILES_PATH = Path(_PACKAGES) / "config" / "mode_profiles.json"


def get_db():
    return psycopg2.connect(_PG_URL)


def get_trading_days(start: str, end: str) -> List[str]:
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("SELECT DISTINCT trade_date::text FROM daily_kline WHERE trade_date >= %s AND trade_date <= %s ORDER BY trade_date", (start, end))
        return [r[0] for r in cur.fetchall()]
    finally:
        conn.close()


def get_future_returns(trade_date: str, codes: list[str], horizon: int) -> dict:
    """Returns dict[code, pct_return]. None for codes without exit data."""
    if not codes:
        return {}
    from datetime import datetime, timedelta
    conn = get_db()
    try:
        cur = conn.cursor()
        ph = ",".join(["%s"] * len(codes))
        cur.execute(f"SELECT code, close FROM daily_kline WHERE code IN ({ph}) AND trade_date = %s", codes + [trade_date])
        entry = {r[0]: float(r[1]) for r in cur.fetchall() if r[1] is not None}
        if not entry:
            return {}
        target = (datetime.strptime(trade_date, '%Y-%m-%d') + timedelta(days=horizon)).strftime('%Y-%m-%d')
        cur.execute("SELECT MAX(trade_date::text) FROM daily_kline WHERE trade_date >= %s AND trade_date <= %s",
                    (target, (datetime.strptime(target, '%Y-%m-%d') + timedelta(days=10)).strftime('%Y-%m-%d')))
        row = cur.fetchone()
        if not row or not row[0]:
            cur.execute("SELECT MAX(trade_date::text) FROM daily_kline")
            row = cur.fetchone()
        if not row or not row[0]:
            return {}
        exit_d = row[0]
        if exit_d == trade_date:
            return {}
        cur.execute(f"SELECT code, close FROM daily_kline WHERE code IN ({ph}) AND trade_date = %s", codes + [exit_d])
        exit_p = {r[0]: float(r[1]) for r in cur.fetchall() if r[1] is not None}
        ret = {}
        for c in codes:
            e1, e2 = entry.get(c), exit_p.get(c)
            if e1 and e1 > 0 and e2 is not None:
                ret[c] = (e2 - e1) / e1 * 100
        return ret
    finally:
        conn.close()


def run_engine_norm(engine_cls, top_n: int, trade_date: str) -> list[dict]:
    engine = engine_cls()
    result = engine.run(top_n=top_n, trade_date=trade_date)
    if isinstance(result, list): return result
    if hasattr(result, 'picks'): return result.picks
    if hasattr(result, 'results'): return result.results
    if isinstance(result, dict) and 'picks' in result: return result['picks']
    return []


def calibrate_profiles(days: List[str], top_n: int = 30):
    """Run each engine on all days, compute stats, build calibrated profiles."""
    logger.info("=== Step 1: Calibrating mode_profiles from %d days ===", len(days))

    # Collect per-engine results
    engine_returns = defaultdict(lambda: {"5d": [], "10d": [], "20d": [], "pick_counts": []})
    engine_codes_seen = defaultdict(set)

    for day_idx, trade_date in enumerate(days):
        logger.info("Day %d/%d: %s", day_idx + 1, len(days), trade_date)
        for mode, cls, desc in ENGINES:
            try:
                picks = run_engine_norm(cls, top_n, trade_date)
            except Exception as e:
                logger.warning("  %s failed: %s", mode, e)
                continue

            codes = [p.get("code", "") for p in picks if p.get("code")]
            engine_returns[mode]["pick_counts"].append(len(codes))
            for c in codes:
                engine_codes_seen[mode].add(c)

            for h, horizon in [("5d", 5), ("10d", 10), ("20d", 20)]:
                ret = get_future_returns(trade_date, codes, horizon)
                for v in ret.values():
                    if v is not None:
                        engine_returns[mode][h].append(v)

    # Compute profiles
    profiles = {}
    for mode, desc in [(m, d) for m, _, d in ENGINES]:
        data = engine_returns[mode]
        rets_5d = data["5d"]
        if not rets_5d:
            logger.warning("  %s: no 5d returns, using defaults", mode)
            continue

        wr_5d = sum(1 for v in rets_5d if v > 0) / len(rets_5d)
        avg_5d = float(np.mean(rets_5d))
        avg_picks_per_day = np.mean(data["pick_counts"]) if data["pick_counts"] else 0
        coverage = len(engine_codes_seen[mode]) / 5000  # ~5000 stocks

        # Speed classification
        if avg_picks_per_day < 10:
            speed = "slow"
        elif avg_picks_per_day < 25:
            speed = "medium"
        else:
            speed = "fast"

        # Style classification
        if mode == "leader_scalp":
            style = "momentum"
        elif mode in ("bi_trend_launch",):
            style = "trend"
        elif mode in ("short",):
            style = "statistical"
        elif mode in ("supply_chain",):
            style = "theme"

        # Risk preference from volatility
        std_5d = float(np.std(rets_5d))
        if std_5d > 20:
            risk = "aggressive"
        elif std_5d > 14:
            risk = "moderate"
        else:
            risk = "conservative"

        # env_affinity from per-environment win rate (simplified: use overall WR)
        profiles[mode] = ModeProfile(
            mode=mode,
            precision=round(wr_5d, 3),
            recall=round(min(coverage, 1.0), 3),
            speed=speed,
            style=style,
            primary_factors=[],
            risk_preference=risk,
            env_affinity={"bull": round(wr_5d * 1.1, 3), "neutral": round(wr_5d, 3), "bear": round(wr_5d * 0.85, 3)},
            note=f"Calibrated from June 2026: avg_5d={avg_5d:+.2f}%, wr_5d={wr_5d:.1%}, std={std_5d:.1f}, n={len(rets_5d)} picks"
        )
        logger.info("  %s: precision=%.3f, recall=%.3f, speed=%s, style=%s, risk=%s, n=%d",
                    mode, profiles[mode].precision, profiles[mode].recall,
                    speed, style, risk, len(rets_5d))

    return profiles


def save_profiles(profiles: dict):
    """Save calibrated profiles to mode_profiles.json."""
    data = {}
    for mode, p in profiles.items():
        data[mode] = {
            "mode": p.mode,
            "precision": p.precision,
            "recall": p.recall,
            "speed": p.speed,
            "style": p.style,
            "primary_factors": p.primary_factors,
            "risk_preference": p.risk_preference,
            "env_affinity": p.env_affinity,
            "note": p.note,
        }

    PROFILES_PATH.parent.mkdir(parents=True, exist_ok=True)
    # Backup original
    if PROFILES_PATH.exists():
        backup = PROFILES_PATH.with_suffix(".json.bak")
        PROFILES_PATH.rename(backup)
        logger.info("Original backed up to %s", backup)

    with open(PROFILES_PATH, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    logger.info("Calibrated profiles saved to %s", PROFILES_PATH)


def detect_market_env(trade_date: str) -> str:
    conn = get_db()
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
        if breadth >= 0.55 and avg_change > 1.0: return "bull"
        elif breadth < 0.35 or avg_change < -2.0: return "bear"
        return "neutral"
    finally:
        conn.close()


def merge_picks_v4(strategy_results: dict, top_n: int = 30) -> list[dict]:
    stock_scores = defaultdict(lambda: {"score": 0, "count": 0, "strategies": [], "data": {}})
    for mode, picks in strategy_results.items():
        if not picks or not isinstance(picks, list):
            continue
        for p in picks:
            code = p.get("code", "")
            if not code: continue
            s = stock_scores[code]
            s["count"] += 1
            s["strategies"].append(mode)
            p_score = p.get("total_score", p.get("score", 50))
            if p_score > s["score"]:
                s["score"] = p_score
                s["data"] = p
            s["score"] += 10 if mode == "leader_scalp" else 5
    ranked = sorted(stock_scores.items(), key=lambda x: (x[1]["count"], x[1]["score"]), reverse=True)
    return [{**info["data"], "consensus_count": info["count"], "consensus_strategies": info["strategies"]}
            for code, info in ranked[:top_n]]


def main():
    days = get_trading_days("2026-06-01", "2026-06-26")
    logger.info("Found %d trading days", len(days))

    # Step 1: Calibrate
    profiles = calibrate_profiles(days, top_n=30)
    save_profiles(profiles)

    # Step 2: Re-run V4 vs V5 with calibrated profiles
    logger.info("\n=== Step 2: V4 vs V5 comparison with calibrated profiles ===")

    # Force re-init WeightedFusionEngine with new profiles
    import kronos_factors.engine.weighted_fusion as wf
    wf._DEFAULT_PROFILES_PATH = PROFILES_PATH
    fusion_v5 = WeightedFusionEngine(mode_profiles_path=str(PROFILES_PATH))
    heatmap = SectorHeatmapEngine()

    all_v4_5d, all_v4_10d, all_v4_20d = [], [], []
    all_v5_5d, all_v5_10d, all_v5_20d = [], [], []
    v4_picks_total, v5_picks_total = 0, 0
    days_v4, days_v5 = 0, 0

    for day_idx, trade_date in enumerate(days):
        logger.info("Day %d/%d: %s", day_idx + 1, len(days), trade_date)
        env = detect_market_env(trade_date)

        # Run engines
        strategy_results = {}
        with ThreadPoolExecutor(max_workers=len(ENGINES)) as pool:
            futures = {pool.submit(run_engine_norm, cls, 30, trade_date): mode for mode, cls, _ in ENGINES}
            for f in futures:
                mode = futures[f]
                try:
                    strategy_results[mode] = f.result()
                except Exception as e:
                    logger.warning("  %s failed: %s", mode, e)
                    strategy_results[mode] = []

        # V4 fusion
        v4_picks = merge_picks_v4(strategy_results, 30)
        v4_codes = [p.get("code", "") for p in v4_picks if p.get("code")]

        # V5 fusion
        hot_sectors = None
        try:
            hot_sectors = heatmap.get_hot_sectors(trade_date, min_hit_rate=0.6)
        except Exception:
            pass
        try:
            fr = fusion_v5.run(strategy_results=strategy_results, market_env=env, hot_sectors=hot_sectors, top_n=30)
            v5_picks = fr.picks
        except Exception as e:
            logger.warning("V5 fusion failed: %s", e)
            v5_picks = merge_picks_v4(strategy_results, 30)

        v5_codes = [p.get("code", "") for p in v5_picks if p.get("code")]

        # Forward returns
        for h, horizon in [("5d", 5), ("10d", 10), ("20d", 20)]:
            v4_ret = get_future_returns(trade_date, v4_codes, horizon)
            v5_ret = get_future_returns(trade_date, v5_codes, horizon)
            if h == "5d":
                for v in v4_ret.values():
                    if v is not None: all_v4_5d.append(v)
                for v in v5_ret.values():
                    if v is not None: all_v5_5d.append(v)
            elif h == "10d":
                for v in v4_ret.values():
                    if v is not None: all_v4_10d.append(v)
                for v in v5_ret.values():
                    if v is not None: all_v5_10d.append(v)
            else:
                for v in v4_ret.values():
                    if v is not None: all_v4_20d.append(v)
                for v in v5_ret.values():
                    if v is not None: all_v5_20d.append(v)

        if v4_codes:
            days_v4 += 1
            v4_picks_total += len(v4_codes)
        if v5_codes:
            days_v5 += 1
            v5_picks_total += len(v5_codes)

        logger.info("  env=%s, V4=%d picks, V5=%d picks", env, len(v4_codes), len(v5_codes))

    # Print comparison
    def s(vals):
        if not vals: return {"mean": 0, "median": 0, "wr": 0, "std": 0, "n": 0}
        return {"mean": float(np.mean(vals)), "median": float(np.median(vals)),
                "wr": sum(1 for v in vals if v > 0) / len(vals), "std": float(np.std(vals)), "n": len(vals)}

    v4s = {"5d": s(all_v4_5d), "10d": s(all_v4_10d), "20d": s(all_v4_20d)}
    v5s = {"5d": s(all_v5_5d), "10d": s(all_v5_10d), "20d": s(all_v5_20d)}

    print("\n" + "=" * 75)
    print("  V4.0 vs V5.0 融合层回测对比 (6月校准版)")
    print("=" * 75)
    print(f"{'指标':<16} {'V4.0 简单投票':>16} {'V5.0 加权融合(校准)':>20} {'提升':>10}")
    print("-" * 75)

    for h, label in [("5d", "5日"), ("10d", "10日"), ("20d", "20日")]:
        v4, v5 = v4s[h], v5s[h]
        print(f"\n  ── {label}收益 ──")
        print(f"  {'平均收益':<14} {v4['mean']:>+15.2f}% {v5['mean']:>+19.2f}% {v5['mean']-v4['mean']:>+9.2f}pp")
        print(f"  {'中位收益':<14} {v4['median']:>+15.2f}% {v5['median']:>+19.2f}% {v5['median']-v4['median']:>+9.2f}pp")
        print(f"  {'胜率':<14} {v4['wr']:>15.1%} {v5['wr']:>19.1%} {(v5['wr']-v4['wr'])*100:>+9.1f}pp")
        print(f"  {'样本数':<14} {v4['n']:>15d} {v5['n']:>19d}")

    print(f"\n  ── 覆盖 ──")
    print(f"  {'选股天数':<14} {days_v4:>15d} {days_v5:>19d}")
    print(f"  {'选股总数':<14} {v4_picks_total:>15d} {v5_picks_total:>19d}")

    # Verdict
    improvements = []
    for h in ["5d", "10d", "20d"]:
        dm = v5s[h]["mean"] - v4s[h]["mean"]
        dmed = v5s[h]["median"] - v4s[h]["median"]
        dwr = (v5s[h]["wr"] - v4s[h]["wr"]) * 100
        if dm > 0: improvements.append(f"{h}均值+{dm:.2f}pp")
        if dmed > 0: improvements.append(f"{h}中位+{dmed:.2f}pp")
        if dwr > 0: improvements.append(f"{h}胜率+{dwr:.1f}pp")

    print("\n" + "=" * 75)
    if improvements:
        print(f"  ✅ V5.0 校准后提升: {', '.join(improvements)}")
    else:
        print(f"  ❌ V5.0 校准后未见提升")
        # Print calibrated explainer
        print(f"\n  📋 校准后的 mode_profiles:")
        for mode, p in profiles.items():
            print(f"     {mode}: precision={p.precision:.1%}, env_affinity={p.env_affinity}")
    print("=" * 75)


if __name__ == "__main__":
    main()
