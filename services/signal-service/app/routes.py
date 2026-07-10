"""Signal API routes — real-time signal generation powered by kronos-factors."""

import os, logging, asyncio, re
from datetime import datetime, timezone
from fastapi import APIRouter, Query, HTTPException
from app.signal_store import get_store

logger = logging.getLogger("signal-service.routes")
router = APIRouter(prefix="/api/v1/signal", tags=["signal"])
store = get_store()


def _trigger_sync_via_data_service(table_key: str, days: int) -> dict | None:
    """Proxy manual sync to data-service so Tushare/PG runtime env stays single-source."""
    import json
    import urllib.parse
    import urllib.request

    base = os.environ.get("DATA_SERVICE_URL", "http://127.0.0.1:8010/api/v1/data").rstrip("/")
    if table_key == "stocks":
        req = urllib.request.Request(f"{base}/sync/stocks", method="POST")
        with urllib.request.urlopen(req, timeout=300) as resp:
            return json.loads(resp.read().decode("utf-8"))
    query = urllib.parse.urlencode({"table_key": table_key, "days": days})
    req = urllib.request.Request(f"{base}/sync/backfill?{query}", method="POST")
    with urllib.request.urlopen(req, timeout=300) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _signal_model_metadata(mode: str) -> dict:
    return {
        "name": "signal-six-dimension-v2",
        "version": "signal-v2.0",
        "provider": "signal-service",
        "inference_mode": mode,
    }


_SIGNAL_DIMENSION_WEIGHTS = {
    "kronos": 0.20, "technical": 0.20, "money_flow": 0.12,
    "fundamental": 0.15, "event_risk": 0.13, "market": 0.20,
}


def _combine_signal_dimensions(dimensions: dict) -> dict:
    """Combine only observed dimensions; never turn missing data into 50."""
    normalized = {name: dimensions.get(name) for name in _SIGNAL_DIMENSION_WEIGHTS}
    unavailable = [name for name, value in normalized.items() if value is None]
    available_weight = sum(_SIGNAL_DIMENSION_WEIGHTS[name] for name, value in normalized.items() if value is not None)
    score = None if not available_weight else round(sum(float(normalized[name]) * _SIGNAL_DIMENSION_WEIGHTS[name] for name in normalized if normalized[name] is not None) / available_weight, 1)
    return {
        "dimensions": normalized,
        "coverage": round(available_weight, 3),
        "unavailable_dimensions": unavailable,
        "result_status": "insufficient_data" if unavailable else "ok",
        "score": score,
    }


def _coerce_iso_date(value) -> str | None:
    if value is None:
        return None
    if hasattr(value, "date"):
        return value.date().isoformat()
    text = str(value)
    if not text:
        return None
    return text[:10]


def _signal_data_freshness(data=None, source: str = "daily_kline") -> dict:
    as_of = None
    try:
        if isinstance(data, dict):
            as_of = _coerce_iso_date(data.get("trade_date") or data.get("as_of") or data.get("date"))
        elif data is not None and len(data) > 0:
            if hasattr(data, "columns") and "trade_date" in data.columns:
                as_of = _coerce_iso_date(data["trade_date"].iloc[-1])
            elif hasattr(data, "index") and len(data.index) > 0:
                as_of = _coerce_iso_date(data.index[-1])
            elif isinstance(data, (list, tuple)) and isinstance(data[-1], dict):
                as_of = _coerce_iso_date(data[-1].get("trade_date") or data[-1].get("as_of") or data[-1].get("date"))
    except Exception:
        as_of = None

    if not as_of:
        return {
            "status": "unknown",
            "as_of": None,
            "source": source,
            "quality_score": 0,
        }

    try:
        as_date = datetime.fromisoformat(as_of).date()
        lag_days = max(0, (datetime.now(timezone.utc).date() - as_date).days)
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


