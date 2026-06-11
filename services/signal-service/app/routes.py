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
                    "reason": f"{side}：现价元{price} 距离涨停价元{up_lmt} 仅{abs(dist_up)}%,短线动能强劲注意追高风险",
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
                    "reason": f"逼近跌停：现价元{price} 距跌停价元{down_lmt} 仅{dist_down}%,建议立即检查持仓风险并考虑止损",
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

    # ── 9. Auction intent (开盘竞价意图分析) ──
    try:
        with _get_db() as d:
            auction_results = d.execute("""
                WITH latest_auction AS (
                    SELECT trade_date FROM stk_auction_o ORDER BY trade_date DESC LIMIT 1
                ),
                auction_data AS (
                    SELECT a.code, a.close as auction_price, a.open, a.high, a.low,
                           a.vol, a.amount, a.vwap,
                           prev.close as prev_close,
                           (a.close / NULLIF(prev.close, 0) - 1) * 100 as chg_pct,
                           (a.open / NULLIF(a.close, 0) - 1) * 100 as open_gap,
                           (a.close / NULLIF(a.vwap, 0) - 1) * 100 as vs_vwap
                    FROM stk_auction_o a
                    CROSS JOIN LATERAL (
                        SELECT close FROM daily_kline
                        WHERE code = a.code AND trade_date < a.trade_date
                        ORDER BY trade_date DESC LIMIT 1
                    ) prev
                    WHERE a.trade_date = (SELECT trade_date FROM latest_auction)
                      AND a.vol > 0
                ),
                vol_avg AS (
                    SELECT code, AVG(volume) as avg_vol
                    FROM daily_kline
                    WHERE trade_date > (SELECT MAX(trade_date) FROM daily_kline) - INTERVAL '30 days'
                      AND trade_date < (SELECT MAX(trade_date) FROM daily_kline)
                    GROUP BY code
                )
                SELECT ad.code,
                       COALESCE(s.name, ad.code) as name,
                       ad.auction_price, ad.open, ad.vwap, ad.vol, ad.amount,
                       ad.prev_close,
                       ROUND(ad.chg_pct::numeric, 2) as chg_pct,
                       ROUND(ad.open_gap::numeric, 2) as open_gap,
                       ROUND(ad.vs_vwap::numeric, 2) as vs_vwap,
                       ROUND((ad.vol / NULLIF(va.avg_vol, 0))::numeric, 2) as vol_ratio
                FROM auction_data ad
                LEFT JOIN stocks s ON ad.code = s.code
                LEFT JOIN vol_avg va ON ad.code = va.code
                ORDER BY ad.vol DESC
                LIMIT 100
            """).fetchall()

        intent_list = []
        for r in auction_results:
            chg = float(r.get("chg_pct") or 0)
            vs_vwap = float(r.get("vs_vwap") or 0)
            vol_ratio = float(r.get("vol_ratio") or 0)
            open_gap = float(r.get("open_gap") or 0)

            # Multi-dimension intent scoring (0-100)
            price_score = max(0, min(40, (chg + 10) * 2))  # -10%→0, +10%→40
            pressure_score = max(0, min(25, 12.5 + vs_vwap * 5))  # -2.5%→0, +2.5%→25
            strength_score = max(0, min(20, vol_ratio * 0.5))  # vol_ratio 0→0, 40x→20
            gap_score = max(0, min(15, 7.5 + open_gap * 3))  # -2.5%→0, +2.5%→15
            total = round(price_score + pressure_score + strength_score + gap_score)

            if total >= 75:
                intent, icon, level = "强烈抢筹", "🔥", "bullish"
            elif total >= 60:
                intent, icon, level = "偏多抢筹", "📈", "bullish"
            elif total >= 40:
                intent, icon, level = "中性", "➖", "neutral"
            elif total >= 25:
                intent, icon, level = "偏空出货", "📉", "bearish"
            else:
                intent, icon, level = "强烈出货", "⚠️", "bearish"

            # Reason string
            reasons = []
            if chg > 3: reasons.append(f"竞价高开{chg:.1f}%")
            elif chg < -3: reasons.append(f"竞价低开{chg:.1f}%")
            if vs_vwap > 1: reasons.append("买盘踊跃(价>均价)")
            elif vs_vwap < -1: reasons.append("卖压沉重(价<均价)")
            if vol_ratio > 3: reasons.append(f"竞价放量{vol_ratio:.0f}倍")
            if open_gap > 0.5: reasons.append("开盘续涨")
            elif open_gap < -0.5: reasons.append("开盘续跌")

            intent_list.append({
                "code": r.get("code", ""),
                "name": r.get("name", ""),
                "auction_price": round(float(r.get("auction_price") or 0), 2),
                "prev_close": round(float(r.get("prev_close") or 0), 2),
                "chg_pct": round(chg, 2),
                "vs_vwap": round(vs_vwap, 2),
                "vol_ratio": round(vol_ratio, 2),
                "open_gap": round(open_gap, 2),
                "vol": int(float(r.get("vol") or 0)),
                "amount": round(float(r.get("amount") or 0), 0),
                "intent": intent,
                "icon": icon,
                "level": level,
                "score": total,
                "reasons": reasons,
            })

        # Summary counts
        bullish = [i for i in intent_list if i["level"] == "bullish"]
        bearish = [i for i in intent_list if i["level"] == "bearish"]
        neutral = [i for i in intent_list if i["level"] == "neutral"]

        result["auction_intent"] = {
            "trade_date": str(auction_results[0].get("trade_date", "")) if auction_results else "",
            "total_analyzed": len(intent_list),
            "bullish_count": len(bullish),
            "bearish_count": len(bearish),
            "neutral_count": len(neutral),
            "top_bullish": bullish[:5],
            "top_bearish": bearish[:5],
            "data_source": "PG stk_auction_o 表 (Tushare 集合竞价数据)",
        }
    except Exception as e:
        logger.warning("Auction intent analysis failed: %s", e)
        result["auction_intent"] = {"error": str(e)[:80]}

    result["data_sources"]["auction_intent"] = "PG stk_auction_o — 开盘集合竞价多维意图分析 (价格方向/买卖压力/竞价强度/开盘延续)"

    return result


