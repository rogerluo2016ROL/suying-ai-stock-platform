"""Screener API routes — 12 screening modes via unified endpoint with Redis caching."""

import asyncio
import json
import logging
import math
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Optional
from fastapi import APIRouter, Query, HTTPException

import numpy as np

from app.config import AVAILABLE_MODES, DEFAULT_TOP_N, MAX_TOP_N

logger = logging.getLogger("screener.routes")

router = APIRouter(prefix="/api/v1/screener", tags=["screener"])


def _normalize_picks(picks: list, mode: str) -> list:
    """Normalize engine-specific field names to frontend-expected fields.

    Frontend expects: price, score, grade, entry_price, stop_loss, target_price
    Different engines use different names, so we normalize here.
    """
    for p in picks:
        # Normalize price
        if "price" not in p:
            if "close" in p:
                p["price"] = p["close"]
            elif "current_price" in p:
                p["price"] = p["current_price"]
            # leader_auction: no price field, use default placeholder
            elif "gap_pct" in p:
                p["price"] = 0  # auction mode doesn't store price

        # Normalize score
        if "score" not in p:
            if "total_score" in p:
                p["score"] = p["total_score"]
            elif "composite_score" in p:
                p["score"] = p["composite_score"]
            elif "gap_score" in p:
                p["score"] = p.get("total_score", 5.0)

        # Normalize grade (default B if missing)
        if "grade" not in p:
            sc = p.get("score", 0)
            if sc >= 20: p["grade"] = "S"
            elif sc >= 16: p["grade"] = "A"
            elif sc >= 10: p["grade"] = "B"
            else: p["grade"] = "C"

        # Normalize entry/stop/target (fill None or missing values)
        base_price = p.get("close") or p.get("price") or 0
        if base_price and float(base_price) > 0:
            bp = float(base_price)
            if not p.get("entry_price"):
                p["entry_price"] = round(bp * 1.01, 2)
            if not p.get("stop_loss"):
                p["stop_loss"] = round(bp * 0.93, 2)
            if not p.get("target_price"):
                p["target_price"] = round(bp * 1.15, 2)

        # Ensure numeric types
        for k in ("price", "score", "entry_price", "stop_loss", "target_price"):
            if k in p and p[k] is not None:
                try:
                    p[k] = round(float(p[k]), 2)
                except (ValueError, TypeError):
                    pass

    return picks


def _sanitize_picks(picks: list) -> list:
    """Convert numpy types in picks to native Python types for JSON serialization."""
    def _convert(v):
        if isinstance(v, (np.integer,)):
            return int(v)
        if isinstance(v, (np.floating,)):
            return float(v) if not math.isnan(v) else None
        if isinstance(v, (np.bool_,)):
            return bool(v)
        if isinstance(v, np.ndarray):
            return v.tolist()
        if isinstance(v, dict):
            return {k: _convert(vv) for k, vv in v.items()}
        if isinstance(v, list):
            return [_convert(vv) for vv in v]
        return v
    return [_convert(p) for p in picks]

# Shared thread pool for offloading synchronous screening engines.
# Each /run call is serialized behind a max_workers=3 pool to limit
# concurrent heavy computation (Kronos factor engine + PG queries).
_executor = ThreadPoolExecutor(max_workers=3)


def _auto_save_snapshot(result: dict, mode: str):
    """Auto-save screening results to JSON file and PG (fire-and-forget).

    Called after every successful screening run. Saves to:
      - outputs/snapshots/{mode}/{date}_{time_slot}.json
      - PG screening_snapshots table via recorder.record_picks()
    """
    import json, os
    from datetime import datetime

    picks = result.get("picks", [])
    if not picks:
        return

    trade_date = result.get("trade_date") or datetime.now().strftime("%Y-%m-%d")
    time_slot = result.get("time_slot") or datetime.now().strftime("%H:%M")

    # 1) JSON file snapshot
    try:
        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
        snap_dir = os.path.join(repo_root, "outputs", "snapshots", mode)
        os.makedirs(snap_dir, exist_ok=True)

        snap_path = os.path.join(snap_dir, f"{trade_date}_{time_slot.replace(':', '')}.json")
        with open(snap_path, "w") as f:
            json.dump({
                "mode": mode,
                "trade_date": trade_date,
                "time_slot": time_slot,
                "saved_at": datetime.now().isoformat(),
                "total_picks": len(picks),
                "picks": picks,
            }, f, ensure_ascii=False, indent=2, default=str)
        logger.info("Snapshot saved: %s (%d picks)", snap_path, len(picks))
    except Exception as e:
        logger.warning("Snapshot file save failed: %s", e)

    # 2) PG screening_snapshots via recorder
    try:
        model_key = mode  # e.g. 'leader_afternoon', 'bi_trend_launch'
        from kronos_factors.recorder import record_picks
        n = record_picks(model_key, trade_date, time_slot, picks)
        if n:
            logger.info("Recorder: %s %s — %d picks", model_key, trade_date, n)
    except Exception as e:
        logger.warning("Recorder save failed (PG may not be available): %s", e)


