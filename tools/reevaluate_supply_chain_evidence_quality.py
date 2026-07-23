#!/usr/bin/env python3
"""Reevaluate supply-chain evidence quality and business-tag mapping fit.

This pass is deliberately conservative. It does not overwrite the existing
expectation-gap or three-high scores. Instead, it writes an auditable review
table that can be used to downgrade duplicated, weak, or mismapped evidence
before the screener is promoted to a trading decision surface.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from typing import Any
from urllib.parse import urlparse

import psycopg2
import psycopg2.extras


DEFAULT_PG_URL = os.environ.get(
    "KRONOS_PG_URL",
    "postgresql://kronos:kronos@localhost:6432/kronos",
)

STRONG_EVIDENCE_TYPES = {
    "order_award",
    "commercial_stage",
    "capacity_mass_production",
    "revenue_margin",
    "patent_standard",
    "prototype_delivery",
}

WEAK_EVIDENCE_TYPES = {
    "business_presence",
    "research_progress",
    "customer_validation",
    "inferred_business_tag",
}

SOURCE_CEILING = {
    "announcement": 0.95,
    "cninfo_announcement": 0.95,
    "patent": 0.95,
    "government_project": 0.9,
    "exchange_interaction": 0.85,
    "irm_qa": 0.82,
    "research_report": 0.75,
    "batch_10y_research_title": 0.55,
    "batch_10y_profile": 0.5,
    "batch_10y_forecast": 0.55,
    "rule_inference": 0.35,
}

TYPE_STRENGTH = {
    "order_award": 1.0,
    "commercial_stage": 0.95,
    "capacity_mass_production": 0.9,
    "revenue_margin": 0.9,
    "patent_standard": 0.85,
    "prototype_delivery": 0.75,
    "customer_validation": 0.65,
    "research_progress": 0.55,
    "business_presence": 0.45,
    "inferred_business_tag": 0.25,
}

STATUS_FACTOR = {
    "approved": 1.0,
    "pending_review": 0.45,
    "candidate": 0.25,
    "rejected": 0.0,
}

TAG_KEYWORDS = {
    "ai_compute_application": [
        "人工智能",
        "AI",
        "智能",
        "智慧",
        "算法",
        "视频分析",
        "自然语言",
        "感知",
        "认知",
        "决策",
        "无人机",
        "机器狗",
        "机器人",
        "低空",
        "城市大脑",
        "应急救援",
        "平台",
        "解决方案",
        "神思智飞",
    ],
    "ai_compute_software": [
        "算力",
        "调度",
        "云脑",
        "AI平台",
        "基础软件",
        "GPU",
        "服务器",
        "数据中心",
        "计算",
    ],
    "generic_ai_compute": [
        "算力",
        "AI",
        "人工智能",
        "智能",
        "GPU",
        "服务器",
        "数据中心",
        "模型",
        "算法",
    ],
}

TAG_REQUIRED_KEYWORDS = [
    (
        "AI芯片/芯片",
        ["芯片", "半导体", "集成电路", "ASIC", "SoC", "NPU", "GPU", "晶圆", "封装", "EDA"],
        "标签写的是 AI芯片/芯片业务，但证据没有直接指向芯片、半导体、GPU/NPU/ASIC 或集成电路",
    ),
    (
        "高速光模块",
        ["光模块", "光通信", "光芯片", "CPO", "800G", "1.6T", "硅光", "光器件", "收发模块"],
        "标签写的是高速光模块，但证据没有直接指向光模块、CPO、800G/1.6T 或光通信器件",
    ),
    (
        "PCB与连接材料",
        ["PCB", "印制电路", "连接器", "覆铜板", "CCL", "高频高速", "封装基板", "电子布"],
        "标签写的是 PCB与连接材料，但证据没有直接指向 PCB、覆铜板、连接器或封装基板",
    ),
    (
        "数据中心/智算中心",
        ["数据中心", "智算", "IDC", "机柜", "液冷", "算力中心", "机房"],
        "标签写的是数据中心/智算中心，但证据没有直接指向数据中心、智算、IDC、机柜或液冷",
    ),
    (
        "云服务",
        ["云", "云服务", "云计算", "算力", "服务器", "IDC", "数据中心"],
        "标签写的是云服务，但证据没有直接指向云服务、算力、服务器、IDC 或数据中心",
    ),
    (
        "算力服务",
        ["算力", "服务器", "GPU", "IDC", "数据中心", "智算", "云计算"],
        "标签写的是算力服务，但证据没有直接指向算力、GPU、服务器、IDC 或智算",
    ),
]


@dataclass
class EvidenceEvent:
    event_id: str
    event_date: date | None
    source_type: str | None
    source_id: str | None
    title: str | None
    excerpt: str | None
    original_url: str | None
    evidence_type: str | None
    confidence: float | None
    review_status: str | None
    impact_dimensions: Any

    @property
    def text(self) -> str:
        return " ".join(
            str(v or "")
            for v in (self.title, self.excerpt, self.source_id, self.original_url)
        )


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def normalize_text(value: str | None) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"\s+", "", text)
    text = re.sub(r"[，。；：、,.!?:;《》“”\"'（）()【】\[\]{}_-]+", "", text)
    return text


def normalize_url(value: str | None) -> str:
    if not value:
        return ""
    parsed = urlparse(str(value).strip())
    path = parsed.path or ""
    if path:
        return path.lower()
    return str(value).strip().lower()


def evidence_duplicate_key(event: EvidenceEvent) -> str:
    """Build a stable key for evidence dedupe.

    Prefer official URL path and source identity. If those are missing, fall
    back to date + normalized title. This keeps duplicated CNINFO detail/PDF
    links from being counted as separate hard proof.
    """

    raw_url = str(event.original_url or "")
    announcement_id = re.search(r"announcementid=(\d+)", raw_url, re.I)
    if announcement_id:
        return f"announcement:{announcement_id.group(1)}"
    url = normalize_url(event.original_url)
    if url:
        m = re.search(r"/(\d{8,})\.pdf$", url)
        if m:
            return f"announcement:{m.group(1)}"
        return f"url:{url}"
    source_id = normalize_text(event.source_id)
    title = normalize_text(event.title)
    day = str(event.event_date or "")
    if source_id and title:
        return f"source:{source_id}:{title}"
    return f"title:{day}:{title}"


def event_weight(event: EvidenceEvent) -> float:
    source = SOURCE_CEILING.get(str(event.source_type or ""), 0.55)
    evidence_type = TYPE_STRENGTH.get(str(event.evidence_type or ""), 0.4)
    status = STATUS_FACTOR.get(str(event.review_status or ""), 0.2)
    confidence = float(event.confidence if event.confidence is not None else 0.5)
    return clamp(source * evidence_type * status * confidence * 100)


def group_unique_events(events: list[EvidenceEvent]) -> list[EvidenceEvent]:
    grouped: dict[str, EvidenceEvent] = {}
    for event in events:
        key = evidence_duplicate_key(event)
        current = grouped.get(key)
        if current is None or event_weight(event) > event_weight(current):
            grouped[key] = event
    return list(grouped.values())


def keyword_hits(text: str, keywords: list[str]) -> int:
    if not text:
        return 0
    return sum(1 for keyword in keywords if keyword and keyword.lower() in text.lower())


# 非算力链回退分支的关键词噪音词表 (通用层名, 每条链都一样, 无区分度)
_KEYWORD_NOISE = {
    "需求层", "任务层", "核心产品层", "底层支撑层", "集成层", "配套层",
    "基础设施层", "商业变现层", "产业链",
}


def _fit_tokens(text: str) -> list[str]:
    """提取 label-fit 关键词: 中文词(>=2字) 或全大写缩写(>=3, 如 HBM/CXL/TSV/EDA).

    英文小写碎片(如 chain_id 拆出的 'new','power','grid')与 JSON 噪音('name','level','id','L1')
    一律排除 — 它们几乎不可能命中中文证据文本, 只会稀释 hit_ratio
    (历史 bug: 非算力链 label_fit 被封底 35 的根因)."""
    words = re.findall(r"[一-鿿]{2,}|[A-Z0-9]{3,}", text or "")
    return [w for w in words
            if not re.fullmatch(r"L[1-8]", w) and w not in _KEYWORD_NOISE]


def mapping_keywords(chain_id: str | None, tag_name: str | None, path_text: str,
                     mapping_id: str | None = None) -> list[str]:
    tag = f"{chain_id or ''} {tag_name or ''} {path_text or ''}"
    if "行业AI应用" in tag or "行业应用" in tag:
        return TAG_KEYWORDS["ai_compute_application"]
    if "基础软件" in tag or "算力调度" in tag:
        return TAG_KEYWORDS["ai_compute_software"]
    if "AI算力" in tag or "ai_compute" in tag:
        return TAG_KEYWORDS["generic_ai_compute"]
    # 回退分支: tag_name + mapping_id 业务后缀 + l1_l8_path 中文节点名
    words = _fit_tokens(f"{tag_name or ''} {mapping_id or ''} {path_text or ''}")
    cleaned: list[str] = []
    for w in words:
        stripped = re.sub(r"(业务|板块|产品)$", "", w)
        cleaned.append(stripped if len(stripped) >= 2 else w)
        if stripped != w and len(stripped) >= 2:
            cleaned.append(w)
    return list(dict.fromkeys(cleaned))[:20]


def assess_label_fit(
    *,
    chain_id: str | None,
    tag_name: str | None,
    l1_l8_path: Any,
    mapping_id: str | None = None,
    unique_events: list[EvidenceEvent],
    revenue_ratio: float | None,
    gross_profit_ratio: float | None,
) -> tuple[float, list[str], dict[str, Any]]:
    path_text = json.dumps(l1_l8_path or [], ensure_ascii=False)
    keywords = mapping_keywords(chain_id, tag_name, path_text, mapping_id=mapping_id)
    evidence_text = "\n".join(event.text for event in unique_events)
    hits = keyword_hits(evidence_text, keywords)
    hit_ratio = hits / max(len(keywords), 1)

    score = 35.0 + min(hit_ratio, 0.55) * 80.0
    if revenue_ratio is not None:
        score += 8
    if gross_profit_ratio is not None:
        score += 6

    issues: list[str] = []
    tag_text = f"{chain_id or ''} {tag_name or ''} {path_text}"
    evidence_lower = evidence_text.lower()
    infrastructure_hits = keyword_hits(
        evidence_text,
        ["算力", "GPU", "服务器", "数据中心", "芯片", "光模块", "集群", "调度"],
    )
    application_hits = keyword_hits(
        evidence_text,
        ["低空", "无人机", "机器狗", "智慧城市", "城市大脑", "身份认证", "医疗", "公安", "应急", "解决方案"],
    )
    detail = {
        "keywords": keywords,
        "keyword_hits": hits,
        "keyword_hit_ratio": round(hit_ratio, 4),
        "infrastructure_hits": infrastructure_hits,
        "application_hits": application_hits,
    }

    if ("基础软件" in tag_text or "算力调度" in tag_text) and infrastructure_hits == 0:
        score -= 28
        issues.append("标签写的是基础软件/算力调度，但证据没有直接指向算力、调度、GPU、服务器或数据中心")
    if ("AI算力" in tag_text or "ai_compute" in str(chain_id or "")) and infrastructure_hits == 0 and application_hits > 0:
        issues.append("证据更像 AI 行业应用/智慧城市/低空数字化，不是 AI 算力基础设施")
        if "行业应用" not in tag_text and "行业AI应用" not in tag_text:
            score -= 18
        elif application_hits >= 2:
            score += 15
    if "ai_compute" in str(chain_id or "") and "AI".lower() not in evidence_lower and "人工智能" not in evidence_text and "智能" not in evidence_text:
        score -= 10
        issues.append("AI 相关关键词不足，需要人工复核是否误映射")
    for tag_fragment, required_keywords, issue_text in TAG_REQUIRED_KEYWORDS:
        if tag_fragment in tag_text:
            required_hits = keyword_hits(evidence_text, required_keywords)
            detail_key = f"required_hits_{tag_fragment}"
            if required_hits == 0:
                score -= 35
                issues.append(issue_text)
            detail[detail_key] = required_hits
    if revenue_ratio is None:
        issues.append("缺少该标签业务收入占比")
    if gross_profit_ratio is None:
        issues.append("缺少该标签业务毛利占比")

    return round(clamp(score), 2), issues, detail


def assess_evidence_quality(events: list[EvidenceEvent]) -> tuple[float, dict[str, Any], list[str]]:
    unique_events = group_unique_events(events)
    approved = [e for e in events if e.review_status == "approved"]
    unique_approved = [e for e in unique_events if e.review_status == "approved"]
    pending = [e for e in events if e.review_status == "pending_review"]
    candidates = [e for e in events if e.review_status == "candidate"]
    strong = [
        e for e in unique_approved
        if str(e.evidence_type or "") in STRONG_EVIDENCE_TYPES
        and str(e.source_type or "") not in {"rule_inference", "batch_10y_profile"}
    ]
    weak = [e for e in unique_approved if str(e.evidence_type or "") in WEAK_EVIDENCE_TYPES]
    duplicate_count = max(len(events) - len(unique_events), 0)

    approved_weight = sum(event_weight(e) for e in unique_approved)
    strong_weight = sum(event_weight(e) for e in strong)
    pending_weight = sum(event_weight(e) for e in group_unique_events(pending))

    score = 0.0
    score += min(approved_weight * 0.72, 58)
    score += min(strong_weight * 0.55, 30)
    score += min(pending_weight * 0.15, 10)
    score += min(len(unique_approved) * 3, 9)
    score -= min(duplicate_count * 6, 24)
    if not strong:
        score -= 18
    if not unique_approved and pending:
        score = max(score, min(pending_weight * 0.3, 28))
    if candidates and not unique_approved:
        score = min(score + 5, 25)

    issues: list[str] = []
    if duplicate_count:
        issues.append(f"发现疑似重复证据 {duplicate_count} 条，需要去重后计分")
    if not strong:
        issues.append("缺少已审核强证据：订单/中标/量产/收入毛利/专利标准等")
    if len(pending) > len(approved):
        issues.append("待审核线索多于已审核证据，不能直接当强证据使用")
    if not unique_approved:
        issues.append("没有已审核证据")

    detail = {
        "event_count": len(events),
        "unique_event_count": len(unique_events),
        "approved_count": len(approved),
        "unique_approved_count": len(unique_approved),
        "pending_count": len(pending),
        "candidate_count": len(candidates),
        "strong_evidence_count": len(strong),
        "weak_approved_count": len(weak),
        "duplicate_count": duplicate_count,
        "approved_weight": round(approved_weight, 2),
        "strong_weight": round(strong_weight, 2),
        "pending_weight": round(pending_weight, 2),
        "unique_event_ids": [e.event_id for e in unique_events[:30]],
        "strong_event_ids": [e.event_id for e in strong],
    }
    return round(clamp(score), 2), detail, issues


def quality_tier(score: float) -> str:
    if score >= 75:
        return "strong_confirmed"
    if score >= 55:
        return "usable_with_review"
    if score >= 35:
        return "weak_watch"
    return "insufficient"


def review_status(evidence_score: float, label_fit_score: float, detail: dict[str, Any]) -> str:
    strong_count = int(detail.get("strong_evidence_count") or 0)
    duplicate_count = int(detail.get("duplicate_count") or 0)
    pending_count = int(detail.get("pending_count") or 0)
    approved_count = int(detail.get("approved_count") or 0)
    noisy_evidence = duplicate_count > 0 or pending_count > max(approved_count * 2, 3)
    if evidence_score >= 70 and label_fit_score >= 65 and strong_count >= 1 and not noisy_evidence:
        return "strong_confirmed"
    if evidence_score >= 50 and label_fit_score >= 55:
        return "watch_review"
    if evidence_score < 30 or label_fit_score < 45:
        return "downgrade_or_remove"
    return "manual_review"


def reliability_adjusted_gap(original_gap: float | None, evidence_score: float, label_fit_score: float) -> float:
    raw = float(original_gap or 0.0)
    multiplier = (0.35 + evidence_score / 200.0) * (0.55 + label_fit_score / 250.0)
    return round(max(0.0, raw * multiplier), 2)


def build_assessment(row: dict[str, Any], events: list[EvidenceEvent], assessment_date: str) -> dict[str, Any]:
    evidence_score, evidence_detail, evidence_issues = assess_evidence_quality(events)
    unique_events = group_unique_events(events)
    label_score, label_issues, label_detail = assess_label_fit(
        chain_id=row.get("chain_id"),
        tag_name=row.get("tag_name"),
        l1_l8_path=row.get("l1_l8_path"),
        mapping_id=row.get("mapping_id"),
        unique_events=unique_events,
        revenue_ratio=row.get("revenue_ratio"),
        gross_profit_ratio=row.get("gross_profit_ratio"),
    )
    original_gap = row.get("expectation_gap_score")
    adjusted_gap = reliability_adjusted_gap(original_gap, evidence_score, label_score)
    detail = {
        "evidence": evidence_detail,
        "label_fit": label_detail,
        "original_scores": {
            "expectation_gap_score": float(original_gap or 0),
            "actual_progress_score": float(row.get("actual_progress_score") or 0),
            "market_expectation_score": float(row.get("market_expectation_score") or 0),
            "evidence_delta_score": float(row.get("evidence_delta_score") or 0),
            "risk_penalty_score": float(row.get("risk_penalty_score") or 0),
        },
    }
    issues = evidence_issues + label_issues
    recommendations = []
    if evidence_detail.get("duplicate_count"):
        recommendations.append("先合并同一公告/同一来源的重复证据，再重算证据分")
    if evidence_detail.get("pending_count", 0) > evidence_detail.get("approved_count", 0):
        recommendations.append("将投资者问答、公司资料、研报标题转为待审核线索，补公告/订单/财务原文")
    if label_score < 55:
        recommendations.append("复核产业链标签，必要时从基础设施标签降级到行业应用标签")
    if row.get("revenue_ratio") is None or row.get("gross_profit_ratio") is None:
        recommendations.append("补充该标签业务收入占比和毛利占比，否则三高只能按线索处理")
    if adjusted_gap < float(original_gap or 0) * 0.75:
        recommendations.append("原预期差分数建议降权使用，先进入观察池而非强确认池")

    status = review_status(evidence_score, label_score, evidence_detail)
    return {
        "assessment_date": assessment_date,
        "mapping_id": row["mapping_id"],
        "code": row["code"],
        "chain_id": row.get("chain_id"),
        "tag_name": row.get("tag_name"),
        "original_gap_score": round(float(original_gap or 0), 2),
        "reliability_adjusted_gap_score": adjusted_gap,
        "evidence_quality_score": evidence_score,
        "evidence_quality_tier": quality_tier(evidence_score),
        "label_fit_score": label_score,
        "review_status": status,
        "strong_evidence_count": int(evidence_detail.get("strong_evidence_count") or 0),
        "approved_evidence_count": int(evidence_detail.get("approved_count") or 0),
        "unique_approved_evidence_count": int(evidence_detail.get("unique_approved_count") or 0),
        "pending_evidence_count": int(evidence_detail.get("pending_count") or 0),
        "duplicate_evidence_count": int(evidence_detail.get("duplicate_count") or 0),
        "issues": issues,
        "recommendations": recommendations,
        "detail": detail,
    }


def ensure_table(cur) -> None:
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS business_tag_evidence_reassessment (
            assessment_date date NOT NULL,
            mapping_id text NOT NULL,
            code text NOT NULL,
            chain_id text,
            tag_name text,
            original_gap_score double precision,
            reliability_adjusted_gap_score double precision,
            evidence_quality_score double precision,
            evidence_quality_tier text,
            label_fit_score double precision,
            review_status text,
            strong_evidence_count integer,
            approved_evidence_count integer,
            unique_approved_evidence_count integer,
            pending_evidence_count integer,
            duplicate_evidence_count integer,
            issues jsonb NOT NULL DEFAULT '[]'::jsonb,
            recommendations jsonb NOT NULL DEFAULT '[]'::jsonb,
            detail jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamp without time zone NOT NULL DEFAULT now(),
            PRIMARY KEY (assessment_date, mapping_id)
        )
        """
    )
    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_business_tag_evidence_reassessment_code
        ON business_tag_evidence_reassessment (code, assessment_date)
        """
    )
    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_business_tag_evidence_reassessment_status
        ON business_tag_evidence_reassessment (assessment_date, review_status)
        """
    )


