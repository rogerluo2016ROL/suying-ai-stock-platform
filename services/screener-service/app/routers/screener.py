"""Screener API routes — 12 screening modes via unified endpoint with Redis caching."""

import asyncio
import json
import logging
import math
import os
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Optional
from fastapi import APIRouter, Body, Query, HTTPException

import numpy as np

from app.config import AVAILABLE_MODES, DEFAULT_TOP_N, MAX_TOP_N

logger = logging.getLogger("screener.routes")

router = APIRouter(prefix="/api/v1/screener", tags=["screener"])


def _normalize_picks(picks: list, mode: str) -> list:
    """Normalize engine-specific field names to frontend-expected fields.

    Frontend expects: price, score, grade, entry_price, stop_loss, target_price
    Different engines use different names, so we normalize here.
    """
    for p in picks:
        # Normalize price
        if "price" not in p:
            if "close" in p:
                p["price"] = p["close"]
            elif "current_price" in p:
                p["price"] = p["current_price"]
            # leader_auction: no price field, use default placeholder
            elif "gap_pct" in p:
                p["price"] = 0  # auction mode doesn't store price

        # Normalize score
        if "score" not in p:
            if "total_score" in p:
                p["score"] = p["total_score"]
            elif "composite_score" in p:
                p["score"] = p["composite_score"]
            elif "gap_score" in p:
                p["score"] = p.get("total_score", 5.0)

        # Normalize grade (default B if missing)
        if "grade" not in p:
            sc = p.get("score", 0)
            if sc >= 20: p["grade"] = "S"
            elif sc >= 16: p["grade"] = "A"
            elif sc >= 10: p["grade"] = "B"
            else: p["grade"] = "C"

        # Normalize entry/stop/target (fill None or missing values)
        base_price = p.get("close") or p.get("price") or 0
        if base_price and float(base_price) > 0:
            bp = float(base_price)
            if not p.get("entry_price"):
                p["entry_price"] = round(bp * 1.01, 2)
            if not p.get("stop_loss"):
                p["stop_loss"] = round(bp * 0.93, 2)
            if not p.get("target_price"):
                p["target_price"] = round(bp * 1.15, 2)

        # Ensure numeric types
        for k in ("price", "score", "entry_price", "stop_loss", "target_price"):
            if k in p and p[k] is not None:
                try:
                    p[k] = round(float(p[k]), 2)
                except (ValueError, TypeError):
                    pass

    return picks


def _sanitize_picks(picks: list) -> list:
    """Convert numpy types in picks to native Python types for JSON serialization."""
    def _convert(v):
        if isinstance(v, (np.integer,)):
            return int(v)
        if isinstance(v, (np.floating,)):
            return float(v) if not math.isnan(v) else None
        if isinstance(v, (np.bool_,)):
            return bool(v)
        if isinstance(v, np.ndarray):
            return v.tolist()
        if isinstance(v, dict):
            return {k: _convert(vv) for k, vv in v.items()}
        if isinstance(v, list):
            return [_convert(vv) for vv in v]
        return v
    return [_convert(p) for p in picks]


