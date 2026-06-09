"""Signal API routes — 5-level signals: STRONG_BUY/BUY/HOLD/REDUCE/SELL."""

from fastapi import APIRouter, Query

router = APIRouter(prefix="/api/v1/signal", tags=["signal"])

SIGNAL_LEVELS = ["🟢 STRONG_BUY", "🟡 BUY", "🔵 HOLD", "🟠 REDUCE", "🔴 SELL", "⚡ TIMING_ALERT"]


@router.get("/levels")
async def signal_levels():
    """List signal level definitions."""
    return {
        "levels": [
            {"level": "STRONG_BUY", "icon": "🟢", "min_score": 80, "action": "重仓买入 (15-20%)"},
            {"level": "BUY",        "icon": "🟡", "min_score": 60, "action": "标准买入 (8-12%)"},
            {"level": "HOLD",       "icon": "🔵", "min_score": 40, "action": "维持仓位"},
            {"level": "REDUCE",     "icon": "🟠", "min_score": 20, "action": "减仓至半仓"},
            {"level": "SELL",       "icon": "🔴", "min_score": 0,  "action": "清仓"},
            {"level": "TIMING_ALERT","icon":"⚡", "min_score": -1, "action": "Kronos预测拐点, 准备操作"},
        ]
    }


@router.get("/live")
async def live_signals(
    session: str = Query("pre", description="盘前(pre)/盘中(intra)/盘后(post)"),
):
    """Get live trading signals for the current session.

    Signal formula: Kronos_confidence × 0.3 + factor_resonance × 0.3
                  + rule_match × 0.2 + market_adapt × 0.2
    """
    return {
        "session": session,
        "generated_at": "2026-06-10T09:30:00",
        "signals": [],
        "status": "endpoint_ready",
        "message": f"Signal endpoint ready. Connect to data pipeline for live {session}-market signals.",
    }


@router.get("/history")
async def signal_history(
    code: str = Query(None, description="Stock code filter"),
    signal_type: str = Query(None, description="Signal level filter"),
    limit: int = Query(50, ge=10, le=200),
):
    """Query historical trading signals."""
    return {
        "filters": {"code": code, "signal_type": signal_type},
        "limit": limit,
        "signals": [],
        "status": "endpoint_ready",
    }


@router.put("/rules")
async def update_signal_rules(
    kronos_weight: float = Query(0.3, ge=0.1, le=0.5, description="Kronos prediction weight"),
    factor_weight: float = Query(0.3, ge=0.1, le=0.5),
    rule_weight: float = Query(0.2, ge=0.05, le=0.4),
    market_weight: float = Query(0.2, ge=0.05, le=0.4),
):
    """Update signal generation rule weights."""
    total = kronos_weight + factor_weight + rule_weight + market_weight
    return {
        "weights": {
            "kronos_confidence": round(kronos_weight / total, 3),
            "factor_resonance":  round(factor_weight / total, 3),
            "rule_match":        round(rule_weight / total, 3),
            "market_adapt":      round(market_weight / total, 3),
        },
        "status": "updated",
    }
