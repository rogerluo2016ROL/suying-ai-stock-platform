"""Supply-chain domain services."""

from datetime import datetime
import json

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
