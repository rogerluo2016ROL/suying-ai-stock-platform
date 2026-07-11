"""Screener API routes — 12 screening modes via unified endpoint with Redis caching."""

import asyncio
import hashlib
import json
import logging
import math
import os
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Body, Depends, Header, Query, HTTPException
from pydantic import BaseModel, Field
import numpy as np

from app import candidate_pool_store, watchlist_store
from app.config import AVAILABLE_MODES, DEFAULT_TOP_N, MAX_TOP_N
from app.database import AsyncSession, get_db
from app.jobs.pipeline_runner import finish_persisted_pipeline, submit_persisted_pipeline
from app.domains.candidates.models import (
    CandidatePoolQueryResponse,
    CandidatePoolRecordRequest,
    CandidatePoolRecordResponse,
    WatchlistAddRequest, WatchlistAddResponse, WatchlistDeleteResponse,
    WatchlistItemResponse, WatchlistQueryResponse,
)
from app.domains.candidates import service as candidate_service
from app.domains.supply_chain import service as supply_chain_service
from app.domains.supply_chain import repository as supply_chain_repository

logger = logging.getLogger("screener.routes")
PROJECT_ROOT = Path(__file__).resolve().parents[5]
INDUSTRY_CHAIN_TEMPLATE_PATH = PROJECT_ROOT / "packages" / "kronos-factors" / "configs" / "industry_chain_templates.json"
BIGTECH_COMPANIES = {"Microsoft", "Alphabet", "Meta", "Amazon", "Oracle"}
AI_COMPUTE_LAYER_KEYWORDS = {
    "demand": ("云", "cloud", "aws", "oci", "AI", "大模型", "算力", "应用"),
    "foundation": ("HBM", "CoWoS", "封装", "服务器", "网络设备", "数据中心土地"),
    "infrastructure": ("IDC", "数据中心", "服务器", "液冷", "光模块", "CPO", "网络", "交换机", "电源", "GPU", "云容量"),
}


# ─────────────────────────────────────────────────────────────────────────────
# Policy Interpretation Request/Response Models
# ─────────────────────────────────────────────────────────────────────────────

class PolicyInterpretRequest(BaseModel):
    """Request model for policy interpretation endpoint."""

    text: str = Field(..., description="Policy document text to interpret")
    source: Optional[dict[str, Any]] = Field(
        default=None, description="Source metadata with title/published_at"
    )
    persist: bool = Field(default=False, description="Persist result to PG")
    provider: str = Field(default="deepseek", description="LLM provider to use")


class SupplyChainMappingReviewRequest(BaseModel):
    decision: str = Field(..., description="verified, rejected, needs_more_evidence, or pending_review")
    reviewer: str = Field(default="system", description="Reviewer name or operator id")
    note: str = Field(default="", description="Short review note")


class BusinessTagEvidenceReviewRequest(BaseModel):
    review_status: str = Field(..., description="approved, rejected, or pending_review")
    reviewer: str = Field(default="system", description="Reviewer name or operator id")
    note: str = Field(default="", description="Short review note")
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    stage_after: Optional[dict[str, Any]] = Field(
        default=None,
        description="Optional R/C stage after approval, e.g. {'research_stage':'R3','commercialization_stage':'C2'}",
    )


class BusinessTagEvidenceExtractRequest(BaseModel):
    source_type: str = Field(..., description="announcement_title, research_title, irm_qa, manual, etc.")
    source_id: Optional[str] = Field(default=None)
    title: str = Field(default="")
    excerpt: str = Field(default="")
    original_url: Optional[str] = Field(default=None)
    event_date: Optional[str] = Field(default=None)
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    persist: bool = Field(default=True, description="Whether to persist as pending_review evidence event")


class BusinessTagEvidenceBatchExtractRequest(BaseModel):
    mapping_id: Optional[str] = Field(default=None, description="Limit extraction to one business-tag mapping")
    code: Optional[str] = Field(default=None, description="Limit extraction to one stock code")
    source_types: list[str] = Field(
        default_factory=lambda: ["announcement_title", "research_title", "irm_qa", "interact_qa"],
        description="Candidate source types to scan",
    )
    limit: int = Field(default=50, ge=1, le=500)
    persist: bool = Field(default=True)


class BusinessTagThreeHighScoreRequest(BaseModel):
    trade_date: Optional[str] = Field(default=None, description="Score date, default today")
    persist: bool = Field(default=True, description="Whether to persist the score snapshot")


class BusinessTagExpectationGapScoreRequest(BaseModel):
    trade_date: Optional[str] = Field(default=None, description="Score date, default today")
    persist: bool = Field(default=True, description="Whether to persist the score snapshot")
    market_expectation_score: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=100.0,
        description="Optional market expectation score; defaults to neutral 50 when unavailable",
    )


class BusinessTagBatchScoreRequest(BaseModel):
    code: Optional[str] = Field(default=None, description="Limit batch scoring to one stock code")
    node_id: Optional[str] = Field(default=None, description="Limit batch scoring to one supply-chain node")
    status: Optional[str] = Field(default=None, description="Limit batch scoring to one mapping status")
    score_types: list[str] = Field(
        default_factory=lambda: ["three_high", "expectation_gap"],
        description="Score types to run: three_high and/or expectation_gap",
    )
    trade_date: Optional[str] = Field(default=None, description="Score date, default today")
    persist: bool = Field(default=True, description="Whether to persist score snapshots")
    market_expectation_score: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    limit: int = Field(default=100, ge=1, le=500)


class SupplyChainRefreshWorkflowRequest(BaseModel):
    mapping_id: Optional[str] = Field(default=None, description="Limit refresh to one business-tag mapping")
    code: Optional[str] = Field(default=None, description="Limit refresh to one stock code")
    node_id: Optional[str] = Field(default=None, description="Limit scoring to one supply-chain node")
    status: Optional[str] = Field(default=None, description="Limit scoring to one mapping status")
    source_types: list[str] = Field(
        default_factory=lambda: ["announcement_title", "research_title", "irm_qa", "interact_qa"],
        description="Candidate source types to scan for evidence",
    )
    score_types: list[str] = Field(
        default_factory=lambda: ["three_high", "expectation_gap"],
        description="Score types to run after evidence extraction",
    )
    rank_types: list[str] = Field(
        default_factory=lambda: ["value", "expectation_gap"],
        description="Ranking previews to return after scoring",
    )
    trade_date: Optional[str] = Field(default=None)
    persist: bool = Field(default=True, description="Whether to persist evidence and score snapshots")
    market_expectation_score: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    include_evidence_extract: bool = Field(default=True)
    include_scores: bool = Field(default=True)
    include_rankings: bool = Field(default=True)
    evidence_limit: int = Field(default=50, ge=1, le=500)
    score_limit: int = Field(default=100, ge=1, le=500)
    top_n: int = Field(default=20, ge=1, le=200)


class SupplyChainInferredMaterializeRequest(BaseModel):
    theme_id: Optional[str] = Field(default="future_industry_core", description="Limit to one policy theme")
    node_id: Optional[str] = Field(default=None, description="Limit to one BOM/chain node")
    code: Optional[str] = Field(default=None, description="Limit to one stock code")
    status: Optional[str] = Field(default=None, description="Limit to mapping status")
    trade_date: Optional[str] = Field(default=None, description="Materialization date, default today")
    limit: int = Field(default=5000, ge=1, le=20000)
    persist: bool = Field(default=True, description="Whether to persist inferred records")
    include_three_high: bool = Field(default=True, description="Whether to persist inference-only three-high baseline")
    include_company_chain_projection: bool = Field(
        default=True,
        description="Whether to copy inferred three-high summary back to company_chain_mapping.three_factors",
    )


class InterpretationResult(BaseModel):
    """Structured interpretation result from LLM."""

    summary: str = Field(default="", description="Brief summary of the policy")
    industry_themes: list[dict[str, Any]] = Field(
        default_factory=list, description="Identified industry themes"
    )
    bom_nodes: list[str] = Field(
        default_factory=list, description="Supply-chain BOM nodes mentioned"
    )
    investment_logic: str = Field(default="", description="Investment thesis")
    risk_factors: list[dict[str, Any]] = Field(
        default_factory=list, description="Risk factors identified"
    )


class LLMUsageInfo(BaseModel):
    """Token usage telemetry from LLM call."""

    prompt_tokens: int = Field(default=0)
    completion_tokens: int = Field(default=0)
    total_tokens: int = Field(default=0)
    provider: str = Field(default="")
    model: str = Field(default="")


class PolicyInterpretResponse(BaseModel):
    """Response model for policy interpretation endpoint."""

    status: str = Field(..., description="ok, disabled, or error")
    interpretation_result: InterpretationResult = Field(
        default_factory=InterpretationResult
    )
    usage: LLMUsageInfo = Field(default_factory=LLMUsageInfo)
    persisted: bool = Field(default=False)
    reason: Optional[str] = Field(default=None, description="Error reason if status!=ok")


router = APIRouter(prefix="/api/v1/screener", tags=["screener"])
_CB_AUCTION_T0_ENGINE = None
_CB_AUCTION_T0_V2_ENGINE = None
_CB_AUCTION_T0_V21_ENGINE = None


def _screener_model_metadata(mode: str) -> dict[str, Any]:
    if mode == "supply_chain_trend_launch":
        return {
            "name": "supply-chain-trend-launch-v1",
            "version": "trend-launch-v1.0",
            "provider": "screener-service",
            "inference_mode": mode,
        }
    if mode.startswith("chain:") or mode == "supply_chain":
        return {
            "name": "supply-chain-deconstruct-v5",
            "version": "supply-chain-v5.0",
            "provider": "screener-service",
            "inference_mode": mode,
        }
    return {
        "name": "screener-multi-strategy-v2",
        "version": "screener-contract-v2",
        "provider": "screener-service",
        "inference_mode": mode,
    }


def _screener_data_freshness(trade_date: str | None = None, source: str = "daily_kline") -> dict[str, Any]:
    if not trade_date:
        return {
            "status": "unknown",
            "as_of": None,
            "source": source,
            "quality_score": 0,
        }
    as_of = str(trade_date)[:10]
    try:
        as_date = datetime.fromisoformat(as_of).date()
        lag_days = max(0, (datetime.now().date() - as_date).days)
    except Exception:
        lag_days = 999
    if lag_days <= 10:
        status, quality_score = "fresh", 96
    elif lag_days <= 30:
        status, quality_score = "stale", 72
    else:
        status, quality_score = "outdated", 35
    return {
        "status": status,
        "as_of": as_of,
        "source": source,
        "quality_score": quality_score,
    }


def _screener_source_for_mode(mode: str) -> str:
    if mode in ("cb_auction_t0", "cb_auction_t0_v2", "cb_auction_t0_v2_1"):
        return "limit_list_d + kpl_list + eastmoney_limit_pool + stk_auction_o"
    if "auction" in mode:
        return "stk_auction_o"
    if mode == "leader_intraday":
        return "rt_sw_k"
    if mode == "cb_intraday":
        return "stk_mins"
    return "daily_kline"


def _with_screener_contract(
    payload: dict[str, Any],
    *,
    mode: str,
    trade_date: str | None = None,
    fallback_reason: str | None = None,
    source: str | None = None,
) -> dict[str, Any]:
    enriched = dict(payload)
    if not enriched.get("trade_date") or enriched.get("trade_date") == "latest":
        try:
            enriched["trade_date"] = _resolve_trade_date(trade_date)
        except RuntimeError as e:
            logger.warning("screener contract trade_date fallback failed: %s", e)
            enriched["trade_date"] = trade_date if trade_date != "latest" else None
    enriched["model_metadata"] = _screener_model_metadata(mode)
    freshness_source = source or _screener_source_for_mode(mode)
    enriched["data_freshness"] = _screener_data_freshness(
        enriched.get("trade_date"),
        source=freshness_source,
    )
    enriched["fallback_reason"] = fallback_reason
    return enriched


