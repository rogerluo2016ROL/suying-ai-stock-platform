#!/usr/bin/env python3
"""Supply-chain evidence pipeline utilities.

This tool manages evidence source metadata first. Later tasks extend it with
document ingestion, fact extraction, freshness, stage transitions, and
expectation monitoring.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime
from dataclasses import asdict, dataclass
from typing import Literal


SourceLevel = Literal["strong", "mid", "weak"]


@dataclass(frozen=True)
class EvidenceSource:
    source_id: str
    source_name: str
    source_type: str
    source_level: SourceLevel
    source_reliability_score: float
    confidence_cap: float
    is_official: bool
    is_third_party_estimate: bool
    is_market_sentiment: bool
    requires_cross_validation: bool
    license_status: str
    update_frequency: str
    crawl_method: str
    enabled: bool = True
    metadata: dict | None = None

    def to_record(self) -> dict:
        record = asdict(self)
        record["metadata"] = record["metadata"] or {}
        return record


@dataclass(frozen=True)
class ExtractedFact:
    company_code: str
    l5_tag: str
    l6_route: str | None
    fact_type: str
    fact_nature: str
    original_quote: str
    source_level: SourceLevel
    confidence: float
    confidence_cap: float
    validation_status: str
    research_stage_signal: str | None = None
    commercial_stage_signal: str | None = None
    growth_signal: bool = False
    profit_signal: bool = False
    moat_signal: bool = False
    risk_signal: bool = False
    fact_value: str | None = None


@dataclass(frozen=True)
class StageTransitionDecision:
    new_research_stage: str | None
    new_commercial_stage: str | None
    review_status: str
    auto_apply: bool
    reason: str


COMMERCIAL_STAGE_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("C6", ("毛利率改善", "利润贡献", "盈利改善")),
    ("C5", ("收入占比达到", "收入占比为", "收入占比可见", "分业务收入", "收入贡献")),
    ("C4", ("批量订单", "框架协议", "批量供货", "批量出货")),
    ("C3", ("量产爬坡", "产线建设", "产能释放", "量产")),
    ("C2", ("小批交付", "小批量出货", "小批量交付")),
    ("C1", ("试产", "试订单", "小批试制")),
)

RESEARCH_STAGE_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("R6", ("产品定型", "具备量产", "研发完成")),
    ("R5", ("验证通过", "进入供应链", "客户定点")),
    ("R4", ("送样", "客户认证", "导入客户")),
    ("R3", ("性能验证", "内部测试", "测试")),
    ("R2", ("样品", "原型机", "样机", "实验室")),
    ("R1", ("研发", "立项", "技术储备", "研发项目")),
)

GROWTH_KEYWORDS = ("收入增长", "快速增长", "订单增长", "产能扩张", "客户增加", "产品升级", "收入占比", "持续提升", "放量")
PROFIT_KEYWORDS = ("毛利率", "高端产品占比", "成本下降", "单价提升", "客户结构改善", "利润贡献")
MOAT_KEYWORDS = ("国产替代", "客户认证", "专利", "标准", "卡脖子", "工艺难度", "良率", "交付能力", "客户绑定")
RISK_KEYWORDS = ("延期", "不及预期", "未形成收入", "否认", "风险", "下滑")
EXPECTATION_KEYWORDS = ("预计", "有望", "放量", "收入快速增长", "贡献利润", "订单兑现")
RESEARCH_STAGE_RANK = {f"R{i}": i for i in range(7)}
COMMERCIAL_STAGE_RANK = {f"C{i}": i for i in range(8)}
STRONG_SOURCE_HINTS = ("公告", "财报", "年报", "半年报", "季报", "招投标", "中标", "专利", "标准", "政府")
MID_SOURCE_HINTS = ("互动", "互动易", "调研", "官网", "新闻", "研报", "纪要", "券商", "财联社")
WEAK_SOURCE_HINTS = ("社区", "雪球", "股吧", "招聘", "公众号", "自媒体", "传闻")


def _contains_any(text: str, words: tuple[str, ...]) -> bool:
    return any(word in text for word in words)


def _stage_from_keywords(text: str, candidates: tuple[tuple[str, tuple[str, ...]], ...]) -> str | None:
    for stage, words in candidates:
        if _contains_any(text, words):
            return stage
    return None


def _confidence_cap_for_level(source_level: str) -> float:
    if source_level == "strong":
        return 0.95
    if source_level == "mid":
        return 0.75
    return 0.45


def map_source_type_to_source_level(source_type: str) -> SourceLevel:
    text = str(source_type or "")
    if _contains_any(text, STRONG_SOURCE_HINTS):
        return "strong"
    if _contains_any(text, WEAK_SOURCE_HINTS):
        return "weak"
    if _contains_any(text, MID_SOURCE_HINTS):
        return "mid"
    return "mid"


def decide_stage_transition(
    *,
    source_level: SourceLevel,
    research_stage_signal: str | None = None,
    commercial_stage_signal: str | None = None,
    old_research_stage: str = "R0",
    old_commercial_stage: str = "C0",
) -> StageTransitionDecision:
    if source_level == "weak":
        return StageTransitionDecision(
            new_research_stage=None,
            new_commercial_stage=None,
            review_status="pending_review",
            auto_apply=False,
            reason="weak signal cannot change R/C stage",
        )

    new_research = None
    if research_stage_signal and RESEARCH_STAGE_RANK.get(research_stage_signal, -1) > RESEARCH_STAGE_RANK.get(old_research_stage, 0):
        new_research = research_stage_signal

    new_commercial = None
    if commercial_stage_signal and COMMERCIAL_STAGE_RANK.get(commercial_stage_signal, -1) > COMMERCIAL_STAGE_RANK.get(old_commercial_stage, 0):
        new_commercial = commercial_stage_signal

    if not new_research and not new_commercial:
        return StageTransitionDecision(
            new_research_stage=None,
            new_commercial_stage=None,
            review_status="pending_review",
            auto_apply=False,
            reason="no upward stage signal",
        )

    if source_level == "strong":
        return StageTransitionDecision(
            new_research_stage=new_research,
            new_commercial_stage=new_commercial,
            review_status="approved",
            auto_apply=True,
            reason="strong evidence stage signal",
        )

    return StageTransitionDecision(
        new_research_stage=new_research,
        new_commercial_stage=new_commercial,
        review_status="pending_review",
        auto_apply=False,
        reason="mid evidence requires review",
    )


def extract_fact_from_text(
    *,
    text: str,
    source_level: SourceLevel,
    company_code: str,
    l5_tag: str,
    l6_route: str | None = None,
) -> ExtractedFact:
    """Extract one conservative business-tag fact from source text."""
    normalized = " ".join(str(text or "").split())
    confidence_cap = _confidence_cap_for_level(source_level)
    research_stage = _stage_from_keywords(normalized, RESEARCH_STAGE_KEYWORDS)
    commercial_stage = _stage_from_keywords(normalized, COMMERCIAL_STAGE_KEYWORDS)

    if source_level == "weak":
        research_stage = None
        commercial_stage = None
        validation_status = "pending"
        fact_nature = "market_signal"
        fact_type = "weak_signal"
        confidence = min(0.35, confidence_cap)
    else:
        validation_status = "confirmed" if source_level == "strong" else "pending"
        fact_nature = "analyst_estimate" if _contains_any(normalized, EXPECTATION_KEYWORDS) and source_level == "mid" else (
            "confirmed_fact" if source_level == "strong" else "media_report"
        )
        if commercial_stage:
            fact_type = "commercial_progress"
        elif research_stage:
            fact_type = "research_progress"
        elif _contains_any(normalized, MOAT_KEYWORDS):
            fact_type = "moat"
        else:
            fact_type = "business_presence"
        confidence = min(0.82 if source_level == "strong" else 0.62, confidence_cap)

    return ExtractedFact(
        company_code=company_code,
        l5_tag=l5_tag,
        l6_route=l6_route,
        fact_type=fact_type,
        fact_nature=fact_nature,
        original_quote=normalized[:1200],
        source_level=source_level,
        confidence=confidence,
        confidence_cap=confidence_cap,
        validation_status=validation_status,
        research_stage_signal=research_stage,
        commercial_stage_signal=commercial_stage,
        growth_signal=_contains_any(normalized, GROWTH_KEYWORDS),
        profit_signal=_contains_any(normalized, PROFIT_KEYWORDS),
        moat_signal=_contains_any(normalized, MOAT_KEYWORDS),
        risk_signal=_contains_any(normalized, RISK_KEYWORDS),
        fact_value=normalized[:300],
    )


def build_expectation_monitor_record(
    *,
    fact_id: str,
    mapping_id: str,
    source_doc_id: str,
    fact: ExtractedFact,
) -> dict:
    monitor_id = _stable_id("EXPECT", mapping_id, fact_id, source_doc_id)
    return {
        "monitor_id": monitor_id,
        "mapping_id": mapping_id,
        "claim_text": fact.original_quote[:1000],
        "claim_date": datetime.now().date().isoformat(),
        "claim_source_type": fact.source_level,
        "expected_result": fact.fact_value or fact.original_quote[:300],
        "expected_date": None,
        "actual_progress": None,
        "gap_status": "pending",
        "market_price_change": None,
        "evidence_ids": [],
        "source_doc_id": source_doc_id,
        "review_status": "pending_review",
        "metadata": {"trigger_fact_id": fact_id, "fact_nature": fact.fact_nature},
    }


def default_source_catalog() -> list[EvidenceSource]:
    """Return the planned strong/mid/weak evidence sources."""
    return [
        EvidenceSource(
            source_id="cninfo_announcement",
            source_name="巨潮资讯公告全文",
            source_type="announcement",
            source_level="strong",
            source_reliability_score=0.95,
            confidence_cap=0.95,
            is_official=True,
            is_third_party_estimate=False,
            is_market_sentiment=False,
            requires_cross_validation=False,
            license_status="public_source_verify_terms",
            update_frequency="daily",
            crawl_method="api_or_html",
            metadata={"batch": "P1", "stage_permission": "can_upgrade_with_review"},
        ),
        EvidenceSource(
            source_id="exchange_announcement",
            source_name="交易所公告全文",
            source_type="exchange_announcement",
            source_level="strong",
            source_reliability_score=0.95,
            confidence_cap=0.95,
            is_official=True,
            is_third_party_estimate=False,
            is_market_sentiment=False,
            requires_cross_validation=False,
            license_status="public_source_verify_terms",
            update_frequency="daily",
            crawl_method="api_or_html",
            metadata={"batch": "P1", "stage_permission": "can_upgrade_with_review"},
        ),
        EvidenceSource(
            source_id="tender_procurement",
            source_name="招投标和政府采购",
            source_type="tender",
            source_level="strong",
            source_reliability_score=0.9,
            confidence_cap=0.9,
            is_official=True,
            is_third_party_estimate=False,
            is_market_sentiment=False,
            requires_cross_validation=False,
            license_status="public_source_verify_terms",
            update_frequency="daily",
            crawl_method="html_or_manual_import",
            metadata={"batch": "P1", "stage_permission": "commercial_candidate"},
        ),
        EvidenceSource(
            source_id="patent_standard",
            source_name="专利和标准",
            source_type="patent_standard",
            source_level="strong",
            source_reliability_score=0.88,
            confidence_cap=0.88,
            is_official=True,
            is_third_party_estimate=False,
            is_market_sentiment=False,
            requires_cross_validation=False,
            license_status="public_source_verify_terms",
            update_frequency="weekly",
            crawl_method="api_or_manual_import",
            metadata={"batch": "P1", "stage_permission": "moat_only"},
        ),
        EvidenceSource(
            source_id="manual_announcement",
            source_name="人工导入公告/强证据文本",
            source_type="announcement",
            source_level="strong",
            source_reliability_score=0.9,
            confidence_cap=0.9,
            is_official=True,
            is_third_party_estimate=False,
            is_market_sentiment=False,
            requires_cross_validation=False,
            license_status="manual_verified",
            update_frequency="manual",
            crawl_method="manual_import",
            metadata={"batch": "P1", "stage_permission": "can_upgrade_with_review"},
        ),
        EvidenceSource(
            source_id="financial_news_authoritative",
            source_name="权威财经新闻",
            source_type="financial_news",
            source_level="mid",
            source_reliability_score=0.75,
            confidence_cap=0.75,
            is_official=False,
            is_third_party_estimate=False,
            is_market_sentiment=False,
            requires_cross_validation=True,
            license_status="requires_source_or_subscription",
            update_frequency="daily",
            crawl_method="api_or_manual_import",
            metadata={"batch": "P2", "stage_permission": "pending_review_only"},
        ),
        EvidenceSource(
            source_id="broker_report",
            source_name="券商研报",
            source_type="broker_report",
            source_level="mid",
            source_reliability_score=0.75,
            confidence_cap=0.75,
            is_official=False,
            is_third_party_estimate=True,
            is_market_sentiment=False,
            requires_cross_validation=True,
            license_status="requires_authorization",
            update_frequency="daily_or_weekly",
            crawl_method="manual_import_or_authorized_api",
            metadata={"batch": "P2", "stage_permission": "expectation_only"},
        ),
        EvidenceSource(
            source_id="industry_price_data",
            source_name="行业价格和景气度数据",
            source_type="industry_price",
            source_level="mid",
            source_reliability_score=0.7,
            confidence_cap=0.7,
            is_official=False,
            is_third_party_estimate=True,
            is_market_sentiment=False,
            requires_cross_validation=True,
            license_status="requires_authorization",
            update_frequency="daily_or_weekly",
            crawl_method="authorized_api_or_manual_import",
            metadata={"batch": "P2", "stage_permission": "industry_cycle_only"},
        ),
        EvidenceSource(
            source_id="market_community_signal",
            source_name="市场社区弱信号",
            source_type="market_community",
            source_level="weak",
            source_reliability_score=0.35,
            confidence_cap=0.45,
            is_official=False,
            is_third_party_estimate=False,
            is_market_sentiment=True,
            requires_cross_validation=True,
            license_status="requires_compliance_review",
            update_frequency="daily",
            crawl_method="manual_import_or_compliant_connector",
            metadata={"batch": "P3", "stage_permission": "warning_only"},
        ),
        EvidenceSource(
            source_id="recruiting_signal",
            source_name="招聘弱信号",
            source_type="recruiting",
            source_level="weak",
            source_reliability_score=0.4,
            confidence_cap=0.45,
            is_official=False,
            is_third_party_estimate=False,
            is_market_sentiment=False,
            requires_cross_validation=True,
            license_status="requires_compliance_review",
            update_frequency="weekly",
            crawl_method="manual_import_or_compliant_connector",
            metadata={"batch": "P3", "stage_permission": "warning_only"},
        ),
        EvidenceSource(
            source_id="social_official_signal",
            source_name="公司公众号和展会弱信号",
            source_type="social_official",
            source_level="weak",
            source_reliability_score=0.45,
            confidence_cap=0.45,
            is_official=False,
            is_third_party_estimate=False,
            is_market_sentiment=False,
            requires_cross_validation=True,
            license_status="requires_compliance_review",
            update_frequency="daily_or_weekly",
            crawl_method="manual_import_or_compliant_connector",
            metadata={"batch": "P3", "stage_permission": "warning_only"},
        ),
    ]


def build_document_hash(source_id: str, url: str | None, title: str, content: str) -> str:
    normalized = "\n".join(
        [
            str(source_id or "").strip(),
            str(url or "").strip(),
            " ".join(str(title or "").split()),
            " ".join(str(content or "").split()),
        ]
    )
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _stable_id(prefix: str, *parts: object, length: int = 24) -> str:
    payload = "|".join(str(part or "") for part in parts)
    return f"{prefix}-{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:length]}"


def _dedupe_text(items: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in items:
        text = " ".join(str(item or "").strip().split())
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _coerce_l1_l8_path(value: object) -> list[str]:
    if isinstance(value, list):
        result: list[str] = []
        for item in value:
            if isinstance(item, dict):
                text = str(item.get("name") or item.get("display_name") or "").strip()
            else:
                text = str(item).strip()
            if text:
                result.append(text)
        return result
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return _coerce_l1_l8_path(parsed)
        except json.JSONDecodeError:
            pass
        return [item.strip() for item in text.replace(">", "/").split("/") if item.strip()]
    return []


def build_mapping_search_terms(mapping: dict) -> dict:
    """Build stable search terms for one business-tag mapping."""
    company_name = str(mapping.get("company_name") or mapping.get("name") or "").strip()
    code = str(mapping.get("code") or "").strip()
    tag_name = str(mapping.get("tag_name") or "").strip()
    chain_id = str(mapping.get("chain_id") or "").strip()
    node_id = str(mapping.get("node_id") or "").strip()
    path_items = _coerce_l1_l8_path(mapping.get("l1_l8_path"))

    terms = _dedupe_text([
        company_name,
        tag_name,
        *path_items,
        chain_id,
        node_id,
    ])
    query_heads = [item for item in (company_name, code) if item]
    query_tails = _dedupe_text([tag_name, *path_items[-3:], chain_id, node_id])
    queries: list[str] = []
    for head in query_heads:
        for tail in query_tails:
            clean_tail = tail
            if company_name and clean_tail.startswith(f"{company_name} - "):
                clean_tail = clean_tail.removeprefix(f"{company_name} - ").strip()
            if clean_tail and clean_tail != head:
                queries.append(f"{head} {clean_tail}")
    queries = _dedupe_text(queries)
    return {
        "mapping_id": str(mapping.get("mapping_id") or ""),
        "code": code,
        "company_name": company_name,
        "tag_name": tag_name,
        "chain_id": chain_id,
        "node_id": node_id,
        "terms": terms,
        "queries": queries,
    }


def build_legacy_evidence_event_record(
    *,
    fact_id: str,
    mapping_id: str | None,
    company_code: str,
    node_id: str | None,
    source_id: str,
    source_type: str,
    title: str,
    url: str | None,
    fact: ExtractedFact,
) -> dict:
    if fact.commercial_stage_signal:
        evidence_type = "commercial_stage"
    elif fact.research_stage_signal:
        evidence_type = "research_stage"
    elif fact.moat_signal:
        evidence_type = "moat"
    elif fact.profit_signal:
        evidence_type = "profit"
    elif fact.growth_signal:
        evidence_type = "growth"
    else:
        evidence_type = fact.fact_type or "business_presence"
    review_status = "approved" if fact.source_level == "strong" and fact.validation_status == "confirmed" else "pending_review"
    event_id = _stable_id("EV", fact_id, mapping_id, company_code, title)
    return {
        "event_id": event_id,
        "mapping_id": mapping_id,
        "code": company_code,
        "node_id": node_id,
        "event_date": datetime.now().date(),
        "source_type": source_type,
        "source_id": source_id,
        "title": title,
        "excerpt": fact.original_quote,
        "original_url": url,
        "evidence_type": evidence_type,
        "impact_dimensions": {
            "research_stage": fact.research_stage_signal,
            "commercial_stage": fact.commercial_stage_signal,
            "growth": fact.growth_signal,
            "profit": fact.profit_signal,
            "moat": fact.moat_signal,
            "risk": fact.risk_signal,
            "fact_id": fact_id,
        },
        "confidence": min(fact.confidence, fact.confidence_cap),
        "review_status": review_status,
        "review_note": "auto synced from evidence_extracted_facts",
    }


def _source_by_id(source_id: str) -> EvidenceSource | None:
    for source in default_source_catalog():
        if source.source_id == source_id:
            return source
    return None


def _ensure_source(cur, source: EvidenceSource) -> None:
    record = source.to_record()
    cur.execute(
        """
        INSERT INTO evidence_source_catalog (
            source_id, source_name, source_type, source_level,
            source_reliability_score, confidence_cap, is_official,
            is_third_party_estimate, is_market_sentiment,
            requires_cross_validation, license_status,
            update_frequency, crawl_method, enabled, metadata
        )
        VALUES (
            %(source_id)s, %(source_name)s, %(source_type)s, %(source_level)s,
            %(source_reliability_score)s, %(confidence_cap)s, %(is_official)s,
            %(is_third_party_estimate)s, %(is_market_sentiment)s,
            %(requires_cross_validation)s, %(license_status)s,
            %(update_frequency)s, %(crawl_method)s, %(enabled)s, %(metadata_json)s::jsonb
        )
        ON CONFLICT (source_id) DO UPDATE SET
            source_name = EXCLUDED.source_name,
            source_type = EXCLUDED.source_type,
            source_level = EXCLUDED.source_level,
            source_reliability_score = EXCLUDED.source_reliability_score,
            confidence_cap = EXCLUDED.confidence_cap,
            is_official = EXCLUDED.is_official,
            is_third_party_estimate = EXCLUDED.is_third_party_estimate,
            is_market_sentiment = EXCLUDED.is_market_sentiment,
            requires_cross_validation = EXCLUDED.requires_cross_validation,
            license_status = EXCLUDED.license_status,
            update_frequency = EXCLUDED.update_frequency,
            crawl_method = EXCLUDED.crawl_method,
            enabled = EXCLUDED.enabled,
            metadata = EXCLUDED.metadata,
            updated_at = CURRENT_TIMESTAMP
        """,
        {**record, "metadata_json": json.dumps(record["metadata"], ensure_ascii=False)},
    )


def _query_source_record(cur, source_id: str) -> dict:
    cur.execute(
        """
        SELECT source_id, source_type, source_level, confidence_cap, license_status
        FROM evidence_source_catalog
        WHERE source_id = %s
        """,
        (source_id,),
    )
    row = cur.fetchone()
    if row:
        return {
            "source_id": row[0],
            "source_type": row[1],
            "source_level": row[2],
            "confidence_cap": float(row[3] or _confidence_cap_for_level(row[2])),
            "license_status": row[4],
        }
    source = _source_by_id(source_id)
    if not source:
        raise ValueError(f"unknown evidence source: {source_id}")
    _ensure_source(cur, source)
    return {
        "source_id": source.source_id,
        "source_type": source.source_type,
        "source_level": source.source_level,
        "confidence_cap": source.confidence_cap,
        "license_status": source.license_status,
    }


def _query_mapping_for_text(cur, company_code: str, text: str, l5_tag: str | None) -> dict:
    if l5_tag:
        cur.execute(
            """
            SELECT mapping_id, chain_id, tag_name, node_id
            FROM business_tag_mapping
            WHERE code = %s AND tag_name = %s
            ORDER BY updated_at DESC NULLS LAST
            LIMIT 1
            """,
            (company_code, l5_tag),
        )
    else:
        cur.execute(
            """
            SELECT mapping_id, chain_id, tag_name, node_id
            FROM business_tag_mapping
            WHERE code = %s
            ORDER BY confidence DESC NULLS LAST, updated_at DESC NULLS LAST
            LIMIT 20
            """,
            (company_code,),
        )
    rows = cur.fetchall()
    if not rows:
        return {"mapping_id": None, "chain_id": None, "l5_tag": l5_tag or "", "node_id": None}
    if l5_tag:
        row = rows[0]
        return {"mapping_id": row[0], "chain_id": row[1], "l5_tag": row[2], "node_id": row[3]}
    for row in rows:
        tag_name = str(row[2] or "")
        if tag_name and tag_name in text:
            return {"mapping_id": row[0], "chain_id": row[1], "l5_tag": tag_name, "node_id": row[3]}
    row = rows[0]
    return {"mapping_id": row[0], "chain_id": row[1], "l5_tag": row[2], "node_id": row[3]}


def _legacy_source_for_level(level: SourceLevel) -> EvidenceSource:
    return EvidenceSource(
        source_id=f"legacy_{level}_evidence_event",
        source_name=f"历史证据事件回填({level})",
        source_type="legacy_business_tag_evidence",
        source_level=level,
        source_reliability_score={"strong": 0.85, "mid": 0.65, "weak": 0.35}[level],
        confidence_cap=_confidence_cap_for_level(level),
        is_official=(level == "strong"),
        is_third_party_estimate=False,
        is_market_sentiment=(level == "weak"),
        requires_cross_validation=(level != "strong"),
        license_status="internal_derived_from_existing_events",
        update_frequency="backfill",
        crawl_method="database_backfill",
        enabled=True,
        metadata={"batch": "backfill", "source_table": "business_tag_evidence_events"},
    )


def _upsert_legacy_evidence_event(cur, record: dict) -> None:
    cur.execute(
        """
        INSERT INTO business_tag_evidence_events (
            event_id, mapping_id, code, node_id, event_date, source_type,
            source_id, title, excerpt, original_url, evidence_type,
            impact_dimensions, confidence, review_status, review_note
        )
        VALUES (
            %(event_id)s, %(mapping_id)s, %(code)s, %(node_id)s, %(event_date)s,
            %(source_type)s, %(source_id)s, %(title)s, %(excerpt)s,
            %(original_url)s, %(evidence_type)s, %(impact_dimensions_json)s::jsonb,
            %(confidence)s, %(review_status)s, %(review_note)s
        )
        ON CONFLICT (event_id) DO UPDATE SET
            mapping_id = EXCLUDED.mapping_id,
            code = EXCLUDED.code,
            node_id = EXCLUDED.node_id,
            event_date = EXCLUDED.event_date,
            source_type = EXCLUDED.source_type,
            source_id = EXCLUDED.source_id,
            title = EXCLUDED.title,
            excerpt = EXCLUDED.excerpt,
            original_url = EXCLUDED.original_url,
            evidence_type = EXCLUDED.evidence_type,
            impact_dimensions = EXCLUDED.impact_dimensions,
            confidence = EXCLUDED.confidence,
            review_status = EXCLUDED.review_status,
            review_note = EXCLUDED.review_note
        """,
        {**record, "impact_dimensions_json": json.dumps(record["impact_dimensions"], ensure_ascii=False)},
    )


def ingest_text_document(
    *,
    pg_url: str,
    source_id: str,
    company_code: str,
    company_name: str,
    title: str,
    text: str,
    url: str | None = None,
    l5_tag: str | None = None,
    l6_route: str | None = None,
) -> dict:
    import psycopg2

    with psycopg2.connect(pg_url) as conn:
        with conn.cursor() as cur:
            source = _query_source_record(cur, source_id)
            mapping = _query_mapping_for_text(cur, company_code, text, l5_tag)
            resolved_l5 = str(mapping.get("l5_tag") or l5_tag or "")
            fact = extract_fact_from_text(
                text=text,
                source_level=source["source_level"],
                company_code=company_code,
                l5_tag=resolved_l5,
                l6_route=l6_route,
            )
            content_hash = build_document_hash(source_id, url, title, text)
            doc_id = _stable_id("DOC", source_id, content_hash)
            fact_id = _stable_id("FACT", doc_id, company_code, resolved_l5, fact.fact_type)
            cur.execute(
                """
                INSERT INTO raw_evidence_documents (
                    doc_id, source_id, source_type, source_level, company_code,
                    company_name, title, publish_time, url, content_text,
                    content_hash, doc_status, license_status, metadata
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                ON CONFLICT (content_hash) DO UPDATE SET
                    source_id = EXCLUDED.source_id,
                    source_type = EXCLUDED.source_type,
                    source_level = EXCLUDED.source_level,
                    company_code = EXCLUDED.company_code,
                    company_name = EXCLUDED.company_name,
                    title = EXCLUDED.title,
                    url = EXCLUDED.url,
                    content_text = EXCLUDED.content_text,
                    doc_status = EXCLUDED.doc_status,
                    license_status = EXCLUDED.license_status,
                    metadata = EXCLUDED.metadata,
                    updated_at = CURRENT_TIMESTAMP
                RETURNING doc_id
                """,
                (
                    doc_id,
                    source_id,
                    source["source_type"],
                    source["source_level"],
                    company_code,
                    company_name,
                    title,
                    datetime.now(),
                    url,
                    text,
                    content_hash,
                    "active",
                    source["license_status"],
                    json.dumps({"ingest_method": "manual_text"}, ensure_ascii=False),
                ),
            )
            stored_doc_id = cur.fetchone()[0]
            cur.execute(
                """
                INSERT INTO evidence_extracted_facts (
                    fact_id, doc_id, mapping_id, company_code, chain_id,
                    l5_tag, l6_route, business_segment, fact_type,
                    fact_nature, fact_value, original_quote, source_level,
                    confidence, confidence_cap, research_stage_signal,
                    commercial_stage_signal, growth_signal, profit_signal,
                    moat_signal, risk_signal, validation_status, metadata
                )
                VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s::jsonb
                )
                ON CONFLICT (fact_id) DO UPDATE SET
                    doc_id = EXCLUDED.doc_id,
                    mapping_id = EXCLUDED.mapping_id,
                    chain_id = EXCLUDED.chain_id,
                    l5_tag = EXCLUDED.l5_tag,
                    l6_route = EXCLUDED.l6_route,
                    fact_type = EXCLUDED.fact_type,
                    fact_nature = EXCLUDED.fact_nature,
                    fact_value = EXCLUDED.fact_value,
                    original_quote = EXCLUDED.original_quote,
                    source_level = EXCLUDED.source_level,
                    confidence = EXCLUDED.confidence,
                    confidence_cap = EXCLUDED.confidence_cap,
                    research_stage_signal = EXCLUDED.research_stage_signal,
                    commercial_stage_signal = EXCLUDED.commercial_stage_signal,
                    growth_signal = EXCLUDED.growth_signal,
                    profit_signal = EXCLUDED.profit_signal,
                    moat_signal = EXCLUDED.moat_signal,
                    risk_signal = EXCLUDED.risk_signal,
                    validation_status = EXCLUDED.validation_status,
                    metadata = EXCLUDED.metadata,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    fact_id,
                    stored_doc_id,
                    mapping.get("mapping_id"),
                    company_code,
                    mapping.get("chain_id"),
                    resolved_l5,
                    l6_route,
                    None,
                    fact.fact_type,
                    fact.fact_nature,
                    fact.fact_value,
                    fact.original_quote,
                    fact.source_level,
                    fact.confidence,
                    fact.confidence_cap,
                    fact.research_stage_signal,
                    fact.commercial_stage_signal,
                    fact.growth_signal,
                    fact.profit_signal,
                    fact.moat_signal,
                    fact.risk_signal,
                    fact.validation_status,
                    json.dumps({"source_id": source_id, "company_name": company_name}, ensure_ascii=False),
                ),
            )
            legacy_event = build_legacy_evidence_event_record(
                fact_id=fact_id,
                mapping_id=mapping.get("mapping_id"),
                company_code=company_code,
                node_id=mapping.get("node_id"),
                source_id=source_id,
                source_type=source["source_type"],
                title=title,
                url=url,
                fact=fact,
            )
            _upsert_legacy_evidence_event(cur, legacy_event)
            freshness_rows = refresh_evidence_freshness(cur)
        conn.commit()
    return {
        "documents": 1,
        "facts": 1,
        "legacy_events": 1,
        "freshness_rows": freshness_rows,
        "doc_id": stored_doc_id,
        "fact_id": fact_id,
        "event_id": legacy_event["event_id"],
    }