def latest_trade_date(cur) -> str:
    cur.execute("SELECT max(trade_date) AS trade_date FROM business_tag_expectation_gap_scores")
    row = cur.fetchone()
    if not row or not row["trade_date"]:
        raise RuntimeError("business_tag_expectation_gap_scores has no trade_date")
    return str(row["trade_date"])[:10]


def fetch_mapping_rows(cur, trade_date: str, code: str | None = None, require_evidence: bool = False) -> list[dict[str, Any]]:
    params: list[Any] = [trade_date]
    code_filter = ""
    if code:
        code_filter = "AND split_part(m.code, '.', 1) = %s"
        params.append(code)
    evidence_filter = ""
    if require_evidence:
        # 只评估有 approved 证据或 verified 状态的映射(同 backfill 的 --require-evidence 宇宙)
        evidence_filter = """
          AND (
              m.status = 'verified'
              OR EXISTS (
                  SELECT 1 FROM business_tag_evidence_events e
                  WHERE e.mapping_id = m.mapping_id AND e.review_status = 'approved'
              )
          )
        """
    cur.execute(
        f"""
        SELECT
            m.mapping_id,
            split_part(m.code, '.', 1) AS code,
            m.chain_id,
            m.tag_name,
            m.l1_l8_path,
            m.revenue_ratio,
            m.gross_profit_ratio,
            g.expectation_gap_score,
            g.actual_progress_score,
            g.market_expectation_score,
            g.evidence_delta_score,
            g.risk_penalty_score
        FROM business_tag_mapping m
        LEFT JOIN business_tag_expectation_gap_scores g
          ON g.mapping_id = m.mapping_id AND g.trade_date = %s
        WHERE coalesce(m.status, '') NOT IN ('rejected', 'disabled')
        {code_filter}
        {evidence_filter}
        ORDER BY split_part(m.code, '.', 1), m.mapping_id
        """,
        params,
    )
    return [dict(row) for row in cur.fetchall()]


