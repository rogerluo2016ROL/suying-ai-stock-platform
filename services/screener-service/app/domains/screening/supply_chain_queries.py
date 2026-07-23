"""供应链 PG 查询与证据/映射审核（从 service.py 拆出，零行为变化）。

业务标签 / L8 / 候选打分的具体实现已下沉到 supply_chain 域，
这里直接从 supply_chain.service 引入同名私有函数，与 service.py 中的
同名薄委托一一对应，行为完全一致。
"""

import json
import logging
from datetime import datetime
from typing import Any, Optional

from fastapi import HTTPException

from app.domains.supply_chain import evidence_review_service
from app.domains.supply_chain.service import (
    _aggregate_supply_chain_candidate_rows,
    _default_business_tag_stage,
    _load_bigtech_capex_context,
    _score_supply_chain_candidate_row,
    _stage_from_evidence_events,
    query_business_tag_evidence as _query_business_tag_evidence,
)
from app.domains.screening.data_access import (
    _json_or_default,
    _load_supply_chain_bom_payload,
    _pg_connect,
    _pg_table_exists,
    _row_get,
    _to_float,
)
from app.domains.screening.schemas import (
    BusinessTagEvidenceReviewRequest,
    LLMUsageInfo,
)

logger = logging.getLogger("screener.routes")


def _query_supply_chain_node_evidence(node_id: str) -> list[dict]:
    try:
        from kronos_factors.scorer._db_stub import _get_db
        with _get_db(readonly=True) as db:
            rows = db.execute(
                """
                SELECT evidence_id, code, evidence_type, summary, excerpt,
                       confidence, evidence_date, status, source_id
                FROM company_evidence
                WHERE node_id = ?
                ORDER BY confidence DESC
                LIMIT 100
                """,
                (node_id,),
            ).fetchall()
        return [{
            "evidence_id": _row_get(r, "evidence_id"),
            "code": _row_get(r, "code"),
            "evidence_type": _row_get(r, "evidence_type"),
            "summary": _row_get(r, "summary"),
            "excerpt": _row_get(r, "excerpt"),
            "confidence": float(_row_get(r, "confidence", 0) or 0),
            "evidence_date": str(_row_get(r, "evidence_date") or ""),
            "status": _row_get(r, "status"),
            "source_id": _row_get(r, "source_id"),
        } for r in rows]
    except Exception as e:
        logger.debug("supply_chain node evidence unavailable (%s): %s", node_id, e)
        return []


def _query_supply_chain_node_companies(node_id: str) -> list[dict]:
    try:
        from kronos_factors.scorer._db_stub import _get_db
        with _get_db(readonly=True) as db:
            rows = db.execute(
                """
                SELECT m.code, COALESCE(s.name, m.code) AS name,
                       m.product_name, m.material_name, m.confidence, m.status,
                       sc.total_score, sc.rating, sc.trade_signal, sc.dimension_scores
                FROM company_bom_mapping m
                LEFT JOIN stocks s ON s.code = m.code
                LEFT JOIN supply_chain_scores sc
                  ON sc.code = m.code
                 AND (sc.node_id = m.node_id OR sc.node_id IS NULL)
                WHERE m.node_id = ?
                  AND m.status IN ('approved', 'pending_review')
                ORDER BY COALESCE(sc.total_score, 0) DESC, m.confidence DESC
                LIMIT 50
                """,
                (node_id,),
            ).fetchall()
        companies = []
        for idx, r in enumerate(rows, start=1):
            companies.append({
                "code": _row_get(r, "code"),
                "name": _row_get(r, "name"),
                "rank": idx,
                "rating": _row_get(r, "rating") or "待评级",
                "trade_signal": _row_get(r, "trade_signal") or "观察",
                "score": float(_row_get(r, "total_score", 0) or 0),
                "product_name": _row_get(r, "product_name"),
                "material_name": _row_get(r, "material_name"),
                "confidence": float(_row_get(r, "confidence", 0) or 0),
                "status": _row_get(r, "status"),
                "dimension_scores": _json_or_default(_row_get(r, "dimension_scores"), {}),
            })
        return companies
    except Exception as e:
        logger.debug("supply_chain node companies unavailable (%s): %s", node_id, e)
        return []


def _query_supply_chain_company_detail(code: str) -> dict | None:
    try:
        from kronos_factors.scorer._db_stub import _get_db
        with _get_db(readonly=True) as db:
            mapping_rows = db.execute(
                """
                SELECT m.node_id, m.product_name, m.material_name, m.confidence,
                       m.evidence_ids, n.name AS node_name, n.theme_id, n.level,
                       COALESCE(s.name, m.code) AS company_name
                FROM company_bom_mapping m
                LEFT JOIN supply_chain_bom_nodes n ON n.node_id = m.node_id
                LEFT JOIN stocks s ON s.code = m.code
                WHERE m.code = ?
                ORDER BY m.confidence DESC
                """,
                (code,),
            ).fetchall()
            score = db.execute(
                """
                SELECT total_score, rating, trade_signal, dimension_scores
                FROM supply_chain_scores
                WHERE code = ?
                ORDER BY trade_date DESC, total_score DESC
                LIMIT 1
                """,
                (code,),
            ).fetchone()
            fin = db.execute(
                """
                SELECT roe, gross_margin, net_margin, debt_ratio, eps,
                       revenue_growth, profit_growth, end_date
                FROM financial_indicator
                WHERE code = ?
                ORDER BY end_date DESC
                LIMIT 1
                """,
                (code,),
            ).fetchone()
            evidence_rows = db.execute(
                """
                SELECT evidence_id, node_id, evidence_type, summary, excerpt,
                       confidence, evidence_date, status, source_id
                FROM company_evidence
                WHERE code = ?
                ORDER BY confidence DESC
                LIMIT 100
                """,
                (code,),
            ).fetchall()
    except Exception as e:
        logger.debug("supply_chain company detail unavailable (%s): %s", code, e)
        return None

    payload = _load_supply_chain_bom_payload()
    theme_by_id = {theme.get("theme_id"): theme for theme in payload["themes"]}
    node_by_id = {node.get("node_id"): node for node in payload["nodes"]}

    products, materials, paths = [], [], []
    for row in mapping_rows:
        product = _row_get(row, "product_name")
        material = _row_get(row, "material_name")
        if product and product not in products:
            products.append(product)
        if material and material not in materials:
            materials.append(material)
        node = node_by_id.get(_row_get(row, "node_id"), {})
        if node.get("bom_path"):
            paths.append(node["bom_path"])

    evidence = [{
        "evidence_id": _row_get(r, "evidence_id"),
        "node_id": _row_get(r, "node_id"),
        "evidence_type": _row_get(r, "evidence_type"),
        "summary": _row_get(r, "summary"),
        "excerpt": _row_get(r, "excerpt"),
        "confidence": float(_row_get(r, "confidence", 0) or 0),
        "evidence_date": str(_row_get(r, "evidence_date") or ""),
        "status": _row_get(r, "status"),
        "source_id": _row_get(r, "source_id"),
    } for r in evidence_rows]
    moat_evidence = [e for e in evidence if e.get("evidence_type") in {"patent", "moat", "announcement", "capacity", "bidding"}]

    financial_indicators = {}
    if fin:
        financial_indicators = {
            "roe": float(_row_get(fin, "roe", 0) or 0),
            "gross_margin": float(_row_get(fin, "gross_margin", 0) or 0),
            "net_margin": float(_row_get(fin, "net_margin", 0) or 0),
            "debt_ratio": float(_row_get(fin, "debt_ratio", 0) or 0),
            "eps": float(_row_get(fin, "eps", 0) or 0),
            "revenue_growth": float(_row_get(fin, "revenue_growth", 0) or 0),
            "profit_growth": float(_row_get(fin, "profit_growth", 0) or 0),
            "end_date": str(_row_get(fin, "end_date") or ""),
        }

    first_node = node_by_id.get(_row_get(mapping_rows[0], "node_id"), {}) if mapping_rows else {}
    first_theme = theme_by_id.get(first_node.get("theme_id"), {})
    return {
        "code": code,
        "name": _row_get(mapping_rows[0], "company_name") if mapping_rows else code,
        "node_name": _row_get(mapping_rows[0], "node_name") if mapping_rows else None,
        "rank": None,
        "rating": _row_get(score, "rating") if score else None,
        "trade_signal": (_row_get(score, "trade_signal") if score else None) or "观察",
        "score": float(_row_get(score, "total_score", 0) or 0) if score else 0,
        "dimension_scores": _json_or_default(_row_get(score, "dimension_scores") if score else None, {}),
        "policy_theme": first_theme.get("name", ""),
        "bom_path": paths[0] if paths else [],
        "products": products,
        "materials": materials,
        "financial_indicators": financial_indicators,
        "moat_evidence": moat_evidence,
        "evidence": evidence,
    }