def refresh_evidence_freshness(cur) -> int:
    cur.execute(
        """
        WITH grouped AS (
            SELECT
                f.mapping_id,
                MAX(d.publish_time::date) FILTER (WHERE f.source_level = 'strong') AS last_strong,
                MAX(d.publish_time::date) FILTER (WHERE f.source_level = 'mid') AS last_mid,
                MAX(d.publish_time::date) FILTER (WHERE f.source_level = 'weak') AS last_weak,
                MAX(d.publish_time::date) AS last_any
            FROM evidence_extracted_facts f
            JOIN raw_evidence_documents d ON d.doc_id = f.doc_id
            WHERE f.mapping_id IS NOT NULL
            GROUP BY f.mapping_id
        ),
        scored AS (
            SELECT
                m.mapping_id,
                g.last_strong,
                g.last_mid,
                g.last_weak,
                g.last_any,
                COALESCE(GREATEST(g.last_strong, g.last_mid), g.last_any) AS effective_last
            FROM business_tag_mapping m
            LEFT JOIN grouped g ON g.mapping_id = m.mapping_id
        )
        INSERT INTO business_tag_evidence_freshness (
            mapping_id, last_strong_evidence_date, last_mid_evidence_date,
            last_weak_signal_date, last_any_evidence_date, days_since_update,
            freshness_status, next_review_date, stale_reason, updated_at
        )
        SELECT
            mapping_id,
            last_strong,
            last_mid,
            last_weak,
            last_any,
            CASE WHEN effective_last IS NULL THEN NULL ELSE CURRENT_DATE - effective_last END,
            CASE
                WHEN effective_last IS NULL THEN 'unknown'
                WHEN CURRENT_DATE - effective_last <= 30 THEN 'fresh'
                WHEN CURRENT_DATE - effective_last <= 90 THEN 'stale'
                ELSE 'expired'
            END,
            CASE
                WHEN effective_last IS NULL THEN CURRENT_DATE
                WHEN CURRENT_DATE - effective_last <= 30 THEN effective_last + 30
                WHEN CURRENT_DATE - effective_last <= 90 THEN effective_last + 90
                ELSE CURRENT_DATE
            END,
            CASE
                WHEN last_strong IS NULL AND last_mid IS NULL AND last_weak IS NOT NULL THEN 'only_weak_signals'
                WHEN effective_last IS NULL THEN 'no_evidence'
                ELSE NULL
            END,
            CURRENT_TIMESTAMP
        FROM scored
        ON CONFLICT (mapping_id) DO UPDATE SET
            last_strong_evidence_date = EXCLUDED.last_strong_evidence_date,
            last_mid_evidence_date = EXCLUDED.last_mid_evidence_date,
            last_weak_signal_date = EXCLUDED.last_weak_signal_date,
            last_any_evidence_date = EXCLUDED.last_any_evidence_date,
            days_since_update = EXCLUDED.days_since_update,
            freshness_status = EXCLUDED.freshness_status,
            next_review_date = EXCLUDED.next_review_date,
            stale_reason = EXCLUDED.stale_reason,
            updated_at = CURRENT_TIMESTAMP
        """,
    )
    return cur.rowcount