def fetch_events(cur, mapping_ids: list[str], as_of_date: str | None = None) -> dict[str, list[EvidenceEvent]]:
    """加载事件;as_of_date 给定即启用 as-of 可见性过滤(无未来函数):
    - approved 行:coalesce(reviewed_at 折算 Asia/Shanghai 日期, created_at 兜底) <= as_of_date
    - 非 approved 行(pending/candidate):created_at <= as_of_date
    """
    if not mapping_ids:
        return {}
    asof_filter = ""
    if as_of_date:
        asof_filter = """
              AND (
                  (review_status = 'approved'
                   AND coalesce((reviewed_at AT TIME ZONE 'Asia/Shanghai')::date, created_at::date) <= %s)
                  OR (review_status <> 'approved' AND created_at::date <= %s)
              )
        """
    events_by_mapping: dict[str, list[EvidenceEvent]] = defaultdict(list)
    for start in range(0, len(mapping_ids), 500):
        batch = mapping_ids[start:start + 500]
        cur.execute(
            """
            SELECT
                mapping_id,
                event_id,
                event_date,
                source_type,
                source_id,
                title,
                excerpt,
                original_url,
                evidence_type,
                confidence,
                review_status,
                impact_dimensions
            FROM business_tag_evidence_events
            WHERE mapping_id = ANY(%s)
            """ + asof_filter,
            [batch, *([as_of_date, as_of_date] if as_of_date else [])],
        )
        for row in cur.fetchall():
            data = dict(row)
            mapping_id = data.pop("mapping_id")
            events_by_mapping[mapping_id].append(EvidenceEvent(**data))
    return events_by_mapping