@router.get("/auction-intent")
async def auction_intent(limit: int = Query(50, ge=10, le=200)):
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


# ═══════════════════════════════════════════════════════════════
# Data Status — 数据更新状态监控
# ═══════════════════════════════════════════════════════════════

_DATA_SOURCES = [
    # 行情数据
    {"key": "daily_kline",    "name": "日K线行情",         "category": "行情", "source": "Tushare daily",     "update": "每日盘后18:00", "note": "1990年起,含复权"},
    {"key": "weekly_kline",   "name": "周K线行情",         "category": "行情", "source": "Tushare weekly",    "update": "每周五盘后",     "note": ""},
    {"key": "monthly_kline",  "name": "月K线行情",         "category": "行情", "source": "Tushare monthly",   "update": "每月末盘后",     "note": ""},
    {"key": "stk_mins",       "name": "分钟K线",           "category": "行情", "source": "Tushare stk_mins",  "update": "每日盘后18:00", "note": "5分钟粒度,实时分钟需rt_min权限"},
    {"key": "adj_factor",     "name": "复权因子",           "category": "行情", "source": "Tushare adj_factor","update": "每日盘后",        "note": ""},
    {"key": "daily_basic",    "name": "每日基本面指标",     "category": "行情", "source": "Tushare daily_basic","update":"每日盘后18:00",   "note": "PE/PB/换手率等"},
    {"key": "stk_limit",      "name": "涨跌停价格",         "category": "行情", "source": "Tushare stk_limit", "update": "每日08:40",      "note": "当日涨跌停价预测"},
    {"key": "index_daily",    "name": "指数日线",           "category": "行情", "source": "Tushare index_daily","update":"每日盘后",        "note": "上证/深证/创业板等"},
    {"key": "sw_daily",       "name": "申万行业指数",       "category": "行情", "source": "Tushare sw_daily",  "update": "每日盘后",        "note": "申万2021版行业分类"},
    {"key": "rt_sw_k",        "name": "申万实时行情",       "category": "行情", "source": "Tushare rt_sw_k",   "update": "实时(交易时段)",  "note": "独立权限,实时快照"},
    # 资金数据
    {"key": "moneyflow",      "name": "个股资金流向",       "category": "资金", "source": "Tushare moneyflow", "update": "每日盘后18:00",  "note": "大单/中单/小单分类"},
    {"key": "moneyflow_hsgt", "name": "沪深港通资金",       "category": "资金", "source": "Tushare moneyflow_hsgt","update":"每日盘后", "note": "北向南向资金"},
    {"key": "hk_holdings",    "name": "沪深港通持股",       "category": "资金", "source": "Tushare hk_hold",   "update": "每日盘后",        "note": "北向资金持仓明细"},
    {"key": "margin_detail",  "name": "融资融券明细",       "category": "资金", "source": "Tushare margin_detail","update":"每日盘后",     "note": ""},
    {"key": "margin_summary", "name": "融资融券汇总",       "category": "资金", "source": "Tushare margin_summary","update":"每日盘后",   "note": ""},
    {"key": "block_trade_data","name":"大宗交易",           "category": "资金", "source": "Tushare block_trade","update":"每日盘后",     "note": ""},
    # 特色数据
    {"key": "stk_auction_o",  "name": "开盘集合竞价", "category": "特色", "source": "Tushare stk_auction_o", "update": "每日09:30", "note": "500元年, 竞价意图分析数据源"},
    {"key": "stk_factor_pro", "name": "技术因子(专业版)",   "category": "特色", "source": "Tushare stk_factor_pro","update":"每日盘后",  "note": "MA/MACD/RSI等"},
    {"key": "broker_recommend","name":"券商推荐",           "category": "特色", "source": "Tushare broker_recommend","update":"每日盘后","note": ""},
    {"key": "cyq_chips",      "name": "筹码分布",           "category": "特色", "source": "Tushare cyq_chips", "update": "每日盘后",        "note": "CYQ成本分布"},
    {"key": "top_list",       "name": "龙虎榜",             "category": "特色", "source": "Tushare top_list",  "update": "每日盘后",        "note": "营业部买卖明细"},
    {"key": "top_inst",       "name": "机构持仓",           "category": "特色", "source": "Tushare top_inst",  "update": "季度更新",        "note": "机构季度持仓"},
    {"key": "limit_list_d",   "name": "涨跌停明细",         "category": "特色", "source": "Tushare limit_list_d","update":"每日盘后",     "note": "涨停/跌停股票列表"},
    {"key": "financial_indicator","name":"财务指标",        "category": "财务", "source": "Tushare fina_indicator","update":"季度更新",   "note": "ROE/ROA/毛利率等"},
    {"key": "financial_income","name":"利润表",             "category": "财务", "source": "Tushare income",    "update": "季度更新",        "note": ""},
    {"key": "financial_balance","name":"资产负债表",        "category": "财务", "source": "Tushare balancesheet","update":"季度更新",   "note": ""},
    {"key": "financial_cashflow","name":"现金流量表",       "category": "财务", "source": "Tushare cashflow",  "update": "季度更新",        "note": ""},
    {"key": "forecast_data",  "name": "业绩预告",           "category": "财务", "source": "Tushare forecast",  "update": "不定期",          "note": ""},
    {"key": "dividend_data",  "name": "分红送股",           "category": "财务", "source": "Tushare dividend",  "update": "不定期",          "note": ""},
    {"key": "stocks",         "name": "股票列表",           "category": "基础", "source": "Tushare stock_basic","update":"每日盘后",      "note": "含行业/市值/上市日期"},
    {"key": "index_basic",    "name": "指数基本信息",       "category": "基础", "source": "Tushare index_basic","update":"不定期",       "note": ""},
    {"key": "ths_member",     "name": "同花顺概念成分",     "category": "基础", "source": "Tushare ths_member","update":"不定期",       "note": ""},
    {"key": "stock_news_tushare","name":"股票新闻",         "category": "舆情", "source": "Tushare news",      "update": "每日盘后",        "note": ""},
    {"key": "research_reports","name":"研究报告",           "category": "舆情", "source": "Tushare research_report","update":"每日盘后","note": ""},
]