def _normalize_picks(picks: list, mode: str) -> list:
    """Normalize engine-specific field names to frontend-expected fields.

    Frontend expects: price, score, grade, entry_price, stop_loss, target_price
    Different engines use different names, so we normalize here.
    """
    for p in picks:
        code = str(p.get("code") or p.get("ts_code") or "").strip().upper()
        if code:
            p["candidate_id"] = p.get("candidate_id") or f"CAND-{mode}-{code}"
        p["source_module"] = p.get("source_module") or "screener"
        p["source_mode"] = p.get("source_mode") or mode
        p["visibility"] = p.get("visibility") or "public"
        p["data_scope"] = p.get("data_scope") or "public"

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
    return supply_chain_service.load_bom_payload()


def _seed_chain_nodes_for_deconstruct(theme_id: str) -> tuple[list[dict[str, Any]], str | None]:
    """Return BOM seed nodes in the shape expected by chain_deconstruct."""
    payload = _load_supply_chain_bom_payload()
    themes = payload.get("themes", [])
    theme = next((item for item in themes if item.get("theme_id") == theme_id), None)
    if not theme:
        return [], None

    level_order = {
        "theme": 0,
        "chain": 1,
        "industry": 1,
        "component": 2,
        "material": 2,
        "equipment": 3,
        "application": 4,
    }

    nodes = []
    for node in payload.get("nodes", []):
        if node.get("theme_id") != theme_id:
            continue
        level = str(node.get("level") or node.get("node_type") or "").lower()
        nodes.append({
            "node_id": str(node.get("node_id") or ""),
            "theme_id": str(node.get("theme_id") or ""),
            "chain_id": str(node.get("chain_id") or ""),
            "node_name": str(node.get("name") or node.get("node_name") or ""),
            "layer": level_order.get(level, 1),
            "parent_node_id": node.get("parent_node_id") or None,
            "keywords": node.get("keywords") or [],
            "node_type": node.get("node_type") or level,
            "source_level": node.get("level"),
            "upstream_nodes": node.get("upstream_nodes") or [],
            "downstream_nodes": node.get("downstream_nodes") or [],
            "value_chain": node.get("value_chain") or {},
            "competition": node.get("competition") or {},
        })
    return nodes, str(theme.get("name") or theme_id)


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


def _get_factor_db():
    from kronos_factors.scorer._db_stub import _get_db
    return _get_db()


def _resolve_trade_date(trade_date: Optional[str]) -> str:
    """Resolve API latest/default trade_date to a concrete YYYY-MM-DD string."""
    if trade_date and trade_date != "latest":
        return trade_date

    try:
        with _get_factor_db() as db:
            row = db.execute("SELECT MAX(trade_date) FROM daily_kline").fetchone()
    except Exception as e:
        logger.warning("latest trade_date lookup failed: %s", e)
        raise RuntimeError("latest trade date unavailable") from e

    if not row:
        raise RuntimeError("latest trade date unavailable")

    if isinstance(row, dict):
        value = next(iter(row.values()), None)
    else:
        value = row[0] if len(row) else None

    if not value:
        raise RuntimeError("latest trade date unavailable")
    return str(value)


def _resolve_intraday_trade_date(trade_date: Optional[str]) -> str:
    """Resolve intraday/default trade_date from stk_mins first, then daily_kline."""
    if trade_date and trade_date != "latest":
        return trade_date
    try:
        with _get_factor_db() as db:
            row = db.execute("SELECT MAX(trade_time)::date FROM stk_mins").fetchone()
            if isinstance(row, dict):
                value = next(iter(row.values()), None)
            else:
                value = row[0] if row and len(row) else None
            if value:
                return str(value)[:10]
    except Exception as e:
        logger.warning("latest intraday trade_date lookup failed: %s", e)
    return _resolve_trade_date(trade_date)


def _query_screener_latest_dates() -> dict[str, str]:
    """Return the latest available date for each screener data source."""
    queries = {
        "daily_kline": "SELECT MAX(trade_date) FROM daily_kline",
        "stk_auction_o": "SELECT MAX(trade_date) FROM stk_auction_o",
        "rt_sw_k": "SELECT MAX(trade_date) FROM rt_sw_k",
        "stk_mins": "SELECT MAX(trade_time)::date FROM stk_mins",
    }
    latest_dates: dict[str, str] = {}
    with _get_factor_db() as db:
        for source, sql in queries.items():
            try:
                row = db.execute(sql).fetchone()
                if isinstance(row, dict):
                    value = next(iter(row.values()), None)
                else:
                    value = row[0] if row and len(row) else None
                if value:
                    latest_dates[source] = str(value)[:10]
            except Exception as e:
                logger.warning("latest date lookup failed for %s: %s", source, e)
    return latest_dates


def _query_index_close_quotes(trade_date: Optional[str] = None) -> dict[str, Any]:
    """Return index close quotes from local index_daily as a post-market fallback."""
    code_labels = {
        "000001": "上证",
        "399001": "深成",
        "399006": "创业板",
        "899050": "北证50",
    }
    codes_sql = ", ".join(f"'{code}'" for code in code_labels)
    date_filter = ""
    if trade_date:
        safe_date = str(trade_date)[:10].replace("'", "")
        date_filter = f"AND trade_date <= '{safe_date}'"

    with _get_factor_db() as db:
        date_row = db.execute(
            f"""
            SELECT MAX(trade_date)
            FROM index_daily
            WHERE code IN ({codes_sql})
            {date_filter}
            """
        ).fetchone()
        latest_date = _row_get(date_row, 0)
        if not latest_date:
            return {
                "source": "index_daily",
                "as_of": None,
                "data": {"diff": []},
            }

        rows = db.execute(
            f"""
            SELECT code, close, change_pct, trade_date
            FROM index_daily
            WHERE trade_date = '{str(latest_date)[:10]}'
              AND code IN ({codes_sql})
            ORDER BY code
            """
        ).fetchall()

    diff = []
    for row in rows:
        code = str(_row_get(row, "code") or _row_get(row, 0) or "")
        diff.append({
            "f12": code,
            "f14": code_labels.get(code, code),
            "f2": _row_get(row, "close") or _row_get(row, 1),
            "f3": _row_get(row, "change_pct") or _row_get(row, 2),
            "f4": None,
            "f6": None,
        })
    return {
        "source": "index_daily_close",
        "as_of": str(latest_date)[:10],
        "data": {"diff": diff},
    }


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


def _pg_connect():
    return supply_chain_repository.connect()


def _pg_table_exists(cur, table_name: str) -> bool:
    return supply_chain_repository.table_exists(cur, table_name)


def _pg_column_exists(cur, table_name: str, column_name: str) -> bool:
    return supply_chain_repository.column_exists(cur, table_name, column_name)


def _pg_count(cur, table_name: str) -> int:
    return supply_chain_repository.count(cur, table_name)


def _pg_distinct_count(cur, table_name: str, column_name: str) -> int:
    return supply_chain_repository.distinct_count(cur, table_name, column_name)


def _pg_nonempty_text_count(cur, table_name: str, column_name: str, min_length: int = 20) -> int:
    return supply_chain_repository.nonempty_text_count(cur, table_name, column_name, min_length)


def _status_from_rows(rows: int, *, ready: int, partial: int = 1) -> str:
    return supply_chain_repository.status_from_rows(rows, ready=ready, partial=partial)


