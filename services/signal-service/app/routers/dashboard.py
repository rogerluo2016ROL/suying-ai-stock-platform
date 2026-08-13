"""Dashboard aggregation routes — /signal/dashboard-summary + /dashboard/* 兼容端点."""

import os, logging, asyncio
from datetime import datetime, timezone
from fastapi import Depends
from kronos_auth import require_role, get_current_user_jwt

from app._shared import (
    router, dashboard_router,
    _http_post_json, _with_signal_contract, _dashboard_row_change_pct,
    SCREENER_RUN_URL,
)
from app.routers.analysis import auction_intent

logger = logging.getLogger("signal-service.routes")


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


def _dashboard_market_sentiment_sql() -> str:
    return """
        WITH latest AS (
            SELECT trade_date
            FROM daily_kline
            WHERE close IS NOT NULL
            ORDER BY trade_date DESC
            LIMIT 1
        ),
        latest_rows AS (
            SELECT d.trade_date,
                   COALESCE(
                       d.change_pct,
                       (d.close / NULLIF(prev.close, 0) - 1) * 100
                   ) AS effective_change_pct
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
            WHERE d.trade_date = (SELECT trade_date FROM latest)
              AND d.close IS NOT NULL
        )
        SELECT AVG(effective_change_pct) as avg_chg,
               SUM(CASE WHEN effective_change_pct > 0 THEN 1 ELSE 0 END) as up_count,
               SUM(CASE WHEN effective_change_pct < 0 THEN 1 ELSE 0 END) as down_count,
               COUNT(*) as total,
               MAX(trade_date) as trade_date
        FROM latest_rows
        WHERE effective_change_pct IS NOT NULL
    """