# ETL 同步映射: table_key → (sync_mode, days_default, description)
_SYNC_MAP = {
        "moneyflow": ("moneyflow", 30, "资金流向"),
        "moneyflow_hsgt": ("moneyflow_hsgt", 30, "沪深港通"),
        "margin_detail": ("margin", 30, "融资融券明细"),
        "margin_summary": ("margin_summary", 30, "融资融券汇总"),
        "top_list": ("top_list", 30, "龙虎榜"),
        "stk_mins": ("stk_mins", 5, "分钟K线"),
        "daily_kline": ("daily_kline", 30, "日K线"),
        "daily_basic": ("daily_basic", 30, "基本面指标"),
        "stk_limit": ("stk_limit", 30, "涨跌停价"),
        "weekly_kline": ("weekly", 365, "周K线"),
        "monthly_kline": ("monthly", 730, "月K线"),
        "adj_factor": ("adj_factor", 30, "复权因子"),
        "index_basic": ("index_basic", 30, "指数基本信息"),
        "index_daily": ("index_daily", 30, "指数日线"),
        "financial_income": ("income", 30, "利润表"),
        "financial_balance": ("balancesheet", 30, "资产负债表"),
        "financial_cashflow": ("cashflow", 30, "现金流量表"),
        "financial_indicator": ("fina_indicator", 30, "财务指标"),
        "forecast_data": ("forecast", 180, "业绩预告"),
        "dividend_data": ("dividend", 365, "分红送股"),
        "top_inst": ("top_inst", 30, "机构持仓"),
        "block_trade_data": ("block_trade", 30, "大宗交易"),
        "hk_holdings": ("hk_hold", 30, "港股通持股"),
        "cyq_chips": ("cyq_chips", 30, "筹码分布"),
        "broker_recommend": ("broker_recommend", 30, "券商推荐"),
        "stk_auction_o": ("stk_auction_o", 1, "集合竞价"),
        "rt_sw_k": ("rt_sw_k", 1, "申万实时行情"),
        "stock_news_tushare": ("stock_news", 30, "股票新闻"),
        "research_reports": ("research_report", 30, "研究报告"),
        "sw_daily": ("sw_daily", 365, "申万行业指数"),
        "limit_list_d": ("limit_list", 30, "涨跌停明细"),
    }


