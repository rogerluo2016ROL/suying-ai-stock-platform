"""候选池装配 / 富化 / 过滤（从 service.py 拆出，零行为变化）。"""

import logging
from typing import Any, Optional

from app.config import MAX_TOP_N

# service 模块 facade：`_run_supply_chain_mode` / `_attach_market_snapshots` 保留在
# service.py（测试 monkeypatch 直接替换 service 模块属性，必须经 service 全局命名空间解析），
# 运行时经模块属性访问，避免循环导入。
from app.domains.screening import service as _screening_service
from app.domains.screening.contract import _sanitize_picks
from app.domains.screening.data_access import (
    _pg_connect,
    _pg_table_exists,
    _to_float,
)

logger = logging.getLogger("screener.routes")


def _pick_products_materials(pick: dict) -> tuple[list[str], list[str]]:
    product_map = pick.get("company_product_map") if isinstance(pick.get("company_product_map"), dict) else {}
    products = [v for v in product_map.get("products", []) if v]
    materials = [v for v in product_map.get("materials", []) if v]
    layer = pick.get("layer")
    if layer and layer not in products:
        products.append(layer)
    return products, materials


def _derive_commercialization_stage(pick: dict) -> str:
    stage = str(pick.get("commercialization_stage") or "").strip()
    if stage and stage != "证据待抽取":
        return stage
    revenue_growth = _to_float(pick.get("revenue_growth"))
    profit_growth = _to_float(pick.get("profit_growth"))
    report_count = int(_to_float(pick.get("report_count")))
    gross_margin = _to_float(pick.get("gross_margin"))
    if revenue_growth >= 50 and profit_growth > 0 and report_count >= 20:
        return "规模推广"
    if revenue_growth >= 25 and profit_growth > 0:
        return "量产爬坡"
    if report_count >= 5 or gross_margin >= 35:
        return "小批量验证"
    return "预研验证"


def _commercialization_cycle(stage: str) -> str:
    mapping = {
        "预研": "早期布局",
        "预研验证": "早期布局",
        "中试": "产业验证",
        "小批量": "小批量验证",
        "小批量验证": "小批量验证",
        "量产": "量产启动",
        "量产爬坡": "量产启动",
        "规模推广": "业绩兑现",
        "成熟": "估值扩散",
    }
    return mapping.get(stage, "产业验证")


def _derive_resonance(pick: dict, stage: str) -> dict:
    dims = pick.get("dimension_scores") if isinstance(pick.get("dimension_scores"), dict) else {}
    policy_score = _to_float(dims.get("policy"))
    revenue_growth = _to_float(pick.get("revenue_growth"))
    profit_growth = _to_float(pick.get("profit_growth"))
    trade_signal = str(pick.get("trade_signal") or "观察")
    policy = "强" if policy_score >= 10 or pick.get("policy_theme") else "中"
    commercialization = "量产放量" if stage in {"量产爬坡", "规模推广"} else "验证推进"
    performance = "高增长" if revenue_growth >= 25 and profit_growth > 0 else "待兑现"
    market = "趋势确认" if trade_signal in {"启动", "强启动"} else "观察跟踪"
    active = sum([
        policy == "强",
        commercialization == "量产放量",
        performance == "高增长",
        market == "趋势确认",
    ])
    if active >= 4:
        summary = "政策、商业化、业绩、市场四维共振"
    elif active >= 3:
        summary = "政策、商业化、业绩三维共振"
    elif active >= 2:
        summary = "政策与产业进程共振，等待市场确认"
    else:
        summary = "处于早期跟踪阶段，等待商业化或业绩证据"
    return {
        "policy": policy,
        "commercialization": commercialization,
        "performance": performance,
        "market": market,
        "summary": summary,
    }


