"""Supply-chain domain services."""

from datetime import datetime
import hashlib
import json
from typing import Any, Optional
from types import SimpleNamespace

from fastapi import HTTPException

from app.domains.supply_chain import repository

BIGTECH_COMPANIES = {"Microsoft", "Alphabet", "Meta", "Amazon", "Oracle"}
AI_COMPUTE_LAYER_KEYWORDS = {
    "demand": ("云", "cloud", "aws", "oci", "AI", "大模型", "算力", "应用"),
    "foundation": ("HBM", "CoWoS", "封装", "服务器", "网络设备", "数据中心土地"),
    "infrastructure": ("IDC", "数据中心", "服务器", "液冷", "光模块", "CPO", "网络", "交换机", "电源", "GPU", "云容量"),
}

TOKEN_OUTPUT_POWER_DIMENSIONS = [
    "function_value",
    "technology_route",
    "physical_bom",
    "value_pool",
    "competition_moat",
    "supply_demand_cycle",
    "evidence_validation",
]

TOKEN_OUTPUT_POWER_LAYERS = {
    "L1": {"name": "需求层", "segments": ["企业Agent", "智能客服", "代码生成", "搜索", "内容生成", "多模态应用"], "evidence": ["API调用量", "DAU", "Token消耗量", "付费客户数"]},
    "L2": {"name": "任务层", "segments": ["实时推理", "批量推理", "长上下文", "视频生成", "端侧推理"], "evidence": ["QPS", "并发数", "上下文长度", "输入输出Token比"]},
    "L3": {"name": "核心产品层", "segments": ["大模型", "推理API", "模型服务平台", "Agent平台"], "evidence": ["模型调用量", "Token价格", "SLA", "客户留存"]},
    "L4": {"name": "底层支撑层", "segments": ["GPU/ASIC", "HBM", "先进封装", "推理软件", "光互联"], "evidence": ["Tokens/s", "Tokens/W", "显存", "芯片供货和适配"]},
    "L5": {"name": "集成层", "segments": ["AI服务器", "推理集群", "模型压缩", "量化", "调度", "推理引擎"], "evidence": ["集群上线", "利用率", "延迟", "KV Cache命中率"]},
    "L6": {"name": "配套层", "segments": ["液冷", "电源", "变压器", "PCB", "连接器", "光模块", "存储"], "evidence": ["机柜功率", "PUE", "冷却能力", "交付订单"]},
    "L7": {"name": "基础设施层", "segments": ["低谷电", "弃风弃光", "绿电交易", "储能", "IDC", "智算中心"], "evidence": ["可用MW", "电价", "供电小时", "并网容量", "机房利用率"]},
    "L8": {"name": "商业变现层", "segments": ["按Token计费", "API", "SaaS", "Agent服务", "算力租赁"], "evidence": ["Token收入", "单Token价格", "毛利率", "续费率", "现金流"]},
}

TOKEN_OUTPUT_POWER_POWER_MODEL = {
    "billable_tokens_formula": "available_mw * operating_hours * utilization * tokens_per_mw_hour * cluster_availability",
    "cost_per_million_tokens_formula": "(electricity + compute_depreciation + facility_and_cooling + network + operation + financing) / billable_tokens * 1000000",
    "tokens_per_mw_hour_requires_profile": True,
    "power_source_types": ["curtailed_renewable", "valley_power", "park_self_generation_or_ppa", "nominal_capacity"],
}


def _json_or_default(value, default):
    if value is None: return default
    if isinstance(value, (dict, list)): return value
    try: return json.loads(value)
    except (TypeError, ValueError, json.JSONDecodeError): return default


def _to_float(value, default=0.0):
    try: return float(value) if value is not None else default
    except (TypeError, ValueError): return default


def load_bom_payload() -> dict:
    """Load and enrich the policy BOM seed for API and screening consumers."""
    from kronos_factors.engine.supply_chain_bom import load_bom_config

    cfg = load_bom_config()
    themes = cfg.get("themes", [])
    nodes = cfg.get("nodes", [])
    edges = cfg.get("edges", [])
    theme_by_id = {theme.get("theme_id"): theme for theme in themes}
    children_by_parent: dict = {}
    for node in nodes:
        parent = node.get("parent_node_id")
        if parent:
            children_by_parent.setdefault(parent, []).append(node.get("node_id"))

    enriched_nodes = []
    for node in nodes:
        theme = theme_by_id.get(node.get("theme_id"), {})
        enriched = dict(node)
        enriched["policy_theme"] = theme.get("name", "")
        enriched["bom_path"] = [value for value in (theme.get("name"), node.get("name")) if value]
        enriched["child_node_ids"] = children_by_parent.get(node.get("node_id"), [])
        enriched["companies"] = []
        enriched_nodes.append(enriched)

    node_counts: dict = {}
    for node in enriched_nodes:
        node_counts[node.get("theme_id")] = node_counts.get(node.get("theme_id"), 0) + 1
    enriched_themes = []
    for theme in themes:
        enriched = dict(theme)
        enriched["node_count"] = node_counts.get(theme.get("theme_id"), 0)
        enriched["matrix"] = {
            "policy_weight": theme.get("policy_weight", 1.0),
            "high_growth": None, "high_profit": None, "high_moat": None,
        }
        enriched_themes.append(enriched)
    return {"version": cfg.get("version", "4.0"), "source": cfg.get("source", ""), "themes": enriched_themes, "nodes": enriched_nodes, "edges": edges}


def themes_payload() -> dict:
    payload = load_bom_payload()
    return {key: payload[key] for key in ("version", "source", "themes")}


def bom_payload() -> dict:
    payload = load_bom_payload()
    return {key: payload[key] for key in ("version", "source", "themes", "nodes", "edges")}


def stage_rank(stage: str | None) -> int:
    if not stage:
        return 0
    try:
        return int(str(stage)[1:])
    except (TypeError, ValueError, IndexError):
        return 0


def pool_for_business_tag(status: str, revenue_ratio: float | None, commercialization_stage: str, evidence_count: int) -> str:
    if status == "rejected": return "剔除池"
    if status == "verified" and revenue_ratio is not None and stage_rank(commercialization_stage) >= 3 and evidence_count > 0: return "核心池"
    if evidence_count > 0 and stage_rank(commercialization_stage) >= 1: return "进展池"
    return "观察池"


def layer_level_from_bom_level(level: str | None) -> str:
    key = str(level or "").lower()
    if key in {"theme", "policy"}: return "L1"
    if key in {"direction", "sector"}: return "L2"
    if key in {"chain", "industry"}: return "L3"
    if key in {"segment", "process"}: return "L4"
    if key in {"component", "material", "equipment"}: return "L5"
    if key in {"product", "technology", "application"}: return "L6"
    return "L5"


def build_layer_tree(nodes: list[dict]) -> list[dict]:
    node_by_id = {node["layer_node_id"]: dict(node, children=[]) for node in nodes}
    roots = []
    for node in node_by_id.values():
        parent_id = node.get("parent_node_id")
        if parent_id and parent_id in node_by_id: node_by_id[parent_id]["children"].append(node)
        else: roots.append(node)
    order = {f"L{i}": i for i in range(1, 9)}
    def sort_node(item):
        item["children"] = sorted((sort_node(child) for child in item.get("children", [])), key=lambda child: (order.get(child.get("layer_level"), 99), child.get("name") or ""))
        return item
    return sorted((sort_node(root) for root in roots), key=lambda node: (order.get(node.get("layer_level"), 99), node.get("name") or ""))


def fallback_layer_nodes() -> list[dict]:
    payload = load_bom_payload(); nodes = []; theme_names = {}
    for theme in payload.get("themes", []):
        theme_id = str(theme.get("theme_id") or "")
        if not theme_id: continue
        theme_names[theme_id] = str(theme.get("name") or theme_id)
        nodes.append({"layer_node_id": f"L1:{theme_id}", "parent_node_id": None, "layer_level": "L1", "layer_name": "政策主题", "name": theme_names[theme_id], "source_table": "policy_themes", "source_id": theme_id, "keywords": theme.get("keywords") or [], "metadata": {"policy_weight": theme.get("policy_weight")}})
    levels = {str(node.get("node_id") or ""): layer_level_from_bom_level(node.get("level") or node.get("node_type")) for node in payload.get("nodes", [])}
    for node in payload.get("nodes", []):
        node_id = str(node.get("node_id") or ""); theme_id = str(node.get("theme_id") or "")
        if not node_id: continue
        level = layer_level_from_bom_level(node.get("level") or node.get("node_type")); parent = node.get("parent_node_id")
        nodes.append({"layer_node_id": f"{level}:{node_id}", "parent_node_id": f"{levels.get(str(parent), 'L5')}:{parent}" if parent else f"L1:{theme_id}", "layer_level": level, "layer_name": {"L2":"产业方向","L3":"产业链","L4":"环节","L5":"BOM节点","L6":"产品/技术路线"}.get(level,"产业链节点"), "name": str(node.get("name") or node_id), "source_table":"supply_chain_bom_nodes", "source_id":node_id, "keywords":node.get("keywords") or [], "metadata":{"theme_id":theme_id,"theme_name":theme_names.get(theme_id),"chain_id":node.get("chain_id"),"node_type":node.get("node_type"),"level":node.get("level")}})
    return nodes


def data_readiness() -> dict[str, Any]:
    layer_coverage = {f"L{i}": {"status": "unknown", "row_count": 0} for i in range(1, 9)}
    payload: dict[str, Any] = {
        "version": "supply-chain-v2-readiness",
        "checked_at": datetime.now().isoformat(timespec="seconds"),
        "layer_coverage": layer_coverage,
        "business_segments": {"status": "unknown", "source_table": "fina_mainbz", "row_count": 0},
        "announcement_body": {"status": "unknown", "source_table": "announcements", "nonempty_rows": 0},
        "research_body": {"status": "unknown", "source_table": "research_reports_tushare", "row_count": 0},
        "evidence_events": {"status": "unknown", "source_table": "company_evidence", "row_count": 0},
        "target_tables": {},
        "implementation_gates": {
            "core_pool_requires_business_evidence": True,
            "missing_segment_margin_caps_profit_score": True,
            "market_concept_only_caps_pool": "观察池",
        },
        "notes": [],
    }
    try:
        with repository.connect() as pg:
            cur = pg.cursor()

            policy_theme_rows = repository.count(cur, "policy_themes")
            bom_node_rows = repository.count(cur, "supply_chain_bom_nodes")
            chain_node_rows = repository.count(cur, "chain_nodes")
            company_mapping_rows = repository.count(cur, "company_bom_mapping")
            evidence_rows = repository.count(cur, "company_evidence")
            segment_rows = repository.count(cur, "fina_mainbz")
            segment_code_rows = repository.distinct_count(cur, "fina_mainbz", "code")
            announcement_rows = repository.count(cur, "announcements")
            announcement_body_rows = repository.nonempty_text_count(cur, "announcements", "content")
            research_rows = repository.count(cur, "research_reports_tushare")
            target_table_names = [
                "supply_chain_hierarchy_nodes",
                "supply_chain_deconstruct_views",
                "company_business_segments",
                "business_tag_mapping",
                "business_tag_evidence_events",
                "business_tag_l8_evidence_status",
                "business_tag_stage_tracking",
                "business_tag_three_high_scores",
                "business_tag_expectation_gap_scores",
            ]

            payload["layer_coverage"] = {
                "L1": {
                    "name": "政策主题",
                    "status": repository.status_from_rows(policy_theme_rows, ready=3),
                    "row_count": policy_theme_rows,
                    "source": "policy_themes",
                },
                "L2": {
                    "name": "产业方向",
                    "status": repository.status_from_rows(bom_node_rows, ready=20),
                    "row_count": bom_node_rows,
                    "source": "supply_chain_bom_nodes",
                },
                "L3": {
                    "name": "产业链",
                    "status": repository.status_from_rows(chain_node_rows, ready=20),
                    "row_count": chain_node_rows,
                    "source": "chain_nodes",
                },
                "L4": {
                    "name": "环节",
                    "status": repository.status_from_rows(company_mapping_rows, ready=1000),
                    "row_count": company_mapping_rows,
                    "source": "company_bom_mapping",
                },
                "L5": {
                    "name": "BOM节点",
                    "status": repository.status_from_rows(bom_node_rows, ready=80, partial=20),
                    "row_count": bom_node_rows,
                    "source": "supply_chain_bom_nodes",
                },
                "L6": {
                    "name": "产品/技术路线",
                    "status": repository.status_from_rows(research_rows, ready=1000),
                    "row_count": research_rows,
                    "source": "research_reports_tushare.title",
                },
                "L7": {
                    "name": "公司业务分部",
                    "status": repository.status_from_rows(segment_code_rows, ready=1000, partial=50),
                    "row_count": segment_rows,
                    "company_count": segment_code_rows,
                    "source": "fina_mainbz",
                },
                "L8": {
                    "name": "证据事件",
                    "status": repository.status_from_rows(evidence_rows, ready=1000, partial=100),
                    "row_count": evidence_rows,
                    "source": "company_evidence",
                },
            }

            payload["business_segments"] = {
                "status": repository.status_from_rows(segment_code_rows, ready=1000, partial=50),
                "source_table": "fina_mainbz",
                "row_count": segment_rows,
                "company_count": segment_code_rows,
                "income_supported": repository.column_exists(cur, "fina_mainbz", "biz_income"),
                "ratio_supported": (
                    repository.column_exists(cur, "fina_mainbz", "biz_ratio")
                    and repository.nonempty_text_count(cur, "fina_mainbz", "biz_ratio", 0) > 0
                ),
                "margin_supported": False,
            }
            payload["announcement_body"] = {
                "status": "ready" if announcement_body_rows else ("metadata_only" if announcement_rows else "missing"),
                "source_table": "announcements",
                "row_count": announcement_rows,
                "nonempty_rows": announcement_body_rows,
            }
            payload["research_body"] = {
                "status": "title_only" if research_rows else "missing",
                "source_table": "research_reports_tushare",
                "row_count": research_rows,
                "body_supported": False,
            }
            payload["evidence_events"] = {
                "status": repository.status_from_rows(evidence_rows, ready=1000, partial=100),
                "source_table": "company_evidence",
                "row_count": evidence_rows,
                "target_table": "business_tag_evidence_events",
                "target_status": "planned",
            }
            payload["target_tables"] = {
                table_name: {
                    "exists": repository.table_exists(cur, table_name),
                    "row_count": repository.count(cur, table_name),
                }
                for table_name in target_table_names
            }
            if not announcement_body_rows:
                payload["notes"].append("announcements.content is empty; use ts_raw_anns_d.url or later parser before approved announcement evidence.")
            if segment_code_rows < 1000:
                payload["notes"].append("fina_mainbz coverage is too low for full-market tag revenue attribution.")
    except Exception as e:
        payload["status"] = "degraded"
        payload["error"] = str(e)
        payload["notes"].append("PostgreSQL readiness lookup failed; returning unknown layer coverage.")
    else:
        payload["status"] = "ok"
    return payload


def _normalize_refresh_rank_types(rank_types: list[str]) -> list[str]:
    allowed = {"value", "expectation_gap"}
    normalized = []
    for rank_type in rank_types or []:
        value = str(rank_type or "").strip()
        if not value:
            continue
        if value not in allowed:
            raise HTTPException(status_code=400, detail=f"Unsupported rank_type '{value}'")
        if value not in normalized:
            normalized.append(value)
    if not normalized:
        raise HTTPException(status_code=400, detail="rank_types is empty")
    return normalized


def _refresh_supply_chain_tracking_workflow(
    request: Any,
    *,
    extract_evidence=None,
    batch_score=None,
    query_rankings=None,
) -> dict[str, Any]:
    extract_evidence = extract_evidence or _batch_extract_business_tag_evidence
    batch_score = batch_score or _batch_score_business_tags
    query_rankings = query_rankings or _query_supply_chain_rankings
    score_types = _normalize_batch_score_types(request.score_types) if request.include_scores else []
    rank_types = _normalize_refresh_rank_types(request.rank_types) if request.include_rankings else []
    steps: dict[str, Any] = {}
    rankings: dict[str, Any] = {}
    limitations: list[str] = []
    source_status = "ready"

    if request.include_evidence_extract:
        if not request.mapping_id and not request.code:
            steps["evidence_extract"] = {
                "source_status": "skipped",
                "created_event_count": 0,
                "reason": "证据抽取需要 mapping_id 或 code",
            }
            limitations.append("证据抽取已跳过：缺少 mapping_id 或 code")
        else:
            evidence_payload = extract_evidence(SimpleNamespace(
                mapping_id=request.mapping_id,
                code=request.code,
                source_types=request.source_types,
                limit=request.evidence_limit,
                persist=request.persist,
            ))
            steps["evidence_extract"] = evidence_payload
            limitations.extend(evidence_payload.get("limitations") or [])
    else:
        steps["evidence_extract"] = {"source_status": "skipped", "created_event_count": 0}

    created_event_count = int((steps.get("evidence_extract") or {}).get("created_event_count") or 0)
    steps["human_review"] = {
        "source_status": "pending_review" if created_event_count else "no_new_events",
        "review_required_count": created_event_count,
        "note": "新增证据默认进入 pending_review；评分只消费已 approved 的证据",
    }

    if request.include_scores:
        score_payload = batch_score(SimpleNamespace(
            code=request.code,
            node_id=request.node_id,
            status=request.status,
            score_types=score_types,
            trade_date=request.trade_date,
            persist=request.persist,
            market_expectation_score=request.market_expectation_score,
            limit=request.score_limit,
        ))
        steps["batch_score"] = score_payload
        limitations.extend(score_payload.get("limitations") or [])
        if score_payload.get("source_status") in {"partial_error", "error"}:
            source_status = score_payload["source_status"]
    else:
        steps["batch_score"] = {"source_status": "skipped", "score_count": 0}

    if request.include_rankings:
        for rank_type in rank_types:
            rankings[rank_type] = query_rankings(rank_type, request.top_n, request.trade_date)
    else:
        rankings = {}

    return {
        "version": "supply-chain-v2-refresh-workflow",
        "source_status": source_status,
        "trade_date": request.trade_date,
        "persisted": request.persist,
        "steps": steps,
        "rankings": rankings,
        "limitations": limitations,
    }


def _normalize_business_ratio(value) -> float | None:
    ratio = _to_float(value, None)
    if ratio is None:
        return None
    if ratio > 1 and ratio <= 100:
        ratio = ratio / 100
    return round(min(1.0, max(0.0, ratio)), 4)