def _query_supply_chain_candidate_ranking(
    top_n: int = 100,
    chain_id: Optional[str] = None,
    signal: Optional[str] = None,
) -> dict[str, Any]:
    safe_top_n = min(200, max(1, int(top_n or 100)))
    safe_chain_id = str(chain_id or "").strip() or None
    safe_signal = str(signal or "").strip() or None
    payload: dict[str, Any] = {
        "version": "supply-chain-candidate-ranking-v1",
        "source_status": "unknown",
        "filters": {"top_n": safe_top_n, "chain_id": safe_chain_id, "signal": safe_signal},
        "summary": {},
        "items": [],
        "by_chain": {},
        "limitations": [
            "候选总榜不是买入建议；交易层仍需结合行情、风控和买卖点模型。",
            "20日涨幅只占2%权重，排序核心是业务标签级证据。",
        ],
    }
    try:
        with _pg_connect() as pg:
            cur = pg.cursor()
            required = [
                "business_tag_mapping",
                "business_tag_three_high_scores",
                "business_tag_expectation_gap_scores",
                "business_tag_l8_evidence_status",
                "business_tag_evidence_freshness",
                "daily_kline",
            ]
            missing = [table for table in required if not _pg_table_exists(cur, table)]
            if missing:
                payload["source_status"] = "missing_tables"
                payload["limitations"].append(f"缺少表：{', '.join(missing)}")
                return payload
            has_capex_table = _pg_table_exists(cur, "business_tag_capex_evidence")
            capex_cte = """
                capex AS (
                    SELECT
                        mapping_id,
                        count(*) FILTER (WHERE review_status = 'approved') AS capex_evidence_count,
                        count(*) FILTER (WHERE review_status = 'approved' AND capex_amount IS NOT NULL) AS capex_amount_count,
                        count(*) FILTER (WHERE review_status = 'approved' AND direction_is_ai_related) AS capex_direction_ai_count,
                        count(*) FILTER (WHERE review_status = 'approved' AND as_of_date >= CURRENT_DATE - INTERVAL '540 days') AS capex_fresh_count,
                        avg(confidence) FILTER (WHERE review_status = 'approved') AS capex_avg_confidence,
                        max(as_of_date) FILTER (WHERE review_status = 'approved') AS capex_latest_as_of_date,
                        jsonb_agg(DISTINCT capex_direction) FILTER (WHERE review_status = 'approved') AS capex_directions
                    FROM business_tag_capex_evidence
                    GROUP BY mapping_id
                ),
            """ if has_capex_table else ""
            capex_select = """
                    coalesce(cx.capex_evidence_count, 0) AS capex_evidence_count,
                    coalesce(cx.capex_amount_count, 0) AS capex_amount_count,
                    coalesce(cx.capex_direction_ai_count, 0) AS capex_direction_ai_count,
                    coalesce(cx.capex_fresh_count, 0) AS capex_fresh_count,
                    coalesce(cx.capex_avg_confidence, 0) AS capex_avg_confidence,
                    cx.capex_latest_as_of_date,
                    coalesce(cx.capex_directions, '[]'::jsonb) AS capex_directions,
            """ if has_capex_table else """
                    0 AS capex_evidence_count,
                    0 AS capex_amount_count,
                    0 AS capex_direction_ai_count,
                    0 AS capex_fresh_count,
                    0 AS capex_avg_confidence,
                    NULL AS capex_latest_as_of_date,
                    '[]'::jsonb AS capex_directions,
            """
            capex_join = "LEFT JOIN capex cx ON cx.mapping_id = b.mapping_id" if has_capex_table else ""
            cur.execute(
                f"""
                WITH mapping_base AS (
                    SELECT mapping_id, split_part(code, '.', 1) AS code, chain_id, node_id, tag_name, status AS mapping_status
                    FROM business_tag_mapping
                    WHERE chain_id IS NOT NULL
                      AND COALESCE(status, '') <> 'rejected'
                ),
                latest_score AS (
                    SELECT DISTINCT ON (mapping_id)
                        mapping_id, trade_date, growth_score, profit_score, moat_score,
                        stage_score, evidence_score, total_score
                    FROM business_tag_three_high_scores
                    ORDER BY mapping_id, trade_date DESC, created_at DESC
                ),
                latest_gap AS (
                    SELECT DISTINCT ON (mapping_id)
                        mapping_id, expectation_gap_score, gap_type
                    FROM business_tag_expectation_gap_scores
                    ORDER BY mapping_id, trade_date DESC, created_at DESC
                ),
                latest_stage AS (
                    SELECT DISTINCT ON (mapping_id)
                        mapping_id, research_stage, commercialization_stage
                    FROM business_tag_stage_tracking
                    ORDER BY mapping_id, trade_date DESC, created_at DESC
                ),
                l8 AS (
                    SELECT mapping_id, count(*) AS l8_total,
                           count(*) FILTER (WHERE source_status = 'matched') AS l8_matched,
                           sum(coalesce(evidence_count, 0)) AS l8_evidence_count
                    FROM business_tag_l8_evidence_status
                    GROUP BY mapping_id
                ),
                facts AS (
                    SELECT mapping_id, count(*) AS fact_count
                    FROM evidence_extracted_facts
                    GROUP BY mapping_id
                ),
                {capex_cte}
                market_latest AS (
                    SELECT DISTINCT ON (code)
                        code, trade_date AS latest_trade_date, close AS latest_price, change_pct AS change_1d_pct
                    FROM daily_kline
                    ORDER BY code, trade_date DESC
                ),
                market_20d AS (
                    SELECT code,
                           max(close) FILTER (WHERE rn = 1) AS latest_close,
                           max(close) FILTER (WHERE rn = 20) AS close_20d
                    FROM (
                        SELECT code, trade_date, close,
                               row_number() OVER (PARTITION BY code ORDER BY trade_date DESC) AS rn
                        FROM daily_kline
                    ) x
                    WHERE rn IN (1, 20)
                    GROUP BY code
                )
                SELECT
                    b.mapping_id, b.code, coalesce(s.name, b.code) AS name, coalesce(s.industry, '') AS industry,
                    b.chain_id, b.node_id, b.tag_name, b.mapping_status,
                    coalesce(sc.growth_score, 0) AS growth_score,
                    coalesce(sc.profit_score, 0) AS profit_score,
                    coalesce(sc.moat_score, 0) AS moat_score,
                    coalesce(sc.stage_score, 0) AS stage_score,
                    coalesce(sc.evidence_score, 0) AS evidence_score,
                    coalesce(sc.total_score, 0) AS three_high_total,
                    coalesce(g.expectation_gap_score, 0) AS expectation_gap_score,
                    coalesce(g.gap_type, '') AS gap_type,
                    coalesce(st.research_stage, '') AS research_stage,
                    coalesce(st.commercialization_stage, '') AS commercialization_stage,
                    coalesce(l8.l8_total, 0) AS l8_total,
                    coalesce(l8.l8_matched, 0) AS l8_matched,
                    CASE WHEN coalesce(l8.l8_total, 0) = 0 THEN 0
                         ELSE coalesce(l8.l8_matched, 0)::float / l8.l8_total END AS l8_match_rate,
                    coalesce(l8.l8_evidence_count, 0) AS l8_evidence_count,
                    coalesce(f.fact_count, 0) AS fact_count,
                    {capex_select}
                    CASE WHEN fr.freshness_status = 'fresh' THEN 1.0
                         WHEN fr.freshness_status = 'stale' THEN 0.6
                         WHEN fr.freshness_status = 'expired' THEN 0.2
                         ELSE 0.0 END AS fresh_rate,
                    coalesce(fr.freshness_status, 'unknown') AS freshness_status,
                    ml.latest_trade_date, ml.latest_price, ml.change_1d_pct,
                    CASE WHEN m20.close_20d IS NULL OR m20.close_20d = 0 THEN NULL
                         ELSE (m20.latest_close / m20.close_20d - 1) * 100 END AS change_20d_pct
                FROM mapping_base b
                LEFT JOIN stocks s ON s.code = b.code
                LEFT JOIN latest_score sc ON sc.mapping_id = b.mapping_id
                LEFT JOIN latest_gap g ON g.mapping_id = b.mapping_id
                LEFT JOIN latest_stage st ON st.mapping_id = b.mapping_id
                LEFT JOIN l8 ON l8.mapping_id = b.mapping_id
                LEFT JOIN facts f ON f.mapping_id = b.mapping_id
                {capex_join}
                LEFT JOIN business_tag_evidence_freshness fr ON fr.mapping_id = b.mapping_id
                LEFT JOIN market_latest ml ON ml.code = b.code
                LEFT JOIN market_20d m20 ON m20.code = b.code
                """,
            )
            columns = [desc[0] for desc in cur.description]
            capex_context = _load_bigtech_capex_context()
            scored = [_score_supply_chain_candidate_row(dict(zip(columns, row)), capex_context) for row in cur.fetchall()]
            aggregated = _aggregate_supply_chain_candidate_rows(scored)
            if safe_chain_id:
                aggregated = [item for item in aggregated if item.get("chain_id") == safe_chain_id]
            if safe_signal:
                aggregated = [item for item in aggregated if item.get("signal") == safe_signal]
            by_chain: dict[str, list[dict[str, Any]]] = {}
            for item in aggregated:
                by_chain.setdefault(str(item.get("chain_id")), [])
                if len(by_chain[str(item.get("chain_id"))]) < safe_top_n:
                    by_chain[str(item.get("chain_id"))].append(item)
            signal_distribution: dict[str, int] = {}
            for item in aggregated:
                signal_distribution[str(item.get("signal"))] = signal_distribution.get(str(item.get("signal")), 0) + 1
            payload["source_status"] = "ready" if aggregated else "empty"
            payload["summary"] = {
                "mapping_rows": len(scored),
                "company_chain_rows": len(aggregated),
                "chain_count": len({item.get("chain_id") for item in aggregated}),
                "signal_distribution": signal_distribution,
                "bigtech_capex_context": {
                    "company_count": capex_context.get("company_count", 0),
                    "record_count": capex_context.get("record_count", 0),
                    "companies": capex_context.get("companies", []),
                },
            }
            payload["items"] = aggregated[:safe_top_n]
            payload["by_chain"] = by_chain
    except Exception as e:
        payload["source_status"] = "degraded"
        payload["error"] = str(e)
        payload["limitations"].append("PostgreSQL candidate ranking lookup failed")
    return payload


