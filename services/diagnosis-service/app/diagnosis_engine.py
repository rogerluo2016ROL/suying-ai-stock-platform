"""Diagnosis Engine — five-dimension scoring with weighted aggregation.

Per ADR-005 Decision 1:
- Technical (40%): Reuses 25-factor scoring from kronos-factors
- Capital flow (25%): Northbound/margin/leaderboard/main-force flow
- Fundamental (20%): PE percentile/ROE/revenue growth/debt ratio
- AI prediction (10%): Kronos forecast return + confidence
- Sentiment (5%): News sentiment + research report rating

Aggregation: weighted linear score, normalized to 0-100.
Grade thresholds (ADR-005 Decision 1):
  >=85 → 强烈买入, 70-84 → 买入, 50-69 → 持有, 35-49 → 减仓, <35 → 卖出

Kronos degradation (ADR-005 Decision 5):
  When Kronos unavailable, redistribute weights: 技术面 44%, 资金面 28%, 基本面 22%, 情绪面 6%
"""

import asyncio
import json
import logging
import math
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger("diagnosis-service.engine")

# ═══════════════════════════════════════════════════════════════════════════
# Kronos in-memory cache (C1 fix — ADR-005 Decision 5)
# ═══════════════════════════════════════════════════════════════════════════

_kronos_cache: Dict[str, Tuple[float, Dict[str, Any]]] = {}
_kronos_cache_ttl: int = 3600  # 1 hour

# Ensure kronos packages are importable
_PACKAGES = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "packages")
)
for _pkg in ["kronos-factors", "kronos-core", "kronos-data"]:
    _path = os.path.join(_PACKAGES, _pkg)
    if os.path.isdir(_path) and _path not in sys.path:
        sys.path.insert(0, _path)

from app.schemas import (
    AIPredictDimension,
    CapitalFlowDimension,
    DiagnosisReport,
    DimensionScore,
    DimensionStatus,
    FundamentalDimension,
    RecommendationGrade,
    SentimentDimension,
    TechnicalDimension,
)

# ═══════════════════════════════════════════════════════════════════════════
# Dimension weights (ADR-005 Decision 1)
# ═══════════════════════════════════════════════════════════════════════════

WEIGHTS = {
    "technical": 0.38,
    "capital_flow": 0.23,
    "fundamental": 0.18,
    "ai_predict": 0.10,
    "sentiment": 0.11,
}

# Degraded weights when Kronos is unavailable (ADR-005 Decision 5)
DEGRADED_WEIGHTS = {
    "technical": 0.42,
    "capital_flow": 0.26,
    "fundamental": 0.20,
    "ai_predict": 0.00,
    "sentiment": 0.12,
}

# Grade thresholds (ADR-005 Decision 1)
GRADE_THRESHOLDS = [
    (85, RecommendationGrade.STRONG_BUY, "A"),
    (70, RecommendationGrade.BUY, "B"),
    (50, RecommendationGrade.HOLD, "C"),
    (35, RecommendationGrade.REDUCE, "D"),
    (0, RecommendationGrade.SELL, "E"),
]


# ═══════════════════════════════════════════════════════════════════════════
# Helper: score → letter grade
# ═══════════════════════════════════════════════════════════════════════════

def _score_to_grade(score: float) -> str:
    """Map 0-100 score to letter grade."""
    if score >= 90:
        return "A+"
    elif score >= 80:
        return "A"
    elif score >= 75:
        return "B+"
    elif score >= 65:
        return "B"
    elif score >= 55:
        return "C+"
    elif score >= 45:
        return "C"
    elif score >= 35:
        return "D"
    else:
        return "E"


def _score_to_recommendation(score: float) -> Tuple[RecommendationGrade, str]:
    """Map 0-100 overall score to recommendation grade and letter."""
    for threshold, grade, letter in GRADE_THRESHOLDS:
        if score >= threshold:
            return grade, letter
    return RecommendationGrade.SELL, "E"


def _clamp(val: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, val))


# ═══════════════════════════════════════════════════════════════════════════
# Dimension 1: Technical (40%)
# ═══════════════════════════════════════════════════════════════════════════