def _calculate_company_value_rankings(tag_scores: list[dict[str, Any]]) -> list[dict[str, Any]]:
    companies: dict[str, dict[str, Any]] = {}
    for row in tag_scores:
        code = str(row.get("code") or "").strip()
        if not code:
            continue
        company = companies.setdefault(
            code,
            {
                "code": code,
                "name": str(row.get("name") or code),
                "value_score": 0.0,
                "attributed_tag_count": 0,
                "theme_only_tag_count": 0,
                "business_tags": [],
            },
        )

        total_score = _to_float(row.get("total_score"), 0.0)
        revenue_ratio = _normalize_business_ratio(row.get("revenue_ratio"))
        gross_profit_ratio = _normalize_business_ratio(row.get("gross_profit_ratio"))
        confidence = min(1.0, max(0.0, _to_float(row.get("confidence"), 0.0)))
        evidence_score = _to_float(row.get("evidence_score"), 0.0)
        evidence_weight = round(min(1.0, max(0.5, 0.5 + evidence_score / 200)), 4)

        if gross_profit_ratio is not None:
            attribution_type = "gross_profit"
            attribution_ratio = gross_profit_ratio
        elif revenue_ratio is not None:
            attribution_type = "revenue"
            attribution_ratio = revenue_ratio
        else:
            attribution_type = "missing"
            attribution_ratio = None

        contribution_score = 0.0
        rank_status = "theme_only"
        if attribution_ratio is not None and attribution_ratio > 0 and total_score > 0:
            contribution_score = round(total_score * attribution_ratio * confidence * evidence_weight, 4)
            rank_status = "rankable"
            company["attributed_tag_count"] += 1
        else:
            company["theme_only_tag_count"] += 1

        company["value_score"] = round(company["value_score"] + contribution_score, 4)
        company["business_tags"].append({
            "mapping_id": str(row.get("mapping_id") or ""),
            "tag_name": str(row.get("tag_name") or ""),
            "trade_date": str(row.get("trade_date")) if row.get("trade_date") else None,
            "total_score": total_score,
            "revenue_ratio": revenue_ratio,
            "gross_profit_ratio": gross_profit_ratio,
            "confidence": confidence,
            "evidence_score": evidence_score,
            "evidence_weight": evidence_weight,
            "attribution_type": attribution_type,
            "attribution_ratio": attribution_ratio,
            "contribution_score": contribution_score,
            "rank_status": rank_status,
            "status": str(row.get("status") or ""),
            "score_detail": row.get("score_detail") if isinstance(row.get("score_detail"), dict) else {},
            "evidence_ids": row.get("evidence_ids") if isinstance(row.get("evidence_ids"), list) else [],
        })

    rankings = []
    for company in companies.values():
        company["rank_status"] = "rankable" if company["attributed_tag_count"] > 0 else "theme_only"
        company["business_tags"] = sorted(
            company["business_tags"],
            key=lambda tag: (
                tag["contribution_score"] <= 0,
                -tag["contribution_score"],
                tag["tag_name"],
            ),
        )
        rankings.append(company)

    rankings.sort(
        key=lambda item: (
            -item["value_score"],
            item["rank_status"] != "rankable",
            -item["attributed_tag_count"],
            item["code"],
        )
    )
    for rank, item in enumerate(rankings, start=1):
        item["rank"] = rank
    return rankings


def _calculate_company_expectation_gap_rankings(tag_scores: list[dict[str, Any]]) -> list[dict[str, Any]]:
    companies: dict[str, dict[str, Any]] = {}
    for row in tag_scores:
        code = str(row.get("code") or "").strip()
        if not code:
            continue
        company = companies.setdefault(
            code,
            {
                "code": code,
                "name": str(row.get("name") or code),
                "expectation_gap_score": 0.0,
                "attributed_tag_count": 0,
                "theme_only_tag_count": 0,
                "business_tags": [],
            },
        )

        gap_score = max(0.0, _to_float(row.get("expectation_gap_score"), 0.0))
        actual_progress_score = _to_float(row.get("actual_progress_score"), None)
        market_expectation_score = _to_float(row.get("market_expectation_score"), None)
        evidence_delta_score = _to_float(row.get("evidence_delta_score"), 0.0)
        risk_penalty_score = _to_float(row.get("risk_penalty_score"), 0.0)
        revenue_ratio = _normalize_business_ratio(row.get("revenue_ratio"))
        gross_profit_ratio = _normalize_business_ratio(row.get("gross_profit_ratio"))
        confidence = min(1.0, max(0.0, _to_float(row.get("confidence"), 0.0)))
        evidence_weight = round(min(1.0, max(0.5, 0.5 + evidence_delta_score / 200)), 4)
        risk_weight = round(min(1.0, max(0.0, 1 - risk_penalty_score / 100)), 4)

        if gross_profit_ratio is not None:
            attribution_type = "gross_profit"
            attribution_ratio = gross_profit_ratio
        elif revenue_ratio is not None:
            attribution_type = "revenue"
            attribution_ratio = revenue_ratio
        else:
            attribution_type = "missing"
            attribution_ratio = None

        gap_type = str(row.get("gap_type") or "")
        gap_contribution_score = 0.0
        rank_status = "theme_only"
        if attribution_ratio is not None and attribution_ratio > 0 and gap_score > 0:
            gap_contribution_score = round(gap_score * attribution_ratio * confidence * evidence_weight * risk_weight, 4)
            rank_status = "rankable"
            company["attributed_tag_count"] += 1
        else:
            company["theme_only_tag_count"] += 1

        company["expectation_gap_score"] = round(company["expectation_gap_score"] + gap_contribution_score, 4)
        company["business_tags"].append({
            "mapping_id": str(row.get("mapping_id") or ""),
            "tag_name": str(row.get("tag_name") or ""),
            "trade_date": str(row.get("trade_date")) if row.get("trade_date") else None,
            "expectation_gap_score": gap_score,
            "actual_progress_score": actual_progress_score,
            "market_expectation_score": market_expectation_score,
            "evidence_delta_score": evidence_delta_score,
            "risk_penalty_score": risk_penalty_score,
            "revenue_ratio": revenue_ratio,
            "gross_profit_ratio": gross_profit_ratio,
            "confidence": confidence,
            "evidence_weight": evidence_weight,
            "risk_weight": risk_weight,
            "attribution_type": attribution_type,
            "attribution_ratio": attribution_ratio,
            "gap_contribution_score": gap_contribution_score,
            "gap_type": gap_type,
            "rank_status": rank_status,
            "status": str(row.get("status") or ""),
            "score_detail": row.get("score_detail") if isinstance(row.get("score_detail"), dict) else {},
            "evidence_ids": row.get("evidence_ids") if isinstance(row.get("evidence_ids"), list) else [],
        })

    rankings = []
    for company in companies.values():
        company["rank_status"] = "rankable" if company["attributed_tag_count"] > 0 else "theme_only"
        company["business_tags"] = sorted(
            company["business_tags"],
            key=lambda tag: (
                tag["gap_contribution_score"] <= 0,
                -tag["gap_contribution_score"],
                tag["tag_name"],
            ),
        )
        rankings.append(company)

    rankings.sort(
        key=lambda item: (
            -item["expectation_gap_score"],
            item["rank_status"] != "rankable",
            -item["attributed_tag_count"],
            item["code"],
        )
    )
    for rank, item in enumerate(rankings, start=1):
        item["rank"] = rank
    return rankings


def _query_supply_chain_rankings(
    rank_type: str = "value",
    top_n: int = 50,
    trade_date: Optional[str] = None,
) -> dict[str, Any]:
    safe_rank_type = str(rank_type or "value").strip() or "value"
    safe_top_n = min(200, max(1, int(top_n or 50)))
    payload: dict[str, Any] = {
        "version": "supply-chain-v2-rankings",
        "rank_type": safe_rank_type,
        "trade_date": trade_date,
        "source_status": "unknown",
        "items": [],
        "limitations": [],
    }
    if safe_rank_type not in {"value", "expectation_gap"}:
        payload["source_status"] = "unsupported_rank_type"
        payload["limitations"].append("目前仅支持 value 和 expectation_gap 排序")
        return payload

    try:
        with repository.connect() as pg:
            cur = pg.cursor()
            if not repository.table_exists(cur, "business_tag_mapping"):
                payload["source_status"] = "mapping_table_missing"
                payload["limitations"].append("business_tag_mapping table is missing")
                return payload

            scan_limit = max(safe_top_n * 20, 200)
            if safe_rank_type == "value":
                if not repository.table_exists(cur, "business_tag_three_high_scores"):
                    payload["source_status"] = "score_table_missing"
                    payload["limitations"].append("business_tag_three_high_scores table is missing")
                    return payload
                cur.execute(
                    """
                    SELECT
                        m.mapping_id,
                        m.code,
                        m.tag_name,
                        m.revenue_ratio,
                        m.gross_profit_ratio,
                        m.confidence,
                        m.status,
                        sc.trade_date,
                        sc.total_score,
                        sc.evidence_score,
                        sc.score_detail,
                        sc.evidence_ids
                    FROM business_tag_mapping m
                    JOIN LATERAL (
                        SELECT trade_date, total_score, evidence_score, score_detail, evidence_ids, created_at
                        FROM business_tag_three_high_scores
                        WHERE mapping_id = m.mapping_id
                          AND (%s IS NULL OR trade_date <= %s::date)
                        ORDER BY trade_date DESC, created_at DESC
                        LIMIT 1
                    ) sc ON TRUE
                    WHERE COALESCE(m.status, '') <> 'rejected'
                    ORDER BY sc.total_score DESC NULLS LAST, m.confidence DESC NULLS LAST
                    LIMIT %s
                    """,
                    (trade_date, trade_date, scan_limit),
                )
                tag_scores = []
                for row in cur.fetchall():
                    tag_scores.append({
                        "mapping_id": str(row[0]),
                        "code": str(row[1] or ""),
                        "name": str(row[1] or ""),
                        "tag_name": str(row[2] or ""),
                        "revenue_ratio": _to_float(row[3], None),
                        "gross_profit_ratio": _to_float(row[4], None),
                        "confidence": _to_float(row[5], 0.0),
                        "status": str(row[6] or ""),
                        "trade_date": str(row[7]) if row[7] else None,
                        "total_score": _to_float(row[8], 0.0),
                        "evidence_score": _to_float(row[9], 0.0),
                        "score_detail": _json_or_default(row[10], {}),
                        "evidence_ids": _json_or_default(row[11], []),
                    })
                rankings = _calculate_company_value_rankings(tag_scores)
                payload["limitations"].append("无收入/毛利归因的标签仅作为主题相关明细，不进入核心排序贡献")
            else:
                if not repository.table_exists(cur, "business_tag_expectation_gap_scores"):
                    payload["source_status"] = "gap_table_missing"
                    payload["limitations"].append("business_tag_expectation_gap_scores table is missing")
                    return payload
                cur.execute(
                    """
                    SELECT
                        m.mapping_id,
                        m.code,
                        m.tag_name,
                        m.revenue_ratio,
                        m.gross_profit_ratio,
                        m.confidence,
                        m.status,
                        eg.trade_date,
                        eg.actual_progress_score,
                        eg.market_expectation_score,
                        eg.evidence_delta_score,
                        eg.risk_penalty_score,
                        eg.expectation_gap_score,
                        eg.gap_type,
                        eg.score_detail,
                        eg.evidence_ids
                    FROM business_tag_mapping m
                    JOIN LATERAL (
                        SELECT trade_date, actual_progress_score, market_expectation_score,
                               evidence_delta_score, risk_penalty_score, expectation_gap_score,
                               gap_type, score_detail, evidence_ids, created_at
                        FROM business_tag_expectation_gap_scores
                        WHERE mapping_id = m.mapping_id
                          AND (%s IS NULL OR trade_date <= %s::date)
                        ORDER BY trade_date DESC, created_at DESC
                        LIMIT 1
                    ) eg ON TRUE
                    WHERE COALESCE(m.status, '') <> 'rejected'
                    ORDER BY eg.expectation_gap_score DESC NULLS LAST, m.confidence DESC NULLS LAST
                    LIMIT %s
                    """,
                    (trade_date, trade_date, scan_limit),
                )
                tag_scores = []
                for row in cur.fetchall():
                    tag_scores.append({
                        "mapping_id": str(row[0]),
                        "code": str(row[1] or ""),
                        "name": str(row[1] or ""),
                        "tag_name": str(row[2] or ""),
                        "revenue_ratio": _to_float(row[3], None),
                        "gross_profit_ratio": _to_float(row[4], None),
                        "confidence": _to_float(row[5], 0.0),
                        "status": str(row[6] or ""),
                        "trade_date": str(row[7]) if row[7] else None,
                        "actual_progress_score": _to_float(row[8], None),
                        "market_expectation_score": _to_float(row[9], None),
                        "evidence_delta_score": _to_float(row[10], 0.0),
                        "risk_penalty_score": _to_float(row[11], 0.0),
                        "expectation_gap_score": _to_float(row[12], 0.0),
                        "gap_type": str(row[13] or ""),
                        "score_detail": _json_or_default(row[14], {}),
                        "evidence_ids": _json_or_default(row[15], []),
                    })
                rankings = _calculate_company_expectation_gap_rankings(tag_scores)
                payload["limitations"].append("无收入/毛利归因的预期差标签仅作为主题相关明细，不进入核心排序贡献")

            payload["source_status"] = "ready" if rankings else "empty"
            if rankings and not payload["trade_date"]:
                payload["trade_date"] = rankings[0]["business_tags"][0].get("trade_date")
            payload["items"] = rankings[:safe_top_n]
    except Exception as e:
        payload["source_status"] = "degraded"
        payload["error"] = str(e)
        payload["limitations"].append("PostgreSQL supply-chain ranking lookup failed")
    return payload


def _candidate_rank_clamp(value: Any, low: float = 0.0, high: float = 100.0) -> float:
    try:
        numeric = float(value or 0.0)
    except Exception:
        numeric = 0.0
    return max(low, min(high, numeric))


def _normalize_candidate_expectation_gap(value: Any) -> float:
    return _candidate_rank_clamp((_to_float(value, 0.0) + 100.0) / 2.0)


def _normalize_candidate_momentum(value: Any) -> float:
    return _candidate_rank_clamp((_to_float(value, 0.0) + 20.0) / 60.0 * 100.0)


def _load_bigtech_capex_context() -> dict[str, Any]:
    if not INDUSTRY_CHAIN_TEMPLATE_PATH.exists():
        return {"company_count": 0, "record_count": 0, "layers": {}, "companies": []}
    try:
        data = json.loads(INDUSTRY_CHAIN_TEMPLATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"company_count": 0, "record_count": 0, "layers": {}, "companies": []}
    template = next((item for item in data.get("templates", []) if item.get("template_id") == "complex_tech"), {})
    layers: dict[str, list[dict[str, Any]]] = {}
    companies: set[str] = set()
    for layer in template.get("layers", []):
        layer_id = str(layer.get("layer_id") or "")
        for record in layer.get("capex_evidence", []):
            company = str(record.get("company") or "")
            if record.get("source_id") != "sec_company_filings":
                continue
            if record.get("evidence_level") != "reported":
                continue
            if company not in BIGTECH_COMPANIES:
                continue
            layers.setdefault(layer_id, []).append(record)
            companies.add(company)
    return {
        "company_count": len(companies),
        "record_count": sum(len(items) for items in layers.values()),
        "layers": layers,
        "companies": sorted(companies),
    }