def _review_business_tag_evidence(
    event_id: str,
    request: BusinessTagEvidenceReviewRequest,
) -> dict[str, Any]:
    review_status = str(request.review_status or "").strip()
    decision_by_status = {
        "approved": "approved",
        "rejected": "rejected",
        "pending_review": "needs_more_evidence",
    }
    if review_status not in decision_by_status:
        raise HTTPException(status_code=400, detail=f"Invalid review_status '{request.review_status}'")
    if not event_id:
        raise HTTPException(status_code=400, detail="event_id is required")
    try:
        result = evidence_review_service.review_event(
            event_id=event_id,
            decision=decision_by_status[review_status],
            reviewer=request.reviewer,
            note=request.note,
            confidence=request.confidence,
            stage_after=request.stage_after,
        )
        stage_record = result.get("stage_record")
        return {
            **result,
            "version": "supply-chain-v2-evidence-review",
            "event_id": event_id,
            "review_status": review_status,
            "stage_updated": bool(stage_record),
            "limitations": list(result.get("limitations") or []),
        }
    except HTTPException:
        raise
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except Exception as e:
        logger.warning("business tag evidence review failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Evidence review failed: {e}") from e


def _map_stage_tracking_row(row) -> dict[str, Any]:
    return {
        "stage_id": str(row[0]),
        "trade_date": str(row[1]) if row[1] else None,
        "research_stage": str(row[2] or "R0"),
        "commercialization_stage": str(row[3] or "C0"),
        "stage_reason": row[4],
        "source_event_id": row[5],
        "last_stage_change_date": str(row[6]) if row[6] else None,
        "review_status": str(row[7] or "pending_review"),
        "created_at": str(row[8]) if row[8] else None,
        "stage_confirmed": bool(row[5] and str(row[7] or "") == "approved"),
    }


