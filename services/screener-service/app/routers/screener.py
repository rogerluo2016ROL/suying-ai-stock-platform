"""Screener API routes — 6 screening modes via unified endpoint."""

import time
from typing import Optional
from fastapi import APIRouter, Query, HTTPException

from app.config import AVAILABLE_MODES, DEFAULT_TOP_N, MAX_TOP_N

router = APIRouter(prefix="/api/v1/screener", tags=["screener"])


@router.get("/modes")
async def list_modes():
    """List available screening modes with descriptions."""
    return {
        "modes": [
            {"id": "leader_scalp",    "name": "龙头战法 (收盘后)", "cycle": "1-5天",  "style": "激进"},
            {"id": "leader_intraday", "name": "龙头战法 (盘中)",   "cycle": "1-2天",  "style": "激进"},
            {"id": "short",           "name": "短线多因子",       "cycle": "1-4周",  "style": "积极"},
            {"id": "long",            "name": "长线价值",         "cycle": "3-12月", "style": "稳健"},
            {"id": "all",             "name": "综合多因子",       "cycle": "1-6月",  "style": "中性"},
            {"id": "chokepoint",      "name": "卡脖子专题",       "cycle": "1-3月",  "style": "主题"},
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

    try:
        if mode in ("leader_scalp", "leader_intraday"):
            result = _run_leader_mode(mode, top_n, trade_date)
        else:
            result = _run_multifactor_mode(mode, top_n, trade_date)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Screening failed: {str(e)}")

    result["elapsed"] = round(time.time() - t0, 1)
    return result


def _run_leader_mode(mode: str, top_n: int, trade_date: Optional[str]) -> dict:
    """Run Leader Scalp strategy (daily or intraday)."""
    from kronos_factors.engine import (
        run_leader_screening, run_intraday_screening,
        generate_execution_plan, generate_intraday_plan,
    )

    if mode == "leader_intraday":
        picks_data = run_intraday_screening(trade_date or "latest", top_n=top_n)
        plans = generate_intraday_plan(picks_data) if picks_data else []
    else:
        picks_data = run_leader_screening(trade_date or "latest", top_n=top_n)
        plans = generate_execution_plan(picks_data) if picks_data else []

    return {
        "mode": mode,
        "trade_date": trade_date,
        "total_picks": len(picks_data) if picks_data else 0,
        "picks": picks_data if picks_data else [],
        "execution_plans": plans,
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