def _selection_reason(pick: dict, stage: str, products: list[str], materials: list[str], resonance: dict) -> str:
    name = pick.get("name") or pick.get("code") or "候选公司"
    chain = pick.get("chain") or "产业链"
    layer = pick.get("layer") or "关键环节"
    product_text = "、".join(products[:2]) if products else layer
    material_text = f"，涉及{'、'.join(materials[:2])}" if materials else ""
    moat = "、".join((pick.get("moat_signals") or [])[:2])
    moat_text = f"，护城河信号为{moat}" if moat else ""
    return (
        f"{name}入选{chain}-{layer}环节，核心产品/能力为{product_text}{material_text}，"
        f"商业化阶段为{stage}，{resonance.get('summary', '处于持续跟踪阶段')}{moat_text}。"
    )


def _enrich_supply_chain_candidate(pick: dict, rank: int) -> dict:
    products, materials = _pick_products_materials(pick)
    stage = _derive_commercialization_stage(pick)
    resonance = pick.get("resonance") if isinstance(pick.get("resonance"), dict) else _derive_resonance(pick, stage)
    financial_indicators = pick.get("financial_indicators") if isinstance(pick.get("financial_indicators"), dict) else {
        "revenue_growth": _to_float(pick.get("revenue_growth")),
        "profit_growth": _to_float(pick.get("profit_growth")),
        "roe": _to_float(pick.get("roe")),
        "gross_margin": _to_float(pick.get("gross_margin")),
    }
    moat_signals = pick.get("moat_signals") if isinstance(pick.get("moat_signals"), list) else []
    moat_evidence = pick.get("moat_evidence") if isinstance(pick.get("moat_evidence"), list) else [
        {"evidence_type": "moat_signal", "summary": signal, "confidence": 0.7}
        for signal in moat_signals
    ]
    enriched = dict(pick)
    enriched.update({
        "rank": pick.get("rank") or rank,
        "score": _to_float(pick.get("score") if pick.get("score") is not None else pick.get("total_score")),
        "rating": pick.get("rating") or pick.get("grade") or "待评级",
        "trade_signal": pick.get("trade_signal") or "观察",
        "policy_theme": pick.get("policy_theme") or "未来产业主攻方向",
        "bom_path": pick.get("bom_path") or [v for v in (pick.get("chain"), pick.get("layer")) if v],
        "products": products,
        "materials": materials,
        "financial_indicators": financial_indicators,
        "moat_evidence": moat_evidence,
        "commercialization_stage": stage,
        "commercialization_cycle": pick.get("commercialization_cycle") or _commercialization_cycle(stage),
        "resonance": resonance,
        "selection_reason": pick.get("selection_reason") or _selection_reason(pick, stage, products, materials, resonance),
        "dimension_scores": pick.get("dimension_scores") if isinstance(pick.get("dimension_scores"), dict) else {},
        "evidence": pick.get("evidence") if isinstance(pick.get("evidence"), list) else [],
    })
    return enriched


def _get_supply_chain_candidate_pool(top_n: int = 30, trade_date: Optional[str] = None) -> list[dict]:
    result = _screening_service._run_supply_chain_mode("supply_chain", top_n, trade_date)
    picks = _sanitize_picks(result.get("picks", []))
    return [_enrich_supply_chain_candidate(pick, idx) for idx, pick in enumerate(picks[:top_n], start=1)]