def upsert_assessments(cur, assessments: list[dict[str, Any]]) -> int:
    if not assessments:
        return 0
    values = [
        (
            row["assessment_date"],
            row["mapping_id"],
            row["code"],
            row["chain_id"],
            row["tag_name"],
            row["original_gap_score"],
            row["reliability_adjusted_gap_score"],
            row["evidence_quality_score"],
            row["evidence_quality_tier"],
            row["label_fit_score"],
            row["review_status"],
            row["strong_evidence_count"],
            row["approved_evidence_count"],
            row["unique_approved_evidence_count"],
            row["pending_evidence_count"],
            row["duplicate_evidence_count"],
            json.dumps(row["issues"], ensure_ascii=False),
            json.dumps(row["recommendations"], ensure_ascii=False),
            json.dumps(row["detail"], ensure_ascii=False, default=str),
        )
        for row in assessments
    ]
    psycopg2.extras.execute_values(
        cur,
        """
        INSERT INTO business_tag_evidence_reassessment (
            assessment_date, mapping_id, code, chain_id, tag_name,
            original_gap_score, reliability_adjusted_gap_score,
            evidence_quality_score, evidence_quality_tier, label_fit_score,
            review_status, strong_evidence_count, approved_evidence_count,
            unique_approved_evidence_count, pending_evidence_count,
            duplicate_evidence_count, issues, recommendations, detail
        )
        VALUES %s
        ON CONFLICT (assessment_date, mapping_id) DO UPDATE SET
            code = EXCLUDED.code,
            chain_id = EXCLUDED.chain_id,
            tag_name = EXCLUDED.tag_name,
            original_gap_score = EXCLUDED.original_gap_score,
            reliability_adjusted_gap_score = EXCLUDED.reliability_adjusted_gap_score,
            evidence_quality_score = EXCLUDED.evidence_quality_score,
            evidence_quality_tier = EXCLUDED.evidence_quality_tier,
            label_fit_score = EXCLUDED.label_fit_score,
            review_status = EXCLUDED.review_status,
            strong_evidence_count = EXCLUDED.strong_evidence_count,
            approved_evidence_count = EXCLUDED.approved_evidence_count,
            unique_approved_evidence_count = EXCLUDED.unique_approved_evidence_count,
            pending_evidence_count = EXCLUDED.pending_evidence_count,
            duplicate_evidence_count = EXCLUDED.duplicate_evidence_count,
            issues = EXCLUDED.issues,
            recommendations = EXCLUDED.recommendations,
            detail = EXCLUDED.detail,
            created_at = now()
        """,
        values,
        page_size=500,
    )
    return len(values)