def _dashboard_signal_movers_sql() -> str:
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
                   d.close as price,
                   COALESCE(
                       d.change_pct,
                       (d.close / NULLIF(prev.close, 0) - 1) * 100
                   ) AS change_pct,
                   d.volume,
                   d.amount
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
        SELECT code, name, price, change_pct, volume, amount
        FROM latest_rows
        WHERE change_pct IS NOT NULL
        ORDER BY ABS(change_pct) DESC
        LIMIT 10
    """


def _dashboard_auction_sql() -> str:
    return """
        WITH latest_auction AS (
            SELECT trade_date FROM stk_auction_o ORDER BY trade_date DESC LIMIT 1
        ),
        auction_data AS (
            SELECT a.trade_date, a.code, a.close as auction_price, a.open, a.high, a.low,
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
        SELECT ad.trade_date,
               ad.code,
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
    """


def _dashboard_volume_alerts_sql() -> str:
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
                   d.trade_date,
                   d.close,
                   COALESCE(
                       d.change_pct,
                       (d.close / NULLIF(prev.close, 0) - 1) * 100
                   ) AS change_pct,
                   d.volume
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
            WHERE d.trade_date = (SELECT trade_date FROM latest)
              AND d.close IS NOT NULL
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
        FROM latest_rows d
        JOIN vol_avg va ON d.code = va.code
        LEFT JOIN stocks s ON d.code = s.code
        WHERE d.change_pct IS NOT NULL
          AND d.volume > va.avg_vol * 3 AND va.avg_vol > 0
        ORDER BY d.volume / va.avg_vol DESC
        LIMIT 5
    """


def _dashboard_limit_alerts_sql() -> str:
    return """
        WITH latest_kline AS (
            SELECT trade_date
            FROM daily_kline
            WHERE close IS NOT NULL
            ORDER BY trade_date DESC
            LIMIT 1
        ),
        latest_limit AS (
            SELECT trade_date FROM stk_limit ORDER BY trade_date DESC LIMIT 1
        ),
        latest_rows AS (
            SELECT d.code,
                   d.trade_date,
                   d.close,
                   COALESCE(
                       d.change_pct,
                       (d.close / NULLIF(prev.close, 0) - 1) * 100
                   ) AS change_pct
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
            WHERE d.trade_date = (SELECT trade_date FROM latest_kline)
              AND d.close IS NOT NULL
        )
        SELECT l.code, COALESCE(s.name, l.code) as name,
               d.close as price, l.up_limit, l.down_limit, d.change_pct
        FROM stk_limit l
        JOIN latest_rows d ON l.code = d.code
        LEFT JOIN stocks s ON l.code = s.code
        WHERE l.trade_date = (SELECT trade_date FROM latest_limit)
          AND l.up_limit > 0 AND d.close > 0
          AND ( ABS(l.up_limit - d.close) / d.close < 0.03
             OR ABS(d.close - l.down_limit) / d.close < 0.03 )
        ORDER BY ABS(d.close / l.up_limit - 1) ASC
        LIMIT 5
    """


def _dashboard_pg_url() -> str:
    return os.environ.get("KRONOS_PG_URL", "postgresql://kronos:kronos@localhost:6432/kronos")


def _fetch_dashboard_auction_rows() -> list[dict]:
    import psycopg2
    import psycopg2.extras

    conn = psycopg2.connect(_dashboard_pg_url(), connect_timeout=5)
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(_dashboard_auction_sql())
            return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()


# ── dashboard_summary 数据来源采集器 ──
# 每个采集器对应原巨型函数里的一个 try/except 块，自行捕获异常并写入
# result[...]（含失败 fallback），保持与原实现完全一致的响应契约。


def _collect_market_sentiment(result: dict) -> None:
    """1. Market Sentiment (aggregate from recent K-line changes)."""
    from kronos_factors.scorer._db_stub import _get_db

    try:
        with _get_db() as d:
            sentiment_rows = d.execute(_dashboard_market_sentiment_sql()).fetchone()
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


def _collect_signal_stocks(result: dict) -> None:
    """2. Signal stocks (top movers with largest absolute change)."""
    from kronos_factors.scorer._db_stub import _get_db

    try:
        with _get_db() as d:
            movers = d.execute(_dashboard_signal_movers_sql()).fetchall()
        signal_stocks = []
        for r in movers:
            chg = _dashboard_row_change_pct(r)
            volume = float(r.get("volume") or 0)
            signal_stocks.append({
                "code": r.get("code",""), "name": r.get("name",""),
                "price": round(float(r.get("price") or 0), 2),
                "change_pct": round(chg, 2),
                "volume": int(volume),
                "signal": "Bullish" if chg > 1 else ("Bearish" if chg < -1 else "consolidation"),
                "desc": f"{'放量' if volume>1e7 else ''}{'上涨' if chg>0 else '下跌'}",
                "market": "A股",
            })
        result["signal_stocks"] = signal_stocks
    except Exception as e:
        logger.warning("Signal stocks query failed: %s", e)
        result["signal_stocks"] = []


def _collect_limit_stocks(result: dict) -> None:
    """3. Limit stocks (today's limit-up / limit-down from stk_limit)."""
    from kronos_factors.scorer._db_stub import _get_db

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


def _collect_watchlist(result: dict) -> None:
    """6. Watchlist (top 10 stocks by market cap)."""
    from kronos_factors.scorer._db_stub import _get_db

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


def _collect_alert_signals(result: dict) -> None:
    """7. Trading alert signals (异常波动 / 预警信号 with reasons)."""
    from kronos_factors.scorer._db_stub import _get_db

    try:
        with _get_db() as d:
            # 7a. Abnormal volume (> 3x 20-day average volume)
            vol_alerts = d.execute(_dashboard_volume_alerts_sql()).fetchall()

            # 7b. Near limit-up/down (price within 3% of limit)
            limit_alerts = d.execute(_dashboard_limit_alerts_sql()).fetchall()

        alert_signals = []

        for r in vol_alerts:
            vol_ratio = round(float(r.get("volume") or 1) / max(float(r.get("avg_vol") or 1), 1), 1)
            chg = round(_dashboard_row_change_pct(r), 2)
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
            chg = round(_dashboard_row_change_pct(r), 2)
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


def _collect_auction_intent(result: dict) -> None:
    """9. Auction intent (开盘竞价意图分析)."""
    try:
        auction_results = _fetch_dashboard_auction_rows()

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
        strong_bullish = [i for i in intent_list if i["score"] >= 75]
        moderate_bullish = [i for i in intent_list if 60 <= i["score"] < 75]
        neutral = [i for i in intent_list if i["level"] == "neutral"]
        moderate_bearish = [i for i in intent_list if 25 <= i["score"] < 40]
        strong_bearish = [i for i in intent_list if i["score"] < 25]
        bullish = strong_bullish + moderate_bullish
        bearish = moderate_bearish + strong_bearish

        result["auction_intent"] = {
            "trade_date": str(auction_results[0].get("trade_date", "")) if auction_results else "",
            "total_analyzed": len(intent_list),
            "strong_bullish_count": len(strong_bullish),
            "moderate_bullish_count": len(moderate_bullish),
            "bullish_count": len(bullish),
            "moderate_bearish_count": len(moderate_bearish),
            "strong_bearish_count": len(strong_bearish),
            "bearish_count": len(bearish),
            "neutral_count": len(neutral),
            "top_bullish": bullish[:5],
            "top_bearish": bearish[:5],
            "data_source": "PG stk_auction_o 表 (Tushare 集合竞价数据)",
        }
    except Exception as e:
        logger.warning("Auction intent analysis failed: %s", e)
        result["auction_intent"] = {"error": str(e)[:80]}


def _collect_market_regime_v2(result: dict) -> None:
    """P4: A股市场风向感知 (V2 八维模型)."""
    try:
        from kronos_factors.scorer.market_regime import get_market_regime_v2
        regime_v2 = get_market_regime_v2()
        result["market_regime_v2"] = regime_v2
    except Exception:
        result["market_regime_v2"] = None


def _collect_trading_calendar(result: dict) -> None:
    """P4: 交易日历."""
    try:
        import psycopg2, os
        pg_url = os.environ.get("KRONOS_PG_URL", "postgresql://kronos:kronos@localhost:6432/kronos")
        conn = psycopg2.connect(pg_url, connect_timeout=3)
        cur = conn.cursor()
        cur.execute(
            "SELECT cal_date, is_open FROM trade_cal "
            "WHERE cal_date >= CURRENT_DATE - INTERVAL '3 days' "
            "AND cal_date <= CURRENT_DATE + INTERVAL '5 days' ORDER BY cal_date")
        result["trading_calendar"] = [
            {"date": str(r[0]), "is_open": bool(r[1])} for r in cur.fetchall()
        ]
        # Next trading day
        cur.execute(
            "SELECT cal_date FROM trade_cal WHERE is_open=1 AND cal_date >= CURRENT_DATE "
            "ORDER BY cal_date LIMIT 1")
        nxt = cur.fetchone()
        result["next_trading_day"] = str(nxt[0]) if nxt else None
        conn.close()
    except Exception:
        result["trading_calendar"] = []
        result["next_trading_day"] = None


def _collect_risk_interact(result: dict) -> None:
    """P3: 互动问答风险信号."""
    try:
        import psycopg2, os
        pg_url = os.environ.get("KRONOS_PG_URL", "postgresql://kronos:kronos@localhost:6432/kronos")
        conn = psycopg2.connect(pg_url, connect_timeout=3)
        cur = conn.cursor()
        cur.execute(
            "SELECT code, COUNT(*) as cnt, MAX(pub_date) as latest FROM interact_qa "
            "WHERE pub_date >= CURRENT_DATE - INTERVAL '7 days' "
            "AND (question ~ %s OR answer ~ %s) "
            "GROUP BY code ORDER BY cnt DESC LIMIT 10",
            ("风险|质押|立案|商誉|减持|退市|亏损|ST|调查|违规|冻结|诉讼|处罚",
             "风险|质押|立案|商誉|减持|退市|亏损|ST|调查|违规|冻结|诉讼|处罚"))
        result["risk_interact"] = [
            {"code": r[0], "risk_count": r[1], "latest_date": str(r[2])}
            for r in cur.fetchall()
        ]
        conn.close()
    except Exception:
        result["risk_interact"] = []


def _collect_policy_news_monetary(result: dict) -> None:
    """P3: 政策风向标 + 新闻联播热度 + 央行货币政策 (PG直连)."""
    try:
        import psycopg2, os
        pg_url = os.environ.get("KRONOS_PG_URL", "postgresql://kronos:kronos@localhost:6432/kronos")
        conn = psycopg2.connect(pg_url, connect_timeout=3)
        cur = conn.cursor()

        # 最新政策法规
        cur.execute("SELECT pub_date, title, ptype, puborg FROM policy_law ORDER BY pub_date DESC LIMIT 5")
        result["policy_signals"] = [
            {"date": str(r[0])[:10], "title": str(r[1])[:80], "type": str(r[2]), "org": str(r[3])}
            for r in cur.fetchall()
        ]

        # 最新新闻联播标题
        cur.execute("SELECT pub_date, title FROM cctv_news ORDER BY pub_date DESC LIMIT 10")
        result["cctv_headlines"] = [
            {"date": str(r[0]), "title": str(r[1])[:80]} for r in cur.fetchall()
        ]

        # 央行货币政策立场
        cur.execute("SELECT pub_date, title, content_html FROM mp_report ORDER BY pub_date DESC LIMIT 1")
        mp_row = cur.fetchone()
        if mp_row:
            import re
            title = str(mp_row[1] or "")
            content = re.sub(r"<[^>]+>", "", str(mp_row[2] or ""))
            full_text = title + " " + content[:2000]
            if any(kw in full_text for kw in ["适度宽松", "宽松的货币政策"]):
                stance, stance_score = "适度宽松", 3
            elif any(kw in full_text for kw in ["从紧", "收紧", "紧缩"]):
                stance, stance_score = "紧缩", -5
            elif any(kw in full_text for kw in ["稳健", "灵活适度"]):
                stance, stance_score = "稳健", 0
            elif any(kw in full_text for kw in ["偏宽松", "流动性充裕"]):
                stance, stance_score = "偏宽松", 2
            else:
                stance, stance_score = "未明确", 0
            result["monetary_policy"] = {
                "report_date": str(mp_row[0]),
                "report_title": title,
                "stance": stance,
                "stance_score": stance_score,
            }
        conn.close()
    except Exception:
        result["policy_signals"] = []
        result["cctv_headlines"] = []
        result["monetary_policy"] = None


@router.get("/dashboard-summary")
async def dashboard_summary(user: dict = Depends(get_current_user_jwt)):
    """Aggregated endpoint for the Dashboard page.

    Returns market sentiment, limit stocks, signal stocks, service health,
    screenings models, and watchlist — all in a single response.
    """
    now_iso = datetime.now(timezone.utc).isoformat()
    result = {"refreshed_at": now_iso}

    # ── 纯内存段 (无 IO)：服务健康 / 选股模式 / 数据源说明 ──
    result["service_health"] = [
        {"key": key, "name": name, "port": port, "online": True}
        for key, name, port in _DASHBOARD_SERVICES
    ]

    result["screener_modes"] = [
        {"id": "leader_scalp",    "name": "秋神龙头战法-盘后", "cycle": "1-5天",  "style": "激进"},
        {"id": "leader_intraday", "name": "秋神龙头战法-盘中", "cycle": "1-2天",  "style": "激进"},
        {"id": "short",           "name": "匪爷短线多因子选股模型",       "cycle": "1-4周",  "style": "积极"},
        {"id": "long",            "name": "长线价值",         "cycle": "3-12月", "style": "稳健"},
        {"id": "all",             "name": "综合多因子",       "cycle": "1-6月",  "style": "中性"},
        {"id": "chokepoint",      "name": "大葱卡脖子选股模型",       "cycle": "1-3月",  "style": "主题"},
        {"id": "cb_floor",       "name": "匪爷可转债底价安全垫选债模型 V3.0",   "cycle": "1-4周",  "style": "稳健"},
        {"id": "cb_intraday",    "name": "匪爷可转债日内投机博弈模型", "cycle": "1-2天",  "style": "激进"},
        {"id": "cb_auction",     "name": "秋神竞价概念选债模型",       "cycle": "1-2天",  "style": "竞价"},
        {"id": "cb_auction_t0",  "name": "竞价选债 T+0 模型",          "cycle": "T+0",    "style": "竞价"},
        {"id": "cb_auction_t0_v2", "name": "竞价选债 T+0 优化版 V2",   "cycle": "T+0",    "style": "竞价优化"},
        {"id": "cb_auction_t0_v2_1", "name": "竞价选债 T+0 优化版 V2.1 稳健版", "cycle": "T+0", "style": "稳健优化"},
    ]

    result["data_sources"] = {
        "market_sentiment": "PG daily_kline 表 — 全市场涨跌幅聚合 + 14因子加权模型",
        "signal_stocks": "PG daily_kline + stocks — 今日涨跌幅绝对值 Top 10",
        "limit_stocks": "PG stk_limit 表 — 今日涨停/跌停限制数据",
        "alert_signals": "PG daily_kline + stk_limit — 实时量价异动 + 涨跌停逼近预警",
        "service_health": "各微服务 /api/v1/health 端点 (被动检测)",
        "screener_modes": "screener-service 策略引擎注册表",
        "watchlist": "PG stocks 表 — 按市值排序 Top 10",
    }

    # ── 10 个阻塞 DB 采集器并行化 (原串行阻塞事件循环) ──
    # _PgAdapter 底层是 psycopg2 ThreadedConnectionPool (execute 线程安全)；
    # 各 collector 只写 result 的不同 key、无共享可变状态 → 可安全 to_thread 并发。
    collectors = [
        _collect_market_sentiment,
        _collect_signal_stocks,
        _collect_limit_stocks,
        _collect_watchlist,
        _collect_alert_signals,
        _collect_auction_intent,
        _collect_market_regime_v2,
        _collect_trading_calendar,
        _collect_risk_interact,
        _collect_policy_news_monetary,
    ]
    await asyncio.gather(*(asyncio.to_thread(fn, result) for fn in collectors))

    result["data_sources"]["auction_intent"] = "PG stk_auction_o — 开盘集合竞价多维意图分析 (价格方向/买卖压力/竞价强度/开盘延续)"

    return _with_signal_contract(
        result,
        mode="dashboard-summary",
        data={"trade_date": result.get("market_sentiment", {}).get("trade_date")},
        fallback_reason=result.get("market_sentiment", {}).get("error"),
        source="PG daily_kline",
    )


# ═══════════════════════════════════════════════════════════════
# Dashboard Router — /api/v1/dashboard/*
# ═══════════════════════════════════════════════════════════════

@dashboard_router.get("/summary")
async def dashboard_screening_summary(user: dict = Depends(get_current_user_jwt)):
    """Multi-strategy fusion screening dashboard summary.

    Returns merged consensus picks from multiple strategies + Kronos predictions.
    """
    from kronos_factors.scorer._db_stub import _get_db

    now_iso = datetime.now(timezone.utc).isoformat()

    # Check for recent snapshots from screener-service
    picks = []
    predictions = []
    summary = {"total_picks": 0, "consensus_dual": 0, "strategies_run": 0,
               "predictions_total": 0, "predictions_up": 0, "predictions_down": 0}

    try:
        # Try to get latest screening_snapshots from PG
        import psycopg2
        pg = psycopg2.connect(
            os.environ.get("KRONOS_PG_URL", "postgresql://kronos:kronos@localhost:6432/kronos"),
            connect_timeout=3
        )
        cur = pg.cursor()
        cur.execute(
            "SELECT DISTINCT ON (code) code, name, score, grade, model_key, trade_date, time_slot "
            "FROM screening_snapshots "
            "WHERE trade_date >= CURRENT_DATE - INTERVAL '3 days' "
            "ORDER BY code, trade_date DESC, time_slot DESC "
            "LIMIT 50"
        )
        rows = cur.fetchall()
        for r in rows:
            code = str(r[0])
            # Count consensus
            cur.execute(
                "SELECT COUNT(DISTINCT model_key) FROM screening_snapshots "
                "WHERE code=%s AND trade_date >= CURRENT_DATE - INTERVAL '3 days'",
                (code,)
            )
            consensus = cur.fetchone()[0]
            picks.append({
                "code": code,
                "name": str(r[1] or ""),
                "best_score": float(r[2] or 0),
                "best_grade": str(r[3] or "B"),
                "consensus": consensus,
                "consensus_level": "🔥 双模型共识" if consensus >= 2 else "单模型",
                "sources": [str(r[4])],
            })
        pg.close()

        # Update summary
        summary["total_picks"] = len(picks)
        summary["consensus_dual"] = sum(1 for p in picks if p["consensus"] >= 2)
        summary["strategies_run"] = len(set(p["sources"][0] for p in picks if p["sources"]))
    except Exception as e:
        logger.warning("Dashboard summary PG query failed: %s", e)

    return {
        "status": "ok" if picks else "no_data",
        "date": datetime.now().strftime("%Y-%m-%d"),
        "elapsed": 0,
        "merged": picks,
        "dual_consensus": [p for p in picks if p.get("consensus", 0) >= 2],
        "predictions": predictions,
        "summary": summary,
    }


@dashboard_router.get("/auction")
async def dashboard_auction(user: dict = Depends(get_current_user_jwt)):
    """Return auction intent picks for the Dashboard auction tab.

    Wraps the auction-intent endpoint data into the format expected by the frontend.
    """
    # Reuse auction_intent logic
    result = await auction_intent(limit=30)
    picks = result.get("results", [])

    # Format for dashboard frontend
    formatted = []
    sectors = {}
    for p in picks:
        formatted.append({
            "code": p.get("code", ""),
            "name": p.get("name", ""),
            "gap_pct": round(float(p.get("score", 0)), 1),
            "score": round(float(p.get("score", 0)), 1),
            "price": round(float(p.get("price", 0)), 2) if p.get("price") else 0,
            "industry": p.get("industry", ""),
        })
        ind = p.get("industry", "其他")
        sectors[ind] = sectors.get(ind, 0) + 1

    sector_list = sorted(
        [{"name": k, "count": v} for k, v in sectors.items()],
        key=lambda x: -x["count"]
    )

    return {"picks": formatted, "sectors": sector_list}


@dashboard_router.post("/run-pipeline")
async def dashboard_run_pipeline(user: dict = Depends(require_role("admin", "internal_analyst"))):
    """Trigger the multi-strategy screening pipeline.

    Fires parallel screener runs and returns when complete.
    """
    modes_to_run = ["leader_scalp", "short", "all"]
    results = {}

    for mode in modes_to_run:
        try:
            url = f"{SCREENER_RUN_URL}?mode={mode}&top_n=20"
            data = await _http_post_json(url, None, timeout=120)
            results[mode] = {"picks": len(data.get("picks", [])), "elapsed": data.get("elapsed", 0)}
        except Exception as e:
            results[mode] = {"error": str(e)[:100]}

    return {
        "status": "ok",
        "message": f"Pipeline complete: {len(results)} strategies run",
        "results": results,
    }