def _query_business_tag_stage(mapping_id: str) -> dict[str, Any]:
    if not mapping_id:
        payload = _default_business_tag_stage(mapping_id)
        payload["source_status"] = "invalid_mapping_id"
        payload["limitations"].append("mapping_id is empty")
        return payload

    evidence_payload = _query_business_tag_evidence(mapping_id)
    evidence_count = int(evidence_payload.get("event_count") or 0)
    payload = _default_business_tag_stage(mapping_id, evidence_count=evidence_count)
    payload["mapping"] = evidence_payload.get("mapping")

    try:
        with _pg_connect() as pg:
            cur = pg.cursor()
            if not _pg_table_exists(cur, "business_tag_stage_tracking"):
                payload["source_status"] = "stage_table_missing"
                payload["limitations"].append("business_tag_stage_tracking table is missing")
                return payload

            cur.execute(
                """
                SELECT stage_id, trade_date, research_stage, commercialization_stage,
                       stage_reason, source_event_id, last_stage_change_date,
                       review_status, created_at
                FROM business_tag_stage_tracking
                WHERE mapping_id = %s
                ORDER BY trade_date DESC, created_at DESC
                LIMIT 100
                """,
                (mapping_id,),
            )
            rows = cur.fetchall()
            if not rows:
                if evidence_count:
                    inferred_stage = _stage_from_evidence_events(evidence_payload.get("events") or [])
                    payload["current_stage"] = inferred_stage
                    payload["source_status"] = "evidence_inferred" if inferred_stage["stage_confirmed"] else "evidence_pending_stage_review"
                    payload["limitations"].append("已有证据事件，但还没有形成正式阶段跟踪记录")
                elif evidence_payload.get("source_status") == "mapping_not_found":
                    payload["source_status"] = "mapping_not_found"
                    payload["limitations"].append("未找到业务标签映射，无法判断阶段")
                return payload

            history = [_map_stage_tracking_row(row) for row in rows]
            current = history[0]
            payload.update({
                "source": "business_tag_stage_tracking",
                "source_status": "ready",
                "current_stage": {
                    "research_stage": current["research_stage"],
                    "commercialization_stage": current["commercialization_stage"],
                    "stage_reason": current["stage_reason"],
                    "stage_confirmed": current["stage_confirmed"],
                    "review_status": current["review_status"],
                    "source_event_id": current["source_event_id"],
                    "last_stage_change_date": current["last_stage_change_date"],
                },
                "history": history,
            })
    except Exception as e:
        payload["source_status"] = "degraded"
        payload["error"] = str(e)
        payload["limitations"].append("PostgreSQL stage lookup failed")
    return payload


def _query_business_tag_evidence_chain(mapping_id: str) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "version": "supply-chain-evidence-chain-v1",
        "mapping_id": mapping_id,
        "source_status": "unknown",
        "documents": [],
        "facts": [],
        "freshness": {},
        "stage_transitions": [],
        "expectations": [],
        "limitations": [],
    }
    if not mapping_id:
        payload["source_status"] = "invalid_mapping_id"
        payload["limitations"].append("mapping_id is empty")
        return payload

    required_tables = [
        "raw_evidence_documents",
        "evidence_extracted_facts",
        "business_tag_evidence_freshness",
        "business_tag_stage_transition_log",
        "business_tag_expectation_monitor",
    ]
    try:
        with _pg_connect() as pg:
            cur = pg.cursor()
            missing = [table for table in required_tables if not _pg_table_exists(cur, table)]
            if missing:
                payload["source_status"] = "table_missing"
                payload["limitations"].append(f"missing evidence-chain tables: {', '.join(missing)}")
                return payload

            cur.execute(
                """
                SELECT f.fact_id, f.doc_id, f.company_code, f.chain_id, f.l5_tag,
                       f.l6_route, f.business_segment, f.fact_type, f.fact_nature,
                       f.fact_value, f.original_quote, f.source_level, f.confidence,
                       f.confidence_cap, f.research_stage_signal,
                       f.commercial_stage_signal, f.growth_signal, f.profit_signal,
                       f.moat_signal, f.risk_signal, f.validation_status,
                       f.evidence_event_id, f.metadata, f.created_at
                FROM evidence_extracted_facts f
                WHERE f.mapping_id = %s
                ORDER BY f.created_at DESC
                LIMIT 200
                """,
                (mapping_id,),
            )
            fact_rows = cur.fetchall()
            payload["facts"] = [
                {
                    "fact_id": str(row[0]),
                    "doc_id": row[1],
                    "company_code": row[2],
                    "chain_id": row[3],
                    "l5_tag": row[4],
                    "l6_route": row[5],
                    "business_segment": row[6],
                    "fact_type": row[7],
                    "fact_nature": row[8],
                    "fact_value": row[9],
                    "original_quote": row[10],
                    "source_level": row[11],
                    "confidence": _to_float(row[12], 0.0),
                    "confidence_cap": _to_float(row[13], 0.0),
                    "research_stage_signal": row[14],
                    "commercial_stage_signal": row[15],
                    "growth_signal": bool(row[16]),
                    "profit_signal": bool(row[17]),
                    "moat_signal": bool(row[18]),
                    "risk_signal": bool(row[19]),
                    "validation_status": row[20],
                    "evidence_event_id": row[21],
                    "metadata": _json_or_default(row[22], {}),
                    "created_at": str(row[23]) if row[23] else None,
                }
                for row in fact_rows
            ]

            doc_ids = [row[1] for row in fact_rows if row[1]]
            if doc_ids:
                cur.execute(
                    """
                    SELECT doc_id, source_id, source_type, source_level, company_code,
                           company_name, title, publish_time, crawl_time, url,
                           content_hash, doc_status, license_status, metadata
                    FROM raw_evidence_documents
                    WHERE doc_id = ANY(%s)
                    ORDER BY COALESCE(publish_time, crawl_time) DESC
                    LIMIT 200
                    """,
                    (doc_ids,),
                )
                payload["documents"] = [
                    {
                        "doc_id": str(row[0]),
                        "source_id": row[1],
                        "source_type": row[2],
                        "source_level": row[3],
                        "company_code": row[4],
                        "company_name": row[5],
                        "title": row[6],
                        "publish_time": str(row[7]) if row[7] else None,
                        "crawl_time": str(row[8]) if row[8] else None,
                        "url": row[9],
                        "content_hash": row[10],
                        "doc_status": row[11],
                        "license_status": row[12],
                        "metadata": _json_or_default(row[13], {}),
                    }
                    for row in cur.fetchall()
                ]

            cur.execute(
                """
                SELECT last_strong_evidence_date, last_mid_evidence_date,
                       last_weak_signal_date, last_any_evidence_date,
                       days_since_update, freshness_status, next_review_date,
                       stale_reason, updated_at
                FROM business_tag_evidence_freshness
                WHERE mapping_id = %s
                LIMIT 1
                """,
                (mapping_id,),
            )
            row = cur.fetchone()
            if row:
                payload["freshness"] = {
                    "last_strong_evidence_date": str(row[0]) if row[0] else None,
                    "last_mid_evidence_date": str(row[1]) if row[1] else None,
                    "last_weak_signal_date": str(row[2]) if row[2] else None,
                    "last_any_evidence_date": str(row[3]) if row[3] else None,
                    "days_since_update": row[4],
                    "freshness_status": row[5],
                    "next_review_date": str(row[6]) if row[6] else None,
                    "stale_reason": row[7],
                    "updated_at": str(row[8]) if row[8] else None,
                }

            cur.execute(
                """
                SELECT transition_id, old_research_stage, new_research_stage,
                       old_commercial_stage, new_commercial_stage, trigger_fact_id,
                       trigger_event_id, change_reason, review_status, created_at
                FROM business_tag_stage_transition_log
                WHERE mapping_id = %s
                ORDER BY created_at DESC
                LIMIT 100
                """,
                (mapping_id,),
            )
            payload["stage_transitions"] = [
                {
                    "transition_id": str(row[0]),
                    "old_research_stage": row[1],
                    "new_research_stage": row[2],
                    "old_commercial_stage": row[3],
                    "new_commercial_stage": row[4],
                    "trigger_fact_id": row[5],
                    "trigger_event_id": row[6],
                    "change_reason": row[7],
                    "review_status": row[8],
                    "created_at": str(row[9]) if row[9] else None,
                }
                for row in cur.fetchall()
            ]

            cur.execute(
                """
                SELECT monitor_id, claim_text, claim_date, claim_source_type,
                       expected_result, expected_date, actual_progress,
                       gap_status, market_price_change, evidence_ids,
                       source_doc_id, review_status, metadata, created_at
                FROM business_tag_expectation_monitor
                WHERE mapping_id = %s
                ORDER BY created_at DESC
                LIMIT 100
                """,
                (mapping_id,),
            )
            payload["expectations"] = [
                {
                    "monitor_id": str(row[0]),
                    "claim_text": row[1],
                    "claim_date": str(row[2]) if row[2] else None,
                    "claim_source_type": row[3],
                    "expected_result": row[4],
                    "expected_date": str(row[5]) if row[5] else None,
                    "actual_progress": row[6],
                    "gap_status": row[7],
                    "market_price_change": _to_float(row[8], None),
                    "evidence_ids": _json_or_default(row[9], []),
                    "source_doc_id": row[10],
                    "review_status": row[11],
                    "metadata": _json_or_default(row[12], {}),
                    "created_at": str(row[13]) if row[13] else None,
                }
                for row in cur.fetchall()
            ]

            payload["source_status"] = "ready"
    except Exception as e:
        payload["source_status"] = "degraded"
        payload["error"] = str(e)
        payload["limitations"].append("PostgreSQL evidence-chain lookup failed")
    return payload


