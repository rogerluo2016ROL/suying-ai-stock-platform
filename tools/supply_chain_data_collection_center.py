#!/usr/bin/env python3
"""Supply-chain data collection center.

This module owns source registration, dry-run keyword planning, simple document
normalization, conservative L8 fact extraction, and collection quality reports.
Crawler adapters are added source by source; this file keeps their shared
contracts stable.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import tempfile
from html import unescape
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urljoin, urlparse


SourceLevel = Literal["strong", "mid", "weak"]


@dataclass(frozen=True)
class CollectionSource:
    source_id: str
    source_name: str
    source_type: str
    source_level: SourceLevel
    confidence_cap: float
    license_status: str
    update_frequency: str
    crawl_method: str
    enabled: bool
    requires_cross_validation: bool
    is_official: bool
    is_market_sentiment: bool = False
    base_url: str | None = None
    rate_limit_per_minute: int | None = None
    metadata: dict | None = None

    def to_record(self) -> dict:
        record = asdict(self)
        record["source_reliability_score"] = {
            "strong": 0.9,
            "mid": 0.7,
            "weak": 0.4,
        }[self.source_level]
        record["is_third_party_estimate"] = self.source_level == "mid" and not self.is_official
        record["metadata"] = record["metadata"] or {}
        return record


@dataclass(frozen=True)
class RawDocument:
    source_id: str
    source_level: SourceLevel
    title: str
    content_text: str
    url: str | None = None
    company_code: str | None = None
    company_name: str | None = None
    publish_time: str | None = None
    doc_type: str | None = None
    metadata: dict[str, Any] | None = None

    @property
    def content_hash(self) -> str:
        return build_document_hash(self.source_id, self.url or "", self.title, self.content_text)

    @property
    def doc_id(self) -> str:
        return "DOC-" + self.content_hash[:24]


@dataclass(frozen=True)
class ExtractedFact:
    company_code: str
    fact_type: str
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
    metadata: dict[str, Any] | None = None


COMMERCIAL_STAGE_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("C4", ("批量供货", "批量出货", "批量订单", "中标", "合同")),
    ("C3", ("量产", "产能释放", "投产", "产线建设")),
    ("C2", ("小批量", "小批交付", "试订单")),
)
RESEARCH_STAGE_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("R5", ("客户验证通过", "客户定点", "进入供应链")),
    ("R4", ("送样", "客户验证", "客户认证", "导入客户")),
    ("R2", ("样品", "样机", "试制")),
    ("R1", ("研发", "技术储备", "立项")),
)
GROWTH_KEYWORDS = ("收入增长", "订单增长", "产能扩张", "放量", "收入占比", "持续提升")
PROFIT_KEYWORDS = ("毛利率", "利润贡献", "成本下降", "产品结构改善")
MOAT_KEYWORDS = ("专利", "标准", "国产替代", "卡脖子", "客户认证", "工艺难度")
RISK_KEYWORDS = ("延期", "不及预期", "否认", "未形成收入", "下滑")
PATENT_EVENT_KEYWORDS = ("专利", "知识产权", "发明专利", "实用新型", "软件著作权")
TENDER_EVENT_KEYWORDS = ("中标", "拟中标", "合同", "框架协议", "采购", "订单")
TENDER_TITLE_KEYWORDS = ("中标", "拟中标", "中标候选", "合同", "框架协议", "采购", "订单")
TENDER_TITLE_NOISE_KEYWORDS = (
    "募集资金", "募投", "问询函", "质押", "法律意见书", "核查意见", "可行性报告",
    "现金管理", "闲置自有资金", "委托理财", "理财产品", "合同资产", "减值准备", "核销",
)
TENDER_AMOUNT_PATTERN = re.compile(
    r"(?P<amount>[0-9][0-9,]*(?:\.[0-9]+)?)\s*(?P<unit>亿元|万元|万|元|美元)"
)
TENDER_CONTEXT_AMOUNT_PATTERNS = (
    re.compile(r"(?:折合人民币约|折合人民币|折算人民币约|折算人民币)[^0-9]{0,20}" + TENDER_AMOUNT_PATTERN.pattern),
    re.compile(
        r"(?:中标金额|合同总金额|合同金额|采购金额|交易金额|成交金额|总费用|金额为|金额约为|中标价)"
        r"[^0-9]{0,40}"
        + TENDER_AMOUNT_PATTERN.pattern
    ),
)
CNINFO_RELEVANT_TITLE_KEYWORDS = (
    "年度报告", "半年度报告", "季度报告", "问询函", "回复", "募集资金", "募投",
    "投资", "项目", "合同", "中标", "订单", "采购", "专利", "研发", "技术",
    "量产", "投产", "扩产", "产能", "客户", "合作", "调研", "投资者关系",
)
CNINFO_NOISE_TITLE_KEYWORDS = (
    "质押", "解除质押", "减持", "增持", "股东大会的法律意见书", "法律意见书",
    "权益分派", "分红派息", "停牌", "复牌", "异常波动", "交易异常波动",
)
OFFICIAL_LINK_KEYWORDS = (
    "新闻", "资讯", "动态", "投资者", "投资者关系", "ir", "公告", "产品", "解决方案",
    "客户", "合作", "项目", "技术", "研发", "专利", "产能", "量产", "业务",
)
OFFICIAL_LINK_NOISE_KEYWORDS = (
    "招聘", "人力", "登录", "注册", "隐私", "法律声明", "联系我们", "地图",
    "english", "en-us", "邮箱", "电话",
)
CHAIN_INDEX_KEYWORDS: dict[str, tuple[str, ...]] = {
    "ai_compute": ("算力", "数据中心", "CPO", "光模块", "液冷服务器", "服务器"),
    "embodied_intelligence": ("人形机器人", "机器人", "机器人执行器"),
    "semiconductor_equipment_materials": ("半导体设备", "半导体材料", "半导体"),
    "low_altitude_economy": ("低空经济", "无人机", "通用航空"),
    "industrial_mother_machine": ("工业母机", "机床"),
    "hydrogen_energy": ("氢能源", "氢能"),
    "nuclear_fusion": ("可控核聚变", "核聚变", "核能核电"),
    "quantum_technology": ("量子科技", "量子通信", "量子"),
    "sixth_generation_6g": ("6G", "卫星互联网", "通信设备"),
    "future_display": ("OLED", "MicroLED", "显示面板", "MiniLED"),
    "future_energy": ("储能", "固态电池", "钠离子电池", "新能源"),
    "future_materials": ("新材料", "碳纤维", "PEEK材料", "先进封装"),
    "future_space": ("商业航天", "卫星互联网", "航天航空"),
    "brain_computer_interface": ("脑机接口",),
    "bio_manufacturing": ("合成生物", "生物制造"),
    "future_health": ("创新药", "医疗器械", "医药医疗"),
    "industrial_software": ("工业软件", "信创", "软件开发"),
    "intelligent_manufacturing": ("智能制造", "工业互联", "机器人"),
}
GOVERNMENT_PROJECT_KEYWORDS = (
    "政府补助", "专项资金", "示范项目", "示范名单", "试点示范", "入选名单",
    "公示", "工信部", "发改委", "科技部", "补贴", "财政补助", "产业化项目",
    "技术改造", "设备更新", "重大项目", "重点项目", "政策支持",
)
GOVERNMENT_PROJECT_NOISE_KEYWORDS = (
    "募集资金", "募投", "核查意见", "问询函", "法律意见书", "股权激励",
    "激励对象名单", "质押", "解除质押", "重大资产重组", "独立财务顾问",
    "薪酬与考核", "永久补充流动资金", "会计师事务所", "质量控制复核",
    "资产评估报告", "项目合伙人", "中标",
)


def default_collection_sources() -> list[CollectionSource]:
    return [
        CollectionSource("cninfo_announcement", "巨潮/交易所公告全文", "announcement", "strong", 0.95, "available", "daily", "html", True, False, True, base_url="https://www.cninfo.com.cn", rate_limit_per_minute=20),
        CollectionSource("exchange_interact_qa", "互动易/上证e互动", "interact_qa", "mid", 0.85, "available", "daily", "api", True, True, True, base_url=None, rate_limit_per_minute=30),
        CollectionSource("official_ir_site", "公司官网/投资者关系", "official_site", "mid", 0.65, "available", "weekly", "html", True, True, True, rate_limit_per_minute=10),
        CollectionSource("public_tender_award", "中国招投标/政府采购", "tender_award", "strong", 0.95, "not_configured", "daily", "html", False, False, True, rate_limit_per_minute=10),
        CollectionSource("patent_public_platform", "国家知识产权/专利平台", "patent", "strong", 0.95, "not_configured", "weekly", "api", False, False, True, rate_limit_per_minute=10),
        CollectionSource("financial_news_authoritative", "权威财经新闻", "financial_news", "mid", 0.75, "available", "daily", "rss", True, True, False, rate_limit_per_minute=20),
        CollectionSource("broker_expectation", "券商研报/盈利预测", "broker_report", "mid", 0.75, "license_required", "daily", "api", False, True, False),
        CollectionSource("broker_expectation_local", "本地研报/盈利预测表", "broker_report", "mid", 0.75, "available", "daily", "existing_table", True, True, False),
        CollectionSource("industry_price_supply", "产业价格/供需数据", "industry_price", "mid", 0.70, "license_required", "daily", "api", False, True, False),
        CollectionSource("industry_index_proxy_local", "本地产业链指数景气代理", "industry_index_proxy", "mid", 0.70, "available", "daily", "existing_table", True, True, False),
        CollectionSource("government_project_notice", "政府项目/政策公示", "government_project", "strong", 0.95, "available", "weekly", "html", True, False, True, rate_limit_per_minute=10),
        CollectionSource("recruiting_signal", "招聘弱信号", "recruiting", "weak", 0.45, "not_configured", "weekly", "html", False, True, False),
        CollectionSource("official_social_signal", "公众号/自媒体弱信号", "social_media", "weak", 0.45, "not_configured", "daily", "manual_import", False, True, False),
        CollectionSource("market_community_signal", "社区/论坛弱信号", "market_community", "weak", 0.45, "not_configured", "daily", "manual_import", False, True, False, is_market_sentiment=True),
    ]


def normalize_text(text: str) -> str:
    return " ".join(str(text or "").replace("\u3000", " ").split())


def build_document_hash(source_id: str, url: str, title: str, content: str) -> str:
    payload = "\n".join([source_id or "", url or "", normalize_text(title), normalize_text(content)])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _contains_any(text: str, words: tuple[str, ...]) -> bool:
    return any(word in text for word in words)


def _stage_from_keywords(text: str, candidates: tuple[tuple[str, tuple[str, ...]], ...]) -> str | None:
    for stage, words in candidates:
        if _contains_any(text, words):
            return stage
    return None


def confidence_cap_for_level(source_level: SourceLevel) -> float:
    return {"strong": 0.95, "mid": 0.75, "weak": 0.45}[source_level]


def sanitize_pending_metadata(metadata: dict[str, Any] | None) -> dict[str, Any] | None:
    if metadata is None:
        return None
    sanitized = dict(metadata)
    sanitized.pop("review_normalization", None)
    return sanitized


def extract_fact_from_document(document: RawDocument, company_code: str | None = None) -> ExtractedFact:
    text = normalize_text(document.content_text)
    source_level = document.source_level
    confidence_cap = confidence_cap_for_level(source_level)

    research_stage = _stage_from_keywords(text, RESEARCH_STAGE_KEYWORDS)
    commercial_stage = _stage_from_keywords(text, COMMERCIAL_STAGE_KEYWORDS)
    validation_status = "pending"
    confidence = min({"strong": 0.8, "mid": 0.6, "weak": 0.35}[source_level], confidence_cap)

    if source_level == "weak":
        research_stage = None
        commercial_stage = None
        fact_type = "weak_signal"
    elif commercial_stage:
        fact_type = "commercial_progress"
    elif research_stage:
        fact_type = "research_progress"
    elif _contains_any(text, MOAT_KEYWORDS):
        fact_type = "moat"
    else:
        fact_type = "business_presence"

    return ExtractedFact(
        company_code=company_code or document.company_code or "",
        fact_type=fact_type,
        original_quote=text[:240],
        source_level=source_level,
        confidence=confidence,
        confidence_cap=confidence_cap,
        validation_status=validation_status,
        research_stage_signal=research_stage,
        commercial_stage_signal=commercial_stage,
        growth_signal=_contains_any(text, GROWTH_KEYWORDS),
        profit_signal=_contains_any(text, PROFIT_KEYWORDS),
        moat_signal=_contains_any(text, MOAT_KEYWORDS),
        risk_signal=_contains_any(text, RISK_KEYWORDS),
        metadata=sanitize_pending_metadata(document.metadata),
    )


def build_mapping_keywords(mapping: dict) -> dict:
    code = str(mapping.get("code") or "")
    company_name = str(mapping.get("company_name") or mapping.get("name") or "")
    tag_name = str(mapping.get("tag_name") or "")
    chain_id = str(mapping.get("chain_id") or "")
    node_id = str(mapping.get("node_id") or "")
    path = mapping.get("l1_l8_path") or []
    if isinstance(path, str):
        try:
            path = json.loads(path)
        except json.JSONDecodeError:
            path = [path]

    path_terms: list[str] = []
    for item in path:
        if isinstance(item, dict):
            name = str(item.get("name") or "").strip()
        else:
            name = str(item).strip()
        if name and name != company_name:
            path_terms.append(name)

    if not company_name:
        for term in path_terms:
            if " - " in term:
                company_name = term.split(" - ", 1)[0].strip()
                break

    terms = []
    for term in [company_name, tag_name, chain_id, node_id, *path_terms]:
        if term and term not in terms:
            terms.append(term)

    queries = []
    for term in terms[1:8]:
        if company_name and term:
            queries.append(f"{company_name} {term}")
        if code and term:
            queries.append(f"{code} {term}")

    return {
        "mapping_id": mapping.get("mapping_id"),
        "code": code,
        "company_name": company_name,
        "terms": terms,
        "queries": list(dict.fromkeys(queries)),
    }


def seed_sources(pg_url: str) -> dict:
    import psycopg2
    import psycopg2.extras

    sources = [source.to_record() for source in default_collection_sources()]
    sql = """
        INSERT INTO evidence_source_catalog (
            source_id, source_name, source_type, source_level,
            source_reliability_score, confidence_cap, is_official,
            is_third_party_estimate, is_market_sentiment,
            requires_cross_validation, license_status, update_frequency,
            crawl_method, enabled, base_url, rate_limit_per_minute, metadata, updated_at
        )
        VALUES (
            %(source_id)s, %(source_name)s, %(source_type)s, %(source_level)s,
            %(source_reliability_score)s, %(confidence_cap)s, %(is_official)s,
            %(is_third_party_estimate)s, %(is_market_sentiment)s,
            %(requires_cross_validation)s, %(license_status)s, %(update_frequency)s,
            %(crawl_method)s, %(enabled)s, %(base_url)s, %(rate_limit_per_minute)s,
            %(metadata)s::jsonb, CURRENT_TIMESTAMP
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
            base_url = EXCLUDED.base_url,
            rate_limit_per_minute = EXCLUDED.rate_limit_per_minute,
            metadata = EXCLUDED.metadata,
            updated_at = CURRENT_TIMESTAMP
    """
    for source in sources:
        source["metadata"] = json.dumps(source["metadata"], ensure_ascii=False)

    with psycopg2.connect(pg_url) as conn:
        with conn.cursor() as cur:
            psycopg2.extras.execute_batch(cur, sql, sources)
        conn.commit()

    return {"upserted": len(sources)}


def dry_run_keywords(pg_url: str, limit: int = 100) -> list[dict]:
    import psycopg2
    import psycopg2.extras

    sql = """
        SELECT b.mapping_id, b.code, s.name AS company_name, b.tag_name,
               b.chain_id, b.node_id, b.l1_l8_path
        FROM business_tag_mapping b
        LEFT JOIN stocks s ON s.code = split_part(b.code, '.', 1)
        ORDER BY b.updated_at DESC NULLS LAST, b.mapping_id
        LIMIT %s
    """
    with psycopg2.connect(pg_url) as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (limit,))
            rows = cur.fetchall()
    return [build_mapping_keywords(dict(row)) for row in rows]


def quality_report(pg_url: str) -> dict:
    import psycopg2
    import psycopg2.extras

    job_status_sql = """
        SELECT status, count(*) AS count
        FROM evidence_collection_jobs
        GROUP BY status
        ORDER BY status
    """
    source_health_sql = """
        WITH latest_job AS (
            SELECT DISTINCT ON (source_id)
                   source_id, job_id, status, started_at, finished_at,
                   fetched_count, inserted_count, duplicate_count,
                   failed_count, error_message
            FROM evidence_collection_jobs
            WHERE source_id IS NOT NULL
            ORDER BY source_id, started_at DESC NULLS LAST, created_at DESC
        ),
        job_rollup AS (
            SELECT source_id,
                   count(*) AS job_count,
                   count(*) FILTER (WHERE status = 'success') AS success_count,
                   count(*) FILTER (WHERE status IN ('failed', 'partial_success')) AS issue_count,
                   sum(fetched_count) AS fetched_total,
                   sum(inserted_count) AS inserted_total,
                   sum(duplicate_count) AS duplicate_total,
                   sum(failed_count) AS failed_total
            FROM evidence_collection_jobs
            WHERE source_id IS NOT NULL
            GROUP BY source_id
        )
        SELECT s.source_id, s.source_name, s.source_level, s.license_status,
               s.enabled, s.update_frequency,
               lj.status AS last_status,
               lj.started_at AS last_started_at,
               lj.finished_at AS last_finished_at,
               lj.fetched_count AS last_fetched_count,
               lj.inserted_count AS last_inserted_count,
               lj.duplicate_count AS last_duplicate_count,
               lj.failed_count AS last_failed_count,
               lj.error_message AS last_error_message,
               coalesce(r.job_count, 0) AS job_count,
               coalesce(r.success_count, 0) AS success_count,
               coalesce(r.issue_count, 0) AS issue_count,
               coalesce(r.fetched_total, 0) AS fetched_total,
               coalesce(r.inserted_total, 0) AS inserted_total,
               coalesce(r.duplicate_total, 0) AS duplicate_total,
               coalesce(r.failed_total, 0) AS failed_total
        FROM evidence_source_catalog s
        LEFT JOIN latest_job lj ON lj.source_id = s.source_id
        LEFT JOIN job_rollup r ON r.source_id = s.source_id
        ORDER BY s.source_level, s.source_id
    """
    failed_jobs_sql = """
        SELECT job_id, source_id, status, started_at, finished_at,
               fetched_count, inserted_count, duplicate_count, failed_count,
               error_message
        FROM evidence_collection_jobs
        WHERE status IN ('failed', 'partial_success')
        ORDER BY started_at DESC NULLS LAST, created_at DESC
        LIMIT 20
    """
    with psycopg2.connect(pg_url) as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(job_status_sql)
            job_status = [dict(row) for row in cur.fetchall()]
            cur.execute("SELECT source_level, license_status, count(*) AS count FROM evidence_source_catalog GROUP BY source_level, license_status ORDER BY source_level, license_status")
            source_status = [dict(row) for row in cur.fetchall()]
            cur.execute(source_health_sql)
            source_health = [dict(row) for row in cur.fetchall()]
            cur.execute(failed_jobs_sql)
            recent_issue_jobs = [dict(row) for row in cur.fetchall()]
    for row in source_health:
        fetched_total = int(row.get("fetched_total") or 0)
        duplicate_total = int(row.get("duplicate_total") or 0)
        inserted_total = int(row.get("inserted_total") or 0)
        row["duplicate_rate"] = round(duplicate_total / fetched_total, 4) if fetched_total else None
        row["insert_rate"] = round(inserted_total / fetched_total, 4) if fetched_total else None
    return {
        "job_status": job_status,
        "source_status": source_status,
        "source_health": source_health,
        "recent_issue_jobs": recent_issue_jobs,
    }


def _job_id(source_id: str, scope_type: str) -> str:
    payload = f"{source_id}:{scope_type}:{datetime.now(UTC).isoformat()}"
    return "JOB-" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:20]


def _fact_id(doc_id: str, mapping_id: str | None) -> str:
    payload = f"{doc_id}:{mapping_id or ''}"
    return "FACT-" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def _event_id_for_fact(fact_id: str) -> str:
    return "EV-" + hashlib.sha256(str(fact_id).encode("utf-8")).hexdigest()[:24]


def _source_by_id(source_id: str) -> CollectionSource:
    sources = {source.source_id: source for source in default_collection_sources()}
    if source_id not in sources:
        raise ValueError(f"unsupported source_id: {source_id}")
    return sources[source_id]


def ensure_weak_signal_source(source_id: str) -> CollectionSource:
    source = _source_by_id(source_id)
    if source.source_level != "weak":
        raise ValueError(f"source_id '{source_id}' is not a weak-signal source")
    return source


def _fact_nature_for_level(source_level: SourceLevel) -> str:
    if source_level == "strong":
        return "confirmed_fact"
    if source_level == "weak":
        return "market_signal"
    return "media_report"


def extract_cninfo_announcement_id(url: str) -> str | None:
    match = re.search(r"(?:announcementId|announceId)=([0-9]+)", str(url or ""))
    return match.group(1) if match else None


def cninfo_pdf_url(adjunct_url: str) -> str:
    text = str(adjunct_url or "").strip().lstrip("/")
    return f"http://static.cninfo.com.cn/{text}"


def is_relevant_cninfo_title(title: str) -> bool:
    text = str(title or "")
    if not text:
        return False
    if _contains_any(text, CNINFO_NOISE_TITLE_KEYWORDS):
        return False
    return _contains_any(text, CNINFO_RELEVANT_TITLE_KEYWORDS)


def is_tender_cninfo_title(title: str) -> bool:
    text = str(title or "")
    if not text:
        return False
    if _contains_any(text, TENDER_TITLE_NOISE_KEYWORDS):
        return False
    if _contains_any(text, CNINFO_NOISE_TITLE_KEYWORDS):
        return False
    return _contains_any(text, TENDER_TITLE_KEYWORDS)


def normalize_website_url(website: str) -> str:
    text = str(website or "").strip()
    if not text:
        return ""
    if not text.startswith(("http://", "https://")):
        text = "http://" + text
    return text.rstrip("/")


def html_to_text(html: str) -> str:
    text = re.sub(r"(?is)<script.*?</script>|<style.*?</style>", " ", str(html or ""))
    text = re.sub(r"(?is)<br\s*/?>|</p>|</div>|</li>|</tr>", "\n", text)
    text = re.sub(r"(?is)<[^>]+>", " ", text)
    return normalize_text(unescape(text))


def extract_relevant_official_links(base_url: str, html: str, max_links: int = 3) -> list[str]:
    parsed_base = urlparse(base_url)
    found: list[str] = []
    for match in re.finditer(r"(?is)<a\s+[^>]*href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", str(html or "")):
        href = unescape(match.group(1)).strip()
        label = html_to_text(match.group(2)).lower()
        full_url = urljoin(base_url + "/", href)
        parsed = urlparse(full_url)
        if parsed.scheme not in {"http", "https"}:
            continue
        if parsed_base.netloc and parsed.netloc and parsed.netloc != parsed_base.netloc:
            continue
        probe = f"{label} {full_url}".lower()
        if _contains_any(probe, OFFICIAL_LINK_NOISE_KEYWORDS):
            continue
        if _contains_any(probe, OFFICIAL_LINK_KEYWORDS) and full_url not in found:
            found.append(full_url)
        if len(found) >= max_links:
            break
    return found


def response_text(response) -> str:
    encoding = getattr(response, "apparent_encoding", None) or getattr(response, "encoding", None)
    if encoding:
        response.encoding = encoding
    return response.text or ""


def parse_tender_award_fact(title: str, text: str, company_name: str = "") -> dict | None:
    normalized_title = normalize_text(title)
    if not _contains_any(normalized_title, TENDER_TITLE_KEYWORDS):
        return None
    if _contains_any(normalized_title, TENDER_TITLE_NOISE_KEYWORDS):
        return None

    content = normalize_text(f"{normalized_title} {text}")
    if not _contains_any(content, TENDER_EVENT_KEYWORDS):
        return None

    if "拟中标" in content or "中标候选" in content:
        event_type = "tender_candidate"
    elif "中标" in content:
        event_type = "award"
    elif "框架协议" in content:
        event_type = "framework_agreement"
    elif "合同" in content:
        event_type = "contract"
    elif "采购" in content:
        event_type = "procurement"
    else:
        event_type = "tender_signal"

    amount_value, currency = parse_tender_amount(content)

    project_name = normalized_title[:240] or content[:120]
    return {
        "event_type": event_type,
        "project_name": project_name,
        "award_amount": amount_value,
        "currency": currency,
        "supplier": company_name or None,
        "commercial_signal": "C4" if event_type in {"award", "contract", "framework_agreement"} else "C3",
    }


def parse_tender_amount(content: str) -> tuple[float | None, str | None]:
    text = normalize_text(content)
    for pattern in TENDER_CONTEXT_AMOUNT_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        raw_amount = float(match.group("amount").replace(",", ""))
        unit = match.group("unit")
        if unit == "亿元":
            return raw_amount * 100000000, "CNY"
        if unit in {"万元", "万"}:
            return raw_amount * 10000, "CNY"
        if unit == "元":
            return raw_amount, "CNY"
        if unit == "美元":
            return raw_amount, "USD"
    return None, None


def parse_patent_event_fact(title: str, text: str, company_name: str = "") -> dict | None:
    normalized_title = normalize_text(title)
    content = normalize_text(f"{normalized_title} {text}")
    if not _contains_any(content, PATENT_EVENT_KEYWORDS):
        return None

    if "授权" in content or "取得" in content or "获得" in content:
        patent_status = "granted_or_obtained"
    elif "申请" in content:
        patent_status = "application"
    elif "软件著作权" in content:
        patent_status = "software_copyright"
    else:
        patent_status = "ip_signal"

    quote = extract_keyword_quote(content, PATENT_EVENT_KEYWORDS, max_length=260)
    return {
        "patent_title": normalized_title[:240] or quote[:120] or "知识产权证据",
        "patent_abstract": quote or content[:260],
        "applicant": company_name or None,
        "patent_status": patent_status,
        "moat_signal": True,
    }


def extract_keyword_quote(content: str, keywords: tuple[str, ...], max_length: int = 260) -> str:
    text = normalize_text(content)
    positions = [text.find(keyword) for keyword in keywords if text.find(keyword) >= 0]
    if not positions:
        return text[:max_length]
    start = max(0, min(positions) - 80)
    return text[start:start + max_length]


def _extract_pdf_text(pdf_bytes: bytes) -> str:
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as pdf_file:
        pdf_file.write(pdf_bytes)
        pdf_path = Path(pdf_file.name)
    txt_path = Path(str(pdf_path) + ".txt")
    try:
        proc = subprocess.run(
            ["pdftotext", str(pdf_path), str(txt_path)],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if proc.returncode != 0 or not txt_path.exists():
            return ""
        return normalize_text(txt_path.read_text(encoding="utf-8", errors="ignore"))
    finally:
        pdf_path.unlink(missing_ok=True)
        txt_path.unlink(missing_ok=True)


def build_legacy_event_record_from_fact(row: dict) -> dict:
    source_level = row.get("source_level") or "mid"
    fact_type = row.get("fact_type") or "business_presence"
    if fact_type == "commercial_progress":
        evidence_type = "commercial_stage"
    elif fact_type == "research_progress":
        evidence_type = "research_progress"
    elif fact_type == "moat":
        evidence_type = "patent_standard"
    elif fact_type == "weak_signal":
        evidence_type = "weak_signal"
    else:
        evidence_type = "business_presence"

    return {
        "event_id": _event_id_for_fact(row["fact_id"]),
        "mapping_id": row["mapping_id"],
        "code": row["company_code"],
        "node_id": row.get("node_id"),
        "event_date": row.get("publish_time"),
        "source_type": row.get("source_type") or row.get("source_level"),
        "source_id": row.get("source_id"),
        "title": row.get("title") or "采集证据",
        "excerpt": row.get("original_quote") or "",
        "original_url": row.get("url"),
        "evidence_type": evidence_type,
        "impact_dimensions": {
            "growth": bool(row.get("growth_signal")),
            "profit": bool(row.get("profit_signal")),
            "moat": bool(row.get("moat_signal")),
            "risk": bool(row.get("risk_signal")),
            "research_stage": row.get("research_stage_signal"),
            "commercial_stage": row.get("commercial_stage_signal"),
        },
        "confidence": row.get("confidence") or 0.0,
        "review_status": "pending_review",
        "review_note": "synced from data collection center",
    }


def _insert_raw_document_and_fact(
    cur,
    document: RawDocument,
    source: CollectionSource,
    job_id: str,
    *,
    mapping_id: str | None = None,
    fact_nature: str | None = None,
) -> dict:
    import json as _json

    raw_metadata = dict(document.metadata or {})
    raw_metadata["backfill_job_id"] = job_id
    cur.execute(
        """
        INSERT INTO raw_evidence_documents (
            doc_id, source_id, source_type, source_level, company_code,
            company_name, title, publish_time, url, content_text,
            content_hash, doc_type, doc_status, license_status, metadata
        )
        VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
            'active', %s, %s::jsonb
        )
        ON CONFLICT (content_hash) DO NOTHING
        """,
        (
            document.doc_id,
            source.source_id,
            source.source_type,
            source.source_level,
            document.company_code,
            document.company_name,
            document.title,
            document.publish_time,
            document.url,
            document.content_text,
            document.content_hash,
            document.doc_type,
            source.license_status,
            _json.dumps(raw_metadata, ensure_ascii=False),
        ),
    )
    inserted_doc = cur.rowcount > 0

    mapping = None
    if mapping_id:
        cur.execute(
            """
            SELECT mapping_id, chain_id, node_id, tag_name
            FROM business_tag_mapping
            WHERE mapping_id = %s
              AND (split_part(code, '.', 1) = %s OR code = %s)
            LIMIT 1
            """,
            (mapping_id, str(document.company_code or "").split(".")[0], document.company_code),
        )
        mapping = cur.fetchone()

    def mapping_value(key: str, index: int):
        if not mapping:
            return None
        if isinstance(mapping, dict):
            return mapping.get(key)
        return mapping[index]

    resolved_mapping_id = mapping_value("mapping_id", 0)
    chain_id = mapping_value("chain_id", 1)
    node_id = mapping_value("node_id", 2)
    tag_name = mapping_value("tag_name", 3)

    fact = extract_fact_from_document(document)
    fact_metadata = dict(fact.metadata or {})
    fact_metadata["backfill_job_id"] = job_id
    if node_id:
        fact_metadata["node_id"] = node_id
    cur.execute(
        """
        INSERT INTO evidence_extracted_facts (
            fact_id, doc_id, mapping_id, company_code, chain_id, l5_tag,
            fact_type, fact_nature, original_quote, source_level,
            confidence, confidence_cap, research_stage_signal,
            commercial_stage_signal, growth_signal, profit_signal,
            moat_signal, risk_signal, validation_status, metadata
        )
        VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb
        )
        ON CONFLICT (fact_id) DO NOTHING
        """,
        (
            _fact_id(document.doc_id, resolved_mapping_id),
            document.doc_id,
            resolved_mapping_id,
            document.company_code or "",
            chain_id,
            tag_name,
            fact.fact_type,
            fact_nature or _fact_nature_for_level(source.source_level),
            fact.original_quote,
            source.source_level,
            fact.confidence,
            fact.confidence_cap,
            fact.research_stage_signal,
            fact.commercial_stage_signal,
            fact.growth_signal,
            fact.profit_signal,
            fact.moat_signal,
            fact.risk_signal,
            fact.validation_status,
            _json.dumps(fact_metadata, ensure_ascii=False),
        ),
    )
    mapping_required = resolved_mapping_id is None
    return {
        "inserted_doc": inserted_doc,
        "inserted_fact": cur.rowcount > 0,
        "duplicate": not inserted_doc,
        "mapping_id": resolved_mapping_id,
        "mapping_required": mapping_required,
        "status": "mapping_required" if mapping_required else "stored",
    }


def run_existing_source_backfill(pg_url: str, source_id: str, limit: int = 50) -> dict:
    """Backfill existing DB tables into the collection center.

    This is intentionally conservative. It does not crawl external sites; it
    converts already-landed announcements/interact_qa rows into the new raw
    document and fact contracts so downstream evidence logic can be tested on
    real local data.
    """
    import psycopg2
    import psycopg2.extras

    source = _source_by_id(source_id)
    if source_id == "exchange_interact_qa":
        source_sql = """
            SELECT q.code, s.name AS company_name, q.pub_date AS publish_time,
                   ('互动问答 ' || q.pub_date::text) AS title,
                   (coalesce(q.question, '') || E'\n' || coalesce(q.answer, '')) AS content_text,
                   NULL::text AS url,
                   'interact_qa' AS doc_type
            FROM interact_qa q
            LEFT JOIN stocks s ON s.code = q.code
            WHERE coalesce(q.question, '') || coalesce(q.answer, '') <> ''
            ORDER BY q.pub_date DESC NULLS LAST, q.id DESC
            LIMIT %s
        """
    elif source_id == "cninfo_announcement":
        source_sql = """
            SELECT a.code, s.name AS company_name, a.ann_date AS publish_time,
                   a.title,
                   coalesce(a.content, a.title, '') AS content_text,
                   NULL::text AS url,
                   'announcement' AS doc_type
            FROM announcements a
            LEFT JOIN stocks s ON s.code = a.code
            WHERE coalesce(a.content, a.title, '') <> ''
            ORDER BY a.ann_date DESC NULLS LAST
            LIMIT %s
        """
    elif source_id == "broker_expectation_local":
        source_sql = """
            WITH mapped_codes AS (
                SELECT DISTINCT split_part(code, '.', 1) AS code
                FROM business_tag_mapping
            ),
            reports AS (
                SELECT split_part(r.code, '.', 1) AS code,
                       s.name AS company_name,
                       r.pub_date AS publish_time,
                       coalesce(nullif(r.title, ''), '券商研报') AS title,
                       (
                         '股票代码：' || split_part(r.code, '.', 1) ||
                         E'\n公司名称：' || coalesce(s.name, '') ||
                         E'\n研报标题：' || coalesce(r.title, '') ||
                         E'\n机构：' || coalesce(r.broker, '') ||
                         E'\n评级：' || coalesce(r.rating, '') ||
                         E'\n目标价：' || coalesce(r.target_price::text, '')
                       ) AS content_text,
                       NULL::text AS url,
                       'research_report' AS doc_type,
                       r.pub_date AS sort_time
                FROM research_reports r
                JOIN mapped_codes m ON m.code = split_part(r.code, '.', 1)
                LEFT JOIN stocks s ON s.code = split_part(r.code, '.', 1)
                WHERE coalesce(r.title, '') <> ''
            ),
            forecasts AS (
                SELECT split_part(f.code, '.', 1) AS code,
                       s.name AS company_name,
                       coalesce(f.ann_date, f.end_date) AS publish_time,
                       ('盈利预测 ' || coalesce(f.forecast_type, '') || ' ' || coalesce(f.end_date::text, '')) AS title,
                       (
                         '股票代码：' || split_part(f.code, '.', 1) ||
                         E'\n公司名称：' || coalesce(s.name, '') ||
                         E'\n盈利预测类型：' || coalesce(f.forecast_type, '') ||
                         E'\n预测净利润：' || coalesce(f.forecast_net_profit::text, '') ||
                         E'\n净利润区间：' || coalesce(f.net_profit_min::text, '') || ' - ' || coalesce(f.net_profit_max::text, '') ||
                         E'\n变动原因：' || coalesce(f.change_reason, '')
                       ) AS content_text,
                       NULL::text AS url,
                       'profit_forecast' AS doc_type,
                       coalesce(f.ann_date, f.end_date) AS sort_time
                FROM forecast_data f
                JOIN mapped_codes m ON m.code = split_part(f.code, '.', 1)
                LEFT JOIN stocks s ON s.code = split_part(f.code, '.', 1)
                WHERE f.forecast_net_profit IS NOT NULL
                   OR f.net_profit_min IS NOT NULL
                   OR f.net_profit_max IS NOT NULL
                   OR coalesce(f.forecast_type, '') <> ''
                   OR coalesce(f.change_reason, '') <> ''
            )
            SELECT *
            FROM (
                SELECT * FROM reports
                UNION ALL
                SELECT * FROM forecasts
            ) x
            ORDER BY sort_time DESC NULLS LAST, code
            LIMIT %s
        """
    elif source_id == "financial_news_authoritative":
        source_sql = """
            WITH mapped_companies AS (
                SELECT DISTINCT split_part(b.code, '.', 1) AS code, s.name AS company_name
                FROM business_tag_mapping b
                LEFT JOIN stocks s ON s.code = split_part(b.code, '.', 1)
                WHERE coalesce(s.name, '') <> ''
            ),
            stock_news_rows AS (
                SELECT split_part(n.code, '.', 1) AS code,
                       m.company_name,
                       n.pub_time AS publish_time,
                       coalesce(nullif(n.title, ''), '财经新闻') AS title,
                       (
                         '股票代码：' || split_part(n.code, '.', 1) ||
                         E'\n公司名称：' || coalesce(m.company_name, '') ||
                         E'\n新闻来源：' || coalesce(n.source, '') ||
                         E'\n新闻标题：' || coalesce(n.title, '') ||
                         E'\n新闻正文：' || coalesce(n.content, '')
                       ) AS content_text,
                       NULL::text AS url,
                       'financial_news' AS doc_type,
                       n.pub_time AS sort_time
                FROM stock_news_tushare n
                JOIN mapped_companies m ON m.code = split_part(n.code, '.', 1)
                WHERE coalesce(n.title, '') <> ''
            ),
            major_news_rows AS (
                SELECT m.code,
                       m.company_name,
                       NULLIF(r.pub_time, '')::timestamp AS publish_time,
                       coalesce(nullif(r.title, ''), '财经新闻') AS title,
                       (
                         '股票代码：' || m.code ||
                         E'\n公司名称：' || coalesce(m.company_name, '') ||
                         E'\n新闻来源：' || coalesce(r.src, '') ||
                         E'\n新闻标题：' || coalesce(r.title, '')
                       ) AS content_text,
                       r.url AS url,
                       'major_financial_news' AS doc_type,
                       NULLIF(r.pub_time, '')::timestamp AS sort_time
                FROM ts_raw_major_news r
                JOIN mapped_companies m ON coalesce(r.title, '') LIKE ('%%' || m.company_name || '%%')
                WHERE coalesce(r.title, '') <> ''
                  AND length(m.company_name) >= 4
            )
            SELECT *
            FROM (
                SELECT * FROM stock_news_rows
                UNION ALL
                SELECT * FROM major_news_rows
            ) x
            ORDER BY sort_time DESC NULLS LAST, code
            LIMIT %s
        """
    elif source_id == "government_project_notice":
        gov_like = " OR ".join([f"probe LIKE '%%{keyword}%%'" for keyword in GOVERNMENT_PROJECT_KEYWORDS])
        gov_noise = " AND ".join([f"probe NOT LIKE '%%{keyword}%%'" for keyword in GOVERNMENT_PROJECT_NOISE_KEYWORDS])
        chain_like = " OR ".join(
            [f"probe LIKE '%%{keyword}%%'" for keywords in CHAIN_INDEX_KEYWORDS.values() for keyword in keywords]
        )
        source_sql = f"""
            WITH mapped_companies AS (
                SELECT DISTINCT split_part(b.code, '.', 1) AS code, s.name AS company_name
                FROM business_tag_mapping b
                LEFT JOIN stocks s ON s.code = split_part(b.code, '.', 1)
            ),
            announcement_candidates AS (
                SELECT DISTINCT ON (split_part(r.ts_code, '.', 1), r.ann_date::text, r.title)
                       split_part(r.ts_code, '.', 1) AS code,
                       m.company_name,
                       to_date(r.ann_date::text, 'YYYYMMDD') AS publish_time,
                       r.title,
                       (
                         '股票代码：' || split_part(r.ts_code, '.', 1) ||
                         E'\n公司名称：' || coalesce(m.company_name, '') ||
                         E'\n公告标题：' || coalesce(r.title, '') ||
                         E'\n公告链接：' || coalesce(r.url, '')
                       ) AS content_text,
                       r.url,
                       'government_project_announcement' AS doc_type,
                       to_date(r.ann_date::text, 'YYYYMMDD') AS sort_time,
                       coalesce(r.title, '') AS probe
                FROM ts_raw_anns_d r
                JOIN mapped_companies m ON m.code = split_part(r.ts_code, '.', 1)
                WHERE coalesce(r.title, '') <> ''
                ORDER BY split_part(r.ts_code, '.', 1), r.ann_date::text, r.title, r.url
            ),
            policy_law_candidates AS (
                SELECT NULL::text AS code,
                       NULL::text AS company_name,
                       p.pub_date AS publish_time,
                       p.title,
                       (
                         '政策发布机构：' || coalesce(p.puborg, '') ||
                         E'\n政策文号：' || coalesce(p.pcode, '') ||
                         E'\n政策类型：' || coalesce(p.ptype, '') ||
                         E'\n政策标题：' || coalesce(p.title, '') ||
                         E'\n政策正文：' || left(regexp_replace(coalesce(p.content_html, ''), '<[^>]+>', ' ', 'g'), 6000)
                       ) AS content_text,
                       p.url,
                       'government_policy_law' AS doc_type,
                       p.pub_date AS sort_time,
                       (coalesce(p.title, '') || ' ' || coalesce(p.ptype, '') || ' ' || coalesce(p.content_html, '')) AS probe
                FROM policy_law p
                WHERE coalesce(p.title, '') <> ''
            )
            SELECT code, company_name, publish_time, title, content_text, url, doc_type, sort_time
            FROM (
                SELECT * FROM announcement_candidates
                UNION ALL
                SELECT * FROM policy_law_candidates
            ) x
            WHERE ({gov_like})
              AND ({gov_noise})
              AND (doc_type = 'government_project_announcement' OR ({chain_like}))
            ORDER BY sort_time DESC NULLS LAST, title
            LIMIT %s
        """
    else:
        raise ValueError("run-source currently supports cninfo_announcement, exchange_interact_qa, broker_expectation_local, financial_news_authoritative and government_project_notice")

    job_id = _job_id(source_id, "existing_table_backfill")
    fetched = inserted_docs = inserted_facts = duplicates = failed = 0

    with psycopg2.connect(pg_url) as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                INSERT INTO evidence_collection_jobs (
                    job_id, source_id, job_type, scope_type, status, started_at, metadata
                )
                VALUES (%s, %s, 'manual', 'existing_table_backfill', 'running', CURRENT_TIMESTAMP, %s::jsonb)
                """,
                (job_id, source_id, json.dumps({"limit": limit}, ensure_ascii=False)),
            )
            cur.execute(source_sql, (limit,))
            rows = [dict(row) for row in cur.fetchall()]
            fetched = len(rows)

            for row in rows:
                try:
                    document = RawDocument(
                        source_id=source_id,
                        source_level=source.source_level,
                        title=row["title"] or source.source_name,
                        content_text=row["content_text"] or "",
                        url=row.get("url"),
                        company_code=row.get("code"),
                        company_name=row.get("company_name"),
                        publish_time=str(row.get("publish_time")) if row.get("publish_time") else None,
                        doc_type=row.get("doc_type"),
                    )
                    fact_nature = "analyst_estimate" if source_id == "broker_expectation_local" else _fact_nature_for_level(source.source_level)
                    result = _insert_raw_document_and_fact(
                        cur,
                        document,
                        source,
                        job_id,
                        fact_nature=fact_nature,
                    )
                    inserted_docs += 1 if result["inserted_doc"] else 0
                    inserted_facts += 1 if result["inserted_fact"] else 0
                    duplicates += 1 if result["duplicate"] else 0
                except Exception:
                    failed += 1

            status = "success" if failed == 0 else "partial_success"
            cur.execute(
                """
                UPDATE evidence_collection_jobs
                SET status = %s,
                    finished_at = CURRENT_TIMESTAMP,
                    fetched_count = %s,
                    inserted_count = %s,
                    duplicate_count = %s,
                    failed_count = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE job_id = %s
                """,
                (status, fetched, inserted_docs + inserted_facts, duplicates, failed, job_id),
            )
        conn.commit()

    return {
        "job_id": job_id,
        "source_id": source_id,
        "fetched": fetched,
        "inserted_docs": inserted_docs,
        "inserted_facts": inserted_facts,
        "duplicates": duplicates,
        "failed": failed,
    }