def _score_bigtech_capex_tailwind(row: dict[str, Any], context: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    if str(row.get("chain_id") or "") != "ai_compute":
        return {
            "score": 0.0,
            "matched_layers": [],
            "commercialization_indicator": "无板块级CAPEX加成",
            "expectation_gap_indicator": "无",
            "trigger_signal_indicator": "无",
        }
    context = context or _load_bigtech_capex_context()
    companies = context.get("companies") or []
    if not companies:
        return {
            "score": 0.0,
            "matched_layers": [],
            "commercialization_indicator": "缺少海外CAPEX证据",
            "expectation_gap_indicator": "无",
            "trigger_signal_indicator": "无",
        }
    text = " ".join(str(row.get(key) or "") for key in ("tag_name", "node_id", "industry", "name"))
    text_lower = text.lower()
    matched_layers = [
        layer_id
        for layer_id, keywords in AI_COMPUTE_LAYER_KEYWORDS.items()
        if any(keyword.lower() in text_lower for keyword in keywords)
    ]
    if not matched_layers:
        matched_layers = ["demand"]
    record_count = int(context.get("record_count") or 0)
    company_count = int(context.get("company_count") or 0)
    layer_coverage = len(set(matched_layers)) / max(len(AI_COMPUTE_LAYER_KEYWORDS), 1)
    evidence_depth = min(record_count / 13.0, 1.0)
    company_depth = min(company_count / len(BIGTECH_COMPANIES), 1.0)
    score = round(_candidate_rank_clamp(company_depth * 45.0 + evidence_depth * 35.0 + layer_coverage * 20.0), 2)
    if score >= 80:
        commercialization = "C3：海外云厂商CAPEX和数据中心扩张已形成强验证"
        gap = "CAPEX/AI基础设施证据强于普通概念预期"
        trigger = "海外大厂继续扩张AI数据中心、服务器、网络和云容量"
    elif score >= 50:
        commercialization = "C2：海外云厂商CAPEX方向已有文件验证"
        gap = "CAPEX方向证据支持预期差跟踪"
        trigger = "关注后续财报CAPEX指引和订单传导"
    else:
        commercialization = "C1：有板块证据但传导仍弱"
        gap = "证据不足以单独构成预期差"
        trigger = "等待更多CAPEX或订单证据"
    return {
        "score": score,
        "matched_layers": matched_layers,
        "company_count": company_count,
        "record_count": record_count,
        "companies": companies,
        "commercialization_indicator": commercialization,
        "expectation_gap_indicator": gap,
        "trigger_signal_indicator": trigger,
    }


def _score_company_capex_evidence(row: dict[str, Any]) -> dict[str, Any]:
    evidence_count = int(row.get("capex_evidence_count") or 0)
    if evidence_count <= 0:
        return {
            "score": 0.0,
            "evidence_count": 0,
            "amount_count": 0,
            "direction_ai_count": 0,
            "fresh_count": 0,
            "indicator": "无个股CAPEX证据",
        }
    amount_count = int(row.get("capex_amount_count") or 0)
    direction_ai_count = int(row.get("capex_direction_ai_count") or 0)
    fresh_count = int(row.get("capex_fresh_count") or 0)
    avg_confidence = _candidate_rank_clamp(_to_float(row.get("capex_avg_confidence"), 0.0) * 100.0)
    amount_score = min(amount_count / evidence_count, 1.0) * 25.0
    direction_score = min(direction_ai_count / evidence_count, 1.0) * 30.0
    freshness_score = min(fresh_count / evidence_count, 1.0) * 20.0
    confidence_score = avg_confidence * 0.25
    score = round(_candidate_rank_clamp(amount_score + direction_score + freshness_score + confidence_score), 2)
    if direction_ai_count and amount_count:
        indicator = "有金额和AI相关投入方向证据"
    elif direction_ai_count:
        indicator = "有AI相关投入方向证据，金额待补"
    elif amount_count:
        indicator = "有CAPEX金额证据，方向需继续确认"
    else:
        indicator = "有CAPEX方向证据，强度较弱"
    return {
        "score": score,
        "evidence_count": evidence_count,
        "amount_count": amount_count,
        "direction_ai_count": direction_ai_count,
        "fresh_count": fresh_count,
        "avg_confidence": round(avg_confidence, 2),
        "latest_as_of_date": str(row.get("capex_latest_as_of_date") or ""),
        "directions": _json_or_default(row.get("capex_directions"), []),
        "indicator": indicator,
    }


def _score_supply_chain_candidate_row(row: dict[str, Any], capex_context: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    three_high = _candidate_rank_clamp(row.get("three_high_total"))
    moat = _candidate_rank_clamp(row.get("moat_score"))
    stage = _candidate_rank_clamp(row.get("stage_score"))
    evidence = _candidate_rank_clamp(row.get("evidence_score"))
    l8 = _candidate_rank_clamp(_to_float(row.get("l8_match_rate"), 0.0) * 100.0)
    fresh = _candidate_rank_clamp(_to_float(row.get("fresh_rate"), 0.0) * 100.0)
    gap = _normalize_candidate_expectation_gap(row.get("expectation_gap_score"))
    momentum = _normalize_candidate_momentum(row.get("change_20d_pct"))
    capex_tailwind = _score_bigtech_capex_tailwind(row, capex_context)
    company_capex = _score_company_capex_evidence(row)
    base_score = (
        three_high * 0.35
        + moat * 0.15
        + stage * 0.12
        + evidence * 0.12
        + l8 * 0.10
        + fresh * 0.08
        + gap * 0.06
        + momentum * 0.02
    )
    rank_score = round(
        _candidate_rank_clamp(
            base_score
            + _to_float(capex_tailwind.get("score"), 0.0) * 0.04
            + _to_float(company_capex.get("score"), 0.0) * 0.03
        ),
        2,
    )
    if rank_score >= 80 and fresh >= 70 and l8 >= 50:
        signal = "重点候选"
    elif rank_score >= 65:
        signal = "观察"
    else:
        signal = "暂缓"
    item = dict(row)
    item.update({
        "rank_score": rank_score,
        "signal": signal,
        "score_parts": {
            "three_high": round(three_high, 2),
            "moat": round(moat, 2),
            "stage": round(stage, 2),
            "evidence": round(evidence, 2),
            "l8": round(l8, 2),
            "freshness": round(fresh, 2),
            "expectation_gap": round(gap, 2),
            "momentum": round(momentum, 2),
            "bigtech_capex_tailwind": round(_to_float(capex_tailwind.get("score"), 0.0), 2),
            "company_capex_evidence": round(_to_float(company_capex.get("score"), 0.0), 2),
        },
        "bigtech_capex_tailwind": capex_tailwind,
        "company_capex_evidence": company_capex,
        "commercialization_indicator": capex_tailwind["commercialization_indicator"] or row.get("commercialization_stage") or "",
        "expectation_gap_indicator": company_capex["indicator"] if company_capex["score"] else capex_tailwind["expectation_gap_indicator"],
        "trigger_signal_indicator": capex_tailwind["trigger_signal_indicator"],
    })
    return item


def _aggregate_supply_chain_candidate_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault((str(row.get("chain_id") or ""), str(row.get("code") or "")), []).append(row)
    aggregated: list[dict[str, Any]] = []
    for (chain_id, code), items in grouped.items():
        best = max(items, key=lambda item: _to_float(item.get("rank_score"), 0.0))
        sorted_items = sorted(items, key=lambda item: -_to_float(item.get("rank_score"), 0.0))
        avg_rank = sum(_to_float(item.get("rank_score"), 0.0) for item in items) / max(len(items), 1)
        aggregated.append({
            "chain_id": chain_id,
            "code": code,
            "name": str(best.get("name") or code),
            "industry": str(best.get("industry") or ""),
            "rank_score": round(_to_float(best.get("rank_score"), 0.0), 2),
            "avg_rank_score": round(avg_rank, 2),
            "signal": best.get("signal"),
            "tag_count": len({item.get("mapping_id") for item in items}),
            "best_mapping_id": best.get("mapping_id"),
            "best_tag_name": best.get("tag_name"),
            "node_id": best.get("node_id"),
            "mapping_status": best.get("mapping_status"),
            "three_high_total": round(_to_float(best.get("three_high_total"), 0.0), 2),
            "growth_score": round(_to_float(best.get("growth_score"), 0.0), 2),
            "profit_score": round(_to_float(best.get("profit_score"), 0.0), 2),
            "moat_score": round(_to_float(best.get("moat_score"), 0.0), 2),
            "stage_score": round(_to_float(best.get("stage_score"), 0.0), 2),
            "evidence_score": round(_to_float(best.get("evidence_score"), 0.0), 2),
            "expectation_gap_score": round(_to_float(best.get("expectation_gap_score"), 0.0), 2),
            "gap_type": str(best.get("gap_type") or ""),
            "research_stage": str(best.get("research_stage") or ""),
            "commercialization_stage": str(best.get("commercialization_stage") or ""),
            "commercialization_indicator": str(best.get("commercialization_indicator") or ""),
            "expectation_gap_indicator": str(best.get("expectation_gap_indicator") or ""),
            "trigger_signal_indicator": str(best.get("trigger_signal_indicator") or ""),
            "bigtech_capex_tailwind": best.get("bigtech_capex_tailwind") or {},
            "company_capex_evidence": best.get("company_capex_evidence") or {},
            "l8_match_rate": round(_to_float(best.get("l8_match_rate"), 0.0), 4),
            "fresh_rate": round(_to_float(best.get("fresh_rate"), 0.0), 4),
            "freshness_status": str(best.get("freshness_status") or "unknown"),
            "fact_count": int(sum(int(item.get("fact_count") or 0) for item in items)),
            "latest_price": _to_float(best.get("latest_price"), None),
            "latest_trade_date": str(best.get("latest_trade_date") or ""),
            "change_1d_pct": _to_float(best.get("change_1d_pct"), None),
            "change_20d_pct": _to_float(best.get("change_20d_pct"), None),
            "mapping_ids": [item.get("mapping_id") for item in sorted_items[:8]],
            "tag_names": [item.get("tag_name") for item in sorted_items[:8]],
        })
    aggregated.sort(key=lambda item: (-_to_float(item.get("rank_score"), 0.0), item.get("chain_id") or "", item.get("code") or ""))
    for idx, item in enumerate(aggregated, start=1):
        item["rank"] = idx
    return aggregated


def _query_business_tag_score_mapping_context(cur, mapping_id: str) -> dict[str, Any] | None:
    if repository.table_exists(cur, "business_tag_mapping"):
        cur.execute(
            """
            SELECT
                m.mapping_id,
                m.code,
                m.node_id,
                m.tag_name,
                m.theme_id,
                m.chain_id,
                m.revenue_ratio,
                m.gross_profit_ratio,
                m.confidence,
                m.status,
                s.gross_margin
            FROM business_tag_mapping m
            LEFT JOIN company_business_segments s ON s.segment_id = m.business_segment_id
            WHERE m.mapping_id = %s
            LIMIT 1
            """,
            (mapping_id,),
        )
        row = cur.fetchone()
        if row:
            return {
                "mapping_id": str(row[0]),
                "code": str(row[1] or ""),
                "node_id": row[2],
                "tag_name": row[3],
                "theme_id": row[4],
                "chain_id": row[5],
                "revenue_ratio": _to_float(row[6], None),
                "gross_profit_ratio": _to_float(row[7], None),
                "confidence": _to_float(row[8], 0.0),
                "status": row[9],
                "gross_margin": _to_float(row[10], None),
                "source": "business_tag_mapping",
            }

    mapping = _query_business_tag_mapping_context(cur, mapping_id)
    if not mapping:
        return None
    mapping.update({
        "revenue_ratio": None,
        "gross_profit_ratio": None,
        "gross_margin": None,
        "confidence": 0.0,
    })
    return mapping


def _query_business_tag_stage_for_score(cur, mapping_id: str) -> dict[str, Any]:
    if not repository.table_exists(cur, "business_tag_stage_tracking"):
        return {"research_stage": "R0", "commercialization_stage": "C0"}
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
    row = cur.fetchone()
    if not row:
        return {"research_stage": "R0", "commercialization_stage": "C0"}
    return {
        "research_stage": str(row[0] or "R0"),
        "commercialization_stage": str(row[1] or "C0"),
    }


def _query_business_tag_events_for_score(cur, mapping_id: str) -> list[dict[str, Any]]:
    if not repository.table_exists(cur, "business_tag_evidence_events"):
        return []
    cur.execute(
        """
        SELECT event_id, evidence_type, impact_dimensions, confidence, review_status
        FROM business_tag_evidence_events
        WHERE mapping_id = %s
        ORDER BY event_date DESC NULLS LAST, created_at DESC
        LIMIT 200
        """,
        (mapping_id,),
    )
    return [
        {
            "event_id": str(row[0]),
            "evidence_type": str(row[1] or ""),
            "impact_dimensions": _json_or_default(row[2], []),
            "confidence": _to_float(row[3], 0.0),
            "review_status": str(row[4] or "pending_review"),
        }
        for row in cur.fetchall()
    ]


def _persist_business_tag_three_high_score(cur, score: dict[str, Any]) -> None:
    cur.execute(
        """
        INSERT INTO business_tag_three_high_scores (
            score_id, mapping_id, trade_date, growth_score, profit_score,
            moat_score, stage_score, evidence_score, total_score,
            score_detail, evidence_ids
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb)
        ON CONFLICT (mapping_id, trade_date) DO UPDATE SET
            growth_score = EXCLUDED.growth_score,
            profit_score = EXCLUDED.profit_score,
            moat_score = EXCLUDED.moat_score,
            stage_score = EXCLUDED.stage_score,
            evidence_score = EXCLUDED.evidence_score,
            total_score = EXCLUDED.total_score,
            score_detail = EXCLUDED.score_detail,
            evidence_ids = EXCLUDED.evidence_ids
        """,
        (
            score["score_id"],
            score["mapping_id"],
            score["trade_date"],
            score["growth_score"],
            score["profit_score"],
            score["moat_score"],
            score["stage_score"],
            score["evidence_score"],
            score["total_score"],
            json.dumps(score["score_detail"], ensure_ascii=False),
            json.dumps(score["evidence_ids"], ensure_ascii=False),
        ),
    )


def _business_tag_materialization_tables() -> list[str]:
    return [
        "business_tag_mapping",
        "business_tag_evidence_events",
        "business_tag_l8_evidence_status",
        "business_tag_stage_tracking",
        "business_tag_three_high_scores",
    ]


def _query_inferred_bom_mapping_rows(
    cur,
    request: Any,
) -> list[dict[str, Any]]:
    if not repository.table_exists(cur, "company_bom_mapping"):
        raise HTTPException(status_code=503, detail="company_bom_mapping table is missing")

    where_clauses = ["m.mapping_id IS NOT NULL"]
    params: list[Any] = []
    if request.theme_id:
        where_clauses.append("n.theme_id = %s")
        params.append(request.theme_id)
    if request.node_id:
        where_clauses.append("m.node_id = %s")
        params.append(request.node_id)
    if request.code:
        where_clauses.append("m.code = ANY(%s)")
        params.append(_code_variants(request.code))
    if request.status:
        where_clauses.append("m.status = %s")
        params.append(request.status)
    params.append(request.limit)

    cur.execute(
        f"""
        SELECT
            m.mapping_id,
            m.code,
            COALESCE(s.name, m.code) AS company_name,
            m.node_id,
            COALESCE(n.name, m.node_id) AS node_name,
            n.theme_id,
            n.chain_id,
            COALESCE(t.name, n.theme_id, '') AS theme_name,
            COALESCE(m.product_name, '') AS product_name,
            COALESCE(m.material_name, '') AS material_name,
            COALESCE(m.confidence, 0.0) AS confidence,
            COALESCE(m.status, 'pending_review') AS status,
            c.evidence
        FROM company_bom_mapping m
        LEFT JOIN supply_chain_bom_nodes n ON n.node_id = m.node_id
        LEFT JOIN policy_themes t ON t.theme_id = n.theme_id
        LEFT JOIN stocks s ON s.code = m.code
        LEFT JOIN company_chain_mapping c ON c.code = m.code AND c.node_id = m.node_id
        WHERE {" AND ".join(where_clauses)}
        ORDER BY
            CASE COALESCE(m.status, '')
                WHEN 'verified' THEN 1
                WHEN 'pending_review' THEN 2
                WHEN 'weak_evidence' THEN 3
                ELSE 4
            END,
            m.confidence DESC NULLS LAST,
            m.updated_at DESC NULLS LAST
        LIMIT %s
        """,
        tuple(params),
    )
    rows: list[dict[str, Any]] = []
    for row in cur.fetchall():
        chain_evidence = _json_or_default(row[12], {})
        mapping_keywords = chain_evidence.get("evidence") if isinstance(chain_evidence, dict) else []
        rows.append({
            "mapping_id": str(row[0]),
            "code": str(row[1] or ""),
            "company_name": str(row[2] or ""),
            "node_id": str(row[3] or ""),
            "node_name": str(row[4] or ""),
            "theme_id": row[5],
            "chain_id": row[6],
            "theme_name": str(row[7] or ""),
            "product_name": str(row[8] or ""),
            "material_name": str(row[9] or ""),
            "confidence": _to_float(row[10], 0.0),
            "status": str(row[11] or "pending_review"),
            "mapping_keywords": mapping_keywords if isinstance(mapping_keywords, list) else [],
            "mapping_source": chain_evidence.get("mapping_source") if isinstance(chain_evidence, dict) else None,
        })
    return rows


def _query_l8_source_evidence_events_for_mapping(
    cur,
    mapping: dict[str, Any],
    *,
    limit: int = 30,
) -> list[dict[str, Any]]:
    sources = _query_candidate_sources_for_mapping(
        cur,
        mapping,
        ["announcement_title", "research_title", "irm_qa", "interact_qa"],
        limit,
    )
    seen: set[str] = set()
    events: list[dict[str, Any]] = []
    for source in sources:
        for event in _build_l8_source_evidence_events(
            mapping_id=str(mapping["mapping_id"]),
            mapping=mapping,
            source=source,
        ):
            dedupe_key = "|".join([
                str(event.get("l8_dimension_id") or event.get("evidence_type") or ""),
                str(event.get("source_type") or ""),
                str(event.get("title") or ""),
                str(event.get("excerpt") or "")[:200],
            ])
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            events.append(event)
    return events


def _clear_generated_l8_events_for_mapping(cur, mapping_id: str) -> None:
    event_like = f"L8-{mapping_id}-%"
    if repository.table_exists(cur, "business_tag_evidence_events"):
        cur.execute(
            """
            DELETE FROM business_tag_evidence_events
            WHERE mapping_id = %s
              AND event_id LIKE %s
              AND COALESCE(review_status, '') <> 'approved'
            """,
            (mapping_id, event_like),
        )
    if repository.table_exists(cur, "company_evidence"):
        cur.execute(
            """
            DELETE FROM company_evidence
            WHERE evidence_id LIKE %s
              AND COALESCE(status, '') <> 'approved'
            """,
            (event_like,),
        )


def _persist_business_tag_mapping(cur, mapping: dict[str, Any]) -> None:
    cur.execute(
        """
        INSERT INTO business_tag_mapping (
            mapping_id, code, business_segment_id, node_id, theme_id, chain_id,
            tag_name, l1_l8_path, revenue_ratio, gross_profit_ratio,
            confidence, status, evidence_ids
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s::jsonb)
        ON CONFLICT (mapping_id) DO UPDATE SET
            code = EXCLUDED.code,
            business_segment_id = EXCLUDED.business_segment_id,
            node_id = EXCLUDED.node_id,
            theme_id = EXCLUDED.theme_id,
            chain_id = EXCLUDED.chain_id,
            tag_name = EXCLUDED.tag_name,
            l1_l8_path = EXCLUDED.l1_l8_path,
            revenue_ratio = EXCLUDED.revenue_ratio,
            gross_profit_ratio = EXCLUDED.gross_profit_ratio,
            confidence = EXCLUDED.confidence,
            status = EXCLUDED.status,
            evidence_ids = EXCLUDED.evidence_ids,
            updated_at = CURRENT_TIMESTAMP
        """,
        (
            mapping["mapping_id"],
            mapping["code"],
            mapping["business_segment_id"],
            mapping["node_id"],
            mapping["theme_id"],
            mapping["chain_id"],
            mapping["tag_name"],
            json.dumps(mapping["l1_l8_path"], ensure_ascii=False),
            mapping["revenue_ratio"],
            mapping["gross_profit_ratio"],
            mapping["confidence"],
            mapping["status"],
            json.dumps(mapping["evidence_ids"], ensure_ascii=False),
        ),
    )


def _persist_business_tag_l8_evidence_status(cur, record: dict[str, Any]) -> None:
    cur.execute(
        """
        INSERT INTO business_tag_l8_evidence_status (
            status_id, mapping_id, code, node_id, dimension_id, dimension_name,
            source_status, evidence_event_ids, evidence_count, evidence_summary,
            required_keywords, updated_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s::jsonb, %s)
        ON CONFLICT (mapping_id, dimension_id) DO UPDATE SET
            code = EXCLUDED.code,
            node_id = EXCLUDED.node_id,
            dimension_name = EXCLUDED.dimension_name,
            source_status = EXCLUDED.source_status,
            evidence_event_ids = EXCLUDED.evidence_event_ids,
            evidence_count = EXCLUDED.evidence_count,
            evidence_summary = EXCLUDED.evidence_summary,
            required_keywords = EXCLUDED.required_keywords,
            updated_at = EXCLUDED.updated_at
        """,
        (
            record["status_id"],
            record["mapping_id"],
            record["code"],
            record["node_id"],
            record["dimension_id"],
            record["dimension_name"],
            record["source_status"],
            json.dumps(record["evidence_event_ids"], ensure_ascii=False),
            record["evidence_count"],
            record["evidence_summary"],
            json.dumps(record["required_keywords"], ensure_ascii=False),
            record["updated_at"],
        ),
    )


def _persist_business_tag_stage(cur, stage: dict[str, Any]) -> None:
    cur.execute(
        """
        INSERT INTO business_tag_stage_tracking (
            stage_id, mapping_id, trade_date, research_stage, commercialization_stage,
            stage_reason, source_event_id, last_stage_change_date, review_status
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (stage_id) DO UPDATE SET
            trade_date = EXCLUDED.trade_date,
            research_stage = EXCLUDED.research_stage,
            commercialization_stage = EXCLUDED.commercialization_stage,
            stage_reason = EXCLUDED.stage_reason,
            source_event_id = EXCLUDED.source_event_id,
            last_stage_change_date = EXCLUDED.last_stage_change_date,
            review_status = EXCLUDED.review_status
        """,
        (
            stage["stage_id"],
            stage["mapping_id"],
            stage["trade_date"],
            stage["research_stage"],
            stage["commercialization_stage"],
            stage["stage_reason"],
            stage["source_event_id"],
            stage["last_stage_change_date"],
            stage["review_status"],
        ),
    )


def _persist_inferred_legacy_company_evidence(cur, materialized: dict[str, Any]) -> None:
    if not repository.table_exists(cur, "company_evidence"):
        return
    event = materialized["evidence_event"]
    _persist_legacy_company_evidence_event(cur, event)


def _persist_legacy_company_evidence_event(cur, event: dict[str, Any]) -> None:
    if not repository.table_exists(cur, "company_evidence"):
        return
    cur.execute(
        """
        INSERT INTO company_evidence (
            evidence_id, code, node_id, source_id, evidence_type,
            summary, excerpt, confidence, evidence_date, status
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (evidence_id) DO UPDATE SET
            code = EXCLUDED.code,
            node_id = EXCLUDED.node_id,
            source_id = EXCLUDED.source_id,
            evidence_type = EXCLUDED.evidence_type,
            summary = EXCLUDED.summary,
            excerpt = EXCLUDED.excerpt,
            confidence = EXCLUDED.confidence,
            evidence_date = EXCLUDED.evidence_date,
            status = EXCLUDED.status
        """,
        (
            event["event_id"],
            event["code"],
            event["node_id"],
            event["source_id"],
            event["evidence_type"],
            event["title"],
            event["excerpt"],
            event["confidence"],
            event["event_date"],
            event["review_status"],
        ),
    )


def _link_inferred_evidence_to_company_bom_mapping(cur, materialized: dict[str, Any]) -> None:
    event_ids = [
        materialized["evidence_event"]["event_id"],
        *[
            str(event.get("event_id"))
            for event in materialized.get("l8_source_events", [])
            if event.get("event_id")
        ],
    ]
    mapping_id = materialized["mapping"]["mapping_id"]
    event_ids_json = json.dumps(event_ids, ensure_ascii=False)
    cur.execute(
        """
        UPDATE company_bom_mapping
        SET evidence_ids = (
                SELECT COALESCE(jsonb_agg(DISTINCT item.value), '[]'::jsonb)
                FROM jsonb_array_elements_text(COALESCE(evidence_ids, '[]'::jsonb) || %s::jsonb) AS item(value)
            ),
            updated_at = CURRENT_TIMESTAMP
        WHERE mapping_id = %s
        """,
        (event_ids_json, mapping_id),
    )


def _persist_inferred_company_chain_projection(cur, materialized: dict[str, Any]) -> bool:
    if not repository.table_exists(cur, "company_chain_mapping"):
        return False
    mapping = materialized["mapping"]
    score = materialized["three_high_score"]
    event = materialized["evidence_event"]
    cur.execute(
        """
        SELECT id, evidence, three_factors
        FROM company_chain_mapping
        WHERE code = %s AND node_id = %s
        LIMIT 1
        """,
        (mapping["code"], mapping["node_id"]),
    )
    row = cur.fetchone()
    if not row:
        return False
    evidence_payload = _json_or_default(row[1], {})
    three_factors_payload = _json_or_default(row[2], {})
    if not isinstance(evidence_payload, dict):
        evidence_payload = {}
    if not isinstance(three_factors_payload, dict):
        three_factors_payload = {}
    evidence_payload["inferred_materialization"] = {
        "source": "rule_inference",
        "business_tag_mapping_id": mapping["mapping_id"],
        "evidence_event_id": event["event_id"],
        "l8_source_event_ids": [
            str(item.get("event_id"))
            for item in materialized.get("l8_source_events", [])
            if item.get("event_id")
        ],
        "l8_evidence_status": materialized.get("l8_evidence_statuses", []),
        "l1_l8_path": mapping["l1_l8_path"],
        "requires_original_evidence": True,
    }
    three_factors_payload["inferred_three_high"] = {
        "source": "rule_inference_baseline",
        "inference_only": True,
        "growth_score": score["growth_score"],
        "profit_score": score["profit_score"],
        "moat_score": score["moat_score"],
        "stage_score": score["stage_score"],
        "evidence_score": score["evidence_score"],
        "total_score": score["total_score"],
        "score_cap": score["score_detail"]["score_cap"],
        "evidence_ids": score["evidence_ids"],
    }
    cur.execute(
        "UPDATE company_chain_mapping SET evidence = %s::jsonb, three_factors = %s::jsonb WHERE id = %s",
        (
            json.dumps(evidence_payload, ensure_ascii=False),
            json.dumps(three_factors_payload, ensure_ascii=False),
            row[0],
        ),
    )
    return True


def _materialize_supply_chain_inferred_data(
    request: Any,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "version": "supply-chain-v2-inferred-materialize",
        "source_status": "unknown",
        "persisted": request.persist,
        "filters": {
            "theme_id": request.theme_id,
            "node_id": request.node_id,
            "code": request.code,
            "status": request.status,
            "limit": request.limit,
        },
        "mapping_count": 0,
        "written": {
            "business_tag_mapping": 0,
            "business_tag_evidence_events": 0,
            "business_tag_l8_evidence_status": 0,
            "business_tag_l8_source_events": 0,
            "business_tag_stage_tracking": 0,
            "business_tag_three_high_scores": 0,
            "company_evidence": 0,
            "company_bom_mapping": 0,
            "company_chain_mapping": 0,
        },
        "preview": [],
        "limitations": [
            "推导证据仅表示系统按 BOM 和映射规则生成的候选证据，不能替代公告、研报、年报原文",
            "inference_only 三高基线不进入强证据结论，盈利分在没有业务级毛利前保持为空",
        ],
    }
    try:
        with repository.connect() as pg:
            cur = pg.cursor()
            missing_tables = [
                table_name
                for table_name in _business_tag_materialization_tables()
                if not repository.table_exists(cur, table_name)
            ]
            if request.persist and missing_tables:
                raise HTTPException(
                    status_code=503,
                    detail=f"business tag materialization tables are missing: {', '.join(missing_tables)}",
                )

            rows = _query_inferred_bom_mapping_rows(cur, request)
            payload["mapping_count"] = len(rows)
            if not rows:
                payload["source_status"] = "empty"
                return payload

            for row in rows:
                materialized = _build_inferred_business_tag_materialization(
                    row,
                    trade_date=request.trade_date,
                )
                l8_source_events = _query_l8_source_evidence_events_for_mapping(
                    cur,
                    materialized["mapping"],
                    limit=30,
                )
                materialized["l8_source_events"] = l8_source_events
                materialized["l8_evidence_statuses"] = _build_l8_evidence_status_records(
                    mapping=materialized["mapping"],
                    l8_source_events=l8_source_events,
                    trade_date=request.trade_date,
                )
                payload["preview"].append({
                    "mapping_id": materialized["mapping"]["mapping_id"],
                    "code": materialized["mapping"]["code"],
                    "tag_name": materialized["mapping"]["tag_name"],
                    "status": materialized["mapping"]["status"],
                    "l1_l8_path": materialized["mapping"]["l1_l8_path"],
                    "evidence_event_id": materialized["evidence_event"]["event_id"],
                    "l8_matched_dimension_count": sum(
                        1 for item in materialized["l8_evidence_statuses"] if item["source_status"] == "matched"
                    ),
                    "three_high_total": materialized["three_high_score"]["total_score"],
                })
                if len(payload["preview"]) > 20:
                    payload["preview"] = payload["preview"][:20]

                if not request.persist:
                    continue

                _clear_generated_l8_events_for_mapping(
                    cur,
                    materialized["mapping"]["mapping_id"],
                )

                _persist_business_tag_mapping(cur, materialized["mapping"])
                payload["written"]["business_tag_mapping"] += 1

                _persist_business_tag_evidence_event(cur, materialized["evidence_event"])
                payload["written"]["business_tag_evidence_events"] += 1

                for event in materialized["l8_source_events"]:
                    _persist_business_tag_evidence_event(cur, event)
                    payload["written"]["business_tag_evidence_events"] += 1
                    payload["written"]["business_tag_l8_source_events"] += 1
                    _persist_legacy_company_evidence_event(cur, event)
                    payload["written"]["company_evidence"] += 1

                for status_record in materialized["l8_evidence_statuses"]:
                    _persist_business_tag_l8_evidence_status(cur, status_record)
                    payload["written"]["business_tag_l8_evidence_status"] += 1

                _persist_business_tag_stage(cur, materialized["stage"])
                payload["written"]["business_tag_stage_tracking"] += 1

                if request.include_three_high:
                    _persist_business_tag_three_high_score(cur, materialized["three_high_score"])
                    payload["written"]["business_tag_three_high_scores"] += 1

                _persist_inferred_legacy_company_evidence(cur, materialized)
                payload["written"]["company_evidence"] += 1

                _link_inferred_evidence_to_company_bom_mapping(cur, materialized)
                payload["written"]["company_bom_mapping"] += 1

                if request.include_company_chain_projection and _persist_inferred_company_chain_projection(cur, materialized):
                    payload["written"]["company_chain_mapping"] += 1

            if request.persist:
                pg.commit()
            payload["source_status"] = "ready"
            return payload
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("supply-chain inferred materialization failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Inferred materialization failed: {e}") from e


def _score_business_tag_progress_evidence(approved_events: list[dict[str, Any]]) -> float:
    score = 0.0
    progress_types = {"order", "commercialization", "customer_validation", "capacity", "certification"}
    for event in approved_events:
        evidence_type = str(event.get("evidence_type") or "")
        dimensions = event.get("impact_dimensions") if isinstance(event.get("impact_dimensions"), list) else []
        if evidence_type in progress_types:
            score += 20 + _to_float(event.get("confidence"), 0.0) * 40
        if "growth" in dimensions:
            score += 10
        if "commercialization" in dimensions:
            score += 10
    return round(min(100.0, score), 2)


def _score_business_tag_risk_penalty(approved_events: list[dict[str, Any]]) -> float:
    score = 0.0
    risk_types = {"risk", "delay", "regulatory_risk", "competition", "customer_loss"}
    for event in approved_events:
        evidence_type = str(event.get("evidence_type") or "")
        dimensions = event.get("impact_dimensions") if isinstance(event.get("impact_dimensions"), list) else []
        if evidence_type in risk_types or "risk" in dimensions:
            score += 15 + _to_float(event.get("confidence"), 0.0) * 35
    return round(min(100.0, score), 2)


def _market_expectation_from_mapping(mapping: dict[str, Any]) -> tuple[float, str]:
    explicit_score = _to_float(mapping.get("market_expectation_score"), None)
    if explicit_score is not None:
        return round(min(100.0, max(0.0, explicit_score)), 2), "explicit"
    return 50.0, "neutral_default"


def _calculate_business_tag_expectation_gap_score(
    *,
    mapping: dict[str, Any],
    stage: dict[str, Any],
    events: list[dict[str, Any]],
    trade_date: str | None = None,
) -> dict[str, Any]:
    score_date = (trade_date or datetime.now().date().isoformat())[:10]
    approved_events = _approved_business_tag_events(events)
    evidence_ids = [str(event.get("event_id")) for event in approved_events if event.get("event_id")]

    stage_progress_score = _score_stage_progress(stage)
    evidence_delta_score = _score_business_tag_progress_evidence(approved_events)
    risk_penalty_score = _score_business_tag_risk_penalty(approved_events)
    market_expectation_score, market_expectation_source = _market_expectation_from_mapping(mapping)
    actual_progress_score = round(min(100.0, stage_progress_score * 0.65 + evidence_delta_score * 0.35), 2)

    raw_gap = actual_progress_score - market_expectation_score + evidence_delta_score * 0.35 - risk_penalty_score * 0.45
    expectation_gap_score = round(min(100.0, max(0.0, raw_gap)), 2)
    if raw_gap >= 15:
        gap_type = "positive"
    elif raw_gap <= -15:
        gap_type = "negative"
    else:
        gap_type = "neutral"

    mapping_id = str(mapping.get("mapping_id") or "")
    return {
        "gap_id": f"GAP-{mapping_id}-{score_date}",
        "mapping_id": mapping_id,
        "trade_date": score_date,
        "actual_progress_score": actual_progress_score,
        "market_expectation_score": market_expectation_score,
        "evidence_delta_score": evidence_delta_score,
        "risk_penalty_score": risk_penalty_score,
        "expectation_gap_score": expectation_gap_score,
        "gap_type": gap_type,
        "score_detail": {
            "stage_progress_score": stage_progress_score,
            "market_expectation_source": market_expectation_source,
            "approved_evidence_count": len(approved_events),
            "raw_gap": round(raw_gap, 2),
            "score_unit": "business_tag",
            "formula": "actual_progress - market_expectation + evidence_delta*0.35 - risk_penalty*0.45",
        },
        "evidence_ids": evidence_ids,
    }


def _persist_business_tag_expectation_gap_score(cur, score: dict[str, Any]) -> None:
    cur.execute(
        """
        INSERT INTO business_tag_expectation_gap_scores (
            gap_id, mapping_id, trade_date, actual_progress_score,
            market_expectation_score, evidence_delta_score, risk_penalty_score,
            expectation_gap_score, gap_type, score_detail, evidence_ids
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb)
        ON CONFLICT (mapping_id, trade_date) DO UPDATE SET
            actual_progress_score = EXCLUDED.actual_progress_score,
            market_expectation_score = EXCLUDED.market_expectation_score,
            evidence_delta_score = EXCLUDED.evidence_delta_score,
            risk_penalty_score = EXCLUDED.risk_penalty_score,
            expectation_gap_score = EXCLUDED.expectation_gap_score,
            gap_type = EXCLUDED.gap_type,
            score_detail = EXCLUDED.score_detail,
            evidence_ids = EXCLUDED.evidence_ids
        """,
        (
            score["gap_id"],
            score["mapping_id"],
            score["trade_date"],
            score["actual_progress_score"],
            score["market_expectation_score"],
            score["evidence_delta_score"],
            score["risk_penalty_score"],
            score["expectation_gap_score"],
            score["gap_type"],
            json.dumps(score["score_detail"], ensure_ascii=False),
            json.dumps(score["evidence_ids"], ensure_ascii=False),
        ),
    )


def _score_business_tag_three_high(
    mapping_id: str,
    request: Any,
) -> dict[str, Any]:
    if not mapping_id:
        raise HTTPException(status_code=400, detail="mapping_id is required")
    try:
        with repository.connect() as pg:
            cur = pg.cursor()
            mapping = _query_business_tag_score_mapping_context(cur, mapping_id)
            if not mapping:
                raise HTTPException(status_code=404, detail=f"Business tag mapping '{mapping_id}' not found")
            stage = _query_business_tag_stage_for_score(cur, mapping_id)
            events = _query_business_tag_events_for_score(cur, mapping_id)
            score = _calculate_business_tag_three_high_score(
                mapping=mapping,
                stage=stage,
                events=events,
                trade_date=request.trade_date,
            )
            limitations = []
            persisted = False
            if request.persist:
                if not repository.table_exists(cur, "business_tag_three_high_scores"):
                    raise HTTPException(status_code=503, detail="business_tag_three_high_scores table is missing")
                _persist_business_tag_three_high_score(cur, score)
                pg.commit()
                persisted = True
            if score["score_detail"]["profit_score_status"] == "unavailable":
                limitations.append("缺少业务标签级毛利或毛利占比，高盈利分不可用")
            if not score["score_detail"]["revenue_supported"]:
                limitations.append("缺少业务标签级收入占比，增长分和总分受限")
            return {
                "version": "supply-chain-v2-three-high-score",
                "mapping_id": mapping_id,
                "persisted": persisted,
                "score": score,
                "limitations": limitations,
            }
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("business tag three-high scoring failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Three-high scoring failed: {e}") from e


def _query_business_tag_three_high_score(mapping_id: str) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "version": "supply-chain-v2-three-high-score",
        "mapping_id": mapping_id,
        "source_status": "unknown",
        "score": None,
        "limitations": [],
    }
    if not mapping_id:
        payload["source_status"] = "invalid_mapping_id"
        payload["limitations"].append("mapping_id is empty")
        return payload
    try:
        with repository.connect() as pg:
            cur = pg.cursor()
            if not repository.table_exists(cur, "business_tag_three_high_scores"):
                payload["source_status"] = "score_table_missing"
                payload["limitations"].append("business_tag_three_high_scores table is missing")
                return payload
            cur.execute(
                """
                SELECT score_id, trade_date, growth_score, profit_score, moat_score,
                       stage_score, evidence_score, total_score, score_detail, evidence_ids
                FROM business_tag_three_high_scores
                WHERE mapping_id = %s
                ORDER BY trade_date DESC, created_at DESC
                LIMIT 1
                """,
                (mapping_id,),
            )
            row = cur.fetchone()
            if not row:
                payload["source_status"] = "empty"
                payload["limitations"].append("该业务标签还没有三高评分快照")
                return payload
            payload["source_status"] = "ready"
            payload["score"] = {
                "score_id": str(row[0]),
                "mapping_id": mapping_id,
                "trade_date": str(row[1]) if row[1] else None,
                "growth_score": _to_float(row[2], None),
                "profit_score": _to_float(row[3], None),
                "moat_score": _to_float(row[4], None),
                "stage_score": _to_float(row[5], None),
                "evidence_score": _to_float(row[6], None),
                "total_score": _to_float(row[7], None),
                "score_detail": _json_or_default(row[8], {}),
                "evidence_ids": _json_or_default(row[9], []),
            }
    except Exception as e:
        payload["source_status"] = "degraded"
        payload["error"] = str(e)
        payload["limitations"].append("PostgreSQL three-high score lookup failed")
    return payload


def _score_business_tag_expectation_gap(
    mapping_id: str,
    request: Any,
) -> dict[str, Any]:
    if not mapping_id:
        raise HTTPException(status_code=400, detail="mapping_id is required")
    try:
        with repository.connect() as pg:
            cur = pg.cursor()
            mapping = _query_business_tag_score_mapping_context(cur, mapping_id)
            if not mapping:
                raise HTTPException(status_code=404, detail=f"Business tag mapping '{mapping_id}' not found")
            if request.market_expectation_score is not None:
                mapping["market_expectation_score"] = request.market_expectation_score
            stage = _query_business_tag_stage_for_score(cur, mapping_id)
            events = _query_business_tag_events_for_score(cur, mapping_id)
            score = _calculate_business_tag_expectation_gap_score(
                mapping=mapping,
                stage=stage,
                events=events,
                trade_date=request.trade_date,
            )
            limitations = []
            persisted = False
            if score["score_detail"]["market_expectation_source"] == "neutral_default":
                limitations.append("缺少明确市场预期分，暂用中性 50 分")
            if request.persist:
                if not repository.table_exists(cur, "business_tag_expectation_gap_scores"):
                    raise HTTPException(status_code=503, detail="business_tag_expectation_gap_scores table is missing")
                _persist_business_tag_expectation_gap_score(cur, score)
                pg.commit()
                persisted = True
            return {
                "version": "supply-chain-v2-expectation-gap-score",
                "mapping_id": mapping_id,
                "persisted": persisted,
                "score": score,
                "limitations": limitations,
            }
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("business tag expectation-gap scoring failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Expectation-gap scoring failed: {e}") from e


def _query_business_tag_expectation_gap_score(mapping_id: str) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "version": "supply-chain-v2-expectation-gap-score",
        "mapping_id": mapping_id,
        "source_status": "unknown",
        "score": None,
        "limitations": [],
    }
    if not mapping_id:
        payload["source_status"] = "invalid_mapping_id"
        payload["limitations"].append("mapping_id is empty")
        return payload
    try:
        with repository.connect() as pg:
            cur = pg.cursor()
            if not repository.table_exists(cur, "business_tag_expectation_gap_scores"):
                payload["source_status"] = "gap_table_missing"
                payload["limitations"].append("business_tag_expectation_gap_scores table is missing")
                return payload
            cur.execute(
                """
                SELECT gap_id, trade_date, actual_progress_score, market_expectation_score,
                       evidence_delta_score, risk_penalty_score, expectation_gap_score,
                       gap_type, score_detail, evidence_ids
                FROM business_tag_expectation_gap_scores
                WHERE mapping_id = %s
                ORDER BY trade_date DESC, created_at DESC
                LIMIT 1
                """,
                (mapping_id,),
            )
            row = cur.fetchone()
            if not row:
                payload["source_status"] = "empty"
                payload["limitations"].append("该业务标签还没有预期差评分快照")
                return payload
            payload["source_status"] = "ready"
            payload["score"] = {
                "gap_id": str(row[0]),
                "mapping_id": mapping_id,
                "trade_date": str(row[1]) if row[1] else None,
                "actual_progress_score": _to_float(row[2], None),
                "market_expectation_score": _to_float(row[3], None),
                "evidence_delta_score": _to_float(row[4], None),
                "risk_penalty_score": _to_float(row[5], None),
                "expectation_gap_score": _to_float(row[6], None),
                "gap_type": str(row[7] or ""),
                "score_detail": _json_or_default(row[8], {}),
                "evidence_ids": _json_or_default(row[9], []),
            }
    except Exception as e:
        payload["source_status"] = "degraded"
        payload["error"] = str(e)
        payload["limitations"].append("PostgreSQL expectation-gap score lookup failed")
    return payload


