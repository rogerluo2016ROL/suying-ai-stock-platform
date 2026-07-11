"""Supply-chain domain services."""

from datetime import datetime
import hashlib
import json
from typing import Any

from fastapi import HTTPException

from app.domains.supply_chain import repository


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
