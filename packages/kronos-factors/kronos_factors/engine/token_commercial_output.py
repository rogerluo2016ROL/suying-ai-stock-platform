"""Pure rules for the AI Token commercial output chain."""

from __future__ import annotations

import re
from typing import Any


DIMENSION_WEIGHTS = {
    "business_authenticity": 0.20,
    "token_value_capture": 0.20,
    "technology_inference_efficiency": 0.15,
    "customer_commercialization": 0.15,
    "competition_moat": 0.10,
    "growth_realization": 0.10,
    "evidence_quality": 0.10,
}

BROAD_TAGS = {"云服务", "软件", "数据中心", "ai业务", "人工智能", "算力", "数字经济"}

ROLE_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("L8", ("token收入", "api收入", "agent收入", "saas收入", "海外服务", "海外收入")),
    ("L7", ("token计量", "计费", "套餐", "结算", "客户运营", "安全合规")),
    ("L6", ("推理api", "api网关", "推理云", "maas平台", "算力租赁", "边缘推理")),
    ("L5", ("ai集群", "光模块", "交换机", "pcb", "液冷", "电源", "存储")),
    ("L4", ("ai服务器", "gpu", "asic", "hbm", "先进封装", "算力芯片")),
    ("L3", ("推理引擎", "量化", "蒸馏", "编译器", "kv cache", "算力调度")),
    ("L2", ("基础模型", "行业模型", "agent平台", "maas", "大模型")),
    ("L1", ("企业agent", "代码生成", "智能客服", "ai搜索", "多模态应用", "行业ai应用")),
)


def normalize_stock_code(code: str) -> str:
    """Return a six-digit mainland stock code without exchange decoration."""
    match = re.search(r"(?<!\d)(\d{6})(?!\d)", str(code or ""))
    return match.group(1) if match else str(code or "").strip().upper()


def classify_token_role(tag: str, evidence: dict[str, Any] | None = None) -> str | None:
    """Classify a specific business tag; broad concepts remain unclassified."""
    normalized = re.sub(r"[\s/_-]+", "", str(tag or "")).lower()
    if not normalized:
        return None
    if normalized in BROAD_TAGS:
        return None
    facts = evidence or {}
    for layer, keywords in ROLE_RULES:
        if any(keyword in normalized for keyword in keywords):
            if layer == "L6" and not any(facts.get(key) for key in ("api_calls", "platform_online", "service_revenue", "customer_usage")):
                return None
            return layer
    return None


def score_token_dimensions(values: dict[str, float | None]) -> dict[str, Any]:
    """Calculate a score using only present dimensions; never impute missing values."""
    available_weight = 0.0
    weighted_sum = 0.0
    missing: list[str] = []
    for dimension, weight in DIMENSION_WEIGHTS.items():
        value = values.get(dimension)
        if value is None:
            missing.append(dimension)
            continue
        bounded = min(100.0, max(0.0, float(value)))
        weighted_sum += bounded * weight
        available_weight += weight
    score = round(weighted_sum / available_weight, 4) if available_weight else None
    coverage = round(available_weight, 4)
    return {
        "weighted_score": score,
        "coverage_ratio": coverage,
        "formal_ranking_eligible": coverage >= 0.60,
        "missing_dimensions": missing,
    }


def derive_token_pool(
    evidence_grade: str,
    review_status: str,
    facts: dict[str, Any] | None = None,
) -> tuple[str | None, list[str]]:
    """Apply evidence gates before any score or market signal."""
    grade = str(evidence_grade or "E0").upper()
    review = str(review_status or "candidate").lower()
    facts = facts or {}
    reasons: list[str] = []
    if review in {"rejected", "disabled"}:
        return None, ["mapping_rejected_or_disabled"]
    if grade in {"E0", "E1"} or review != "approved":
        return "D", ["evidence_not_formally_approved"]
    if grade == "E2":
        if facts.get("verified_supply") or facts.get("verified_product") or facts.get("verified_order") or facts.get("verified_project"):
            if not facts.get("token_revenue"):
                reasons.append("token_revenue_unverified")
            return "C", reasons
        return "D", ["e2_fact_missing"]
    if grade == "E3":
        if facts.get("customer_usage") and (facts.get("running") or facts.get("recurring_delivery")):
            return "B", reasons
        return "C", ["runtime_or_delivery_fact_missing"]
    if grade in {"E4", "E5"}:
        if not facts.get("token_revenue"):
            return "B", ["token_revenue_unverified"]
        if grade == "E5" and not facts.get("continuous_cashflow"):
            return "A", ["continuous_cashflow_unverified"]
        return "A", reasons
    return "D", ["unknown_evidence_grade"]