def _query_supply_chain_data_readiness() -> dict[str, Any]:
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
        with _pg_connect() as pg:
            cur = pg.cursor()

            policy_theme_rows = _pg_count(cur, "policy_themes")
            bom_node_rows = _pg_count(cur, "supply_chain_bom_nodes")
            chain_node_rows = _pg_count(cur, "chain_nodes")
            company_mapping_rows = _pg_count(cur, "company_bom_mapping")
            evidence_rows = _pg_count(cur, "company_evidence")
            segment_rows = _pg_count(cur, "fina_mainbz")
            segment_code_rows = _pg_distinct_count(cur, "fina_mainbz", "code")
            announcement_rows = _pg_count(cur, "announcements")
            announcement_body_rows = _pg_nonempty_text_count(cur, "announcements", "content")
            research_rows = _pg_count(cur, "research_reports_tushare")
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
                    "status": _status_from_rows(policy_theme_rows, ready=3),
                    "row_count": policy_theme_rows,
                    "source": "policy_themes",
                },
                "L2": {
                    "name": "产业方向",
                    "status": _status_from_rows(bom_node_rows, ready=20),
                    "row_count": bom_node_rows,
                    "source": "supply_chain_bom_nodes",
                },
                "L3": {
                    "name": "产业链",
                    "status": _status_from_rows(chain_node_rows, ready=20),
                    "row_count": chain_node_rows,
                    "source": "chain_nodes",
                },
                "L4": {
                    "name": "环节",
                    "status": _status_from_rows(company_mapping_rows, ready=1000),
                    "row_count": company_mapping_rows,
                    "source": "company_bom_mapping",
                },
                "L5": {
                    "name": "BOM节点",
                    "status": _status_from_rows(bom_node_rows, ready=80, partial=20),
                    "row_count": bom_node_rows,
                    "source": "supply_chain_bom_nodes",
                },
                "L6": {
                    "name": "产品/技术路线",
                    "status": _status_from_rows(research_rows, ready=1000),
                    "row_count": research_rows,
                    "source": "research_reports_tushare.title",
                },
                "L7": {
                    "name": "公司业务分部",
                    "status": _status_from_rows(segment_code_rows, ready=1000, partial=50),
                    "row_count": segment_rows,
                    "company_count": segment_code_rows,
                    "source": "fina_mainbz",
                },
                "L8": {
                    "name": "证据事件",
                    "status": _status_from_rows(evidence_rows, ready=1000, partial=100),
                    "row_count": evidence_rows,
                    "source": "company_evidence",
                },
            }

            payload["business_segments"] = {
                "status": _status_from_rows(segment_code_rows, ready=1000, partial=50),
                "source_table": "fina_mainbz",
                "row_count": segment_rows,
                "company_count": segment_code_rows,
                "income_supported": _pg_column_exists(cur, "fina_mainbz", "biz_income"),
                "ratio_supported": (
                    _pg_column_exists(cur, "fina_mainbz", "biz_ratio")
                    and _pg_nonempty_text_count(cur, "fina_mainbz", "biz_ratio", 0) > 0
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
                "status": _status_from_rows(evidence_rows, ready=1000, partial=100),
                "source_table": "company_evidence",
                "row_count": evidence_rows,
                "target_table": "business_tag_evidence_events",
                "target_status": "planned",
            }
            payload["target_tables"] = {
                table_name: {
                    "exists": _pg_table_exists(cur, table_name),
                    "row_count": _pg_count(cur, table_name),
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


def _stage_rank(stage: str | None) -> int:
    return supply_chain_service.stage_rank(stage)


def _pool_for_business_tag(status: str, revenue_ratio: float | None, commercialization_stage: str, evidence_count: int) -> str:
    return supply_chain_service.pool_for_business_tag(status, revenue_ratio, commercialization_stage, evidence_count)


def _layer_level_from_bom_level(level: str | None) -> str:
    return supply_chain_service.layer_level_from_bom_level(level)


def _build_layer_tree(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return supply_chain_service.build_layer_tree(nodes)


def _fallback_supply_chain_layer_nodes() -> list[dict[str, Any]]:
    return supply_chain_service.fallback_layer_nodes()


def _query_supply_chain_layers() -> dict[str, Any]:
    payload: dict[str, Any] = {
        "version": "supply-chain-v2-layers",
        "source": "fallback_bom_config",
        "source_status": "fallback",
        "layers": {},
        "nodes": [],
        "tree": [],
    }
    try:
        with _pg_connect() as pg:
            cur = pg.cursor()
            if _pg_table_exists(cur, "supply_chain_hierarchy_nodes") and _pg_count(cur, "supply_chain_hierarchy_nodes") > 0:
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
                nodes = _fallback_supply_chain_layer_nodes()
    except Exception as e:
        nodes = _fallback_supply_chain_layer_nodes()
        payload["source_status"] = "degraded_fallback"
        payload["error"] = str(e)

    layers: dict[str, list[dict[str, Any]]] = {f"L{i}": [] for i in range(1, 9)}
    for node in nodes:
        layers.setdefault(node["layer_level"], []).append(node)
    payload["layers"] = layers
    payload["nodes"] = nodes
    payload["tree"] = _build_layer_tree(nodes)
    payload["node_count"] = len(nodes)
    return payload


def _query_supply_chain_layer_detail(layer_node_id: str) -> dict[str, Any]:
    payload = _query_supply_chain_layers()
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


def _business_tag_score_status(revenue_ratio: float | None, gross_profit_ratio: float | None, evidence_count: int) -> str:
    if revenue_ratio is not None and gross_profit_ratio is not None and evidence_count > 0:
        return "scorable"
    if revenue_ratio is not None and evidence_count > 0:
        return "profit_insufficient"
    if evidence_count > 0:
        return "evidence_only"
    return "insufficient_business_data"


def _query_company_business_tags(code: str) -> dict[str, Any]:
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
        with _pg_connect() as pg:
            cur = pg.cursor()
            if _pg_table_exists(cur, "business_tag_mapping"):
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
                        score_status = _business_tag_score_status(revenue_ratio, gross_profit_ratio, evidence_count)
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
                            "pool": _pool_for_business_tag(str(row[10] or "pending_review"), revenue_ratio, commercialization_stage, evidence_count),
                        })
                    payload.update({
                        "source": "business_tag_mapping",
                        "source_status": "ready",
                        "tag_count": len(tags),
                        "tags": tags,
                    })
                    return payload

            if not _pg_table_exists(cur, "company_bom_mapping"):
                payload["source_status"] = "missing_mapping_table"
                payload["limitations"].append("company_bom_mapping table is missing")
                return payload

            has_company_evidence = _pg_table_exists(cur, "company_evidence")
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
                        "score_status": _business_tag_score_status(None, None, evidence_count),
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
                        "score_status": _business_tag_score_status(None, None, evidence_count),
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
                    "pool": _pool_for_business_tag(status, None, "C0", evidence_count),
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


def _query_business_tag_mapping_context(cur, mapping_id: str) -> dict[str, Any] | None:
    if _pg_table_exists(cur, "business_tag_mapping"):
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

    if _pg_table_exists(cur, "company_bom_mapping"):
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


def _query_business_tag_evidence(mapping_id: str) -> dict[str, Any]:
    payload = _empty_business_tag_evidence_payload(mapping_id)
    if not mapping_id:
        payload["source_status"] = "invalid_mapping_id"
        payload["limitations"].append("mapping_id is empty")
        return payload

    try:
        with _pg_connect() as pg:
            cur = pg.cursor()
            mapping = _query_business_tag_mapping_context(cur, mapping_id)

            if _pg_table_exists(cur, "business_tag_evidence_events"):
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
            if not _pg_table_exists(cur, "company_evidence"):
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


def _query_business_tag_mappings_for_batch(
    cur,
    request: BusinessTagEvidenceBatchExtractRequest,
) -> list[dict[str, Any]]:
    if request.mapping_id:
        mapping = _query_business_tag_mapping_context(cur, request.mapping_id)
        return [mapping] if mapping else []

    normalized_code = str(request.code or "").strip().upper()
    code6 = normalized_code.split(".")[0] if "." in normalized_code else normalized_code
    if not code6:
        return []

    mappings: list[dict[str, Any]] = []
    if _pg_table_exists(cur, "business_tag_mapping"):
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
    if mappings or not _pg_table_exists(cur, "company_bom_mapping"):
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
        if _pg_column_exists(cur, table_name, column):
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
    if not _pg_table_exists(cur, table_name):
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
    request: BusinessTagEvidenceExtractRequest,
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
        with _pg_connect() as pg:
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

            if not _pg_table_exists(cur, "business_tag_evidence_events"):
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
    request: BusinessTagEvidenceBatchExtractRequest,
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
        with _pg_connect() as pg:
            cur = pg.cursor()
            mappings = _query_business_tag_mappings_for_batch(cur, request)
            payload["mapping_count"] = len(mappings)
            if not mappings:
                payload["source_status"] = "mapping_not_found"
                payload["limitations"].append("未找到业务标签映射，无法抽取证据")
                return payload
            if request.persist and not _pg_table_exists(cur, "business_tag_evidence_events"):
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


def _score_stage_progress(stage: dict[str, Any]) -> float:
    research_rank = _stage_rank(stage.get("research_stage"))
    commercialization_rank = _stage_rank(stage.get("commercialization_stage"))
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


def _query_business_tag_score_mapping_context(cur, mapping_id: str) -> dict[str, Any] | None:
    if _pg_table_exists(cur, "business_tag_mapping"):
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
    if not _pg_table_exists(cur, "business_tag_stage_tracking"):
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
    if not _pg_table_exists(cur, "business_tag_evidence_events"):
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
    request: SupplyChainInferredMaterializeRequest,
) -> list[dict[str, Any]]:
    if not _pg_table_exists(cur, "company_bom_mapping"):
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
    if _pg_table_exists(cur, "business_tag_evidence_events"):
        cur.execute(
            """
            DELETE FROM business_tag_evidence_events
            WHERE mapping_id = %s
              AND event_id LIKE %s
              AND COALESCE(review_status, '') <> 'approved'
            """,
            (mapping_id, event_like),
        )
    if _pg_table_exists(cur, "company_evidence"):
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
    if not _pg_table_exists(cur, "company_evidence"):
        return
    event = materialized["evidence_event"]
    _persist_legacy_company_evidence_event(cur, event)


def _persist_legacy_company_evidence_event(cur, event: dict[str, Any]) -> None:
    if not _pg_table_exists(cur, "company_evidence"):
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
    if not _pg_table_exists(cur, "company_chain_mapping"):
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
    request: SupplyChainInferredMaterializeRequest,
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
        with _pg_connect() as pg:
            cur = pg.cursor()
            missing_tables = [
                table_name
                for table_name in _business_tag_materialization_tables()
                if not _pg_table_exists(cur, table_name)
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
    request: BusinessTagThreeHighScoreRequest,
) -> dict[str, Any]:
    if not mapping_id:
        raise HTTPException(status_code=400, detail="mapping_id is required")
    try:
        with _pg_connect() as pg:
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
                if not _pg_table_exists(cur, "business_tag_three_high_scores"):
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
        with _pg_connect() as pg:
            cur = pg.cursor()
            if not _pg_table_exists(cur, "business_tag_three_high_scores"):
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
    request: BusinessTagExpectationGapScoreRequest,
) -> dict[str, Any]:
    if not mapping_id:
        raise HTTPException(status_code=400, detail="mapping_id is required")
    try:
        with _pg_connect() as pg:
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
                if not _pg_table_exists(cur, "business_tag_expectation_gap_scores"):
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
        with _pg_connect() as pg:
            cur = pg.cursor()
            if not _pg_table_exists(cur, "business_tag_expectation_gap_scores"):
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
    request: BusinessTagBatchScoreRequest,
) -> list[dict[str, Any]]:
    try:
        with _pg_connect() as pg:
            cur = pg.cursor()
            if not _pg_table_exists(cur, "business_tag_mapping"):
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