def _query_business_tag_mapping_candidates(top_n: int = 30, node_id: Optional[str] = None) -> list[dict]:
    safe_top_n = min(MAX_TOP_N, max(1, int(top_n or 30)))
    conditions = ["COALESCE(m.status, '') <> 'rejected'"]
    params: list[Any] = []
    if node_id:
        conditions.append("m.node_id = %s")
        params.append(node_id)
    where = " AND ".join(conditions)

    try:
        with _pg_connect() as pg:
            cur = pg.cursor()
            if not _pg_table_exists(cur, "business_tag_mapping"):
                return []
            facts_join = """
                LEFT JOIN (
                    SELECT mapping_id,
                           COUNT(*) AS fact_count,
                           MAX(created_at) AS latest_fact_at,
                           MAX(research_stage_signal) FILTER (WHERE research_stage_signal IS NOT NULL) AS research_stage_signal,
                           MAX(commercial_stage_signal) FILTER (WHERE commercial_stage_signal IS NOT NULL) AS commercial_stage_signal
                    FROM evidence_extracted_facts
                    GROUP BY mapping_id
                ) f ON f.mapping_id = m.mapping_id
            """ if _pg_table_exists(cur, "evidence_extracted_facts") else "LEFT JOIN (SELECT NULL::text AS mapping_id, 0::int AS fact_count, NULL::timestamp AS latest_fact_at, NULL::text AS research_stage_signal, NULL::text AS commercial_stage_signal) f ON FALSE"
            freshness_join = """
                LEFT JOIN business_tag_evidence_freshness fr ON fr.mapping_id = m.mapping_id
            """ if _pg_table_exists(cur, "business_tag_evidence_freshness") else "LEFT JOIN (SELECT NULL::text AS mapping_id, NULL::text AS freshness_status, NULL::int AS days_since_update) fr ON FALSE"
            cur.execute(
                f"""
                SELECT m.mapping_id, m.code, COALESCE(s.name, m.code) AS name,
                       m.node_id, COALESCE(n.name, cn.node_name, m.node_id) AS node_name,
                       m.chain_id, m.theme_id, m.tag_name, m.confidence, m.status,
                       m.revenue_ratio, m.gross_profit_ratio,
                       COALESCE(f.fact_count, 0) AS fact_count,
                       f.latest_fact_at, f.research_stage_signal, f.commercial_stage_signal,
                       fr.freshness_status, fr.days_since_update, m.updated_at
                FROM business_tag_mapping m
                LEFT JOIN stocks s
                  ON regexp_replace(s.code, '\\.(SZ|SH|BJ)$', '') = regexp_replace(m.code, '\\.(SZ|SH|BJ)$', '')
                LEFT JOIN supply_chain_bom_nodes n ON n.node_id = m.node_id
                LEFT JOIN chain_nodes cn ON cn.node_id = m.node_id
                {facts_join}
                {freshness_join}
                WHERE {where}
                ORDER BY COALESCE(f.fact_count, 0) DESC,
                         m.confidence DESC NULLS LAST,
                         m.updated_at DESC NULLS LAST
                LIMIT %s
                """,
                [*params, safe_top_n],
            )
            rows = cur.fetchall()
    except Exception as e:
        logger.warning("business_tag mapping fallback candidates unavailable: %s", e)
        return []

    candidates: list[dict] = []
    for idx, row in enumerate(rows, start=1):
        confidence = _to_float(row[8], 0.0)
        fact_count = int(row[12] or 0)
        freshness_status = str(row[16] or "unknown")
        evidence_gaps = [] if fact_count > 0 else ["该业务标签暂无结构化证据事实"]
        if freshness_status in {"unknown", "stale", "expired"}:
            evidence_gaps.append("证据新鲜度不足，需要补充最新公告、研报或新闻")
        candidates.append({
            "rank": idx,
            "mapping_id": str(row[0]),
            "code": str(row[1] or ""),
            "name": str(row[2] or row[1] or ""),
            "node_id": str(row[3] or ""),
            "node_name": str(row[4] or ""),
            "chain": str(row[5] or ""),
            "policy_theme": str(row[6] or ""),
            "products": [str(row[7])] if row[7] else [],
            "materials": [],
            "mapping_confidence": confidence,
            "mapping_status": str(row[9] or "pending_review"),
            "mapping_source": "business_tag_mapping",
            "mapping_quality_weight": confidence,
            "score": round(confidence * 100 + min(fact_count, 20), 2),
            "mapping_adjusted_score": round(confidence * 100 + min(fact_count, 20), 2),
            "rating": "证据充分" if fact_count >= 3 else "待补证据",
            "trade_signal": "观察",
            "financial_indicators": {
                "revenue_ratio": _to_float(row[10], None),
                "gross_profit_ratio": _to_float(row[11], None),
            },
            "commercialization_stage": row[15] or "待证据确认",
            "commercialization_cycle": row[14] or "待证据确认",
            "selection_reason": f"来自业务标签映射，结构化事实 {fact_count} 条",
            "evidence": [f"结构化事实 {fact_count} 条", f"新鲜度 {freshness_status}"],
            "evidence_gaps": evidence_gaps,
            "candidate_source": "business_tag_mapping_fallback",
            "last_trade_date": str(row[18]) if row[18] else None,
        })
    return candidates