def _normalize_batch_score_types(score_types: list[str]) -> list[str]:
    allowed = {"three_high", "expectation_gap"}
    normalized = []
    for score_type in score_types or []:
        value = str(score_type or "").strip()
        if not value:
            continue
        if value not in allowed:
            raise HTTPException(status_code=400, detail=f"Unsupported score_type '{value}'")
        if value not in normalized:
            normalized.append(value)
    if not normalized:
        raise HTTPException(status_code=400, detail="score_types is empty")
    return normalized


def _query_business_tag_mappings_for_batch_score(
    request: Any,
) -> list[dict[str, Any]]:
    try:
        with repository.connect() as pg:
            cur = pg.cursor()
            if not repository.table_exists(cur, "business_tag_mapping"):
                return []

            where_clauses = ["COALESCE(status, '') <> 'rejected'"]
            params: list[Any] = []
            if request.code:
                normalized_code = str(request.code or "").strip().upper()
                code6 = normalized_code.split(".")[0] if "." in normalized_code else normalized_code
                where_clauses.append("code IN (%s, %s)")
                params.extend([normalized_code, code6])
            if request.node_id:
                where_clauses.append("node_id = %s")
                params.append(request.node_id)
            if request.status:
                where_clauses.append("status = %s")
                params.append(request.status)
            params.append(request.limit)

            cur.execute(
                f"""
                SELECT mapping_id, code, tag_name, node_id, status
                FROM business_tag_mapping
                WHERE {' AND '.join(where_clauses)}
                ORDER BY confidence DESC NULLS LAST, updated_at DESC NULLS LAST
                LIMIT %s
                """,
                tuple(params),
            )
            return [
                {
                    "mapping_id": str(row[0]),
                    "code": str(row[1] or ""),
                    "tag_name": str(row[2] or ""),
                    "node_id": row[3],
                    "status": str(row[4] or ""),
                }
                for row in cur.fetchall()
            ]
    except Exception as e:
        logger.warning("business tag batch-score mapping query failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Batch-score mapping query failed: {e}") from e


