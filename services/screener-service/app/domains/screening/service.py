



# ── re-export：保持 app.domains.screening.service 的导入路径兼容 ──



# ── re-export：保持 app.domains.screening.service 的导入路径兼容 ──
from app.domains.screening.supply_chain_queries import (  # noqa: F401
    _apply_supply_chain_mapping_review,
    _map_stage_tracking_row,
    _mapping_evidence_gaps,
    _mapping_evidence_items,
    _mapping_review_priority,
    _mapping_source_from_evidence,
    _persist_policy_interpretation,
    _query_business_tag_evidence_chain,
    _query_business_tag_stage,
    _query_capex_evidence_review_queue,
    _query_evidence_review_queue,
    _query_recent_research_reports,
    _query_research_report_freshness,
    _query_supply_chain_candidate_ranking,
    _query_supply_chain_company_detail,
    _query_supply_chain_data_freshness,
    _query_supply_chain_mapping_quality,
    _query_supply_chain_mapping_review_queue,
    _query_supply_chain_node_companies,
    _query_supply_chain_node_evidence,
    _research_report_text,
    _review_business_tag_evidence,
    _review_capex_evidence,
)
from app.domains.screening.candidates import (  # noqa: F401
    VALID_FILTERS,
    VALID_RESONANCE_LEVELS,
    _build_evidence_summary,
    _build_selected_node_thesis,
    _candidate_matches_node,
    _candidate_search_terms,
    _commercialization_cycle,
    _derive_commercialization_stage,
    _derive_resonance,
    _derive_resonance_from_three_factors,
    _enrich_candidate_with_resonance_v6,
    _enrich_supply_chain_candidate,
    _filter_candidate_by_filter_type,
    _filter_candidate_by_resonance_level,
    _filter_candidates_for_node,
    _get_supply_chain_candidate_pool,
    _node_match_terms,
    _normalize_match_terms,
    _pick_products_materials,
    _query_business_tag_mapping_candidates,
    _query_latest_market_snapshots,
    _query_upstream_influence_candidates,
    _selection_reason,
    _supply_chain_model_payload,
)
from app.domains.screening.modes import (  # noqa: F401
    _auto_save_snapshot,
    _candidate_pool_record_safe,
    _executor,
    _load_supply_chain_expectation_gap_snapshot,
    _run_afternoon_mode,
    _run_bi_full_market_mode,
    _run_bi_shifu_trend_mode,
    _run_bi_trend_mode,
    _run_leader_mode,
    _run_multifactor_mode,
    _run_supply_chain_trend_launch_mode,
)


# ── re-export：保持 app.domains.screening.service 的导入路径兼容 ──
from app.domains.screening.schemas import (  # noqa: F401
    BusinessTagBatchScoreRequest,
    BusinessTagEvidenceBatchExtractRequest,
    BusinessTagEvidenceExtractRequest,
    BusinessTagEvidenceReviewRequest,
    BusinessTagExpectationGapScoreRequest,
    BusinessTagThreeHighScoreRequest,
    InterpretationResult,
    LLMUsageInfo,
    PolicyInterpretRequest,
    PolicyInterpretResponse,
    SupplyChainInferredMaterializeRequest,
    SupplyChainMappingReviewRequest,
    SupplyChainRefreshWorkflowRequest,
    _LegacyCandidatePoolQueryResponse,
    _LegacyCandidatePoolRecordRequest,
    _LegacyCandidatePoolRecordResponse,
)


from app.domains.screening.contract import (  # noqa: F401
    _normalize_picks,
    _sanitize_picks,
    _screener_data_freshness,
    _screener_model_metadata,
    _screener_source_for_mode,
    _snapshot_rows,
)


from app.domains.screening.data_access import (  # noqa: F401
    _json_or_default,
    _load_supply_chain_bom_payload,
    _pg_column_exists,
    _pg_connect,
    _pg_count,
    _pg_distinct_count,
    _pg_nonempty_text_count,
    _pg_table_exists,
    _row_get,
    _seed_chain_nodes_for_deconstruct,
    _status_from_rows,
    _to_float,
)


"""Screener API routes — 12 screening modes via unified endpoint with Redis caching."""


import asyncio


import hashlib


import json


import logging


import math


import os


import time


# /run 执行限时（秒, env 可调）: 超时返回明确 503 而非网关 30s 切断后的不透明 502
_RUN_TIMEOUT_SEC = float(os.environ.get("SCREENER_RUN_TIMEOUT_SEC", "25"))