def summarize(assessments: list[dict[str, Any]]) -> dict[str, Any]:
    status_counts: dict[str, int] = defaultdict(int)
    tier_counts: dict[str, int] = defaultdict(int)
    downgrade_examples = []
    for row in assessments:
        status_counts[row["review_status"]] += 1
        tier_counts[row["evidence_quality_tier"]] += 1
        if row["review_status"] in {"downgrade_or_remove", "manual_review"}:
            downgrade_examples.append({
                "code": row["code"],
                "mapping_id": row["mapping_id"],
                "tag_name": row["tag_name"],
                "original_gap_score": row["original_gap_score"],
                "adjusted_gap_score": row["reliability_adjusted_gap_score"],
                "evidence_quality_score": row["evidence_quality_score"],
                "label_fit_score": row["label_fit_score"],
                "issues": row["issues"][:3],
            })
    downgrade_examples.sort(
        key=lambda x: (float(x["original_gap_score"] or 0) - float(x["adjusted_gap_score"] or 0)),
        reverse=True,
    )
    return {
        "total": len(assessments),
        "review_status_counts": dict(status_counts),
        "evidence_quality_tier_counts": dict(tier_counts),
        "top_downgrade_examples": downgrade_examples[:10],
    }


def run(
    pg_url: str,
    trade_date: str | None,
    assessment_date: str,
    code: str | None,
    as_of_date: str | None = None,
    require_evidence: bool = False,
) -> dict[str, Any]:
    # as_of_date 缺省取 assessment_date:评估只消费评估日当天及之前可见的证据,无未来函数。
    as_of = as_of_date or assessment_date
    with psycopg2.connect(pg_url) as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            ensure_table(cur)
            score_date = trade_date or latest_trade_date(cur)
            mappings = fetch_mapping_rows(cur, score_date, code, require_evidence=require_evidence)
            events_by_mapping = fetch_events(cur, [row["mapping_id"] for row in mappings], as_of_date=as_of)
            assessments = [
                build_assessment(row, events_by_mapping.get(row["mapping_id"], []), assessment_date)
                for row in mappings
            ]
            written = upsert_assessments(cur, assessments)
        conn.commit()
    payload = summarize(assessments)
    payload.update({
        "trade_date": trade_date or score_date,
        "assessment_date": assessment_date,
        "as_of_date": as_of,
        "require_evidence": require_evidence,
        "universe_mappings": len(mappings),
        "written": written,
        "code": code,
    })
    digest = hashlib.sha1(json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")).hexdigest()[:12]
    payload["run_digest"] = digest
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Reevaluate evidence quality and business-tag mapping fit")
    parser.add_argument("--pg-url", default=DEFAULT_PG_URL)
    parser.add_argument("--trade-date", default=None)
    parser.add_argument("--assessment-date", default=os.environ.get("ASSESSMENT_DATE", "2026-07-07"))
    parser.add_argument("--as-of-date", default=None,
                        help="as-of 可见性截止日,缺省取 assessment-date;只消费该日及之前可见(approved 按 reviewed_at,created_at 兜底)的事件")
    parser.add_argument("--require-evidence", action="store_true",
                        help="只评估有 approved 证据或 verified 状态的映射")
    parser.add_argument("--code", default=None, help="Optional stock code, e.g. 300479")
    args = parser.parse_args()
    payload = run(
        args.pg_url,
        args.trade_date,
        args.assessment_date,
        args.code,
        as_of_date=args.as_of_date,
        require_evidence=args.require_evidence,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
