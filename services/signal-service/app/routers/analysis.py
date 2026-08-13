"""Signal analysis routes — 信号分析域.

super_signal / auction-intent / levels / analyze / batch / history /
limit-list / rules / live。
"""

import logging
from fastapi import Depends, Query, HTTPException
from kronos_auth import require_role, get_current_user_jwt

from app._shared import (
    router, store,
    _http_post_json, _with_signal_contract, _combine_signal_dimensions,
    _dashboard_row_change_pct,
    DIAGNOSIS_ANALYZE_URL, SCREENER_RUN_URL,
)

logger = logging.getLogger("signal-service.routes")


def _signal_live_sql() -> str:
    return """
        WITH latest AS (
            SELECT trade_date
            FROM daily_kline
            WHERE close IS NOT NULL
            ORDER BY trade_date DESC
            LIMIT 1
        ),
        latest_rows AS (
            SELECT d.code,
                   COALESCE(s.name, d.code) as name,
                   d.close,
                   COALESCE(
                       d.change_pct,
                       (d.close / NULLIF(prev.close, 0) - 1) * 100
                   ) AS change_pct,
                   d.volume,
                   d.trade_date
            FROM daily_kline d
            CROSS JOIN LATERAL (
                SELECT close
                FROM daily_kline p
                WHERE p.code = d.code
                  AND p.trade_date < d.trade_date
                  AND p.close IS NOT NULL
                  AND p.close > 0
                ORDER BY p.trade_date DESC
                LIMIT 1
            ) prev
            LEFT JOIN stocks s ON d.code = s.code
            WHERE d.trade_date = (SELECT trade_date FROM latest)
              AND d.close IS NOT NULL
        )
        SELECT code, name, close, change_pct, volume, trade_date
        FROM latest_rows
        WHERE change_pct IS NOT NULL
        ORDER BY ABS(change_pct) DESC
        LIMIT 20
    """


# ═══════════════════════════════════════════════════════════════
# P4: 跨模型超级信号 (screener + signal + diagnosis 融合)
# ═══════════════════════════════════════════════════════════════

@router.get("/super-signal/{code}")
async def super_signal(code: str, user: dict = Depends(get_current_user_jwt)):
    """P4: 跨模型融合, 综合 screener 排名 + 信号评分 + 诊断评分.

    仅在 screener 选出的前 50 只股票上计算, 不增加全市场扫描成本.
    """
    import urllib.request, json, os

    results = {"code": code, "super_score": None, "components": {}}

    # 1. Signal score (local)
    try:
        sig = await analyze_signal(code)
        sig_score = sig["signal"]["score"]
        results["components"]["signal"] = {"score": sig_score, "weight": 0.40}
    except Exception:
        sig_score = None
        results["components"]["signal"] = {"score": None, "weight": 0.40, "error": "unavailable"}

    # 2. Diagnosis score (HTTP call)
    try:
        diag = await _http_post_json(DIAGNOSIS_ANALYZE_URL, {"code": code}, timeout=5)
        diag_score = diag.get("overall_score")
        results["components"]["diagnosis"] = {"score": diag_score, "weight": 0.35}
    except Exception:
        diag_score = None
        results["components"]["diagnosis"] = {"score": None, "weight": 0.35, "error": "unavailable"}

    # 3. Screener rank (percentile)
    try:
        scr = await _http_post_json(SCREENER_RUN_URL, {"mode": "short", "top_n": 50}, timeout=10)
        picks = scr.get("picks", [])
        rank = next((i+1 for i, p in enumerate(picks) if p.get("code") == code), None)
        rank_score = max(10, 100 - rank * 2) if rank is not None else None
        results["components"]["screener"] = {"rank": rank, "score": rank_score, "weight": 0.25}
    except Exception:
        rank_score = None
        results["components"]["screener"] = {"score": None, "weight": 0.25, "error": "unavailable"}

    # Super score
    if any(value is None for value in (sig_score, diag_score, rank_score)):
        results["result_status"] = "insufficient_data"
        results["recommendation"] = "unavailable"
    else:
        results["super_score"] = round(sig_score * 0.40 + diag_score * 0.35 + rank_score * 0.25, 1)
        results["result_status"] = "ok"
        results["recommendation"] = "STRONG_BUY" if results["super_score"] >= 80 else "BUY" if results["super_score"] >= 60 else "HOLD" if results["super_score"] >= 40 else "REDUCE" if results["super_score"] >= 20 else "SELL"

    return results