def fetch_cninfo_pdf_announcements(pg_url: str, limit: int = 20, title_mode: str = "relevant") -> dict:
    """Fetch CNInfo announcement PDFs for mapped candidate companies."""
    import requests
    import psycopg2
    import psycopg2.extras

    if title_mode not in {"relevant", "tender"}:
        raise ValueError("title_mode must be relevant or tender")

    source = _source_by_id("cninfo_announcement")
    job_id = _job_id("cninfo_announcement", "candidate_pool_pdf")
    selected = fetched = inserted_docs = inserted_facts = duplicates = failed = skipped = 0
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0",
        "Referer": "http://www.cninfo.com.cn/new/disclosure/detail",
    })

    title_filter_sql = ""
    if title_mode == "tender":
        title_filter_sql = """
          AND (
            r.title LIKE '%%中标%%' OR r.title LIKE '%%合同%%' OR r.title LIKE '%%框架协议%%'
            OR r.title LIKE '%%采购%%' OR r.title LIKE '%%订单%%'
          )
          AND r.title NOT LIKE '%%募集资金%%'
          AND r.title NOT LIKE '%%募投%%'
          AND r.title NOT LIKE '%%问询函%%'
          AND r.title NOT LIKE '%%质押%%'
          AND r.title NOT LIKE '%%法律意见%%'
          AND r.title NOT LIKE '%%核查意见%%'
          AND r.title NOT LIKE '%%可行性报告%%'
        """
    candidate_sql = f"""
        SELECT DISTINCT
            split_part(r.ts_code, '.', 1) AS code,
            s.name AS company_name,
            r.ann_date,
            r.title,
            r.url,
            r.ts_code
        FROM ts_raw_anns_d r
        JOIN business_tag_mapping b
          ON split_part(b.code, '.', 1) = split_part(r.ts_code, '.', 1)
        LEFT JOIN stocks s ON s.code = split_part(r.ts_code, '.', 1)
        WHERE coalesce(r.url, '') <> ''
          AND coalesce(r.title, '') <> ''
          {title_filter_sql}
        ORDER BY r.ann_date DESC NULLS LAST, r.ts_code, r.title
        LIMIT %s
    """

    with psycopg2.connect(pg_url) as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                INSERT INTO evidence_collection_jobs (
                    job_id, source_id, job_type, scope_type, status, started_at, metadata
                )
                VALUES (%s, %s, 'manual', 'candidate_pool_pdf', 'running', CURRENT_TIMESTAMP, %s::jsonb)
                """,
                (job_id, source.source_id, json.dumps({"limit": limit, "title_mode": title_mode}, ensure_ascii=False)),
            )
            cur.execute(candidate_sql, (max(limit * 10, limit),))
            rows = [dict(row) for row in cur.fetchall()]
            selected = len(rows)

            for row in rows:
                if fetched >= limit:
                    break
                try:
                    title = str(row.get("title") or "")
                    keep_title = is_tender_cninfo_title(title) if title_mode == "tender" else is_relevant_cninfo_title(title)
                    if not keep_title:
                        skipped += 1
                        continue
                    detail_url = str(row.get("url") or "")
                    announcement_id = extract_cninfo_announcement_id(detail_url)
                    if not announcement_id:
                        skipped += 1
                        continue
                    fetched += 1

                    ann_date_text = str(row.get("ann_date") or "")
                    announce_time = f"{ann_date_text[:4]}-{ann_date_text[4:6]}-{ann_date_text[6:8]}" if len(ann_date_text) >= 8 else ann_date_text
                    flag = str(row.get("ts_code") or "").upper().endswith(".SZ")
                    detail = session.post(
                        "http://www.cninfo.com.cn/new/announcement/bulletin_detail",
                        params={"announceId": announcement_id, "flag": str(flag).lower(), "announceTime": announce_time},
                        timeout=20,
                    )
                    if detail.status_code != 200:
                        failed += 1
                        continue
                    payload = detail.json()
                    announcement = payload.get("announcement") or {}
                    adjunct = announcement.get("adjunctUrl")
                    if not adjunct:
                        skipped += 1
                        continue
                    pdf_url = cninfo_pdf_url(adjunct)
                    pdf_response = session.get(pdf_url, timeout=30)
                    if pdf_response.status_code != 200 or not pdf_response.content.startswith(b"%PDF"):
                        failed += 1
                        continue
                    content_text = _extract_pdf_text(pdf_response.content)
                    if not content_text:
                        failed += 1
                        continue

                    document = RawDocument(
                        source_id=source.source_id,
                        source_level=source.source_level,
                        title=str(announcement.get("announcementTitle") or row.get("title") or "公告全文"),
                        content_text=content_text,
                        url=pdf_url,
                        company_code=str(row.get("code") or ""),
                        company_name=str(row.get("company_name") or announcement.get("secName") or ""),
                        publish_time=announce_time,
                        doc_type="announcement_pdf",
                    )
                    result = _insert_raw_document_and_fact(cur, document, source, job_id)
                    inserted_docs += 1 if result["inserted_doc"] else 0
                    inserted_facts += 1 if result["inserted_fact"] else 0
                    duplicates += 1 if result["duplicate"] else 0
                except Exception:
                    failed += 1

            status = "success" if failed == 0 else "partial_success"
            cur.execute(
                """
                UPDATE evidence_collection_jobs
                SET status = %s,
                    finished_at = CURRENT_TIMESTAMP,
                    fetched_count = %s,
                    inserted_count = %s,
                    duplicate_count = %s,
                    failed_count = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE job_id = %s
                """,
                (status, fetched, inserted_docs + inserted_facts, duplicates, failed, job_id),
            )
        conn.commit()

    return {
        "job_id": job_id,
        "source_id": source.source_id,
        "selected": selected,
        "title_mode": title_mode,
        "fetched": fetched,
        "inserted_docs": inserted_docs,
        "inserted_facts": inserted_facts,
        "duplicates": duplicates,
        "skipped": skipped,
        "failed": failed,
    }


def fetch_official_ir_pages(pg_url: str, limit: int = 10, pages_per_company: int = 2) -> dict:
    """Fetch official company website/IR pages for mapped candidate companies."""
    import requests
    import psycopg2
    import psycopg2.extras

    source = _source_by_id("official_ir_site")
    job_id = _job_id(source.source_id, "candidate_official_ir")
    selected = fetched = inserted_docs = inserted_facts = duplicates = failed = skipped = official_events = 0
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0"})

    company_sql = """
        SELECT DISTINCT
            split_part(b.code, '.', 1) AS code,
            s.name AS company_name,
            coalesce(nullif(p.website, ''), nullif(r.website, '')) AS website
        FROM business_tag_mapping b
        LEFT JOIN stocks s ON s.code = split_part(b.code, '.', 1)
        LEFT JOIN stock_profiles p ON p.code = split_part(b.code, '.', 1)
        LEFT JOIN ts_raw_stock_company r ON split_part(r.ts_code, '.', 1) = split_part(b.code, '.', 1)
        WHERE coalesce(nullif(p.website, ''), nullif(r.website, '')) IS NOT NULL
        ORDER BY split_part(b.code, '.', 1)
        LIMIT %s
    """

    with psycopg2.connect(pg_url) as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                INSERT INTO evidence_collection_jobs (
                    job_id, source_id, job_type, scope_type, status, started_at, metadata
                )
                VALUES (%s, %s, 'manual', 'candidate_official_ir', 'running', CURRENT_TIMESTAMP, %s::jsonb)
                """,
                (job_id, source.source_id, json.dumps({"limit": limit, "pages_per_company": pages_per_company}, ensure_ascii=False)),
            )
            cur.execute(company_sql, (limit,))
            companies = [dict(row) for row in cur.fetchall()]
            selected = len(companies)

            for company in companies:
                website = normalize_website_url(str(company.get("website") or ""))
                if not website:
                    skipped += 1
                    continue
                try:
                    homepage = session.get(website, timeout=15)
                    homepage_text = response_text(homepage)
                    if homepage.status_code >= 400 or not homepage_text:
                        failed += 1
                        continue
                    urls = [homepage.url]
                    urls.extend(extract_relevant_official_links(homepage.url.rstrip("/"), homepage_text, max_links=max(0, pages_per_company - 1)))

                    for page_url in list(dict.fromkeys(urls))[:pages_per_company]:
                        try:
                            page = homepage if page_url == homepage.url else session.get(page_url, timeout=15)
                            page_text = response_text(page)
                            if page.status_code >= 400 or not page_text:
                                failed += 1
                                continue
                            text = html_to_text(page_text)
                            if len(text) < 80:
                                skipped += 1
                                continue
                            title_match = re.search(r"(?is)<title[^>]*>(.*?)</title>", page_text)
                            page_title = html_to_text(title_match.group(1)) if title_match else f"{company.get('company_name') or company.get('code')} 官网页面"
                            document = RawDocument(
                                source_id=source.source_id,
                                source_level=source.source_level,
                                title=page_title[:240],
                                content_text=text,
                                url=page_url,
                                company_code=str(company.get("code") or ""),
                                company_name=str(company.get("company_name") or ""),
                                publish_time=None,
                                doc_type="official_site_page",
                            )
                            result = _insert_raw_document_and_fact(cur, document, source, job_id)
                            inserted_docs += 1 if result["inserted_doc"] else 0
                            inserted_facts += 1 if result["inserted_fact"] else 0
                            duplicates += 1 if result["duplicate"] else 0
                            fetched += 1

                            event_id = "OFF-" + document.content_hash[:24]
                            cur.execute(
                                """
                                INSERT INTO official_site_events (
                                    event_id, doc_id, company_code, company_name,
                                    source_level, event_type, title, url,
                                    evidence_summary, metadata
                                )
                                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                                ON CONFLICT (event_id) DO UPDATE SET
                                    title = EXCLUDED.title,
                                    evidence_summary = EXCLUDED.evidence_summary,
                                    updated_at = CURRENT_TIMESTAMP
                                """,
                                (
                                    event_id,
                                    document.doc_id,
                                    document.company_code,
                                    document.company_name,
                                    source.source_level,
                                    "official_site_page",
                                    document.title,
                                    page_url,
                                    text[:500],
                                    json.dumps({"backfill_job_id": job_id}, ensure_ascii=False),
                                ),
                            )
                            if cur.rowcount:
                                official_events += 1
                        except Exception:
                            failed += 1
                except Exception:
                    failed += 1

            status = "success" if failed == 0 else "partial_success"
            cur.execute(
                """
                UPDATE evidence_collection_jobs
                SET status = %s,
                    finished_at = CURRENT_TIMESTAMP,
                    fetched_count = %s,
                    inserted_count = %s,
                    duplicate_count = %s,
                    failed_count = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE job_id = %s
                """,
                (status, fetched, inserted_docs + inserted_facts + official_events, duplicates, failed, job_id),
            )
        conn.commit()

    return {
        "job_id": job_id,
        "source_id": source.source_id,
        "selected_companies": selected,
        "fetched_pages": fetched,
        "inserted_docs": inserted_docs,
        "inserted_facts": inserted_facts,
        "official_events": official_events,
        "duplicates": duplicates,
        "skipped": skipped,
        "failed": failed,
    }