@router.get("/modes")
async def list_modes():
    """List available screening modes with descriptions."""
    return {
        "modes": [
            {"id": "leader_auction",  "name": "🔥秋神龙头竞价超预期战法 V4.3", "cycle": "1-3天",  "style": "竞价"},
            {"id": "leader_scalp",    "name": "秋神龙头战法-盘后", "cycle": "1-5天",  "style": "激进"},
            {"id": "leader_intraday", "name": "秋神龙头战法-盘中 V7.0", "cycle": "1-2天",  "style": "激进"},
            {"id": "leader_closing",  "name": "秋神龙头战法-尾盘顺势 V2.0", "cycle": "1-2天",  "style": "顺势"},
            {"id": "leader_afternoon","name": "🔥秋神龙头战法-午后选股 V1.0", "cycle": "1-2天",  "style": "午后"},
            {"id": "short",           "name": "匪爷短线多因子选股模型",       "cycle": "1-4周",  "style": "积极"},
            {"id": "long",            "name": "长线价值",         "cycle": "3-12月", "style": "稳健"},
            {"id": "all",             "name": "综合多因子",       "cycle": "1-6月",  "style": "中性"},
            {"id": "chokepoint",      "name": "大葱卡脖子选股模型",       "cycle": "1-3月",  "style": "主题"},
            {"id": "cb_floor",       "name": "匪爷可转债底价选债模型",   "cycle": "1-4周",  "style": "稳健"},
            {"id": "cb_intraday",    "name": "匪爷可转债日内投机博弈模型", "cycle": "1-2天",  "style": "激进"},
            {"id": "cb_auction",     "name": "秋神竞价概念选债模型",       "cycle": "1-2天",  "style": "竞价"},
            {"id": "bi_trend_launch","name": "毕师傅硬核科技趋势启动 V5.9", "cycle": "5-20天", "style": "趋势"},
            {"id": "bi_trend_full_market","name": "毕师傅全市场趋势启动 V1.0", "cycle": "5-20天", "style": "全市场"},
            {"id": "supply_chain",  "name": "大葱产业链解构选股", "cycle": "3-12月", "style": "中长线"},
        ]
    }


