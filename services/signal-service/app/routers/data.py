"""Data status & sync-schedule routes — 数据状态监控与定时同步任务管理."""

import os, logging
from datetime import datetime, timezone
from fastapi import Depends, Query, Response
from kronos_auth import require_role, get_current_user_jwt

from app._shared import router, data_router

logger = logging.getLogger("signal-service.routes")


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
async def data_status(user: dict = Depends(get_current_user_jwt)):
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


# ═══════════════════════════════════════════════════════════════
# Sync Schedules — 持久化定时同步任务
# ═══════════════════════════════════════════════════════════════

@router.get("/sync-schedules")
async def get_sync_schedules(user: dict = Depends(get_current_user_jwt)):
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
    user: dict = Depends(require_role("admin", "internal_analyst")),
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
async def delete_sync_schedule(table_key: str = Query(...),
                               user: dict = Depends(require_role("admin", "internal_analyst"))):
    """Delete a sync schedule."""
    from kronos_factors.scorer._db_stub import _get_db as _db
    try:
        with _db() as d:
            d.execute("DELETE FROM sync_schedules WHERE table_key = ?", (table_key,))
        return {"status": "ok", "table_key": table_key, "message": "定时任务已删除"}
    except Exception as e:
        return {"status": "error", "message": str(e)[:100]}


# ═══════════════════════════════════════════════════════════════
# Data Router — /api/v1/data/*
# ═══════════════════════════════════════════════════════════════

@data_router.get("/status")
async def data_status_endpoint(response: Response, user: dict = Depends(get_current_user_jwt)):
    """Alias for /signal/data-status — serves the DataUpdate page."""
    response.headers["Deprecation"] = "true"
    return await data_status()


@data_router.post("/sync/{sync_type}")
async def data_sync(sync_type: str, days: int = Query(30, ge=1, le=3650),
                    table_key: str = Query(None), response: Response = None,
                    user: dict = Depends(require_role("admin", "internal_analyst"))):
    """Trigger data sync. Maps sync_type to table_key for signal-service compatibility.

    Frontend DataUpdate page calls /api/v1/data/sync/{type}
    """
    from app.routes import trigger_sync

    # Map front-end sync types to table keys
    TYPE_TO_KEY = {
        "rt_min": "stk_mins",
        "stocks": "stocks",
        "post_market": table_key or "daily_kline",
    }

    mapped_key = table_key or TYPE_TO_KEY.get(sync_type, sync_type)

    if response is not None:
        response.headers["Deprecation"] = "true"
    return await trigger_sync(table_key=mapped_key, days=days)


@data_router.post("/status")
async def data_save_schedule(
    table_key: str = Query(...),
    days_back: int = Query(30, ge=1, le=3650),
    interval_minutes: int = Query(0, ge=0, le=10080),
    daily_at: str = Query(None),
    enabled: bool = Query(True),
    user: dict = Depends(require_role("admin", "internal_analyst")),
):
    """Save sync schedule (alias for /signal/sync-schedules POST)."""
    return await save_sync_schedule(
        table_key=table_key, days_back=days_back,
        interval_minutes=interval_minutes, daily_at=daily_at, enabled=enabled
    )


@data_router.delete("/status")
async def data_delete_schedule(table_key: str = Query(...),
                               user: dict = Depends(require_role("admin", "internal_analyst"))):
    """Delete sync schedule (alias for /signal/sync-schedules DELETE)."""
    return await delete_sync_schedule(table_key=table_key)