def backfill_existing_events(*, pg_url: str, run_prefix: str | None = None, limit: int = 500) -> dict:
    import psycopg2

    where = []
    params: list[object] = []
    if run_prefix:
        where.append("(e.event_id LIKE %s OR e.mapping_id LIKE %s)")
        params.extend([f"{run_prefix}%", f"{run_prefix}%"])
    where_sql = "WHERE " + " AND ".join(where) if where else ""
    params.append(limit)

    with psycopg2.connect(pg_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT e.event_id, e.mapping_id, e.code, e.event_date, e.source_type,
                       e.title, e.excerpt, e.original_url, e.evidence_type,
                       e.confidence, e.review_status, m.tag_name, m.chain_id
                FROM business_tag_evidence_events e
                LEFT JOIN business_tag_mapping m ON m.mapping_id = e.mapping_id
                {where_sql}
                ORDER BY e.created_at DESC NULLS LAST, e.event_date DESC NULLS LAST
                LIMIT %s
                """,
                params,
            )
            rows = cur.fetchall()
            documents = 0
            facts = 0
            for row in rows:
                (
                    event_id,
                    mapping_id,
                    code,
                    event_date,
                    source_type,
                    title,
                    excerpt,
                    original_url,
                    evidence_type,
                    confidence,
                    review_status,
                    tag_name,
                    chain_id,
                ) = row
                level = map_source_type_to_source_level(str(source_type or ""))
                source = _legacy_source_for_level(level)
                _ensure_source(cur, source)
                text = str(excerpt or title or "")
                title_text = str(title or f"历史证据事件 {event_id}")
                content_hash = build_document_hash(source.source_id, str(original_url or event_id), title_text, text)
                doc_id = _stable_id("DOC", source.source_id, content_hash)
                fact_id = _stable_id("FACT", event_id, mapping_id, code, tag_name)
                fact = extract_fact_from_text(
                    text=text,
                    source_level=level,
                    company_code=str(code or ""),
                    l5_tag=str(tag_name or ""),
                    l6_route=None,
                )
                cur.execute(
                    """
                    INSERT INTO raw_evidence_documents (
                        doc_id, source_id, source_type, source_level, company_code,
                        title, publish_time, url, content_text, content_hash,
                        doc_status, license_status, metadata
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                    ON CONFLICT (content_hash) DO UPDATE SET
                        title = EXCLUDED.title,
                        content_text = EXCLUDED.content_text,
                        metadata = EXCLUDED.metadata,
                        updated_at = CURRENT_TIMESTAMP
                    RETURNING doc_id
                    """,
                    (
                        doc_id,
                        source.source_id,
                        str(source_type or source.source_type),
                        level,
                        code,
                        title_text,
                        event_date or datetime.now(),
                        original_url,
                        text,
                        content_hash,
                        "active",
                        source.license_status,
                        json.dumps({"source_event_id": event_id, "review_status": review_status}, ensure_ascii=False),
                    ),
                )
                stored_doc_id = cur.fetchone()[0]
                documents += 1
                cur.execute(
                    """
                    INSERT INTO evidence_extracted_facts (
                        fact_id, doc_id, mapping_id, company_code, chain_id,
                        l5_tag, l6_route, fact_type, fact_nature, fact_value,
                        original_quote, source_level, confidence, confidence_cap,
                        research_stage_signal, commercial_stage_signal,
                        growth_signal, profit_signal, moat_signal, risk_signal,
                        validation_status, evidence_event_id, metadata
                    )
                    VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb
                    )
                    ON CONFLICT (fact_id) DO UPDATE SET
                        doc_id = EXCLUDED.doc_id,
                        original_quote = EXCLUDED.original_quote,
                        confidence = EXCLUDED.confidence,
                        confidence_cap = EXCLUDED.confidence_cap,
                        research_stage_signal = EXCLUDED.research_stage_signal,
                        commercial_stage_signal = EXCLUDED.commercial_stage_signal,
                        growth_signal = EXCLUDED.growth_signal,
                        profit_signal = EXCLUDED.profit_signal,
                        moat_signal = EXCLUDED.moat_signal,
                        risk_signal = EXCLUDED.risk_signal,
                        validation_status = EXCLUDED.validation_status,
                        evidence_event_id = EXCLUDED.evidence_event_id,
                        metadata = EXCLUDED.metadata,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (
                        fact_id,
                        stored_doc_id,
                        mapping_id,
                        code,
                        chain_id,
                        tag_name,
                        None,
                        fact.fact_type if fact.fact_type != "business_presence" else str(evidence_type or fact.fact_type),
                        fact.fact_nature,
                        fact.fact_value,
                        fact.original_quote,
                        level,
                        min(float(confidence or fact.confidence), fact.confidence_cap),
                        fact.confidence_cap,
                        fact.research_stage_signal,
                        fact.commercial_stage_signal,
                        fact.growth_signal,
                        fact.profit_signal,
                        fact.moat_signal,
                        fact.risk_signal,
                        "confirmed" if str(review_status or "") == "approved" and level == "strong" else fact.validation_status,
                        event_id,
                        json.dumps({"backfill": True, "source_type": source_type}, ensure_ascii=False),
                    ),
                )
                facts += 1
            freshness_rows = refresh_evidence_freshness(cur)
        conn.commit()
    return {"events_read": len(rows), "documents": documents, "facts": facts, "freshness_rows": freshness_rows}