@router.post("/run")
async def run_screening(
    mode: str = Query("all", description="Screening mode"),
    top_n: int = Query(DEFAULT_TOP_N, ge=5, le=MAX_TOP_N, description="Top N picks"),
    trade_date: Optional[str] = Query(None, description="Trade date (YYYY-MM-DD), defaults to latest"),
):
    """Run stock screening with the specified mode.

    Returns ranked picks with scores, grades, entry/stop/target prices, and rationales.
    """
    if mode not in AVAILABLE_MODES:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown mode '{mode}'. Available: {AVAILABLE_MODES}"
        )

    t0 = time.time()
    loop = asyncio.get_running_loop()

    # ── Redis cache check (L4: screener results, TTL 1h) ──
    cache_key = f"screener:{mode}:{top_n}:{trade_date or 'latest'}"
    try:
        from app.cache import cache_get
        cached = await cache_get(cache_key)
        if cached:
            cached["cached"] = True
            cached["elapsed"] = round(time.time() - t0, 1)
            return cached
    except Exception:
        pass  # cache miss or Redis unavailable → proceed normally

    try:
        if mode in ("leader_scalp", "leader_intraday", "leader_auction", "leader_closing"):
            result = await loop.run_in_executor(
                _executor, _run_leader_mode, mode, top_n, trade_date
            )
        elif mode == "leader_afternoon":
            result = await loop.run_in_executor(
                _executor, _run_afternoon_mode, mode, top_n, trade_date
            )
        elif mode in ("cb_floor", "cb_intraday", "cb_auction"):
            result = await loop.run_in_executor(
                _executor, _run_cb_mode, mode, top_n, trade_date
            )
        elif mode == "bi_trend_launch":
            result = await loop.run_in_executor(
                _executor, _run_bi_trend_mode, mode, top_n, trade_date
            )
        elif mode == "bi_trend_full_market":
            result = await loop.run_in_executor(
                _executor, _run_bi_full_market_mode, mode, top_n, trade_date
            )
        else:
            result = await loop.run_in_executor(
                _executor, _run_multifactor_mode, mode, top_n, trade_date
            )
    except Exception as e:
        err = str(e)
        logger.exception("Screening failed for mode=%s: %s", mode, err)
        if any(k in err.lower() for k in ("division by zero", "'code'", "'pct_chg'", "keyerror", "none")):
            raise HTTPException(status_code=503, detail="数据不足：部分行情数据缺失或不完整，请等待数据同步完成后再试")
        if "does not exist" in err.lower():
            raise HTTPException(status_code=503, detail="数据库表缺失：部分数据表未迁移，请先运行数据同步")
        raise HTTPException(status_code=500, detail=f"Screening failed: {err}")

    result["elapsed"] = round(time.time() - t0, 1)

    # ── Sanitize numpy types across all modes ──
    if "picks" in result and result["picks"]:
        result["picks"] = _sanitize_picks(result["picks"])
        result["picks"] = _normalize_picks(result["picks"], mode)

    # ── Auto-save snapshot (JSON file + PG) — before cache to ensure persistence ──
    _auto_save_snapshot(result, mode)

    # ── Redis cache write (L4: screener results, TTL 1h) ──
    try:
        from app.cache import cache_set
        loop.create_task(cache_set(cache_key, result, ttl=3600))
    except Exception:
        pass

    return result


def _run_leader_mode(mode: str, top_n: int, trade_date: Optional[str]) -> dict:
    """Run Leader Scalp strategy (daily or intraday)."""
    from kronos_factors.engine import (
        run_leader_screening, run_intraday_screening,
        generate_execution_plan, generate_intraday_plan,
    )
    from kronos_factors.scorer._db_stub import _get_db

    # Resolve 'latest' to actual date from PG
    td = trade_date
    if not td or td == 'latest':
        try:
            with _get_db() as db:
                latest = db.execute(
                    "SELECT MAX(trade_date) FROM daily_kline"
                ).fetchone()
                if latest:
                    td = str(list(latest.values())[0]) if isinstance(latest, dict) else str(latest[0])
        except Exception:
            td = trade_date or 'latest'

    if mode == "leader_auction":
        from kronos_factors.engine.leader_auction import AuctionScalpEngine
        engine = AuctionScalpEngine()
        picks_data = engine.run(trade_date=td, top_n=top_n)
        engine.close()
        plans = generate_execution_plan(picks_data) if picks_data else []
    elif mode == "leader_intraday":
        result = run_intraday_screening(td or "latest", top_n=top_n)
        picks_data = result[0] if isinstance(result, tuple) else result
        plans = generate_intraday_plan(picks_data) if picks_data else []
    elif mode == "leader_closing":
        from kronos_factors.engine.leader_closing import run_intraday_screening as run_closing
        result = run_closing(td or "latest", time_slot="14:40", top_n=top_n)
        picks_data = result[0] if isinstance(result, tuple) else result
        plans = generate_intraday_plan(picks_data) if picks_data else []
    else:
        result = run_leader_screening(td or "latest", top_n=top_n)
        picks_data = result[0] if isinstance(result, tuple) else result
        plans = generate_execution_plan(picks_data) if picks_data else []

    picks_out = _sanitize_picks(picks_data) if picks_data else []
    picks_out = _normalize_picks(picks_out, mode)

    return {
        "mode": mode,
        "trade_date": trade_date,
        "total_picks": len(picks_out),
        "picks": picks_out,
        "execution_plans": plans,
    }


