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
            {"id": "leader_auction",  "name": "🔥竞价超预期 V4.3", "cycle": "1-3天",  "style": "竞价"},
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
        if mode in ("leader_scalp", "leader_intraday", "leader_auction"):
            result = _run_leader_mode(mode, top_n, trade_date)
        else:
            result = _run_multifactor_mode(mode, top_n, trade_date)
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