def _with_signal_contract(
    payload: dict,
    *,
    mode: str,
    data=None,
    fallback_reason: str | None = None,
    source: str = "daily_kline",
) -> dict:
    enriched = dict(payload)
    enriched["model_metadata"] = _signal_model_metadata(mode)
    enriched["data_freshness"] = _signal_data_freshness(data, source)
    enriched["fallback_reason"] = fallback_reason
    return enriched


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


def _dashboard_row_change_pct(row: dict) -> float:
    value = row.get("change_pct")
    if value is None:
        value = row.get("pct_chg")
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


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

    # ── 2. Signal stocks (top movers with largest absolute change) ──
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

    result["data_sources"]["auction_intent"] = "PG stk_auction_o — 开盘集合竞价多维意图分析 (价格方向/买卖压力/竞价强度/开盘延续)"

    # ── P4: A股市场风向感知 (V2 八维模型) ──
    try:
        from kronos_factors.scorer.market_regime import get_market_regime_v2
        regime_v2 = get_market_regime_v2()
        result["market_regime_v2"] = regime_v2
    except Exception:
        result["market_regime_v2"] = None

    # ── P4: 交易日历 ──
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

    # ── P3: 互动问答风险信号 ──
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

    # ── P3: 政策风向标 + 新闻联播热度 + 央行货币政策 (PG直连) ──
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

    return _with_signal_contract(
        result,
        mode="dashboard-summary",
        data={"trade_date": result.get("market_sentiment", {}).get("trade_date")},
        fallback_reason=result.get("market_sentiment", {}).get("error"),
        source="PG daily_kline",
    )


# ═══════════════════════════════════════════════════════════════
# P4: 跨模型超级信号 (screener + signal + diagnosis 融合)
# ═══════════════════════════════════════════════════════════════

@router.get("/super-signal/{code}")
async def super_signal(code: str):
    """P4: 跨模型融合, 综合 screener 排名 + 信号评分 + 诊断评分.

    仅在 screener 选出的前 50 只股票上计算, 不增加全市场扫描成本.
    """
    import urllib.request, json, os

    results = {"code": code, "super_score": 50.0, "components": {}}

    # 1. Signal score (local)
    try:
        sig = await analyze_signal(code)
        sig_score = sig["signal"]["score"]
        results["components"]["signal"] = {"score": sig_score, "weight": 0.40}
    except Exception:
        sig_score = 50.0
        results["components"]["signal"] = {"score": 50, "weight": 0.40, "error": "unavailable"}

    # 2. Diagnosis score (HTTP call)
    try:
        diag_url = "http://localhost:8009/api/v1/diagnosis/analyze"
        req = urllib.request.Request(diag_url,
            data=json.dumps({"code": code}).encode(),
            headers={"Content-Type": "application/json"})
        diag = json.loads(urllib.request.urlopen(req, timeout=5).read())
        diag_score = diag.get("overall_score", 50)
        results["components"]["diagnosis"] = {"score": diag_score, "weight": 0.35}
    except Exception:
        diag_score = 50.0
        results["components"]["diagnosis"] = {"score": 50, "weight": 0.35, "error": "unavailable"}

    # 3. Screener rank (percentile)
    try:
        scr_url = "http://localhost:8001/api/v1/screener/run"
        req = urllib.request.Request(scr_url,
            data=json.dumps({"mode": "short", "top_n": 50}).encode(),
            headers={"Content-Type": "application/json"})
        scr = json.loads(urllib.request.urlopen(req, timeout=10).read())
        picks = scr.get("picks", [])
        rank = next((i+1 for i, p in enumerate(picks) if p.get("code") == code), 51)
        rank_score = max(10, 100 - rank * 2) if rank <= 50 else 50
        results["components"]["screener"] = {"rank": rank, "score": rank_score, "weight": 0.25}
    except Exception:
        rank_score = 50.0
        results["components"]["screener"] = {"score": 50, "weight": 0.25, "error": "unavailable"}

    # Super score
    results["super_score"] = round(
        sig_score * 0.40 + diag_score * 0.35 + rank_score * 0.25, 1
    )
    results["recommendation"] = (
        "STRONG_BUY" if results["super_score"] >= 80 else
        "BUY" if results["super_score"] >= 60 else
        "HOLD" if results["super_score"] >= 40 else
        "REDUCE" if results["super_score"] >= 20 else "SELL"
    )

    return results


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
async def analyze_signal(code: str):
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
        pass

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
        pass

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
            "fundamental":       {"score": round(fundamental_score, 1), "weight": 0.15},
            "event_risk":        {"score": round(event_risk_score, 1), "weight": 0.13},
            "market_adapt":      {"score": round(market_adapt, 1), "weight": 0.20},
            "rule_match":        {"score": 50, "weight": 0.00, "note": "deprecated-merged-into-event-risk"},
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
    {"key": "weekly_kline",   "name": "周K线行情",         "category": "行情", "source": "Tushare weekly",    "update": "每交易日盘后16:00", "note": "节前最后交易日即补本周周K"},
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
    {"key": "research_reports_tushare","name":"研究报告",   "category": "舆情", "source": "Tushare research_report","update":"每日盘后","note": ""},
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
        "stk_factor_pro": ("stk_factor_pro", 7, "技术因子"),
        "stocks": ("stocks", 30, "股票列表"),
        "rt_sw_k": ("rt_sw_k", 1, "申万实时行情"),
        "stock_news_tushare": ("stock_news", 30, "股票新闻"),
        "research_reports_tushare": ("research_report", 30, "研究报告"),
        "sw_daily": ("sw_daily", 365, "申万行业指数"),
        "limit_list_d": ("limit_list", 30, "涨跌停明细"),
    }


