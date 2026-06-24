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