def _load_supply_chain_bom_payload() -> dict:
    """Load BOM seed config and enrich it for read-only API responses."""
    from kronos_factors.engine.supply_chain_bom import load_bom_config

    cfg = load_bom_config()
    themes = cfg.get("themes", [])
    nodes = cfg.get("nodes", [])
    edges = cfg.get("edges", [])

    theme_by_id = {theme.get("theme_id"): theme for theme in themes}
    children_by_parent = {}
    for node in nodes:
        parent = node.get("parent_node_id")
        if parent:
            children_by_parent.setdefault(parent, []).append(node.get("node_id"))

    enriched_nodes = []
    for node in nodes:
        theme = theme_by_id.get(node.get("theme_id"), {})
        enriched = dict(node)
        enriched["policy_theme"] = theme.get("name", "")
        enriched["bom_path"] = [v for v in (theme.get("name"), node.get("name")) if v]
        enriched["child_node_ids"] = children_by_parent.get(node.get("node_id"), [])
        enriched["companies"] = []
        enriched_nodes.append(enriched)

    node_counts = {}
    for node in enriched_nodes:
        node_counts[node.get("theme_id")] = node_counts.get(node.get("theme_id"), 0) + 1

    enriched_themes = []
    for theme in themes:
        enriched = dict(theme)
        enriched["node_count"] = node_counts.get(theme.get("theme_id"), 0)
        enriched["matrix"] = {
            "policy_weight": theme.get("policy_weight", 1.0),
            "high_growth": None,
            "high_profit": None,
            "high_moat": None,
        }
        enriched_themes.append(enriched)

    return {
        "version": cfg.get("version", "4.0"),
        "source": cfg.get("source", ""),
        "themes": enriched_themes,
        "nodes": enriched_nodes,
        "edges": edges,
    }


def _json_or_default(value, default):
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return default
    return default


def _row_get(row, key, default=None):
    try:
        return row[key]
    except (KeyError, IndexError, TypeError):
        return default


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