def sync_facts_to_legacy_events(pg_url: str, limit: int = 500) -> dict:
    import psycopg2
    import psycopg2.extras

    select_sql = """
        SELECT
            f.fact_id, f.mapping_id, f.company_code, f.fact_type,
            f.original_quote, f.source_level, f.confidence, f.validation_status,
            f.research_stage_signal, f.commercial_stage_signal,
            f.growth_signal, f.profit_signal, f.moat_signal, f.risk_signal,
            d.source_id, d.source_type, d.title, d.publish_time::date AS publish_time, d.url,
            b.node_id
        FROM evidence_extracted_facts f
        LEFT JOIN raw_evidence_documents d ON d.doc_id = f.doc_id
        LEFT JOIN business_tag_mapping b ON b.mapping_id = f.mapping_id
        WHERE f.evidence_event_id IS NULL
          AND f.mapping_id IS NOT NULL
        ORDER BY f.created_at DESC
        LIMIT %s
    """
    insert_sql = """
        INSERT INTO business_tag_evidence_events (
            event_id, mapping_id, code, node_id, event_date, source_type,
            source_id, title, excerpt, original_url, evidence_type,
            impact_dimensions, confidence, review_status, review_note
        )
        VALUES (
            %(event_id)s, %(mapping_id)s, %(code)s, %(node_id)s, %(event_date)s,
            %(source_type)s, %(source_id)s, %(title)s, %(excerpt)s,
            %(original_url)s, %(evidence_type)s, %(impact_dimensions)s::jsonb,
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
    """

    synced = 0
    with psycopg2.connect(pg_url) as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(select_sql, (limit,))
            rows = [dict(row) for row in cur.fetchall()]
            for row in rows:
                event = build_legacy_event_record_from_fact(row)
                cur.execute(insert_sql, {**event, "impact_dimensions": json.dumps(event["impact_dimensions"], ensure_ascii=False)})
                cur.execute(
                    """
                    UPDATE evidence_extracted_facts
                    SET evidence_event_id = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE fact_id = %s
                    """,
                    (event["event_id"], row["fact_id"]),
                )
                synced += 1
        conn.commit()

    return {"selected": len(rows), "synced": synced}