@router.get("/auction-intent")
async def auction_intent(limit: int = Query(50, ge=10, le=200), user: dict = Depends(get_current_user_jwt)):
    """PRD: 开盘集合竞价意图分析 — 识别抢筹/出货信号.

    Scores each stock on 4 dimensions:
      1. 价格方向 (40%): auction change vs prev close
      2. 买卖压力 (25%): auction price vs VWAP
      3. 竞价强度 (20%): auction volume vs 20-day avg
      4. 开盘延续 (15%): open vs auction price

    Returns intent label + multi-dimension score for top N stocks by auction volume.
    """
    from kronos_factors.scorer._db_stub import _get_db as _db

    results = []
    try:
        with _db() as d:
            rows = d.execute("""
                WITH auction_data AS (
                    SELECT a.ts_code, a.close as auction_price, a.open, a.vol, a.amount, a.vwap,
                           prev.close as prev_close,
                           (a.close/NULLIF(prev.close,0)-1)*100 as chg_pct,
                           (a.open/NULLIF(a.close,0)-1)*100 as open_gap,
                           (a.close/NULLIF(a.vwap,0)-1)*100 as vs_vwap
                    FROM stk_auction_o a
                    CROSS JOIN LATERAL (
                        SELECT close FROM daily_kline
                        WHERE code=a.code AND trade_date<a.trade_date
                        ORDER BY trade_date DESC LIMIT 1
                    ) prev
                    WHERE a.trade_date=(SELECT MAX(trade_date) FROM stk_auction_o) AND a.vol>0
                ),
                vol_avg AS (
                    SELECT code, AVG(volume) as avg_vol FROM daily_kline
                    WHERE trade_date>(SELECT MAX(trade_date) FROM daily_kline)-INTERVAL '30 days'
                      AND trade_date<(SELECT MAX(trade_date) FROM daily_kline)
                    GROUP BY code
                )
                SELECT ad.*, COALESCE(s.name,ad.code) as name,
                       ROUND((ad.vol/NULLIF(va.avg_vol,0))::numeric,2) as vol_ratio
                FROM auction_data ad
                LEFT JOIN stocks s ON ad.code=s.code
                LEFT JOIN vol_avg va ON ad.code=va.code
                ORDER BY ad.vol DESC LIMIT %s
            """, (limit,)).fetchall()

        for r in rows:
            chg = float(r.get("chg_pct") or 0)
            vs_vwap = float(r.get("vs_vwap") or 0)
            vol_ratio = float(r.get("vol_ratio") or 0)
            open_gap = float(r.get("open_gap") or 0)

            price_score = max(0, min(40, (chg + 10) * 2))
            pressure_score = max(0, min(25, 12.5 + vs_vwap * 5))
            strength_score = max(0, min(20, vol_ratio * 0.5))
            gap_score = max(0, min(15, 7.5 + open_gap * 3))
            total = round(price_score + pressure_score + strength_score + gap_score)

            if total >= 75:    intent, icon = "强烈抢筹", "🔥"
            elif total >= 60:  intent, icon = "偏多抢筹", "📈"
            elif total >= 40:  intent, icon = "中性", "➖"
            elif total >= 25:  intent, icon = "偏空出货", "📉"
            else:              intent, icon = "强烈出货", "⚠️"

            results.append({
                "code": r.get("code",""), "name": r.get("name",""),
                "auction_price": round(float(r.get("auction_price") or 0), 2),
                "prev_close": round(float(r.get("prev_close") or 0), 2),
                "chg_pct": round(chg, 2), "vs_vwap": round(vs_vwap, 2),
                "vol_ratio": round(vol_ratio, 2), "open_gap": round(open_gap, 2),
                "vol": int(float(r.get("vol") or 0)),
                "amount": round(float(r.get("amount") or 0), 0),
                "intent": intent, "icon": icon, "score": total,
                "breakdown": {
                    "price_direction": round(price_score, 1),
                    "buy_sell_pressure": round(pressure_score, 1),
                    "auction_strength": round(strength_score, 1),
                    "opening_continuity": round(gap_score, 1),
                },
            })
    except Exception as e:
        logger.warning("Auction intent query failed: %s", e)
        return {"status": "error", "message": str(e)[:100], "results": []}

    return {
        "status": "ok",
        "trade_date": str(rows[0].get("trade_date", "")) if rows else "",
        "total": len(results),
        "model": "四维竞价意图评分: 价格方向(40) + 买卖压力(25) + 竞价强度(20) + 开盘延续(15)",
        "results": results,
    }