DATA_STATUS_DATE_COLUMNS = {
    "daily_kline": ("trade_date",),
    "weekly_kline": ("trade_date",),
    "monthly_kline": ("trade_date",),
    "stk_mins": ("trade_time",),
    "stk_auction_o": ("trade_date",),
    "moneyflow": ("trade_date",),
    "stk_limit": ("trade_date",),
    "daily_basic": ("trade_date",),
    "adj_factor": ("trade_date",),
    "index_daily": ("trade_date",),
    "sw_daily": ("trade_date",),
    "top_list": ("trade_date",),
    "top_inst": ("trade_date",),
    "margin_detail": ("trade_date",),
    "margin_summary": ("trade_date",),
    "moneyflow_hsgt": ("trade_date",),
    "hk_holdings": ("trade_date",),
    "block_trade_data": ("trade_date",),
    "limit_list_d": ("trade_date",),
    "cyq_chips": ("trade_date",),
    "rt_sw_k": ("trade_date",),
    "financial_indicator": ("end_date",),
    "financial_income": ("end_date",),
    "financial_balance": ("end_date",),
    "financial_cashflow": ("end_date",),
    "forecast_data": ("end_date",),
    "dividend_data": ("ex_date",),
    "broker_recommend": ("month",),
    "stk_factor_pro": ("trade_date",),
    "stock_news_tushare": ("pub_time",),
    "research_reports_tushare": ("pub_date",),
}

DATA_STATUS_FALLBACK_DATE_COLUMNS = (
    "trade_date",
    "end_date",
    "ann_date",
    "pub_date",
    "pub_time",
    "month",
    "trade_time",
    "f_ann_date",
    "datetime",
    "report_date",
    "updated_at",
)