def extract_tender_events_from_documents(pg_url: str, limit: int = 500) -> dict:
    import psycopg2
    import psycopg2.extras

    select_sql = """
        SELECT
            d.doc_id, d.company_code, d.company_name, d.title, d.content_text,
            d.publish_time::date AS publish_time, f.mapping_id
        FROM raw_evidence_documents d
        LEFT JOIN evidence_extracted_facts f ON f.doc_id = d.doc_id
        WHERE d.doc_type IN ('announcement_pdf', 'official_site_page')
          AND (
            d.title LIKE '%%中标%%' OR d.title LIKE '%%合同%%' OR d.title LIKE '%%采购%%'
            OR d.content_text LIKE '%%中标%%' OR d.content_text LIKE '%%合同%%'
            OR d.content_text LIKE '%%框架协议%%' OR d.content_text LIKE '%%采购%%'
          )
        ORDER BY d.created_at DESC
        LIMIT %s
    """
    insert_sql = """
        INSERT INTO tender_award_events (
            event_id, doc_id, company_code, company_name, project_name,
            purchaser, supplier, award_amount, currency, publish_date,
            event_type, related_mapping_id, commercial_signal, metadata
        )
        VALUES (
            %(event_id)s, %(doc_id)s, %(company_code)s, %(company_name)s,
            %(project_name)s, %(purchaser)s, %(supplier)s, %(award_amount)s,
            %(currency)s, %(publish_date)s, %(event_type)s, %(related_mapping_id)s,
            %(commercial_signal)s, %(metadata)s::jsonb
        )
        ON CONFLICT (event_id) DO UPDATE SET
            project_name = EXCLUDED.project_name,
            award_amount = EXCLUDED.award_amount,
            currency = EXCLUDED.currency,
            event_type = EXCLUDED.event_type,
            commercial_signal = EXCLUDED.commercial_signal,
            updated_at = CURRENT_TIMESTAMP
    """

    selected = inserted_or_updated = skipped = 0
    with psycopg2.connect(pg_url) as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(select_sql, (limit,))
            rows = [dict(row) for row in cur.fetchall()]
            selected = len(rows)
            for row in rows:
                fact = parse_tender_award_fact(row.get("title") or "", row.get("content_text") or "", row.get("company_name") or "")
                if not fact:
                    skipped += 1
                    continue
                event_id = "TEN-" + hashlib.sha256(str(row["doc_id"]).encode("utf-8")).hexdigest()[:24]
                cur.execute(
                    insert_sql,
                    {
                        "event_id": event_id,
                        "doc_id": row["doc_id"],
                        "company_code": row.get("company_code"),
                        "company_name": row.get("company_name"),
                        "project_name": fact["project_name"],
                        "purchaser": None,
                        "supplier": fact["supplier"],
                        "award_amount": fact["award_amount"],
                        "currency": fact["currency"],
                        "publish_date": row.get("publish_time"),
                        "event_type": fact["event_type"],
                        "related_mapping_id": row.get("mapping_id"),
                        "commercial_signal": fact["commercial_signal"],
                        "metadata": json.dumps({"source": "raw_evidence_documents"}, ensure_ascii=False),
                    },
                )
                inserted_or_updated += 1
        conn.commit()
    return {"selected": selected, "written": inserted_or_updated, "skipped": skipped}