def _query_latest_market_snapshots(codes: list[str], trade_date: Optional[str] = None) -> dict[str, dict]:
    clean_codes = sorted({str(code) for code in codes if code})
    if not clean_codes:
        return {}
    try:
        with _pg_connect() as pg:
            cur = pg.cursor()
            placeholders = ",".join(["%s"] * len(clean_codes))
            params: list[object] = clean_codes[:]
            cutoff = ""
            if trade_date:
                cutoff = " AND trade_date <= %s"
                params.append(trade_date)
            cur.execute(
                f"""
                SELECT DISTINCT ON (code)
                       code, trade_date, close, change_pct
                FROM daily_kline
                WHERE code IN ({placeholders}){cutoff}
                ORDER BY code, trade_date DESC
                """,
                params,
            )
            return {
                str(row[0]): {
                    "last_trade_date": str(row[1]) if row[1] else "",
                    "last_price": _to_float(row[2], None),
                    "last_change_pct": _to_float(row[3], None),
                }
                for row in cur.fetchall()
            }
    except Exception as e:
        logger.debug("supply_chain market snapshots unavailable: %s", e)
        return {}


def _query_upstream_influence_candidates(limit: int = 50, trade_date: Optional[str] = None) -> list[dict]:
    """Return companies that affect strategic chains as upstream enablers."""
    safe_limit = max(1, min(int(limit or 50), 200))
    try:
        from kronos_factors.engine.supply_chain import (
            load_upstream_influence_rules,
            match_upstream_influence_rules,
        )
        rules = load_upstream_influence_rules()
        if not rules:
            return []
        with _pg_connect() as pg:
            cur = pg.cursor()
            cur.execute(
                """
                SELECT s.code, s.name, s.industry, COALESCE(p.main_business, '') AS main_business
                FROM stocks s
                LEFT JOIN stock_profiles p ON p.code = s.code
                WHERE s.is_st = 0
                """
            )
            candidates = []
            for code, name, industry, main_business in cur.fetchall():
                matches = match_upstream_influence_rules(
                    code=str(code or ""),
                    name=str(name or ""),
                    industry=str(industry or ""),
                    main_business=str(main_business or ""),
                    rules=rules,
                )
                for match in matches:
                    downstream = match.get("downstream_chains") or []
                    influence_score = min(100.0, 35.0 + len(downstream) * 5.0)
                    candidates.append({
                        "code": str(code or ""),
                        "name": str(name or ""),
                        "industry": str(industry or ""),
                        "chain": "上游影响",
                        "layer": match.get("upstream_node"),
                        "score": round(influence_score, 1),
                        "rating": "观察",
                        "trade_signal": "观察",
                        "candidate_source": match.get("candidate_source"),
                        "pool_status": match.get("pool_status"),
                        "policy_theme": match.get("policy_theme"),
                        "upstream_node": match.get("upstream_node"),
                        "impact_role": match.get("impact_role"),
                        "downstream_chains": downstream,
                        "influence_paths": match.get("influence_paths") or [],
                        "evidence_gaps": match.get("evidence_gaps") or [],
                        "products": [match.get("upstream_node")] if match.get("upstream_node") else [],
                        "materials": [match.get("upstream_node")] if match.get("upstream_node") else [],
                        "commercialization_stage": "证据待抽取",
                        "commercialization_cycle": "上游映射验证",
                        "resonance": {"summary": "等待产品、客户、量产和财务证据验证"},
                        "selection_reason": (
                            f"{name or code}不因{industry or '原行业'}行业被排除，"
                            f"作为{match.get('impact_role') or '上游使能环节'}进入上游影响观察池；"
                            "需要继续验证其产品/材料是否真实影响下游战略产业。"
                        ),
                    })
            candidates = _screening_service._attach_market_snapshots(candidates, trade_date)
            candidates.sort(
                key=lambda item: (
                    float(item.get("score") or 0),
                    float(item.get("last_change_pct") or 0),
                ),
                reverse=True,
            )
            return candidates[:safe_limit]
    except Exception as e:
        logger.debug("supply_chain upstream influence candidates unavailable: %s", e)
        return []


