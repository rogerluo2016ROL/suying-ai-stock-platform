"""Policy-driven supply-chain BOM helpers for the V4 screener."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


CONFIG_PATH = Path(__file__).resolve().parents[2] / "configs" / "supply_chain_bom_v4.json"

DIM_WEIGHTS = {
    "policy": 15,
    "bom": 15,
    "chokepoint": 20,
    "growth": 15,
    "profit": 10,
    "commercialization": 15,
    "market": 10,
}


def load_bom_config(path: str | Path | None = None) -> dict[str, Any]:
    """Load the V4 policy/BOM seed config."""
    config_path = Path(path) if path else CONFIG_PATH
    data = json.loads(config_path.read_text(encoding="utf-8"))
    data.setdefault("themes", [])
    data.setdefault("nodes", [])
    data.setdefault("edges", [])
    return data


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
    """Convert V4 score dimensions into a research signal, not an order action."""
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


def _clip(value: float, upper: float) -> float:
    return round(max(0.0, min(float(value), upper)), 1)


def _evidence_score(evidence: list[dict[str, Any]], evidence_type: str, upper: float) -> float:
    matched = [float(item.get("confidence") or 0) for item in evidence if item.get("evidence_type") == evidence_type]
    if not matched:
        return round(upper * 0.35, 1)
    return _clip(sum(matched) / len(matched) * upper, upper)


def _default_bom_path(base_pick: dict[str, Any]) -> list[str]:
    chain = str(base_pick.get("chain") or base_pick.get("policy_theme") or "产业链")
    layer = str(base_pick.get("layer") or "待映射节点")
    return [chain, layer]


def score_company_v4(base_pick: dict[str, Any], evidence: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Enrich a V3 supply-chain pick with V4 policy/BOM dimensions."""
    ev = evidence or []
    policy_score = _evidence_score(ev, "policy", DIM_WEIGHTS["policy"])
    bom_score = _clip(DIM_WEIGHTS["bom"] * 0.6, DIM_WEIGHTS["bom"])
    chokepoint_score = _clip(float(base_pick.get("moat_score") or 0) / 40 * DIM_WEIGHTS["chokepoint"], DIM_WEIGHTS["chokepoint"])
    growth_score = _clip(float(base_pick.get("growth_score") or 0) / 30 * DIM_WEIGHTS["growth"], DIM_WEIGHTS["growth"])
    profit_score = _clip(float(base_pick.get("profit_score") or 0) / 15 * DIM_WEIGHTS["profit"], DIM_WEIGHTS["profit"])
    commercialization_score = _evidence_score(ev, "commercialization", DIM_WEIGHTS["commercialization"])
    market_score = _clip(float(base_pick.get("consensus_score") or 0) / 5 * DIM_WEIGHTS["market"], DIM_WEIGHTS["market"])
    risk_score = _evidence_score(ev, "risk", 10) if any(item.get("evidence_type") == "risk" for item in ev) else 0

    dimensions = {
        "policy": policy_score,
        "bom": bom_score,
        "chokepoint": chokepoint_score,
        "growth": growth_score,
        "profit": profit_score,
        "commercialization": commercialization_score,
        "market": market_score,
        "risk": risk_score,
    }
    total = sum(dimensions[k] for k in DIM_WEIGHTS) - min(risk_score, 10)
    total = _clip(total, 100)
    enriched = dict(base_pick)
    bom_path = _default_bom_path(base_pick)
    enriched.update({
        "policy_theme": base_pick.get("policy_theme") or "未来产业主攻方向",
        "bom_path": bom_path,
        "company_product_map": {
            "products": [base_pick.get("layer")] if base_pick.get("layer") else [],
            "materials": [],
        },
        "commercialization_stage": "证据待抽取",
        "chokepoint_level": "高" if dimensions["chokepoint"] >= 14 else ("中" if dimensions["chokepoint"] >= 8 else "观察"),
        "dimension_scores": dimensions,
        "v4_score": total,
        "rating": derive_rating(total),
        "trade_signal": derive_trade_signal(total, dimensions),
        "evidence": ev,
    })
    enriched["total_score"] = total
    enriched["score"] = total
    return enriched