def _batch_score_business_tags(
    request: Any,
    *,
    query_mappings=None,
    score_three_high=None,
    score_expectation_gap=None,
) -> dict[str, Any]:
    query_mappings = query_mappings or _query_business_tag_mappings_for_batch_score
    score_three_high = score_three_high or _score_business_tag_three_high
    score_expectation_gap = score_expectation_gap or _score_business_tag_expectation_gap
    score_types = _normalize_batch_score_types(request.score_types)
    mappings = query_mappings(request)
    results = []
    score_count = 0
    error_count = 0
    limitations: list[str] = []

    for mapping in mappings:
        mapping_id = str(mapping.get("mapping_id") or "")
        item = {
            "mapping_id": mapping_id,
            "code": mapping.get("code"),
            "tag_name": mapping.get("tag_name"),
            "node_id": mapping.get("node_id"),
            "status": mapping.get("status"),
            "scores": {},
            "limitations": [],
            "errors": [],
        }
        for score_type in score_types:
            try:
                if score_type == "three_high":
                    score_payload = score_three_high(
                        mapping_id,
                        SimpleNamespace(
                            trade_date=request.trade_date,
                            persist=request.persist,
                        ),
                    )
                else:
                    score_payload = score_expectation_gap(
                        mapping_id,
                        SimpleNamespace(
                            trade_date=request.trade_date,
                            persist=request.persist,
                            market_expectation_score=request.market_expectation_score,
                        ),
                    )
                item["scores"][score_type] = score_payload.get("score")
                item["limitations"].extend(score_payload.get("limitations") or [])
                score_count += 1
            except HTTPException as e:
                error_count += 1
                item["errors"].append({"score_type": score_type, "detail": e.detail})
            except Exception as e:
                error_count += 1
                item["errors"].append({"score_type": score_type, "detail": str(e)})
        results.append(item)

    if not mappings:
        source_status = "empty"
        limitations.append("没有找到符合条件的业务标签映射")
    elif error_count and score_count:
        source_status = "partial_error"
    elif error_count:
        source_status = "error"
    else:
        source_status = "ready"

    return {
        "version": "supply-chain-v2-batch-score",
        "source_status": source_status,
        "score_types": score_types,
        "trade_date": request.trade_date,
        "persisted": request.persist,
        "mapping_count": len(mappings),
        "score_count": score_count,
        "error_count": error_count,
        "results": results,
        "limitations": limitations,
    }


def _l8_dimension_payloads() -> list[dict[str, Any]]:
    return [
        {
            "dimension_id": item["dimension_id"],
            "name": item["name"],
            "evidence_type": item["evidence_type"],
            "keywords": item["keywords"],
        }
        for item in L8_EVIDENCE_DIMENSIONS
    ]


def _matching_l8_dimensions(text: str) -> list[dict[str, Any]]:
    source_text = str(text or "").lower()
    matched = []
    for dimension in L8_EVIDENCE_DIMENSIONS:
        if any(str(keyword).lower() in source_text for keyword in dimension["keywords"]):
            matched.append(dimension)
    return matched


def _l8_source_confidence(source_type: str) -> float:
    return {
        "announcement_body": 0.8,
        "announcement_title": 0.6,
        "research_body": 0.72,
        "research_title": 0.58,
        "irm_qa": 0.55,
        "interact_qa": 0.55,
        "company_business_segment": 0.7,
    }.get(source_type, 0.45)


def _build_l8_source_evidence_events(
    *,
    mapping_id: str,
    mapping: dict[str, Any],
    source: dict[str, Any],
) -> list[dict[str, Any]]:
    title = str(source.get("title") or "")
    excerpt = str(source.get("excerpt") or "")
    source_type = str(source.get("source_type") or "manual")
    text = f"{title} {excerpt}"
    dimensions = _matching_l8_dimensions(text)
    events = []
    for dimension in dimensions:
        event_key = "|".join([
            str(mapping_id),
            str(dimension["dimension_id"]),
            source_type,
            str(source.get("source_id") or ""),
            title,
            excerpt[:120],
        ])
        digest = hashlib.sha1(event_key.encode("utf-8")).hexdigest()[:12]
        events.append({
            "event_id": f"L8-{mapping_id}-{dimension['dimension_id']}-{digest}",
            "mapping_id": mapping_id,
            "code": str(mapping.get("code") or ""),
            "node_id": mapping.get("node_id"),
            "event_date": source.get("event_date"),
            "source_type": source_type,
            "source_id": source.get("source_id"),
            "title": title or dimension["name"],
            "excerpt": excerpt or title,
            "original_url": source.get("original_url"),
            "evidence_type": dimension["evidence_type"],
            "impact_dimensions": dimension["impact_dimensions"],
            "confidence": _to_float(source.get("confidence"), _l8_source_confidence(source_type)),
            "review_status": "pending_review",
            "stage_before": {},
            "stage_after": dimension["stage_after"],
            "l8_dimension_id": dimension["dimension_id"],
            "l8_dimension_name": dimension["name"],
        })
    return events


def _build_l8_evidence_status_records(
    *,
    mapping: dict[str, Any],
    l8_source_events: list[dict[str, Any]],
    trade_date: str | None = None,
) -> list[dict[str, Any]]:
    score_date = (trade_date or datetime.now().date().isoformat())[:10]
    events_by_dimension: dict[str, list[dict[str, Any]]] = {}
    for event in l8_source_events:
        dimension_id = str(event.get("l8_dimension_id") or event.get("evidence_type") or "")
        if dimension_id:
            events_by_dimension.setdefault(dimension_id, []).append(event)

    records = []
    for dimension in L8_EVIDENCE_DIMENSIONS:
        dimension_id = str(dimension["dimension_id"])
        events = events_by_dimension.get(dimension_id, [])
        event_ids = [str(event.get("event_id")) for event in events if event.get("event_id")]
        source_status = "matched" if event_ids else "missing"
        records.append({
            "status_id": f"L8STATUS-{mapping['mapping_id']}-{dimension_id}",
            "mapping_id": mapping["mapping_id"],
            "code": mapping["code"],
            "node_id": mapping.get("node_id"),
            "dimension_id": dimension_id,
            "dimension_name": dimension["name"],
            "source_status": source_status,
            "evidence_event_ids": event_ids,
            "evidence_count": len(event_ids),
            "evidence_summary": (
                f"已匹配 {len(event_ids)} 条{dimension['name']}资料"
                if event_ids
                else f"暂无本地资料命中{dimension['name']}，需补公告、研报、互动问答或主营构成证据"
            ),
            "required_keywords": dimension["keywords"],
            "updated_at": score_date,
        })
    return records


def _inferred_item_name(row: dict[str, Any]) -> str:
    return str(
        row.get("product_name")
        or row.get("material_name")
        or row.get("tag_name")
        or row.get("node_name")
        or row.get("node_id")
        or "AI算力"
    )


def _inferred_l4_name(node_id: str, item_name: str) -> str:
    if node_id == "ai_compute_hardware":
        return "算力硬件"
    if node_id == "ai_compute_software":
        return "基础软件/算力调度"
    if node_id == "ai_compute_application":
        return "行业应用"
    if "硬件" in item_name or any(keyword in item_name for keyword in ("光模块", "芯片", "服务器", "交换机", "数据中心", "PCB")):
        return "算力硬件"
    if any(keyword in item_name for keyword in ("软件", "算法", "操作系统", "数据库", "云服务", "平台", "中间件")):
        return "基础软件/算力调度"
    if any(keyword in item_name for keyword in ("应用", "服务", "解决方案", "智能")):
        return "行业应用"
    return "算力硬件/基础软件/网络互联/行业应用"


def _inferred_l6_name(item_name: str, node_id: str) -> str:
    if "光模块" in item_name:
        return "高速光互联/CPO/LPO"
    if "芯片" in item_name:
        return "AI芯片/GPU/ASIC/光芯片"
    if "服务器" in item_name:
        return "AI服务器/整机集群"
    if "数据中心" in item_name:
        return "智算中心/IDC/液冷基础设施"
    if "交换机" in item_name:
        return "高速交换机/网络互联"
    if "印制电路" in item_name or "PCB" in item_name.upper():
        return "高速PCB/服务器PCB"
    if "算力" in item_name:
        return "算力服务/算力租赁"
    if "操作系统" in item_name:
        return "服务器操作系统/国产操作系统"
    if "数据库" in item_name:
        return "数据库/数据管理"
    if "云服务" in item_name:
        return "云算力/云服务"
    if "算法" in item_name:
        return "AI算法/推理算法"
    if any(keyword in item_name for keyword in ("软件", "中间件", "平台")):
        return "算力调度/AI平台软件"
    if node_id == "ai_compute_application":
        return "行业AI应用/解决方案"
    return "云边端推理/AI算力综合映射"


def _inferred_l7_name(item_name: str, node_id: str) -> str:
    if "光模块" in item_name:
        return "公司业务标签：光模块业务"
    if "芯片" in item_name:
        return "公司业务标签：AI芯片/芯片业务"
    if "服务器" in item_name:
        return "公司业务标签：AI服务器业务"
    if "数据中心" in item_name:
        return "公司业务标签：数据中心/智算中心业务"
    if "交换机" in item_name:
        return "公司业务标签：交换机与网络设备业务"
    if "印制电路" in item_name or "PCB" in item_name.upper():
        return "公司业务标签：PCB与连接材料业务"
    if "算力" in item_name:
        return "公司业务标签：算力服务业务"
    if "操作系统" in item_name:
        return "公司业务标签：操作系统业务"
    if "数据库" in item_name:
        return "公司业务标签：数据库业务"
    if "云服务" in item_name:
        return "公司业务标签：云服务业务"
    if "算法" in item_name:
        return "公司业务标签：AI算法业务"
    if any(keyword in item_name for keyword in ("软件", "中间件", "平台")):
        return "公司业务标签：基础软件/算力调度软件业务"
    if node_id == "ai_compute_application":
        return "公司业务标签：行业AI应用业务"
    return "公司业务标签：AI算力综合业务"


def _build_inferred_l1_l8_path(row: dict[str, Any]) -> list[dict[str, Any]]:
    node_id = str(row.get("node_id") or "")
    chain_id = str(row.get("chain_id") or "")
    item_name = _inferred_item_name(row)
    is_ai_compute = chain_id == "ai_compute" or "ai_compute" in node_id or "AI算力" in item_name
    l2_name = "AI算力" if is_ai_compute else str(row.get("node_name") or item_name)
    return [
        {"layer": "L1", "name": str(row.get("theme_name") or "未来产业主攻方向"), "source": "policy_theme"},
        {"layer": "L2", "name": l2_name, "source": "inferred_direction"},
        {"layer": "L3", "name": f"{l2_name}产业链", "source": "inferred_chain"},
        {"layer": "L4", "name": _inferred_l4_name(node_id, item_name), "source": "inferred_value_segment"},
        {"layer": "L5", "name": item_name, "source": "company_bom_mapping"},
        {"layer": "L6", "name": _inferred_l6_name(item_name, node_id), "source": "rule_inference"},
        {"layer": "L7", "name": _inferred_l7_name(item_name, node_id), "source": "rule_inference"},
        {
            "layer": "L8",
            "name": "证据事件",
            "source": "evidence_requirements",
            "dimensions": _l8_dimension_payloads(),
        },
    ]


def _stage_from_inferred_mapping_status(status: str) -> dict[str, Any]:
    if status == "verified":
        return {
            "research_stage": "R1",
            "commercialization_stage": "C1",
            "stage_reason": "系统根据旧 BOM 映射 verified 状态推导，只能说明业务方向已确认；真实阶段仍需公告、研报或年报原文证据",
            "review_status": "candidate",
        }
    return {
        "research_stage": "R0",
        "commercialization_stage": "C0",
        "stage_reason": "系统仅发现产业链标签映射，未发现足够原文证据确认研发或商业化阶段",
        "review_status": "candidate",
    }


def _inferred_node_bonus(item_name: str) -> float:
    if any(keyword in item_name for keyword in ("光模块", "芯片", "服务器", "数据中心", "交换机")):
        return 15.0
    if any(keyword in item_name for keyword in ("操作系统", "数据库", "云服务", "算法")):
        return 12.0
    if any(keyword in item_name for keyword in ("软件", "平台", "中间件")):
        return 8.0
    return 5.0


def _inferred_moat_bonus(item_name: str) -> float:
    if any(keyword in item_name for keyword in ("芯片", "光模块", "操作系统", "数据库")):
        return 45.0
    if any(keyword in item_name for keyword in ("服务器", "交换机", "数据中心", "算法")):
        return 35.0
    if any(keyword in item_name for keyword in ("云服务", "软件", "平台", "中间件")):
        return 25.0
    return 15.0