def _default_sync_schedules() -> list[dict]:
    """Build executable default schedules from the supported sync map."""
    schedules = []
    for table_key, (mode, days_default, desc) in _SYNC_MAP.items():
        if mode in ("stk_auction_o",):
            interval_minutes = 0
            daily_at = "09:30"
            next_sync_at = "09:30"
        elif mode in ("rt_sw_k",):
            interval_minutes = 5
            daily_at = None
            next_sync_at = "交易时段每 5 分钟"
        elif mode in ("stk_factor_pro",):
            interval_minutes = 0
            daily_at = "16:05"
            next_sync_at = "16:05"
        elif mode in ("stocks",):
            interval_minutes = 0
            daily_at = "02:00"
            next_sync_at = "02:00"
        elif mode in ("stk_mins",):
            interval_minutes = 0
            daily_at = "18:00"
            next_sync_at = "18:00"
        elif mode in ("stock_news",):
            interval_minutes = 30
            daily_at = None
            next_sync_at = "交易时段每 30 分钟"
        else:
            interval_minutes = 0
            daily_at = "18:00"
            next_sync_at = "18:00"
        schedules.append({
            "table_key": table_key,
            "mode": mode,
            "desc": desc,
            "days_back": days_default,
            "interval_minutes": interval_minutes,
            "daily_at": daily_at,
            "enabled": True,
            "last_sync_at": "",
            "next_sync_at": next_sync_at,
            "created_at": "",
            "updated_at": "",
            "source": "default_sync_map",
        })
    return schedules


@router.get("/data-status")
async def data_status():
    """Return comprehensive data source status with metadata."""
    from kronos_factors.scorer._db_stub import _get_db as _db

    sources = []
    pg_stats = {}; date_cache = {}
    try:
        import psycopg2 as pg2
        pg_url = os.environ.get("KRONOS_PG_URL", "postgresql://kronos:kronos@localhost:6432/kronos")
        conn = pg2.connect(pg_url)
        conn.autocommit = True
        cur = conn.cursor()

        # Get estimated row counts. Do not run ANALYZE here: this endpoint is
        # page-facing and must stay lightweight on 100M+ row databases.
        cur.execute("SELECT relname, n_live_tup FROM pg_stat_user_tables")
        pg_stats = {r[0]: int(r[1]) for r in cur.fetchall()}

        # MIN/MAX with specific date columns first, then fallback
        # P1-7 (audit): use psycopg2.sql.Identifier for col/key interpolation
        # instead of f-string with double-quoted identifiers. col/key come from
        # _DATE_COL_MAP/_DATA_SOURCES constants today (not user input), but
        # Identifier is the defense-in-depth pattern (see pg_writer.py:228) so a
        # future refactor that makes these dynamic can't become an injection.
        from psycopg2.sql import SQL, Identifier
        all_table_keys = {s["key"] for s in _DATA_SOURCES}
        for key in all_table_keys:
            cols_to_try = list(DATA_STATUS_DATE_COLUMNS.get(key, DATA_STATUS_FALLBACK_DATE_COLUMNS))
            for col in cols_to_try:
                try:
                    cur.execute(
                        SQL('SELECT MIN({}), MAX({}) FROM {} WHERE {} IS NOT NULL').format(
                            Identifier(col), Identifier(col), Identifier(key), Identifier(col)
                        )
                    )
                    row = cur.fetchone()
                    if row and row[0] is not None:
                        mn, mx = str(row[0]), str(row[1])
                        if len(mn) == 8 and mn.isdigit(): mn = f"{mn[:4]}-{mn[4:6]}-{mn[6:8]}"
                        if len(mx) == 8 and mx.isdigit(): mx = f"{mx[:4]}-{mx[4:6]}-{mx[6:8]}"
                        date_cache[key] = (mn[:19], mx[:19])
                        # Fallback COUNT if stats show 0
                        if pg_stats.get(key, 0) == 0:
                            try:
                                cur.execute(SQL("SELECT COUNT(*) FROM {}").format(Identifier(key)))
                                pg_stats[key] = int(cur.fetchone()[0])
                            except Exception:
                                pass
                        break
                except Exception:
                    continue
        conn.close()
    except Exception as e:
        logger.warning("Data status query failed: %s", e)

    for src in _DATA_SOURCES:
        key = src["key"]; cnt = pg_stats.get(key, 0)
        mn, mx = date_cache.get(key, ("—", "—"))
        sources.append({
            **src, "rows": cnt, "min_date": mn, "max_date": mx,
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
        proxied = _trigger_sync_via_data_service(table_key, days)
        if proxied is not None:
            return {
                **proxied,
                "table_key": table_key,
                "mode": mode,
                "desc": desc,
                "days": days,
                "source": "data-service",
            }
    except Exception as e:
        logger.warning("Data-service manual sync proxy failed for %s, fallback to subprocess: %s", table_key, e)

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
                "next_sync_at": str(r.get("next_sync_at") or ""),
                "created_at": str(r.get("created_at") or ""),
                "updated_at": str(r.get("updated_at") or ""),
                "source": "sync_schedules",
            })
        if not schedules:
            schedules = _default_sync_schedules()
        return {"status": "ok", "schedules": schedules}
    except Exception as e:
        logger.warning("Get schedules failed: %s", e)
        return {
            "status": "ok",
            "message": f"sync_schedules 未初始化，展示默认调度: {str(e)[:80]}",
            "schedules": _default_sync_schedules(),
        }


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