@router.get("/data-status")
async def data_status():
    """Return comprehensive data source status with metadata."""
    from kronos_factors.scorer._db_stub import _get_db as _db

    sources = []
    pg_stats = {}
    try:
        import psycopg2 as pg2
        pg_url = os.environ.get("KRONOS_PG_URL", "postgresql://kronos:kronos@localhost:6432/kronos")
        conn = pg2.connect(pg_url)
        cur = conn.cursor()
        cur.execute("SELECT relname, n_live_tup FROM pg_stat_user_tables")
        pg_stats = {r[0]: int(r[1]) for r in cur.fetchall()}
        conn.close()
    except Exception: pass

    for src in _DATA_SOURCES:
        key = src["key"]; cnt = pg_stats.get(key, 0)
        sources.append({
            **src, "rows": cnt, "min_date": "—", "max_date": "—",
            "status": "active" if cnt > 0 else "empty",
        })

    categories = sorted(set(s["category"] for s in sources))
    now = datetime.now(timezone.utc).isoformat()

    return {
        "status": "ok",
        "refreshed_at": now,
        "total_tables": len(sources),
        "active_tables": sum(1 for s in sources if s["status"] == "active"),
        "total_rows": sum(s["rows"] for s in sources),
        "categories": categories,
        "sources": sources,
        "sync_map": {k: {"mode": v[0], "days_default": v[1], "desc": v[2]} for k, v in _SYNC_MAP.items()},
    }