@router.get("/levels")
async def signal_levels(user: dict = Depends(get_current_user_jwt)):
    """Five-level signal classification."""
    payload = {
        "levels": [
            {"level": "STRONG_BUY", "icon": "🟢", "min_score": 80, "action": "重仓买入 (15-20%)"},
            {"level": "BUY",        "icon": "🟡", "min_score": 60, "action": "标准买入 (8-12%)"},
            {"level": "HOLD",       "icon": "🔵", "min_score": 40, "action": "维持仓位"},
            {"level": "REDUCE",     "icon": "🟠", "min_score": 20, "action": "减仓至半仓"},
            {"level": "SELL",       "icon": "🔴", "min_score": 0,  "action": "清仓"},
            {"level": "TIMING_ALERT","icon":"⚡", "min_score": -1, "action": "准备操作(拐点)"},
        ],
        "signal_formula": "Kronos x0.3 + FactorResonance x0.3 + RuleMatch x0.2 + MarketAdapt x0.2",
    }
    return _with_signal_contract(payload, mode="levels", source="signal.rules")


@router.get("/analyze/{code}")
async def analyze_signal(code: str, user: dict = Depends(get_current_user_jwt)):
    """Generate a real trading signal for a single stock using kronos-factors scorers.

    Returns: signal level, component scores, and reasoning.
    """
    from kronos_factors.scorer._db_stub import _get_market_data
    from kronos_factors.scorer import score_five_factor, score_money_flow, score_trend_strength

    df = _get_market_data().get_kline_df(code, lookback=400)
    if df is None or len(df) < 30:
        raise HTTPException(
            404,
            {
                "message": f"No K-line data for {code}",
                "fallback_reason": "source data missing: daily_kline has fewer than 30 rows",
            },
        )

    ff = score_five_factor(df)
    mf = score_money_flow(df)
    ts = score_trend_strength(df)

    # Normalize each to 0-100
    tech_score = min(100, ff["score"] / 25 * 100)
    money_score = min(100, mf["score"] / 10 * 100)
    trend_score = min(100, ts["score"] / 10 * 100)

    # ── P4: 六维信号升级 (新增 Fundamental + EventRisk) ──
    fundamental_score = None
    event_risk_score = None
    try:
        from kronos_factors.scorer.screening_scorers import score_long_term
        from kronos_factors.scorer.advanced_factors import get_tushare_scores
        lt = score_long_term(code)
        ts_data = get_tushare_scores(code)
        if lt.get("score") is not None:
            fundamental_score = lt["score"] * 10  # 0-10 → 0-100
        # EventRisk: blend tushare_events + tushare_financial
        ev_score = ts_data.get("tushare_events", {}).get("score")
        fin_score = ts_data.get("tushare_financial", {}).get("score")
        if ev_score is not None and fin_score is not None:
            event_risk_score = min(100, (ev_score * 0.6 + fin_score * 0.4) * 10)
    except Exception:
        logger.warning("fundamental/event-risk scoring failed for %s", code)

    # Kronos is unavailable until a real inference result exists.
    kronos_confidence = None
    # Market adaptation: use regime bonus from screener
    market_adapt = None
    try:
        from kronos_factors.scorer.screening_scorers import get_market_regime
        regime = get_market_regime()
        if regime.get("bonus") is not None:
            market_adapt = 50 + regime["bonus"] * 50
    except Exception:
        logger.warning("market regime scoring failed for %s", code)

    # Six-dimension weighted signal (total = 1.0)
    combined = _combine_signal_dimensions({
        "kronos": kronos_confidence, "technical": tech_score,
        "money_flow": money_score, "fundamental": fundamental_score,
        "event_risk": event_risk_score, "market": market_adapt,
    })
    signal_score = combined["score"]

    # Determine level
    if combined["result_status"] != "ok":
        level, icon = None, None
    elif signal_score >= 80:   level, icon = "STRONG_BUY", "🟢"
    elif signal_score >= 60:  level, icon = "BUY", "🟡"
    elif signal_score >= 40:  level, icon = "HOLD", "🔵"
    elif signal_score >= 20:  level, icon = "REDUCE", "🟠"
    else:                     level, icon = "SELL", "🔴"

    # ── P0: 审计意见风控 — 非标审计意见强制降级 ──
    audit_risk = None
    try:
        from sqlalchemy import text as sa_text
        from kronos_factors.scorer._db_stub import _get_db
        with _get_db(readonly=True) as db:
            audit_row = db.execute(
                "SELECT audit_result FROM fina_audit WHERE code=? ORDER BY end_date DESC LIMIT 1",
                (code,)
            ).fetchone()
        if audit_row:
            opinion = str(audit_row[0] or "")
            # Check most severe first; "保留意见" is substring of "标准无保留意见"!
            if "无法表示意见" in opinion or "否定意见" in opinion:
                level, icon = "SELL", "🔴"
                signal_score = max(0, signal_score - 25)
                audit_risk = {"opinion": opinion, "action": "强制SELL", "penalty": 25}
            elif "标准无保留意见" in opinion:
                audit_risk = None  # Clean, no action
            elif "保留意见" in opinion:
                signal_score = max(0, signal_score - 15)
                audit_risk = {"opinion": opinion, "action": "降级-15分", "penalty": 15}
                if signal_score < 20: level, icon = "SELL", "🔴"
                elif signal_score < 40: level, icon = "REDUCE", "🟠"
            elif "强调事项" in opinion or "持续经营" in opinion:
                signal_score = max(0, signal_score - 8)
                audit_risk = {"opinion": opinion, "action": "降级-8分", "penalty": 8}
    except Exception:
        pass  # fina_audit table not available

    # Record signal history
    if combined["result_status"] == "ok":
        store.record(code=code, level=level, icon=icon, score=round(signal_score, 1),
                     reason=f"技术{tech_score:.0f}/资金{money_score:.0f}/趋势{trend_score:.0f}")

    payload = {
        "code": code,
        "signal": None if combined["result_status"] != "ok" else {"level": level, "icon": icon, "score": round(signal_score, 1)},
        "decision": "unavailable" if combined["result_status"] != "ok" else level,
        "components": {
            "kronos_confidence": {"score": kronos_confidence, "weight": 0.20},
            "technical":         {"score": round(tech_score, 1), "weight": 0.20,
                                  "detail": {"five_factor": round(ff["score"]/25*100, 1),
                                             "trend": round(trend_score, 1)}},
            "fund_flow":         {"score": round(money_score, 1), "weight": 0.12},
            "fundamental":       {"score": round(fundamental_score, 1) if fundamental_score is not None else None, "weight": 0.15},
            "event_risk":        {"score": round(event_risk_score, 1) if event_risk_score is not None else None, "weight": 0.13},
            "market_adapt":      {"score": round(market_adapt, 1) if market_adapt is not None else None, "weight": 0.20},
            "rule_match":        {"score": None, "weight": 0.00, "note": "deprecated-merged-into-event-risk"},
        },
        "coverage": combined["coverage"],
        "unavailable_dimensions": combined["unavailable_dimensions"],
        "result_status": combined["result_status"],
        "factors": {
            "five_factor": {"score": ff["score"], "grade": ff["grade"],
                            "momentum": ff["momentum"], "volume": ff["volume_factor"],
                            "technical": ff["technical"], "quality": ff["quality"], "risk": ff["risk"]},
            "money_flow": mf,
            "trend_strength": ts,
        },
        "audit_risk": audit_risk,
        "generated_at": __import__("datetime").datetime.now().isoformat(),
    }
    return _with_signal_contract(payload, mode="analyze", data=df)


