"""Data foundation builders for the 大葱产业链解构模型.

Pure helpers only: no database writes and no network access.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Any


CONFIG_PATH = Path(__file__).resolve().parent.parent / "configs" / "supply_chains.json"


CHAIN_IDS = {
    "半导体": "semiconductor",
    "华为韬定律_先进封装": "tao_law_advanced_packaging",
    "新能源": "new_energy",
    "AI算力": "ai_compute",
    "机器人": "robotics",
    "创新药": "innovative_drug",
    "新能源车": "new_energy_vehicle",
    "消费升级": "consumer_upgrade",
    "国防军工": "defense",
    "高端制造": "advanced_manufacturing",
    "周期资源": "cyclical_resources",
    "EDA工业软件": "eda_industrial_software",
    "华为终端": "huawei_devices",
    "存储芯片": "memory_chips",
    "光通信": "optical_communication",
    "AI Token输出电力": "ai_token_output_power",
}

LAYER_IDS = {
    "材料": "materials",
    "设备": "equipment",
    "制造": "manufacturing",
    "封测": "packaging_test",
    "设计": "design",
    "光伏": "photovoltaic",
    "电池": "battery",
    "硬件": "hardware",
    "软件": "software",
    "应用": "application",
    "核心部件": "core_parts",
    "整机": "complete_machine",
    "集成": "integration",
    "CXO": "cxo",
    "原料药": "api",
    "创新药": "innovative_drug",
    "零部件": "parts",
    "整车": "vehicle",
    "品牌": "brand",
    "渠道": "channel",
    "主机厂": "prime_contractor",
    "分系统": "subsystem",
    "元器件": "components",
    "资源": "resources",
    "冶炼": "smelting",
    "加工": "processing",
}

GENERIC_KEYWORDS = {
    "品牌",
    "研发",
    "生产",
    "制造",
    "服务",
    "应用",
    "解决方案",
    "集成",
    "加工",
    "材料",
    "设备",
    "装备",
    "硬件",
    "软件",
    "整机",
    "渠道",
    "智能",
    "系统",
    "机械",
    "平台",
}


@dataclass(frozen=True)
class FoundationCatalog:
    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]
    chain_lookup: dict[str, dict[str, Any]]


@dataclass(frozen=True)
class CompanyText:
    code: str
    name: str
    industry: str = ""
    main_business: str = ""
    introduction: str = ""
    report_titles: tuple[str, ...] = ()


@dataclass(frozen=True)
class CompanyMapping:
    code: str
    node_id: str
    chain_id: str
    product_name: str | None
    confidence: float
    status: str
    evidence: list[str]
    evidence_gaps: list[str]
    mapping_source: str


def load_supply_chain_config(path: str | Path | None = None) -> dict:
    config_path = Path(path) if path else CONFIG_PATH
    return json.loads(config_path.read_text(encoding="utf-8"))


def _slug_chain(chain_name: str) -> str:
    return CHAIN_IDS.get(chain_name, re.sub(r"\W+", "_", chain_name.lower()).strip("_"))


def _slug_layer(layer_name: str) -> str:
    return LAYER_IDS.get(layer_name, re.sub(r"\W+", "_", layer_name.lower()).strip("_"))


def build_foundation_catalog(config: dict, chains: list[str] | None = None) -> FoundationCatalog:
    selected = set(chains or [])
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    chain_lookup: dict[str, dict[str, Any]] = {}

    for chain_name, chain_cfg in (config.get("chains") or {}).items():
        if selected and chain_name not in selected:
            continue
        chain_slug = _slug_chain(chain_name)
        root_id = f"chain_{chain_slug}"
        root = {
            "node_id": root_id,
            "theme_id": "future_industry_core",
            "chain_id": chain_slug,
            "parent_node_id": None,
            "level": "chain",
            "name": chain_name,
            "node_type": "industry",
            "keywords": list(chain_cfg.get("industries") or []),
            "policy_weight": 1.5,
        }
        nodes.append(root)
        chain_lookup[chain_name] = root

        previous_layer_id: str | None = None
        for layer in chain_cfg.get("layers") or []:
            layer_slug = _slug_layer(layer)
            node_id = f"{chain_slug}_{layer_slug}"
            keywords = list((chain_cfg.get("layer_keywords") or {}).get(layer) or [])
            nodes.append({
                "node_id": node_id,
                "theme_id": "future_industry_core",
                "chain_id": chain_slug,
                "parent_node_id": root_id,
                "level": "layer",
                "name": layer,
                "node_type": "layer",
                "keywords": keywords,
                "policy_weight": 1.5,
            })
            edges.append({
                "edge_id": f"edge_{root_id}_{node_id}",
                "from_node_id": root_id,
                "to_node_id": node_id,
                "relation": "contains",
            })
            if previous_layer_id:
                edges.append({
                    "edge_id": f"edge_{previous_layer_id}_{node_id}",
                    "from_node_id": previous_layer_id,
                    "to_node_id": node_id,
                    "relation": "upstream_to_downstream",
                })
            previous_layer_id = node_id

    return FoundationCatalog(nodes=nodes, edges=edges, chain_lookup=chain_lookup)


def _normalise_company(raw: CompanyText | dict[str, Any]) -> CompanyText:
    if isinstance(raw, CompanyText):
        return raw
    return CompanyText(
        code=str(raw.get("code") or ""),
        name=str(raw.get("name") or ""),
        industry=str(raw.get("industry") or ""),
        main_business=str(raw.get("main_business") or ""),
        introduction=str(raw.get("introduction") or ""),
        report_titles=tuple(str(t) for t in (raw.get("report_titles") or [])),
    )


def _evidence_gaps(status: str) -> list[str]:
    if status == "verified":
        return []
    return [
        "是否有明确客户或供应链认证",
        "是否有量产、扩产、订单或定点公告",
        "该产品收入占比是否足够高",
        "是否存在国产替代或卡脖子稀缺性证据",
    ]


def _status_for(confidence: float) -> str:
    if confidence >= 0.85:
        return "verified"
    if confidence >= 0.45:
        return "pending_review"
    return "weak_evidence"


def _specific_hits(hits: list[str]) -> list[str]:
    return [hit for hit in hits if hit not in GENERIC_KEYWORDS and len(hit) >= 2]


def _industry_matches(company_industry: str, root_keywords: list[str]) -> bool:
    return any(str(keyword) in company_industry for keyword in root_keywords if keyword)


def score_company_mappings(
    catalog: FoundationCatalog,
    companies: list[CompanyText | dict[str, Any]],
    min_confidence: float = 0.30,
) -> list[CompanyMapping]:
    root_keywords = {
        node["chain_id"]: list(node.get("keywords") or [])
        for node in catalog.nodes
        if node["level"] == "chain"
    }
    by_code_node: dict[tuple[str, str], CompanyMapping] = {}

    for raw in companies:
        company = _normalise_company(raw)
        text_main = company.main_business
        text_intro = company.introduction
        text_reports = " ".join(company.report_titles)
        industry_only_done: set[str] = set()
        for node in catalog.nodes:
            keywords = [str(k) for k in node.get("keywords") or [] if k]
            if not keywords:
                continue
            industry_hit = _industry_matches(company.industry, root_keywords.get(node["chain_id"], []))
            if node["level"] == "chain":
                if not industry_hit or node["chain_id"] in industry_only_done:
                    continue
                confidence = 0.30
                source = "industry"
                evidence = [company.industry]
                industry_only_done.add(node["chain_id"])
            else:
                main_hits = [k for k in keywords if k in text_main]
                intro_hits = [k for k in keywords if k in text_intro]
                report_hits = [k for k in keywords if k in text_reports]

                confidence = 0.0
                source = ""
                evidence: list[str] = []
                if main_hits:
                    specific = _specific_hits(main_hits)
                    if specific:
                        confidence = 0.85 if industry_hit else 0.65
                    else:
                        confidence = 0.50 if industry_hit else 0.25
                    source = "main_business"
                    evidence = main_hits[:5]
                elif intro_hits:
                    specific = _specific_hits(intro_hits)
                    if specific:
                        confidence = 0.80 if industry_hit else 0.65
                    else:
                        confidence = 0.45 if industry_hit else 0.25
                    source = "introduction"
                    evidence = intro_hits[:5]
                elif report_hits:
                    specific = _specific_hits(report_hits)
                    confidence = 0.50 if specific else 0.35
                    source = "research_report"
                    evidence = report_hits[:5]
                else:
                    continue

            if confidence < min_confidence:
                continue

            status = _status_for(confidence)
            mapping = CompanyMapping(
                code=company.code,
                node_id=node["node_id"],
                chain_id=node["chain_id"],
                product_name=evidence[0] if evidence else None,
                confidence=round(confidence, 2),
                status=status,
                evidence=evidence,
                evidence_gaps=_evidence_gaps(status),
                mapping_source=source,
            )
            key = (mapping.code, mapping.node_id)
            prev = by_code_node.get(key)
            if prev is None or mapping.confidence > prev.confidence:
                by_code_node[key] = mapping

    return sorted(by_code_node.values(), key=lambda m: (-m.confidence, m.code, m.node_id))


def build_foundation_report(catalog: FoundationCatalog, mappings: list[CompanyMapping]) -> dict[str, Any]:
    status_counts: dict[str, int] = {}
    chain_counts: dict[str, int] = {}
    source_counts: dict[str, int] = {}
    node_status_counts: dict[str, dict[str, int]] = {}
    mapped_nodes = {m.node_id for m in mappings}
    for mapping in mappings:
        status_counts[mapping.status] = status_counts.get(mapping.status, 0) + 1
        chain_counts[mapping.chain_id] = chain_counts.get(mapping.chain_id, 0) + 1
        source_counts[mapping.mapping_source] = source_counts.get(mapping.mapping_source, 0) + 1
        node_status = node_status_counts.setdefault(mapping.node_id, {})
        node_status[mapping.status] = node_status.get(mapping.status, 0) + 1
    audit_hotspots = [
        {
            "node_id": node_id,
            "weak_evidence": counts.get("weak_evidence", 0),
            "pending_review": counts.get("pending_review", 0),
            "verified": counts.get("verified", 0),
        }
        for node_id, counts in node_status_counts.items()
        if counts.get("weak_evidence", 0) + counts.get("pending_review", 0) >= 100
    ]
    audit_hotspots.sort(key=lambda row: (row["weak_evidence"] + row["pending_review"], row["weak_evidence"]), reverse=True)
    suspicious_samples = [
        {
            "code": m.code,
            "node_id": m.node_id,
            "chain_id": m.chain_id,
            "confidence": m.confidence,
            "status": m.status,
            "mapping_source": m.mapping_source,
            "evidence": m.evidence,
            "evidence_gaps": m.evidence_gaps,
        }
        for m in mappings
        if m.status in {"pending_review", "weak_evidence"}
    ][:50]
    return {
        "node_count": len(catalog.nodes),
        "edge_count": len(catalog.edges),
        "mapping_count": len(mappings),
        "status_counts": status_counts,
        "chain_counts": chain_counts,
        "source_counts": source_counts,
        "audit": {
            "hotspot_nodes": audit_hotspots[:30],
            "suspicious_samples": suspicious_samples,
            "review_queue_count": status_counts.get("pending_review", 0) + status_counts.get("weak_evidence", 0),
        },
        "empty_nodes": [
            n["node_id"]
            for n in catalog.nodes
            if n["level"] != "chain" and n["node_id"] not in mapped_nodes
        ],
        "top_mappings": [
            {
                "code": m.code,
                "node_id": m.node_id,
                "chain_id": m.chain_id,
                "confidence": m.confidence,
                "status": m.status,
                "mapping_source": m.mapping_source,
            }
            for m in mappings[:20]
        ],
    }


def mapping_to_pg_rows(mapping: CompanyMapping) -> dict[str, dict[str, Any]]:
    evidence_payload = {
        "chain_id": mapping.chain_id,
        "confidence": mapping.confidence,
        "status": mapping.status,
        "evidence": mapping.evidence,
        "evidence_gaps": mapping.evidence_gaps,
        "mapping_source": mapping.mapping_source,
        "source": "supply_chain_foundation",
    }
    return {
        "company_bom_mapping": {
            "mapping_id": f"auto_{mapping.code}_{mapping.node_id}",
            "code": mapping.code,
            "node_id": mapping.node_id,
            "product_name": mapping.product_name,
            "material_name": None,
            "evidence_ids": [],
            "confidence": mapping.confidence,
            "status": mapping.status,
        },
        "company_chain_mapping": {
            "code": mapping.code,
            "node_id": mapping.node_id,
            "main_pct": None,
            "policy_match_score": mapping.confidence,
            "chokepoint_score": 0,
            "evidence": evidence_payload,
            "three_factors": {},
            "trade_signal": "观察",
        },
    }