def extract_patent_events_from_documents(pg_url: str, limit: int = 500) -> dict:
    import psycopg2
    import psycopg2.extras

    select_sql = """
        SELECT
            d.doc_id, d.company_code, d.company_name, d.title, d.content_text,
            d.publish_time::date AS publish_time, f.mapping_id
        FROM raw_evidence_documents d
        LEFT JOIN evidence_extracted_facts f ON f.doc_id = d.doc_id
        WHERE d.source_level IN ('strong', 'mid')
          AND d.doc_type IN ('announcement_pdf', 'official_site_page', 'interact_qa')
          AND (
            (
              d.doc_type = 'announcement_pdf'
              AND (
                d.title LIKE '%%专利%%' OR d.title LIKE '%%知识产权%%' OR d.title LIKE '%%软件著作权%%'
              )
            )
            OR (
              d.doc_type IN ('official_site_page', 'interact_qa')
              AND (
                d.content_text LIKE '%%取得%%专利%%' OR d.content_text LIKE '%%获得%%专利%%'
                OR d.content_text LIKE '%%专利%%授权%%' OR d.content_text LIKE '%%申请%%专利%%'
                OR d.content_text LIKE '%%软件著作权%%'
              )
            )
          )
        ORDER BY d.created_at DESC
        LIMIT %s
    """
    insert_sql = """
        INSERT INTO patent_events (
            event_id, doc_id, company_code, company_name, publication_number,
            application_number, patent_title, patent_abstract, applicant,
            ipc_class, application_date, publication_date, grant_date,
            patent_status, related_mapping_id, moat_signal, metadata
        )
        VALUES (
            %(event_id)s, %(doc_id)s, %(company_code)s, %(company_name)s,
            NULL, NULL, %(patent_title)s, %(patent_abstract)s, %(applicant)s,
            NULL, NULL, NULL, NULL, %(patent_status)s, %(related_mapping_id)s,
            %(moat_signal)s, %(metadata)s::jsonb
        )
        ON CONFLICT (event_id) DO UPDATE SET
            patent_title = EXCLUDED.patent_title,
            patent_abstract = EXCLUDED.patent_abstract,
            applicant = EXCLUDED.applicant,
            patent_status = EXCLUDED.patent_status,
            related_mapping_id = EXCLUDED.related_mapping_id,
            moat_signal = EXCLUDED.moat_signal,
            metadata = EXCLUDED.metadata,
            updated_at = CURRENT_TIMESTAMP
    """

    selected = inserted_or_updated = skipped = 0
    with psycopg2.connect(pg_url) as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(select_sql, (limit,))
            rows = [dict(row) for row in cur.fetchall()]
            selected = len(rows)
            for row in rows:
                fact = parse_patent_event_fact(row.get("title") or "", row.get("content_text") or "", row.get("company_name") or "")
                if not fact:
                    skipped += 1
                    continue
                event_id = "PAT-" + hashlib.sha256(str(row["doc_id"]).encode("utf-8")).hexdigest()[:24]
                cur.execute(
                    insert_sql,
                    {
                        "event_id": event_id,
                        "doc_id": row["doc_id"],
                        "company_code": row.get("company_code"),
                        "company_name": row.get("company_name"),
                        "patent_title": fact["patent_title"],
                        "patent_abstract": fact["patent_abstract"],
                        "applicant": fact["applicant"],
                        "patent_status": fact["patent_status"],
                        "related_mapping_id": row.get("mapping_id"),
                        "moat_signal": fact["moat_signal"],
                        "metadata": json.dumps(
                            {
                                "source": "raw_evidence_documents",
                                "evidence_publish_time": str(row.get("publish_time") or ""),
                            },
                            ensure_ascii=False,
                        ),
                    },
                )
                inserted_or_updated += 1
        conn.commit()
    return {"selected": selected, "written": inserted_or_updated, "skipped": skipped}


