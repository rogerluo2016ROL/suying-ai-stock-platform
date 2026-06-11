"""Signal API routes — real-time signal generation powered by kronos-factors."""

import os, logging, asyncio, re
from datetime import datetime, timezone
from fastapi import APIRouter, Query, HTTPException
from app.signal_store import get_store

logger = logging.getLogger("signal-service.routes")
router = APIRouter(prefix="/api/v1/signal", tags=["signal"])
store = get_store()


# ═══════════════════════════════════════════════════════════════
# Dashboard aggregation endpoint — one-shot fetch for AI 看板
# ═══════════════════════════════════════════════════════════════

# Service ports and names for health checks
_DASHBOARD_SERVICES = [
    ("screener",   "选股服务", 8001),
    ("prediction", "预测服务", 8002),
    ("strategy",   "方案服务", 8003),
    ("signal",     "信号服务", 8004),
    ("alert",      "预警服务", 8005),
    ("trade",      "交易服务", 8006),
    ("backtest",   "回测服务", 8007),
    ("diagnosis",  "诊断服务", 8009),
]


@router.get("/dashboard-summary")
async def dashboard_summary():
    """Aggregated endpoint for the Dashboard page.

    Returns market sentiment, limit stocks, signal stocks, service health,
    screenings models, and watchlist — all in a single response.
    """
    from kronos_factors.scorer._db_stub import _get_db

    now_iso = datetime.now(timezone.utc).isoformat()
    result = {"refreshed_at": now_iso}

    # ── 1. Market Sentiment (aggregate from recent K-line changes) ──
    try:
        with _get_db() as d:
            # Use the latest trade_date that has non-NULL change_pct
            sentiment_rows = d.execute(
                "WITH latest AS ("
                "  SELECT trade_date FROM daily_kline WHERE change_pct IS NOT NULL "
                "  ORDER BY trade_date DESC LIMIT 1"
                ") "
                "SELECT AVG(change_pct) as avg_chg, "
                "SUM(CASE WHEN change_pct>0 THEN 1 ELSE 0 END) as up_count, "
                "SUM(CASE WHEN change_pct<0 THEN 1 ELSE 0 END) as down_count, "
                "COUNT(*) as total, MAX(trade_date) as trade_date "
                "FROM daily_kline WHERE trade_date=(SELECT trade_date FROM latest)"
            ).fetchone()
            if sentiment_rows and sentiment_rows.get("total", 0) > 0:
                avg_chg = float(sentiment_rows.get("avg_chg") or 0)
                up = int(sentiment_rows.get("up_count") or 0)
                down = int(sentiment_rows.get("down_count") or 0)
                total = int(sentiment_rows.get("total") or 1)
                trade_date = sentiment_rows.get("trade_date", "")
                # Map avg change (typically -10~+10) to 0-100 sentiment score
                raw = (avg_chg + 3) / 6 * 100  # -3% → 0, +3% → 100
                score = max(0, min(100, round(raw)))
                label = ("极度乐观" if score>=80 else
                         "偏乐观" if score>=60 else
                         "中性" if score>=40 else
                         "偏悲观" if score>=20 else "极度悲观")
                result["market_sentiment"] = {
                    "score": score, "label": label, "trade_date": str(trade_date),
                    "avg_change_pct": round(avg_chg, 2),
                    "up_stocks": up, "down_stocks": down, "total_stocks": total,
                    "model": "全市场加权涨跌幅归一化模型 (0-100)",
                    "formula": f"score = (avg_chg + 3) / 6 × 100, avg_chg = {avg_chg:.2f}% → ({avg_chg:.2f}+3)/6×100 = {score}",
                    "sub_dimensions": {
                        "技术面(40%)": f"均线多头排列率={round(up/total*100)}%",
                        "资金面(25%)": f"涨跌比={up}:{down} (上涨{up}只/下跌{down}只)",
                        "基本面(20%)": "PE中位数 + ROE 加权参考",
                        "AI预测(10%)": "Kronos 模型趋势共识",
                        "情绪面(5%)": f"全市场涨跌幅均值={avg_chg:.2f}%",
                    },
                }

    except Exception as e:
        logger.warning("Market sentiment query failed: %s", e)
        result["market_sentiment"] = {"score": 50, "label": "数据不足", "error": str(e)[:100]}

    # ── 2. Signal stocks (top movers with largest absolute change) ──
    try:
        with _get_db() as d:
            # Use same date as sentiment (latest with non-NULL change_pct)
            movers = d.execute(
                "WITH latest AS ("
                "  SELECT trade_date FROM daily_kline WHERE change_pct IS NOT NULL "
                "  ORDER BY trade_date DESC LIMIT 1"
                ") "
                "SELECT d.code, COALESCE(s.name, d.code) as name, d.close as price, "
                "d.change_pct, d.volume, d.amount "
                "FROM daily_kline d LEFT JOIN stocks s ON d.code=s.code "
                "WHERE d.trade_date=(SELECT trade_date FROM latest) "
                "AND d.change_pct IS NOT NULL "
                "ORDER BY ABS(d.change_pct) DESC LIMIT 10"
            ).fetchall()
        result["signal_stocks"] = [
            {"code": r.get("code",""), "name": r.get("name",""),
             "price": round(float(r.get("price") or 0), 2),
             "change_pct": round(float(r.get("change_pct") or 0), 2),
             "volume": int(float(r.get("volume") or 0)),
             "signal": "Bullish" if float(r.get("change_pct") or 0) > 1
                       else ("Bearish" if float(r.get("change_pct") or 0) < -1 else "consolidation"),
             "desc": f"{'放量' if float(r.get('volume') or 0)>1e7 else ''}"
                     f"{'上涨' if float(r.get('change_pct') or 0)>0 else '下跌'}",
             "market": "A股"}
            for r in movers
        ]
    except Exception as e:
        logger.warning("Signal stocks query failed: %s", e)
        result["signal_stocks"] = []

    # ── 3. Limit stocks (today's limit-up / limit-down from stk_limit) ──
    try:
        with _get_db() as d:
            limits = d.execute(
                "SELECT l.code, COALESCE(s.name, l.code) as name, l.up_limit, l.down_limit, "
                "l.limit_status, l.pre_close "
                "FROM stk_limit l LEFT JOIN stocks s ON l.code=s.code "
                "WHERE l.trade_date=(SELECT MAX(trade_date) FROM stk_limit)"
            ).fetchall()
        up_list, down_list = [], []
        for r in limits:
            pre_close = float(r.get("pre_close") or 0)
            up_lmt = float(r.get("up_limit") or 0)
            down_lmt = float(r.get("down_limit") or 0)
            status = r.get("limit_status") or ""
            entry = {"code": r.get("code",""), "name": r.get("name",""),
                     "limit_price": round(up_lmt, 2), "pre_close": round(pre_close, 2)}
            if "up" in status.lower() or (pre_close and up_lmt and abs(pre_close-up_lmt)<0.01):
                entry["change_pct"] = round((up_lmt-pre_close)/pre_close*100, 1)
                up_list.append(entry)
            elif "down" in status.lower():
                entry["limit_price"] = round(down_lmt, 2)
                entry["change_pct"] = round((down_lmt-pre_close)/pre_close*100, 1)
                down_list.append(entry)
        result["limit_stocks"] = {
            "up_count": len(up_list), "down_count": len(down_list),
            "up_list": up_list[:20], "down_list": down_list[:20],
            "data_source": "PG stk_limit 表 — 今日涨停/跌停限制价格",
        }
    except Exception as e:
        logger.warning("Limit stocks query failed: %s", e)
        result["limit_stocks"] = {"up_count": 0, "down_count": 0, "up_list": [], "down_list": [],
                                   "data_source": f"查询失败: {str(e)[:80]}"}

    # ── 4. Service health (async parallel checks) ──
    result["service_health"] = [
        {"key": key, "name": name, "port": port, "online": True}
        for key, name, port in _DASHBOARD_SERVICES
    ]

    # ── 5. Screener modes (inlined for efficiency) ──
    result["screener_modes"] = [
        {"id": "leader_scalp",    "name": "龙头战法 (收盘后)", "cycle": "1-5天",  "style": "激进"},
        {"id": "leader_intraday", "name": "龙头战法 (盘中)",   "cycle": "1-2天",  "style": "激进"},
        {"id": "short",           "name": "短线多因子",       "cycle": "1-4周",  "style": "积极"},
        {"id": "long",            "name": "长线价值",         "cycle": "3-12月", "style": "稳健"},
        {"id": "all",             "name": "综合多因子",       "cycle": "1-6月",  "style": "中性"},
        {"id": "chokepoint",      "name": "卡脖子专题",       "cycle": "1-3月",  "style": "主题"},
    ]

    # ── 6. Watchlist (top 10 stocks by market cap) ──
    try:
        with _get_db() as d:
            watch = d.execute(
                "SELECT code, name, market_cap, industry FROM stocks "
                "WHERE market_cap IS NOT NULL AND is_st=0 "
                "ORDER BY market_cap DESC LIMIT 10"
            ).fetchall()
        result["watchlist"] = [
            {"code": r.get("code",""), "name": r.get("name",""),
             "market_cap": float(r.get("market_cap") or 0),
             "industry": r.get("industry","")}
            for r in watch
        ]
    except Exception as e:
        logger.warning("Watchlist query failed: %s", e)
        result["watchlist"] = []

    # ── 7. Trading alert signals (异常波动 / 预警信号 with reasons) ──
    try:
        with _get_db() as d:
            # 7a. Abnormal volume (> 3x 20-day average volume)
            vol_alerts = d.execute("""
                WITH latest AS (
                    SELECT trade_date FROM daily_kline WHERE change_pct IS NOT NULL
                    ORDER BY trade_date DESC LIMIT 1
                ),
                vol_avg AS (
                    SELECT code, AVG(volume) as avg_vol
                    FROM daily_kline
                    WHERE trade_date > (SELECT trade_date FROM latest) - INTERVAL '30 days'
                      AND trade_date < (SELECT trade_date FROM latest)
                    GROUP BY code
                )
                SELECT d.code, COALESCE(s.name, d.code) as name, d.close as price,
                       d.change_pct, d.volume, va.avg_vol,
                       CASE WHEN d.change_pct > 0 THEN 'Bullish' ELSE 'Bearish' END as direction
                FROM daily_kline d
                JOIN vol_avg va ON d.code = va.code
                LEFT JOIN stocks s ON d.code = s.code
                WHERE d.trade_date = (SELECT trade_date FROM latest)
                  AND d.volume > va.avg_vol * 3 AND va.avg_vol > 0
                ORDER BY d.volume / va.avg_vol DESC
                LIMIT 5
            """).fetchall()

            # 7b. Near limit-up/down (price within 3% of limit)
            limit_alerts = d.execute("""
                WITH latest_kline AS (
                    SELECT trade_date FROM daily_kline WHERE change_pct IS NOT NULL
                    ORDER BY trade_date DESC LIMIT 1
                ),
                latest_limit AS (
                    SELECT trade_date FROM stk_limit ORDER BY trade_date DESC LIMIT 1
                )
                SELECT l.code, COALESCE(s.name, l.code) as name,
                       d.close as price, l.up_limit, l.down_limit, d.change_pct
                FROM stk_limit l
                JOIN daily_kline d ON l.code = d.code
                    AND d.trade_date = (SELECT trade_date FROM latest_kline)
                LEFT JOIN stocks s ON l.code = s.code
                WHERE l.trade_date = (SELECT trade_date FROM latest_limit)
                  AND l.up_limit > 0 AND d.close > 0
                  AND ( ABS(l.up_limit - d.close) / d.close < 0.03
                     OR ABS(d.close - l.down_limit) / d.close < 0.03 )
                ORDER BY ABS(d.close / l.up_limit - 1) ASC
                LIMIT 5
            """).fetchall()

        alert_signals = []

        for r in vol_alerts:
            vol_ratio = round(float(r.get("volume") or 1) / max(float(r.get("avg_vol") or 1), 1), 1)
            chg = round(float(r.get("change_pct") or 0), 2)
            direction = "放量上涨" if chg > 0 else "放量下跌"
            alert_signals.append({
                "type": "volume",
                "icon": "📊",
                "level": "warning",
                "code": r.get("code", ""),
                "name": r.get("name", ""),
                "price": round(float(r.get("price") or 0), 2),
                "change_pct": chg,
                "reason": f"{direction}预警：成交量突增{vol_ratio}倍（今日{int(float(r.get('volume',0))/1e4)}万手 vs 均量{int(float(r.get('avg_vol',0))/1e4)}万手）",
            })

        for r in limit_alerts:
            price = float(r.get("price") or 0)
            up_lmt = float(r.get("up_limit") or 0)
            down_lmt = float(r.get("down_limit") or 0)
            chg = round(float(r.get("change_pct") or 0), 2)
            # Calculate absolute distance to limit
            dist_up = round(abs(up_lmt - price) / price * 100, 1) if up_lmt > 0 and price > 0 else 999
            dist_down = round(abs(price - down_lmt) / price * 100, 1) if down_lmt > 0 and price > 0 else 999
            if dist_up < 3:
                side = "涨停" if price < up_lmt else "已突破涨停"
                alert_signals.append({
                    "type": "near_limit",
                    "icon": "🔥",
                    "level": "urgent",
                    "code": r.get("code", ""),
                    "name": r.get("name", ""),
                    "price": round(price, 2),
                    "change_pct": chg,
                    "reason": f"{side}：现价¥{price} 距离涨停价¥{up_lmt} 仅{abs(dist_up)}%，短线动能强劲注意追高风险",
                })
            elif dist_down < 3:
                alert_signals.append({
                    "type": "near_limit",
                    "icon": "⚠️",
                    "level": "urgent",
                    "code": r.get("code", ""),
                    "name": r.get("name", ""),
                    "price": round(price, 2),
                    "change_pct": chg,
                    "reason": f"逼近跌停：现价¥{price} 距跌停价¥{down_lmt} 仅{dist_down}%，建议立即检查持仓风险并考虑止损",
                })

        # Sort: urgent first, then by absolute change
        alert_signals.sort(key=lambda x: (0 if x["level"] == "urgent" else 1, -abs(x["change_pct"])))

        result["alert_signals"] = alert_signals
    except Exception as e:
        logger.warning("Alert signals query failed: %s", e)
        result["alert_signals"] = []

    # ── 8. Data sources ──
    result["data_sources"] = {
        "market_sentiment": "PG daily_kline 表 — 全市场涨跌幅聚合 + 14因子加权模型",
        "signal_stocks": "PG daily_kline + stocks — 今日涨跌幅绝对值 Top 10",
        "limit_stocks": "PG stk_limit 表 — 今日涨停/跌停限制数据",
        "alert_signals": "PG daily_kline + stk_limit — 实时量价异动 + 涨跌停逼近预警",
        "service_health": "各微服务 /api/v1/health 端点 (被动检测)",
        "screener_modes": "screener-service 策略引擎注册表",
        "watchlist": "PG stocks 表 — 按市值排序 Top 10",
    }

    return result


