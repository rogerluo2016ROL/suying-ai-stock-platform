"""Reusable V5 scoring rules for policy-driven supply-chain BOM picks.

The module is intentionally pure: no database, Tushare, or filesystem access.
Production APIs, persistence scripts, and OOS validation should call these
functions so scoring semantics do not drift across entry points.
"""

from __future__ import annotations

from typing import Any

DIM_WEIGHTS = {
    "policy": 15,
    "bom": 15,
    "chokepoint": 20,
    "growth": 15,
    "profit": 10,
    "commercialization": 15,
    "market": 10,
}

CHOKEPOINT_WEIGHTS = {
    "垄断": 5,
    "独家": 5,
    "首家": 5,
    "稀缺": 5,
    "寡头": 5,
    "唯一": 5,
    "国产替代": 4,
    "进口替代": 4,
    "自主可控": 4,
    "打破垄断": 5,
    "卡脖子": 4,
    "客户验证": 3,
    "认证": 3,
    "供应商": 3,
    "定点": 3,
    "进入供应链": 3,
}

COMMERCIALIZATION_RANK = ["放量/订单", "量产", "小批量", "样品/研发"]
COMMERCIALIZATION_SCORE = {
    "放量/订单": 12.0,
    "量产": 9.0,
    "小批量": 6.0,
    "样品/研发": 3.0,
    "未识别": 2.0,
}


def _clip(value: float, upper: float) -> float:
    return round(max(0.0, min(float(value), upper)), 1)


def _to_float(value: Any, default: float | None = None) -> float | None:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def derive_rating(total_score: float) -> str:
    if total_score >= 85:
        return "S"
    if total_score >= 75:
        return "A"
    if total_score >= 65:
        return "B"
    if total_score >= 50:
        return "C"
    return "D"


# V6 Three-factor resonance scoring constants
INDUSTRY_CYCLE_SCORE = {
    "放量": 12.0,
    "放量/订单": 12.0,
    "量产": 9.0,
    "小批量": 6.0,
    "样品": 3.0,
    "样品/研发": 3.0,
    "研发": 3.0,
    "未识别": 2.0,
}

PERFORMANCE_YIELD_SCORE = {
    (100, float("inf")): 20.0,
    (50, 100): 15.0,
    (20, 50): 10.0,
    (0, 20): 5.0,
}


def derive_trade_signal(total_score: float, dimension_scores: dict[str, float]) -> str:
    """Convert V5 score dimensions into a research signal, not an order action."""
    if total_score < 50 or dimension_scores.get("risk", 0) >= 8:
        return "风险回避"
    commercialization = dimension_scores.get("commercialization", 0)
    market = dimension_scores.get("market", 0)
    policy = dimension_scores.get("policy", 0)
    bom = dimension_scores.get("bom", 0)
    growth = dimension_scores.get("growth", 0)
    if total_score >= 85 and commercialization >= 12 and market >= 8:
        return "强启动"
    if total_score >= 75 and commercialization >= 10 and market >= 6:
        return "启动"
    strong_dims = sum(1 for value in (policy, bom, growth) if value >= 10)
    if total_score >= 75 and strong_dims >= 2:
        return "关注"
    return "观察"


def score_bom_ratio(main_pct: float | None) -> float:
    """Score node concentration from product/main-business revenue share."""
    ratio = _to_float(main_pct, 0.0) or 0.0
    if ratio >= 80:
        return 15.0
    if ratio >= 50:
        return 12.0
    if ratio >= 25:
        return 8.0
    if ratio >= 10:
        return 4.0
    return 2.0


def score_chokepoint_hits(keyword_counts: dict[str, int]) -> float:
    """Diversity-weighted chokepoint score: one keyword counts at most twice."""
    total = 0.0
    for keyword, count in keyword_counts.items():
        total += min(int(count or 0), 2) * CHOKEPOINT_WEIGHTS.get(str(keyword), 2)
    return _clip(total, DIM_WEIGHTS["chokepoint"])