def _build_inferred_business_tag_materialization(
    row: dict[str, Any],
    *,
    trade_date: str | None = None,
) -> dict[str, Any]:
    score_date = (trade_date or datetime.now().date().isoformat())[:10]
    mapping_id = str(row.get("mapping_id") or "")
    code = str(row.get("code") or "")
    node_id = str(row.get("node_id") or "")
    status = str(row.get("status") or "pending_review")
    confidence = min(1.0, max(0.0, _to_float(row.get("confidence"), 0.0)))
    item_name = _inferred_item_name(row)
    path = _build_inferred_l1_l8_path(row)
    evidence_id = f"INF-{mapping_id}-L1L8"
    evidence_ids = [evidence_id]
    tag_name = path[6]["name"]
    mapping_keywords = row.get("mapping_keywords") if isinstance(row.get("mapping_keywords"), list) else []
    stage_seed = _stage_from_inferred_mapping_status(status)

    mapping = {
        "mapping_id": mapping_id,
        "code": code,
        "business_segment_id": None,
        "node_id": node_id,
        "theme_id": row.get("theme_id"),
        "chain_id": row.get("chain_id"),
        "tag_name": tag_name,
        "l1_l8_path": path,
        "revenue_ratio": None,
        "gross_profit_ratio": None,
        "confidence": confidence,
        "status": status if status in {"candidate", "pending_review", "weak_evidence", "verified", "rejected"} else "pending_review",
        "evidence_ids": evidence_ids,
    }

    event_confidence = round(min(0.65, max(0.2, confidence)), 4)
    event = {
        "event_id": evidence_id,
        "mapping_id": mapping_id,
        "code": code,
        "node_id": node_id,
        "event_date": score_date,
        "source_type": "rule_inference",
        "source_id": mapping_id,
        "title": f"{row.get('company_name') or code} {tag_name} L1-L8 推导证据",
        "excerpt": (
            f"系统根据 company_bom_mapping 与 supply_chain_bom_nodes 推导："
            f"{' > '.join(item['name'] for item in path)}。"
            "这不是公告或研报原文，只能作为候选证据，后续需要补充客户验证、订单、量产、收入毛利或专利标准等 L8 原始证据。"
        ),
        "original_url": None,
        "evidence_type": "inferred_business_tag",
        "impact_dimensions": ["business_tag", "l1_l8", "three_high"],
        "confidence": event_confidence,
        "review_status": "candidate",
        "stage_before": {},
        "stage_after": {
            "research_stage": stage_seed["research_stage"],
            "commercialization_stage": stage_seed["commercialization_stage"],
        },
    }

    stage = {
        "stage_id": f"STAGE-{mapping_id}-INF",
        "mapping_id": mapping_id,
        "trade_date": score_date,
        "research_stage": stage_seed["research_stage"],
        "commercialization_stage": stage_seed["commercialization_stage"],
        "stage_reason": stage_seed["stage_reason"],
        "source_event_id": evidence_id,
        "last_stage_change_date": score_date,
        "review_status": stage_seed["review_status"],
    }

    growth_score = round(min(60.0, confidence * 45.0 + _inferred_node_bonus(item_name)), 2)
    moat_score = round(min(55.0, _inferred_moat_bonus(item_name) + confidence * 10.0), 2)
    stage_score = _score_stage_progress(stage)
    evidence_score = round(min(30.0, event_confidence * 45.0), 2)
    total_score = round(
        min(
            45.0,
            growth_score * 0.25
            + moat_score * 0.25
            + stage_score * 0.15
            + evidence_score * 0.15,
        ),
        2,
    )
    score = {
        "score_id": f"THREE-HIGH-{mapping_id}-{score_date}",
        "mapping_id": mapping_id,
        "trade_date": score_date,
        "growth_score": growth_score,
        "profit_score": None,
        "moat_score": moat_score,
        "stage_score": stage_score,
        "evidence_score": evidence_score,
        "total_score": total_score,
        "score_detail": {
            "score_unit": "business_tag",
            "source": "rule_inference_baseline",
            "inference_only": True,
            "requires_original_evidence": True,
            "revenue_supported": False,
            "profit_supported": False,
            "profit_score_status": "unavailable",
            "approved_evidence_count": 0,
            "candidate_evidence_count": 1,
            "score_cap": 45.0,
            "mapping_status": status,
            "mapping_source": row.get("mapping_source"),
            "mapping_keywords": mapping_keywords,
        },
        "evidence_ids": evidence_ids,
    }
    l8_statuses = _build_l8_evidence_status_records(
        mapping=mapping,
        l8_source_events=[],
        trade_date=score_date,
    )
    return {
        "mapping": mapping,
        "evidence_event": event,
        "l8_source_events": [],
        "l8_evidence_statuses": l8_statuses,
        "stage": stage,
        "three_high_score": score,
    }


def _score_stage_progress(stage: dict[str, Any]) -> float:
    research_rank = stage_rank(stage.get("research_stage"))
    commercialization_rank = stage_rank(stage.get("commercialization_stage"))
    research_score = min(100.0, research_rank / 6 * 100) if research_rank else 0.0
    commercialization_score = min(100.0, commercialization_rank / 7 * 100) if commercialization_rank else 0.0
    return round(research_score * 0.4 + commercialization_score * 0.6, 2)


def _approved_business_tag_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [event for event in events if str(event.get("review_status") or "") == "approved"]


def _score_business_tag_growth(mapping: dict[str, Any], approved_events: list[dict[str, Any]]) -> float:
    score = 0.0
    revenue_ratio = _to_float(mapping.get("revenue_ratio"), None)
    if revenue_ratio is not None:
        score += min(40.0, max(0.0, revenue_ratio * 100))
    for event in approved_events:
        evidence_type = str(event.get("evidence_type") or "")
        dimensions = event.get("impact_dimensions") if isinstance(event.get("impact_dimensions"), list) else []
        if evidence_type in {"order", "commercialization"}:
            score += 30
        elif evidence_type == "customer_validation":
            score += 15
        if "growth" in dimensions:
            score += 10
    if revenue_ratio is None:
        score = min(score, 75.0)
    return round(min(100.0, score), 2)


def _score_business_tag_profit(mapping: dict[str, Any], approved_events: list[dict[str, Any]]) -> tuple[float | None, str]:
    gross_profit_ratio = _to_float(mapping.get("gross_profit_ratio"), None)
    gross_margin = _to_float(mapping.get("gross_margin"), None)
    if gross_profit_ratio is None and gross_margin is None:
        return None, "unavailable"

    if gross_profit_ratio is not None:
        score = min(100.0, 50.0 + max(0.0, gross_profit_ratio * 100))
        status = "gross_profit_attributed"
    else:
        margin_value = gross_margin * 100 if gross_margin is not None and gross_margin <= 1 else gross_margin
        score = min(75.0, max(0.0, 35.0 + (margin_value or 0)))
        status = "gross_margin_proxy"

    if any("profit" in (event.get("impact_dimensions") or []) for event in approved_events):
        score = min(100.0, score + 10)
    return round(score, 2), status


def _score_business_tag_moat(approved_events: list[dict[str, Any]]) -> float:
    score = 0.0
    moat_types = {"moat", "patent", "certification", "chokepoint", "capacity", "customer_validation"}
    for event in approved_events:
        evidence_type = str(event.get("evidence_type") or "")
        dimensions = event.get("impact_dimensions") if isinstance(event.get("impact_dimensions"), list) else []
        if evidence_type in moat_types or "moat" in dimensions:
            confidence = _to_float(event.get("confidence"), 0.0)
            score += 25 + confidence * 35
    return round(min(100.0, score), 2)


def _score_business_tag_evidence_strength(approved_events: list[dict[str, Any]]) -> float:
    if not approved_events:
        return 0.0
    avg_confidence = sum(_to_float(event.get("confidence"), 0.0) for event in approved_events) / len(approved_events)
    return round(min(100.0, len(approved_events) * 20 + avg_confidence * 60), 2)


def _calculate_business_tag_three_high_score(
    *,
    mapping: dict[str, Any],
    stage: dict[str, Any],
    events: list[dict[str, Any]],
    trade_date: str | None = None,
) -> dict[str, Any]:
    score_date = (trade_date or datetime.now().date().isoformat())[:10]
    approved_events = _approved_business_tag_events(events)
    evidence_ids = [str(event.get("event_id")) for event in approved_events if event.get("event_id")]

    growth_score = _score_business_tag_growth(mapping, approved_events)
    profit_score, profit_status = _score_business_tag_profit(mapping, approved_events)
    moat_score = _score_business_tag_moat(approved_events)
    stage_score = _score_stage_progress(stage)
    evidence_score = _score_business_tag_evidence_strength(approved_events)
    revenue_supported = _to_float(mapping.get("revenue_ratio"), None) is not None
    profit_supported = profit_score is not None

    total_score = (
        growth_score * 0.25
        + (profit_score or 0.0) * 0.20
        + moat_score * 0.25
        + stage_score * 0.15
        + evidence_score * 0.15
    )
    score_cap = 100.0
    if not revenue_supported and not profit_supported:
        score_cap = 65.0
    elif not profit_supported:
        score_cap = 80.0
    total_score = round(min(score_cap, total_score), 2)

    mapping_id = str(mapping.get("mapping_id") or "")
    return {
        "score_id": f"THREE-HIGH-{mapping_id}-{score_date}",
        "mapping_id": mapping_id,
        "trade_date": score_date,
        "growth_score": growth_score,
        "profit_score": profit_score,
        "moat_score": moat_score,
        "stage_score": stage_score,
        "evidence_score": evidence_score,
        "total_score": total_score,
        "score_detail": {
            "revenue_supported": revenue_supported,
            "profit_supported": profit_supported,
            "profit_score_status": profit_status,
            "approved_evidence_count": len(approved_events),
            "score_cap": score_cap,
            "score_unit": "business_tag",
        },
        "evidence_ids": evidence_ids,
    }


L8_EVIDENCE_DIMENSIONS: list[dict[str, Any]] = [
    {
        "dimension_id": "research_progress",
        "name": "研发进展",
        "evidence_type": "research_progress",
        "keywords": ["研发", "开发", "预研", "技术突破", "技术方向", "布局"],
        "impact_dimensions": ["research_stage"],
        "stage_after": {"research_stage": "R1", "commercialization_stage": "C0"},
    },
    {
        "dimension_id": "prototype_delivery",
        "name": "样机或小批量交付",
        "evidence_type": "prototype_delivery",
        "keywords": ["样机", "样品", "送样", "小批量", "试制", "交付"],
        "impact_dimensions": ["research_stage", "commercialization_stage"],
        "stage_after": {"research_stage": "R2", "commercialization_stage": "C1"},
    },
    {
        "dimension_id": "customer_validation",
        "name": "客户验证",
        "evidence_type": "customer_validation",
        "keywords": ["客户验证", "验证", "测试", "认证", "导入", "试用"],
        "impact_dimensions": ["research_stage", "commercialization_stage", "moat"],
        "stage_after": {"research_stage": "R3", "commercialization_stage": "C2"},
    },
    {
        "dimension_id": "order_award",
        "name": "订单或中标",
        "evidence_type": "order_award",
        "keywords": ["订单", "中标", "定点", "合同", "采购", "框架协议"],
        "impact_dimensions": ["commercialization_stage", "growth"],
        "stage_after": {"research_stage": "R5", "commercialization_stage": "C3"},
    },
    {
        "dimension_id": "capacity_mass_production",
        "name": "产线建设或量产",
        "evidence_type": "capacity_mass_production",
        "keywords": ["量产", "产线", "扩产", "投产", "产能", "基地", "出货", "起量", "释放"],
        "impact_dimensions": ["commercialization_stage", "growth", "profit"],
        "stage_after": {"research_stage": "R6", "commercialization_stage": "C5"},
    },
    {
        "dimension_id": "revenue_margin",
        "name": "收入和毛利改善",
        "evidence_type": "revenue_margin",
        "keywords": ["收入", "营收", "毛利", "毛利率", "业绩", "利润", "高增", "增长", "贡献"],
        "impact_dimensions": ["growth", "profit"],
        "stage_after": {},
    },
    {
        "dimension_id": "patent_standard",
        "name": "专利与标准",
        "evidence_type": "patent_standard",
        "keywords": ["专利", "标准", "知识产权", "认证", "壁垒", "独家"],
        "impact_dimensions": ["moat"],
        "stage_after": {},
    },
]


def _persist_business_tag_evidence_event(cur, event: dict[str, Any]) -> None:
    cur.execute(
        """
        INSERT INTO business_tag_evidence_events (
            event_id, mapping_id, code, node_id, event_date, source_type,
            source_id, title, excerpt, original_url, evidence_type,
            impact_dimensions, confidence, review_status, stage_before, stage_after
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s::jsonb, %s::jsonb)
        ON CONFLICT (event_id) DO UPDATE SET
            title = EXCLUDED.title,
            excerpt = EXCLUDED.excerpt,
            original_url = EXCLUDED.original_url,
            evidence_type = EXCLUDED.evidence_type,
            impact_dimensions = EXCLUDED.impact_dimensions,
            confidence = EXCLUDED.confidence,
            stage_after = EXCLUDED.stage_after
        """,
        (
            event["event_id"],
            event["mapping_id"],
            event["code"],
            event["node_id"],
            event["event_date"],
            event["source_type"],
            event["source_id"],
            event["title"],
            event["excerpt"],
            event["original_url"],
            event["evidence_type"],
            json.dumps(event["impact_dimensions"], ensure_ascii=False),
            event["confidence"],
            event["review_status"],
            json.dumps(event["stage_before"], ensure_ascii=False),
            json.dumps(event["stage_after"], ensure_ascii=False),
        ),
    )


def _extract_business_tag_evidence_event(
    mapping_id: str,
    request: Any,
) -> dict[str, Any]:
    if not mapping_id:
        raise HTTPException(status_code=400, detail="mapping_id is required")
    source = {
        "source_type": request.source_type,
        "source_id": request.source_id,
        "title": request.title,
        "excerpt": request.excerpt,
        "original_url": request.original_url,
        "event_date": request.event_date,
        "confidence": request.confidence,
    }

    try:
        with repository.connect() as pg:
            cur = pg.cursor()
            mapping = _query_business_tag_mapping_context(cur, mapping_id)
            if not mapping:
                raise HTTPException(status_code=404, detail=f"Business tag mapping '{mapping_id}' not found")

            event = _infer_business_tag_evidence_event(
                mapping_id=mapping_id,
                mapping=mapping,
                source=source,
            )
            if not request.persist:
                return {
                    "version": "supply-chain-v2-evidence-extract",
                    "mapping_id": mapping_id,
                    "persisted": False,
                    "event": event,
                    "limitations": ["candidate event was not persisted"],
                }

            if not repository.table_exists(cur, "business_tag_evidence_events"):
                raise HTTPException(status_code=503, detail="business_tag_evidence_events table is missing")

            _persist_business_tag_evidence_event(cur, event)
            pg.commit()
            return {
                "version": "supply-chain-v2-evidence-extract",
                "mapping_id": mapping_id,
                "persisted": True,
                "event": event,
                "limitations": ["candidate evidence requires review before scoring or stage confirmation"],
            }
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("business tag evidence extraction failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Evidence extraction failed: {e}") from e


def _batch_extract_business_tag_evidence(
    request: Any,
) -> dict[str, Any]:
    safe_limit = max(1, min(int(request.limit or 50), 500))
    source_types = [str(item) for item in (request.source_types or []) if str(item).strip()]
    payload: dict[str, Any] = {
        "version": "supply-chain-v2-evidence-batch-extract",
        "source_status": "unknown",
        "mapping_count": 0,
        "candidate_source_count": 0,
        "created_event_count": 0,
        "events": [],
        "limitations": [],
    }
    if not request.mapping_id and not request.code:
        raise HTTPException(status_code=400, detail="mapping_id or code is required")
    try:
        with repository.connect() as pg:
            cur = pg.cursor()
            mappings = _query_business_tag_mappings_for_batch(cur, request)
            payload["mapping_count"] = len(mappings)
            if not mappings:
                payload["source_status"] = "mapping_not_found"
                payload["limitations"].append("未找到业务标签映射，无法抽取证据")
                return payload
            if request.persist and not repository.table_exists(cur, "business_tag_evidence_events"):
                raise HTTPException(status_code=503, detail="business_tag_evidence_events table is missing")

            seen_event_ids: set[str] = set()
            for mapping in mappings:
                sources = _query_candidate_sources_for_mapping(cur, mapping, source_types, safe_limit)
                payload["candidate_source_count"] += len(sources)
                for source in sources:
                    event = _infer_business_tag_evidence_event(
                        mapping_id=str(mapping["mapping_id"]),
                        mapping=mapping,
                        source=source,
                    )
                    if event["event_id"] in seen_event_ids:
                        continue
                    seen_event_ids.add(event["event_id"])
                    if request.persist:
                        _persist_business_tag_evidence_event(cur, event)
                    payload["events"].append(event)
                    if len(payload["events"]) >= safe_limit:
                        break
                if len(payload["events"]) >= safe_limit:
                    break

            if request.persist:
                pg.commit()
            payload["created_event_count"] = len(payload["events"])
            payload["source_status"] = "ok"
            if request.persist:
                payload["limitations"].append("批量抽取生成的证据均为 pending_review，审核通过前不进入阶段和评分")
            else:
                payload["limitations"].append("本次只预览候选证据，未写入数据库")
            return payload
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("business tag batch evidence extraction failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Batch evidence extraction failed: {e}") from e


def _query_business_tag_mappings_for_batch(
    cur,
    request: Any,
) -> list[dict[str, Any]]:
    if request.mapping_id:
        mapping = _query_business_tag_mapping_context(cur, request.mapping_id)
        return [mapping] if mapping else []

    normalized_code = str(request.code or "").strip().upper()
    code6 = normalized_code.split(".")[0] if "." in normalized_code else normalized_code
    if not code6:
        return []

    mappings: list[dict[str, Any]] = []
    if repository.table_exists(cur, "business_tag_mapping"):
        cur.execute(
            """
            SELECT mapping_id, code, node_id, tag_name, theme_id, chain_id, l1_l8_path, status
            FROM business_tag_mapping
            WHERE code IN (%s, %s)
            ORDER BY confidence DESC, updated_at DESC
            LIMIT 100
            """,
            (normalized_code, code6),
        )
        for row in cur.fetchall():
            mappings.append({
                "mapping_id": str(row[0]),
                "code": str(row[1] or ""),
                "node_id": row[2],
                "tag_name": row[3],
                "theme_id": row[4],
                "chain_id": row[5],
                "l1_l8_path": _json_or_default(row[6], []),
                "status": row[7],
                "source": "business_tag_mapping",
            })
    if mappings or not repository.table_exists(cur, "company_bom_mapping"):
        return mappings

    cur.execute(
        """
        SELECT
            m.mapping_id,
            m.code,
            m.node_id,
            COALESCE(n.name, m.product_name, m.material_name, m.node_id) AS tag_name,
            n.theme_id,
            n.chain_id,
            m.status
        FROM company_bom_mapping m
        LEFT JOIN supply_chain_bom_nodes n ON n.node_id = m.node_id
        WHERE m.code IN (%s, %s)
        ORDER BY m.confidence DESC, m.updated_at DESC NULLS LAST
        LIMIT 100
        """,
        (normalized_code, code6),
    )
    for row in cur.fetchall():
        mappings.append({
            "mapping_id": str(row[0]),
            "code": str(row[1] or ""),
            "node_id": row[2],
            "tag_name": row[3],
            "theme_id": row[4],
            "chain_id": row[5],
            "l1_l8_path": [],
            "status": row[6],
            "source": "company_bom_mapping",
        })
    return mappings


def _first_existing_column(cur, table_name: str, columns: list[str]) -> str | None:
    for column in columns:
        if repository.column_exists(cur, table_name, column):
            return column
    return None


def _code_variants(code: str) -> list[str]:
    code_value = str(code or "").strip().upper()
    code6 = code_value.split(".")[0] if "." in code_value else code_value
    variants = [code_value, code6]
    if code6 and "." not in code_value:
        variants.extend([f"{code6}.SZ", f"{code6}.SH"])
    return sorted({item for item in variants if item})