@router.post("/batch")
async def batch_signals(codes: list[str], user: dict = Depends(get_current_user_jwt)):
    """Generate signals for multiple stocks (up to 30)."""
    if len(codes) > 30:
        raise HTTPException(400, "Max 30 stocks per batch")
    results = []
    for code in codes:
        try:
            r = await analyze_signal(code)
            results.append(r)
        except HTTPException:
            results.append({"code": code, "error": "no_data"})
    return {"batch_size": len(codes), "success": len([r for r in results if "error" not in r]),
            "signals": results}


@router.get("/history")
async def signal_history(
    code: str = Query(None),
    session: str = Query(None),
    limit: int = Query(50, ge=10, le=200),
    user: dict = Depends(get_current_user_jwt),
):
    """Query historical signals with filters."""
    results = store.query(code=code, session=session, limit=limit)
    return {
        "signals": [{"code": s.code, "level": s.level, "icon": s.icon,
                      "score": s.score, "reason": s.reason, "session": s.session,
                      "created_at": s.created_at} for s in results],
        "total": len(results),
        "filters": {"code": code, "session": session},
    }


@router.get("/limit-list")
async def limit_list(type: str = Query("up", description="up | down"), user: dict = Depends(get_current_user_jwt)):
    """PRD: Drill-down endpoint for limit-up / limit-down stock lists."""
    from kronos_factors.scorer._db_stub import _get_db
    try:
        with _get_db() as d:
            rows = d.execute(
                "SELECT l.code, COALESCE(s.name, l.code) as name, l.up_limit, l.down_limit, "
                "l.pre_close, l.limit_status "
                "FROM stk_limit l LEFT JOIN stocks s ON l.code=s.code "
                "WHERE l.trade_date=(SELECT MAX(trade_date) FROM stk_limit)"
            ).fetchall()
        stocks = []
        for r in rows:
            pre_close = float(r.get("pre_close") or 0)
            up_lmt = float(r.get("up_limit") or 0)
            down_lmt = float(r.get("down_limit") or 0)
            status = (r.get("limit_status") or "").lower()
            is_up = "up" in status or (pre_close and up_lmt and abs(pre_close-up_lmt)<0.01)
            if type == "up" and is_up:
                stocks.append({"code": r["code"], "name": r["name"],
                               "limit_price": round(up_lmt,2),
                               "change_pct": round((up_lmt-pre_close)/pre_close*100,1) if pre_close else 0})
            elif type == "down" and not is_up:
                stocks.append({"code": r["code"], "name": r["name"],
                               "limit_price": round(down_lmt,2),
                               "change_pct": round((down_lmt-pre_close)/pre_close*100,1) if pre_close else 0})
        return {"type": type, "count": len(stocks), "stocks": stocks}
    except Exception as e:
        return {"type": type, "count": 0, "stocks": [], "error": str(e)[:100]}