def score_growth(
    q_sales_yoy: float | None,
    netprofit_yoy: float | None,
    forecast_max: float | None = None,
    forecast_type: str | None = None,
) -> tuple[float, str]:
    """Score growth using visible financial growth first, forecast as fallback."""
    sales = _to_float(q_sales_yoy)
    profit = _to_float(netprofit_yoy)
    values = [v for v in (sales, profit) if v is not None]
    if values:
        growth = max(values)
        note = f"财务yoy{growth:.0f}%"
        if growth >= 100:
            return 15.0, note
        if growth >= 50:
            return 12.0, note
        if growth >= 20:
            return 9.0, note
        if growth >= 0:
            return 6.0, note
        return 3.0, f"{note}(负)"

    forecast = _to_float(forecast_max)
    if forecast is not None and forecast_type and "预增" in str(forecast_type):
        note = f"预告预增{forecast:.0f}%"
        if forecast >= 100:
            return 15.0, note
        if forecast >= 50:
            return 12.0, note
        return 9.0, note
    return 6.0, "中性(无财务无预告)"


def score_profit(gross_margin: float | None) -> tuple[float, str]:
    """Score profitability from gross margin with manufacturing-friendly thresholds."""
    margin = _to_float(gross_margin)
    if margin is None:
        return 6.0, "中性(无财务)"
    note = f"毛利率{margin:.0f}%"
    if margin >= 50:
        return 10.0, note
    if margin >= 30:
        return 7.0, note
    if margin >= 15:
        return 4.0, note
    return 2.0, f"{note}(低)"


def score_commercialization(
    stage_hits: set[str],
    forecast_type: str | None = None,
) -> tuple[float, str]:
    top = next((stage for stage in COMMERCIALIZATION_RANK if stage in stage_hits), "未识别")
    score = COMMERCIALIZATION_SCORE[top]
    note = top
    if forecast_type and "预增" in str(forecast_type) and score >= 9:
        score = min(score + 3, DIM_WEIGHTS["commercialization"])
        note = f"{top}+业绩兑现"
    return float(score), note


def score_market(evidence_count: int) -> float:
    count = int(evidence_count or 0)
    if count >= 20:
        return 10.0
    if count >= 10:
        return 7.0
    if count >= 5:
        return 5.0
    if count >= 1:
        return 3.0
    return 1.0


def extract_v5_evidence_features(evidence: list[dict[str, Any]] | None) -> dict[str, Any]:
    keyword_counts: dict[str, int] = {}
    stage_hits: set[str] = set()
    risk_score = 0.0
    items = [item for item in (evidence or []) if isinstance(item, dict)]
    for item in items:
        for keyword in _as_list(item.get("keywords") or item.get("chokepoint")):
            if keyword:
                text = str(keyword)
                keyword_counts[text] = keyword_counts.get(text, 0) + 1
        for stage in _as_list(item.get("stage") or item.get("stages")):
            if stage:
                stage_hits.add(str(stage))
        if item.get("evidence_type") == "risk":
            risk_score = max(risk_score, float(item.get("confidence") or 0) * 10)
    return {
        "evidence_count": len(items),
        "keyword_counts": keyword_counts,
        "stage_hits": stage_hits,
        "risk": _clip(risk_score, 10),
    }