def _query_evidence_review_queue(limit: int = 50) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "version": "supply-chain-evidence-review-queue-v1",
        "queue": [],
        "counts": {
            "stage_transitions": 0,
            "stale_evidence": 0,
            "expectations": 0,
        },
        "limitations": [],
    }
    capped_limit = max(1, min(int(limit or 50), 200))
    try:
        with _pg_connect() as pg:
            cur = pg.cursor()
            required_tables = [
                "business_tag_stage_transition_log",
                "business_tag_evidence_freshness",
                "business_tag_expectation_monitor",
            ]
            missing = [table for table in required_tables if not _pg_table_exists(cur, table)]
            if missing:
                payload["limitations"].append(f"missing evidence review tables: {', '.join(missing)}")
                return payload

            cur.execute(
                """
                SELECT transition_id, mapping_id, new_research_stage,
                       new_commercial_stage, change_reason, review_status, created_at
                FROM business_tag_stage_transition_log
                WHERE review_status = 'pending_review'
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (capped_limit,),
            )
            stage_items = [
                {
                    "queue_type": "stage_transition",
                    "id": str(row[0]),
                    "mapping_id": row[1],
                    "title": f"阶段待复核 {row[2] or ''}/{row[3] or ''}".strip(),
                    "summary": row[4],
                    "review_status": row[5],
                    "created_at": str(row[6]) if row[6] else None,
                }
                for row in cur.fetchall()
            ]
            payload["counts"]["stage_transitions"] = len(stage_items)

            cur.execute(
                """
                SELECT mapping_id, freshness_status, days_since_update,
                       stale_reason, next_review_date, updated_at
                FROM business_tag_evidence_freshness
                WHERE freshness_status IN ('stale','expired','unknown')
                ORDER BY
                    CASE freshness_status WHEN 'expired' THEN 0 WHEN 'unknown' THEN 1 ELSE 2 END,
                    next_review_date ASC NULLS FIRST
                LIMIT %s
                """,
                (capped_limit,),
            )
            freshness_items = [
                {
                    "queue_type": "evidence_freshness",
                    "id": str(row[0]),
                    "mapping_id": row[0],
                    "title": f"证据状态 {row[1]}",
                    "summary": row[3],
                    "freshness_status": row[1],
                    "days_since_update": row[2],
                    "next_review_date": str(row[4]) if row[4] else None,
                    "created_at": str(row[5]) if row[5] else None,
                }
                for row in cur.fetchall()
            ]
            payload["counts"]["stale_evidence"] = len(freshness_items)

            cur.execute(
                """
                SELECT monitor_id, mapping_id, claim_text, gap_status,
                       review_status, created_at
                FROM business_tag_expectation_monitor
                WHERE gap_status = 'pending'
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (capped_limit,),
            )
            expectation_items = [
                {
                    "queue_type": "expectation_monitor",
                    "id": str(row[0]),
                    "mapping_id": row[1],
                    "title": "预期差待验证",
                    "summary": row[2],
                    "gap_status": row[3],
                    "review_status": row[4],
                    "created_at": str(row[5]) if row[5] else None,
                }
                for row in cur.fetchall()
            ]
            payload["counts"]["expectations"] = len(expectation_items)

            payload["queue"] = (stage_items + freshness_items + expectation_items)[:capped_limit]
    except Exception as e:
        payload["error"] = str(e)
        payload["limitations"].append("PostgreSQL evidence review queue lookup failed")
    return payload