# ═══════════════════════════════════════════════════════════════
# Live Signal Endpoint — real-time signal stream
# ═══════════════════════════════════════════════════════════════

@router.get("/live")
async def signal_live(session: str = Query("intra", description="intra | post | auction")):
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


# ═══════════════════════════════════════════════════════════════
# Dashboard Router — /api/v1/dashboard/*
# ═══════════════════════════════════════════════════════════════

dashboard_router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])


@dashboard_router.get("/summary")
async def dashboard_screening_summary():
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
async def dashboard_auction():
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
async def dashboard_run_pipeline():
    """Trigger the multi-strategy screening pipeline.

    Fires parallel screener runs and returns when complete.
    """
    import urllib.request

    modes_to_run = ["leader_scalp", "short", "all"]
    results = {}

    for mode in modes_to_run:
        try:
            url = f"http://localhost:8001/api/v1/screener/run?mode={mode}&top_n=20"
            req = urllib.request.Request(url, method="POST")
            resp = urllib.request.urlopen(req, timeout=120)
            data = json.loads(resp.read())
            results[mode] = {"picks": len(data.get("picks", [])), "elapsed": data.get("elapsed", 0)}
        except Exception as e:
            results[mode] = {"error": str(e)[:100]}

    return {
        "status": "ok",
        "message": f"Pipeline complete: {len(results)} strategies run",
        "results": results,
    }


# ═══════════════════════════════════════════════════════════════
# Data Router — /api/v1/data/*
# ═══════════════════════════════════════════════════════════════

data_router = APIRouter(prefix="/api/v1/data", tags=["data"])


@data_router.get("/status")
async def data_status_endpoint():
    """Alias for /signal/data-status — serves the DataUpdate page."""
    return await data_status()


@data_router.post("/sync/{sync_type}")
async def data_sync(sync_type: str, days: int = Query(30, ge=1, le=3650),
                    table_key: str = Query(None)):
    """Trigger data sync. Maps sync_type to table_key for signal-service compatibility.

    Frontend DataUpdate page calls /api/v1/data/sync/{type}
    """
    # Map front-end sync types to table keys
    TYPE_TO_KEY = {
        "rt_min": "stk_mins",
        "stocks": "stocks",
        "post_market": table_key or "daily_kline",
    }

    mapped_key = table_key or TYPE_TO_KEY.get(sync_type, sync_type)

    return await trigger_sync(table_key=mapped_key, days=days)


@data_router.post("/status")
async def data_save_schedule(
    table_key: str = Query(...),
    days_back: int = Query(30, ge=1, le=3650),
    interval_minutes: int = Query(0, ge=0, le=10080),
    daily_at: str = Query(None),
    enabled: bool = Query(True),
):
    """Save sync schedule (alias for /signal/sync-schedules POST)."""
    return await save_sync_schedule(
        table_key=table_key, days_back=days_back,
        interval_minutes=interval_minutes, daily_at=daily_at, enabled=enabled
    )


@data_router.delete("/status")
async def data_delete_schedule(table_key: str = Query(...)):
    """Delete sync schedule (alias for /signal/sync-schedules DELETE)."""
    return await delete_sync_schedule(table_key=table_key)