def _query_candidate_sources_from_table(
    cur,
    *,
    table_name: str,
    source_type: str,
    code: str,
    limit: int,
    title_columns: list[str],
    excerpt_columns: list[str],
    date_columns: list[str],
    source_id_columns: list[str],
    url_columns: list[str] | None = None,
) -> list[dict[str, Any]]:
    if not repository.table_exists(cur, table_name):
        return []
    code_column = _first_existing_column(cur, table_name, ["code", "ts_code", "symbol", "stock_code"])
    title_column = _first_existing_column(cur, table_name, title_columns)
    if not title_column:
        return []
    excerpt_column = _first_existing_column(cur, table_name, excerpt_columns)
    date_column = _first_existing_column(cur, table_name, date_columns)
    source_id_column = _first_existing_column(cur, table_name, source_id_columns)
    url_column = _first_existing_column(cur, table_name, url_columns or ["url", "source_url"])

    select_parts = [
        f'"{title_column}" AS title',
        f'"{excerpt_column}" AS excerpt' if excerpt_column else "NULL AS excerpt",
        f'"{date_column}" AS event_date' if date_column else "NULL AS event_date",
        f'"{source_id_column}" AS source_id' if source_id_column else "NULL AS source_id",
        f'"{url_column}" AS original_url' if url_column else "NULL AS original_url",
    ]
    where_parts = [f'"{title_column}" IS NOT NULL']
    params: list[Any] = []
    if code_column:
        variants = _code_variants(code)
        where_parts.append(f'"{code_column}" = ANY(%s)')
        params.append(variants)
    order_sql = f'ORDER BY "{date_column}" DESC NULLS LAST' if date_column else ""
    params.append(limit)
    cur.execute(
        f"""
        SELECT {", ".join(select_parts)}
        FROM "{table_name}"
        WHERE {" AND ".join(where_parts)}
        {order_sql}
        LIMIT %s
        """,
        params,
    )
    rows = cur.fetchall()
    sources = []
    for row in rows:
        sources.append({
            "source_type": source_type,
            "title": str(row[0] or ""),
            "excerpt": str(row[1] or ""),
            "event_date": str(row[2])[:10] if row[2] else None,
            "source_id": str(row[3] or ""),
            "original_url": row[4],
        })
    return sources


def _query_candidate_sources_for_mapping(
    cur,
    mapping: dict[str, Any],
    source_types: list[str],
    limit: int,
) -> list[dict[str, Any]]:
    code = str(mapping.get("code") or "")
    sources: list[dict[str, Any]] = []
    if "announcement_title" in source_types:
        sources.extend(_query_candidate_sources_from_table(
            cur,
            table_name="announcements",
            source_type="announcement_title",
            code=code,
            limit=limit,
            title_columns=["title", "ann_title", "name"],
            excerpt_columns=["content", "summary"],
            date_columns=["ann_date", "trade_date", "date", "publish_time"],
            source_id_columns=["announcement_id", "ann_id", "id"],
            url_columns=["url", "source_url"],
        ))
    if "research_title" in source_types:
        sources.extend(_query_candidate_sources_from_table(
            cur,
            table_name="research_reports_tushare",
            source_type="research_title",
            code=code,
            limit=limit,
            title_columns=["title", "report_title", "name"],
            excerpt_columns=["summary", "abstract"],
            date_columns=["report_date", "ann_date", "date"],
            source_id_columns=["report_id", "id"],
            url_columns=["url", "source_url"],
        ))
    if "interact_qa" in source_types:
        sources.extend(_query_candidate_sources_from_table(
            cur,
            table_name="interact_qa",
            source_type="interact_qa",
            code=code,
            limit=limit,
            title_columns=["question", "title"],
            excerpt_columns=["answer", "content"],
            date_columns=["pub_date", "trade_date", "date", "created_at"],
            source_id_columns=["qa_id", "id"],
            url_columns=["url", "source_url"],
        ))
    if "irm_qa" in source_types:
        for table_name in ("ts_raw_irm_qa_sh", "ts_raw_irm_qa_sz"):
            sources.extend(_query_candidate_sources_from_table(
                cur,
                table_name=table_name,
                source_type="irm_qa",
                code=code,
                limit=limit,
                title_columns=["question", "title", "q"],
                excerpt_columns=["answer", "content", "a"],
                date_columns=["pub_date", "trade_date", "date", "created_at"],
                source_id_columns=["qa_id", "id", "_row_hash"],
                url_columns=["url", "source_url"],
            ))
    matched = [source for source in sources if _source_record_matches_mapping(source, mapping)]
    return matched[:limit]


def _default_business_tag_stage(mapping_id: str, evidence_count: int = 0) -> dict[str, Any]:
    return {
        "version": "supply-chain-v2-stage",
        "mapping_id": mapping_id,
        "source": None,
        "source_status": "empty",
        "current_stage": {
            "research_stage": "R0",
            "commercialization_stage": "C0",
            "stage_reason": "没有结构化阶段证据，维持默认阶段并等待复核",
            "stage_confirmed": False,
            "review_status": "pending_review",
            "source_event_id": None,
        },
        "history": [],
        "evidence_event_count": evidence_count,
        "stage_gate": {
            "stage_change_requires_evidence": True,
            "approved_event_required_for_confirmed_stage": True,
            "interaction_or_legacy_evidence_can_only_pending_review": True,
        },
        "limitations": [],
    }


def _stage_from_evidence_events(events: list[dict[str, Any]]) -> dict[str, Any]:
    for event in events:
        if str(event.get("review_status") or "") != "approved":
            continue
        stage_after = event.get("stage_after") if isinstance(event.get("stage_after"), dict) else {}
        research_stage = str(stage_after.get("research_stage") or stage_after.get("research") or "R0")
        commercialization_stage = str(
            stage_after.get("commercialization_stage")
            or stage_after.get("commercialization")
            or "C0"
        )
        if research_stage == "R0" and commercialization_stage == "C0":
            continue
        return {
            "research_stage": research_stage,
            "commercialization_stage": commercialization_stage,
            "stage_reason": event.get("title") or event.get("excerpt") or "已审核证据事件触发阶段变化",
            "stage_confirmed": True,
            "review_status": "approved",
            "source_event_id": event.get("event_id"),
        }
    return {
        "research_stage": "R0",
        "commercialization_stage": "C0",
        "stage_reason": "没有已审核阶段证据，维持默认阶段并等待复核",
        "stage_confirmed": False,
        "review_status": "pending_review",
        "source_event_id": None,
    }


def _stage_record_from_reviewed_event(
    event: dict[str, Any],
    *,
    review_status: str,
) -> dict[str, Any] | None:
    if review_status != "approved":
        return None
    stage_after = event.get("stage_after") if isinstance(event.get("stage_after"), dict) else {}
    research_stage = str(stage_after.get("research_stage") or stage_after.get("research") or "R0")
    commercialization_stage = str(
        stage_after.get("commercialization_stage")
        or stage_after.get("commercialization")
        or "C0"
    )
    if research_stage == "R0" and commercialization_stage == "C0":
        return None

    mapping_id = str(event.get("mapping_id") or "")
    event_id = str(event.get("event_id") or "")
    event_date = str(event.get("event_date") or datetime.now().date().isoformat())[:10]
    return {
        "stage_id": f"STAGE-{mapping_id}-{event_id}",
        "mapping_id": mapping_id,
        "trade_date": event_date,
        "research_stage": research_stage,
        "commercialization_stage": commercialization_stage,
        "stage_reason": event.get("title") or event.get("excerpt") or "已审核证据事件触发阶段变化",
        "source_event_id": event_id,
        "last_stage_change_date": event_date,
        "review_status": review_status,
    }


def _infer_business_tag_evidence_event(
    *,
    mapping_id: str,
    mapping: dict[str, Any],
    source: dict[str, Any],
) -> dict[str, Any]:
    title = str(source.get("title") or "")
    excerpt = str(source.get("excerpt") or "")
    text = f"{title} {excerpt}".lower()

    if any(keyword in text for keyword in ("订单", "中标", "定点", "小批量")):
        evidence_type = "order"
        impact_dimensions = ["commercialization_stage", "growth"]
        stage_after = {"research_stage": "R5", "commercialization_stage": "C3"}
    elif any(keyword in text for keyword in ("客户验证", "验证", "测试", "样品")):
        evidence_type = "customer_validation"
        impact_dimensions = ["research_stage", "commercialization_stage"]
        stage_after = {"research_stage": "R3", "commercialization_stage": "C2"}
    elif any(keyword in text for keyword in ("量产", "规模化", "规模推广")):
        evidence_type = "commercialization"
        impact_dimensions = ["commercialization_stage", "growth", "profit"]
        stage_after = {"research_stage": "R6", "commercialization_stage": "C5"}
    elif any(keyword in text for keyword in ("专利", "认证", "壁垒", "独家")):
        evidence_type = "moat"
        impact_dimensions = ["moat"]
        stage_after = {}
    elif any(keyword in text for keyword in ("研发", "开发", "立项")):
        evidence_type = "research_progress"
        impact_dimensions = ["research_stage"]
        stage_after = {"research_stage": "R1", "commercialization_stage": "C0"}
    else:
        evidence_type = "business_mention"
        impact_dimensions = ["business_tag"]
        stage_after = {}

    source_type = str(source.get("source_type") or "manual")
    base_confidence = {
        "announcement_body": 0.8,
        "announcement_title": 0.55,
        "research_body": 0.7,
        "research_title": 0.5,
        "irm_qa": 0.45,
        "manual": 0.6,
    }.get(source_type, 0.4)
    confidence = _to_float(source.get("confidence"), base_confidence)
    event_key = "|".join([
        str(mapping_id),
        source_type,
        str(source.get("source_id") or ""),
        title,
        excerpt[:80],
    ])
    digest = hashlib.sha1(event_key.encode("utf-8")).hexdigest()[:12]
    return {
        "event_id": f"EV-{mapping_id}-{digest}",
        "mapping_id": mapping_id,
        "code": str(mapping.get("code") or ""),
        "node_id": mapping.get("node_id"),
        "event_date": source.get("event_date"),
        "source_type": source_type,
        "source_id": source.get("source_id"),
        "title": title,
        "excerpt": excerpt,
        "original_url": source.get("original_url"),
        "evidence_type": evidence_type,
        "impact_dimensions": impact_dimensions,
        "confidence": confidence,
        "review_status": "pending_review",
        "stage_before": {},
        "stage_after": stage_after,
    }


def _mapping_text_terms(mapping: dict[str, Any]) -> set[str]:
    raw_terms: list[Any] = [
        mapping.get("tag_name"),
        mapping.get("node_id"),
        mapping.get("theme_id"),
        mapping.get("chain_id"),
    ]
    path = mapping.get("l1_l8_path") if isinstance(mapping.get("l1_l8_path"), list) else []
    for item in path:
        if isinstance(item, dict):
            raw_terms.extend([item.get("name"), item.get("display_name")])
        else:
            raw_terms.append(item)
    terms = set()
    for term in raw_terms:
        value = str(term or "").strip().lower()
        if len(value) >= 2:
            terms.add(value)
    return terms


def _source_record_matches_mapping(source: dict[str, Any], mapping: dict[str, Any]) -> bool:
    text = f"{source.get('title') or ''} {source.get('excerpt') or ''}".lower()
    if not text.strip():
        return False
    terms = _mapping_text_terms(mapping)
    if terms and any(term in text for term in terms):
        return True
    evidence_keywords = ("客户验证", "订单", "中标", "定点", "量产", "小批量", "专利", "认证", "研发", "样品")
    return not terms and any(keyword in text for keyword in evidence_keywords)


def _query_business_tag_mapping_context(cur, mapping_id: str) -> dict[str, Any] | None:
    if repository.table_exists(cur, "business_tag_mapping"):
        cur.execute(
            """
            SELECT mapping_id, code, node_id, tag_name, theme_id, chain_id, l1_l8_path, status
            FROM business_tag_mapping
            WHERE mapping_id = %s
            LIMIT 1
            """,
            (mapping_id,),
        )
        row = cur.fetchone()
        if row:
            return {
                "mapping_id": str(row[0]),
                "code": str(row[1] or ""),
                "node_id": row[2],
                "tag_name": row[3],
                "theme_id": row[4],
                "chain_id": row[5],
                "l1_l8_path": _json_or_default(row[6], []),
                "status": row[7],
                "source": "business_tag_mapping",
            }

    if repository.table_exists(cur, "company_bom_mapping"):
        cur.execute(
            """
            SELECT
                m.mapping_id,
                m.code,
                m.node_id,
                COALESCE(n.name, m.product_name, m.material_name, m.node_id) AS tag_name,
                n.theme_id,
                n.chain_id,
                m.status
            FROM company_bom_mapping m
            LEFT JOIN supply_chain_bom_nodes n ON n.node_id = m.node_id
            WHERE m.mapping_id = %s
            LIMIT 1
            """,
            (mapping_id,),
        )
        row = cur.fetchone()
        if row:
            return {
                "mapping_id": str(row[0]),
                "code": str(row[1] or ""),
                "node_id": row[2],
                "tag_name": row[3],
                "theme_id": row[4],
                "chain_id": row[5],
                "l1_l8_path": [],
                "status": row[6],
                "source": "company_bom_mapping",
            }
    return None


def _empty_business_tag_evidence_payload(mapping_id: str) -> dict[str, Any]:
    return {
        "version": "supply-chain-v2-evidence",
        "mapping_id": mapping_id,
        "source": None,
        "source_status": "unknown",
        "mapping": None,
        "event_count": 0,
        "events": [],
        "review_gate": {
            "approved_events_enter_scoring": True,
            "pending_events_only_update_observation": True,
            "market_concept_only_caps_pool": "观察池",
        },
        "limitations": [],
    }


def _map_business_tag_event_row(row) -> dict[str, Any]:
    return {
        "event_id": str(row[0]),
        "code": str(row[1] or ""),
        "node_id": row[2],
        "event_date": str(row[3]) if row[3] else None,
        "source_type": str(row[4] or ""),
        "source_id": row[5],
        "title": row[6],
        "excerpt": row[7],
        "original_url": row[8],
        "evidence_type": str(row[9] or ""),
        "impact_dimensions": _json_or_default(row[10], []),
        "confidence": _to_float(row[11], 0.0),
        "review_status": str(row[12] or "pending_review"),
        "stage_before": _json_or_default(row[13], {}),
        "stage_after": _json_or_default(row[14], {}),
        "created_at": str(row[15]) if row[15] else None,
    }


def query_business_tag_evidence(mapping_id: str) -> dict[str, Any]:
    payload = _empty_business_tag_evidence_payload(mapping_id)
    if not mapping_id:
        payload["source_status"] = "invalid_mapping_id"
        payload["limitations"].append("mapping_id is empty")
        return payload

    try:
        with repository.connect() as pg:
            cur = pg.cursor()
            mapping = _query_business_tag_mapping_context(cur, mapping_id)

            if repository.table_exists(cur, "business_tag_evidence_events"):
                cur.execute(
                    """
                    SELECT event_id, code, node_id, event_date, source_type, source_id,
                           title, excerpt, original_url, evidence_type, impact_dimensions,
                           confidence, review_status, stage_before, stage_after, created_at
                    FROM business_tag_evidence_events
                    WHERE mapping_id = %s
                    ORDER BY event_date DESC NULLS LAST, created_at DESC
                    LIMIT 200
                    """,
                    (mapping_id,),
                )
                rows = cur.fetchall()
                if rows:
                    events = [_map_business_tag_event_row(row) for row in rows]
                    payload.update({
                        "source": "business_tag_evidence_events",
                        "source_status": "ready",
                        "mapping": mapping,
                        "event_count": len(events),
                        "events": events,
                    })
                    return payload

            if not mapping:
                payload["source_status"] = "mapping_not_found"
                payload["limitations"].append("未找到业务标签映射，无法归集证据")
                return payload

            payload["mapping"] = mapping
            if not repository.table_exists(cur, "company_evidence"):
                payload["source_status"] = "empty"
                payload["limitations"].append("company_evidence table is missing")
                return payload

            cur.execute(
                """
                SELECT evidence_id, code, node_id, source_id, evidence_type,
                       summary, excerpt, confidence, evidence_date, status
                FROM company_evidence
                WHERE code = %s
                  AND (node_id = %s OR node_id IS NULL)
                ORDER BY evidence_date DESC NULLS LAST
                LIMIT 200
                """,
                (mapping["code"], mapping.get("node_id")),
            )
            rows = cur.fetchall()
            events = [
                {
                    "event_id": str(row[0]),
                    "mapping_id": mapping_id,
                    "code": str(row[1] or ""),
                    "node_id": row[2],
                    "event_date": str(row[8]) if row[8] else None,
                    "source_type": "company_evidence",
                    "source_id": row[3],
                    "title": row[5],
                    "excerpt": row[6],
                    "original_url": None,
                    "evidence_type": str(row[4] or ""),
                    "impact_dimensions": ["business_tag", "stage", "three_high"],
                    "confidence": _to_float(row[7], 0.0),
                    "review_status": "approved" if str(row[9] or "") == "approved" else "pending_review",
                    "stage_before": {},
                    "stage_after": {},
                    "legacy_status": row[9],
                }
                for row in rows
            ]
            payload.update({
                "source": "company_evidence",
                "source_status": "legacy_fallback" if events else "empty",
                "event_count": len(events),
                "events": events,
                "limitations": [
                    "旧 company_evidence 未绑定 business_tag_evidence_events，不能直接进入正式阶段变化",
                ] if events else [],
            })
    except Exception as e:
        payload["source_status"] = "degraded"
        payload["error"] = str(e)
        payload["limitations"].append("PostgreSQL evidence lookup failed")
    return payload


def business_tag_score_status(revenue_ratio: float | None, gross_profit_ratio: float | None, evidence_count: int) -> str:
    if revenue_ratio is not None and gross_profit_ratio is not None and evidence_count > 0:
        return "scorable"
    if revenue_ratio is not None and evidence_count > 0:
        return "profit_insufficient"
    if evidence_count > 0:
        return "evidence_only"
    return "insufficient_business_data"


