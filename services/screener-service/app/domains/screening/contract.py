"""Screener 响应契约与 picks 归一化/序列化（从 service.py 拆出，零行为变化）。"""

import logging
import math
from datetime import datetime
from typing import Any

import numpy as np

logger = logging.getLogger("screener.routes")


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


def _snapshot_rows(result: dict) -> list[dict]:
    """Return the observed factor universe for persistence.

    ``picks`` is the risk-controlled trading list and can be intentionally
    short in weak markets.  Backtest evidence must use the real scored
    cross-section when the engine supplies it, without changing the list
    shown to users or inventing rows.
    """
    observations = result.get("factor_observations")
    if isinstance(observations, list) and observations:
        return [row for row in observations if isinstance(row, dict) and row.get("code")]
    picks = result.get("picks")
    return [row for row in picks if isinstance(row, dict) and row.get("code")] if isinstance(picks, list) else []


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