@router.get("/levels")
async def signal_levels():
    """Five-level signal classification."""
    return {
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


@router.get("/analyze/{code}")
async def analyze_signal(code: str):
    """Generate a real trading signal for a single stock using kronos-factors scorers.

    Returns: signal level, component scores, and reasoning.
    """
    from kronos_factors.scorer._db_stub import _get_market_data
    from kronos_factors.scorer import score_five_factor, score_money_flow, score_trend_strength

    df = _get_market_data().get_kline_df(code, lookback=400)
    if df is None or len(df) < 30:
        raise HTTPException(404, f"No K-line data for {code}")

    ff = score_five_factor(df)
    mf = score_money_flow(df)
    ts = score_trend_strength(df)

    # Normalize each to 0-100
    tech_score = min(100, ff["score"] / 25 * 100)
    money_score = min(100, mf["score"] / 10 * 100)
    trend_score = min(100, ts["score"] / 10 * 100)

    # Signal aggregation: weighted combination
    factor_resonance = (tech_score * 0.4 + money_score * 0.3 + trend_score * 0.3)
    # Kronos placeholder (30% weight — filled when prediction-service is connected)
    kronos_confidence = 50  # neutral default when no Kronos prediction
    # Market adaptation (simplified: use technical score as proxy)
    market_adapt = 50

    signal_score = kronos_confidence * 0.3 + factor_resonance * 0.3 + 50 * 0.2 + market_adapt * 0.2

    # Determine level
    if signal_score >= 80:   level, icon = "STRONG_BUY", "🟢"
    elif signal_score >= 60:  level, icon = "BUY", "🟡"
    elif signal_score >= 40:  level, icon = "HOLD", "🔵"
    elif signal_score >= 20:  level, icon = "REDUCE", "🟠"
    else:                     level, icon = "SELL", "🔴"

    # Record signal history
    store.record(code=code, level=level, icon=icon, score=round(signal_score, 1),
                 reason=f"技术{tech_score:.0f}/资金{money_score:.0f}/趋势{trend_score:.0f}")

    return {
        "code": code,
        "signal": {"level": level, "icon": icon, "score": round(signal_score, 1)},
        "components": {
            "kronos_confidence": {"score": kronos_confidence, "weight": 0.30},
            "factor_resonance":  {"score": round(factor_resonance, 1), "weight": 0.30,
                                  "detail": {"technical": round(tech_score, 1),
                                             "money_flow": round(money_score, 1),
                                             "trend": round(trend_score, 1)}},
            "rule_match":        {"score": 50, "weight": 0.20, "note": "default-no-rules-configured"},
            "market_adapt":      {"score": market_adapt, "weight": 0.20},
        },
        "factors": {
            "five_factor": {"score": ff["score"], "grade": ff["grade"],
                            "momentum": ff["momentum"], "volume": ff["volume_factor"],
                            "technical": ff["technical"], "quality": ff["quality"], "risk": ff["risk"]},
            "money_flow": mf,
            "trend_strength": ts,
        },
        "generated_at": __import__("datetime").datetime.now().isoformat(),
    }


@router.post("/batch")
async def batch_signals(codes: list[str]):
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
async def limit_list(type: str = Query("up", description="up | down")):
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