def _normalize_match_terms(values: list[object]) -> set[str]:
    terms: set[str] = set()
    for value in values:
        if value is None:
            continue
        if isinstance(value, list):
            terms.update(_normalize_match_terms(value))
            continue
        text = str(value).strip().lower()
        if text:
            terms.add(text)
    return terms


def _candidate_search_terms(candidate: dict) -> set[str]:
    return _normalize_match_terms([
        candidate.get("chain"),
        candidate.get("layer"),
        candidate.get("bom_path") if isinstance(candidate.get("bom_path"), list) else [],
        candidate.get("products") if isinstance(candidate.get("products"), list) else [],
        candidate.get("materials") if isinstance(candidate.get("materials"), list) else [],
        candidate.get("selection_reason"),
    ])


def _node_match_terms(node: dict) -> set[str]:
    bom_path = node.get("bom_path") if isinstance(node.get("bom_path"), list) else []
    return _normalize_match_terms([
        node.get("name"),
        node.get("chain_id"),
        node.get("level"),
        node.get("node_type"),
        bom_path[1:] if len(bom_path) > 1 else bom_path,
        node.get("keywords") if isinstance(node.get("keywords"), list) else [],
    ])


def _candidate_matches_node(candidate: dict, node: dict) -> bool:
    search_text = " ".join(_candidate_search_terms(candidate))
    node_terms = _node_match_terms(node)
    return any(term and term in search_text for term in node_terms)


def _filter_candidates_for_node(candidates: list[dict], node: dict | None) -> list[dict]:
    if not node:
        return []
    matched = []
    for candidate in candidates:
        if _candidate_matches_node(candidate, node):
            enriched = dict(candidate)
            enriched["matched_node_id"] = node.get("node_id")
            enriched["matched_node_name"] = node.get("name")
            matched.append(enriched)
    return matched


def _build_selected_node_thesis(node: dict | None, node_candidates: list[dict]) -> dict:
    if not node:
        return {}
    keywords = node.get("keywords") if isinstance(node.get("keywords"), list) else []
    name = node.get("name") or "BOM节点"
    candidate_count = len(node_candidates)
    mapping_status = "mapped" if candidate_count else "missing_company_mapping"
    mapping_message = f"已映射 {candidate_count} 家候选上市公司" if candidate_count else "该节点缺少公司映射证据"
    return {
        "node_id": node.get("node_id"),
        "name": name,
        "policy_theme": node.get("policy_theme", ""),
        "bom_path": node.get("bom_path", []),
        "keywords": keywords,
        "thesis": (
            f"{name}是{node.get('policy_theme') or '政策主题'}下的关键BOM节点，"
            "需要用产品、材料、订单、产能和财务兑现证据验证公司映射。"
        ),
        "trigger_conditions": ["政策持续加码", "产品进入量产或规模推广", "订单与产能公告验证", "收入和利润增速同步改善"],
        "risk_factors": ["商业化进度低于预期", "国产替代节奏放缓", "毛利率下降", "市场交易拥挤"],
        "mapping_status": mapping_status,
        "mapping_message": mapping_message,
    }


def _build_evidence_summary(candidates: list[dict]) -> dict:
    approved = 0
    pending_review = 0
    low_confidence = 0
    for candidate in candidates:
        evidence = candidate.get("evidence") if isinstance(candidate.get("evidence"), list) else []
        for item in evidence:
            status = item.get("status") if isinstance(item, dict) else None
            confidence = _to_float(item.get("confidence") if isinstance(item, dict) else None)
            if status == "approved":
                approved += 1
            elif status == "pending_review":
                pending_review += 1
            if confidence and confidence < 0.5:
                low_confidence += 1
    return {
        "approved": approved,
        "pending_review": pending_review,
        "low_confidence": low_confidence,
    }