def _to_float(value, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return round(float(value), 4)
    except (TypeError, ValueError):
        return default


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
    result = _run_supply_chain_mode("supply_chain", top_n, trade_date)
    picks = _sanitize_picks(result.get("picks", []))
    return [_enrich_supply_chain_candidate(pick, idx) for idx, pick in enumerate(picks[:top_n], start=1)]


def _pg_connect():
    import psycopg2

    return psycopg2.connect(
        os.environ.get("KRONOS_PG_URL", "postgresql://kronos:kronos@localhost:6432/kronos"),
        connect_timeout=5,
    )


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


def _attach_market_snapshots(candidates: list[dict], trade_date: Optional[str] = None) -> list[dict]:
    snapshots = _query_latest_market_snapshots([c.get("code") for c in candidates], trade_date)
    if not snapshots:
        return candidates
    enriched = []
    for candidate in candidates:
        next_candidate = dict(candidate)
        snapshot = snapshots.get(str(candidate.get("code")))
        if snapshot:
            next_candidate.update(snapshot)
        enriched.append(next_candidate)
    return enriched


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
            candidates = _attach_market_snapshots(candidates, trade_date)
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


def _query_research_ingestion_status() -> dict:
    auto_enabled = str(os.environ.get("SUPPLY_CHAIN_REPORT_AUTO_INGEST", "")).lower() in {"1", "true", "yes"}
    llm_enabled = bool(os.environ.get("DEEPSEEK_API_KEY"))
    report_freshness = _query_research_report_freshness()
    source_latest = report_freshness.get("latest_pub_date", "")
    source_count = int(report_freshness.get("row_count", 0) or 0)
    if auto_enabled and llm_enabled:
        status = "enabled"
        message = f"Tushare研报库已接入，最新研报日期 {source_latest or '未知'}；研报自动采集与LLM抽取已启用，抽取结果进入待审核图谱。"
    elif auto_enabled:
        status = "llm_key_missing"
        message = f"Tushare研报库已接入，最新研报日期 {source_latest or '未知'}；研报自动采集已启用，但缺少LLM密钥，暂不能自动抽取图谱。"
    elif source_count > 0:
        status = "local_catalog_available"
        message = f"Tushare研报库已接入，最新研报日期 {source_latest or '未知'}，但LLM批量抽取和图谱写入调度尚未开启。"
    else:
        status = "not_configured"
        message = "当前未发现本地研报库数据，页面仅支持手工粘贴政策、公告、研报文本进行抽取。"
    return {
        "auto_collection_status": status,
        "llm_auto_extract_enabled": auto_enabled and llm_enabled,
        "manual_extract_available": True,
        "batch_extract_endpoint": "/api/v1/screener/supply-chain/research/ingest",
        "source_table": "research_reports_tushare",
        "source_latest_pub_date": source_latest,
        "source_row_count": source_count,
        "message": message,
    }


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
    return {
        "name": "大葱产业链解构选股模型 V4",
        "version": "4.0",
        "philosophy": "政策主题定方向，BOM 拆解定环节，上市公司候选池定标的，商业化、政策、业绩、市场共振定启动信号。",
        "score_dimensions": [
            {"key": "policy", "name": "政策力度", "weight": 15},
            {"key": "bom", "name": "BOM关键度", "weight": 15},
            {"key": "chokepoint", "name": "卡脖子/国产替代", "weight": 15},
            {"key": "commercialization", "name": "商业化阶段", "weight": 15},
            {"key": "growth", "name": "业绩成长", "weight": 15},
            {"key": "profit", "name": "盈利质量", "weight": 10},
            {"key": "moat", "name": "护城河证据", "weight": 10},
            {"key": "market", "name": "市场共振", "weight": 5},
        ],
    }

# Shared thread pool for offloading synchronous screening engines.
# Each /run call is serialized behind a max_workers=3 pool to limit
# concurrent heavy computation (Kronos factor engine + PG queries).
_executor = ThreadPoolExecutor(max_workers=3)


def _auto_save_snapshot(result: dict, mode: str):
    """Auto-save screening results to JSON file and PG (fire-and-forget).

    Called after every successful screening run. Saves to:
      - outputs/snapshots/{mode}/{date}_{time_slot}.json
      - PG screening_snapshots table via recorder.record_picks()
    """
    import json, os
    from datetime import datetime

    picks = result.get("picks", [])
    if not picks:
        return

    trade_date = result.get("trade_date") or datetime.now().strftime("%Y-%m-%d")
    time_slot = result.get("time_slot") or datetime.now().strftime("%H:%M")

    # 1) JSON file snapshot
    try:
        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
        snap_dir = os.path.join(repo_root, "outputs", "snapshots", mode)
        os.makedirs(snap_dir, exist_ok=True)

        snap_path = os.path.join(snap_dir, f"{trade_date}_{time_slot.replace(':', '')}.json")
        with open(snap_path, "w") as f:
            json.dump({
                "mode": mode,
                "trade_date": trade_date,
                "time_slot": time_slot,
                "saved_at": datetime.now().isoformat(),
                "total_picks": len(picks),
                "picks": picks,
            }, f, ensure_ascii=False, indent=2, default=str)
        logger.info("Snapshot saved: %s (%d picks)", snap_path, len(picks))
    except Exception as e:
        logger.warning("Snapshot file save failed: %s", e)

    # 2) PG screening_snapshots via recorder
    try:
        model_key = mode  # e.g. 'leader_afternoon', 'bi_trend_launch'
        from kronos_factors.recorder import record_picks
        n = record_picks(model_key, trade_date, time_slot, picks)
        if n:
            logger.info("Recorder: %s %s — %d picks", model_key, trade_date, n)
    except Exception as e:
        logger.warning("Recorder save failed (PG may not be available): %s", e)


@router.get("/modes")
async def list_modes():
    """List available screening modes with descriptions."""
    return {
        "modes": [
            {"id": "leader_auction",  "name": "🔥秋神龙头竞价超预期战法 V4.3", "cycle": "1-3天",  "style": "竞价"},
            {"id": "leader_scalp",    "name": "秋神龙头战法-盘后", "cycle": "1-5天",  "style": "激进"},
            {"id": "leader_intraday", "name": "秋神龙头战法-盘中 V7.0", "cycle": "1-2天",  "style": "激进"},
            {"id": "leader_closing",  "name": "秋神龙头战法-尾盘顺势 V2.0", "cycle": "1-2天",  "style": "顺势"},
            {"id": "leader_afternoon","name": "🔥秋神龙头战法-午后选股 V1.0", "cycle": "1-2天",  "style": "午后"},
            {"id": "short",           "name": "匪爷短线多因子选股模型",       "cycle": "1-4周",  "style": "积极"},
            {"id": "long",            "name": "长线价值",         "cycle": "3-12月", "style": "稳健"},
            {"id": "all",             "name": "综合多因子",       "cycle": "1-6月",  "style": "中性"},
            {"id": "chokepoint",      "name": "大葱卡脖子选股模型",       "cycle": "1-3月",  "style": "主题"},
            {"id": "cb_floor",       "name": "匪爷可转债底价选债模型",   "cycle": "1-4周",  "style": "稳健"},
            {"id": "cb_intraday",    "name": "匪爷可转债日内投机博弈模型", "cycle": "1-2天",  "style": "激进"},
            {"id": "cb_auction",     "name": "秋神竞价概念选债模型",       "cycle": "1-2天",  "style": "竞价"},
            {"id": "bi_trend_launch","name": "毕师傅硬核科技趋势启动 V13", "cycle": "5-20天", "style": "趋势"},
            {"id": "bi_trend_full_market","name": "毕师傅全市场趋势启动 V1.0", "cycle": "5-20天", "style": "全市场"},
            {"id": "supply_chain",  "name": "大葱产业链解构选股", "cycle": "3-12月", "style": "中长线"},
        ]
    }


@router.get("/supply-chain/themes")
async def supply_chain_themes():
    """Return policy themes and the top-level matrix for BOM drill-down."""
    payload = _load_supply_chain_bom_payload()
    return {
        "version": payload["version"],
        "source": payload["source"],
        "themes": payload["themes"],
    }


@router.get("/supply-chain/bom")
async def supply_chain_bom():
    """Return the policy-BOM graph seed used by the V4 model."""
    payload = _load_supply_chain_bom_payload()
    return {
        "version": payload["version"],
        "source": payload["source"],
        "themes": payload["themes"],
        "nodes": payload["nodes"],
        "edges": payload["edges"],
    }


@router.get("/supply-chain/workbench")
async def supply_chain_workbench(
    top_n: int = Query(30, ge=5, le=MAX_TOP_N),
    trade_date: Optional[str] = Query(None),
    theme_id: Optional[str] = Query(None),
    node_id: Optional[str] = Query(None),
):
    """Return the full BOM workbench payload with model logic and candidates."""
    loop = asyncio.get_running_loop()
    payload = _load_supply_chain_bom_payload()
    candidates = await loop.run_in_executor(
        _executor,
        _get_supply_chain_candidate_pool,
        top_n,
        trade_date,
    )
    candidates = _attach_market_snapshots(candidates, trade_date)
    upstream_candidates = await loop.run_in_executor(
        _executor,
        _query_upstream_influence_candidates,
        50,
        trade_date,
    )
    node_by_id = {node.get("node_id"): node for node in payload["nodes"]}
    selected_node = node_by_id.get(node_id or "")
    if node_id and not selected_node:
        raise HTTPException(status_code=404, detail=f"Unknown BOM node '{node_id}'")
    node_candidates = _filter_candidates_for_node(candidates, selected_node) if selected_node else []
    return {
        "version": payload["version"],
        "source": payload["source"],
        "model": _supply_chain_model_payload(),
        "themes": payload["themes"],
        "policy_themes": payload["themes"],
        "nodes": payload["nodes"],
        "graph_nodes": payload["nodes"],
        "edges": payload["edges"],
        "graph_edges": payload["edges"],
        "selected_theme_id": theme_id,
        "selected_node_id": selected_node.get("node_id") if selected_node else None,
        "selected_node_thesis": _build_selected_node_thesis(selected_node, node_candidates),
        "candidate_count": len(candidates),
        "candidates": candidates,
        "upstream_influence_count": len(upstream_candidates),
        "upstream_influence_candidates": upstream_candidates,
        "node_candidate_count": len(node_candidates),
        "node_candidate_companies": node_candidates,
        "evidence_summary": _build_evidence_summary(node_candidates),
        "data_freshness": _query_supply_chain_data_freshness(),
        "research_ingestion": _query_research_ingestion_status(),
        "resonance_model": {"dimensions": ["policy", "commercialization", "order_capacity", "performance", "market"]},
        "stage_options": ["预研验证", "中试", "小批量验证", "量产爬坡", "规模推广", "成熟"],
    }


@router.get("/supply-chain/node/{node_id}")
async def supply_chain_node(node_id: str):
    """Return one BOM node with company candidates and evidence."""
    payload = _load_supply_chain_bom_payload()
    node = next((n for n in payload["nodes"] if n.get("node_id") == node_id), None)
    if not node:
        raise HTTPException(status_code=404, detail=f"Unknown BOM node '{node_id}'")
    companies = _query_supply_chain_node_companies(node_id)
    evidence = _query_supply_chain_node_evidence(node_id)
    return {
        "node_id": node_id,
        "node": node,
        "policy_theme": node.get("policy_theme", ""),
        "bom_path": node.get("bom_path", []),
        "companies": companies,
        "evidence": evidence,
    }


@router.get("/supply-chain/company/{code}")
async def supply_chain_company(code: str):
    """Return a company drill-down with product, material, financials, and evidence."""
    detail = _query_supply_chain_company_detail(code)
    if detail:
        return detail
    for candidate in _get_supply_chain_candidate_pool(top_n=100):
        if str(candidate.get("code")) == code:
            return candidate
    return {
        "code": code,
        "name": code,
        "rank": None,
        "rating": None,
        "trade_signal": "观察",
        "policy_theme": "",
        "bom_path": [],
        "products": [],
        "materials": [],
        "financial_indicators": {},
        "moat_evidence": [],
        "evidence": [],
        "selection_reason": "",
        "commercialization_stage": "",
        "commercialization_cycle": "",
        "resonance": {},
    }


@router.post("/supply-chain/extract")
async def supply_chain_extract(payload: dict = Body(...)):
    """Extract policy/BOM/company facts from policy, announcement, or research text."""
    text = str(payload.get("text") or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="text is required")
    source = payload.get("source") if isinstance(payload.get("source"), dict) else {}
    provider = str(payload.get("provider") or "deepseek")
    from app.llm_supply_chain import extract_supply_chain_facts
    result = extract_supply_chain_facts(text, source, provider=provider)
    if result.get("status") != "ok":
        return result

    from app.supply_chain_graph_store import build_graph_records, persist_graph_records
    records = build_graph_records(result, {**source, "raw_text": text})
    result["records"] = records
    result["persisted"] = False
    if bool(payload.get("persist")):
        try:
            result["persist_result"] = persist_graph_records(records)
            result["persisted"] = result["persist_result"].get("status") == "ok"
        except Exception as e:
            logger.warning("supply_chain extract persist failed: %s", e)
            result["persist_result"] = {"status": "error", "reason": str(e)}
    return result


@router.post("/supply-chain/research/ingest")
async def supply_chain_research_ingest(payload: dict | None = Body(default=None)):
    """Batch extract graph facts from recent Tushare research-report metadata."""
    payload = payload or {}
    limit = max(1, min(int(payload.get("limit") or 5), 20))
    keyword = str(payload.get("keyword") or "").strip() or None
    provider = str(payload.get("provider") or "deepseek")
    persist = bool(payload.get("persist"))
    reports = _query_recent_research_reports(limit=limit, keyword=keyword)

    if not os.environ.get("DEEPSEEK_API_KEY"):
        return {
            "status": "disabled",
            "reason": "DEEPSEEK_API_KEY missing",
            "report_count": len(reports),
            "source_table": "research_reports_tushare",
            "reports": reports,
        }

    from app.llm_supply_chain import extract_supply_chain_facts
    from app.supply_chain_graph_store import build_graph_records, persist_graph_records

    results = []
    extracted = 0
    persisted_count = 0
    for report in reports:
        text = _research_report_text(report)
        source = {
            "source_type": "tushare_research_report",
            "title": report.get("title") or f"research_report_{report.get('code')}",
            "published_at": report.get("pub_date"),
            "raw_text": text,
        }
        extraction = extract_supply_chain_facts(text, source, provider=provider)
        item = {
            "report": report,
            "status": extraction.get("status"),
            "reason": extraction.get("reason"),
            "policy_theme": extraction.get("policy_theme"),
            "bom_nodes": extraction.get("bom_nodes", []),
            "commercialization_stage": extraction.get("commercialization_stage", ""),
        }
        if extraction.get("status") == "ok":
            records = build_graph_records(extraction, source)
            item["records"] = records
            extracted += 1
            if persist:
                try:
                    item["persist_result"] = persist_graph_records(records)
                    if item["persist_result"].get("status") == "ok":
                        persisted_count += 1
                except Exception as e:
                    logger.warning("supply_chain research ingest persist failed: %s", e)
                    item["persist_result"] = {"status": "error", "reason": str(e)}
        results.append(item)

    return {
        "status": "ok",
        "source_table": "research_reports_tushare",
        "scanned": len(reports),
        "extracted": extracted,
        "persisted": persist and persisted_count > 0,
        "persisted_count": persisted_count,
        "reports": results,
    }


@router.post("/run")
async def run_screening(
    mode: str = Query("all", description="Screening mode"),
    top_n: int = Query(DEFAULT_TOP_N, ge=5, le=MAX_TOP_N, description="Top N picks"),
    trade_date: Optional[str] = Query(None, description="Trade date (YYYY-MM-DD), defaults to latest"),
):
    """Run stock screening with the specified mode.

    Returns ranked picks with scores, grades, entry/stop/target prices, and rationales.
    """
    if mode not in AVAILABLE_MODES:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown mode '{mode}'. Available: {AVAILABLE_MODES}"
        )

    t0 = time.time()
    loop = asyncio.get_running_loop()

    # ── Redis cache check (L4: screener results, TTL 1h) ──
    cache_key = f"screener:{mode}:{top_n}:{trade_date or 'latest'}"
    try:
        from app.cache import cache_get
        cached = await cache_get(cache_key)
        if cached:
            cached["cached"] = True
            cached["elapsed"] = round(time.time() - t0, 1)
            return cached
    except Exception:
        pass  # cache miss or Redis unavailable → proceed normally

    try:
        if mode in ("leader_scalp", "leader_intraday", "leader_auction", "leader_closing"):
            result = await loop.run_in_executor(
                _executor, _run_leader_mode, mode, top_n, trade_date
            )
        elif mode == "leader_afternoon":
            result = await loop.run_in_executor(
                _executor, _run_afternoon_mode, mode, top_n, trade_date
            )
        elif mode in ("cb_floor", "cb_intraday", "cb_auction"):
            result = await loop.run_in_executor(
                _executor, _run_cb_mode, mode, top_n, trade_date
            )
        elif mode == "bi_trend_launch":
            result = await loop.run_in_executor(
                _executor, _run_bi_trend_mode, mode, top_n, trade_date
            )
        elif mode == "bi_trend_full_market":
            result = await loop.run_in_executor(
                _executor, _run_bi_full_market_mode, mode, top_n, trade_date
            )
        elif mode == "supply_chain":
            result = await loop.run_in_executor(
                _executor, _run_supply_chain_mode, mode, top_n, trade_date
            )
        else:
            result = await loop.run_in_executor(
                _executor, _run_multifactor_mode, mode, top_n, trade_date
            )
    except Exception as e:
        err = str(e)
        logger.exception("Screening failed for mode=%s: %s", mode, err)
        if any(k in err.lower() for k in ("division by zero", "'code'", "'pct_chg'", "keyerror", "none")):
            raise HTTPException(status_code=503, detail="数据不足：部分行情数据缺失或不完整，请等待数据同步完成后再试")
        if "does not exist" in err.lower():
            raise HTTPException(status_code=503, detail="数据库表缺失：部分数据表未迁移，请先运行数据同步")
        raise HTTPException(status_code=500, detail=f"Screening failed: {err}")

    result["elapsed"] = round(time.time() - t0, 1)

    # ── Sanitize numpy types across all modes ──
    if "picks" in result and result["picks"]:
        result["picks"] = _sanitize_picks(result["picks"])
        result["picks"] = _normalize_picks(result["picks"], mode)

    # ── Auto-save snapshot (JSON file + PG) — before cache to ensure persistence ──
    _auto_save_snapshot(result, mode)

    # ── Redis cache write (L4: screener results, TTL 1h) ──
    try:
        from app.cache import cache_set
        loop.create_task(cache_set(cache_key, result, ttl=3600))
    except Exception:
        pass

    return result