def _float_or_none(value) -> float | None:
    text = str(value or "").replace(",", "").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _date_from_yyyymmdd(value: str) -> str | None:
    text = str(value or "").strip()
    if len(text) != 8 or not text.isdigit():
        return None
    return f"{text[:4]}-{text[4:6]}-{text[6:8]}"


def _industry_series_id(source_id: str, chain_id: str, metric_name: str, trade_date: str, region: str) -> str:
    payload = f"{source_id}:{chain_id}:{metric_name}:{trade_date}:{region}"
    return "IPS-" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def backfill_industry_index_proxy(pg_url: str, limit_per_chain: int = 5) -> dict:
    import psycopg2
    import psycopg2.extras

    source = _source_by_id("industry_index_proxy_local")
    job_id = _job_id(source.source_id, "industry_index_proxy")
    chain_ids = sorted(CHAIN_INDEX_KEYWORDS)
    metrics = (
        ("dc_index_pct_change", "pct_change", "%"),
        ("dc_index_up_num", "up_num", "count"),
        ("dc_index_down_num", "down_num", "count"),
        ("dc_index_turnover_rate", "turnover_rate", "%"),
        ("dc_index_total_mv", "total_mv", "CNY"),
    )
    select_sql = """
        SELECT ts_code, name, trade_date, pct_change, up_num, down_num,
               turnover_rate, total_mv, "leading", leading_code, leading_pct
        FROM ts_raw_dc_index
        WHERE name ILIKE ANY(%s)
        ORDER BY trade_date DESC NULLS LAST, name
        LIMIT %s
    """
    insert_sql = """
        INSERT INTO industry_price_series (
            series_id, source_id, chain_id, node_id, metric_name, metric_value,
            unit, trade_date, region, source_url, metadata
        )
        VALUES (
            %(series_id)s, %(source_id)s, %(chain_id)s, NULL, %(metric_name)s,
            %(metric_value)s, %(unit)s, %(trade_date)s, %(region)s, NULL,
            %(metadata)s::jsonb
        )
        ON CONFLICT (series_id)
        DO UPDATE SET
            metric_value = EXCLUDED.metric_value,
            unit = EXCLUDED.unit,
            metadata = EXCLUDED.metadata,
            updated_at = CURRENT_TIMESTAMP
    """

    selected_rows = written = skipped_chains = 0
    with psycopg2.connect(pg_url) as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                INSERT INTO evidence_collection_jobs (
                    job_id, source_id, job_type, scope_type, status, started_at, metadata
                )
                VALUES (%s, %s, 'manual', 'industry_index_proxy', 'running', CURRENT_TIMESTAMP, %s::jsonb)
                """,
                (job_id, source.source_id, json.dumps({"limit_per_chain": limit_per_chain}, ensure_ascii=False)),
            )
            for chain_id in chain_ids:
                patterns = [f"%{keyword}%" for keyword in CHAIN_INDEX_KEYWORDS[chain_id]]
                cur.execute(select_sql, (patterns, limit_per_chain))
                rows = [dict(row) for row in cur.fetchall()]
                selected_rows += len(rows)
                if not rows:
                    skipped_chains += 1
                    continue
                for row in rows:
                    trade_date = _date_from_yyyymmdd(row.get("trade_date"))
                    if not trade_date:
                        continue
                    region = f"{row.get('name') or ''}/{row.get('ts_code') or ''}".strip("/")
                    metadata = json.dumps(
                        {
                            "source_table": "ts_raw_dc_index",
                            "index_code": row.get("ts_code"),
                            "index_name": row.get("name"),
                            "leading": row.get("leading"),
                            "leading_code": row.get("leading_code"),
                            "leading_pct": row.get("leading_pct"),
                            "proxy_note": "industry index proxy, not commodity price",
                        },
                        ensure_ascii=False,
                    )
                    for metric_name, field, unit in metrics:
                        metric_value = _float_or_none(row.get(field))
                        if metric_value is None:
                            continue
                        cur.execute(
                            insert_sql,
                            {
                                "series_id": _industry_series_id(source.source_id, chain_id, metric_name, trade_date, region),
                                "source_id": source.source_id,
                                "chain_id": chain_id,
                                "metric_name": metric_name,
                                "metric_value": metric_value,
                                "unit": unit,
                                "trade_date": trade_date,
                                "region": region,
                                "metadata": metadata,
                            },
                        )
                        written += 1
            cur.execute(
                """
                UPDATE evidence_collection_jobs
                SET status = 'success',
                    finished_at = CURRENT_TIMESTAMP,
                    fetched_count = %s,
                    inserted_count = %s,
                    duplicate_count = 0,
                    failed_count = 0,
                    updated_at = CURRENT_TIMESTAMP
                WHERE job_id = %s
                """,
                (selected_rows, written, job_id),
            )
        conn.commit()

    return {
        "job_id": job_id,
        "source_id": source.source_id,
        "chains": len(chain_ids),
        "selected_index_rows": selected_rows,
        "written_metrics": written,
        "skipped_chains": skipped_chains,
    }


def load_weak_signal_documents(file_path: str, source_id: str) -> list[RawDocument]:
    source = ensure_weak_signal_source(source_id)
    path = Path(file_path)
    documents: list[RawDocument] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        text = line.strip()
        if not text:
            continue
        try:
            item = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSON at line {line_no}: {exc}") from exc
        record_source_id = str(item.get("source_id") or source.source_id)
        if record_source_id != source.source_id:
            raise ValueError(f"line {line_no} source_id '{record_source_id}' does not match import source '{source.source_id}'")
        title = normalize_text(item.get("title") or "")
        content_text = normalize_text(item.get("content_text") or item.get("content") or "")
        company_code = str(item.get("company_code") or item.get("code") or "").strip()
        if not title or not content_text or not company_code:
            raise ValueError(f"line {line_no} requires title, content_text and company_code")
        documents.append(
            RawDocument(
                source_id=source.source_id,
                source_level="weak",
                title=title,
                content_text=content_text,
                url=item.get("url"),
                company_code=company_code,
                company_name=item.get("company_name"),
                publish_time=item.get("publish_time"),
                doc_type=item.get("doc_type") or source.source_type,
                metadata=item.get("metadata") if isinstance(item.get("metadata"), dict) else None,
            )
        )
    return documents


def import_weak_signal_file(pg_url: str, file_path: str, source_id: str = "market_community_signal") -> dict:
    import psycopg2

    source = ensure_weak_signal_source(source_id)
    documents = load_weak_signal_documents(file_path, source.source_id)
    job_id = _job_id(source.source_id, "weak_signal_import")
    inserted_docs = inserted_facts = duplicates = 0
    with psycopg2.connect(pg_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO evidence_collection_jobs (
                    job_id, source_id, job_type, scope_type, status, started_at, metadata
                )
                VALUES (%s, %s, 'manual', 'weak_signal', 'running', CURRENT_TIMESTAMP, %s::jsonb)
                """,
                (job_id, source.source_id, json.dumps({"file_path": str(file_path)}, ensure_ascii=False)),
            )
            for document in documents:
                result = _insert_raw_document_and_fact(cur, document, source, job_id)
                inserted_docs += 1 if result["inserted_doc"] else 0
                inserted_facts += 1 if result["inserted_fact"] else 0
                duplicates += 1 if result["duplicate"] else 0
            cur.execute(
                """
                UPDATE evidence_collection_jobs
                SET status = 'success',
                    finished_at = CURRENT_TIMESTAMP,
                    fetched_count = %s,
                    inserted_count = %s,
                    duplicate_count = %s,
                    failed_count = 0,
                    updated_at = CURRENT_TIMESTAMP
                WHERE job_id = %s
                """,
                (len(documents), inserted_docs, duplicates, job_id),
            )
        conn.commit()

    sync_result = sync_facts_to_legacy_events(pg_url, limit=max(100, inserted_facts + 20)) if inserted_facts else {"synced": 0}
    return {
        "job_id": job_id,
        "source_id": source.source_id,
        "loaded": len(documents),
        "inserted_docs": inserted_docs,
        "inserted_facts": inserted_facts,
        "duplicates": duplicates,
        "review_events_synced": sync_result.get("synced", 0),
        "guardrail": "weak signals are pending_review only and do not upgrade stages",
    }