def _query_capex_evidence_review_queue(
    limit: int = 50,
    chain_id: Optional[str] = None,
    review_status: str = "pending_review",
) -> dict[str, Any]:
    capped_limit = max(1, min(int(limit or 50), 200))
    safe_chain_id = str(chain_id or "").strip() or None
    safe_status = str(review_status or "pending_review").strip()
    allowed_statuses = {"pending_review", "approved", "rejected"}
    if safe_status not in allowed_statuses:
        safe_status = "pending_review"
    payload: dict[str, Any] = {
        "version": "business-tag-capex-evidence-review-queue-v1",
        "source_status": "unknown",
        "filters": {"limit": capped_limit, "chain_id": safe_chain_id, "review_status": safe_status},
        "counts": {},
        "queue": [],
        "limitations": [],
    }
    try:
        with _pg_connect() as pg:
            cur = pg.cursor()
            if not _pg_table_exists(cur, "business_tag_capex_evidence"):
                payload["source_status"] = "missing_table"
                payload["limitations"].append("business_tag_capex_evidence table is missing")
                return payload
            params: list[Any] = [safe_status]
            chain_filter = ""
            if safe_chain_id:
                chain_filter = "AND c.chain_id = %s"
                params.append(safe_chain_id)
            cur.execute(
                f"""
                SELECT c.review_status, count(*)
                FROM business_tag_capex_evidence c
                WHERE 1=1 {chain_filter}
                GROUP BY c.review_status
                """,
                params[1:] if safe_chain_id else [],
            )
            payload["counts"] = {str(row[0]): int(row[1]) for row in cur.fetchall()}
            params.append(capped_limit)
            cur.execute(
                f"""
                SELECT
                    c.capex_evidence_id, c.mapping_id, c.code,
                    coalesce(c.company_name, s.name, c.code) AS company_name,
                    coalesce(c.chain_id, m.chain_id, '') AS chain_id,
                    coalesce(c.node_id, m.node_id, '') AS node_id,
                    coalesce(m.tag_name, '') AS tag_name,
                    c.fiscal_period, c.as_of_date, c.capex_amount,
                    c.capex_amount_unit, c.currency, c.capex_direction,
                    c.mapped_layer_id, c.mapped_segments, c.source_type,
                    c.source_level, c.source_name, c.source_url, c.quote,
                    c.evidence_level, c.confidence, c.review_status,
                    c.amount_is_total_capex, c.amount_is_segment_capex,
                    c.direction_is_ai_related, c.metadata, c.created_at
                FROM business_tag_capex_evidence c
                LEFT JOIN business_tag_mapping m ON m.mapping_id = c.mapping_id
                LEFT JOIN stocks s ON s.code = c.code
                WHERE c.review_status = %s {chain_filter}
                ORDER BY
                    c.direction_is_ai_related DESC,
                    c.confidence DESC,
                    c.as_of_date DESC,
                    c.created_at DESC
                LIMIT %s
                """,
                params,
            )
            payload["queue"] = [
                {
                    "capex_evidence_id": str(row[0]),
                    "mapping_id": str(row[1]),
                    "code": str(row[2]),
                    "company_name": str(row[3] or ""),
                    "chain_id": str(row[4] or ""),
                    "node_id": str(row[5] or ""),
                    "tag_name": str(row[6] or ""),
                    "fiscal_period": str(row[7] or ""),
                    "as_of_date": str(row[8]) if row[8] else None,
                    "capex_amount": _to_float(row[9], None),
                    "capex_amount_unit": str(row[10] or ""),
                    "currency": str(row[11] or ""),
                    "capex_direction": _json_or_default(row[12], []),
                    "mapped_layer_id": str(row[13] or ""),
                    "mapped_segments": _json_or_default(row[14], []),
                    "source_type": str(row[15] or ""),
                    "source_level": str(row[16] or ""),
                    "source_name": str(row[17] or ""),
                    "source_url": str(row[18] or ""),
                    "quote": str(row[19] or ""),
                    "evidence_level": str(row[20] or ""),
                    "confidence": _to_float(row[21], 0.0),
                    "review_status": str(row[22] or ""),
                    "amount_is_total_capex": bool(row[23]),
                    "amount_is_segment_capex": bool(row[24]),
                    "direction_is_ai_related": bool(row[25]),
                    "metadata": _json_or_default(row[26], {}),
                    "created_at": str(row[27]) if row[27] else None,
                }
                for row in cur.fetchall()
            ]
            payload["source_status"] = "ready"
    except Exception as e:
        payload["source_status"] = "degraded"
        payload["error"] = str(e)
        payload["limitations"].append("PostgreSQL CAPEX evidence review queue lookup failed")
    return payload


def _review_capex_evidence(
    capex_evidence_id: str,
    request: BusinessTagEvidenceReviewRequest,
) -> dict[str, Any]:
    allowed_statuses = {"approved", "rejected", "pending_review"}
    review_status = str(request.review_status or "").strip()
    if review_status not in allowed_statuses:
        raise HTTPException(status_code=400, detail=f"Invalid review_status '{request.review_status}'")
    if not capex_evidence_id:
        raise HTTPException(status_code=400, detail="capex_evidence_id is required")
    try:
        with _pg_connect() as pg:
            cur = pg.cursor()
            if not _pg_table_exists(cur, "business_tag_capex_evidence"):
                raise HTTPException(status_code=503, detail="business_tag_capex_evidence table is missing")
            cur.execute(
                """
                SELECT capex_evidence_id, mapping_id, code, review_status, confidence
                FROM business_tag_capex_evidence
                WHERE capex_evidence_id = %s
                LIMIT 1
                """,
                (capex_evidence_id,),
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail=f"CAPEX evidence '{capex_evidence_id}' not found")
            confidence = request.confidence if request.confidence is not None else _to_float(row[4], 0.0)
            metadata_patch = {
                "reviewer": request.reviewer,
                "review_note": request.note,
                "reviewed_at": datetime.now().isoformat(timespec="seconds"),
            }
            cur.execute(
                """
                UPDATE business_tag_capex_evidence
                SET review_status = %s,
                    confidence = %s,
                    metadata = metadata || %s::jsonb,
                    updated_at = CURRENT_TIMESTAMP
                WHERE capex_evidence_id = %s
                """,
                (
                    review_status,
                    confidence,
                    json.dumps(metadata_patch, ensure_ascii=False),
                    capex_evidence_id,
                ),
            )
            pg.commit()
            return {
                "version": "business-tag-capex-evidence-review-v1",
                "capex_evidence_id": str(row[0]),
                "mapping_id": str(row[1] or ""),
                "code": str(row[2] or ""),
                "previous_review_status": str(row[3] or ""),
                "review_status": review_status,
                "confidence": confidence,
                "reviewer": request.reviewer,
            }
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("CAPEX evidence review failed: %s", e)
        raise HTTPException(status_code=500, detail=f"CAPEX evidence review failed: {e}") from e