def _run_leader_mode(mode: str, top_n: int, trade_date: Optional[str]) -> dict:
    """Run Leader Scalp strategy (daily or intraday)."""
    from kronos_factors.engine import (
        run_leader_screening, run_intraday_screening,
        generate_execution_plan, generate_intraday_plan,
    )
    from kronos_factors.scorer._db_stub import _get_db

    # Resolve 'latest' to actual date from PG
    td = trade_date
    if not td or td == 'latest':
        try:
            with _get_db() as db:
                latest = db.execute(
                    "SELECT MAX(trade_date) FROM daily_kline"
                ).fetchone()
                if latest:
                    td = str(list(latest.values())[0]) if isinstance(latest, dict) else str(latest[0])
        except Exception:
            td = trade_date or 'latest'

    if mode == "leader_auction":
        from kronos_factors.engine.leader_auction import AuctionScalpEngine
        engine = AuctionScalpEngine()
        picks_data = engine.run(trade_date=td, top_n=top_n)
        engine.close()
        plans = generate_execution_plan(picks_data) if picks_data else []
    elif mode == "leader_intraday":
        result = run_intraday_screening(td or "latest", top_n=top_n)
        picks_data = result[0] if isinstance(result, tuple) else result
        plans = generate_intraday_plan(picks_data) if picks_data else []
    elif mode == "leader_closing":
        from kronos_factors.engine.leader_closing import run_intraday_screening as run_closing
        result = run_closing(td or "latest", time_slot="14:40", top_n=top_n)
        picks_data = result[0] if isinstance(result, tuple) else result
        plans = generate_intraday_plan(picks_data) if picks_data else []
    else:
        result = run_leader_screening(td or "latest", top_n=top_n)
        picks_data = result[0] if isinstance(result, tuple) else result
        plans = generate_execution_plan(picks_data) if picks_data else []

    picks_out = _sanitize_picks(picks_data) if picks_data else []
    picks_out = _normalize_picks(picks_out, mode)

    return {
        "mode": mode,
        "trade_date": trade_date,
        "total_picks": len(picks_out),
        "picks": picks_out,
        "execution_plans": plans,
    }