def scheduled_collection_plan() -> list[dict]:
    return [
        {
            "batch": "daily_core",
            "frequency": "trading_day_after_close",
            "recommended_time": "20:30",
            "tasks": [
                "seed_sources",
                "broker_expectation_local",
                "financial_news_authoritative",
                "government_project_notice",
                "industry_index_proxy_local",
                "refresh_expectation_scores",
                "quality_report",
            ],
        },
        {
            "batch": "weekly_official_and_ip",
            "frequency": "weekly",
            "recommended_time": "saturday_10:00",
            "tasks": [
                "fetch_official_ir",
                "fetch_cninfo_pdf_relevant",
                "extract_patent_events",
                "extract_tender_events",
                "sync_facts_to_events",
                "refresh_expectation_scores",
            ],
        },
        {
            "batch": "manual_weak_signal",
            "frequency": "manual",
            "recommended_time": "as_needed",
            "tasks": [
                "import_weak_signals",
                "quality_report",
            ],
        },
    ]


def run_scheduled_batch(pg_url: str, batch: str = "daily_core", limit: int = 100) -> dict:
    plan_by_batch = {item["batch"]: item for item in scheduled_collection_plan()}
    if batch not in plan_by_batch:
        raise ValueError(f"unsupported scheduled batch: {batch}")

    results: list[dict] = []
    failures = 0

    def record(task_name: str, fn):
        nonlocal failures
        try:
            result = fn()
            results.append({"task": task_name, "status": "success", "result": result})
        except Exception as exc:
            failures += 1
            results.append({"task": task_name, "status": "failed", "error": str(exc)})

    if batch == "daily_core":
        record("seed_sources", lambda: seed_sources(pg_url))
        record("broker_expectation_local", lambda: run_existing_source_backfill(pg_url, "broker_expectation_local", limit))
        record("financial_news_authoritative", lambda: run_existing_source_backfill(pg_url, "financial_news_authoritative", limit))
        record("government_project_notice", lambda: run_existing_source_backfill(pg_url, "government_project_notice", limit))
        record("industry_index_proxy_local", lambda: backfill_industry_index_proxy(pg_url, limit_per_chain=max(1, min(5, limit // 20 or 1))))
        record("refresh_expectation_scores", lambda: refresh_expectation_and_prosperity_scores(pg_url, limit=max(limit, 1000)))
        record("quality_report", lambda: quality_report(pg_url))
    elif batch == "weekly_official_and_ip":
        record("fetch_official_ir", lambda: fetch_official_ir_pages(pg_url, limit=max(1, min(limit, 20)), pages_per_company=2))
        record("fetch_cninfo_pdf_relevant", lambda: fetch_cninfo_pdf_announcements(pg_url, limit=max(1, min(limit, 50)), title_mode="relevant"))
        record("extract_patent_events", lambda: extract_patent_events_from_documents(pg_url, limit=max(limit, 100)))
        record("extract_tender_events", lambda: extract_tender_events_from_documents(pg_url, limit=max(limit, 100)))
        record("sync_facts_to_events", lambda: sync_facts_to_legacy_events(pg_url, limit=max(limit, 500)))
        record("refresh_expectation_scores", lambda: refresh_expectation_and_prosperity_scores(pg_url, limit=max(limit, 1000)))
    else:
        results.append({
            "task": "import_weak_signals",
            "status": "skipped",
            "reason": "manual batch requires --file through import-weak-signals",
        })
        record("quality_report", lambda: quality_report(pg_url))

    return {
        "batch": batch,
        "status": "success" if failures == 0 else "partial_success",
        "task_count": len(results),
        "failed_count": failures,
        "results": results,
    }


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


def clamp_score(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return round(min(high, max(low, float(value or 0.0))), 2)


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


def _score_row_id(prefix: str, mapping_id: str, trade_date: str) -> str:
    payload = f"{prefix}:{mapping_id}:{trade_date}"
    return f"{prefix}-" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def _json_list(value) -> list:
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


def _latest_trade_date(cur) -> str:
    cur.execute("SELECT max(trade_date) AS latest_trade_date FROM daily_kline")
    row = cur.fetchone()
    if row:
        value = row.get("latest_trade_date") if isinstance(row, dict) else row[0]
        if value:
            return str(value)[:10]
    return datetime.now().date().isoformat()


def _price_change_20d(cur, code: str, trade_date: str) -> float | None:
    base_code = str(code or "").split(".", 1)[0]
    if not base_code:
        return None
    cur.execute(
        """
        SELECT close
        FROM daily_kline
        WHERE code = %s AND trade_date <= %s AND close IS NOT NULL AND close > 0
        ORDER BY trade_date DESC
        LIMIT 21
        """,
        (base_code, trade_date),
    )
    rows = cur.fetchall()
    def close_value(row) -> float | None:
        value = row.get("close") if isinstance(row, dict) else row[0]
        return float(value) if value else None

    old_close = close_value(rows[-1]) if len(rows) >= 2 else None
    new_close = close_value(rows[0]) if rows else None
    if old_close is None or new_close is None:
        return None
    return round((new_close / old_close - 1.0) * 100.0, 2)


def _chain_prosperity(cur, chain_id: str | None) -> dict:
    if not chain_id:
        return {"latest_pct_change": None, "avg_pct_change": None, "sample_days": 0}
    cur.execute(
        """
        SELECT trade_date, avg(metric_value) AS avg_pct
        FROM industry_price_series
        WHERE chain_id = %s AND metric_name = 'dc_index_pct_change'
        GROUP BY trade_date
        ORDER BY trade_date DESC
        LIMIT 5
        """,
        (chain_id,),
    )
    rows = cur.fetchall()
    if not rows:
        return {"latest_pct_change": None, "avg_pct_change": None, "sample_days": 0}
    values = [
        float((row.get("avg_pct") if isinstance(row, dict) else row[1]) or 0.0)
        for row in rows
    ]
    return {
        "latest_pct_change": values[0],
        "avg_pct_change": round(sum(values) / len(values), 4),
        "sample_days": len(values),
    }


def refresh_expectation_and_prosperity_scores(
    pg_url: str,
    *,
    limit: int = 1000,
    chain_id: str | None = None,
    trade_date: str | None = None,
) -> dict:
    import psycopg2
    import psycopg2.extras

    mapping_sql = """
        SELECT mapping_id, code, chain_id, tag_name, revenue_ratio,
               gross_profit_ratio, confidence, status
        FROM business_tag_mapping
        WHERE (%s IS NULL OR chain_id = %s)
        ORDER BY updated_at DESC NULLS LAST, created_at DESC NULLS LAST, mapping_id
        LIMIT %s
    """
    stage_sql = """
        SELECT research_stage, commercialization_stage
        FROM business_tag_stage_tracking
        WHERE mapping_id = %s
        ORDER BY trade_date DESC NULLS LAST, created_at DESC NULLS LAST
        LIMIT 1
    """
    events_sql = """
        SELECT event_id, evidence_type, impact_dimensions, confidence,
               source_id, event_date
        FROM business_tag_evidence_events
        WHERE mapping_id = %s AND review_status = 'approved'
        ORDER BY event_date DESC NULLS LAST, created_at DESC NULLS LAST
        LIMIT 100
    """
    monitors_sql = """
        SELECT coalesce(claim_source_type, 'unknown') AS source_type, count(*) AS count
        FROM business_tag_expectation_monitor
        WHERE mapping_id = %s
          AND review_status IN ('candidate', 'pending_review', 'approved')
        GROUP BY coalesce(claim_source_type, 'unknown')
    """
    three_high_sql = """
        INSERT INTO business_tag_three_high_scores (
            score_id, mapping_id, trade_date, growth_score, profit_score,
            moat_score, stage_score, evidence_score, total_score,
            score_detail, evidence_ids
        )
        VALUES (
            %(score_id)s, %(mapping_id)s, %(trade_date)s, %(growth_score)s,
            %(profit_score)s, %(moat_score)s, %(stage_score)s,
            %(evidence_score)s, %(total_score)s, %(score_detail)s::jsonb,
            %(evidence_ids)s::jsonb
        )
        ON CONFLICT (mapping_id, trade_date) DO UPDATE SET
            growth_score = EXCLUDED.growth_score,
            profit_score = EXCLUDED.profit_score,
            moat_score = EXCLUDED.moat_score,
            stage_score = EXCLUDED.stage_score,
            evidence_score = EXCLUDED.evidence_score,
            total_score = EXCLUDED.total_score,
            score_detail = EXCLUDED.score_detail,
            evidence_ids = EXCLUDED.evidence_ids
    """
    gap_sql = """
        INSERT INTO business_tag_expectation_gap_scores (
            gap_id, mapping_id, trade_date, actual_progress_score,
            market_expectation_score, evidence_delta_score, risk_penalty_score,
            expectation_gap_score, gap_type, score_detail, evidence_ids
        )
        VALUES (
            %(gap_id)s, %(mapping_id)s, %(trade_date)s, %(actual_progress_score)s,
            %(market_expectation_score)s, %(evidence_delta_score)s,
            %(risk_penalty_score)s, %(expectation_gap_score)s, %(gap_type)s,
            %(score_detail)s::jsonb, %(evidence_ids)s::jsonb
        )
        ON CONFLICT (mapping_id, trade_date) DO UPDATE SET
            actual_progress_score = EXCLUDED.actual_progress_score,
            market_expectation_score = EXCLUDED.market_expectation_score,
            evidence_delta_score = EXCLUDED.evidence_delta_score,
            risk_penalty_score = EXCLUDED.risk_penalty_score,
            expectation_gap_score = EXCLUDED.expectation_gap_score,
            gap_type = EXCLUDED.gap_type,
            score_detail = EXCLUDED.score_detail,
            evidence_ids = EXCLUDED.evidence_ids
    """

    written_three_high = written_gap = 0
    preview: list[dict] = []
    with psycopg2.connect(pg_url) as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            score_date = trade_date or _latest_trade_date(cur)
            cur.execute(mapping_sql, (chain_id, chain_id, limit))
            mappings = [dict(row) for row in cur.fetchall()]
            for mapping in mappings:
                mapping_id = str(mapping["mapping_id"])
                cur.execute(stage_sql, (mapping_id,))
                stage = dict(cur.fetchone() or {})
                stage_score = calculate_stage_progress_score(
                    stage.get("research_stage"),
                    stage.get("commercialization_stage"),
                )

                cur.execute(events_sql, (mapping_id,))
                events = [dict(row) for row in cur.fetchall()]
                evidence_ids = [str(row["event_id"]) for row in events if row.get("event_id")][:50]
                avg_confidence = (
                    sum(float(row.get("confidence") or 0.0) for row in events) / len(events)
                    if events
                    else 0.0
                )
                growth_events = profit_events = moat_events = risk_events = order_events = 0
                for event in events:
                    dims = set(str(item) for item in _json_list(event.get("impact_dimensions")))
                    evidence_type = str(event.get("evidence_type") or "")
                    if "growth" in dims or evidence_type in {"order", "commercial_stage", "order_award"}:
                        growth_events += 1
                    if "profit" in dims or evidence_type == "revenue_margin":
                        profit_events += 1
                    if "moat" in dims or evidence_type in {"patent_standard", "patent", "moat"}:
                        moat_events += 1
                    if "risk" in dims or evidence_type == "risk":
                        risk_events += 1
                    if evidence_type in {"order", "commercial_stage", "order_award"}:
                        order_events += 1

                evidence_score = clamp_score(len(events) * 12.0 + avg_confidence * 60.0 + growth_events * 4.0 + moat_events * 4.0)

                cur.execute(monitors_sql, (mapping_id,))
                monitor_counts = {str(row["source_type"]): int(row["count"] or 0) for row in cur.fetchall()}
                analyst_claims = sum(
                    count for source_type, count in monitor_counts.items()
                    if source_type in {"analyst_estimate", "broker_report", "research_report", "profit_forecast"}
                )
                news_claims = sum(
                    count for source_type, count in monitor_counts.items()
                    if source_type in {"financial_news", "media_report", "news"}
                )
                total_claims = sum(monitor_counts.values())
                price_change_20d = _price_change_20d(cur, str(mapping.get("code") or ""), score_date)
                market_expectation_score = calculate_market_expectation_score(
                    analyst_claims=analyst_claims,
                    news_claims=news_claims,
                    total_claims=total_claims,
                    price_change_20d=price_change_20d,
                )

                prosperity = _chain_prosperity(cur, mapping.get("chain_id"))
                prosperity_score = calculate_prosperity_score(
                    prosperity["latest_pct_change"],
                    prosperity["avg_pct_change"],
                )

                revenue_ratio = _float_or_none(mapping.get("revenue_ratio"))
                gross_profit_ratio = _float_or_none(mapping.get("gross_profit_ratio"))
                growth_score = clamp_score(
                    (revenue_ratio or 0.0) * 100.0
                    + growth_events * 14.0
                    + order_events * 12.0
                    + max(0.0, prosperity_score - 50.0) * 0.55
                )
                profit_score = None
                if gross_profit_ratio is not None or profit_events:
                    profit_score = clamp_score((35.0 if gross_profit_ratio is None else 45.0 + gross_profit_ratio * 100.0) + profit_events * 10.0)
                moat_score = clamp_score(moat_events * 28.0 + avg_confidence * 35.0)
                score_cap = 100.0
                if revenue_ratio is None and profit_score is None:
                    score_cap = 70.0
                elif profit_score is None:
                    score_cap = 85.0
                total_score = clamp_score(
                    growth_score * 0.24
                    + (profit_score or 0.0) * 0.18
                    + moat_score * 0.22
                    + stage_score * 0.16
                    + evidence_score * 0.14
                    + prosperity_score * 0.06,
                    high=score_cap,
                )

                risk_penalty_score = clamp_score(risk_events * 20.0 + max(0.0, -float(price_change_20d or 0.0)) * 0.3)
                actual_progress_score = clamp_score(stage_score * 0.50 + evidence_score * 0.32 + prosperity_score * 0.18)
                raw_gap = (
                    actual_progress_score
                    - market_expectation_score
                    + evidence_score * 0.22
                    + (prosperity_score - 50.0) * 0.20
                    - risk_penalty_score * 0.40
                )
                expectation_gap_score = clamp_score(raw_gap)
                if raw_gap >= 15:
                    gap_type = "positive"
                elif raw_gap <= -15:
                    gap_type = "negative"
                else:
                    gap_type = "neutral"

                shared_detail = {
                    "version": "supply-chain-collection-v1-second-layer-refresh",
                    "trade_date_source": "daily_kline_latest" if trade_date is None else "explicit",
                    "approved_evidence_count": len(events),
                    "monitor_counts": monitor_counts,
                    "price_change_20d": price_change_20d,
                    "prosperity_score": prosperity_score,
                    "prosperity_proxy": prosperity,
                    "score_note": "二层数据用于市场预期和景气修正，不替代强证据",
                }
                cur.execute(
                    three_high_sql,
                    {
                        "score_id": _score_row_id("THREE-HIGH", mapping_id, score_date),
                        "mapping_id": mapping_id,
                        "trade_date": score_date,
                        "growth_score": growth_score,
                        "profit_score": profit_score,
                        "moat_score": moat_score,
                        "stage_score": stage_score,
                        "evidence_score": evidence_score,
                        "total_score": total_score,
                        "score_detail": json.dumps(
                            {
                                **shared_detail,
                                "revenue_supported": revenue_ratio is not None,
                                "profit_supported": profit_score is not None,
                                "score_cap": score_cap,
                                "growth_events": growth_events,
                                "profit_events": profit_events,
                                "moat_events": moat_events,
                            },
                            ensure_ascii=False,
                        ),
                        "evidence_ids": json.dumps(evidence_ids, ensure_ascii=False),
                    },
                )
                written_three_high += 1

                cur.execute(
                    gap_sql,
                    {
                        "gap_id": _score_row_id("GAP", mapping_id, score_date),
                        "mapping_id": mapping_id,
                        "trade_date": score_date,
                        "actual_progress_score": actual_progress_score,
                        "market_expectation_score": market_expectation_score,
                        "evidence_delta_score": evidence_score,
                        "risk_penalty_score": risk_penalty_score,
                        "expectation_gap_score": expectation_gap_score,
                        "gap_type": gap_type,
                        "score_detail": json.dumps(
                            {
                                **shared_detail,
                                "market_expectation_source": "second_layer_monitor_and_price_reaction",
                                "actual_progress_formula": "stage*0.50 + evidence*0.32 + prosperity*0.18",
                                "raw_gap": round(raw_gap, 2),
                                "formula": "actual_progress - market_expectation + evidence*0.22 + prosperity_delta*0.20 - risk*0.40",
                            },
                            ensure_ascii=False,
                        ),
                        "evidence_ids": json.dumps(evidence_ids, ensure_ascii=False),
                    },
                )
                written_gap += 1
                if len(preview) < 20:
                    preview.append(
                        {
                            "mapping_id": mapping_id,
                            "code": mapping.get("code"),
                            "tag_name": mapping.get("tag_name"),
                            "three_high_total": total_score,
                            "market_expectation_score": market_expectation_score,
                            "prosperity_score": prosperity_score,
                            "expectation_gap_score": expectation_gap_score,
                            "gap_type": gap_type,
                        }
                    )
        conn.commit()

    return {
        "trade_date": score_date,
        "chain_id": chain_id,
        "mappings_read": len(mappings),
        "written_three_high_scores": written_three_high,
        "written_expectation_gap_scores": written_gap,
        "preview": preview,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Supply-chain data collection center")
    sub = parser.add_subparsers(dest="command", required=True)

    seed = sub.add_parser("seed-sources")
    seed.add_argument("--pg-url", required=True)

    dry = sub.add_parser("dry-run-keywords")
    dry.add_argument("--pg-url", required=True)
    dry.add_argument("--pool", default="all-18-chains")
    dry.add_argument("--limit", type=int, default=50)

    report = sub.add_parser("quality-report")
    report.add_argument("--pg-url", required=True)

    run = sub.add_parser("run-source")
    run.add_argument("--pg-url", required=True)
    run.add_argument("--source", required=True)
    run.add_argument("--scope", default="existing_table_backfill")
    run.add_argument("--limit", type=int, default=50)

    cninfo_pdf = sub.add_parser("fetch-cninfo-pdf")
    cninfo_pdf.add_argument("--pg-url", required=True)
    cninfo_pdf.add_argument("--limit", type=int, default=20)
    cninfo_pdf.add_argument("--title-mode", choices=("relevant", "tender"), default="relevant")

    official = sub.add_parser("fetch-official-ir")
    official.add_argument("--pg-url", required=True)
    official.add_argument("--limit", type=int, default=10)
    official.add_argument("--pages-per-company", type=int, default=2)

    sync = sub.add_parser("sync-facts-to-events")
    sync.add_argument("--pg-url", required=True)
    sync.add_argument("--limit", type=int, default=500)

    tender = sub.add_parser("extract-tender-events")
    tender.add_argument("--pg-url", required=True)
    tender.add_argument("--limit", type=int, default=500)

    patent = sub.add_parser("extract-patent-events")
    patent.add_argument("--pg-url", required=True)
    patent.add_argument("--limit", type=int, default=500)

    industry_index = sub.add_parser("backfill-industry-index-proxy")
    industry_index.add_argument("--pg-url", required=True)
    industry_index.add_argument("--limit-per-chain", type=int, default=5)

    weak_import = sub.add_parser("import-weak-signals")
    weak_import.add_argument("--pg-url", required=True)
    weak_import.add_argument("--file", required=True)
    weak_import.add_argument("--source", default="market_community_signal")

    schedule_plan_parser = sub.add_parser("schedule-plan")

    scheduled_batch = sub.add_parser("run-scheduled-batch")
    scheduled_batch.add_argument("--pg-url", required=True)
    scheduled_batch.add_argument("--batch", default="daily_core")
    scheduled_batch.add_argument("--limit", type=int, default=100)

    scores = sub.add_parser("refresh-expectation-scores")
    scores.add_argument("--pg-url", required=True)
    scores.add_argument("--limit", type=int, default=1000)
    scores.add_argument("--chain-id", default=None)
    scores.add_argument("--trade-date", default=None)

    args = parser.parse_args()
    if args.command == "seed-sources":
        print(json.dumps(seed_sources(args.pg_url), ensure_ascii=False, indent=2))
    elif args.command == "dry-run-keywords":
        print(json.dumps(dry_run_keywords(args.pg_url, args.limit), ensure_ascii=False, indent=2))
    elif args.command == "quality-report":
        print(json.dumps(quality_report(args.pg_url), ensure_ascii=False, indent=2, default=str))
    elif args.command == "run-source":
        print(json.dumps(run_existing_source_backfill(args.pg_url, args.source, args.limit), ensure_ascii=False, indent=2, default=str))
    elif args.command == "fetch-cninfo-pdf":
        print(json.dumps(fetch_cninfo_pdf_announcements(args.pg_url, args.limit, args.title_mode), ensure_ascii=False, indent=2, default=str))
    elif args.command == "fetch-official-ir":
        print(json.dumps(fetch_official_ir_pages(args.pg_url, args.limit, args.pages_per_company), ensure_ascii=False, indent=2, default=str))
    elif args.command == "sync-facts-to-events":
        print(json.dumps(sync_facts_to_legacy_events(args.pg_url, args.limit), ensure_ascii=False, indent=2, default=str))
    elif args.command == "extract-tender-events":
        print(json.dumps(extract_tender_events_from_documents(args.pg_url, args.limit), ensure_ascii=False, indent=2, default=str))
    elif args.command == "extract-patent-events":
        print(json.dumps(extract_patent_events_from_documents(args.pg_url, args.limit), ensure_ascii=False, indent=2, default=str))
    elif args.command == "backfill-industry-index-proxy":
        print(json.dumps(backfill_industry_index_proxy(args.pg_url, args.limit_per_chain), ensure_ascii=False, indent=2, default=str))
    elif args.command == "import-weak-signals":
        print(json.dumps(import_weak_signal_file(args.pg_url, args.file, args.source), ensure_ascii=False, indent=2, default=str))
    elif args.command == "schedule-plan":
        print(json.dumps(scheduled_collection_plan(), ensure_ascii=False, indent=2, default=str))
    elif args.command == "run-scheduled-batch":
        print(json.dumps(run_scheduled_batch(args.pg_url, args.batch, args.limit), ensure_ascii=False, indent=2, default=str))
    elif args.command == "refresh-expectation-scores":
        print(json.dumps(
            refresh_expectation_and_prosperity_scores(
                args.pg_url,
                limit=args.limit,
                chain_id=args.chain_id,
                trade_date=args.trade_date,
            ),
            ensure_ascii=False,
            indent=2,
            default=str,
        ))


if __name__ == "__main__":
    main()
