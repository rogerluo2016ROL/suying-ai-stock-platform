"""Mode Orchestrator — V4.0 multi-strategy fusion + Kronos prediction + pipeline."""
import asyncio
import logging
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

logger = logging.getLogger("screener.orchestrator")

# Strategy engine registry (lazy import)
_ENGINES = {}
_executor = ThreadPoolExecutor(max_workers=3)

def _get_engine(mode: str):
    if mode in _ENGINES:
        return _ENGINES[mode]
    try:
        from kronos_factors.engine.modes import (
            ChokepointEngine, ShortModeEngine, LongModeEngine, AllModeEngine
        )
        from kronos_factors.engine.leader_scalp import LeaderScalpEngine
        from kronos_factors.engine.leader_intraday import IntradayScalpEngine
        from kronos_factors.engine.leader_auction import AuctionScalpEngine
        from kronos_factors.engine.cb_floor import CbFloorEngine
        from kronos_factors.engine.cb_intraday import CbIntradayEngine
        from kronos_factors.engine.cb_auction import CbAuctionEngine

        _ENGINES.update({
            "leader_scalp": LeaderScalpEngine,
            "leader_auction": AuctionScalpEngine,
            "intraday": IntradayScalpEngine,
            "short": ShortModeEngine,
            "long": LongModeEngine,
            "all": AllModeEngine,
            "chokepoint": ChokepointEngine,
            "cb_floor": CbFloorEngine,
            "cb_intraday": CbIntradayEngine,
            "cb_auction": CbAuctionEngine,
        })
        return _ENGINES.get(mode)
    except ImportError as e:
        logger.error("Failed to load engines: %s", e)
        return None


async def run_screening(mode: str, top_n: int = 30, trade_date: str = None) -> dict:
    """Execute stock screening via the specified mode engine."""
    engine_cls = _get_engine(mode)
    if not engine_cls:
        return {"error": f"Unknown mode: {mode}", "available": list(_ENGINES.keys())}

    try:
        engine = engine_cls()
        loop = asyncio.get_running_loop()
        kwargs = {"top_n": top_n}
        if trade_date:
            kwargs["trade_date"] = trade_date
        result = await loop.run_in_executor(None, lambda: engine.run(**kwargs))
        return {"picks": result, "mode": mode, "top_n": top_n}
    except Exception as e:
        err = str(e)
        logger.exception("Screening failed for mode=%s", mode)
        if "division by zero" in err.lower():
            return {"error": "数据不足：缺少行情数据，请先同步日线数据后再试", "mode": mode}
        if "does not exist" in err.lower():
            return {"error": "数据库表缺失：部分数据表未迁移，请检查数据同步状态", "mode": mode}
        return {"error": f"选股失败: {err}", "mode": mode}


# ── V4.0 Multi-strategy fusion ──

async def run_fusion_screening(modes: list[str], top_n: int = 30,
                               trade_date: str = None) -> dict:
    """V4.0 多策略并行 → 共识融合 → Kronos 预测.

    Runs multiple strategies in parallel, merges results by consensus,
    and optionally enriches with Kronos 30-day predictions.

    Args:
        modes: list of strategy modes (default: leader_scalp + short)
        top_n: picks per strategy
        trade_date: trading date

    Returns: {consensus: [...], strategies: {...}, fusion_stats: {...}}
    """
    if not modes:
        modes = ["leader_scalp", "short"]

    t0 = time.time()
    strategy_results = {}

    # Run all strategies in parallel
    def _run_one(mode):
        engine_cls = _get_engine(mode)
        if not engine_cls:
            return mode, None
        try:
            engine = engine_cls()
            kwargs = {"top_n": top_n}
            if trade_date:
                kwargs["trade_date"] = trade_date
            result = engine.run(**kwargs)
            # Normalize result to list of dicts
            if hasattr(result, 'picks'):
                result = result.picks
            if hasattr(result, 'results'):
                result = result.results
            if isinstance(result, dict) and 'picks' in result:
                result = result['picks']
            if not isinstance(result, list):
                result = []
            return mode, result
        except Exception as e:
            logger.error("Strategy %s failed: %s", mode, e)
            return mode, []

    with ThreadPoolExecutor(max_workers=len(modes)) as pool:
        futures = {pool.submit(_run_one, m): m for m in modes}
        for f in futures:
            mode, result = f.result()
            if result is not None:
                strategy_results[mode] = result

    # V4.0 consensus fusion: stocks picked by ≥2 strategies get weighted boost
    consensus = merge_picks(strategy_results, top_n)

    elapsed = time.time() - t0
    return {
        "consensus": consensus,
        "strategies": {k: len(v) for k, v in strategy_results.items()},
        "fusion_stats": {
            "modes_used": len(strategy_results),
            "total_candidates": sum(len(v) for v in strategy_results.values()),
            "consensus_count": len(consensus),
            "elapsed_sec": round(elapsed, 1),
        },
    }


def merge_picks(strategy_results: dict, top_n: int = 30) -> list[dict]:
    """V4.0 consensus fusion — stocks picked by multiple strategies get higher weight.

    Scoring: base = individual score, +10 per additional strategy that picked it,
             +5 if picked by leader_scalp (highest precision).
    """
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
            # Keep highest-scored entry
            p_score = p.get("total_score", p.get("score", 50))
            if p_score > s["score"]:
                s["score"] = p_score
                s["data"] = p
            # Consensus boost
            boost = 10 if mode == "leader_scalp" else 5
            s["score"] += boost

    # Sort by count (consensus) then score
    ranked = sorted(stock_scores.items(),
                    key=lambda x: (x[1]["count"], x[1]["score"]), reverse=True)
    result = []
    for code, info in ranked[:top_n]:
        entry = {**info["data"], "consensus_count": info["count"],
                 "consensus_strategies": info["strategies"]}
        result.append(entry)
    return result


def get_available_modes() -> list[str]:
    """Return list of registered screening modes."""
    return list(_ENGINES.keys()) if _ENGINES else [
        "leader_scalp", "intraday", "short", "long", "all", "chokepoint"
    ]