def _run_cb_mode(mode: str, top_n: int, trade_date: Optional[str]) -> dict:
    """Run convertible bond screening (cb_floor / cb_intraday / cb_auction)."""
    from kronos_factors.engine.cb_floor import CbFloorEngine
    from kronos_factors.engine.cb_intraday import CbIntradayEngine
    from kronos_factors.engine.cb_auction import CbAuctionEngine

    engine_map = {
        "cb_floor": CbFloorEngine,
        "cb_intraday": CbIntradayEngine,
        "cb_auction": CbAuctionEngine,
    }
    engine = engine_map[mode]()

    picks = engine.run(trade_date=trade_date, top_n=top_n)
    engine.close()

    picks = _sanitize_picks(picks)
    picks = _normalize_picks(picks, mode)

    return {
        "mode": mode,
        "trade_date": trade_date,
        "total_picks": len(picks),
        "picks": picks,
    }


def _run_supply_chain_mode(mode: str, top_n: int, trade_date: Optional[str]) -> dict:
    """Run 大葱产业链解构选股 (中长线)."""
    from kronos_factors.engine.supply_chain import SupplyChainEngine

    engine = SupplyChainEngine()
    result = engine.run(top_n=top_n, trade_date=trade_date)

    picks = result.picks
    picks = _sanitize_picks(picks)
    # Normalize: total_score→score, preserve chain/layer/moat fields
    for p in picks:
        if "total_score" in p and "score" not in p:
            p["score"] = p["total_score"]
        if "price" not in p:
            p["price"] = 0
        sc = p.get("score", 0)
        if sc >= 80: p["grade"] = "S"
        elif sc >= 65: p["grade"] = "A"
        elif sc >= 50: p["grade"] = "B"
        else: p["grade"] = "C"

    return {
        "mode": mode,
        "trade_date": trade_date,
        "total_picks": len(picks),
        "picks": picks,
    }