def refresh_stage_transitions(*, pg_url: str, run_prefix: str | None = None, limit: int = 1000) -> dict:
    import psycopg2

    with psycopg2.connect(pg_url) as conn:
        with conn.cursor() as cur:
            params: list[object] = []
            where = [
                "f.mapping_id IS NOT NULL",
                "(f.research_stage_signal IS NOT NULL OR f.commercial_stage_signal IS NOT NULL)",
                "f.source_level IN ('strong','mid')",
            ]
            if run_prefix:
                where.append("f.mapping_id LIKE %s")
                params.append(f"{run_prefix}%")
            params.append(limit)
            cur.execute(
                f"""
                SELECT f.fact_id, f.mapping_id, f.evidence_event_id, f.source_level,
                       f.research_stage_signal, f.commercial_stage_signal,
                       f.original_quote, f.created_at
                FROM evidence_extracted_facts f
                WHERE {" AND ".join(where)}
                ORDER BY f.created_at DESC
                LIMIT %s
                """,
                params,
            )
            facts = cur.fetchall()
            transitions = 0
            applied = 0
            for fact in facts:
                fact_id, mapping_id, event_id, source_level, research_signal, commercial_signal, quote, created_at = fact
                cur.execute(
                    """
                    SELECT research_stage, commercialization_stage
                    FROM business_tag_stage_tracking
                    WHERE mapping_id = %s
                    ORDER BY trade_date DESC, created_at DESC
                    LIMIT 1
                    """,
                    (mapping_id,),
                )
                stage_row = cur.fetchone()
                old_research = str(stage_row[0]) if stage_row else "R0"
                old_commercial = str(stage_row[1]) if stage_row else "C0"
                decision = decide_stage_transition(
                    source_level=source_level,
                    research_stage_signal=research_signal,
                    commercial_stage_signal=commercial_signal,
                    old_research_stage=old_research,
                    old_commercial_stage=old_commercial,
                )
                if not decision.new_research_stage and not decision.new_commercial_stage:
                    continue
                new_research = decision.new_research_stage or old_research
                new_commercial = decision.new_commercial_stage or old_commercial
                transition_id = _stable_id("TRANS", fact_id, mapping_id, new_research, new_commercial)
                reason = f"{decision.reason}: {str(quote or '')[:240]}"
                cur.execute(
                    """
                    INSERT INTO business_tag_stage_transition_log (
                        transition_id, mapping_id, old_research_stage, new_research_stage,
                        old_commercial_stage, new_commercial_stage, trigger_fact_id,
                        trigger_event_id, change_reason, review_status
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (transition_id) DO UPDATE SET
                        change_reason = EXCLUDED.change_reason,
                        review_status = EXCLUDED.review_status
                    """,
                    (
                        transition_id,
                        mapping_id,
                        old_research,
                        new_research,
                        old_commercial,
                        new_commercial,
                        fact_id,
                        event_id,
                        reason,
                        decision.review_status,
                    ),
                )
                transitions += 1
                if decision.auto_apply:
                    stage_id = _stable_id("STAGE", transition_id)
                    cur.execute(
                        """
                        INSERT INTO business_tag_stage_tracking (
                            stage_id, mapping_id, trade_date, research_stage,
                            commercialization_stage, stage_reason, source_event_id,
                            last_stage_change_date, review_status
                        )
                        VALUES (%s, %s, CURRENT_DATE, %s, %s, %s, %s, CURRENT_DATE, %s)
                        ON CONFLICT (stage_id) DO UPDATE SET
                            research_stage = EXCLUDED.research_stage,
                            commercialization_stage = EXCLUDED.commercialization_stage,
                            stage_reason = EXCLUDED.stage_reason,
                            source_event_id = EXCLUDED.source_event_id,
                            last_stage_change_date = EXCLUDED.last_stage_change_date,
                            review_status = EXCLUDED.review_status
                        """,
                        (
                            stage_id,
                            mapping_id,
                            new_research,
                            new_commercial,
                            reason,
                            event_id,
                            decision.review_status,
                        ),
                    )
                    applied += 1
        conn.commit()
    return {"facts_read": len(facts), "transitions": transitions, "stage_applied": applied}


