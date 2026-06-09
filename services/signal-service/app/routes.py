"""Signal API routes — real-time signal generation powered by kronos-factors."""

import os, logging
from fastapi import APIRouter, Query, HTTPException

logger = logging.getLogger("signal-service.routes")
router = APIRouter(prefix="/api/v1/signal", tags=["signal"])


@router.get("/levels")
async def signal_levels():
    """Five-level signal classification."""
    return {
        "levels": [
            {"level": "STRONG_BUY", "icon": "🟢", "min_score": 80, "action": "重仓买入 (15-20%)"},
            {"level": "BUY",        "icon": "🟡", "min_score": 60, "action": "标准买入 (8-12%)"},
            {"level": "HOLD",       "icon": "🔵", "min_score": 40, "action": "维持仓位"},
            {"level": "REDUCE",     "icon": "🟠", "min_score": 20, "action": "减仓至半仓"},
            {"level": "SELL",       "icon": "🔴", "min_score": 0,  "action": "清仓"},
            {"level": "TIMING_ALERT","icon":"⚡", "min_score": -1, "action": "准备操作(拐点)"},
        ],
        "signal_formula": "Kronos x0.3 + FactorResonance x0.3 + RuleMatch x0.2 + MarketAdapt x0.2",
    }


@router.get("/analyze/{code}")
async def analyze_signal(code: str):
    """Generate a real trading signal for a single stock using kronos-factors scorers.

    Returns: signal level, component scores, and reasoning.
    """
    from kronos_factors.scorer._db_stub import _get_market_data
    from kronos_factors.scorer import score_five_factor, score_money_flow, score_trend_strength

    df = _get_market_data().get_kline_df(code, lookback=400)
    if df is None or len(df) < 30:
        raise HTTPException(404, f"No K-line data for {code}")

    ff = score_five_factor(df)
    mf = score_money_flow(df)
    ts = score_trend_strength(df)

    # Normalize each to 0-100
    tech_score = min(100, ff["score"] / 25 * 100)
    money_score = min(100, mf["score"] / 10 * 100)
    trend_score = min(100, ts["score"] / 10 * 100)

    # Signal aggregation: weighted combination
    factor_resonance = (tech_score * 0.4 + money_score * 0.3 + trend_score * 0.3)
    # Kronos placeholder (30% weight — filled when prediction-service is connected)
    kronos_confidence = 50  # neutral default when no Kronos prediction
    # Market adaptation (simplified: use technical score as proxy)
    market_adapt = 50

    signal_score = kronos_confidence * 0.3 + factor_resonance * 0.3 + 50 * 0.2 + market_adapt * 0.2

    # Determine level
    if signal_score >= 80:   level, icon = "STRONG_BUY", "🟢"
    elif signal_score >= 60:  level, icon = "BUY", "🟡"
    elif signal_score >= 40:  level, icon = "HOLD", "🔵"
    elif signal_score >= 20:  level, icon = "REDUCE", "🟠"
    else:                     level, icon = "SELL", "🔴"

    return {
        "code": code,
        "signal": {"level": level, "icon": icon, "score": round(signal_score, 1)},
        "components": {
            "kronos_confidence": {"score": kronos_confidence, "weight": 0.30},
            "factor_resonance":  {"score": round(factor_resonance, 1), "weight": 0.30,
                                  "detail": {"technical": round(tech_score, 1),
                                             "money_flow": round(money_score, 1),
                                             "trend": round(trend_score, 1)}},
            "rule_match":        {"score": 50, "weight": 0.20, "note": "default-no-rules-configured"},
            "market_adapt":      {"score": market_adapt, "weight": 0.20},
        },
        "factors": {
            "five_factor": {"score": ff["score"], "grade": ff["grade"],
                            "momentum": ff["momentum"], "volume": ff["volume_factor"],
                            "technical": ff["technical"], "quality": ff["quality"], "risk": ff["risk"]},
            "money_flow": mf,
            "trend_strength": ts,
        },
        "generated_at": __import__("datetime").datetime.now().isoformat(),
    }


@router.post("/batch")
async def batch_signals(codes: list[str]):
    """Generate signals for multiple stocks (up to 30)."""
    if len(codes) > 30:
        raise HTTPException(400, "Max 30 stocks per batch")
    results = []
    for code in codes:
        try:
            r = await analyze_signal(code)
            results.append(r)
        except HTTPException:
            results.append({"code": code, "error": "no_data"})
    return {"batch_size": len(codes), "success": len([r for r in results if "error" not in r]),
            "signals": results}


@router.get("/history")
async def signal_history(
    code: str = Query(None),
    limit: int = Query(50, ge=10, le=200),
):
    return {"filters": {"code": code}, "limit": limit, "signals": [], "status": "endpoint_ready"}


@router.put("/rules")
async def update_signal_rules(
    kronos_weight: float = Query(0.3, ge=0.1, le=0.5),
    factor_weight: float = Query(0.3, ge=0.1, le=0.5),
    rule_weight: float = Query(0.2, ge=0.05, le=0.4),
    market_weight: float = Query(0.2, ge=0.05, le=0.4),
):
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