def _run_multifactor_mode(mode: str, top_n: int, trade_date: Optional[str]) -> dict:
    """Run multi-factor mode (short/long/all/chokepoint)."""
    from kronos_factors.engine.modes import (
        ShortModeEngine, LongModeEngine, AllModeEngine, ChokepointEngine,
    )

    engine_map = {
        "short": ShortModeEngine,
        "long": LongModeEngine,
        "all": AllModeEngine,
        "chokepoint": ChokepointEngine,
    }
    engine = engine_map[mode]()
    result = engine.run(top_n=top_n)

    picks = _sanitize_picks(result.picks)
    picks = _normalize_picks(picks, mode)

    return {
        "mode": result.mode,
        "market_env": result.market_env,
        "total_scored": result.total_scored,
        "total_excluded": result.total_excluded,
        "picks": picks,
        "factor_weights": engine.get_factor_weights(),
    }


def _run_bi_trend_mode(mode: str, top_n: int, trade_date: Optional[str]) -> dict:
    """Run 毕师傅趋势启动战法 V13 (OBV+WR trend launch screening + 黑天鹅防护 + 止损降权分散 + 智能卖出决策树)."""
    from kronos_factors.engine.bi_trend_launch import BiTrendLaunchEngine, generate_bi_plan

    engine = BiTrendLaunchEngine()
    picks = engine.run(top_n=top_n, trade_date=trade_date)

    picks = _sanitize_picks(picks)
    picks = _normalize_picks(picks, mode)

    # Generate execution plans with market regime awareness
    regime = "neutral"
    plans = generate_bi_plan(picks, market_regime=regime) if picks else []

    return {
        "mode": mode,
        "trade_date": trade_date,
        "total_picks": len(picks),
        "picks": picks,
        "execution_plans": plans,
    }