def refresh_expectation_monitor(*, pg_url: str, run_prefix: str | None = None, limit: int = 1000) -> dict:
    import psycopg2

    with psycopg2.connect(pg_url) as conn:
        with conn.cursor() as cur:
            where = [
                "f.mapping_id IS NOT NULL",
                "(f.fact_nature = 'analyst_estimate' OR f.original_quote LIKE '%%预计%%' OR f.original_quote LIKE '%%有望%%' OR f.original_quote LIKE '%%放量%%')",
            ]
            params: list[object] = []
            if run_prefix:
                where.append("f.mapping_id LIKE %s")
                params.append(f"{run_prefix}%")
            params.append(limit)
            cur.execute(
                f"""
                SELECT f.fact_id, f.mapping_id, f.doc_id, f.company_code, f.l5_tag,
                       f.l6_route, f.fact_type, f.fact_nature, f.fact_value,
                       f.original_quote, f.source_level, f.confidence,
                       f.confidence_cap, f.research_stage_signal,
                       f.commercial_stage_signal, f.growth_signal,
                       f.profit_signal, f.moat_signal, f.risk_signal
                FROM evidence_extracted_facts f
                WHERE {" AND ".join(where)}
                ORDER BY f.created_at DESC
                LIMIT %s
                """,
                params,
            )
            rows = cur.fetchall()
            written = 0
            for row in rows:
                (
                    fact_id,
                    mapping_id,
                    doc_id,
                    company_code,
                    l5_tag,
                    l6_route,
                    fact_type,
                    fact_nature,
                    fact_value,
                    original_quote,
                    source_level,
                    confidence,
                    confidence_cap,
                    research_stage_signal,
                    commercial_stage_signal,
                    growth_signal,
                    profit_signal,
                    moat_signal,
                    risk_signal,
                ) = row
                fact = ExtractedFact(
                    company_code=str(company_code or ""),
                    l5_tag=str(l5_tag or ""),
                    l6_route=l6_route,
                    fact_type=str(fact_type or "expectation"),
                    fact_nature=str(fact_nature or "analyst_estimate"),
                    original_quote=str(original_quote or ""),
                    source_level=source_level,
                    confidence=float(confidence or 0.0),
                    confidence_cap=float(confidence_cap or _confidence_cap_for_level(source_level)),
                    validation_status="pending",
                    research_stage_signal=research_stage_signal,
                    commercial_stage_signal=commercial_stage_signal,
                    growth_signal=bool(growth_signal),
                    profit_signal=bool(profit_signal),
                    moat_signal=bool(moat_signal),
                    risk_signal=bool(risk_signal),
                    fact_value=fact_value,
                )
                record = build_expectation_monitor_record(
                    fact_id=fact_id,
                    mapping_id=mapping_id,
                    source_doc_id=doc_id,
                    fact=fact,
                )
                cur.execute(
                    """
                    INSERT INTO business_tag_expectation_monitor (
                        monitor_id, mapping_id, claim_text, claim_date,
                        claim_source_type, expected_result, expected_date,
                        actual_progress, gap_status, market_price_change,
                        evidence_ids, source_doc_id, review_status, metadata
                    )
                    VALUES (
                        %(monitor_id)s, %(mapping_id)s, %(claim_text)s, %(claim_date)s,
                        %(claim_source_type)s, %(expected_result)s, %(expected_date)s,
                        %(actual_progress)s, %(gap_status)s, %(market_price_change)s,
                        %(evidence_ids_json)s::jsonb, %(source_doc_id)s, %(review_status)s,
                        %(metadata_json)s::jsonb
                    )
                    ON CONFLICT (monitor_id) DO UPDATE SET
                        claim_text = EXCLUDED.claim_text,
                        expected_result = EXCLUDED.expected_result,
                        gap_status = EXCLUDED.gap_status,
                        review_status = EXCLUDED.review_status,
                        metadata = EXCLUDED.metadata,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    {
                        **record,
                        "evidence_ids_json": json.dumps(record["evidence_ids"], ensure_ascii=False),
                        "metadata_json": json.dumps(record["metadata"], ensure_ascii=False),
                    },
                )
                written += 1
        conn.commit()
    return {"facts_read": len(rows), "monitors": written}


def seed_source_catalog(pg_url: str) -> dict[str, int]:
    import psycopg2

    sources = default_source_catalog()
    inserted_or_updated = 0
    with psycopg2.connect(pg_url) as conn:
        with conn.cursor() as cur:
            for source in sources:
                record = source.to_record()
                cur.execute(
                    """
                    INSERT INTO evidence_source_catalog (
                        source_id, source_name, source_type, source_level,
                        source_reliability_score, confidence_cap, is_official,
                        is_third_party_estimate, is_market_sentiment,
                        requires_cross_validation, license_status,
                        update_frequency, crawl_method, enabled, metadata
                    )
                    VALUES (
                        %(source_id)s, %(source_name)s, %(source_type)s, %(source_level)s,
                        %(source_reliability_score)s, %(confidence_cap)s, %(is_official)s,
                        %(is_third_party_estimate)s, %(is_market_sentiment)s,
                        %(requires_cross_validation)s, %(license_status)s,
                        %(update_frequency)s, %(crawl_method)s, %(enabled)s, %(metadata_json)s::jsonb
                    )
                    ON CONFLICT (source_id) DO UPDATE SET
                        source_name = EXCLUDED.source_name,
                        source_type = EXCLUDED.source_type,
                        source_level = EXCLUDED.source_level,
                        source_reliability_score = EXCLUDED.source_reliability_score,
                        confidence_cap = EXCLUDED.confidence_cap,
                        is_official = EXCLUDED.is_official,
                        is_third_party_estimate = EXCLUDED.is_third_party_estimate,
                        is_market_sentiment = EXCLUDED.is_market_sentiment,
                        requires_cross_validation = EXCLUDED.requires_cross_validation,
                        license_status = EXCLUDED.license_status,
                        update_frequency = EXCLUDED.update_frequency,
                        crawl_method = EXCLUDED.crawl_method,
                        enabled = EXCLUDED.enabled,
                        metadata = EXCLUDED.metadata,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    {**record, "metadata_json": json.dumps(record["metadata"], ensure_ascii=False)},
                )
                inserted_or_updated += 1
        conn.commit()
    return {"inserted_or_updated": inserted_or_updated}