def _batch_score_business_tags(request: BusinessTagBatchScoreRequest) -> dict[str, Any]:
    score_types = _normalize_batch_score_types(request.score_types)
    mappings = _query_business_tag_mappings_for_batch_score(request)
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
                    score_payload = _score_business_tag_three_high(
                        mapping_id,
                        BusinessTagThreeHighScoreRequest(
                            trade_date=request.trade_date,
                            persist=request.persist,
                        ),
                    )
                else:
                    score_payload = _score_business_tag_expectation_gap(
                        mapping_id,
                        BusinessTagExpectationGapScoreRequest(
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


def _refresh_supply_chain_tracking_workflow(request: SupplyChainRefreshWorkflowRequest) -> dict[str, Any]:
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
            evidence_payload = _batch_extract_business_tag_evidence(BusinessTagEvidenceBatchExtractRequest(
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
        score_payload = _batch_score_business_tags(BusinessTagBatchScoreRequest(
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
            rankings[rank_type] = _query_supply_chain_rankings(rank_type, request.top_n, request.trade_date)
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
        with _pg_connect() as pg:
            cur = pg.cursor()
            if not _pg_table_exists(cur, "business_tag_mapping"):
                payload["source_status"] = "mapping_table_missing"
                payload["limitations"].append("business_tag_mapping table is missing")
                return payload

            scan_limit = max(safe_top_n * 20, 200)
            if safe_rank_type == "value":
                if not _pg_table_exists(cur, "business_tag_three_high_scores"):
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
                if not _pg_table_exists(cur, "business_tag_expectation_gap_scores"):
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
    allowed_statuses = {"approved", "rejected", "pending_review"}
    review_status = str(request.review_status or "").strip()
    if review_status not in allowed_statuses:
        raise HTTPException(status_code=400, detail=f"Invalid review_status '{request.review_status}'")

    if not event_id:
        raise HTTPException(status_code=400, detail="event_id is required")

    try:
        with _pg_connect() as pg:
            cur = pg.cursor()
            if not _pg_table_exists(cur, "business_tag_evidence_events"):
                raise HTTPException(status_code=503, detail="business_tag_evidence_events table is missing")

            cur.execute(
                """
                SELECT event_id, mapping_id, code, node_id, event_date, title,
                       excerpt, confidence, stage_after
                FROM business_tag_evidence_events
                WHERE event_id = %s
                LIMIT 1
                """,
                (event_id,),
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail=f"Evidence event '{event_id}' not found")

            stage_after = request.stage_after if request.stage_after is not None else _json_or_default(row[8], {})
            confidence = request.confidence if request.confidence is not None else _to_float(row[7], 0.0)

            set_clauses = [
                "review_status = %s",
                "confidence = %s",
                "stage_after = %s::jsonb",
            ]
            params: list[Any] = [
                review_status,
                confidence,
                json.dumps(stage_after or {}, ensure_ascii=False),
            ]
            if _pg_column_exists(cur, "business_tag_evidence_events", "reviewer"):
                set_clauses.append("reviewer = %s")
                params.append(request.reviewer)
            if _pg_column_exists(cur, "business_tag_evidence_events", "review_note"):
                set_clauses.append("review_note = %s")
                params.append(request.note)
            if _pg_column_exists(cur, "business_tag_evidence_events", "reviewed_at"):
                set_clauses.append("reviewed_at = CURRENT_TIMESTAMP")

            params.append(event_id)
            cur.execute(
                f"""
                UPDATE business_tag_evidence_events
                SET {", ".join(set_clauses)}
                WHERE event_id = %s
                """,
                params,
            )

            event = {
                "event_id": str(row[0]),
                "mapping_id": str(row[1] or ""),
                "code": str(row[2] or ""),
                "node_id": row[3],
                "event_date": str(row[4]) if row[4] else None,
                "title": row[5],
                "excerpt": row[6],
                "confidence": confidence,
                "stage_after": stage_after or {},
            }
            stage_record = _stage_record_from_reviewed_event(event, review_status=review_status)
            stage_updated = False
            limitations: list[str] = []
            if stage_record:
                if not _pg_table_exists(cur, "business_tag_stage_tracking"):
                    limitations.append("business_tag_stage_tracking table is missing; evidence reviewed but stage not updated")
                else:
                    cur.execute(
                        """
                        INSERT INTO business_tag_stage_tracking (
                            stage_id, mapping_id, trade_date, research_stage,
                            commercialization_stage, stage_reason, source_event_id,
                            last_stage_change_date, review_status
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
                            stage_record["stage_id"],
                            stage_record["mapping_id"],
                            stage_record["trade_date"],
                            stage_record["research_stage"],
                            stage_record["commercialization_stage"],
                            stage_record["stage_reason"],
                            stage_record["source_event_id"],
                            stage_record["last_stage_change_date"],
                            stage_record["review_status"],
                        ),
                    )
                    stage_updated = True

            pg.commit()
            return {
                "version": "supply-chain-v2-evidence-review",
                "event_id": event_id,
                "mapping_id": event["mapping_id"],
                "review_status": review_status,
                "reviewer": request.reviewer,
                "stage_updated": stage_updated,
                "stage_record": stage_record,
                "limitations": limitations,
            }
    except HTTPException:
        raise
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


async def _candidate_pool_record_safe(
    db: AsyncSession | None,
    *,
    result: dict,
    mode: str,
    top_n: int,
    tenant_id: str | None,
    owner_user_id: str | None,
    account_id: str | None,
    data_scope: str | None,
) -> None:
    if db is None:
        return

    picks = result.get("picks") or []
    if not picks:
        return

    resolved_tenant = tenant_id or "tenant-default"
    resolved_scope = data_scope or ("account" if account_id or owner_user_id else "public")
    visibility = "public" if resolved_scope == "public" else "private"
    trade_date = result.get("trade_date") or datetime.now().strftime("%Y-%m-%d")
    time_slot = result.get("time_slot") or datetime.now().strftime("%H:%M")
    pool_id = f"POOL-{mode}-{trade_date}-{time_slot.replace(':', '')}-{account_id or owner_user_id or 'public'}"

    try:
        await candidate_pool_store.record(
            db,
            pool_id=pool_id,
            tenant_id=resolved_tenant,
            owner_user_id=owner_user_id,
            account_id=account_id,
            source_module="screener",
            source_mode=mode,
            name=f"{mode} 候选池",
            candidates=picks,
            metadata={
                "trade_date": trade_date,
                "time_slot": time_slot,
                "top_n": top_n,
                "elapsed": result.get("elapsed"),
            },
            visibility=visibility,
            data_scope=resolved_scope,
        )
        await db.commit()
    except Exception as e:
        await db.rollback()
        logger.warning("CandidatePool save failed (PG may not be available): %s", e)


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


@router.get("/modes")
async def list_modes():
    """List available screening modes with descriptions."""
    latest_dates: dict[str, str] = {}
    latest_trade_date = None
    try:
        latest_dates = _query_screener_latest_dates()
        latest_trade_date = latest_dates.get("daily_kline")
    except Exception as e:
        logger.warning("screener modes latest trade date unavailable: %s", e)
    return {
        "latest_trade_date": latest_trade_date,
        "latest_dates": latest_dates,
        "data_freshness": _screener_data_freshness(latest_trade_date, source="daily_kline"),
        "modes": [
            {"id": "leader_auction",  "name": "🔥秋神龙头竞价超预期战法 V4.3", "cycle": "1-3天",  "style": "竞价"},
            {"id": "leader_scalp",    "name": "秋神龙头战法-盘后", "cycle": "1-5天",  "style": "激进"},
            {"id": "leader_intraday", "name": "秋神龙头战法-盘中 V7.0", "cycle": "1-2天",  "style": "激进"},
            {"id": "leader_closing",  "name": "秋神龙头战法-尾盘顺势 V2.0", "cycle": "1-2天",  "style": "顺势"},
            {"id": "leader_afternoon","name": "🔥秋神龙头战法-午后选股 V1.0", "cycle": "1-2天",  "style": "午后"},
            {"id": "leader_afternoon_trend_full","name": "🔥秋神趋势启动午后全量版选股", "cycle": "1-3天",  "style": "午后全量"},
            {"id": "short",           "name": "匪爷短线多因子选股模型",       "cycle": "1-4周",  "style": "积极"},
            {"id": "chokepoint",      "name": "大葱卡脖子选股模型",       "cycle": "1-3月",  "style": "主题"},
            {"id": "cb_floor",       "name": "匪爷可转债底价安全垫选债模型 V3.0",   "cycle": "1-4周",  "style": "稳健"},
            {"id": "cb_intraday",    "name": "匪爷可转债日内投机博弈模型", "cycle": "1-2天",  "style": "激进"},
            {"id": "cb_auction",     "name": "秋神竞价概念选债模型",       "cycle": "1-2天",  "style": "竞价"},
            {"id": "cb_auction_t0",  "name": "竞价选债 T+0 模型",          "cycle": "T+0",    "style": "竞价"},
            {"id": "cb_auction_t0_v2", "name": "竞价选债 T+0 优化版 V2",   "cycle": "T+0",    "style": "竞价优化"},
            {"id": "cb_auction_t0_v2_1", "name": "竞价选债 T+0 优化版 V2.1 稳健版", "cycle": "T+0", "style": "稳健优化"},
            {"id": "bi_trend_launch","name": "毕师傅硬核科技趋势启动 V13", "cycle": "5-20天", "style": "趋势"},
            {"id": "bi_trend_full_market","name": "毕师傅全市场趋势启动 V1.0", "cycle": "5-20天", "style": "全市场"},
            {"id": "bi_shifu_trend","name": "毕师傅趋势战法 v2.0", "cycle": "5-20天", "style": "趋势"},
            {"id": "supply_chain",  "name": "产业链预期差选股模型", "cycle": "3-12月", "style": "产业链预期差"},
            {"id": "supply_chain_trend_launch", "name": "大葱产业链趋势启动战法 vFinal", "cycle": "1月", "style": "动态轮动"},
        ]
    }


@router.get("/market/index-quotes")
async def market_index_quotes(trade_date: Optional[str] = Query(None)):
    """Index quotes for the header tape.

    Real-time index quote vendors can be unavailable after close. This endpoint
    returns the latest local index_daily close snapshot at or before trade_date.
    """
    try:
        return _query_index_close_quotes(trade_date)
    except Exception as e:
        logger.warning("index close quote lookup failed: %s", e)
        return {
            "source": "index_daily_close",
            "as_of": None,
            "data": {"diff": []},
            "fallback_reason": str(e),
        }


@router.get("/supply-chain/themes")
async def supply_chain_themes():
    """Return policy themes and the top-level matrix for BOM drill-down."""
    return supply_chain_service.themes_payload()


@router.get("/supply-chain/bom")
async def supply_chain_bom():
    """Return the policy-BOM graph seed used by the V4 model."""
    return supply_chain_service.bom_payload()


@router.get("/supply-chain/layers")
async def supply_chain_layers():
    """Return the V2 L1-L8 supply-chain hierarchy."""
    return _query_supply_chain_layers()


@router.get("/supply-chain/layer/{layer_node_id}")
async def supply_chain_layer_detail(layer_node_id: str):
    """Return one L1-L8 layer node with ancestors and children."""
    return _query_supply_chain_layer_detail(layer_node_id)


@router.get("/supply-chain/data-readiness")
async def supply_chain_data_readiness():
    """Return V2 data readiness by L1-L8 layer and source."""
    return _query_supply_chain_data_readiness()


@router.get("/supply-chain/company/{code}/business-tags")
async def supply_chain_company_business_tags(code: str):
    """Return business-tag cards for one company with attribution limits."""
    return _query_company_business_tags(code)


@router.get("/supply-chain/business-tag/{mapping_id}/evidence")
async def supply_chain_business_tag_evidence(mapping_id: str):
    """Return evidence timeline for one business-tag mapping."""
    return _query_business_tag_evidence(mapping_id)


@router.get("/supply-chain/business-tag/{mapping_id}/evidence-chain")
async def supply_chain_business_tag_evidence_chain(mapping_id: str):
    """Return raw documents, extracted facts, freshness, stage transitions, and expectations."""
    return _query_business_tag_evidence_chain(mapping_id)


@router.get("/supply-chain/business-tag/{mapping_id}/stage")
async def supply_chain_business_tag_stage(mapping_id: str):
    """Return research and commercialization stages for one business-tag mapping."""
    return _query_business_tag_stage(mapping_id)


@router.post("/supply-chain/business-tag/{mapping_id}/evidence/extract")
async def supply_chain_business_tag_evidence_extract(
    mapping_id: str,
    request: BusinessTagEvidenceExtractRequest,
):
    """Extract and optionally persist a pending-review evidence event."""
    return _extract_business_tag_evidence_event(mapping_id, request)


@router.post("/supply-chain/evidence/batch-extract")
async def supply_chain_evidence_batch_extract(
    request: BusinessTagEvidenceBatchExtractRequest,
):
    """Batch extract pending-review evidence events from local source tables."""
    return _batch_extract_business_tag_evidence(request)


@router.post("/supply-chain/evidence/{event_id}/review")
async def supply_chain_evidence_review(
    event_id: str,
    request: BusinessTagEvidenceReviewRequest,
):
    """Review one evidence event and optionally update business-tag stage."""
    return _review_business_tag_evidence(event_id, request)


@router.get("/supply-chain/evidence-review/queue")
async def supply_chain_evidence_review_queue(
    limit: int = Query(50, ge=1, le=200),
):
    """Return evidence-chain review queue from stage, freshness, and expectation monitors."""
    return _query_evidence_review_queue(limit)


@router.get("/supply-chain/capex-evidence-review/queue")
async def supply_chain_capex_evidence_review_queue(
    limit: int = Query(50, ge=1, le=200),
    chain_id: Optional[str] = Query(None),
    review_status: str = Query("pending_review"),
):
    """Return mapped-company CAPEX evidence records waiting for review."""
    return _query_capex_evidence_review_queue(limit=limit, chain_id=chain_id, review_status=review_status)


@router.post("/supply-chain/capex-evidence/{capex_evidence_id}/review")
async def supply_chain_capex_evidence_review(
    capex_evidence_id: str,
    request: BusinessTagEvidenceReviewRequest,
):
    """Approve or reject one structured CAPEX evidence record."""
    return _review_capex_evidence(capex_evidence_id, request)


@router.post("/supply-chain/business-tag/{mapping_id}/three-high/score")
async def supply_chain_business_tag_three_high_score(
    mapping_id: str,
    request: BusinessTagThreeHighScoreRequest,
):
    """Calculate and optionally persist business-tag three-high score."""
    return _score_business_tag_three_high(mapping_id, request)


@router.get("/supply-chain/business-tag/{mapping_id}/three-high/score")
async def supply_chain_business_tag_three_high_score_latest(mapping_id: str):
    """Return latest business-tag three-high score snapshot."""
    return _query_business_tag_three_high_score(mapping_id)


@router.post("/supply-chain/business-tag/{mapping_id}/expectation-gap/score")
async def supply_chain_business_tag_expectation_gap_score(
    mapping_id: str,
    request: BusinessTagExpectationGapScoreRequest,
):
    """Calculate and optionally persist business-tag expectation-gap score."""
    return _score_business_tag_expectation_gap(mapping_id, request)


@router.get("/supply-chain/business-tag/{mapping_id}/expectation-gap/score")
async def supply_chain_business_tag_expectation_gap_score_latest(mapping_id: str):
    """Return latest business-tag expectation-gap score snapshot."""
    return _query_business_tag_expectation_gap_score(mapping_id)


@router.post("/supply-chain/business-tags/batch-score")
async def supply_chain_business_tags_batch_score(request: BusinessTagBatchScoreRequest):
    """Batch calculate and optionally persist business-tag score snapshots."""
    return _batch_score_business_tags(request)


@router.post("/supply-chain/refresh-workflow")
async def supply_chain_refresh_workflow(request: SupplyChainRefreshWorkflowRequest):
    """Run evidence extraction, human-review handoff, scoring, and ranking preview."""
    return _refresh_supply_chain_tracking_workflow(request)


@router.post("/supply-chain/inferred-data/materialize")
async def supply_chain_inferred_data_materialize(request: SupplyChainInferredMaterializeRequest):
    """Materialize rule-inferred L1-L8 tags, candidate evidence, and three-high baselines."""
    return _materialize_supply_chain_inferred_data(request)


@router.get("/supply-chain/rankings")
async def supply_chain_rankings(
    rank_type: str = Query("value", description="value or expectation_gap"),
    top_n: int = Query(50, ge=1, le=200),
    trade_date: Optional[str] = Query(None),
):
    """Return company rankings aggregated from business-tag scores."""
    return _query_supply_chain_rankings(rank_type, top_n, trade_date)


@router.get("/supply-chain/candidate-ranking")
async def supply_chain_candidate_ranking(
    top_n: int = Query(100, ge=1, le=200),
    chain_id: Optional[str] = Query(None),
    signal: Optional[str] = Query(None),
):
    """Return evidence-first company ranking from business-tag, L8, stage, freshness, and market data."""
    return _query_supply_chain_candidate_ranking(top_n=top_n, chain_id=chain_id, signal=signal)


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
    warnings: list[dict] = []
    data_status = {"candidate_pool": "ok", "upstream_influence": "ok"}
    try:
        candidates = await loop.run_in_executor(
            _executor,
            _get_supply_chain_candidate_pool,
            top_n,
            trade_date,
        )
        candidates = _attach_market_snapshots(candidates, trade_date)
    except Exception as e:
        logger.warning("supply_chain candidate pool unavailable: %s", e)
        candidates = []
        data_status["candidate_pool"] = "unavailable"
        warnings.append({
            "code": "candidate_pool_unavailable",
            "message": "候选池模型或行情数据源暂不可用，已返回真实BOM图谱；候选公司需要服务恢复后刷新。",
        })
    try:
        upstream_candidates = await loop.run_in_executor(
            _executor,
            _query_upstream_influence_candidates,
            50,
            trade_date,
        )
    except Exception as e:
        logger.warning("supply_chain upstream influence unavailable: %s", e)
        upstream_candidates = []
        data_status["upstream_influence"] = "unavailable"
        warnings.append({
            "code": "upstream_influence_unavailable",
            "message": "上游影响观察池暂不可用，已保留BOM图谱和主候选池结果。",
        })
    node_by_id = {node.get("node_id"): node for node in payload["nodes"]}
    selected_node = node_by_id.get(node_id or "")
    if node_id and not selected_node:
        raise HTTPException(status_code=404, detail=f"Unknown BOM node '{node_id}'")
    if not candidates and data_status["candidate_pool"] == "ok":
        fallback_candidates = _query_business_tag_mapping_candidates(top_n, selected_node.get("node_id") if selected_node else None)
        if fallback_candidates:
            candidates = _attach_market_snapshots(fallback_candidates, trade_date)
            data_status["candidate_pool"] = "mapping_fallback"
            warnings.append({
                "code": "candidate_pool_mapping_fallback",
                "message": "模型候选池为空，已改用 business_tag_mapping 真实业务标签映射作为候选公司清单。",
            })
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
        "data_status": data_status,
        "warnings": warnings,
        "data_freshness": _query_supply_chain_data_freshness(),
        "research_ingestion": _query_research_ingestion_status(),
        "resonance_model": {"dimensions": ["policy", "commercialization", "order_capacity", "performance", "market"]},
        "stage_options": ["预研验证", "中试", "小批量验证", "量产爬坡", "规模推广", "成熟"],
    }


@router.get("/supply-chain/mapping-review/queue")
async def supply_chain_mapping_review_queue(
    status: str = Query("reviewable"),
    node_id: Optional[str] = Query(None),
    chain_id: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """Return reviewable company-to-chain mappings sorted by review priority."""
    allowed_statuses = {"reviewable", "pending_review", "weak_evidence", "verified", "rejected"}
    if status not in allowed_statuses:
        raise HTTPException(status_code=400, detail=f"Unsupported status '{status}'")
    return _query_supply_chain_mapping_review_queue(status, node_id, chain_id, limit, offset)


@router.get("/supply-chain/mapping-review/quality")
async def supply_chain_mapping_review_quality():
    """Return mapping quality counts and node-level review pressure."""
    return _query_supply_chain_mapping_quality()


@router.post("/supply-chain/mapping-review/{code}/{node_id}")
async def supply_chain_mapping_review_decision(
    code: str,
    node_id: str,
    payload: SupplyChainMappingReviewRequest,
):
    """Apply a human review decision to one company-node mapping."""
    result = _apply_supply_chain_mapping_review(
        code=code,
        node_id=node_id,
        decision=payload.decision,
        reviewer=payload.reviewer,
        note=payload.note,
    )
    if result.get("status") == "not_found":
        raise HTTPException(status_code=404, detail=result.get("reason") or "mapping not found")
    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result.get("reason") or "mapping review failed")
    return result


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

    from app.llm_multi_provider import PROVIDER_CONFIG, _missing_api_key_message
    provider_config = PROVIDER_CONFIG.get(provider)
    if not provider_config:
        return {
            "status": "disabled",
            "reason": f"unsupported provider: {provider}",
            "report_count": len(reports),
            "source_table": "research_reports_tushare",
            "reports": reports,
        }
    if not os.environ.get(provider_config["api_key_env"]):
        return {
            "status": "disabled",
            "reason": _missing_api_key_message(provider, provider_config["api_key_env"]),
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


@router.post(
    "/policy/interpret",
    response_model=PolicyInterpretResponse,
    operation_id="policy_interpret",
    summary="Interpret policy document via LLM",
)
async def policy_interpret(request: PolicyInterpretRequest = Body(...)):
    """Interpret policy document text using LLM to extract structured insights.

    Extracts:
    - summary: Brief policy summary
    - industry_themes: Identified industry themes with policy intensity
    - bom_nodes: Supply-chain BOM nodes mentioned
    - investment_logic: Investment thesis and rationale
    - risk_factors: Risk factors identified

    Optionally persists results to policy_interpretations table when persist=True.
    """
    text = str(request.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="text is required")

    source = request.source if isinstance(request.source, dict) else {}
    provider = str(request.provider or "deepseek")

    # Check if LLM is enabled (has API key for the requested provider)
    from app.llm_multi_provider import PROVIDER_CONFIG, ProviderConfigError

    provider_config = PROVIDER_CONFIG.get(provider)
    if not provider_config:
        return PolicyInterpretResponse(
            status="disabled",
            reason=f"Unknown provider: {provider}",
        )

    api_key_env = provider_config.get("api_key_env")
    if not os.environ.get(api_key_env):
        return PolicyInterpretResponse(
            status="disabled",
            reason=f"{api_key_env} missing",
        )

    try:
        # Build prompt and call LLM
        from app.llm_policy_interpret import (
            build_policy_interpret_prompt,
            parse_interpretation_json,
        )
        from app.llm_multi_provider import call_llm_with_fallback, LLMResponse

        prompt = build_policy_interpret_prompt(text, source)
        messages = [{"role": "user", "content": prompt}]

        t0 = time.time()
        llm_response: LLMResponse = await call_llm_with_fallback(
            messages,
            provider_override=provider,
            temperature=0.3,  # Lower temperature for structured extraction
            max_tokens=2000,
        )
        elapsed = time.time() - t0

        logger.info(
            "policy_interpret LLM call: provider=%s, tokens=%d, elapsed=%.2fs",
            llm_response.usage.provider,
            llm_response.usage.total_tokens,
            elapsed,
        )

        # Parse LLM response into structured interpretation
        interpretation = parse_interpretation_json(llm_response.content)

        # Build usage info
        usage = LLMUsageInfo(
            prompt_tokens=llm_response.usage.prompt_tokens,
            completion_tokens=llm_response.usage.completion_tokens,
            total_tokens=llm_response.usage.total_tokens,
            provider=llm_response.usage.provider,
            model=llm_response.usage.model,
        )

        # Build interpretation result
        result = InterpretationResult(
            summary=interpretation.get("summary", ""),
            industry_themes=interpretation.get("industry_themes", []),
            bom_nodes=interpretation.get("bom_nodes", []),
            investment_logic=interpretation.get("investment_logic", ""),
            risk_factors=interpretation.get("risk_factors", []),
        )

        # Persist if requested
        persisted = False
        if request.persist:
            persist_result = _persist_policy_interpretation(
                text, source, interpretation, usage
            )
            persisted = persist_result.get("status") == "ok"
            if not persisted:
                logger.warning("policy_interpret persist failed: %s", persist_result.get("reason"))

        return PolicyInterpretResponse(
            status="ok",
            interpretation_result=result,
            usage=usage,
            persisted=persisted,
        )

    except ProviderConfigError as e:
        logger.warning("policy_interpret provider config error: %s", e)
        return PolicyInterpretResponse(
            status="disabled",
            reason=str(e),
        )
    except Exception as e:
        logger.exception("policy_interpret failed: %s", e)
        return PolicyInterpretResponse(
            status="error",
            reason=str(e),
        )


@router.post("/run")
async def run_screening(
    mode: str = Query("short", description="Screening mode"),
    top_n: int = Query(DEFAULT_TOP_N, ge=5, le=MAX_TOP_N, description="Top N picks"),
    trade_date: Optional[str] = Query(None, description="Trade date (YYYY-MM-DD), defaults to latest"),
    tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    owner_user_id: str | None = Header(default=None, alias="X-Owner-User-Id"),
    account_id: str | None = Header(default=None, alias="X-Trade-Account-Id"),
    data_scope: str | None = Header(default=None, alias="X-Data-Scope"),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    db: AsyncSession | None = Depends(get_db),
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
    pipeline_run = None
    if db is not None:
        request_payload = {"mode": mode, "top_n": top_n, "trade_date": trade_date}
        key = idempotency_key or hashlib.sha256(json.dumps(request_payload, sort_keys=True).encode()).hexdigest()
        pipeline_run = await submit_persisted_pipeline(db, request_payload, key)

    # ── Redis cache check (L4: screener results, TTL 1h) ──
    cache_key = f"screener:{mode}:{top_n}:{trade_date or 'latest'}"
    try:
        from app.cache import cache_get
        cached = await cache_get(cache_key)
        if cached:
            cached["cached"] = True
            cached["elapsed"] = round(time.time() - t0, 1)
            if not cached.get("result_status"):
                cached["result_status"] = "success" if cached.get("picks") else "success_no_matches"
            response = _with_screener_contract(cached, mode=mode, trade_date=trade_date)
            if pipeline_run is not None:
                await finish_persisted_pipeline(db, pipeline_run.run_id, result=response)
                response["run_id"] = pipeline_run.run_id
            return response
    except Exception:
        pass  # cache miss or Redis unavailable → proceed normally

    try:
        if mode in ("leader_scalp", "leader_intraday", "leader_auction", "leader_closing"):
            result = await loop.run_in_executor(
                _executor, _run_leader_mode, mode, top_n, trade_date
            )
        elif mode in ("leader_afternoon", "leader_afternoon_trend_full"):
            result = await loop.run_in_executor(
                _executor, _run_afternoon_mode, mode, top_n, trade_date
            )
        elif mode in ("cb_floor", "cb_intraday", "cb_auction", "cb_auction_t0", "cb_auction_t0_v2", "cb_auction_t0_v2_1"):
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
        elif mode == "bi_shifu_trend":
            result = await loop.run_in_executor(
                _executor, _run_bi_shifu_trend_mode, mode, top_n, trade_date
            )
        elif mode == "supply_chain":
            result = await loop.run_in_executor(
                _executor, _run_supply_chain_mode, mode, top_n, trade_date
            )
        elif mode == "supply_chain_trend_launch":
            result = await loop.run_in_executor(
                _executor, _run_supply_chain_trend_launch_mode, mode, top_n, trade_date
            )
        else:
            result = await loop.run_in_executor(
                _executor, _run_multifactor_mode, mode, top_n, trade_date
            )
    except Exception as e:
        err = str(e)
        logger.exception("Screening failed for mode=%s: %s", mode, err)
        if pipeline_run is not None:
            await finish_persisted_pipeline(db, pipeline_run.run_id, error={"message": err})
        if any(k in err.lower() for k in ("division by zero", "'code'", "'pct_chg'", "keyerror", "none")):
            raise HTTPException(status_code=503, detail="数据不足：部分行情数据缺失或不完整，请等待数据同步完成后再试")
        if "does not exist" in err.lower():
            raise HTTPException(status_code=503, detail="数据库表缺失：部分数据表未迁移，请先运行数据同步")
        raise HTTPException(status_code=500, detail=f"Screening failed: {err}")

    result["elapsed"] = round(time.time() - t0, 1)
    if not result.get("trade_date") or result.get("trade_date") == "latest":
        try:
            result["trade_date"] = _resolve_trade_date(trade_date)
        except RuntimeError as exc:
            if pipeline_run is not None:
                await finish_persisted_pipeline(db, pipeline_run.run_id, error={"message": str(exc)})
            raise HTTPException(
                status_code=503,
                detail="数据不足：无法确定最新交易日，请等待行情数据同步完成后重试",
            ) from exc

    # ── Sanitize numpy types across all modes ──
    if "picks" in result and result["picks"]:
        result["picks"] = _sanitize_picks(result["picks"])
        result["picks"] = _normalize_picks(result["picks"], mode)
    if not result.get("result_status"):
        result["result_status"] = "success" if result.get("picks") else "success_no_matches"

    # ── Auto-save snapshot (JSON file + PG) — before cache to ensure persistence ──
    _auto_save_snapshot(result, mode)
    await _candidate_pool_record_safe(
        db,
        result=result,
        mode=mode,
        top_n=top_n,
        tenant_id=tenant_id,
        owner_user_id=owner_user_id,
        account_id=account_id,
        data_scope=data_scope,
    )

    # ── Redis cache write (L4: screener results, TTL 1h) ──
    try:
        from app.cache import cache_set
        loop.create_task(cache_set(cache_key, result, ttl=3600))
    except Exception:
        pass

    response = _with_screener_contract(result, mode=mode, trade_date=trade_date)
    if pipeline_run is not None:
        await finish_persisted_pipeline(db, pipeline_run.run_id, result=response)
        response["run_id"] = pipeline_run.run_id
    return response


def _run_leader_mode(mode: str, top_n: int, trade_date: Optional[str]) -> dict:
    """Run Leader Scalp strategy (daily or intraday)."""
    from kronos_factors.engine import (
        run_leader_screening, run_intraday_screening,
        generate_execution_plan, generate_intraday_plan,
    )
    td = _resolve_intraday_trade_date(trade_date) if mode in {"leader_intraday", "leader_closing"} else _resolve_trade_date(trade_date)

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
        "trade_date": td,
        "total_picks": len(picks_out),
        "picks": picks_out,
        "execution_plans": plans,
    }


def _run_cb_mode(mode: str, top_n: int, trade_date: Optional[str]) -> dict:
    """Run convertible bond screening modes."""
    from kronos_factors.engine.cb_floor import CbFloorEngine
    from kronos_factors.engine.cb_intraday import CbIntradayEngine
    from kronos_factors.engine.cb_auction import CbAuctionEngine
    from kronos_factors.engine.cb_auction_t0 import CbAuctionT0Engine, CbAuctionT0V21Engine, CbAuctionT0V2Engine

    engine_map = {
        "cb_floor": CbFloorEngine,
        "cb_intraday": CbIntradayEngine,
        "cb_auction": CbAuctionEngine,
        "cb_auction_t0": _CB_AUCTION_T0_ENGINE or CbAuctionT0Engine,
        "cb_auction_t0_v2": _CB_AUCTION_T0_V2_ENGINE or CbAuctionT0V2Engine,
        "cb_auction_t0_v2_1": _CB_AUCTION_T0_V21_ENGINE or CbAuctionT0V21Engine,
    }
    engine = engine_map[mode]()

    raw_result = engine.run(trade_date=trade_date, top_n=top_n)
    engine.close()

    if mode in ("cb_auction_t0", "cb_auction_t0_v2", "cb_auction_t0_v2_1") and isinstance(raw_result, dict):
        trade_date = str(raw_result.get("trade_date") or trade_date or "")
        def map_bonds(bonds: list[dict[str, Any]]) -> list[dict[str, Any]]:
            mapped = []
            for bond in bonds:
                item = dict(bond)
                item["code"] = item.get("code") or item.get("cb_code")
                item["name"] = item.get("name") or item.get("cb_name")
                item["score"] = item.get("score") or item.get("theme_score")
                item["entry_reason"] = item.get("entry_reason") or item.get("relation_reason")
                item["risk_flags"] = item.get("risk_flags") or item.get("risk_notes") or []
                mapped.append(item)
            return mapped

        picks = map_bonds(raw_result.get("bonds", []))
        observation_picks = map_bonds(raw_result.get("observation_bonds", []))
    else:
        picks = raw_result
        observation_picks = []

    picks = _sanitize_picks(picks)
    picks = _normalize_picks(picks, mode)
    observation_picks = _sanitize_picks(observation_picks)
    observation_picks = _normalize_picks(observation_picks, mode)

    result = {
        "mode": mode,
        "trade_date": trade_date,
        "total_picks": len(picks),
        "picks": picks,
        "observation_picks": observation_picks,
        "total_observation_picks": len(observation_picks),
    }
    if mode in ("cb_auction_t0", "cb_auction_t0_v2", "cb_auction_t0_v2_1") and isinstance(raw_result, dict):
        result.update(_build_cb_t0_process(mode, trade_date, raw_result, picks, observation_picks))
    return result


def _build_cb_t0_process(
    mode: str,
    trade_date: str,
    raw_result: dict[str, Any],
    picks: list[dict[str, Any]],
    observation_picks: list[dict[str, Any]],
) -> dict[str, Any]:
    """Summarize CB T+0 screening steps for transparent empty-result UI."""
    triggers = raw_result.get("trigger_stocks") or []
    concepts = raw_result.get("concepts") or []
    rejections = raw_result.get("rejections") or []
    trigger_count = len(triggers)
    concept_count = len(concepts)
    main_count = len(picks)
    observation_count = len(observation_picks)
    rejection_count = len(rejections)

    rejection_summary: dict[str, int] = {}
    for item in rejections:
        reason = str(item.get("reason") or "未说明原因")
        rejection_summary[reason] = rejection_summary.get(reason, 0) + 1

    if trigger_count == 0:
        no_result_reason = (
            f"{trade_date} 未找到符合竞价 T+0 条件的触发股。"
            "常见原因是当日竞价/涨停数据未入库，或没有封单金额达到模型阈值的正股。"
        )
    elif concept_count == 0:
        no_result_reason = "触发股存在，但未映射到有效同花顺概念，无法继续匹配转债。"
    elif main_count == 0 and observation_count > 0:
        no_result_reason = "稳健主买规则筛选后无可买入债，候选只进入观察池。"
    elif main_count == 0 and rejection_summary:
        top_reason = max(rejection_summary.items(), key=lambda item: item[1])[0]
        no_result_reason = f"转债候选被风控规则剔除，主要原因：{top_reason}。"
    elif main_count == 0:
        no_result_reason = "触发概念下未匹配到满足条件的可转债。"
    else:
        no_result_reason = None

    screening_trace = [
        {
            "step": "交易日确认",
            "status": "ok",
            "detail": f"使用交易日 {trade_date}",
        },
        {
            "step": "触发股筛选",
            "status": "ok" if trigger_count else "empty",
            "detail": f"竞价触发股 {trigger_count} 只",
        },
        {
            "step": "概念映射",
            "status": "ok" if concept_count else ("skipped" if trigger_count == 0 else "empty"),
            "detail": f"有效概念 {concept_count} 个",
        },
        {
            "step": "转债匹配",
            "status": "ok" if main_count or observation_count else ("skipped" if concept_count == 0 else "empty"),
            "detail": f"主买 {main_count} 只，观察 {observation_count} 只",
        },
        {
            "step": "输出分层",
            "status": "ok" if main_count else ("review" if observation_count else "empty"),
            "detail": (
                f"{mode} 输出主买 {main_count} 只"
                + (f"，观察池 {observation_count} 只" if observation_count else "")
                + (f"，剔除 {rejection_count} 条" if rejection_count else "")
            ),
        },
    ]

    return {
        "process_summary": {
            "trigger_stock_count": trigger_count,
            "concept_count": concept_count,
            "main_pick_count": main_count,
            "observation_pick_count": observation_count,
            "rejection_count": rejection_count,
        },
        "screening_trace": screening_trace,
        "rejection_summary": [
            {"reason": reason, "count": count}
            for reason, count in sorted(rejection_summary.items(), key=lambda item: (-item[1], item[0]))
        ],
        "no_result_reason": no_result_reason,
    }


def _load_supply_chain_expectation_gap_snapshot(top_n: int, trade_date: Optional[str]) -> Optional[dict]:
    model_key = "supply_chain_expectation_gap_v1"
    time_slot = "close"
    try:
        with _pg_connect() as conn:
            with conn.cursor() as cur:
                if not _pg_table_exists(cur, "screening_snapshots"):
                    return None
                resolved_trade_date = trade_date
                if not resolved_trade_date:
                    cur.execute(
                        """
                        SELECT max(trade_date)
                        FROM screening_snapshots
                        WHERE model_key = %s AND time_slot = %s
                        """,
                        (model_key, time_slot),
                    )
                    row = cur.fetchone()
                    resolved_trade_date = str(row[0]) if row and row[0] else None
                if not resolved_trade_date:
                    return None
                cur.execute(
                    """
                    SELECT
                        ss.stock_code,
                        coalesce(s.name, split_part(ss.stock_code, '.', 1)) AS name,
                        ss.total_score,
                        ss.grade,
                        ss.rank_in_day,
                        ss.factors,
                        ss.trade_date
                    FROM screening_snapshots ss
                    LEFT JOIN stocks s ON s.code = split_part(ss.stock_code, '.', 1)
                    WHERE ss.model_key = %s
                      AND ss.time_slot = %s
                      AND ss.trade_date = %s
                    ORDER BY ss.rank_in_day ASC
                    LIMIT %s
                    """,
                    (model_key, time_slot, resolved_trade_date, top_n),
                )
                rows = cur.fetchall()
        if not rows:
            return None
        picks = []
        for stock_code, name, total_score, grade, rank, factors, row_trade_date in rows:
            if isinstance(factors, str):
                factors = json.loads(factors)
            if not isinstance(factors, dict):
                factors = {}
            pick = {
                "rank": int(rank or len(picks) + 1),
                "code": str(stock_code),
                "name": str(name),
                "score": _to_float(total_score, 0.0),
                "total_score": _to_float(total_score, 0.0),
                "grade": str(grade or ""),
                "signal": factors.get("signal_tier"),
                "industry": factors.get("chain_id") or "产业链预期差",
                "chain_id": factors.get("chain_id"),
                "tag_name": factors.get("tag_name"),
                "source_mode": "supply_chain",
                "trade_date": str(row_trade_date),
            }
            for key in (
                "expectation_gap_score",
                "reliability_adjusted_gap_score",
                "evidence_quality_score",
                "label_fit_score",
                "reassessment_status",
                "gap_momentum_score",
                "three_high_total",
                "growth_score",
                "profit_score",
                "moat_score",
            ):
                if key in factors:
                    pick[key] = factors.get(key)
            picks.append(pick)
        return {
            "mode": "supply_chain",
            "model_key": model_key,
            "trade_date": str(rows[0][6]),
            "total_picks": len(picks),
            "picks": picks,
            "source": "screening_snapshots",
            "score_contract": "reassessment_adjusted",
        }
    except Exception as exc:
        logger.warning("Load supply-chain expectation-gap snapshot failed: %s", exc)
        return None


def _run_supply_chain_mode(mode: str, top_n: int, trade_date: Optional[str]) -> dict:
    """Run the supply-chain entry, preferring expectation-gap registered snapshots."""
    snapshot = _load_supply_chain_expectation_gap_snapshot(top_n, trade_date)
    if snapshot and snapshot.get("picks"):
        snapshot["mode"] = mode
        for pick in snapshot["picks"]:
            pick["source_mode"] = mode
        return snapshot

    from kronos_factors.engine.supply_chain import SupplyChainEngine

    resolved_trade_date = _resolve_trade_date(trade_date)
    engine = SupplyChainEngine()
    result = engine.run(top_n=top_n, trade_date=resolved_trade_date)

    picks = result.get("picks", []) if isinstance(result, dict) else getattr(result, "picks", [])
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
        "trade_date": resolved_trade_date,
        "total_picks": len(picks),
        "picks": picks,
    }


def _run_supply_chain_trend_launch_mode(mode: str, top_n: int, trade_date: Optional[str]) -> dict:
    """Run 产业链趋势启动选股 vFinal."""
    from kronos_factors.engine.supply_chain_trend import TrendLaunchEngine

    resolved_trade_date = _resolve_trade_date(trade_date)
    engine = TrendLaunchEngine()
    result = engine.run(top_n=top_n, trade_date=resolved_trade_date)

    picks = result.picks
    picks = _sanitize_picks(picks)
    for p in picks:
        sc = p.get("total_score", 0)
        if sc >= 75: p["grade"] = "S"
        elif sc >= 60: p["grade"] = "A"
        elif sc >= 45: p["grade"] = "B"
        else: p["grade"] = "C"

    return {
        "mode": mode,
        "trade_date": resolved_trade_date,
        "total_picks": len(picks),
        "picks": picks,
        "metadata": result.metadata,
    }


def _run_multifactor_mode(mode: str, top_n: int, trade_date: Optional[str]) -> dict:
    """Run multi-factor mode (short/chokepoint)."""
    from kronos_factors.engine.modes import (
        ShortModeEngine, ChokepointEngine,
    )

    engine_map = {
        "short": ShortModeEngine,
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

    resolved_trade_date = _resolve_trade_date(trade_date)
    engine = BiTrendLaunchEngine()
    picks = engine.run(top_n=top_n, trade_date=resolved_trade_date)

    picks = _sanitize_picks(picks)
    picks = _normalize_picks(picks, mode)

    # Generate execution plans with market regime awareness
    regime = "neutral"
    plans = generate_bi_plan(picks, market_regime=regime) if picks else []

    return {
        "mode": mode,
        "trade_date": resolved_trade_date,
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


def _run_bi_shifu_trend_mode(mode: str, top_n: int, trade_date: Optional[str]) -> dict:
    """Run 毕师傅趋势战法 v2.0 (全市场多维度评分 + 趋势识别)."""
    from kronos_factors.engine.bi_shifu_trend import BiShifuTrendEngine

    resolved_trade_date = _resolve_trade_date(trade_date)
    engine = BiShifuTrendEngine()
    picks = engine.run(top_n=top_n, trade_date=resolved_trade_date)

    picks = _sanitize_picks(picks)
    picks = _normalize_picks(picks, mode)

    return {
        "mode": mode,
        "trade_date": resolved_trade_date,
        "total_picks": len(picks),
        "picks": picks,
    }


def _run_afternoon_mode(mode: str, top_n: int, trade_date: Optional[str]) -> dict:
    """Run 秋神龙头战法-午后选股 V1.0 (14:30 afternoon leader screening)."""
    from kronos_factors.engine.leader_afternoon import (
        AfternoonLeaderEngine,
        AfternoonTrendFullEngine,
        build_sector_resonance_summary,
        resolve_afternoon_trade_date,
    )

    is_full = mode == "leader_afternoon_trend_full"
    engine = AfternoonTrendFullEngine() if is_full else AfternoonLeaderEngine()
    run_top_n = max(top_n, 30) if is_full else top_n
    if trade_date is None:
        with _get_factor_db() as db:
            trade_date = resolve_afternoon_trade_date(db)
    picks = engine.run(top_n=run_top_n, trade_date=trade_date, time_slot="14:30")

    picks = _sanitize_picks(picks)
    picks = _normalize_picks(picks, mode)
    sector_resonance = build_sector_resonance_summary(picks) if is_full else []

    result = {
        "mode": mode,
        "trade_date": trade_date,
        "total_picks": len(picks),
        "picks": picks,
    }
    if is_full:
        result["sector_resonance"] = sector_resonance
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Industry Chain Deconstruct Endpoints (Phase 2)
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/chain/deconstruct")
async def chain_deconstruct(
    theme_id: str = Query(..., description="Industry theme ID (e.g., 'semiconductor')"),
    method: str = Query("upstream_downstream", description="Deconstruct method: bom, upstream_downstream, value_chain, competition"),
    template: Optional[str] = Query(None, description="Optional industry-link template, e.g. complex_tech"),
):
    """Return industry chain deconstruct tree with selected view method.

    Methods:
    - bom: L1-L8 BOM tree and root-to-leaf paths
    - upstream_downstream: 5-layer tree (原材料→零部件→制造→渠道→终端)
    - value_chain: tree + margin/pricing_power/value_added per node
    - competition: tree + concentration/leader_share/barrier/threat per node
    - template=complex_tech: 8-layer complex-technology industry-link template
    """
    from kronos_factors.engine.chain_deconstruct import deconstruct_chain

    # Query chain_nodes from PG for the given theme_id
    fallback_reason = None
    try:
        with _pg_connect() as pg:
            cur = pg.cursor()
            cur.execute(
                """
                SELECT node_id, theme_id, node_name, layer, parent_node_id,
                       upstream_nodes, downstream_nodes, value_chain, competition
                FROM chain_nodes
                WHERE theme_id = %s
                ORDER BY layer, node_id
                """,
                (theme_id,),
            )
            rows = cur.fetchall()
            if not rows:
                nodes, theme_name = _seed_chain_nodes_for_deconstruct(theme_id)
                if not nodes:
                    raise HTTPException(status_code=404, detail=f"Theme '{theme_id}' not found in chain_nodes")
                fallback_reason = "chain_nodes is empty; using bundled BOM seed config"
                logger.info(
                    "chain_deconstruct fallback to bundled BOM seed for theme_id=%s",
                    theme_id,
                )
            else:
                # Get theme_name from industry_themes
                cur.execute(
                    "SELECT theme_name FROM industry_themes WHERE theme_id = %s",
                    (theme_id,),
                )
                theme_row = cur.fetchone()
                theme_name = str(theme_row[0]) if theme_row else theme_id

                # Build nodes list for deconstruct_chain
                nodes = []
                for row in rows:
                    node = {
                        "node_id": str(row[0] or ""),
                        "theme_id": str(row[1] or ""),
                        "node_name": str(row[2] or ""),
                        "layer": int(row[3] or 0),
                        "parent_node_id": str(row[4] or "") if row[4] else None,
                        "upstream_nodes": _json_or_default(row[5], []),
                        "downstream_nodes": _json_or_default(row[6], []),
                        "value_chain": _json_or_default(row[7], {}),
                        "competition": _json_or_default(row[8], {}),
                    }
                    nodes.append(node)

    except HTTPException:
        raise
    except Exception as e:
        logger.warning("chain_deconstruct query failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Database query failed: {e}")

    # Call deconstruct_chain with the nodes
    try:
        result = deconstruct_chain(theme_id, method, nodes, theme_name, template=template)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return _with_screener_contract(
        result,
        mode=f"chain:{template or method}",
        fallback_reason=fallback_reason,
        source="chain_nodes",
    )


@router.get("/chain/node/{node_id}/companies")
async def chain_node_companies(node_id: str):
    """Return companies mapped to a specific chain node with resonance scores.

    Response includes:
    - node_id, node_name
    - companies: list of mapped companies with code, name, main_pct, resonance, trade_signal
    """
    try:
        with _pg_connect() as pg:
            cur = pg.cursor()

            # 1. Verify node exists and get node_name
            cur.execute(
                "SELECT node_id, node_name FROM chain_nodes WHERE node_id = %s",
                (node_id,),
            )
            node_row = cur.fetchone()
            if not node_row:
                raise HTTPException(status_code=404, detail=f"Node '{node_id}' not found")
            node_name = str(node_row[1] or node_id)

            # 2. Query company_chain_mapping for the node
            cur.execute(
                """
                SELECT m.code, COALESCE(s.name, m.code) AS name, m.main_pct,
                       m.policy_match_score, m.chokepoint_score, m.evidence,
                       m.three_factors, m.trade_signal
                FROM company_chain_mapping m
                LEFT JOIN stocks s ON s.code = m.code
                WHERE m.node_id = %s
                  AND (m.valid_to IS NULL OR m.valid_to >= CURRENT_DATE)
                ORDER BY m.chokepoint_score DESC NULLS LAST, m.main_pct DESC NULLS LAST
                LIMIT 50
                """,
                (node_id,),
            )
            rows = cur.fetchall()

            companies = []
            for idx, row in enumerate(rows, start=1):
                three_factors = _json_or_default(row[6], {})
                evidence = _json_or_default(row[5], [])

                # Derive resonance summary from three_factors
                resonance = _derive_resonance_from_three_factors(three_factors)

                companies.append({
                    "code": str(row[0] or ""),
                    "name": str(row[1] or ""),
                    "rank": idx,
                    "main_pct": _to_float(row[2], None),
                    "policy_match_score": _to_float(row[3], None),
                    "chokepoint_score": int(row[4] or 0),
                    "evidence": evidence,
                    "three_factors": three_factors,
                    "trade_signal": str(row[7] or "观察"),
                    "resonance": resonance,
                })

            return {
                "node_id": node_id,
                "node_name": node_name,
                "company_count": len(companies),
                "companies": companies,
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.warning("chain_node_companies query failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Database query failed: {e}")


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
        return perf_yield >= 15.0

    if filter_type == "high_profit":
        gross_margin = _to_float(candidate.get("gross_margin", 0))
        profit_dim = _to_float(dim_scores.get("profit", 0))
        # High profit: gross_margin >= 50% OR profit_dim >= 10 (V5 max)
        return gross_margin >= 50.0 or profit_dim >= 10.0

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


@router.get(
    "/chain/candidates",
    response_model=dict,
    operation_id="chain_candidates",
    summary="Get filtered supply-chain candidates with V6 resonance scoring",
)
async def chain_candidates(
    filter: str = Query("all", description="Filter type: high_growth, high_profit, high_moat, chokepoint_core, all"),
    resonance_level: Optional[str] = Query(None, description="Resonance level: 强启动, 启动, 关注, 观察"),
    top_n: int = Query(30, ge=5, le=MAX_TOP_N, description="Top N candidates"),
    trade_date: Optional[str] = Query(None, description="Trade date (YYYY-MM-DD)"),
):
    """Return filtered supply-chain candidates with three-factor resonance V6 scoring.

    This endpoint integrates derive_resonance_v6 scoring and provides multi-dimensional filtering:

    Filter types:
    - high_growth: Candidates with performance_yield >= 15 (yoy >= 50%)
    - high_profit: Candidates with gross_margin >= 50% or profit dimension >= 10
    - high_moat: Candidates with chokepoint_score >= 6 or chokepoint keywords
    - chokepoint_core: Candidates classified as "卡脖子核心" level
    - all: No filter (default)

    Resonance levels (V6 three-factor resonance):
    - 强启动: All 3 factors pass threshold (industry_cycle >= 9, policy >= 9, performance >= 15)
    - 启动: 2 factors pass threshold
    - 关注: 1 factor passes threshold
    - 观察: 0 factors pass threshold (default catch-all)

    Response includes:
    - candidates: list of filtered candidates with three_factor_scores + resonance summary
    - filter_summary: counts per filter type
    - resonance_summary: counts per resonance level
    """
    # Validate filter parameter
    filter_type = str(filter or "all").strip().lower()
    if filter_type not in VALID_FILTERS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid filter '{filter}'. Valid: {sorted(VALID_FILTERS)}"
        )

    # Validate resonance_level parameter
    if resonance_level:
        level = str(resonance_level).strip()
        if level not in VALID_RESONANCE_LEVELS:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid resonance_level '{resonance_level}'. Valid: {sorted(VALID_RESONANCE_LEVELS)}"
            )

    t0 = time.time()
    loop = asyncio.get_running_loop()

    # Get candidate pool from supply_chain mode
    candidates = await loop.run_in_executor(
        _executor,
        _get_supply_chain_candidate_pool,
        100,  # Fetch more for filtering
        trade_date,
    )
    candidates = _attach_market_snapshots(candidates, trade_date)

    # Enrich each candidate with V6 resonance scoring
    enriched_candidates = [_enrich_candidate_with_resonance_v6(c) for c in candidates]

    # Apply filter type
    filtered_by_type = [c for c in enriched_candidates if _filter_candidate_by_filter_type(c, filter_type)]

    # Apply resonance_level filter
    filtered_candidates = [c for c in filtered_by_type if _filter_candidate_by_resonance_level(c, resonance_level)]

    # Sort by resonance_factors (descending), then by score (descending)
    filtered_candidates.sort(
        key=lambda c: (
            int(c.get("resonance_factors", 0)),
            _to_float(c.get("score", 0)),
        ),
        reverse=True,
    )

    # Limit to top_n
    top_candidates = filtered_candidates[:top_n]

    # Build filter summary (counts for all filter types)
    filter_summary = {}
    for ft in sorted(VALID_FILTERS):
        count = sum(1 for c in enriched_candidates if _filter_candidate_by_filter_type(c, ft))
        filter_summary[ft] = count

    # Build resonance summary (counts for all resonance levels)
    resonance_summary = {}
    for level in sorted(VALID_RESONANCE_LEVELS):
        count = sum(1 for c in enriched_candidates if _filter_candidate_by_resonance_level(c, level))
        resonance_summary[level] = count

    return {
        "filter": filter_type,
        "resonance_level": resonance_level,
        "total_candidates": len(candidates),
        "filtered_count": len(filtered_candidates),
        "top_n": top_n,
        "candidates": top_candidates,
        "filter_summary": filter_summary,
        "resonance_summary": resonance_summary,
        "elapsed": round(time.time() - t0, 2),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Candidate Pool REST API — 解封"选股 → 加候选池 → 决策"咽喉
#
# Scope（tenant_id / owner_user_id / account_id）全部从认证头注入，前端绝不传明文。
# pool_id 由后端按 POOL-{mode}-{trade_date}-{time_slot}-{scope} 生成（幂等 UPSERT）。
# ─────────────────────────────────────────────────────────────────────────────

class _LegacyCandidatePoolRecordRequest(BaseModel):
    """POST /screener/candidate-pool 入参。

    scope 字段（tenant/owner/account）不在此处——由后端从认证头注入。
    """

    source_module: str = Field(..., description="来源模块，如 screener / strategy / signal")
    source_mode: str = Field(..., description="来源模式，如 leader_auction / bi_trend_launch")
    name: str = Field(..., description="候选池名称")
    candidates: list[dict[str, Any]] = Field(
        default_factory=list, description="候选快照列表（每项含 candidate_id/code/score 等）"
    )
    candidate_pool_metadata: dict[str, Any] = Field(
        default_factory=dict, description="附加元数据（trade_date/time_slot/top_n 等）"
    )
    visibility: str = Field(default="private", description="可见性：private / tenant_shared / public")
    data_scope: str = Field(default="account", description="数据范围：account / tenant / public")
    trade_date: Optional[str] = Field(default=None, description="交易日 YYYY-MM-DD，用于 pool_id 生成")
    time_slot: Optional[str] = Field(default=None, description="时段 HH:MM，用于 pool_id 生成")


class _LegacyCandidatePoolRecordResponse(BaseModel):
    """POST /screener/candidate-pool 响应。"""

    pool_id: str = Field(..., description="后端生成的候选池 ID")
    id: Optional[int] = Field(default=None, description="数据库行 id（PG 不可用时为 None）")
    created_at: Optional[str] = Field(default=None, description="创建时间 ISO（PG 不可用时为 None）")
    fallback_reason: Optional[str] = Field(
        default=None, description="非空表示降级（如 PG 不可用、db 未注入），已忽略写入"
    )


class _LegacyCandidatePoolQueryResponse(BaseModel):
    """GET /screener/candidate-pool 响应。"""

    total: int = Field(..., description="满足 scope 过滤的总记录数")
    page: int = Field(..., description="当前页码")
    page_size: int = Field(..., description="每页大小")
    records: list[dict[str, Any]] = Field(default_factory=list, description="候选池记录列表")
    empty_state: Optional[dict[str, Any]] = Field(
        default=None, description="无数据时的空态提示（含 hint / suggestion）"
    )
    fallback_reason: Optional[str] = Field(
        default=None, description="非空表示降级（如 PG 不可用、db 未注入）"
    )


@router.post(
    "/candidate-pool",
    response_model=CandidatePoolRecordResponse,
    operation_id="record_candidate_pool",
    summary="记录候选池快照（scope 从认证头注入）",
)
async def record_candidate_pool(
    payload: CandidatePoolRecordRequest,
    tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    owner_user_id: str | None = Header(default=None, alias="X-Owner-User-Id"),
    account_id: str | None = Header(default=None, alias="X-Trade-Account-Id"),
    db: AsyncSession | None = Depends(get_db),
):
    """记录一次候选池快照。pool_id 后端生成，scope 从 Header 取，幂等 UPSERT。

    PG 不可用或 db 未注入时降级返回 `fallback_reason`，不抛 500。
    """
    return await candidate_service.record_candidate_pool(
        db=db, payload=payload, tenant_id=tenant_id,
        owner_user_id=owner_user_id, account_id=account_id,
    )


@router.get(
    "/candidate-pool",
    response_model=CandidatePoolQueryResponse,
    operation_id="query_candidate_pool",
    summary="查询候选池（scope 从认证头注入自动过滤）",
)
async def query_candidate_pool(
    source_module: Optional[str] = Query(default=None, description="按来源模块过滤"),
    source_mode: Optional[str] = Query(default=None, description="按来源模式过滤"),
    page: int = Query(default=1, ge=1, description="页码，从 1 起"),
    page_size: int = Query(default=50, ge=1, le=200, description="每页大小，上限 200"),
    tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    owner_user_id: str | None = Header(default=None, alias="X-Owner-User-Id"),
    account_id: str | None = Header(default=None, alias="X-Trade-Account-Id"),
    db: AsyncSession | None = Depends(get_db),
):
    """查询当前 scope 可见的候选池快照。

    store.query 内置 scope 过滤（private 仅 owner/同账户、tenant_shared 同租户、public 全局）。
    PG 不可用或 db 未注入时降级返回 `fallback_reason` + 空 records。
    """
    return await candidate_service.query_candidate_pool(
        db=db, tenant_id=tenant_id, owner_user_id=owner_user_id, account_id=account_id,
        source_module=source_module, source_mode=source_mode, page=page, page_size=page_size,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Watchlist REST API — 自选股（POST 加自选 / GET 查列表 / DELETE 移除）
#
# 解禁前端 Screener / OpenDecision 的"加入自选"按钮。完全仿 candidate-pool：
# scope（tenant_id / owner_user_id / account_id）全部从认证头注入，前端绝不传明文。
# ─────────────────────────────────────────────────────────────────────────────

@router.post(
    "/watchlist",
    response_model=WatchlistAddResponse,
    operation_id="add_watchlist",
    summary="加入自选股（scope 从认证头注入）",
)
async def add_watchlist(
    payload: WatchlistAddRequest,
    tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    owner_user_id: str | None = Header(default=None, alias="X-Owner-User-Id"),
    account_id: str | None = Header(default=None, alias="X-Trade-Account-Id"),
    db: AsyncSession | None = Depends(get_db),
):
    """加入自选股（UPSERT：同一 scope + code 重复加只更新 name/notes/sort_order）。

    PG 不可用或 db 未注入时降级返回 `fallback_reason`，不抛 500。
    """
    return await candidate_service.add_watchlist(db=db, payload=payload, tenant_id=tenant_id, owner_user_id=owner_user_id, account_id=account_id)


@router.get(
    "/watchlist",
    response_model=WatchlistQueryResponse,
    operation_id="list_watchlist",
    summary="查询自选股列表（scope 从认证头注入自动过滤）",
)
async def list_watchlist(
    code: Optional[str] = Query(default=None, description="按股票代码过滤"),
    page: int = Query(default=1, ge=1, description="页码，从 1 起"),
    page_size: int = Query(default=100, ge=1, le=500, description="每页大小，上限 500"),
    tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    owner_user_id: str | None = Header(default=None, alias="X-Owner-User-Id"),
    account_id: str | None = Header(default=None, alias="X-Trade-Account-Id"),
    db: AsyncSession | None = Depends(get_db),
):
    """查询当前 scope 可见的自选股列表，按 sort_order 升序 + added_at 降序。"""
    return await candidate_service.list_watchlist(db=db, code=code, page=page, page_size=page_size, tenant_id=tenant_id, owner_user_id=owner_user_id, account_id=account_id)


@router.delete(
    "/watchlist",
    response_model=WatchlistDeleteResponse,
    operation_id="remove_watchlist",
    summary="移除自选股（按 code 或 id，scope 校验归属）",
)
async def remove_watchlist(
    code: Optional[str] = Query(default=None, description="按股票代码移除"),
    id: Optional[int] = Query(default=None, description="按行 id 移除"),
    tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    owner_user_id: str | None = Header(default=None, alias="X-Owner-User-Id"),
    account_id: str | None = Header(default=None, alias="X-Trade-Account-Id"),
    db: AsyncSession | None = Depends(get_db),
):
    """移除自选股。code 与 id 二选一；store 层用 scope WHERE 校验归属，
    scope 不可见 → deleted=0（不泄露存在性）。"""
    if code is None and id is None:
        raise HTTPException(status_code=400, detail="必须提供 code 或 id 查询参数之一")
    if code is not None and id is not None:
        raise HTTPException(status_code=400, detail="code 与 id 不能同时提供")
    return await candidate_service.remove_watchlist(db=db, code=code, row_id=id, tenant_id=tenant_id, owner_user_id=owner_user_id, account_id=account_id)