def _run_bi_full_market_mode(mode: str, top_n: int, trade_date: Optional[str]) -> dict:
    """Run 毕师傅全市场趋势启动战法 V1.0 (全市场 + VR过滤)."""
    from kronos_factors.engine.bi_trend_full_market import BiTrendFullMarketEngine, generate_bi_plan

    engine = BiTrendFullMarketEngine()
    picks = engine.run(top_n=top_n, trade_date=trade_date, hard_tech_only=False)

    picks = _sanitize_picks(picks)
    picks = _normalize_picks(picks, mode)

    regime = "neutral"
    plans = generate_bi_plan(picks, market_regime=regime) if picks else []

    return {
        "mode": mode,
        "trade_date": trade_date,
        "total_picks": len(picks),
        "picks": picks,
        "execution_plans": plans,
    }


def _run_afternoon_mode(mode: str, top_n: int, trade_date: Optional[str]) -> dict:
    """Run 秋神龙头战法-午后选股 V1.0 (14:30 afternoon leader screening)."""
    from kronos_factors.engine.leader_afternoon import AfternoonLeaderEngine

    engine = AfternoonLeaderEngine()
    picks = engine.run(top_n=top_n, trade_date=trade_date, time_slot="14:30")

    picks = _sanitize_picks(picks)
    picks = _normalize_picks(picks, mode)

    return {
        "mode": mode,
        "trade_date": trade_date,
        "total_picks": len(picks),
        "picks": picks,
    }