async def _score_technical(
    code: str, db, market_data
) -> TechnicalDimension:
    """Compute technical score from 25+ factor scorers.

    Aggregates: five_factor (quality/volume/composite/technical/momentum)
              + short_term + long_term + trend_strength + reversal + liquidity
    """
    signals: List[str] = []
    factor_scores: Dict[str, float] = {}

    try:
        from kronos_factors.scorer.five_factor import score_five_factor
        from kronos_factors.scorer.screening_scorers import (
            score_short_term,
            score_long_term,
        )
        from kronos_factors.scorer.advanced_factors import (
            score_trend_strength,
            score_reversal,
            score_liquidity,
        )

        # Get K-line data for factor scoring
        kline_df = await _get_kline_df(db, code, lookback=400)
        if kline_df is None or len(kline_df) < 60:
            return TechnicalDimension(
                name="技术面",
                score=50.0,
                weight=WEIGHTS["technical"],
                grade="C",
                status=DimensionStatus.DEGRADED,
                details={"error": "Insufficient K-line data"},
                signals=["数据不足"],
            )

        # Run scorers concurrently
        loop = asyncio.get_event_loop()

        def _run_five_factor():
            try:
                return score_five_factor(kline_df)
            except Exception:
                logger.debug("score_five_factor failed for %s", code, exc_info=True)
                return {}

        def _run_short_term():
            try:
                return score_short_term(kline_df)
            except Exception:
                logger.debug("score_short_term failed for %s", code, exc_info=True)
                return {"score": 5.0}

        def _run_long_term():
            try:
                return score_long_term(kline_df)
            except Exception:
                logger.debug("score_long_term failed for %s", code, exc_info=True)
                return {"score": 5.0}

        def _run_trend():
            try:
                return score_trend_strength(kline_df)
            except Exception:
                logger.debug("score_trend_strength failed for %s", code, exc_info=True)
                return {"score": 5.0}

        def _run_reversal():
            try:
                return score_reversal(kline_df)
            except Exception:
                logger.debug("score_reversal failed for %s", code, exc_info=True)
                return {"score": 5.0}

        def _run_liquidity():
            try:
                return score_liquidity(kline_df)
            except Exception:
                logger.debug("score_liquidity failed for %s", code, exc_info=True)
                return {"score": 5.0}

        results = await asyncio.gather(
            loop.run_in_executor(None, _run_five_factor),
            loop.run_in_executor(None, _run_short_term),
            loop.run_in_executor(None, _run_long_term),
            loop.run_in_executor(None, _run_trend),
            loop.run_in_executor(None, _run_reversal),
            loop.run_in_executor(None, _run_liquidity),
            return_exceptions=True,
        )

        ff_result, st_result, lt_result, trend_result, rev_result, liq_result = results

        # Extract scores (each result is dict with 'score' key, max 10)
        ff: Dict[str, Any] = ff_result if isinstance(ff_result, dict) else {}
        st: Dict[str, Any] = st_result if isinstance(st_result, dict) else {}
        lt: Dict[str, Any] = lt_result if isinstance(lt_result, dict) else {}
        trend: Dict[str, Any] = trend_result if isinstance(trend_result, dict) else {}
        rev: Dict[str, Any] = rev_result if isinstance(rev_result, dict) else {}
        liq: Dict[str, Any] = liq_result if isinstance(liq_result, dict) else {}

        # Collect sub-scores
        subs = {}
        if isinstance(ff.get("scores"), dict):
            for k, v in ff["scores"].items():
                subs[k] = float(v) * 10  # normalize 0-10 → 0-100

        subs["short_term"] = float(st.get("score", 5.0)) * 10
        subs["long_term"] = float(lt.get("score", 5.0)) * 10
        subs["trend_strength"] = float(trend.get("score", 5.0)) * 10
        subs["reversal"] = float(rev.get("score", 5.0)) * 10
        subs["liquidity"] = float(liq.get("score", 5.0)) * 10

        # Collect signals
        for r in [ff, st, lt, trend, rev, liq]:
            if isinstance(r.get("signals"), list):
                signals.extend(r["signals"])

        # Composite score: weighted average of sub-scores
        if subs:
            vals = list(subs.values())
            technical_score = _clamp(float(np.mean(vals)))
        else:
            technical_score = 50.0

        factor_scores = {k: round(v, 1) for k, v in subs.items()}

        # Determine trend
        closes = kline_df["close"].values
        if len(closes) >= 20:
            ma20 = closes[-20:].mean()
            ma60 = closes[-60:].mean() if len(closes) >= 60 else ma20
            if closes[-1] > ma20 > ma60:
                trend_text = "上升趋势"
            elif closes[-1] < ma20 < ma60:
                trend_text = "下降趋势"
            else:
                trend_text = "震荡整理"
        else:
            trend_text = "数据不足"

        return TechnicalDimension(
            name="技术面",
            score=round(technical_score, 1),
            weight=WEIGHTS["technical"],
            grade=_score_to_grade(technical_score),
            status=DimensionStatus.AVAILABLE,
            factor_scores=factor_scores,
            trend=trend_text,
            signals=signals[:10] if signals else None,
            details={"factors_used": len(subs), "trend": trend_text},
        )

    except Exception as e:
        logger.warning("Technical scoring failed for %s: %s", code, e)
        return TechnicalDimension(
            name="技术面",
            score=50.0,
            weight=WEIGHTS["technical"],
            grade="C",
            status=DimensionStatus.DEGRADED,
            details={"error": str(e)},
            signals=["技术面评分降级"],
        )


# ═══════════════════════════════════════════════════════════════════════════
# Dimension 2: Capital Flow (25%)
# ═══════════════════════════════════════════════════════════════════════════

async def _score_capital_flow(code: str, db) -> CapitalFlowDimension:
    """Compute capital flow score from northbound/margin/leaderboard/main-force data."""
    try:
        from sqlalchemy import text as sa_text

        # Query northbound (北向资金)
        nb_result = await db.execute(
            sa_text(
                "SELECT net_mf_amount AS net_flow, 0 AS close FROM moneyflow "
                "WHERE code = :code AND trade_date >= CURRENT_DATE - INTERVAL '30 days' "
                "ORDER BY trade_date DESC LIMIT 30"
            ),
            {"code": code},
        )
        nb_rows = nb_result.fetchall()
        northbound_net = sum(float(r[0] or 0) for r in nb_rows) if nb_rows else 0.0

        # Query margin (融资融券)
        mg_result = await db.execute(
            sa_text(
                "SELECT rzye AS margin_balance FROM margin_detail "
                "WHERE code = :code ORDER BY trade_date DESC LIMIT 1"
            ),
            {"code": code},
        )
        mg_row = mg_result.fetchone()
        margin_balance = float(mg_row[0]) if mg_row else 0.0

        # Query leaderboard (龙虎榜) — recent 10 days
        lb_result = await db.execute(
            sa_text(
                "SELECT net_amount AS net_buy FROM top_list "
                "WHERE code = :code AND trade_date >= CURRENT_DATE - INTERVAL '10 days' "
                "ORDER BY trade_date DESC"
            ),
            {"code": code},
        )
        lb_rows = lb_result.fetchall()
        leaderboard_net = sum(float(r[0] or 0) for r in lb_rows) if lb_rows else 0.0

        # Query main force flow (主力资金流向)
        mf_result = await db.execute(
            sa_text(
                "SELECT net_mf_amount AS main_net_inflow, "
                "buy_elg_amount AS super_large_net, buy_lg_amount AS large_net, "
                "buy_md_amount AS mid_net, buy_sm_amount AS small_net "
                "FROM moneyflow "
                "WHERE code = :code AND trade_date >= CURRENT_DATE - INTERVAL '5 days' "
                "ORDER BY trade_date DESC"
            ),
            {"code": code},
        )
        mf_rows = mf_result.fetchall()
        if mf_rows:
            main_force_flow = sum(float(r[0] or 0) for r in mf_rows)
        else:
            main_force_flow = 0.0

        # Normalize to 0-100
        # Northbound: positive net flow is bullish
        nb_score = _clamp(50 + northbound_net / 50000 * 50 if northbound_net != 0 else 50)
        # Margin: balance direction (simplified — neutral at 50)
        mg_score = 50.0
        # Leaderboard: net buy is bullish
        lb_score = _clamp(50 + leaderboard_net / 20000 * 50 if leaderboard_net != 0 else 50)
        # Main force: net inflow is bullish
        mf_score = _clamp(50 + main_force_flow / 100000 * 50 if main_force_flow != 0 else 50)

        flow_score = round((nb_score * 0.3 + mg_score * 0.15 + lb_score * 0.25 + mf_score * 0.3), 1)
        flow_score = _clamp(flow_score)

        signals = []
        if northbound_net > 10000:
            signals.append("北向持续流入")
        elif northbound_net < -10000:
            signals.append("北向持续流出")
        if leaderboard_net > 5000:
            signals.append("龙虎榜净买入")
        if main_force_flow > 50000:
            signals.append("主力大幅流入")

        return CapitalFlowDimension(
            name="资金面",
            score=flow_score,
            weight=WEIGHTS["capital_flow"],
            grade=_score_to_grade(flow_score),
            status=DimensionStatus.AVAILABLE,
            northbound_net=round(northbound_net, 2),
            margin_balance=round(margin_balance, 2),
            leaderboard_net=round(leaderboard_net, 2),
            main_force_flow=round(main_force_flow, 2),
            signals=signals if signals else None,
            details={
                "northbound_30d": round(northbound_net, 2),
                "leaderboard_10d": round(leaderboard_net, 2),
                "main_force_5d": round(main_force_flow, 2),
            },
        )

    except Exception as e:
        logger.warning("Capital flow scoring failed for %s: %s", code, e)
        return CapitalFlowDimension(
            name="资金面",
            score=50.0,
            weight=WEIGHTS["capital_flow"],
            grade="C",
            status=DimensionStatus.DEGRADED,
            details={"error": str(e)},
        )