from concurrent.futures import ThreadPoolExecutor


from datetime import datetime


from pathlib import Path


from typing import Any, List, Optional


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


from app.domains.supply_chain import evidence_review_service


logger = logging.getLogger("screener.routes")


PROJECT_ROOT = Path(__file__).resolve().parents[5]


INDUSTRY_CHAIN_TEMPLATE_PATH = PROJECT_ROOT / "packages" / "kronos-factors" / "configs" / "industry_chain_templates.json"


BIGTECH_COMPANIES = {"Microsoft", "Alphabet", "Meta", "Amazon", "Oracle"}


AI_COMPUTE_LAYER_KEYWORDS = {
    "demand": ("云", "cloud", "aws", "oci", "AI", "大模型", "算力", "应用"),
    "foundation": ("HBM", "CoWoS", "封装", "服务器", "网络设备", "数据中心土地"),
    "infrastructure": ("IDC", "数据中心", "服务器", "液冷", "光模块", "CPO", "网络", "交换机", "电源", "GPU", "云容量"),
}


router = APIRouter(prefix="/api/v1/screener", tags=["screener"])


_CB_AUCTION_T0_ENGINE = None


_CB_AUCTION_T0_V2_ENGINE = None


_CB_AUCTION_T0_V21_ENGINE = None


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
        "000688": "科创50",
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
            SELECT MAX(trade_date) AS trade_date
            FROM index_daily
            WHERE code IN ({codes_sql})
            {date_filter}
            """
        ).fetchone()
        # pg_adapter 返回 dict 行（键为列别名），SQLite/其他适配器可能是元组，两种都兼容
        latest_date = _row_get(date_row, "trade_date") or _row_get(date_row, 0)
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
            # pg_adapter 会把 change_pct 结果键改写成 pct_chg（_KEY_MAP），两种都取
            "f3": _row_get(row, "change_pct") if _row_get(row, "change_pct") is not None else _row_get(row, "pct_chg"),
            "f4": None,
            "f6": None,
        })
    return {
        "source": "index_daily_close",
        "as_of": str(latest_date)[:10],
        "data": {"diff": diff},
    }


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


def _query_supply_chain_data_readiness() -> dict[str, Any]:
    return supply_chain_service.data_readiness()


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
    return supply_chain_service.query_layers()


def _query_supply_chain_layer_detail(layer_node_id: str) -> dict[str, Any]:
    return supply_chain_service.query_layer_detail(layer_node_id)


def _business_tag_score_status(revenue_ratio: float | None, gross_profit_ratio: float | None, evidence_count: int) -> str:
    return supply_chain_service.business_tag_score_status(revenue_ratio, gross_profit_ratio, evidence_count)


def _query_company_business_tags(code: str) -> dict[str, Any]:
    return supply_chain_service.query_company_business_tags(code)


def _query_business_tag_mapping_context(cur, mapping_id: str) -> dict[str, Any] | None:
    return supply_chain_service._query_business_tag_mapping_context(cur, mapping_id)


def _empty_business_tag_evidence_payload(mapping_id: str) -> dict[str, Any]:
    return supply_chain_service._empty_business_tag_evidence_payload(mapping_id)


def _map_business_tag_event_row(row) -> dict[str, Any]:
    return supply_chain_service._map_business_tag_event_row(row)


def _query_business_tag_evidence(mapping_id: str) -> dict[str, Any]:
    return supply_chain_service.query_business_tag_evidence(mapping_id)


def _default_business_tag_stage(mapping_id: str, evidence_count: int = 0) -> dict[str, Any]:
    return supply_chain_service._default_business_tag_stage(mapping_id, evidence_count)


def _stage_from_evidence_events(events: list[dict[str, Any]]) -> dict[str, Any]:
    return supply_chain_service._stage_from_evidence_events(events)


def _stage_record_from_reviewed_event(event: dict[str, Any], *, review_status: str) -> dict[str, Any] | None:
    return supply_chain_service._stage_record_from_reviewed_event(event, review_status=review_status)


def _infer_business_tag_evidence_event(*, mapping_id: str, mapping: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
    return supply_chain_service._infer_business_tag_evidence_event(mapping_id=mapping_id, mapping=mapping, source=source)


def _mapping_text_terms(mapping: dict[str, Any]) -> set[str]:
    return supply_chain_service._mapping_text_terms(mapping)


def _source_record_matches_mapping(source: dict[str, Any], mapping: dict[str, Any]) -> bool:
    return supply_chain_service._source_record_matches_mapping(source, mapping)


def _query_business_tag_mappings_for_batch(cur, request: BusinessTagEvidenceBatchExtractRequest) -> list[dict[str, Any]]:
    return supply_chain_service._query_business_tag_mappings_for_batch(cur, request)


def _first_existing_column(cur, table_name: str, columns: list[str]) -> str | None:
    return supply_chain_service._first_existing_column(cur, table_name, columns)


def _code_variants(code: str) -> list[str]:
    return supply_chain_service._code_variants(code)


def _query_candidate_sources_from_table(cur, **kwargs) -> list[dict[str, Any]]:
    return supply_chain_service._query_candidate_sources_from_table(cur, **kwargs)


def _query_candidate_sources_for_mapping(cur, mapping: dict[str, Any], source_types: list[str], limit: int) -> list[dict[str, Any]]:
    return supply_chain_service._query_candidate_sources_for_mapping(cur, mapping, source_types, limit)


def _persist_business_tag_evidence_event(cur, event: dict[str, Any]) -> None:
    return supply_chain_service._persist_business_tag_evidence_event(cur, event)


def _extract_business_tag_evidence_event(mapping_id: str, request: BusinessTagEvidenceExtractRequest) -> dict[str, Any]:
    return supply_chain_service._extract_business_tag_evidence_event(mapping_id, request)


def _batch_extract_business_tag_evidence(request: BusinessTagEvidenceBatchExtractRequest) -> dict[str, Any]:
    return supply_chain_service._batch_extract_business_tag_evidence(request)


def _approved_business_tag_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return supply_chain_service._approved_business_tag_events(events)


def _calculate_business_tag_three_high_score(*args, **kwargs): return supply_chain_service._calculate_business_tag_three_high_score(*args, **kwargs)


def _l8_dimension_payloads(*args, **kwargs): return supply_chain_service._l8_dimension_payloads(*args, **kwargs)


def _matching_l8_dimensions(*args, **kwargs): return supply_chain_service._matching_l8_dimensions(*args, **kwargs)


def _l8_source_confidence(*args, **kwargs): return supply_chain_service._l8_source_confidence(*args, **kwargs)


def _build_l8_source_evidence_events(*args, **kwargs): return supply_chain_service._build_l8_source_evidence_events(*args, **kwargs)


def _build_l8_evidence_status_records(*args, **kwargs): return supply_chain_service._build_l8_evidence_status_records(*args, **kwargs)


def _inferred_item_name(*args, **kwargs): return supply_chain_service._inferred_item_name(*args, **kwargs)


def _inferred_l4_name(*args, **kwargs): return supply_chain_service._inferred_l4_name(*args, **kwargs)


def _inferred_l6_name(*args, **kwargs): return supply_chain_service._inferred_l6_name(*args, **kwargs)


def _inferred_l7_name(*args, **kwargs): return supply_chain_service._inferred_l7_name(*args, **kwargs)


def _build_inferred_l1_l8_path(*args, **kwargs): return supply_chain_service._build_inferred_l1_l8_path(*args, **kwargs)


def _stage_from_inferred_mapping_status(*args, **kwargs): return supply_chain_service._stage_from_inferred_mapping_status(*args, **kwargs)


def _inferred_node_bonus(*args, **kwargs): return supply_chain_service._inferred_node_bonus(*args, **kwargs)


def _inferred_moat_bonus(*args, **kwargs): return supply_chain_service._inferred_moat_bonus(*args, **kwargs)


def _build_inferred_business_tag_materialization(*args, **kwargs): return supply_chain_service._build_inferred_business_tag_materialization(*args, **kwargs)


def _query_business_tag_score_mapping_context(*args, **kwargs): return supply_chain_service._query_business_tag_score_mapping_context(*args, **kwargs)


def _query_business_tag_stage_for_score(*args, **kwargs): return supply_chain_service._query_business_tag_stage_for_score(*args, **kwargs)


def _query_business_tag_events_for_score(*args, **kwargs): return supply_chain_service._query_business_tag_events_for_score(*args, **kwargs)


def _persist_business_tag_three_high_score(*args, **kwargs): return supply_chain_service._persist_business_tag_three_high_score(*args, **kwargs)


def _business_tag_materialization_tables(*args, **kwargs): return supply_chain_service._business_tag_materialization_tables(*args, **kwargs)


def _query_inferred_bom_mapping_rows(*args, **kwargs): return supply_chain_service._query_inferred_bom_mapping_rows(*args, **kwargs)


def _query_l8_source_evidence_events_for_mapping(*args, **kwargs): return supply_chain_service._query_l8_source_evidence_events_for_mapping(*args, **kwargs)


def _clear_generated_l8_events_for_mapping(*args, **kwargs): return supply_chain_service._clear_generated_l8_events_for_mapping(*args, **kwargs)


def _persist_business_tag_mapping(*args, **kwargs): return supply_chain_service._persist_business_tag_mapping(*args, **kwargs)


def _persist_business_tag_l8_evidence_status(*args, **kwargs): return supply_chain_service._persist_business_tag_l8_evidence_status(*args, **kwargs)


def _persist_business_tag_stage(*args, **kwargs): return supply_chain_service._persist_business_tag_stage(*args, **kwargs)


def _persist_inferred_legacy_company_evidence(*args, **kwargs): return supply_chain_service._persist_inferred_legacy_company_evidence(*args, **kwargs)


def _persist_legacy_company_evidence_event(*args, **kwargs): return supply_chain_service._persist_legacy_company_evidence_event(*args, **kwargs)


def _link_inferred_evidence_to_company_bom_mapping(*args, **kwargs): return supply_chain_service._link_inferred_evidence_to_company_bom_mapping(*args, **kwargs)


def _persist_inferred_company_chain_projection(*args, **kwargs): return supply_chain_service._persist_inferred_company_chain_projection(*args, **kwargs)


def _materialize_supply_chain_inferred_data(*args, **kwargs): return supply_chain_service._materialize_supply_chain_inferred_data(*args, **kwargs)


def _calculate_business_tag_expectation_gap_score(*args, **kwargs): return supply_chain_service._calculate_business_tag_expectation_gap_score(*args, **kwargs)


def _persist_business_tag_expectation_gap_score(*args, **kwargs): return supply_chain_service._persist_business_tag_expectation_gap_score(*args, **kwargs)


def _score_business_tag_three_high(*args, **kwargs): return supply_chain_service._score_business_tag_three_high(*args, **kwargs)


def _query_business_tag_three_high_score(*args, **kwargs): return supply_chain_service._query_business_tag_three_high_score(*args, **kwargs)


def _score_business_tag_expectation_gap(*args, **kwargs): return supply_chain_service._score_business_tag_expectation_gap(*args, **kwargs)


def _query_business_tag_expectation_gap_score(*args, **kwargs): return supply_chain_service._query_business_tag_expectation_gap_score(*args, **kwargs)


def _normalize_batch_score_types(*args, **kwargs): return supply_chain_service._normalize_batch_score_types(*args, **kwargs)


def _query_business_tag_mappings_for_batch_score(*args, **kwargs): return supply_chain_service._query_business_tag_mappings_for_batch_score(*args, **kwargs)


def _batch_score_business_tags(request):
    return supply_chain_service._batch_score_business_tags(
        request,
        query_mappings=_query_business_tag_mappings_for_batch_score,
        score_three_high=_score_business_tag_three_high,
        score_expectation_gap=_score_business_tag_expectation_gap,
    )


def _normalize_refresh_rank_types(*args, **kwargs): return supply_chain_service._normalize_refresh_rank_types(*args, **kwargs)


def _refresh_supply_chain_tracking_workflow(request):
    return supply_chain_service._refresh_supply_chain_tracking_workflow(
        request,
        extract_evidence=_batch_extract_business_tag_evidence,
        batch_score=_batch_score_business_tags,
        query_rankings=_query_supply_chain_rankings,
    )


def _normalize_business_ratio(*args, **kwargs): return supply_chain_service._normalize_business_ratio(*args, **kwargs)


def _calculate_company_value_rankings(*args, **kwargs): return supply_chain_service._calculate_company_value_rankings(*args, **kwargs)


def _calculate_company_expectation_gap_rankings(*args, **kwargs): return supply_chain_service._calculate_company_expectation_gap_rankings(*args, **kwargs)


def _query_supply_chain_rankings(*args, **kwargs): return supply_chain_service._query_supply_chain_rankings(*args, **kwargs)


def _candidate_rank_clamp(*args, **kwargs): return supply_chain_service._candidate_rank_clamp(*args, **kwargs)


def _normalize_candidate_expectation_gap(*args, **kwargs): return supply_chain_service._normalize_candidate_expectation_gap(*args, **kwargs)


def _normalize_candidate_momentum(*args, **kwargs): return supply_chain_service._normalize_candidate_momentum(*args, **kwargs)


def _load_bigtech_capex_context(*args, **kwargs): return supply_chain_service._load_bigtech_capex_context(*args, **kwargs)


def _score_bigtech_capex_tailwind(*args, **kwargs): return supply_chain_service._score_bigtech_capex_tailwind(*args, **kwargs)


def _score_company_capex_evidence(*args, **kwargs): return supply_chain_service._score_company_capex_evidence(*args, **kwargs)


def _score_supply_chain_candidate_row(*args, **kwargs): return supply_chain_service._score_supply_chain_candidate_row(*args, **kwargs)


def _aggregate_supply_chain_candidate_rows(*args, **kwargs): return supply_chain_service._aggregate_supply_chain_candidate_rows(*args, **kwargs)


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
            {"id": "bi_shifu_trend_v23","name": "毕师傅趋势战法候选 V2.3", "cycle": "5-20天", "style": "候选趋势"},
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
    """Return pending facts, events, and expectation monitors."""
    return evidence_review_service.list_queue(limit=limit)


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


@router.get("/supply-chain/token-output-power")
async def supply_chain_token_output_power(
    top_n: int = Query(50, ge=1, le=200),
    pool_code: Optional[str] = Query(None, pattern="^[ABCD]$"),
    include_provisional: bool = Query(False),
    trade_date: Optional[str] = Query(None),
):
    """Return the evidence-first Token output power chain snapshot."""
    return supply_chain_service.token_output_power_payload(top_n, pool_code, include_provisional, trade_date)


@router.get("/supply-chain/token-output-power/{mapping_id}")
async def supply_chain_token_output_power_mapping(mapping_id: str):
    """Return one Token output mapping and its complete evidence trace."""
    return supply_chain_service.token_output_power_mapping_detail(mapping_id)


@router.get("/supply-chain/token-output")
async def supply_chain_token_output(
    top_n: int = Query(50, ge=1, le=200),
    pool_code: Optional[str] = Query(None, pattern="^[ABCD]$"),
    include_provisional: bool = Query(False),
    as_of_date: Optional[str] = Query(None),
):
    """Return the commercial AI Token output chain snapshot."""
    return supply_chain_service.token_output_payload(top_n, pool_code, include_provisional, as_of_date)


@router.get("/supply-chain/token-output/{mapping_id}")
async def supply_chain_token_output_mapping(mapping_id: str):
    """Return one commercial Token mapping and its evidence gaps."""
    return supply_chain_service.token_output_mapping_detail(mapping_id)


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
        # 选出执行器后用 wait_for 统一限时: 冷缓存/缺当日数据时 mode 可能跑超
        # 网关 30s 代理超时 → 返回明确 503 而非不透明 502 (env 可调)
        if mode in ("leader_scalp", "leader_intraday", "leader_auction", "leader_closing"):
            runner_coro = loop.run_in_executor(
                _executor, _run_leader_mode, mode, top_n, trade_date
            )
        elif mode in ("leader_afternoon", "leader_afternoon_trend_full"):
            runner_coro = loop.run_in_executor(
                _executor, _run_afternoon_mode, mode, top_n, trade_date
            )
        elif mode in ("cb_floor", "cb_intraday", "cb_auction", "cb_auction_t0", "cb_auction_t0_v2", "cb_auction_t0_v2_1"):
            runner_coro = loop.run_in_executor(
                _executor, _run_cb_mode, mode, top_n, trade_date
            )
        elif mode == "bi_trend_launch":
            runner_coro = loop.run_in_executor(
                _executor, _run_bi_trend_mode, mode, top_n, trade_date
            )
        elif mode == "bi_trend_full_market":
            runner_coro = loop.run_in_executor(
                _executor, _run_bi_full_market_mode, mode, top_n, trade_date
            )
        elif mode in ("bi_shifu_trend", "bi_shifu_trend_v23"):
            runner_coro = loop.run_in_executor(
                _executor, _run_bi_shifu_trend_mode, mode, top_n, trade_date
            )
        elif mode == "supply_chain":
            runner_coro = loop.run_in_executor(
                _executor, _run_supply_chain_mode, mode, top_n, trade_date
            )
        elif mode == "supply_chain_trend_launch":
            runner_coro = loop.run_in_executor(
                _executor, _run_supply_chain_trend_launch_mode, mode, top_n, trade_date
            )
        else:
            runner_coro = loop.run_in_executor(
                _executor, _run_multifactor_mode, mode, top_n, trade_date
            )
        result = await asyncio.wait_for(runner_coro, timeout=_RUN_TIMEOUT_SEC)
    except asyncio.TimeoutError:
        logger.error("Screening mode=%s 超时 (%ss)", mode, _RUN_TIMEOUT_SEC)
        if pipeline_run is not None:
            await finish_persisted_pipeline(db, pipeline_run.run_id, error={"message": "timeout"})
        raise HTTPException(
            status_code=503,
            detail=f"选股超时（{_RUN_TIMEOUT_SEC}s）：行情数据可能未就绪，请稍后重试",
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


# ─────────────────────────────────────────────────────────────────────────────
# Industry Chain Deconstruct Endpoints (Phase 2)
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/chain/deconstruct")
async def chain_deconstruct(
    theme_id: str = Query(..., description="Industry theme ID (e.g., 'semiconductor')"),
    method: str = Query("upstream_downstream", description="Deconstruct method: bom, upstream_downstream, value_chain, competition"),
    template: Optional[str] = Query(None, description="Optional industry-link template (8-layer 传导链/transmission, e.g. complex_tech); 与 BOM 钻取链 (drilldown) L1-L8 不同维度"),
    overlays: Optional[List[str]] = Query(None, description="Optional overlay annotators applied on any method (subset of value_chain/competition); 单树 + 叠加注解, 标签按 node_id 合并进树节点"),
):
    """Return industry chain deconstruct tree with selected view method.

    Methods:
    - bom: 钻取链 (drilldown) L1-L8 BOM tree and root-to-leaf paths (研究钻取深度)
    - upstream_downstream: 5-layer tree (原材料→零部件→制造→渠道→终端)
    - value_chain: tree + margin/pricing_power/value_added per node
    - competition: tree + concentration/leader_share/barrier/threat per node
    - overlays=value_chain&overlays=competition: 任意 method 上叠加 overlay 注解
      (主推 method=upstream_downstream + overlays 单树多维分析); 返回追加顶层
      "overlays" 键, 树节点按 node_id 合并 value_chain/competition 标签
    - template=complex_tech: 8-layer 传导链 (transmission) 产业传导位置模板
      (demand→task→core_product→foundation→integration→supporting→infrastructure→commercialization),
      与钻取链 (drilldown) L1-L8 是不同维度
    """
    from kronos_factors.engine.chain_deconstruct import deconstruct_chain

    # Query chain_nodes from PG for the given theme_id
    fallback_reason = None
    try:
        with _pg_connect() as pg:
            cur = pg.cursor()
            # transmission_layer 由 migration 040 引入; 未迁移的库探测不到该列时
            # 回退旧 SELECT, 由 chain_deconstruct 按旧 layer 推导 (向后兼容)
            cur.execute(
                """
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'chain_nodes' AND column_name = 'transmission_layer'
                """
            )
            transmission_col = ", transmission_layer" if cur.fetchone() else ""
            cur.execute(
                f"""
                SELECT node_id, theme_id, node_name, layer, parent_node_id,
                       upstream_nodes, downstream_nodes, value_chain, competition
                       {transmission_col}
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
                        # 传导链 (transmission) 位置 (migration 040), 缺列/NULL 时
                        # 由 chain_deconstruct 按旧 layer 推导
                        "transmission_layer": str(row[9]) if len(row) > 9 and row[9] else None,
                    }
                    nodes.append(node)

    except HTTPException:
        raise
    except Exception as e:
        logger.warning("chain_deconstruct query failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Database query failed: {e}")

    # Call deconstruct_chain with the nodes
    try:
        result = deconstruct_chain(theme_id, method, nodes, theme_name, template=template, overlays=overlays)
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
    fallback_reason = None
    try:
        candidates = await loop.run_in_executor(
            _executor,
            _get_supply_chain_candidate_pool,
            100,  # Fetch more for filtering
            trade_date,
        )
    except RuntimeError as exc:
        if str(exc) != "latest trade date unavailable":
            raise
        candidates = []
        fallback_reason = str(exc)
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
        "data_status": "ready" if candidates else "empty",
        "fallback_reason": fallback_reason,
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
