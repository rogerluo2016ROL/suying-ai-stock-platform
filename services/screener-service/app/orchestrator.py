"""Mode Orchestrator — routes screening modes to strategy engines."""
import logging
from typing import Optional

logger = logging.getLogger("screener.orchestrator")

# Strategy engine registry (lazy import to avoid circular deps)
_ENGINES = {}

def _get_engine(mode: str):
    if mode in _ENGINES:
        return _ENGINES[mode]
    try:
        from kronos_factors.engine.modes import (
            ChokepointEngine, ShortModeEngine, LongModeEngine, AllModeEngine
        )
        from kronos_factors.engine.leader_scalp import LeaderScalpEngine
        from kronos_factors.engine.leader_intraday import IntradayScalpEngine
        
        _ENGINES.update({
            "leader_scalp": LeaderScalpEngine,
            "intraday": IntradayScalpEngine,
            "short": ShortModeEngine,
            "long": LongModeEngine,
            "all": AllModeEngine,
            "chokepoint": ChokepointEngine,
        })
        return _ENGINES.get(mode)
    except ImportError as e:
        logger.error("Failed to load engines: %s", e)
        return None

async def run_screening(mode: str, top_n: int = 30, use_kronos: bool = False) -> dict:
    """Execute stock screening via the specified mode engine.
    
    Returns: {picks: [...], mode, top_n, engine_version}
    """
    engine_cls = _get_engine(mode)
    if not engine_cls:
        return {"error": f"Unknown mode: {mode}", "available": list(_ENGINES.keys())}
    
    try:
        engine = engine_cls()
        result = engine.run(top_n=top_n)
        return {"picks": result, "mode": mode, "top_n": top_n}
    except Exception as e:
        logger.exception("Screening failed for mode=%s", mode)
        return {"error": str(e), "mode": mode}

def get_available_modes() -> list[str]:
    """Return list of registered screening modes."""
    return list(_ENGINES.keys()) if _ENGINES else [
        "leader_scalp", "intraday", "short", "long", "all", "chokepoint"
    ]