def _run_cb_mode(mode: str, top_n: int, trade_date: Optional[str]) -> dict:
    """Run convertible bond screening (cb_floor / cb_intraday / cb_auction)."""
    from kronos_factors.engine.cb_floor import CbFloorEngine
    from kronos_factors.engine.cb_intraday import CbIntradayEngine
    from kronos_factors.engine.cb_auction import CbAuctionEngine

    engine_map = {
        "cb_floor": CbFloorEngine,
        "cb_intraday": CbIntradayEngine,
        "cb_auction": CbAuctionEngine,
    }
    engine = engine_map[mode]()

    picks = engine.run(trade_date=trade_date, top_n=top_n)
    engine.close()

    picks = _sanitize_picks(picks)
    picks = _normalize_picks(picks, mode)

    return {
        "mode": mode,
        "trade_date": trade_date,
        "total_picks": len(picks),
        "picks": picks,
    }


def _run_multifactor_mode(mode: str, top_n: int, trade_date: Optional[str]) -> dict:
    """Run multi-factor mode (short/long/all/chokepoint)."""
    from kronos_factors.engine.modes import (
        ShortModeEngine, LongModeEngine, AllModeEngine, ChokepointEngine,
    )

    engine_map = {
        "short": ShortModeEngine,
        "long": LongModeEngine,
        "all": AllModeEngine,
        "chokepoint": ChokepointEngine,
    }
    engine = engine_map[mode]()
    result = engine.run(top_n=top_n)

    picks = _sanitize_picks(result.picks)
    picks = _normalize_picks(picks, mode)

    return {
        "mode": result.mode,
        "market_env": result.market_env,
        "total_scored": result.total_scored,
        "total_excluded": result.total_excluded,
        "picks": picks,
        "factor_weights": engine.get_factor_weights(),
    }


def _run_bi_trend_mode(mode: str, top_n: int, trade_date: Optional[str]) -> dict:
    """Run 毕师傅趋势启动战法 V5.9 (OBV+WR trend launch screening)."""
    from kronos_factors.engine.bi_trend_launch import BiTrendLaunchEngine, generate_bi_plan

    engine = BiTrendLaunchEngine()
    picks = engine.run(top_n=top_n, trade_date=trade_date)

    picks = _sanitize_picks(picks)
    picks = _normalize_picks(picks, mode)

    # Generate execution plans with market regime awareness
    regime = "neutral"
    plans = generate_bi_plan(picks, market_regime=regime) if picks else []

    return {
        "mode": mode,
        "trade_date": trade_date,
        "total_picks": len(picks),
        "picks": picks,
        "execution_plans": plans,
    }


def _run_bi_full_market_mode(mode: str, top_n: int, trade_date: Optional[str]) -> dict:
    """Run 毕师傅全市场趋势启动战法 V1.0 (全市场 + VR过滤)."""
    from kronos_factors.engine.bi_trend_full_market import BiTrendFullMarketEngine, generate_bi_plan

    engine = BiTrendFullMarketEngine()
    picks = engine.run(top_n=top_n, trade_date=trade_date, hard_tech_only=False)

    picks = _sanitize_picks(picks)
    picks = _normalize_picks(picks, mode)

    regime = "neutral"
    plans = generate_bi_plan(picks, market_regime=regime) if picks else []

    return {
        "mode": mode,
        "trade_date": trade_date,
        "total_picks": len(picks),
        "picks": picks,
        "execution_plans": plans,
    }


def _run_afternoon_mode(mode: str, top_n: int, trade_date: Optional[str]) -> dict:
    """Run 秋神龙头战法-午后选股 V1.0 (14:30 afternoon leader screening)."""
    from kronos_factors.engine.leader_afternoon import AfternoonLeaderEngine

    engine = AfternoonLeaderEngine()
    picks = engine.run(top_n=top_n, trade_date=trade_date, time_slot="14:30")

    picks = _sanitize_picks(picks)
    picks = _normalize_picks(picks, mode)

    return {
        "mode": mode,
        "trade_date": trade_date,
        "total_picks": len(picks),
        "picks": picks,
    }