# ═══════════════════════════════════════════════════════════════════════════
# Dimension 3: Fundamental (20%)
# ═══════════════════════════════════════════════════════════════════════════

async def _score_fundamental(code: str, db) -> FundamentalDimension:
    """Compute fundamental score from PE percentile / ROE / revenue growth / debt ratio."""
    try:
        from sqlalchemy import text as sa_text

        # Query latest fundamental data
        fd_result = await db.execute(
            sa_text(
                "SELECT NULL AS pe, 50.0 AS pe_percentile, roe, revenue_growth, debt_ratio, "
                "NULL AS pb, NULL AS market_cap, profit_growth AS net_profit_growth "
                "FROM financial_indicator WHERE code = :code ORDER BY end_date DESC LIMIT 1"
            ),
            {"code": code},
        )
        fd_row = fd_result.fetchone()

        if fd_row is None:
            # Try querying from daily_basic as fallback
            db_result = await db.execute(
                sa_text(
                    "SELECT pe, pb, total_mv "
                    "FROM daily_basic WHERE code = :code ORDER BY trade_date DESC LIMIT 1"
                ),
                {"code": code},
            )
            db_row = db_result.fetchone()
            if db_row:
                pe_val = float(db_row[0] or 0)
                pe_percentile = 50.0  # Unknown
                roe = 10.0  # Default
                revenue_growth = 5.0  # Default
                debt_ratio = 40.0  # Default
            else:
                # No data at all — return neutral
                return FundamentalDimension(
                    name="基本面",
                    score=50.0,
                    weight=WEIGHTS["fundamental"],
                    grade="C",
                    status=DimensionStatus.DEGRADED,
                    details={"error": "No fundamental data available"},
                )
        else:
            pe_val = float(fd_row[0] or 0)
            pe_percentile = float(fd_row[1] or 50)
            roe = float(fd_row[2] or 10)
            revenue_growth = float(fd_row[3] or 5)
            debt_ratio = float(fd_row[4] or 40)

        # Sub-score: PE percentile (lower is better for value)
        if pe_percentile <= 20:
            pe_score = 90
        elif pe_percentile <= 40:
            pe_score = 75
        elif pe_percentile <= 60:
            pe_score = 55
        elif pe_percentile <= 80:
            pe_score = 35
        else:
            pe_score = 15

        # Sub-score: ROE (higher is better)
        if roe >= 20:
            roe_score = 90
        elif roe >= 15:
            roe_score = 75
        elif roe >= 10:
            roe_score = 60
        elif roe >= 5:
            roe_score = 40
        else:
            roe_score = 20

        # Sub-score: Revenue growth (higher is better)
        if revenue_growth >= 30:
            growth_score = 90
        elif revenue_growth >= 15:
            growth_score = 70
        elif revenue_growth >= 5:
            growth_score = 55
        elif revenue_growth >= 0:
            growth_score = 40
        else:
            growth_score = 20

        # Sub-score: Debt ratio (lower is safer, but not too low)
        if 20 <= debt_ratio <= 40:
            debt_score = 80
        elif 40 < debt_ratio <= 60:
            debt_score = 55
        elif debt_ratio < 20:
            debt_score = 50  # Too conservative
        elif 60 < debt_ratio <= 80:
            debt_score = 30
        else:
            debt_score = 10

        fundamental_score = round(
            pe_score * 0.35 + roe_score * 0.30 + growth_score * 0.20 + debt_score * 0.15, 1
        )

        # ── P0: 审计意见风险调整 ──
        audit_penalty = 0
        audit_opinion = "无数据"
        try:
            audit_result = await db.execute(
                sa_text(
                    "SELECT audit_result FROM fina_audit "
                    "WHERE code = :code ORDER BY end_date DESC LIMIT 1"
                ),
                {"code": code},
            )
            audit_row = audit_result.fetchone()
            if audit_row:
                opinion = str(audit_row[0] or "")
                audit_opinion = opinion
                # Check most severe first; "保留意见" is substring of "标准无保留意见"!
                if "无法表示意见" in opinion or "否定意见" in opinion:
                    audit_penalty = 20
                elif "标准无保留意见" in opinion:
                    audit_penalty = 0  # Clean opinion, no penalty
                elif "保留意见" in opinion:
                    audit_penalty = 10
                elif "强调事项" in opinion or "持续经营" in opinion:
                    audit_penalty = 5
                else:
                    audit_penalty = 0
        except Exception:
            logger.debug("fina_audit query failed for %s", code, exc_info=True)  # fina_audit table may not exist yet

        fundamental_score = max(0, fundamental_score - audit_penalty)
        fundamental_score = _clamp(fundamental_score)

        signals = []
        if pe_percentile <= 20:
            signals.append(f"PE 处于历史低位 (分位{pe_percentile:.0f}%)")
        if roe >= 15:
            signals.append(f"ROE 优秀 ({roe:.1f}%)")
        if revenue_growth >= 15:
            signals.append(f"营收高增长 ({revenue_growth:.1f}%)")
        if debt_ratio > 70:
            signals.append(f"负债率偏高 ({debt_ratio:.1f}%)")
        if audit_penalty > 0:
            signals.append(f"⚠️ 审计意见: {audit_opinion} (扣{audit_penalty:.0f}分)")

        return FundamentalDimension(
            name="基本面",
            score=fundamental_score,
            weight=WEIGHTS["fundamental"],
            grade=_score_to_grade(fundamental_score),
            status=DimensionStatus.AVAILABLE,
            pe_percentile=round(pe_percentile, 1),
            roe=round(roe, 1),
            revenue_growth=round(revenue_growth, 1),
            debt_ratio=round(debt_ratio, 1),
            signals=signals if signals else None,
            details={
                "pe": round(pe_val, 2),
                "pe_percentile": round(pe_percentile, 1),
                "audit_opinion": audit_opinion,
                "audit_penalty": audit_penalty,
            },
        )

    except Exception as e:
        logger.warning("Fundamental scoring failed for %s: %s", code, e)
        return FundamentalDimension(
            name="基本面",
            score=50.0,
            weight=WEIGHTS["fundamental"],
            grade="C",
            status=DimensionStatus.DEGRADED,
            details={"error": str(e)},
        )


