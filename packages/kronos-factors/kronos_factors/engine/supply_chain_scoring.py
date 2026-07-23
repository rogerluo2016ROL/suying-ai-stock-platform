"""Supply-chain business-tag 双评分(三高 / 预期差)唯一实现。

公式口径以 tools/supply_chain_data_collection_center.py 的 refresh 实现为准,
采集中心(refresh-expectation-scores)、screener-service 实时评分端点、
backfill_supply_chain_expectation_gap_history.py 三方统一从这里 import,
避免同一指标两套公式漂移。

注意:公式与过滤口径(review_status='approved')变更不追溯重算历史分数,
历史快照按写入时口径保留,新分数由后续 refresh/backfill 自然覆盖。

分数口径变更记录:
- 2026-07(阶段二B) expectation_gap_score 映射变更:
  旧口径 expectation_gap_score=clamp(raw_gap, 0, 100),负预期差全部截断为 0,丢失幅度;
  新口径 expectation_gap_score=clamp((raw_gap+100)/2, 0, 100),50=中性(0 偏离),
  <50 为负预期差且保留幅度,raw_gap 字段始终保留原始值,gap_type 仍按 raw_gap ±15 判定。
- 2026-07(阶段二B) classify_business_tag_events 增加事件去重:
  同 code + 标准化标题(小写去空白去标点) + 同 event_date 的重复事件只计一次
  (保留 confidence 最高),去重数量经返回 stats 的 dedup_removed 透出。
"""

from __future__ import annotations

import json
from typing import Any

RESEARCH_STAGE_SCORE = {
    "R0": 0.0,
    "R1": 15.0,
    "R2": 30.0,
    "R3": 45.0,
    "R4": 60.0,
    "R5": 75.0,
    "R6": 90.0,
}
COMMERCIAL_STAGE_SCORE = {
    "C0": 0.0,
    "C1": 20.0,
    "C2": 40.0,
    "C3": 60.0,
    "C4": 80.0,
    "C5": 95.0,
}

ANALYST_CLAIM_SOURCE_TYPES = frozenset({
    "analyst_estimate",
    "broker_report",
    "research_report",
    "profit_forecast",
})
NEWS_CLAIM_SOURCE_TYPES = frozenset({
    "financial_news",
    "media_report",
    "news",
})

EXPECTATION_GAP_FORMULA = (
    "actual_progress - market_expectation + evidence*0.22 "
    "+ prosperity_delta*0.20 - risk*0.40"
)
ACTUAL_PROGRESS_FORMULA = "stage*0.50 + evidence*0.32 + prosperity*0.18"

# 三高总分权重(归一化到 1.0)。阶段三B 起由
# tools/calibrate_supply_chain_scores.py --apply-weights 按 walk-forward IC
# 标定写回;手工调整时请同步更新模块 docstring 变更记录。
THREE_HIGH_WEIGHTS: dict[str, float] = {
    "growth": 0.24,
    "profit": 0.18,
    "moat": 0.22,
    "stage": 0.16,
    "evidence": 0.14,
    "prosperity": 0.06,
}