def query_company_business_tags(code: str) -> dict[str, Any]:
    normalized_code = str(code or "").strip().upper()
    code6 = normalized_code.split(".")[0] if "." in normalized_code else normalized_code
    payload: dict[str, Any] = {
        "code": normalized_code,
        "normalized_code": code6,
        "version": "supply-chain-v2-business-tags",
        "source": None,
        "source_status": "unknown",
        "tag_count": 0,
        "tags": [],
        "limitations": [],
    }
    if not code6:
        payload["source_status"] = "invalid_code"
        payload["limitations"].append("code is empty")
        return payload

    try:
        with repository.connect() as pg:
            cur = pg.cursor()
            if repository.table_exists(cur, "business_tag_mapping"):
                cur.execute(
                    """
                    SELECT
                        m.mapping_id,
                        m.code,
                        m.tag_name,
                        m.node_id,
                        m.theme_id,
                        m.chain_id,
                        m.l1_l8_path,
                        m.revenue_ratio,
                        m.gross_profit_ratio,
                        m.confidence,
                        m.status,
                        s.segment_name,
                        s.revenue,
                        s.gross_margin,
                        st.research_stage,
                        st.commercialization_stage,
                        st.stage_reason,
                        sc.growth_score,
                        sc.profit_score,
                        sc.moat_score,
                        sc.total_score,
                        eg.expectation_gap_score,
                        eg.gap_type,
                        COALESCE(ev.event_count, 0) AS evidence_count,
                        COALESCE(l8.l8_statuses, '[]'::jsonb) AS l8_evidence_status
                    FROM business_tag_mapping m
                    LEFT JOIN company_business_segments s ON s.segment_id = m.business_segment_id
                    LEFT JOIN LATERAL (
                        SELECT research_stage, commercialization_stage, stage_reason
                        FROM business_tag_stage_tracking
                        WHERE mapping_id = m.mapping_id
                        ORDER BY trade_date DESC
                        LIMIT 1
                    ) st ON TRUE
                    LEFT JOIN LATERAL (
                        SELECT growth_score, profit_score, moat_score, total_score
                        FROM business_tag_three_high_scores
                        WHERE mapping_id = m.mapping_id
                        ORDER BY trade_date DESC
                        LIMIT 1
                    ) sc ON TRUE
                    LEFT JOIN LATERAL (
                        SELECT expectation_gap_score, gap_type
                        FROM business_tag_expectation_gap_scores
                        WHERE mapping_id = m.mapping_id
                        ORDER BY trade_date DESC
                        LIMIT 1
                    ) eg ON TRUE
                    LEFT JOIN LATERAL (
                        SELECT COUNT(*) AS event_count
                        FROM business_tag_evidence_events
                        WHERE mapping_id = m.mapping_id
                    ) ev ON TRUE
                    LEFT JOIN LATERAL (
                        SELECT jsonb_agg(
                            jsonb_build_object(
                                'dimension_id', dimension_id,
                                'dimension_name', dimension_name,
                                'source_status', source_status,
                                'evidence_event_ids', evidence_event_ids,
                                'evidence_count', evidence_count,
                                'evidence_summary', evidence_summary,
                                'required_keywords', required_keywords,
                                'updated_at', updated_at
                            )
                            ORDER BY CASE dimension_id
                                WHEN 'research_progress' THEN 1
                                WHEN 'prototype_delivery' THEN 2
                                WHEN 'customer_validation' THEN 3
                                WHEN 'order_award' THEN 4
                                WHEN 'capacity_mass_production' THEN 5
                                WHEN 'revenue_margin' THEN 6
                                WHEN 'patent_standard' THEN 7
                                ELSE 99
                            END
                        ) AS l8_statuses
                        FROM business_tag_l8_evidence_status
                        WHERE mapping_id = m.mapping_id
                    ) l8 ON TRUE
                    WHERE m.code IN (%s, %s)
                    ORDER BY COALESCE(sc.total_score, 0) DESC, m.confidence DESC
                    LIMIT 100
                    """,
                    (normalized_code, code6),
                )
                rows = cur.fetchall()
                if rows:
                    tags = []
                    for row in rows:
                        revenue_ratio = _to_float(row[7], None)
                        gross_profit_ratio = _to_float(row[8], None)
                        commercialization_stage = str(row[15] or "C0")
                        evidence_count = int(row[23] or 0)
                        score_status = business_tag_score_status(revenue_ratio, gross_profit_ratio, evidence_count)
                        tags.append({
                            "mapping_id": str(row[0]),
                            "code": str(row[1]),
                            "tag_name": str(row[2] or ""),
                            "node_id": row[3],
                            "theme_id": row[4],
                            "chain_id": row[5],
                            "l1_l8_path": _json_or_default(row[6], []),
                            "business_segment": {
                                "name": row[11],
                                "revenue": _to_float(row[12], None),
                                "gross_margin": _to_float(row[13], None),
                            },
                            "attribution": {
                                "revenue_ratio": revenue_ratio,
                                "gross_profit_ratio": gross_profit_ratio,
                                "score_status": score_status,
                            },
                            "stage": {
                                "research_stage": str(row[14] or "R0"),
                                "commercialization_stage": commercialization_stage,
                                "stage_reason": row[16],
                            },
                            "three_high_scores": {
                                "growth": _to_float(row[17], None),
                                "profit": _to_float(row[18], None),
                                "moat": _to_float(row[19], None),
                                "total": _to_float(row[20], None),
                                "score_status": score_status,
                            },
                            "expectation_gap": {
                                "score": _to_float(row[21], None),
                                "gap_type": row[22],
                            },
                            "evidence_summary": {"event_count": evidence_count},
                            "l8_evidence_status": _json_or_default(row[24], []),
                            "confidence": _to_float(row[9], 0.0),
                            "status": str(row[10] or "pending_review"),
                            "pool": pool_for_business_tag(str(row[10] or "pending_review"), revenue_ratio, commercialization_stage, evidence_count),
                        })
                    payload.update({
                        "source": "business_tag_mapping",
                        "source_status": "ready",
                        "tag_count": len(tags),
                        "tags": tags,
                    })
                    return payload

            if not repository.table_exists(cur, "company_bom_mapping"):
                payload["source_status"] = "missing_mapping_table"
                payload["limitations"].append("company_bom_mapping table is missing")
                return payload

            has_company_evidence = repository.table_exists(cur, "company_evidence")
            evidence_join = """
                LEFT JOIN LATERAL (
                    SELECT COUNT(*) AS evidence_count
                    FROM company_evidence e
                    WHERE e.code IN (%s, %s)
                      AND (e.node_id = m.node_id OR e.node_id IS NULL)
                ) ev ON TRUE
            """ if has_company_evidence else "LEFT JOIN LATERAL (SELECT 0 AS evidence_count) ev ON TRUE"
            fallback_sql = f"""
                SELECT
                    m.mapping_id,
                    m.code,
                    m.node_id,
                    m.product_name,
                    m.material_name,
                    m.confidence,
                    m.status,
                    m.evidence_ids,
                    n.name,
                    n.theme_id,
                    n.chain_id,
                    n.level,
                    t.name AS theme_name,
                    COALESCE(ev.evidence_count, 0) AS evidence_count
                FROM company_bom_mapping m
                LEFT JOIN supply_chain_bom_nodes n ON n.node_id = m.node_id
                LEFT JOIN policy_themes t ON t.theme_id = n.theme_id
                {evidence_join}
                WHERE m.code IN (%s, %s)
                ORDER BY m.confidence DESC, m.updated_at DESC NULLS LAST
                LIMIT 100
            """
            params = (normalized_code, code6, normalized_code, code6) if has_company_evidence else (normalized_code, code6)
            cur.execute(fallback_sql, params)
            rows = cur.fetchall()
            tags = []
            for row in rows:
                evidence_count = int(row[13] or 0)
                tag_name = str(row[8] or row[3] or row[4] or row[2] or "")
                status = str(row[6] or "pending_review")
                tags.append({
                    "mapping_id": str(row[0]),
                    "code": str(row[1]),
                    "tag_name": tag_name,
                    "node_id": row[2],
                    "theme_id": row[9],
                    "chain_id": row[10],
                    "l1_l8_path": [
                        {"layer": "L1", "name": row[12]},
                        {"layer": "L5", "name": row[8], "level": row[11]},
                    ],
                    "business_segment": {
                        "name": row[3] or row[4],
                        "revenue": None,
                        "gross_margin": None,
                    },
                    "attribution": {
                        "revenue_ratio": None,
                        "gross_profit_ratio": None,
                        "score_status": business_tag_score_status(None, None, evidence_count),
                    },
                    "stage": {
                        "research_stage": "R0",
                        "commercialization_stage": "C0",
                        "stage_reason": "旧 BOM 映射未结构化阶段，需由证据事件确认",
                    },
                    "three_high_scores": {
                        "growth": None,
                        "profit": None,
                        "moat": None,
                        "total": None,
                        "score_status": business_tag_score_status(None, None, evidence_count),
                    },
                    "expectation_gap": {
                        "score": None,
                        "gap_type": None,
                    },
                    "evidence_summary": {
                        "event_count": evidence_count,
                        "legacy_evidence_ids": _json_or_default(row[7], []),
                    },
                    "confidence": _to_float(row[5], 0.0),
                    "status": status,
                    "pool": pool_for_business_tag(status, None, "C0", evidence_count),
                })
            payload.update({
                "source": "company_bom_mapping",
                "source_status": "legacy_fallback" if tags else "empty",
                "tag_count": len(tags),
                "tags": tags,
                "limitations": [
                    "旧 BOM 映射没有业务级收入和毛利归因，不能进入核心评分",
                    "研发阶段和商用阶段需要 business_tag_evidence_events 确认",
                ] if tags else [],
            })
    except Exception as e:
        payload["source_status"] = "degraded"
        payload["error"] = str(e)
        payload["limitations"].append("PostgreSQL business tag lookup failed")
    return payload


def query_layers() -> dict[str, Any]:
    payload: dict[str, Any] = {
        "version": "supply-chain-v2-layers",
        "source": "fallback_bom_config",
        "source_status": "fallback",
        "layers": {},
        "nodes": [],
        "tree": [],
    }
    try:
        with repository.connect() as pg:
            cur = pg.cursor()
            if repository.table_exists(cur, "supply_chain_hierarchy_nodes") and repository.count(cur, "supply_chain_hierarchy_nodes") > 0:
                cur.execute(
                    """
                    SELECT node_id, parent_node_id, layer_level, layer_name, display_name,
                           source_table, source_id, keywords, metadata
                    FROM supply_chain_hierarchy_nodes
                    ORDER BY layer_level, display_name
                    """
                )
                rows = cur.fetchall()
                nodes = [
                    {
                        "layer_node_id": str(row[0]),
                        "parent_node_id": row[1],
                        "layer_level": str(row[2]),
                        "layer_name": str(row[3]),
                        "name": str(row[4]),
                        "source_table": row[5],
                        "source_id": row[6],
                        "keywords": _json_or_default(row[7], []),
                        "metadata": _json_or_default(row[8], {}),
                    }
                    for row in rows
                ]
                payload["source"] = "supply_chain_hierarchy_nodes"
                payload["source_status"] = "ready"
            else:
                nodes = fallback_layer_nodes()
    except Exception as e:
        nodes = fallback_layer_nodes()
        payload["source_status"] = "degraded_fallback"
        payload["error"] = str(e)

    layers: dict[str, list[dict[str, Any]]] = {f"L{i}": [] for i in range(1, 9)}
    for node in nodes:
        layers.setdefault(node["layer_level"], []).append(node)
    payload["layers"] = layers
    payload["nodes"] = nodes
    payload["tree"] = build_layer_tree(nodes)
    payload["node_count"] = len(nodes)
    return payload


def query_layer_detail(layer_node_id: str) -> dict[str, Any]:
    payload = query_layers()
    nodes = payload.get("nodes", [])
    node_by_id = {node.get("layer_node_id"): node for node in nodes}
    selected = node_by_id.get(layer_node_id)
    if not selected:
        raise HTTPException(status_code=404, detail=f"Layer node '{layer_node_id}' not found")

    children = [node for node in nodes if node.get("parent_node_id") == layer_node_id]
    ancestors = []
    parent_id = selected.get("parent_node_id")
    while parent_id and parent_id in node_by_id:
        parent = node_by_id[parent_id]
        ancestors.append(parent)
        parent_id = parent.get("parent_node_id")
    ancestors.reverse()
    return {
        "version": payload["version"],
        "source": payload["source"],
        "source_status": payload["source_status"],
        "node": selected,
        "ancestors": ancestors,
        "children": children,
        "child_count": len(children),
    }


def _token_output_power_row(row: dict[str, Any]) -> dict[str, Any]:
    result = dict(row)
    result["mapping_id"] = str(result.get("mapping_id") or "")
    result["chain_id"] = str(result.get("chain_id") or "ai_token_output_power")
    result["pool_code"] = str(result.get("pool_code") or "D").upper()
    result["evidence_grade"] = str(result.get("evidence_grade") or "E0").upper()
    result["reason_codes"] = _json_or_default(result.get("reason_codes"), [])
    result["coverage_ratio"] = _to_float(result.get("coverage_ratio"), None)
    return result


def token_output_power_payload(
    top_n: int = 50,
    pool_code: str | None = None,
    include_provisional: bool = False,
    trade_date: str | None = None,
) -> dict[str, Any]:
    """Return the evidence-first Token output chain payload."""

    safe_top_n = min(200, max(1, int(top_n or 50)))
    safe_pool = str(pool_code or "").upper() or None
    if safe_pool not in {None, "A", "B", "C", "D"}:
        raise HTTPException(status_code=400, detail="pool_code must be A, B, C, or D")
    payload: dict[str, Any] = {
        "version": "ai-token-output-power-v1",
        "chain_id": "ai_token_output_power",
        "as_of": trade_date,
        "source_status": "unknown",
        "layers": {key: dict(value) for key, value in TOKEN_OUTPUT_POWER_LAYERS.items()},
        "industry_dimensions": list(TOKEN_OUTPUT_POWER_DIMENSIONS),
        "power_model": dict(TOKEN_OUTPUT_POWER_POWER_MODEL),
        "pools": {"A": {"name": "Token业绩兑现池", "count": 0}, "B": {"name": "Token客户验证池", "count": 0}, "C": {"name": "Token技术卡位池", "count": 0}, "D": {"name": "电力/算力概念观察池", "count": 0}},
        "items": [],
        "provisional_items": [],
        "market_layer": {"separate_from_industry_evidence": True, "fields": ["valuation", "price_change", "turnover", "fund_flow", "crowding", "strategy_signal"]},
        "coverage_ratio": 0.0,
        "limitations": ["市场交易层不参与产业证据准入"],
    }
    try:
        formal_rows = repository.fetch_token_output_power_snapshot(
            None,
            safe_top_n,
            safe_pool if safe_pool in {"A", "B", "C"} else None,
            trade_date,
        )
        provisional_rows = []
        if include_provisional or safe_pool == "D":
            provisional_rows = repository.fetch_token_output_power_provisional_snapshot(
                None,
                safe_top_n,
                "D" if safe_pool == "D" else None,
                trade_date,
            )
        payload["items"] = [_token_output_power_row(row) for row in formal_rows]
        payload["provisional_items"] = [_token_output_power_row(row) for row in provisional_rows]
        all_rows = payload["items"] + payload["provisional_items"]
        for row in all_rows:
            pool = row["pool_code"] if row["pool_code"] in payload["pools"] else "D"
            payload["pools"][pool]["count"] += 1
        covered = [row["coverage_ratio"] for row in all_rows if row.get("coverage_ratio") is not None]
        payload["coverage_ratio"] = round(sum(covered) / len(covered), 4) if covered else 0.0
        payload["source_status"] = "ready" if all_rows else "empty"
        if not payload["items"]:
            payload["limitations"].append("暂无达到 A/B/C 正式池准入条件的映射")
        if payload["provisional_items"]:
            payload["limitations"].append("D 池仅作观察，不进入正式推荐和回测")
    except Exception as exc:
        payload["source_status"] = "degraded"
        payload["limitations"].append(f"Token 输出链查询失败：{exc}")
    return payload


def token_output_power_mapping_detail(mapping_id: str) -> dict[str, Any]:
    """Return one mapping with evidence, capacity, pool and market trace."""

    payload = repository.fetch_token_output_power_mapping(None, str(mapping_id))
    if not payload:
        raise HTTPException(status_code=404, detail=f"Token output mapping '{mapping_id}' not found")
    payload = dict(payload)
    payload.setdefault("chain_id", "ai_token_output_power")
    payload.setdefault("market_layer", {"separate_from_industry_evidence": True, "snapshots": []})
    payload["market_layer"]["separate_from_industry_evidence"] = True
    payload["source_status"] = "ready"
    return payload


TOKEN_OUTPUT_DIMENSIONS = [
    "demand_authenticity", "model_product_strength", "inference_unit_economics",
    "bom_supply_position", "delivery_customer_stickiness", "commercial_output",
    "evidence_realization",
]


def _token_output_row(row: dict[str, Any]) -> dict[str, Any]:
    result = dict(row)
    result["mapping_id"] = str(result.get("mapping_id") or "")
    result["code"] = str(result.get("code") or "")
    result["pool_code"] = str(result.get("pool_code") or "D").upper()
    result["evidence_grade"] = str(result.get("evidence_grade") or "E0").upper()
    result["reason_codes"] = _json_or_default(result.get("reason_codes"), [])
    result["coverage_ratio"] = _to_float(result.get("coverage_ratio"), None)
    result["industry_score"] = _to_float(result.get("industry_score"), None)
    result["market_signal_score"] = _to_float(result.get("market_signal_score"), None)
    return result


def token_output_payload(
    top_n: int = 50,
    pool_code: str | None = None,
    include_provisional: bool = False,
    as_of_date: str | None = None,
) -> dict[str, Any]:
    """Return the evidence-first AI Token commercial output chain."""
    safe_top_n = min(200, max(1, int(top_n or 50)))
    safe_pool = str(pool_code or "").upper() or None
    if safe_pool not in {None, "A", "B", "C", "D"}:
        raise HTTPException(status_code=400, detail="pool_code must be A, B, C, or D")
    formal_codes = (safe_pool,) if safe_pool in {"A", "B", "C"} else ("A", "B", "C")
    formal = repository.list_token_output_pools(None, top_n=safe_top_n, pool_codes=formal_codes, as_of_date=as_of_date)
    provisional = []
    if include_provisional or safe_pool == "D":
        provisional = repository.list_token_output_pools(None, top_n=safe_top_n, pool_codes=("D",), as_of_date=as_of_date)
    counts = repository.token_output_counts(None, as_of_date)
    return {
        "version": "ai-token-output-v1",
        "chain_id": "ai_token_output",
        "as_of": as_of_date,
        "layers": {f"L{i}": {} for i in range(1, 9)},
        "industry_dimensions": list(TOKEN_OUTPUT_DIMENSIONS),
        "mapping_count": int(counts.get("mapping_count") or 0),
        "unique_company_count": int(counts.get("unique_company_count") or 0),
        "formal_company_count": int(counts.get("formal_company_count") or 0),
        "domestic_output_count": int(counts.get("domestic_output_count") or 0),
        "overseas_output_count": int(counts.get("overseas_output_count") or 0),
        "items": [_token_output_row(row) for row in formal],
        "provisional_items": [_token_output_row(row) for row in provisional],
        "market_layer_separate": True,
        "limitations": ["D池只表示待验证业务相关性", "市场信号不改变产业证据等级"],
    }


def token_output_mapping_detail(mapping_id: str) -> dict[str, Any]:
    payload = repository.get_token_output_evidence(None, str(mapping_id))
    if not payload:
        raise HTTPException(status_code=404, detail=f"Token output mapping '{mapping_id}' not found")
    result = dict(payload)
    result["missing_fields"] = _json_or_default(result.get("missing_fields"), [])
    result["reason_codes"] = _json_or_default(result.get("reason_codes"), [])
    result["source_mapping_ids"] = _json_or_default(result.get("source_mapping_ids"), [])
    result["market_layer_separate"] = True
    return result