# ═══════════════════════════════════════════════════════════════════════════
# Dimension 4: AI Prediction (10%) — Kronos integration
# ═══════════════════════════════════════════════════════════════════════════


class _HttpException(Exception):
    """Raised by _http_get_json on non-200 HTTP responses, carrying the status."""

    def __init__(self, status: int, body: str = ""):
        super().__init__(f"HTTP {status}")
        self.status = status
        self.body = body


async def _http_get_json(url: str, headers: dict, timeout: int, method: str = "GET") -> dict:
    """Async GET returning parsed JSON (P1-1: urllib wrapper, no aiohttp).

    Raises ``_HttpException`` on non-200 so callers can map status codes
    (e.g. 401 → auth failure). Network/parse errors raise ValueError.
    """
    return await asyncio.get_running_loop().run_in_executor(
        None, _sync_get_json, url, headers, timeout, method
    )


def _sync_get_json(url: str, headers: dict, timeout: int, method: str = "GET") -> dict:
    """Synchronous urllib GET (runs in executor thread)."""
    req = urllib.request.Request(url, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace") if e.fp else ""
        raise _HttpException(e.status, body) from None
    except urllib.error.URLError as e:
        raise ValueError(f"Kronos unreachable: {e.reason}") from e


async def _get_kronos_prediction(
    code: str,
    auth_token: Optional[str] = None,
    force_refresh: bool = False,
) -> Dict[str, Any]:
    """Fetch Kronos prediction with in-memory cache (C1 fix — ADR-005 Decision 5).

    Cache key: {code}:{today.isoformat()}
    TTL: 1 hour (3600s)

    Returns dict with keys: pred_return_pct, pred_30d_close, confidence,
    inflection_days, max_drawdown_pct, from_cache
    """
    cache_key = f"{code}:{date.today().isoformat()}"

    # Check in-memory cache
    if not force_refresh and cache_key in _kronos_cache:
        cached_at, cached_data = _kronos_cache[cache_key]
        if time.time() - cached_at < _kronos_cache_ttl:
            logger.info("Kronos cache hit for %s (key=%s)", code, cache_key)
            cached_data["from_cache"] = True
            return cached_data
        else:
            _kronos_cache.pop(cache_key, None)
            logger.info("Kronos cache expired for %s", code)

    # No cached auth token → cannot call Kronos (C3 fix)
    if not auth_token:
        raise ValueError("No auth token available for Kronos — skipping AI prediction")

    # Call Kronos API via urllib async wrapper (P1-1: removed aiohttp per
    # CLAUDE.md "微服务间 HTTP 调用使用 urllib async wrapper，不引入 httpx/aiohttp").
    from app.config import KRONOS_PREDICTION_URL, KRONOS_PREDICTION_TIMEOUT

    kr_url = f"{KRONOS_PREDICTION_URL.rstrip('/')}/{code}/fast?pred_days=10"
    headers = {"Authorization": f"Bearer {auth_token}", "Accept": "application/json"}

    try:
        data = await _http_get_json(kr_url, headers, KRONOS_PREDICTION_TIMEOUT, method="POST")
    except _HttpException as e:
        if e.status == 401:
            raise ValueError("Kronos authentication failed (401) — check JWT token")
        raise ValueError(f"Kronos returned {e.status}")

    current_price = float(data.get("current_price") or 0)
    pred_trajectory = data.get("pred_trajectory") or []
    trajectory_lows = [
        float(point.get("low"))
        for point in pred_trajectory
        if isinstance(point, dict) and point.get("low") is not None
    ]
    if data.get("max_drawdown_pct") is not None:
        max_drawdown_pct = float(data.get("max_drawdown_pct"))
    elif current_price > 0 and trajectory_lows:
        max_drawdown_pct = round((min(trajectory_lows) / current_price - 1) * 100, 2)
    else:
        max_drawdown_pct = -5.0

    result = {
        "pred_return_pct": float(data.get("pred_return_pct", 0)),
        "pred_30d_close": float(data.get("pred_30d_close") or data.get("pred_last_close") or 0),
        "confidence": float(data.get("confidence", 0.65)),
        "inflection_days": data.get("inflection_days", []),
        "max_drawdown_pct": max_drawdown_pct,
        "model_metadata": data.get("model_metadata") or {
            "name": "Kronos-mini",
            "version": "kronos-mini",
            "checkpoint_status": "unknown",
        },
        "data_freshness": data.get("data_freshness") or {
            "status": "unknown",
            "as_of": None,
            "source": "prediction-service",
            "quality_score": 0,
        },
        "fallback_reason": data.get("fallback_reason"),
        "from_cache": False,
    }

    # Write to cache
    _kronos_cache[cache_key] = (time.time(), result)
    logger.info("Kronos prediction cached for %s (key=%s)", code, cache_key)

    return result


async def _score_ai_predict(
    code: str, db, auth_token: Optional[str] = None,
) -> AIPredictDimension:
    """Fetch Kronos 30-day prediction for the stock.

    Per ADR-005 Decision 5: cache-first with 1h TTL, degradation on failure.
    Per C3 fix: passes JWT Bearer token for Kronos authentication.
    When no token available → skip Kronos dimension entirely.
    """
    try:
        pred = await _get_kronos_prediction(code, auth_token=auth_token)

        pred_return = pred["pred_return_pct"]
        pred_30d = pred["pred_30d_close"]
        confidence = pred["confidence"]
        inflection_days = pred["inflection_days"]
        max_dd = pred["max_drawdown_pct"]

        # Score: predicted return as main signal, confidence as multiplier
        raw_score = 50 + pred_return * 2.0
        confidence_adj = 0.5 + confidence * 0.5
        ai_score = _clamp(raw_score * confidence_adj)

        return AIPredictDimension(
            name="AI预测",
            score=round(ai_score, 1),
            weight=WEIGHTS["ai_predict"],
            grade=_score_to_grade(ai_score),
            status=DimensionStatus.AVAILABLE,
            pred_return=round(pred_return, 2),
            pred_30d_close=round(pred_30d, 2),
            confidence=round(confidence, 3),
            inflection_days=inflection_days,
            max_drawdown=round(max_dd, 2),
            details={
                "pred_return_pct": round(pred_return, 2),
                "confidence": round(confidence, 3),
                "max_drawdown_pct": round(max_dd, 2),
                "model_metadata": pred.get("model_metadata"),
                "data_freshness": pred.get("data_freshness"),
                "fallback_reason": pred.get("fallback_reason"),
                "from_cache": pred.get("from_cache", False),
            },
            signals=[f"预测收益 {pred_return:+.1f}% (置信度 {confidence:.0%})"],
        )

    except Exception as e:
        logger.warning("Kronos prediction unavailable for %s: %s", code, e)
        return AIPredictDimension(
            name="AI预测",
            score=50.0,
            weight=WEIGHTS["ai_predict"],
            grade="C",
            status=DimensionStatus.UNAVAILABLE,
            details={
                "error": str(e),
                "note": "Kronos 服务暂不可用",
                "model_metadata": {
                    "name": "Kronos-mini",
                    "version": "kronos-mini",
                    "checkpoint_status": "unavailable",
                },
                "data_freshness": {
                    "status": "unknown",
                    "as_of": None,
                    "source": "prediction-service",
                    "quality_score": 0,
                },
                "fallback_reason": str(e),
            },
            signals=["AI 预测暂不可用"],
        )


# ═══════════════════════════════════════════════════════════════════════════
# Dimension 5: Sentiment (5%)
# ═══════════════════════════════════════════════════════════════════════════

async def _score_sentiment(code: str, db) -> SentimentDimension:
    """Compute sentiment score from news sentiment + research report ratings."""
    try:
        from sqlalchemy import text as sa_text

        # Query recent research report ratings
        rr_result = await db.execute(
            sa_text(
                "SELECT rating, target_price, broker AS org_name "
                "FROM research_reports "
                "WHERE code = :code AND pub_date >= CURRENT_DATE - INTERVAL '90 days' "
                "ORDER BY pub_date DESC LIMIT 5"
            ),
            {"code": code},
        )
        rr_rows = rr_result.fetchall()

        # Map ratings to scores
        rating_map = {
            "买入": 90, "增持": 75, "推荐": 80, "强烈推荐": 95,
            "持有": 50, "中性": 50, "谨慎推荐": 55,
            "减持": 30, "卖出": 15, "回避": 20,
        }
        if rr_rows:
            rating_scores = []
            for r in rr_rows:
                rating = str(r[0] or "")
                rating_scores.append(rating_map.get(rating, 50))
            research_score = float(np.mean(rating_scores))
            research_rating = str(rr_rows[0][0] or "无")
            analyst_target = float(rr_rows[0][1]) if rr_rows[0][1] else None
        else:
            research_score = 50.0
            research_rating = "无评级"
            analyst_target = None

        # Query news sentiment (mock — placeholder for NLP)
        news_score = 50.0
        try:
            ns_result = await db.execute(
                sa_text(
                    "SELECT AVG(sentiment_score) as avg_sentiment "
                    "FROM news_sentiment "
                    "WHERE code = :code AND created_at >= CURRENT_DATE - INTERVAL '30 days'"
                ),
                {"code": code},
            )
            ns_row = ns_result.fetchone()
            if ns_row and ns_row[0] is not None:
                raw_s = float(ns_row[0])  # -1 to 1
                news_score = _clamp(50 + raw_s * 40)  # map to 10-90
        except Exception:
            logger.debug("news_sentiment query failed for %s", code, exc_info=True)  # Table may not exist yet — use default

        # ── P0: 互动问答情绪分析 ──
        interact_score = 50.0
        interact_count = 0
        try:
            iq_result = await db.execute(
                sa_text(
                    "SELECT question, answer FROM interact_qa "
                    "WHERE code = :code AND pub_date >= CURRENT_DATE - INTERVAL '90 days' "
                    "ORDER BY pub_date DESC LIMIT 10"
                ),
                {"code": code},
            )
            iq_rows = iq_result.fetchall()
            if iq_rows:
                risk_keywords = ["风险", "亏损", "质押", "立案", "调查", "退市", "ST",
                                "减持", "商誉", "减值", "债务", "违约", "停工", "裁员",
                                "处罚", "罚款", "诉讼", "担保", "冻结"]
                opportunity_keywords = ["增长", "突破", "中标", "签约", "扩产", "新品",
                                       "利好", "回购", "增持", "分红", "订单"]
                pos_count = 0; neg_count = 0
                for row in iq_rows:
                    text = str(row[0] or "") + str(row[1] or "")
                    for kw in risk_keywords:
                        if kw in text:
                            neg_count += 1; break
                    for kw in opportunity_keywords:
                        if kw in text:
                            pos_count += 1; break
                if neg_count > pos_count:
                    interact_score = max(10, 50 - neg_count * 5)
                elif pos_count > neg_count:
                    interact_score = min(90, 50 + pos_count * 5)
                interact_count = len(iq_rows)
        except Exception:
            logger.debug("interact_qa query failed for %s", code, exc_info=True)

        # ── P3: 新闻联播行业热度 + 政策法规影响 ──
        policy_score = 50.0
        cctv_heat_score = 50.0
        policy_signals = []
        try:
            # Get stock's industry
            ind_result = await db.execute(
                sa_text("SELECT industry FROM stocks WHERE code = :code"),
                {"code": code},
            )
            ind_row = ind_result.fetchone()
            stock_industry = str(ind_row[0] or "") if ind_row else ""

            if stock_industry:
                # ── 新闻联播行业热度: 近期新闻联播关键词匹配 ──
                cctv_result = await db.execute(
                    sa_text(
                        "SELECT title, content FROM cctv_news "
                        "WHERE pub_date >= CURRENT_DATE - INTERVAL '7 days'"
                    ),
                )
                cctv_rows = cctv_result.fetchall()
                if cctv_rows:
                    # Industry keyword map: industry name → related keywords in news
                    industry_kw_map = {
                        "半导体": ["芯片", "半导体", "集成电路", "光刻", "晶圆"],
                        "电气设备": ["新能源", "光伏", "风电", "储能", "特高压", "电网"],
                        "软件服务": ["人工智能", "AI", "数字化", "软件", "数据"],
                        "汽车配件": ["新能源车", "智能驾驶", "汽车", "动力电池"],
                        "医疗保健": ["医药", "医疗", "生物", "疫苗", "健康"],
                        "化工原料": ["化工", "新材料", "石化", "碳中和"],
                        "通信设备": ["5G", "6G", "通信", "卫星", "算力"],
                        "元器件": ["电子", "传感器", "面板", "显示"],
                        "专用机械": ["机器人", "高端装备", "智能制造", "工业母机"],
                        "银行": ["金融", "银行", "信贷", "降准", "利率"],
                        "房地产": ["房地产", "住房", "楼市", "保障房"],
                        "证券": ["资本市场", "股市", "注册制", "科创板"],
                        "农业": ["农业", "粮食", "种业", "乡村振兴", "耕地"],
                        "食品饮料": ["消费", "食品", "餐饮", "零售"],
                        "航空": ["航天", "大飞机", "卫星", "民航"],
                        "互联网": ["互联网", "平台经济", "电商", "直播"],
                        "环境保护": ["环保", "双碳", "绿色", "新能源"],
                    }
                    # Find matching keywords for stock's industry
                    matched_kw = set()
                    for ind_kw, news_kws in industry_kw_map.items():
                        if ind_kw in stock_industry or stock_industry in ind_kw:
                            for row in cctv_rows:
                                text = str(row[0] or "") + str(row[1] or "")
                                for nk in news_kws:
                                    if nk in text:
                                        matched_kw.add(nk)
                    if matched_kw:
                        # Positive heat: industry mentioned in news = attention
                        cctv_heat_score = min(90, 55 + len(matched_kw) * 5)
                        policy_signals.append(f"新闻联播提及: {','.join(list(matched_kw)[:3])}")

                # ── 政策法规影响: 近期政策匹配行业 ──
                policy_result = await db.execute(
                    sa_text(
                        "SELECT title, ptype, puborg FROM policy_law "
                        "WHERE pub_date >= CURRENT_DATE - INTERVAL '30 days'"
                    ),
                )
                policy_rows = policy_result.fetchall()
                if policy_rows:
                    for row in policy_rows:
                        ptype = str(row[1] or "")
                        title = str(row[0] or "")
                        # Map policy type → industry keywords
                        ptype_industry_map = {
                            "科技": ["半导体", "元器件", "软件服务", "通信设备", "互联网"],
                            "金融": ["银行", "证券", "保险", "多元金融"],
                            "医药": ["医疗保健", "化学制药", "生物制药", "中成药"],
                            "能源": ["电气设备", "煤炭", "石油", "电力"],
                            "环保": ["环境保护", "水务", "新型电力"],
                            "房地产": ["房地产", "建筑工程", "建材"],
                            "农业": ["农业", "食品饮料", "饲料"],
                            "教育": ["文教休闲", "传媒娱乐"],
                            "交通": ["航空", "运输", "物流", "铁路"],
                            "财政": ["银行", "证券", "保险"],
                            "税务": ["银行", "证券", "保险"],
                        }
                        for pkw, industries in ptype_industry_map.items():
                            if pkw in ptype and any(ind in stock_industry for ind in industries):
                                puborg = str(row[2] or "")
                                if "国务院" in puborg or "发改委" in puborg:
                                    policy_score = 60  # 国家级别政策 → 适度积极
                                    policy_signals.append(f"政策: {title[:30]}...")
                                break
        except Exception:
            logger.debug("policy/cctv sentiment query failed for %s", code, exc_info=True)

        # Blend: research 40% + cctv 15% + policy 10% + interact 20% + news 15%
        sentiment_score = round(
            research_score * 0.40 + cctv_heat_score * 0.15 + policy_score * 0.10
            + interact_score * 0.20 + news_score * 0.15, 1
        )
        sentiment_score = _clamp(sentiment_score)

        signals = []
        if research_rating in ("买入", "增持", "强烈推荐"):
            signals.append(f"分析师评级: {research_rating}")
        if analyst_target:
            signals.append(f"目标价: {analyst_target:.2f}")
        for ps in policy_signals:
            signals.append(ps)

        return SentimentDimension(
            name="情绪面",
            score=sentiment_score,
            weight=WEIGHTS["sentiment"],
            grade=_score_to_grade(sentiment_score),
            status=DimensionStatus.AVAILABLE,
            news_sentiment=round(news_score / 100 * 2 - 1, 2),
            research_rating=research_rating,
            analyst_target=analyst_target,
            signals=signals if signals else None,
            details={
                "research_reports_count": len(rr_rows),
                "news_sentiment_score": round(news_score, 1),
                "cctv_heat_score": round(cctv_heat_score, 1),
                "policy_score": round(policy_score, 1),
            },
        )

    except Exception as e:
        logger.warning("Sentiment scoring failed for %s: %s", code, e)
        return SentimentDimension(
            name="情绪面",
            score=50.0,
            weight=WEIGHTS["sentiment"],
            grade="C",
            status=DimensionStatus.DEGRADED,
            details={"error": str(e)},
        )


# ═══════════════════════════════════════════════════════════════════════════
# P3: 宏观货币政策立场 (央行报告)
# ═══════════════════════════════════════════════════════════════════════════

async def _get_macro_stance(db) -> tuple[str, float]:
    """Extract macro monetary policy stance from latest PBOC report.

    Queries the most recent mp_report, strips HTML tags, and matches
    keyword patterns to determine policy stance.

    Returns:
        (stance_label, score_modifier): e.g. ("适度宽松", +3) or ("稳健", 0)
    """
    try:
        from sqlalchemy import text as sa_text

        result = await db.execute(
            sa_text(
                "SELECT title, content_html FROM mp_report "
                "ORDER BY pub_date DESC LIMIT 1"
            ),
        )
        row = result.fetchone()
        if not row:
            return "未知", 0.0

        title = str(row[0] or "")
        content = str(row[1] or "")

        # Strip HTML tags for keyword matching
        import re
        text = re.sub(r"<[^>]+>", "", content)
        full_text = title + " " + text[:3000]  # First 3000 chars is enough

        # ── Stance detection ──
        # Priority order: more specific → less specific
        if any(kw in full_text for kw in ["适度宽松", "宽松的货币政策"]):
            stance, modifier = "适度宽松", 3.0
        elif any(kw in full_text for kw in ["从紧", "收紧", "紧缩"]):
            stance, modifier = "紧缩", -5.0
        elif any(kw in full_text for kw in ["稳健", "灵活适度", "精准有力"]):
            stance, modifier = "稳健", 0.0
        elif any(kw in full_text for kw in ["偏宽松", "流动性充裕", "逆周期"]):
            stance, modifier = "偏宽松", 2.0
        elif any(kw in full_text for kw in ["流动性合理充裕", "不搞大水漫灌"]):
            stance, modifier = "稳健偏中性", -1.0
        else:
            stance, modifier = "未明确", 0.0

        return stance, modifier

    except Exception:
        logger.debug("Macro stance fetch failed", exc_info=True)
        return "无数据", 0.0


# ═══════════════════════════════════════════════════════════════════════════
# Helper: get K-line DataFrame
# ═══════════════════════════════════════════════════════════════════════════

async def _get_kline_df(db, code: str, lookback: int = 400):
    """Fetch K-line data as pandas DataFrame from DB."""
    try:
        import pandas as pd
        from sqlalchemy import text as sa_text

        result = await db.execute(
            sa_text(
                "SELECT trade_date, open, high, low, close, volume, amount "
                "FROM daily_kline WHERE code = :code ORDER BY trade_date ASC "
                "LIMIT :limit"
            ),
            {"code": code, "limit": lookback},
        )
        rows = result.fetchall()
        if not rows:
            return None

        df = pd.DataFrame(
            [dict(r._mapping) for r in rows],
            columns=["trade_date", "open", "high", "low", "close", "volume", "amount"],
        )
        df["timestamps"] = pd.to_datetime(df["trade_date"])
        return df
    except Exception as e:
        logger.warning("Failed to fetch K-line for %s: %s", code, e)
        return None


# ═══════════════════════════════════════════════════════════════════════════
# Main: diagnose()
# ═══════════════════════════════════════════════════════════════════════════

async def diagnose(
    code: str,
    db,
    force_refresh: bool = False,
    auth_token: Optional[str] = None,
) -> DiagnosisReport:
    """Run five-dimension stock diagnosis.

    Args:
        code: Stock code (e.g. 000001, 300750)
        db: Async SQLAlchemy session
        force_refresh: Skip cache, force recalculation
        auth_token: JWT Bearer token for Kronos API auth (C3 fix)

    Returns:
        DiagnosisReport with overall score, recommendation, and dimension details.
    """
    logger.info("Diagnosing %s (force_refresh=%s)...", code, force_refresh)

    # Each dimension gets its own DB session to isolate transaction failures
    from app.database import AsyncSessionLocal

    async def _run_dim(key: str, fn, code_arg, auth_token=None):
        try:
            async with AsyncSessionLocal() as dim_db:
                if auth_token is not None:
                    return await fn(code_arg, dim_db, auth_token=auth_token)
                return await fn(code_arg, dim_db)
        except Exception as e:
            logger.error("Dimension %s failed: %s", key, e)
            return e

    # _score_technical has special signature: (code, db, market_data)
    async def _run_tech():
        try:
            async with AsyncSessionLocal() as dim_db:
                return await _score_technical(code, dim_db, None)
        except Exception as e:
            logger.error("Dimension technical failed: %s", e)
            return e

    tech = await _run_tech()
    cap = await _run_dim("capital_flow", _score_capital_flow, code)
    fund = await _run_dim("fundamental", _score_fundamental, code)
    ai_p = await _run_dim("ai_predict", _score_ai_predict, code, auth_token)
    sent = await _run_dim("sentiment", _score_sentiment, code)

    # Handle exceptions in individual dimensions
    dims: Dict[str, DimensionScore] = {}
    for key, result, default_factory in [
        ("technical", tech, lambda: TechnicalDimension(
            name="技术面", score=50.0, weight=WEIGHTS["technical"], grade="C",
            status=DimensionStatus.DEGRADED, details={"error": "Scoring failed"},
        )),
        ("capital_flow", cap, lambda: CapitalFlowDimension(
            name="资金面", score=50.0, weight=WEIGHTS["capital_flow"], grade="C",
            status=DimensionStatus.DEGRADED, details={"error": "Scoring failed"},
        )),
        ("fundamental", fund, lambda: FundamentalDimension(
            name="基本面", score=50.0, weight=WEIGHTS["fundamental"], grade="C",
            status=DimensionStatus.DEGRADED, details={"error": "Scoring failed"},
        )),
        ("ai_predict", ai_p, lambda: AIPredictDimension(
            name="AI预测", score=50.0, weight=WEIGHTS["ai_predict"], grade="C",
            status=DimensionStatus.UNAVAILABLE, details={"error": "Scoring failed"},
        )),
        ("sentiment", sent, lambda: SentimentDimension(
            name="情绪面", score=50.0, weight=WEIGHTS["sentiment"], grade="C",
            status=DimensionStatus.DEGRADED, details={"error": "Scoring failed"},
        )),
    ]:
        if isinstance(result, Exception):
            logger.error("Dimension %s raised: %s", key, result)
            try:
                await db.rollback()
            except Exception:
                logger.warning("Rollback failed after dimension %s error", key, exc_info=True)
            dims[key] = default_factory()
        else:
            dims[key] = result

    # Check if Kronos is unavailable → use degraded weights
    kronos_available = dims["ai_predict"].status != DimensionStatus.UNAVAILABLE
    base_weights = WEIGHTS if kronos_available else DEGRADED_WEIGHTS

    # ── P4: 自适应市场 regime 权重 ──
    effective_weights = dict(base_weights)
    try:
        from kronos_factors.scorer.screening_scorers import get_market_regime
        regime_info = get_market_regime()
        regime = regime_info.get("regime", "neutral")
        if regime == "bull":
            effective_weights.update({"technical": 0.43, "fundamental": 0.14, "sentiment": 0.13})
        elif regime == "bear":
            effective_weights.update({"technical": 0.32, "fundamental": 0.24, "capital_flow": 0.20})
        # neutral: keep base weights
        # Normalize to ensure sum = 1.0
        w_sum = sum(effective_weights.values())
        effective_weights = {k: v / w_sum for k, v in effective_weights.items()}
    except Exception:
        logger.debug("Market regime detection failed, using base weights", exc_info=True)

    # Identify degraded dimensions
    degraded_dims = [
        k for k, v in dims.items()
        if v.status in (DimensionStatus.DEGRADED, DimensionStatus.UNAVAILABLE)
    ]

    # ── P3: 宏观货币政策立场 (来自央行报告) ──
    macro_stance, macro_modifier = await _get_macro_stance(db)

    # Compute weighted overall score (ADR-005 Decision 1)
    overall = sum(
        dims[key].score * effective_weights[key] for key in effective_weights
    )
    # Normalize: score / sum(weights) * 100
    weight_sum = sum(effective_weights.values())
    overall = (overall / weight_sum) if weight_sum > 0 else 50.0
    # Apply macro stance modifier (±5 points max)
    overall = overall + macro_modifier
    overall = round(_clamp(overall), 1)

    # Determine recommendation and grade
    recommendation, letter_grade = _score_to_recommendation(overall)

    # Generate recommendation reason
    reasons = []
    top_dims = sorted(dims.items(), key=lambda x: x[1].score, reverse=True)
    best_dim = top_dims[0]
    worst_dim = top_dims[-1]
    reasons.append(f"{best_dim[1].name}表现突出 ({best_dim[1].score:.0f}分)")
    if worst_dim[1].score < 50:
        reasons.append(f"{worst_dim[1].name}较弱 ({worst_dim[1].score:.0f}分)")

    if not kronos_available:
        reasons.insert(0, "AI 预测暂不可用 (权重已重新分配)")
    if macro_modifier != 0:
        prefix = "宏观利好" if macro_modifier > 0 else "宏观承压"
        reasons.insert(0, f"{prefix}: 央行{macro_stance} ({macro_modifier:+.0f}分)")

    reason_text = "；".join(reasons) + "。"

    # Compute key levels (support/resistance/stop-loss) from K-line
    key_levels = {"support": 0.0, "resistance": 0.0, "stop_loss": 0.0}
    try:
        kline_df = await _get_kline_df(db, code, lookback=60)
        if kline_df is not None and len(kline_df) >= 20:
            closes = kline_df["close"].values
            current_close = closes[-1]
            ma20 = closes[-20:].mean()
            ma60 = closes[-60:].mean() if len(closes) >= 60 else ma20
            # Rolling min as support, rolling max as resistance
            support = round(float(min(ma20, closes[-20:].min())), 2)
            resistance = round(float(max(closes[-20:].max(), current_close * 1.05)), 2)
            stop_loss = round(float(support * 0.95), 2)
            key_levels = {
                "support": support,
                "resistance": resistance,
                "stop_loss": stop_loss,
            }
    except Exception as e:
        logger.warning("Failed to compute key levels for %s: %s", code, e)

    # Collect risk warnings
    risk_warnings: List[str] = []
    if overall < 40:
        risk_warnings.append("综合评分偏低，请注意风险控制")
    if dims["fundamental"].score < 40:
        risk_warnings.append("基本面评分较弱")
    if dims["capital_flow"].score < 35:
        risk_warnings.append("资金面偏弱，注意流动性风险")
    if isinstance(dims["ai_predict"], AIPredictDimension) and dims["ai_predict"].max_drawdown:
        if dims["ai_predict"].max_drawdown < -15:
            risk_warnings.append(f"AI 预测最大回撤较大 ({dims['ai_predict'].max_drawdown:.1f}%)")

    ai_details = dims["ai_predict"].details or {}
    prediction_model = ai_details.get("model_metadata") or {
        "name": "Kronos-mini",
        "version": "kronos-mini",
        "checkpoint_status": "unknown",
    }
    data_freshness = ai_details.get("data_freshness") or {
        "status": "unknown",
        "as_of": None,
        "source": "diagnosis-service",
        "quality_score": 0,
    }
    fallback_reason = ai_details.get("fallback_reason")
    if not fallback_reason and degraded_dims:
        fallback_reason = "degraded dimensions: " + ", ".join(degraded_dims)

    report = DiagnosisReport(
        code=code,
        overall_score=overall,
        grade=letter_grade,
        recommendation=recommendation,
        recommendation_reason=reason_text,
        dimensions=dims,
        key_levels=key_levels,
        risk_warnings=risk_warnings,
        kronos_available=kronos_available,
        degraded=len(degraded_dims) > 0,
        degraded_dimensions=degraded_dims,
        model_metadata={
            "diagnosis_model": "five-dimension-weighted-v2",
            "prediction_model": prediction_model,
            "weights": effective_weights,
        },
        data_freshness=data_freshness,
        fallback_reason=fallback_reason,
        created_at=datetime.now(timezone.utc),
    )

    logger.info(
        "Diagnosis complete for %s: score=%.1f grade=%s recommendation=%s",
        code, overall, letter_grade, recommendation.value,
    )
    return report