def clamp_score(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return round(min(high, max(low, float(value or 0.0))), 2)


def json_list(value: Any) -> list:
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return list(value.keys())
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return []
        return parsed if isinstance(parsed, list) else []
    return []


def calculate_stage_progress_score(research_stage: str | None, commercial_stage: str | None) -> float:
    research_score = RESEARCH_STAGE_SCORE.get(str(research_stage or "R0").upper(), 0.0)
    commercial_score = COMMERCIAL_STAGE_SCORE.get(str(commercial_stage or "C0").upper(), 0.0)
    return clamp_score(max(research_score, commercial_score))


def calculate_market_expectation_score(
    *,
    analyst_claims: int = 0,
    news_claims: int = 0,
    total_claims: int = 0,
    price_change_20d: float | None = None,
) -> float:
    price_component = max(0.0, float(price_change_20d or 0.0)) * 1.25
    score = 35.0 + min(25.0, analyst_claims * 4.0) + min(15.0, news_claims * 2.5)
    score += min(15.0, max(0, total_claims - analyst_claims - news_claims) * 1.5)
    score += min(25.0, price_component)
    return clamp_score(score)


def calculate_prosperity_score(latest_pct_change: float | None, avg_pct_change: float | None) -> float:
    latest = float(latest_pct_change or 0.0)
    avg = float(avg_pct_change or 0.0)
    return clamp_score(50.0 + latest * 3.0 + avg * 2.0)


def normalize_event_title(title: Any) -> str:
    """标准化事件标题用于去重:小写 + 去空白 + 去标点(仅保留字母/数字/CJK 字符)。"""
    return "".join(ch for ch in str(title or "").lower() if ch.isalnum())


def classify_business_tag_events(events: list[dict[str, Any]]) -> dict[str, int]:
    """按 impact_dimensions/evidence_type 统计 growth/profit/moat/risk/order 事件数。

    去重:同 code + 标准化标题(小写去空白去标点) + 同 event_date 的事件只计一次,
    重复组内保留 confidence 最高的一条;无标题的事件不参与去重(各自唯一)。
    去重数量写入返回 stats 的 "dedup_removed"。
    """
    deduped: dict[tuple[str, str, str], dict[str, Any]] = {}
    undedupable: list[dict[str, Any]] = []
    for event in events:
        title_key = normalize_event_title(event.get("title"))
        if not title_key:
            undedupable.append(event)
            continue
        key = (
            str(event.get("code") or ""),
            title_key,
            str(event.get("event_date") or ""),
        )
        existing = deduped.get(key)
        if existing is None or float(event.get("confidence") or 0.0) > float(
            existing.get("confidence") or 0.0
        ):
            deduped[key] = event
    kept = list(deduped.values()) + undedupable
    counts = {"growth": 0, "profit": 0, "moat": 0, "risk": 0, "order": 0}
    for event in kept:
        dims = set(str(item) for item in json_list(event.get("impact_dimensions")))
        evidence_type = str(event.get("evidence_type") or "")
        if "growth" in dims or evidence_type in {"order", "commercial_stage", "order_award"}:
            counts["growth"] += 1
        if "profit" in dims or evidence_type == "revenue_margin":
            counts["profit"] += 1
        if "moat" in dims or evidence_type in {"patent_standard", "patent", "moat"}:
            counts["moat"] += 1
        if "risk" in dims or evidence_type == "risk":
            counts["risk"] += 1
        if evidence_type in {"order", "commercial_stage", "order_award"}:
            counts["order"] += 1
    counts["dedup_removed"] = len(events) - len(kept)
    return counts


def split_claim_counts(monitor_counts: dict[str, int]) -> tuple[int, int, int]:
    """按共享常量把 claim_source_type 计数拆成 (analyst, news, total)。"""
    analyst_claims = sum(
        count for source_type, count in monitor_counts.items()
        if source_type in ANALYST_CLAIM_SOURCE_TYPES
    )
    news_claims = sum(
        count for source_type, count in monitor_counts.items()
        if source_type in NEWS_CLAIM_SOURCE_TYPES
    )
    return analyst_claims, news_claims, sum(monitor_counts.values())


def calculate_evidence_score(
    events: list[dict[str, Any]],
    event_counts: dict[str, int] | None = None,
) -> float:
    counts = event_counts or classify_business_tag_events(events)
    avg_confidence = (
        sum(float(event.get("confidence") or 0.0) for event in events) / len(events)
        if events
        else 0.0
    )
    return clamp_score(
        len(events) * 12.0
        + avg_confidence * 60.0
        + counts["growth"] * 4.0
        + counts["moat"] * 4.0
    )


def compute_three_high_score(
    *,
    revenue_ratio: float | None,
    gross_profit_ratio: float | None,
    events: list[dict[str, Any]],
    stage_score: float,
    prosperity_score: float,
) -> dict[str, Any]:
    """三高评分:growth*0.24+profit*0.18+moat*0.22+stage*0.16+evidence*0.14+prosperity*0.06。

    总分上限按收入/毛利可得性收敛:两者皆缺 70,仅缺毛利 85,齐全 100。
    """
    event_counts = classify_business_tag_events(events)
    evidence_score = calculate_evidence_score(events, event_counts)
    growth_score = clamp_score(
        (revenue_ratio or 0.0) * 100.0
        + event_counts["growth"] * 14.0
        + event_counts["order"] * 12.0
        + max(0.0, prosperity_score - 50.0) * 0.55
    )
    profit_score = None
    if gross_profit_ratio is not None or event_counts["profit"]:
        profit_score = clamp_score(
            (35.0 if gross_profit_ratio is None else 45.0 + gross_profit_ratio * 100.0)
            + event_counts["profit"] * 10.0
        )
    avg_confidence = (
        sum(float(event.get("confidence") or 0.0) for event in events) / len(events)
        if events
        else 0.0
    )
    moat_score = clamp_score(event_counts["moat"] * 28.0 + avg_confidence * 35.0)
    score_cap = 100.0
    if revenue_ratio is None and profit_score is None:
        score_cap = 70.0
    elif profit_score is None:
        score_cap = 85.0
    total_score = clamp_score(
        growth_score * THREE_HIGH_WEIGHTS["growth"]
        + (profit_score or 0.0) * THREE_HIGH_WEIGHTS["profit"]
        + moat_score * THREE_HIGH_WEIGHTS["moat"]
        + stage_score * THREE_HIGH_WEIGHTS["stage"]
        + evidence_score * THREE_HIGH_WEIGHTS["evidence"]
        + prosperity_score * THREE_HIGH_WEIGHTS["prosperity"],
        high=score_cap,
    )
    return {
        "growth_score": growth_score,
        "profit_score": profit_score,
        "moat_score": moat_score,
        "stage_score": clamp_score(stage_score),
        "evidence_score": evidence_score,
        "total_score": total_score,
        "score_cap": score_cap,
        "event_counts": event_counts,
        "revenue_supported": revenue_ratio is not None,
        "profit_supported": profit_score is not None,
    }


def compute_expectation_gap_score(
    *,
    stage_score: float,
    evidence_score: float,
    prosperity_score: float,
    market_expectation_score: float,
    risk_events: int = 0,
    price_change_20d: float | None = None,
) -> dict[str, Any]:
    """预期差评分:actual=stage*0.5+evidence*0.32+prosperity*0.18。

    raw=actual-market+evidence*0.22+(prosperity-50)*0.20-risk*0.40;
    expectation_gap_score=clamp((raw+100)/2, 0, 100),50=中性,负预期差保留幅度
    (旧口径 clamp(raw,0,100) 会把所有负值截断为 0,见模块 docstring 变更记录);
    gap_type 以 raw 的 ±15 分划 positive/negative/neutral。
    """
    risk_penalty_score = clamp_score(
        risk_events * 20.0 + max(0.0, -float(price_change_20d or 0.0)) * 0.3
    )
    actual_progress_score = clamp_score(
        stage_score * 0.50 + evidence_score * 0.32 + prosperity_score * 0.18
    )
    raw_gap = (
        actual_progress_score
        - market_expectation_score
        + evidence_score * 0.22
        + (prosperity_score - 50.0) * 0.20
        - risk_penalty_score * 0.40
    )
    expectation_gap_score = clamp_score((raw_gap + 100.0) / 2.0)
    if raw_gap >= 15:
        gap_type = "positive"
    elif raw_gap <= -15:
        gap_type = "negative"
    else:
        gap_type = "neutral"
    return {
        "actual_progress_score": actual_progress_score,
        "market_expectation_score": market_expectation_score,
        "risk_penalty_score": risk_penalty_score,
        "expectation_gap_score": expectation_gap_score,
        "gap_type": gap_type,
        "raw_gap": round(raw_gap, 2),
        "formula": EXPECTATION_GAP_FORMULA,
        "actual_progress_formula": ACTUAL_PROGRESS_FORMULA,
    }


def calculate_gap_momentum_score(
    *,
    current_gap: float,
    previous_gap: float | None,
    gap_20d_ago: float | None,
) -> float:
    recent_delta = float(current_gap or 0.0) - float(previous_gap if previous_gap is not None else current_gap or 0.0)
    medium_delta = float(current_gap or 0.0) - float(gap_20d_ago if gap_20d_ago is not None else current_gap or 0.0)
    return clamp_score(50.0 + recent_delta * 2.0 + medium_delta * 1.0)