def generate_mapping_search_terms(*, pg_url: str, limit: int = 500, node_id: str | None = None) -> dict:
    import psycopg2

    conditions = ["COALESCE(m.status, '') <> 'rejected'"]
    params: list[object] = []
    if node_id:
        conditions.append("m.node_id = %s")
        params.append(node_id)
    params.append(limit)
    with psycopg2.connect(pg_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT m.mapping_id, m.code, COALESCE(s.name, m.code) AS company_name,
                       m.tag_name, m.chain_id, m.node_id, m.l1_l8_path
                FROM business_tag_mapping m
                LEFT JOIN stocks s
                  ON regexp_replace(s.code, '\\.(SZ|SH|BJ)$', '') = regexp_replace(m.code, '\\.(SZ|SH|BJ)$', '')
                WHERE {" AND ".join(conditions)}
                ORDER BY m.updated_at DESC NULLS LAST, m.confidence DESC NULLS LAST
                LIMIT %s
                """,
                params,
            )
            rows = cur.fetchall()
    items = [
        build_mapping_search_terms({
            "mapping_id": row[0],
            "code": row[1],
            "company_name": row[2],
            "tag_name": row[3],
            "chain_id": row[4],
            "node_id": row[5],
            "l1_l8_path": row[6],
        })
        for row in rows
    ]
    return {"mapping_count": len(items), "items": items}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Supply-chain evidence pipeline utility")
    sub = parser.add_subparsers(dest="command", required=True)

    seed = sub.add_parser("seed-source-catalog", help="Upsert planned evidence source catalog")
    seed.add_argument("--pg-url", default="postgresql://kronos:kronos@localhost:6432/kronos")

    ingest = sub.add_parser("ingest-text", help="Ingest one manually supplied evidence text")
    ingest.add_argument("--pg-url", default="postgresql://kronos:kronos@localhost:6432/kronos")
    ingest.add_argument("--source-id", required=True)
    ingest.add_argument("--company-code", required=True)
    ingest.add_argument("--company-name", default="")
    ingest.add_argument("--title", required=True)
    ingest.add_argument("--text", required=True)
    ingest.add_argument("--url")
    ingest.add_argument("--l5-tag")
    ingest.add_argument("--l6-route")

    backfill = sub.add_parser("backfill-existing-events", help="Backfill existing evidence events into raw documents and facts")
    backfill.add_argument("--pg-url", default="postgresql://kronos:kronos@localhost:6432/kronos")
    backfill.add_argument("--run-prefix")
    backfill.add_argument("--limit", type=int, default=500)

    stage = sub.add_parser("refresh-stage-transitions", help="Create stage transition logs from extracted facts")
    stage.add_argument("--pg-url", default="postgresql://kronos:kronos@localhost:6432/kronos")
    stage.add_argument("--run-prefix")
    stage.add_argument("--limit", type=int, default=1000)

    expectation = sub.add_parser("refresh-expectation-monitor", help="Create expectation monitor records from extracted facts")
    expectation.add_argument("--pg-url", default="postgresql://kronos:kronos@localhost:6432/kronos")
    expectation.add_argument("--run-prefix")
    expectation.add_argument("--limit", type=int, default=1000)

    search_terms = sub.add_parser("generate-search-terms", help="Generate dry-run search terms from business_tag_mapping")
    search_terms.add_argument("--pg-url", default="postgresql://kronos:kronos@localhost:6432/kronos")
    search_terms.add_argument("--limit", type=int, default=500)
    search_terms.add_argument("--node-id")

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.command == "seed-source-catalog":
        print(json.dumps(seed_source_catalog(args.pg_url), ensure_ascii=False))
        return 0
    if args.command == "ingest-text":
        print(json.dumps(ingest_text_document(
            pg_url=args.pg_url,
            source_id=args.source_id,
            company_code=args.company_code,
            company_name=args.company_name,
            title=args.title,
            text=args.text,
            url=args.url,
            l5_tag=args.l5_tag,
            l6_route=args.l6_route,
        ), ensure_ascii=False))
        return 0
    if args.command == "backfill-existing-events":
        print(json.dumps(backfill_existing_events(
            pg_url=args.pg_url,
            run_prefix=args.run_prefix,
            limit=args.limit,
        ), ensure_ascii=False))
        return 0
    if args.command == "refresh-stage-transitions":
        print(json.dumps(refresh_stage_transitions(
            pg_url=args.pg_url,
            run_prefix=args.run_prefix,
            limit=args.limit,
        ), ensure_ascii=False))
        return 0
    if args.command == "refresh-expectation-monitor":
        print(json.dumps(refresh_expectation_monitor(
            pg_url=args.pg_url,
            run_prefix=args.run_prefix,
            limit=args.limit,
        ), ensure_ascii=False))
        return 0
    if args.command == "generate-search-terms":
        print(json.dumps(generate_mapping_search_terms(
            pg_url=args.pg_url,
            limit=args.limit,
            node_id=args.node_id,
        ), ensure_ascii=False))
        return 0
    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