def _mapping_source_from_evidence(evidence: object) -> str:
    payload = _json_or_default(evidence, {})
    if isinstance(payload, dict):
        return str(payload.get("mapping_source") or payload.get("source") or "")
    return ""


def _mapping_evidence_items(evidence: object) -> list:
    payload = _json_or_default(evidence, {})
    if isinstance(payload, dict):
        items = payload.get("evidence") or []
        return items if isinstance(items, list) else [items]
    return []


def _mapping_evidence_gaps(evidence: object) -> list:
    payload = _json_or_default(evidence, {})
    if isinstance(payload, dict):
        gaps = payload.get("evidence_gaps") or []
        return gaps if isinstance(gaps, list) else [gaps]
    return []


def _mapping_review_priority(status: str, confidence: float, source: str) -> float:
    status_base = {"pending_review": 45.0, "weak_evidence": 35.0, "needs_more_evidence": 40.0}.get(status, 10.0)
    source_base = {"industry": 22.0, "introduction": 18.0, "research_report": 14.0, "main_business": 8.0}.get(source, 12.0)
    confidence_gap = max(0.0, 1.0 - confidence) * 25.0
    return round(status_base + source_base + confidence_gap, 2)


def _query_supply_chain_mapping_review_queue(
    status: str = "reviewable",
    node_id: Optional[str] = None,
    chain_id: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    statuses = ["pending_review", "weak_evidence"] if status == "reviewable" else [status]
    safe_limit = max(1, min(int(limit or 50), 200))
    safe_offset = max(0, int(offset or 0))
    conditions = ["m.status = ANY(%s)"]
    params: list[object] = [statuses]
    if node_id:
        conditions.append("m.node_id = %s")
        params.append(node_id)
    if chain_id:
        conditions.append("COALESCE(n.chain_id, c.evidence->>'chain_id') = %s")
        params.append(chain_id)
    where = " AND ".join(conditions)
    fallback_reason = None
    try:
        with _pg_connect() as pg:
            cur = pg.cursor()
            cur.execute(
                f"""
                SELECT COUNT(*) OVER() AS total_count,
                       m.code, COALESCE(s.name, m.code) AS name,
                       m.node_id, COALESCE(n.name, cn.node_name, m.node_id) AS node_name,
                       COALESCE(n.chain_id, c.evidence->>'chain_id') AS chain_id,
                       m.product_name, m.material_name, m.confidence, m.status,
                       c.evidence, m.updated_at
                FROM company_bom_mapping m
                LEFT JOIN stocks s ON s.code = m.code
                LEFT JOIN supply_chain_bom_nodes n ON n.node_id = m.node_id
                LEFT JOIN chain_nodes cn ON cn.node_id = m.node_id
                LEFT JOIN company_chain_mapping c ON c.code = m.code AND c.node_id = m.node_id
                WHERE {where}
                ORDER BY
                    CASE m.status WHEN 'pending_review' THEN 1 WHEN 'weak_evidence' THEN 2 ELSE 3 END,
                    m.confidence DESC,
                    m.updated_at DESC NULLS LAST
                LIMIT %s OFFSET %s
                """,
                [*params, safe_limit, safe_offset],
            )
            rows = cur.fetchall()
    except Exception as e:
        logger.debug("supply_chain mapping review queue unavailable: %s", e)
        return {"total": 0, "limit": safe_limit, "offset": safe_offset, "items": []}

    total = int(rows[0][0] or 0) if rows else 0
    items = []
    for row in rows:
        evidence = row[10]
        confidence = _to_float(row[8], 0.0)
        mapping_source = _mapping_source_from_evidence(evidence)
        mapping_status = str(row[9] or "")
        items.append({
            "code": str(row[1] or ""),
            "name": str(row[2] or ""),
            "node_id": str(row[3] or ""),
            "node_name": str(row[4] or ""),
            "chain_id": str(row[5] or ""),
            "product_name": row[6],
            "material_name": row[7],
            "confidence": confidence,
            "status": mapping_status,
            "mapping_source": mapping_source,
            "evidence": _mapping_evidence_items(evidence),
            "evidence_gaps": _mapping_evidence_gaps(evidence),
            "updated_at": str(row[11] or ""),
            "review_priority": _mapping_review_priority(mapping_status, confidence, mapping_source),
        })
    items.sort(key=lambda item: item["review_priority"], reverse=True)
    return {"total": total, "limit": safe_limit, "offset": safe_offset, "items": items}


def _query_supply_chain_mapping_quality() -> dict:
    status_counts: dict[str, int] = {}
    source_counts: dict[str, int] = {}
    hotspot_nodes: list[dict] = []
    try:
        with _pg_connect() as pg:
            cur = pg.cursor()
            cur.execute("SELECT status, COUNT(*) FROM company_bom_mapping GROUP BY status")
            for status, count in cur.fetchall():
                status_counts[str(status or "")] = int(count or 0)

            cur.execute("""
                SELECT COALESCE(c.evidence->>'mapping_source', 'unknown') AS mapping_source, COUNT(*)
                FROM company_bom_mapping m
                LEFT JOIN company_chain_mapping c ON c.code = m.code AND c.node_id = m.node_id
                GROUP BY mapping_source
            """)
            for source, count in cur.fetchall():
                source_counts[str(source or "unknown")] = int(count or 0)

            cur.execute("""
                SELECT m.node_id,
                       COALESCE(n.name, cn.node_name, m.node_id) AS node_name,
                       COALESCE(n.chain_id, c.evidence->>'chain_id') AS chain_id,
                       COUNT(*) FILTER (WHERE m.status = 'verified') AS verified,
                       COUNT(*) FILTER (WHERE m.status = 'pending_review') AS pending_review,
                       COUNT(*) FILTER (WHERE m.status = 'weak_evidence') AS weak_evidence,
                       COUNT(*) FILTER (WHERE m.status = 'rejected') AS rejected
                FROM company_bom_mapping m
                LEFT JOIN supply_chain_bom_nodes n ON n.node_id = m.node_id
                LEFT JOIN chain_nodes cn ON cn.node_id = m.node_id
                LEFT JOIN company_chain_mapping c ON c.code = m.code AND c.node_id = m.node_id
                GROUP BY m.node_id, n.name, cn.node_name, n.chain_id, c.evidence->>'chain_id'
                ORDER BY
                    (COUNT(*) FILTER (WHERE m.status IN ('pending_review', 'weak_evidence'))) DESC,
                    m.node_id
                LIMIT 50
            """)
            for row in cur.fetchall():
                pending = int(row[4] or 0)
                weak = int(row[5] or 0)
                hotspot_nodes.append({
                    "node_id": str(row[0] or ""),
                    "node_name": str(row[1] or ""),
                    "chain_id": str(row[2] or ""),
                    "verified": int(row[3] or 0),
                    "pending_review": pending,
                    "weak_evidence": weak,
                    "rejected": int(row[6] or 0),
                    "review_pressure": pending + weak,
                })
    except Exception as e:
        logger.debug("supply_chain mapping quality unavailable: %s", e)

    return {
        "mapping_count": sum(status_counts.values()),
        "status_counts": status_counts,
        "source_counts": source_counts,
        "review_queue_count": status_counts.get("pending_review", 0) + status_counts.get("weak_evidence", 0),
        "hotspot_nodes": hotspot_nodes,
    }


def _apply_supply_chain_mapping_review(
    code: str,
    node_id: str,
    decision: str,
    reviewer: str = "system",
    note: str = "",
) -> dict:
    from psycopg2.extras import Json

    status_by_decision = {
        "verified": "verified",
        "rejected": "rejected",
        "needs_more_evidence": "weak_evidence",
        "pending_review": "pending_review",
    }
    if decision not in status_by_decision:
        return {"status": "error", "reason": f"unsupported decision: {decision}"}
    mapping_status = status_by_decision[decision]
    review = {
        "decision": decision,
        "reviewer": reviewer or "system",
        "note": note or "",
        "reviewed_at": datetime.now().isoformat(timespec="seconds"),
    }
    try:
        with _pg_connect() as pg:
            cur = pg.cursor()
            cur.execute(
                """
                UPDATE company_bom_mapping
                SET status = %s, updated_at = CURRENT_TIMESTAMP
                WHERE code = %s AND node_id = %s
                """,
                (mapping_status, code, node_id),
            )
            if cur.rowcount == 0:
                pg.rollback()
                return {"status": "not_found", "reason": "mapping not found", "code": code, "node_id": node_id}

            cur.execute(
                """
                SELECT id, evidence
                FROM company_chain_mapping
                WHERE code = %s AND node_id = %s
                """,
                (code, node_id),
            )
            for row_id, evidence in cur.fetchall():
                payload = _json_or_default(evidence, {})
                if not isinstance(payload, dict):
                    payload = {}
                payload["status"] = mapping_status
                payload["review"] = review
                cur.execute(
                    "UPDATE company_chain_mapping SET evidence = %s WHERE id = %s",
                    (Json(payload), row_id),
                )
            pg.commit()
    except Exception as e:
        logger.warning("supply_chain mapping review update failed: %s", e)
        return {"status": "error", "reason": str(e), "code": code, "node_id": node_id}

    return {
        "status": "ok",
        "code": code,
        "node_id": node_id,
        "mapping_status": mapping_status,
        "review": review,
    }


def _query_supply_chain_data_freshness() -> dict:
    result = {
        "market": {"latest_trade_date": "", "row_count": 0},
        "research_reports": {"latest_pub_date": "", "row_count": 0},
        "broker_recommend": {"latest_month": "", "row_count": 0},
    }
    try:
        with _pg_connect() as pg:
            cur = pg.cursor()
            cur.execute("SELECT MAX(trade_date), COUNT(*) FROM daily_kline")
            latest, count = cur.fetchone()
            result["market"] = {"latest_trade_date": str(latest or ""), "row_count": int(count or 0)}

            result["research_reports"] = _query_research_report_freshness()

            cur.execute("SELECT MAX(month), COUNT(*) FROM broker_recommend")
            latest, count = cur.fetchone()
            result["broker_recommend"] = {"latest_month": str(latest or ""), "row_count": int(count or 0)}
    except Exception as e:
        logger.debug("supply_chain data freshness unavailable: %s", e)
    return result


def _query_research_report_freshness() -> dict:
    result = {"latest_pub_date": "", "row_count": 0}
    try:
        with _pg_connect() as pg:
            cur = pg.cursor()
            cur.execute("SELECT MAX(pub_date), COUNT(*) FROM research_reports_tushare")
            latest, count = cur.fetchone()
            return {"latest_pub_date": str(latest or ""), "row_count": int(count or 0)}
    except Exception as e:
        logger.debug("supply_chain research report freshness unavailable: %s", e)
        return result


def _query_recent_research_reports(limit: int = 5, keyword: Optional[str] = None) -> list[dict]:
    safe_limit = max(1, min(int(limit or 5), 20))
    params: list[object] = []
    where = ""
    if keyword:
        keyword_text = str(keyword).strip()
        if keyword_text:
            where = "WHERE title ILIKE %s OR broker ILIKE %s OR code = %s"
            params.extend([f"%{keyword_text}%", f"%{keyword_text}%", keyword_text])
    try:
        with _pg_connect() as pg:
            cur = pg.cursor()
            cur.execute(
                f"""
                SELECT code, pub_date, title, broker, rating, target_price
                FROM research_reports_tushare
                {where}
                ORDER BY pub_date DESC NULLS LAST, code
                LIMIT %s
                """,
                [*params, safe_limit],
            )
            return [{
                "code": str(row[0] or ""),
                "pub_date": str(row[1] or ""),
                "title": str(row[2] or ""),
                "broker": str(row[3] or ""),
                "rating": str(row[4] or "") if row[4] is not None else "",
                "target_price": _to_float(row[5], None),
            } for row in cur.fetchall()]
    except Exception as e:
        logger.debug("supply_chain recent research reports unavailable: %s", e)
        return []


def _research_report_text(report: dict) -> str:
    return "\n".join([
        f"研报标题：{report.get('title') or ''}",
        f"股票代码：{report.get('code') or ''}",
        f"发布日期：{report.get('pub_date') or ''}",
        f"机构/覆盖对象：{report.get('broker') or ''}",
        f"评级：{report.get('rating') or ''}",
        f"目标价：{report.get('target_price') or ''}",
        "说明：当前Tushare研报表提供的是研报元数据，若需全文证据，需要接入研报PDF/正文解析后再进入LLM抽取。",
    ])


def _persist_policy_interpretation(
    text: str,
    source: dict[str, Any] | None,
    interpretation: dict[str, Any],
    usage: LLMUsageInfo,
) -> dict[str, Any]:
    """Persist policy interpretation result to policy_interpretations table.

    Args:
        text: Original policy text
        source: Source metadata (title, url, etc.)
        interpretation: Parsed interpretation dict from LLM
        usage: Token usage telemetry

    Returns:
        Dict with status and inserted row id
    """
    source = source or {}
    try:
        with _pg_connect() as pg:
            cur = pg.cursor()
            cur.execute(
                """
                INSERT INTO policy_interpretations
                    (source_type, source_content, source_url, interpreted_themes, model_used, tokens_used, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    source.get("source_type", "manual"),
                    text,
                    source.get("source_url"),
                    json.dumps(interpretation, ensure_ascii=False),
                    f"{usage.provider}/{usage.model}",
                    usage.total_tokens,
                    datetime.now(),
                ),
            )
            row_id = cur.fetchone()[0]
            pg.commit()
            return {"status": "ok", "id": row_id}
    except Exception as e:
        logger.warning("policy_interpretation persist failed: %s", e)
        return {"status": "error", "reason": str(e)}