def score_company_v5(base_pick: dict[str, Any], evidence: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Return a V5-scored pick while preserving the caller's original fields."""
    features = extract_v5_evidence_features(evidence)
    growth, growth_note = score_growth(
        base_pick.get("q_sales_yoy", base_pick.get("revenue_growth")),
        base_pick.get("netprofit_yoy", base_pick.get("profit_growth")),
        base_pick.get("forecast_max"),
        base_pick.get("forecast_type"),
    )
    profit, profit_note = score_profit(base_pick.get("gross_margin"))
    commercialization, commercialization_note = score_commercialization(
        features["stage_hits"],
        base_pick.get("forecast_type"),
    )

    dimensions = {
        "policy": _clip(base_pick.get("policy_score", 12.0), DIM_WEIGHTS["policy"]),
        "bom": score_bom_ratio(base_pick.get("main_pct", base_pick.get("main_ratio"))),
        "chokepoint": score_chokepoint_hits(features["keyword_counts"]),
        "growth": growth,
        "profit": profit,
        "commercialization": commercialization,
        "market": score_market(features["evidence_count"]),
        "risk": features["risk"],
    }
    total = sum(dimensions[key] for key in DIM_WEIGHTS) - min(dimensions["risk"], 10)
    total = _clip(total, 100)
    enriched = dict(base_pick)
    enriched.update({
        "dimension_scores": dimensions,
        "total_score": total,
        "score": total,
        "rating": derive_rating(total),
        "trade_signal": derive_trade_signal(total, dimensions),
        "growth_note": growth_note,
        "profit_note": profit_note,
        "commercialization_note": commercialization_note,
        "evidence": evidence or [],
        "model_version": "supply_chain_bom_v5",
    })
    return enriched


def _score_industry_cycle(stage: str | None) -> float:
    """Score industry cycle stage (V6 three-factor: 产业周期)."""
    if stage is None:
        return INDUSTRY_CYCLE_SCORE["未识别"]
    stage_str = str(stage).strip()
    return INDUSTRY_CYCLE_SCORE.get(stage_str, INDUSTRY_CYCLE_SCORE["未识别"])


def _score_policy_intensity(policy_score: float | None, relevance: float | None = None) -> float:
    """Score policy intensity (V6 three-factor: 政策强度).

    policy_score may be a 0-15 direct score. When policy_relevance is provided,
    1-5 star scores are converted to the 0-15 range before applying relevance.
    """
    policy = _to_float(policy_score, 0.0) or 0.0
    if relevance is None:
        return _clip(policy, 15.0)

    rel = _to_float(relevance, 1.0)
    rel = 1.0 if rel is None else rel
    if policy > 5:
        return _clip(policy * rel, 15.0)
    return _clip(policy * 3.0 * rel, 15.0)


def _score_performance_yield(yoy: float | None) -> float:
    """Score performance yield (V6 three-factor: 业绩兑现).

    Based on revenue/profit YoY growth:
    - yoy >= 100%: 20 points
    - yoy >= 50%: 15 points
    - yoy >= 20%: 10 points
    - yoy >= 0%: 5 points
    - yoy < 0%: 0 points
    """
    if yoy is None:
        return 0.0
    growth = _to_float(yoy, 0.0) or 0.0
    for (lower, upper), score in PERFORMANCE_YIELD_SCORE.items():
        if lower <= growth < upper:
            return score
    if growth >= 100:
        return 20.0
    return 0.0


def derive_resonance_v6(pick: dict[str, Any], stage: str | None = None) -> dict[str, Any]:
    """Calculate three-factor resonance score and determine startup signal.

    Three factors:
    1. Industry cycle (产业周期): commercialization stage score
    2. Policy intensity (政策强度): policy_score * relevance
    3. Performance yield (业绩兑现): revenue/profit YoY growth score

    Resonance determination:
    - All 3 factors pass threshold (强启动 threshold): "强启动"
    - 2 factors pass threshold (启动 threshold): "启动"
    - 1 factor passes threshold: "关注"
    - 0 factors: "观察"

    Thresholds:
    - Industry cycle >= 9.0 (量产及以上)
    - Policy intensity >= 9.0
    - Performance yield >= 15.0 (yoy >= 50%)

    Returns dict with:
        - industry_cycle_score: float
        - policy_intensity_score: float
        - performance_yield_score: float
        - resonance_factors: int (count of factors passing threshold)
        - resonance_signal: str ("强启动"/"启动"/"关注"/"观察")
        - resonance_details: dict with per-factor pass/fail status
    """
    # Factor 1: Industry cycle (产业周期)
    industry_cycle_score = _score_industry_cycle(stage)

    # Factor 2: Policy intensity (政策强度)
    policy_intensity_score = _score_policy_intensity(
        pick.get("policy_score"),
        pick.get("policy_relevance")
    )

    # Factor 3: Performance yield (业绩兑现)
    # Use max of revenue_yoy and profit_yoy
    revenue_yoy = _to_float(pick.get("q_sales_yoy") or pick.get("revenue_yoy") or pick.get("revenue_growth"))
    profit_yoy = _to_float(pick.get("netprofit_yoy") or pick.get("profit_yoy") or pick.get("profit_growth"))
    best_yoy = max((y for y in [revenue_yoy, profit_yoy] if y is not None), default=None)
    performance_yield_score = _score_performance_yield(best_yoy)

    # Thresholds for resonance
    INDUSTRY_CYCLE_THRESHOLD = 9.0  # 量产及以上
    POLICY_INTENSITY_THRESHOLD = 9.0
    PERFORMANCE_YIELD_THRESHOLD = 15.0  # yoy >= 50%

    # Count factors passing threshold
    factors = [
        (industry_cycle_score >= INDUSTRY_CYCLE_THRESHOLD, "industry_cycle"),
        (policy_intensity_score >= POLICY_INTENSITY_THRESHOLD, "policy_intensity"),
        (performance_yield_score >= PERFORMANCE_YIELD_THRESHOLD, "performance_yield"),
    ]
    resonance_count = sum(1 for passed, _ in factors if passed)

    # Determine resonance signal
    if resonance_count >= 3:
        resonance_signal = "强启动"
    elif resonance_count == 2:
        resonance_signal = "启动"
    elif resonance_count == 1:
        resonance_signal = "关注"
    else:
        resonance_signal = "观察"

    return {
        "industry_cycle_score": industry_cycle_score,
        "policy_intensity_score": policy_intensity_score,
        "performance_yield_score": performance_yield_score,
        "resonance_factors": resonance_count,
        "resonance_signal": resonance_signal,
        "resonance_details": {
            "industry_cycle_passed": factors[0][0],
            "policy_intensity_passed": factors[1][0],
            "performance_yield_passed": factors[2][0],
        },
        "thresholds": {
            "industry_cycle": INDUSTRY_CYCLE_THRESHOLD,
            "policy_intensity": POLICY_INTENSITY_THRESHOLD,
            "performance_yield": PERFORMANCE_YIELD_THRESHOLD,
        },
    }


CHOKEPOINT_CORE_KEYWORDS = frozenset({
    "垄断", "独家", "首家", "稀缺", "寡头", "唯一", "打破垄断", "卡脖子",
})

CHOKEPOINT_KEY_KEYWORDS = frozenset({
    "国产替代", "进口替代", "自主可控", "客户验证", "认证", "供应商", "定点", "进入供应链",
})


def classify_chokepoint_level(score: float, keywords: list[str] | None = None) -> str:
    """Classify chokepoint level based on score and keywords.

    Classification rules:
    1. "卡脖子核心": score >= 10 AND has core keywords (垄断/独家/首家/稀缺/寡头/唯一/打破垄断/卡脖子)
    2. "关键环节": score >= 6 OR has key keywords (国产替代/进口替代/自主可控/客户验证/认证/供应商/定点/进入供应链)
    3. "普通": otherwise

    Args:
        score: Chokepoint dimension score (0-20)
        keywords: List of chokepoint keywords found in evidence

    Returns:
        "卡脖子核心" / "关键环节" / "普通"
    """
    keyword_set = set(str(kw).strip() for kw in (keywords or []) if kw)
    has_core_keyword = bool(keyword_set & CHOKEPOINT_CORE_KEYWORDS)
    has_key_keyword = bool(keyword_set & CHOKEPOINT_KEY_KEYWORDS)

    if score >= 10 and has_core_keyword:
        return "卡脖子核心"
    if score >= 6 or has_key_keyword:
        return "关键环节"
    return "普通"