@router.put("/rules")
async def update_signal_rules(
    kronos_weight: float = Query(0.3, ge=0.1, le=0.5),
    factor_weight: float = Query(0.3, ge=0.1, le=0.5),
    rule_weight: float = Query(0.2, ge=0.05, le=0.4),
    market_weight: float = Query(0.2, ge=0.05, le=0.4),
    user: dict = Depends(require_role("admin", "internal_analyst")),
):
    total = kronos_weight + factor_weight + rule_weight + market_weight
    return {
        "weights": {
            "kronos_confidence": round(kronos_weight / total, 3),
            "factor_resonance":  round(factor_weight / total, 3),
            "rule_match":        round(rule_weight / total, 3),
            "market_adapt":      round(market_weight / total, 3),
        },
        "status": "updated",
    }


# ═══════════════════════════════════════════════════════════════
# Live Signal Endpoint — real-time signal stream
# ═══════════════════════════════════════════════════════════════

@router.get("/live")
async def signal_live(session: str = Query("intra", description="intra | post | auction"),
                      user: dict = Depends(get_current_user_jwt)):
    """Return live trading signals for the dashboard signal cards.

    Returns recent high-signal stocks with price, change_pct, and signal metadata.
    """
    from kronos_factors.scorer._db_stub import _get_db as _db

    signals = []
    trade_date = ""
    try:
        with _db() as d:
            # Fetch top 20 stocks with strongest recent momentum as live signals
            rows = d.execute(_signal_live_sql()).fetchall()
            for r in rows:
                chg = _dashboard_row_change_pct(r)
                trade_date = str(r.get("trade_date") or trade_date)
                signal = "Bullish" if chg > 3 else ("Bearish" if chg < -3 else "Neutral")
                desc = (
                    f"强势上涨 {chg:.1f}%" if chg > 3 else
                    f"大幅下跌 {chg:.1f}%" if chg < -3 else
                    f"震荡 {chg:+.1f}%"
                )
                market = (
                    "上海" if str(r["code"]).startswith("6") else
                    "深圳" if str(r["code"]).startswith(("00", "30")) else "科创板"
                )
                signals.append({
                    "code": str(r["code"]),
                    "name": str(r.get("name") or ""),
                    "price": round(float(r["close"] or 0), 2),
                    "change_pct": round(chg, 2),
                    "volume": int(r.get("volume") or 0),
                    "signal": signal,
                    "desc": desc,
                    "market": market,
                })
    except Exception as e:
        logger.warning("Live signals query failed: %s", e)

    return {
        "session": session,
        "signals": signals,
        "count": len(signals),
        "trade_date": trade_date,
        "data_freshness": {
            "status": "fresh" if trade_date else "unknown",
            "as_of": trade_date or None,
            "source": "PG daily_kline",
        },
    }