def _supply_chain_model_payload() -> dict:
    from kronos_factors.engine.supply_chain_bom_v5 import DIM_WEIGHTS

    dimension_names = {
        "policy": "政策力度",
        "bom": "BOM关键度",
        "chokepoint": "卡脖子/国产替代",
        "growth": "业绩成长",
        "profit": "盈利质量",
        "commercialization": "商业化阶段",
        "market": "市场共振",
    }
    return {
        "name": "产业链预期差选股模型 V1.0",
        "version": "1.0",
        "philosophy": "政策主题定方向，BOM 拆解定环节，上市公司候选池定标的，商业化、政策、业绩、市场共振定启动信号。",
        "score_dimensions": [
            {"key": key, "name": dimension_names[key], "weight": weight}
            for key, weight in DIM_WEIGHTS.items()
        ],
    }


def _derive_resonance_from_three_factors(three_factors: dict) -> dict:
    """Derive resonance summary from three_factors JSONB field.

    three_factors structure (from PRD):
    {
        "industry_cycle": {"stage": "量产", "score": 9},
        "policy_intensity": {"stars": 4, "score": 12},
        "performance_proof": {"status": "业绩兑现", "score": 10}
    }
    """
    if not three_factors:
        return {"summary": "待评估", "dimensions": {}}

    industry_cycle = three_factors.get("industry_cycle", {})
    policy_intensity = three_factors.get("policy_intensity", {})
    performance_proof = three_factors.get("performance_proof", {})

    dims = {
        "industry_cycle": {
            "stage": industry_cycle.get("stage", "未知"),
            "score": _to_float(industry_cycle.get("score"), 0),
        },
        "policy_intensity": {
            "stars": int(policy_intensity.get("stars", 0)),
            "score": _to_float(policy_intensity.get("score"), 0),
        },
        "performance_proof": {
            "status": performance_proof.get("status", "待验证"),
            "score": _to_float(performance_proof.get("score"), 0),
        },
    }

    # Count how many dimensions are "达标" (score >= threshold)
    cycle_ok = dims["industry_cycle"]["score"] >= 9  # 量产/放量
    policy_ok = dims["policy_intensity"]["stars"] >= 4
    perf_ok = dims["performance_proof"]["score"] >= 10

    active_count = sum([cycle_ok, policy_ok, perf_ok])

    if active_count >= 3:
        summary = "三因子共振 — 强启动信号"
    elif active_count >= 2:
        summary = "双因子共振 — 关注信号"
    elif active_count >= 1:
        summary = "单因子达标 — 观察信号"
    else:
        summary = "待兑现 — 暂无共振"

    return {
        "summary": summary,
        "dimensions": dims,
        "active_count": active_count,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Chain Candidates Endpoint (Phase 3)
# ─────────────────────────────────────────────────────────────────────────────

VALID_FILTERS = frozenset({
    "high_growth", "high_profit", "high_moat", "chokepoint_core", "all"
})


VALID_RESONANCE_LEVELS = frozenset({
    "强启动", "启动", "关注", "观察"
})


def _enrich_candidate_with_resonance_v6(candidate: dict) -> dict:
    """Enrich a candidate with V6 three-factor resonance scoring."""
    from kronos_factors.engine.supply_chain_bom_v5 import (
        derive_resonance_v6,
        classify_chokepoint_level,
        CHOKEPOINT_CORE_KEYWORDS,
    )

    # Extract stage from candidate
    stage = candidate.get("commercialization_stage")
    if not stage or stage == "证据待抽取":
        stage = candidate.get("stage")

    # Compute V6 resonance scores
    resonance_v6 = derive_resonance_v6(candidate, stage)

    # Determine chokepoint level from dimension_scores keywords
    dim_scores = candidate.get("dimension_scores") if isinstance(candidate.get("dimension_scores"), dict) else {}
    chokepoint_score = _to_float(dim_scores.get("chokepoint", 0))
    evidence = candidate.get("evidence") if isinstance(candidate.get("evidence"), list) else []
    keywords = []
    for item in evidence:
        if isinstance(item, dict):
            kw_list = item.get("keywords") or item.get("chokepoint")
            if isinstance(kw_list, list):
                keywords.extend([str(k) for k in kw_list if k])
            elif isinstance(kw_list, str):
                keywords.append(kw_list)

    chokepoint_level = classify_chokepoint_level(chokepoint_score, keywords)

    enriched = dict(candidate)
    enriched.update({
        "three_factor_scores": {
            "industry_cycle": resonance_v6["industry_cycle_score"],
            "policy_intensity": resonance_v6["policy_intensity_score"],
            "performance_yield": resonance_v6["performance_yield_score"],
        },
        "resonance_factors": resonance_v6["resonance_factors"],
        "resonance_signal": resonance_v6["resonance_signal"],
        "resonance_details": resonance_v6["resonance_details"],
        "chokepoint_level": chokepoint_level,
        "chokepoint_keywords": [k for k in keywords if k in CHOKEPOINT_CORE_KEYWORDS] if keywords else [],
    })

    # Preserve existing resonance if available (backward compatibility)
    if not enriched.get("resonance"):
        enriched["resonance"] = {
            "summary": resonance_v6["resonance_signal"],
            "dimensions": resonance_v6["resonance_details"],
        }

    return enriched


def _filter_candidate_by_filter_type(candidate: dict, filter_type: str) -> bool:
    """Filter candidate by filter type criteria.

    Filter criteria:
    - high_growth: performance_yield >= 15 (yoy >= 50%)
    - high_profit: gross_margin >= 50%
    - high_moat: chokepoint_score >= 10
    - chokepoint_core: chokepoint_level == "卡脖子核心"
    - all: no filter
    """
    if filter_type == "all":
        return True

    three_factors = candidate.get("three_factor_scores") if isinstance(candidate.get("three_factor_scores"), dict) else {}
    dim_scores = candidate.get("dimension_scores") if isinstance(candidate.get("dimension_scores"), dict) else {}

    if filter_type == "high_growth":
        perf_yield = _to_float(three_factors.get("performance_yield", 0))
        if perf_yield:
            return perf_yield >= 15.0
        # 快照三路回退: V6 原始字段 (q_sales_yoy 等) 缺失时,
        # 用快照三高 growth_score (0-100, 事件+收入占比驱动), ≥75 约当业绩兑现档
        snap_growth = _to_float(candidate.get("growth_score"))
        return snap_growth is not None and snap_growth >= 75.0

    if filter_type == "high_profit":
        gross_margin = _to_float(candidate.get("gross_margin", 0))
        profit_dim = _to_float(dim_scores.get("profit", 0))
        # High profit: gross_margin >= 50% OR profit_dim >= 10 (V5 max)
        if gross_margin >= 50.0 or profit_dim >= 10.0:
            return True
        # 快照三路回退: profit_score (0-100, 毛利占比+盈利事件驱动) ≥75 视作高盈利
        snap_profit = _to_float(candidate.get("profit_score"))
        return snap_profit is not None and snap_profit >= 75.0

    if filter_type == "high_moat":
        chokepoint_score = _to_float(dim_scores.get("chokepoint", 0))
        choke_keywords = candidate.get("chokepoint_keywords") if isinstance(candidate.get("chokepoint_keywords"), list) else []
        # High moat: chokepoint_score >= 6 OR has chokepoint keywords
        return chokepoint_score >= 6.0 or len(choke_keywords) > 0

    if filter_type == "chokepoint_core":
        chokepoint_level = str(candidate.get("chokepoint_level") or "")
        return chokepoint_level == "卡脖子核心"

    return True


def _filter_candidate_by_resonance_level(candidate: dict, resonance_level: str | None) -> bool:
    """Filter candidate by resonance level.

    resonance_level options: 强启动, 启动, 关注, 观察
    """
    if not resonance_level:
        return True

    signal = str(candidate.get("resonance_signal") or candidate.get("trade_signal") or "观察")
    return signal == resonance_level
