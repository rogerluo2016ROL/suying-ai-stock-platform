"""Screener API routes — 9 screening modes via unified endpoint."""

import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Optional
from fastapi import APIRouter, Query, HTTPException

from app.config import AVAILABLE_MODES, DEFAULT_TOP_N, MAX_TOP_N

router = APIRouter(prefix="/api/v1/screener", tags=["screener"])

# Shared thread pool for offloading synchronous screening engines.
# Each /run call is serialized behind a max_workers=3 pool to limit
# concurrent heavy computation (Kronos factor engine + PG queries).
_executor = ThreadPoolExecutor(max_workers=3)


@router.get("/modes")
async def list_modes():
    """List available screening modes with descriptions."""
    return {
        "modes": [
            {"id": "leader_auction",  "name": "🔥秋神龙头竞价超预期战法 V4.3", "cycle": "1-3天",  "style": "竞价"},
            {"id": "leader_scalp",    "name": "秋神龙头战法-盘后", "cycle": "1-5天",  "style": "激进"},
            {"id": "leader_intraday", "name": "秋神龙头战法-盘中 V7.0", "cycle": "1-2天",  "style": "激进"},
            {"id": "leader_closing",  "name": "秋神龙头战法-尾盘顺势 V2.0", "cycle": "1-2天",  "style": "顺势"},
            {"id": "short",           "name": "匪爷短线多因子选股模型",       "cycle": "1-4周",  "style": "积极"},
            {"id": "long",            "name": "长线价值",         "cycle": "3-12月", "style": "稳健"},
            {"id": "all",             "name": "综合多因子",       "cycle": "1-6月",  "style": "中性"},
            {"id": "chokepoint",      "name": "大葱卡脖子选股模型",       "cycle": "1-3月",  "style": "主题"},
            {"id": "cb_floor",       "name": "匪爷可转债底价选债模型",   "cycle": "1-4周",  "style": "稳健"},
            {"id": "cb_intraday",    "name": "匪爷可转债日内投机博弈模型", "cycle": "1-2天",  "style": "激进"},
            {"id": "cb_auction",     "name": "秋神竞价概念选债模型",       "cycle": "1-2天",  "style": "竞价"},
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

    try:
        if mode in ("leader_scalp", "leader_intraday", "leader_auction", "leader_closing"):
            result = await loop.run_in_executor(
                _executor, _run_leader_mode, mode, top_n, trade_date
            )
        elif mode in ("cb_floor", "cb_intraday", "cb_auction"):
            result = await loop.run_in_executor(
                _executor, _run_cb_mode, mode, top_n, trade_date
            )
        else:
            result = await loop.run_in_executor(
                _executor, _run_multifactor_mode, mode, top_n, trade_date
            )
    except Exception as e:
        err = str(e)
        if any(k in err.lower() for k in ("division by zero", "'code'", "'pct_chg'", "keyerror", "none")):
            raise HTTPException(status_code=503, detail="数据不足：部分行情数据缺失或不完整，请等待数据同步完成后再试")
        if "does not exist" in err.lower():
            raise HTTPException(status_code=503, detail="数据库表缺失：部分数据表未迁移，请先运行数据同步")
        raise HTTPException(status_code=500, detail=f"Screening failed: {err}")

    result["elapsed"] = round(time.time() - t0, 1)
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

    return {
        "mode": mode,
        "trade_date": trade_date,
        "total_picks": len(picks_data) if picks_data else 0,
        "picks": picks_data if picks_data else [],
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

    return {
        "mode": result.mode,
        "market_env": result.market_env,
        "total_scored": result.total_scored,
        "total_excluded": result.total_excluded,
        "picks": result.picks,
        "factor_weights": engine.get_factor_weights(),
    }