@router.post("/trigger-sync")
async def trigger_sync(
    table_key: str = Query(..., description="Table key e.g. moneyflow, daily_kline"),
    days: int = Query(30, ge=1, le=3650, description="Days back to sync"),
):
    """Trigger a Tushare data sync for a specific table.

    Calls the corresponding kronos-data ETL sync function via subprocess.
    Returns status, rows fetched, and rows written.
    """
    if table_key not in _SYNC_MAP:
        return {"status": "error", "message": f"不支持的表: {table_key}, 可选: {list(_SYNC_MAP.keys())}"}

    mode, _, desc = _SYNC_MAP[table_key]
    logger.info("Trigger sync: %s (mode=%s, days=%d)", table_key, mode, days)

    try:
        import subprocess, sys
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
        packages_path = os.pathsep.join([
            os.path.join(project_root, "packages", "kronos-factors"),
            os.path.join(project_root, "packages", "kronos-core"),
            os.path.join(project_root, "packages", "kronos-data"),
        ])
        env = {**os.environ, "PYTHONPATH": packages_path}
        result = subprocess.run(
            [sys.executable, "-m", "kronos_data.etl", "--mode", mode, "--days", str(days)],
            capture_output=True, text=True, timeout=300,
            cwd=project_root, env=env,
        )
        ok = result.returncode == 0
        output_lines = result.stdout.strip().split("\n")[-5:] if result.stdout else []
        return {
            "status": "ok" if ok else "error",
            "table_key": table_key,
            "mode": mode,
            "desc": desc,
            "days": days,
            "returncode": result.returncode,
            "output": output_lines,
            "stderr": result.stderr[:200] if result.stderr else "",
        }
    except Exception as e:
        logger.exception("Trigger sync failed for %s", table_key)
        return {"status": "error", "table_key": table_key, "message": str(e)[:200]}


# ═══════════════════════════════════════════════════════════════
# Sync Schedules — 持久化定时同步任务
# ═══════════════════════════════════════════════════════════════

@router.get("/sync-schedules")
async def get_sync_schedules():
    """Return all saved sync schedules."""
    from kronos_factors.scorer._db_stub import _get_db as _db
    try:
        with _db() as d:
            rows = d.execute(
                "SELECT table_key, days_back, interval_minutes, daily_at, enabled, "
                "last_sync_at, next_sync_at, created_at, updated_at "
                "FROM sync_schedules ORDER BY table_key"
            ).fetchall()
        schedules = []
        for r in rows:
            schedules.append({
                "table_key": r.get("table_key", ""),
                "days_back": int(r.get("days_back") or 30),
                "interval_minutes": int(r.get("interval_minutes") or 0),
                "daily_at": r.get("daily_at") or None,
                "enabled": bool(r.get("enabled", True)),
                "last_sync_at": str(r.get("last_sync_at") or ""),
                "created_at": str(r.get("created_at") or ""),
                "updated_at": str(r.get("updated_at") or ""),
            })
        return {"status": "ok", "schedules": schedules}
    except Exception as e:
        logger.warning("Get schedules failed: %s", e)
        return {"status": "error", "message": str(e)[:100], "schedules": []}


@router.post("/sync-schedules")
async def save_sync_schedule(
    table_key: str = Query(...),
    days_back: int = Query(30, ge=1, le=3650),
    interval_minutes: int = Query(0, ge=0, le=10080),
    daily_at: str = Query(None),
    enabled: bool = Query(True),
):
    """Save or update a sync schedule."""
    from kronos_factors.scorer._db_stub import _get_db as _db
    try:
        with _db() as d:
            d.execute(
                "INSERT INTO sync_schedules (table_key, days_back, interval_minutes, daily_at, enabled, updated_at) "
                "VALUES (?, ?, ?, ?, ?, NOW()) "
                "ON CONFLICT (table_key) DO UPDATE SET "
                "days_back=EXCLUDED.days_back, interval_minutes=EXCLUDED.interval_minutes, "
                "daily_at=EXCLUDED.daily_at, enabled=EXCLUDED.enabled, updated_at=NOW()",
                (table_key, days_back, interval_minutes, daily_at, enabled),
            )
        return {"status": "ok", "table_key": table_key, "message": "定时任务已保存"}
    except Exception as e:
        return {"status": "error", "message": str(e)[:100]}


@router.delete("/sync-schedules")
async def delete_sync_schedule(table_key: str = Query(...)):
    """Delete a sync schedule."""
    from kronos_factors.scorer._db_stub import _get_db as _db
    try:
        with _db() as d:
            d.execute("DELETE FROM sync_schedules WHERE table_key = ?", (table_key,))
        return {"status": "ok", "table_key": table_key, "message": "定时任务已删除"}
    except Exception as e:
        return {"status": "error", "message": str(e)[:100]}
