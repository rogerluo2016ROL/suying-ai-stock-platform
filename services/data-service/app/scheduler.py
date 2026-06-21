"""内置 asyncio 定时任务调度 — 零外部依赖."""

import asyncio, logging, os, sys, time
from datetime import datetime, date
from psycopg2.sql import SQL, Identifier
from app.sync.rt_min import collect_rt_min
from app.sync.tushare import sync_post_market_core, sync_post_market_ext
from app.sync.pg_writer import refresh_materialized_views
from app.sync.stocks import sync_stock_list, sync_stocks_incremental
from app.sync.cb_sync import sync_ths_daily, sync_cb_price_chg_all, sync_ths_concept_map
from app.sync.announcements import sync_announcements
from app.sync.fina_mainbz import sync_fina_mainbz
from app.sync.fina_audit import sync_fina_audit
from app.sync.stock_profiles import sync_stock_profiles
from app.sync.interact import sync_interact_qa
from app.sync.policy_law import sync_policy_law
from app.sync.mp_report import sync_mp_report
from app.sync.cctv_news import sync_cctv_news

# 从 kronos-data/etl.py 导入已有 sync 函数 (零重复代码)
_PROJ_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
_KRONOS_DATA = os.path.join(_PROJ_ROOT, "packages", "kronos-data")
if _KRONOS_DATA not in sys.path:
    sys.path.insert(0, _KRONOS_DATA)
from kronos_data.etl import (
    sync_cb_daily, sync_cb_factor, sync_cb_call, sync_index_daily,
    sync_moneyflow, sync_daily_basic, sync_stk_limit, sync_daily_kline,
    sync_limit_list_d, sync_moneyflow_hsgt, sync_sw_daily, sync_stk_mins,
    sync_stk_auction_o,
    # ── P0 新接入: 风控 + 财务 + 资讯 + 行情 (24 个函数, 代码已实现) ──
    sync_hk_hold, sync_margin, sync_margin_summary, sync_top_list, sync_top_inst,
    sync_block_trade_data, sync_stk_holdertrade, sync_stk_holdernumber,
    sync_pledge_detail, sync_repurchase, sync_share_float, sync_cyq_chips,
    sync_broker_recommend, sync_weekly_kline, sync_monthly_kline, sync_adj_factor,
    sync_index_basic, sync_income, sync_balancesheet, sync_cashflow,
    sync_financial_indicator, sync_forecast_data, sync_dividend_data,
    sync_research_report, sync_stock_news,
    # ── P3 实时行情 ──
    sync_rt_k, sync_rt_sw_k,
)

logger = logging.getLogger("data-service.scheduler")

_job_status: dict = {}
_jobs: list[dict] = []
_running = False

# ═══════════════════════════════════════════════════════════════
# 数据治理: 分频监控表配置 (L0-L4 分层)
# ═══════════════════════════════════════════════════════════════

# PG 连接 (复用 pg_writer 配置)
_PG_URL = os.environ.get("KRONOS_PG_URL", "postgresql://kronos:kronos@localhost:6432/kronos")
_DATA_INTEGRITY_LOOKBACK = int(os.environ.get("DATA_INTEGRITY_LOOKBACK", "30"))

# 表 → 监控配置: date_col=日期列, lookback=检查窗口天数, freq=频率标签, gap_threshold=允许的最大滞后天数
MONITORED_TABLES: dict[str, dict] = {
    # ── L2 盘后级 (每日应有数据) ──
    "daily_kline":    {"date_col": "trade_date", "lookback": 30, "freq": "L2-daily",  "gap_threshold": 1},
    "moneyflow":      {"date_col": "trade_date", "lookback": 30, "freq": "L2-daily",  "gap_threshold": 1},
    "stk_limit":      {"date_col": "trade_date", "lookback": 30, "freq": "L2-daily",  "gap_threshold": 1},
    "daily_basic":    {"date_col": "trade_date", "lookback": 30, "freq": "L2-daily",  "gap_threshold": 1},
    "ths_daily":      {"date_col": "trade_date", "lookback": 30, "freq": "L2-daily",  "gap_threshold": 1},
    "sw_daily":       {"date_col": "trade_date", "lookback": 60, "freq": "L2-daily",  "gap_threshold": 2},
    "index_daily":    {"date_col": "trade_date", "lookback": 30, "freq": "L2-daily",  "gap_threshold": 1},
    "stk_factor_pro": {"date_col": "trade_date", "lookback": 60, "freq": "L2-daily",  "gap_threshold": 2},
    "limit_list_d":   {"date_col": "trade_date", "lookback": 30, "freq": "L1-intra",  "gap_threshold": 1},
    # ── L3 周级 (每周应有数据) ──
    "moneyflow_hsgt": {"date_col": "trade_date", "lookback": 14, "freq": "L3-weekly", "gap_threshold": 5},
    "stocks":         {"date_col": "updated_at",  "lookback": 14, "freq": "L3-weekly", "gap_threshold": 7},
    # ── L0 实时级 (交易日每分钟应有数据) ──
    "stk_mins":       {"date_col": "trade_time",  "lookback": 10, "freq": "L0-realtime","gap_threshold": 1},
    "rt_k":           {"date_col": "trade_date",  "lookback": 5,  "freq": "L0-realtime","gap_threshold": 1},
    "rt_sw_k":        {"date_col": "trade_date",  "lookback": 5,  "freq": "L0-realtime","gap_threshold": 1},
    # ── 基础日历 (每周一更新, 1天缺口即触发) ──
    "trade_cal":      {"date_col": "cal_date",    "lookback": 90, "freq": "L3-weekly", "gap_threshold": 1},
    # ── P0 新接入: L2 风控数据 (每日盘后应有数据) ──
    "hk_holdings":              {"date_col": "trade_date", "lookback": 14, "freq": "L2-daily",  "gap_threshold": 2},
    "margin_detail":            {"date_col": "trade_date", "lookback": 14, "freq": "L2-daily",  "gap_threshold": 2},
    "margin_summary":           {"date_col": "trade_date", "lookback": 14, "freq": "L2-daily",  "gap_threshold": 1},
    "top_list":                 {"date_col": "trade_date", "lookback": 14, "freq": "L2-daily",  "gap_threshold": 1},
    "top_inst":                 {"date_col": "trade_date", "lookback": 14, "freq": "L2-daily",  "gap_threshold": 1},
    "block_trade_data":         {"date_col": "trade_date", "lookback": 14, "freq": "L2-daily",  "gap_threshold": 2},
    "stk_holdertrade":          {"date_col": "ann_date",   "lookback": 30, "freq": "L2-daily",  "gap_threshold": 3},
    "pledge_detail":            {"date_col": "end_date",   "lookback": 30, "freq": "L2-daily",  "gap_threshold": 3},
    "share_float":              {"date_col": "float_date", "lookback": 30, "freq": "L3-weekly", "gap_threshold": 7},
    "cyq_chips":                {"date_col": "trade_date", "lookback": 14, "freq": "L2-daily",  "gap_threshold": 2},
    "forecast_data":            {"date_col": "end_date",   "lookback": 30, "freq": "L2-daily",  "gap_threshold": 3},
    "dividend_data":            {"date_col": "ex_date",    "lookback": 30, "freq": "L3-weekly", "gap_threshold": 7},
    "adj_factor":               {"date_col": "trade_date", "lookback": 14, "freq": "L2-daily",  "gap_threshold": 1},
    # ── P0 新接入: L2 财务数据 (财报季日更, 普通季周更) ──
    "financial_indicator":      {"date_col": "end_date",   "lookback": 120,"freq": "L3-weekly", "gap_threshold": 14},
    "financial_income":         {"date_col": "end_date",   "lookback": 120,"freq": "L3-weekly", "gap_threshold": 14},
    "financial_balance":        {"date_col": "end_date",   "lookback": 120,"freq": "L3-weekly", "gap_threshold": 14},
    "financial_cashflow":       {"date_col": "end_date",   "lookback": 120,"freq": "L3-weekly", "gap_threshold": 14},
    "fina_mainbz":              {"date_col": "end_date",   "lookback": 120,"freq": "L3-weekly", "gap_threshold": 14},
    "fina_audit":               {"date_col": "ann_date",   "lookback": 120,"freq": "L3-weekly", "gap_threshold": 14},
    # ── P0 新接入: L2 资讯数据 ──
    "research_reports_tushare": {"date_col": "pub_date",   "lookback": 7,  "freq": "L2-daily",  "gap_threshold": 2},
    "stock_news_tushare":       {"date_col": "pub_time",   "lookback": 7,  "freq": "L1-intra",  "gap_threshold": 1},
    "announcements":            {"date_col": "ann_date",   "lookback": 7,  "freq": "L2-daily",  "gap_threshold": 2},
    # ── P0 新接入: L3 周/月级行情 ──
    "weekly_kline":             {"date_col": "trade_date", "lookback": 14, "freq": "L3-weekly", "gap_threshold": 7},
    "monthly_kline":            {"date_col": "trade_date", "lookback": 60, "freq": "L3-monthly","gap_threshold": 31},
    "stk_holdernumber":         {"date_col": "end_date",   "lookback": 90, "freq": "L3-weekly", "gap_threshold": 14},
    "repurchase":               {"date_col": "ann_date",   "lookback": 30, "freq": "L3-weekly", "gap_threshold": 7},
    "index_basic":              {"date_col": "updated_at", "lookback": 30, "freq": "L3-weekly", "gap_threshold": 7},
    "broker_recommend":         {"date_col": "month",      "lookback": 90, "freq": "L3-monthly","gap_threshold": 31},
    "stock_profiles":           {"date_col": "updated_at", "lookback": 14, "freq": "L3-weekly", "gap_threshold": 7},
    "interact_qa":              {"date_col": "pub_date",   "lookback": 7,  "freq": "L2-daily",  "gap_threshold": 2},
    "policy_law":               {"date_col": "pub_date",   "lookback": 7,  "freq": "L2-daily",  "gap_threshold": 2},
    "mp_report":                {"date_col": "pub_date",   "lookback": 120,"freq": "L3-monthly","gap_threshold": 35},
    "cctv_news":                {"date_col": "pub_date",   "lookback": 7,  "freq": "L2-daily",  "gap_threshold": 2},
}

# 表 → 回补函数 (来自 kronos_data.etl, 接受 days_back=int 参数)
_BACKFILL_MAP: dict[str, callable] = {
    "daily_kline":    sync_daily_kline,
    "moneyflow":      sync_moneyflow,
    "stk_limit":      sync_stk_limit,
    "daily_basic":    sync_daily_basic,
    "limit_list_d":   sync_limit_list_d,
    "moneyflow_hsgt": sync_moneyflow_hsgt,
    "sw_daily":       sync_sw_daily,
    "stk_mins":       sync_stk_mins,
    "rt_k":           sync_rt_k,
    "rt_sw_k":        sync_rt_sw_k,
    # ── P0 风控数据回补 ──
    "hk_holdings":    sync_hk_hold,
    "margin_detail":  sync_margin,
    "margin_summary": sync_margin_summary,
    "top_list":       sync_top_list,
    "top_inst":       sync_top_inst,
    "block_trade_data": sync_block_trade_data,
    "stk_holdertrade":  sync_stk_holdertrade,
    "stk_holdernumber": sync_stk_holdernumber,
    "pledge_detail":    sync_pledge_detail,
    "repurchase":       sync_repurchase,
    "share_float":      sync_share_float,
    "cyq_chips":        sync_cyq_chips,
    "forecast_data":    sync_forecast_data,
    "dividend_data":    sync_dividend_data,
    "adj_factor":       sync_adj_factor,
    # ── P0 财务数据回补 ──
    "financial_indicator": sync_financial_indicator,
    "financial_income":    sync_income,
    "financial_balance":   sync_balancesheet,
    "financial_cashflow":  sync_cashflow,
    # ── P0 资讯数据回补 ──
    "research_reports_tushare": sync_research_report,
    "stock_news_tushare":       sync_stock_news,
    "announcements":            sync_announcements,
    "fina_mainbz":              sync_fina_mainbz,
    "fina_audit":               sync_fina_audit,
    "stock_profiles":           sync_stock_profiles,
    "interact_qa":              sync_interact_qa,
    "policy_law":               sync_policy_law,
    "mp_report":                sync_mp_report,
    "cctv_news":                sync_cctv_news,
    # ── P0 周/月线回补 ──
    "weekly_kline":     sync_weekly_kline,
    "monthly_kline":    sync_monthly_kline,
    "index_basic":      sync_index_basic,
    "broker_recommend": sync_broker_recommend,
}


# ═══════════════════════════════════════════════════════════════
# 数据完整性检测 (L4 历史回补)
# ═══════════════════════════════════════════════════════════════

def _parse_date(val) -> date | None:
    """将 DB 返回值统一解析为 date 对象."""
    if val is None:
        return None
    if isinstance(val, date):
        return val
    if isinstance(val, datetime):
        return val.date()
    s = str(val)[:10]
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        return None


def check_table_latest_date(table: str, date_col: str = "trade_date") -> date | None:
    """查询 PG (主) 或 SQLite (fallback) 中表的最新日期.

    Args:
        table: 表名
        date_col: 日期列名 (trade_date / trade_time / updated_at)

    Returns:
        最新日期 date 对象, 无数据返回 None
    """
    # 主路径: PG
    try:
        import psycopg2
        conn = psycopg2.connect(_PG_URL)
        conn.autocommit = True
        cur = conn.cursor()
        # 使用 quote_ident 防止 SQL 注入 (table/column 不可参数化)
        cur.execute(SQL("SELECT MAX({})".format(Identifier(date_col))).format(Identifier(table)))
        row = cur.fetchone()
        conn.close()
        parsed = _parse_date(row[0]) if row else None
        if parsed:
            return parsed
    except Exception:
        logger.debug("PG check %s.%s failed, trying SQLite", table, date_col)

    # Fallback: SQLite
    try:
        from app.config import DB_PATH
        import sqlite3
        db = sqlite3.connect(DB_PATH)
        row = db.execute(f"SELECT MAX({date_col}) FROM {table}").fetchone()
        db.close()
        parsed = _parse_date(row[0]) if row else None
        if parsed:
            return parsed
    except Exception:
        logger.debug("SQLite check %s.%s also failed", table, date_col)

    return None


def _count_trading_days(from_date: date, to_date: date) -> int:
    """使用 trade_cal 表计算两个日期之间的真实交易日数。

    若 trade_cal 不可用, fallback 到自然日数 (保守估计)。
    """
    try:
        import psycopg2
        conn = psycopg2.connect(_PG_URL)
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM trade_cal WHERE cal_date > %s AND cal_date <= %s AND is_open=1",
            (from_date.isoformat(), to_date.isoformat())
        )
        cnt = cur.fetchone()[0]
        conn.close()
        return cnt if cnt else (to_date - from_date).days  # fallback
    except Exception:
        return (to_date - from_date).days


def detect_data_gaps(lookback_days: int = None) -> dict:
    """扫描所有监控表, 检测数据缺口 (使用真实交易日历)。

    对每张表查询最新日期, 通过 trade_cal 计算交易日缺口。
    超过 gap_threshold 个交易日即标记为缺口。

    Args:
        lookback_days: 覆盖 MONITORED_TABLES 中的默认 lookback, None=使用各表默认值

    Returns:
        {"ok": 正常表数, "gaps": 缺口表数, "no_data": 无数据表数,
         "tables": {table_name: {"status":"ok"|"gap"|"no_data",
                                  "latest_date": "YYYY-MM-DD"|null,
                                  "gap_days": int, "threshold": int, "freq": str}}}
    """
    today = date.today()
    tables = {}
    ok_count, gap_count, no_data_count = 0, 0, 0

    for table, cfg in MONITORED_TABLES.items():
        date_col = cfg["date_col"]
        threshold = cfg.get("gap_threshold", 1)
        freq = cfg.get("freq", "unknown")
        tbl_lookback = lookback_days if lookback_days else cfg.get("lookback", 30)

        latest = check_table_latest_date(table, date_col)

        if latest is None:
            tables[table] = {
                "status": "no_data", "latest_date": None,
                "gap_days": tbl_lookback, "threshold": threshold, "freq": freq,
            }
            no_data_count += 1
            logger.debug("Data gap: %s — no data found", table)
            continue

        # 使用真实交易日历计算缺口 (而非自然日)
        gap_trading_days = _count_trading_days(latest, today)
        if gap_trading_days > threshold:
            tables[table] = {
                "status": "gap", "latest_date": latest.isoformat(),
                "gap_days": gap_trading_days, "threshold": threshold, "freq": freq,
            }
            gap_count += 1
            logger.info("Data gap: %s — latest=%s, %d trading days behind (threshold=%d)",
                       table, latest.isoformat(), gap_trading_days, threshold)
        else:
            tables[table] = {
                "status": "ok", "latest_date": latest.isoformat(),
                "gap_days": gap_trading_days, "threshold": threshold, "freq": freq,
            }
            ok_count += 1

    return {"ok": ok_count, "gaps": gap_count, "no_data": no_data_count, "tables": tables}


def trigger_data_backfill(gaps: dict = None, dry_run: bool = False) -> dict:
    """对检测到的缺口自动触发回补.

    Args:
        gaps: detect_data_gaps() 的返回值, None=先执行一次检测
        dry_run: True=仅计算需回补天数不实际执行

    Returns:
        {"triggered": N, "skipped": N, "results": {table: {status, days_back, ...}}}
    """
    if gaps is None:
        gaps = detect_data_gaps()

    tables_info = gaps.get("tables", {})
    results = {}
    triggered, skipped = 0, 0

    for table, info in tables_info.items():
        if info.get("status") != "gap":
            continue

        fn = _BACKFILL_MAP.get(table)
        if fn is None:
            results[table] = {"status": "no_handler", "gap_days": info["gap_days"]}
            skipped += 1
            logger.debug("Backfill %s: no handler registered, skipping", table)
            continue

        # 回补窗口 = 滞后天数 + 3 天缓冲区 (覆盖非交易日)
        days_needed = info["gap_days"] + 3

        if dry_run:
            results[table] = {"status": "dry_run", "gap_days": info["gap_days"],
                              "days_needed": days_needed, "latest_date": info["latest_date"]}
            triggered += 1
            continue

        try:
            fn_result = fn(days_back=days_needed)
            results[table] = {
                "status": "backfilled", "gap_days": info["gap_days"],
                "days_back": days_needed,
                "latest_date": info["latest_date"],
                "written": fn_result.get("written", 0) if isinstance(fn_result, dict) else 0,
            }
            triggered += 1
            logger.info("Backfill %s: %d days, written=%d",
                       table, days_needed, results[table].get("written", 0))
        except Exception as e:
            results[table] = {"status": "error", "gap_days": info["gap_days"],
                              "error": str(e)[:200]}
            skipped += 1
            logger.warning("Backfill %s FAILED: %s", table, e)

    return {"triggered": triggered, "skipped": skipped, "results": results}


def run_data_integrity_check(dry_run: bool = False) -> dict:
    """每日数据完整性检查 + 自动回补 (L4 按需触发).

    在非交易时段 (凌晨 4:00) 执行, 避免与实时采集抢 Tushare 配额。
    回补使用 kronos_data.etl 中的已有函数, 零重复代码。

    Returns:
        {"check": {...}, "backfill": {...}}
    """
    logger.info("Data integrity check starting (dry_run=%s)...", dry_run)
    t0 = time.time()

    gaps = detect_data_gaps()
    logger.info("Integrity scan: %d ok, %d gaps, %d no_data (%.1fs)",
               gaps["ok"], gaps["gaps"], gaps["no_data"], time.time() - t0)

    if gaps["gaps"] == 0:
        return {"check": gaps, "backfill": {"triggered": 0, "skipped": 0, "results": {}}}

    # 有缺口 → 触发回补
    backfill = trigger_data_backfill(gaps, dry_run=dry_run)
    logger.info("Integrity backfill: %d triggered, %d skipped (%.1fs total)",
               backfill["triggered"], backfill["skipped"], time.time() - t0)

    return {"check": gaps, "backfill": backfill}


def run_data_quality_report() -> dict:
    """L4 数据质量检查 — 检测异常值、空值、重复、新鲜度。

    对 PG 中的核心表执行质量扫描，输出异常计数报告。
    每周六凌晨 4:30 执行，避免与数据完整性检查冲突。

    检查项:
      - daily_kline: close<=0, volume<0, change_pct NULL
      - stk_auction_o: close NULL, vwap NULL
      - index_daily: close NULL
      - cb_daily: close<=0, duplicate (ts_code, trade_date)
      - cb_factor: RSI 越界 [0,100]
      - stocks: market_cap NULL (非ST)
      - 数据新鲜度: 每张表最新日期距今天数
    """
    import psycopg2
    logger.info("Data quality report starting...")
    t0 = time.time()
    today = date.today()
    results: dict[str, list] = {}

    try:
        conn = psycopg2.connect(_PG_URL)
        conn.autocommit = True
        cur = conn.cursor()

        # ── 行情数据质量 ──
        checks = [
            ("daily_kline", "close <= 0",
             "SELECT COUNT(*) FROM daily_kline WHERE close <= 0 OR close IS NULL"),
            ("daily_kline", "volume < 0",
             "SELECT COUNT(*) FROM daily_kline WHERE volume < 0"),
            ("daily_kline", "change_pct IS NULL",
             "SELECT COUNT(*) FROM daily_kline WHERE change_pct IS NULL"),
            ("index_daily", "close IS NULL",
             "SELECT COUNT(*) FROM index_daily WHERE close IS NULL"),
            ("stk_auction_o", "close IS NULL",
             "SELECT COUNT(*) FROM stk_auction_o WHERE close IS NULL"),
        ]

        # Only check cb_* tables if they exist
        for table in ("cb_daily", "cb_factor", "cb_price_chg", "cb_basic"):
            try:
                cur.execute(SQL("SELECT 1 FROM {} LIMIT 1").format(Identifier(table)))
            except Exception:
                continue  # table doesn't exist, skip

        # cb_daily checks
        try:
            cur.execute("SELECT COUNT(*) FROM cb_daily WHERE close <= 0 OR close IS NULL")
            results["cb_daily"] = [{"check": "close <= 0", "count": cur.fetchone()[0]}]
            cur.execute("SELECT COUNT(*) FROM (SELECT ts_code, trade_date FROM cb_daily GROUP BY ts_code, trade_date HAVING COUNT(*) > 1) d")
            results["cb_daily"].append({"check": "duplicate", "count": cur.fetchone()[0]})
        except Exception:
            pass

        # cb_factor RSI range check
        try:
            for field in ("rsi_6", "rsi_12", "rsi_24"):
                cur.execute(SQL("SELECT COUNT(*) FROM cb_factor WHERE {} IS NOT NULL AND ({} < 0 OR {} > 100)").format(Identifier(field), Identifier(field)))
                k = f"cb_factor.{field}_out_of_range"
                results[k] = [{"check": f"{field} ∉ [0,100]", "count": cur.fetchone()[0]}]
        except Exception:
            pass

        # stocks check
        try:
            cur.execute("SELECT COUNT(*) FROM stocks WHERE market_cap IS NULL AND is_st = 0")
            results["stocks"] = [{"check": "market_cap NULL (non-ST)", "count": cur.fetchone()[0]}]
        except Exception:
            pass

        # ── 数据新鲜度 (days behind today) ──
        freshness_checks = [
            ("daily_kline", "trade_date"),
            ("index_daily", "trade_date"),
            ("ths_daily", "trade_date"),
            ("stk_auction_o", "trade_date"),
            ("stk_mins", "trade_time"),
        ]
        for table, col in freshness_checks:
            try:
                cur.execute(SQL("SELECT MAX({})").format(Identifier(col)).format(Identifier(table)))
                row = cur.fetchone()
                if row and row[0]:
                    latest = _parse_date(row[0])
                    if latest:
                        days_behind = (today - latest).days
                        results.setdefault("freshness", []).append(
                            {"table": table, "latest": latest.isoformat(), "days_behind": days_behind})
            except Exception:
                pass

        conn.close()
    except Exception as e:
        logger.warning("Data quality report PG check failed: %s", e)

    elapsed = time.time() - t0

    # ── 汇总并告警 ──
    total_anomalies = 0
    for key, items in results.items():
        if key != "freshness":
            for item in items:
                total_anomalies += item.get("count", 0)

    report = {
        "checked_at": datetime.now().isoformat(),
        "total_anomalies": total_anomalies,
        "results": results,
        "elapsed": round(elapsed, 1),
    }

    if total_anomalies > 0:
        logger.warning("Data quality: %d anomalies detected", total_anomalies)
    else:
        logger.info("Data quality: all checks passed (%.1fs)", elapsed)

    return report


# ═══════════════════════════════════════════════════════════════
# 新增同步函数 (L1 日内 / L2 盘后 / L3 周级 补充)
# ═══════════════════════════════════════════════════════════════

def sync_stk_factor_pro_daily() -> dict:
    """同步 Tushare stk_factor_pro — 股票每日技术因子 (盘后 16:05).

    接口: pro.stk_factor_pro(trade_date=YYYYMMDD)
    包含 MACD/KDJ/RSI/BOLL/ATR 等技术指标, 为秋神选股模型提供因子数据。
    写入 PG (主) + SQLite (fallback).

    Returns:
        {"table": "stk_factor_pro", "written": N, "pg_written": N, "elapsed": S}
    """
    import sqlite3
    from datetime import date
    from app.config import DB_PATH, TUSHARE_TOKEN
    from app.sync.rate_limiter import rate_limit

    t0 = time.time()
    today = date.today().strftime("%Y%m%d")
    trade_date = date.today().strftime("%Y-%m-%d")

    if not TUSHARE_TOKEN:
        return {"status": "skipped", "reason": "no Tushare token"}

    try:
        import tushare as ts
        ts.set_token(TUSHARE_TOKEN)
        pro = ts.pro_api()
        rate_limit()
        df = pro.stk_factor_pro(trade_date=today)
    except Exception as e:
        return {"status": "error", "reason": str(e)[:200]}

    if df is None or len(df) == 0:
        return {"table": "stk_factor_pro", "written": 0, "note": "no data for today"}

    # PG stk_factor_pro columns: ts_code, trade_date,
    #   ma5, ma10, ma20, ma60 (computed from close),
    #   macd_dif, macd_dea, macd, rsi_6, rsi_12, rsi_24,
    #   boll_upper, boll_mid, boll_lower, kdj_k, kdj_d, kdj_j,
    #   vol_ratio, turnover_rate
    # Tushare API returns: close, macd_*, rsi_*, boll_*, kdj_*, turnover_rate, volume_ratio
    api_cols = ["ts_code", "macd_dif", "macd_dea", "macd",
                "kdj_k", "kdj_d", "kdj_j",
                "rsi_6", "rsi_12", "rsi_24",
                "boll_upper", "boll_mid", "boll_lower",
                "turnover_rate", "volume_ratio"]
    pg_col_map = {  # API field → PG column name
        "volume_ratio": "vol_ratio",  # PG column name differs
    }

    rows = []
    for _, r in df.iterrows():
        vals = []
        for c in api_cols:
            if c == "ts_code":
                vals.append(r.get("ts_code"))
            else:
                v = r.get(c)
                try:
                    import numpy as np
                    if isinstance(v, (np.floating,)) and np.isnan(v):
                        vals.append(None)
                        continue
                except ImportError:
                    pass
                vals.append(v)
        rows.append(tuple(vals))

    pg_cols = [pg_col_map.get(c, c) for c in api_cols]

    # PG 直写 (主路径)
    pg_written = 0
    if rows:
        try:
            from app.sync.pg_writer import _pg_write
            pg_written = _pg_write("stk_factor_pro", pg_cols,
                                    ["ts_code", "trade_date"], rows)
        except Exception as e:
            logger.debug("PG write stk_factor_pro skipped: %s", e)

    # SQLite 写入 (fallback) — 使用 pg_cols (PG兼容列名)
    sqlite_written = 0
    if rows:
        try:
            db = sqlite3.connect(DB_PATH)
            sqlite_cols = ["ts_code", "trade_date"] + pg_cols[1:]  # trade_date first
            placeholders = ",".join(["?"] * len(sqlite_cols))
            # Build rows with trade_date prepended
            sqlite_rows = [(row[0], trade_date) + tuple(row[1:]) for row in rows]
            db.executemany(
                f"INSERT OR REPLACE INTO stk_factor_pro({','.join(sqlite_cols)}) "
                f"VALUES({placeholders})", sqlite_rows)
            sqlite_written = len(sqlite_rows)
            db.commit()
            db.close()
        except Exception as e:
            logger.warning("SQLite write stk_factor_pro failed: %s", e)

    elapsed = time.time() - t0
    logger.info("stk_factor_pro: %d rows, PG=%d, SQLite=%d, %.1fs",
               len(rows), pg_written, sqlite_written, elapsed)
    return {"table": "stk_factor_pro", "written": len(rows),
            "pg_written": pg_written, "sqlite_written": sqlite_written, "elapsed": elapsed}


def sync_sw_daily_batch(days_back: int = 7) -> dict:
    """同步申万行业日线 — 从 etl.sync_sw_daily 封装.

    原 etl.py 的 sync_sw_daily 默认拉 10 年数据, 此处供日常增量使用。
    """
    try:
        return sync_sw_daily(days_back=min(days_back, 30))
    except Exception as e:
        logger.warning("sw_daily batch sync failed: %s", e)
        return {"status": "error", "table": "sw_daily", "reason": str(e)[:200]}


def sync_limit_list_d_intraday() -> dict:
    """日内 limit_list_d 增量 — L1 每 30 分钟采集当日涨跌停数据.

    与盘后的 sync_post_market_ext 互补: 盘后只有 U (涨停),
    此处采集 U + D (跌停) + Z (炸板) 完整数据, 支持盘中选股决策。
    """
    import sqlite3
    from datetime import date
    from app.config import DB_PATH, TUSHARE_TOKEN
    from app.sync.rate_limiter import rate_limit

    t0 = time.time()
    today_yyyymmdd = date.today().strftime("%Y%m%d")
    today = date.today().strftime("%Y-%m-%d")

    if not TUSHARE_TOKEN:
        return {"status": "skipped", "reason": "no Tushare token"}

    try:
        import tushare as ts
        ts.set_token(TUSHARE_TOKEN)
        pro = ts.pro_api()
    except Exception as e:
        return {"status": "error", "reason": str(e)[:200]}

    all_rows = []
    for limit_type in ("U", "D", "Z"):
        try:
            rate_limit()
            df = pro.limit_list_d(trade_date=today_yyyymmdd, limit_type=limit_type)
        except Exception:
            continue
        if df is None or len(df) == 0:
            continue
        for _, r in df.iterrows():
            all_rows.append((
                str(r.get("ts_code", "")), today,
                limit_type,
                r.get("up_limit"), r.get("down_limit"),
                str(r.get("first_time", "")), str(r.get("last_time", "")),
                r.get("open_times"), str(r.get("up_stat", "")),
                r.get("fd_amount"),
                r.get("pct_chg"), r.get("pre_close"),
                r.get("close"), r.get("open"),
            ))

    if not all_rows:
        return {"table": "limit_list_d", "written": 0, "note": "no intraday data"}

    # PG 直写
    pg_written = 0
    pg_cols = ["ts_code", "trade_date", "limit_type", "up_limit", "down_limit",
               "first_time", "last_time", "open_times", "up_stat", "fd_amount",
               "pct_chg", "pre_close", "close", "open"]
    try:
        from app.sync.pg_writer import _pg_write
        pg_written = _pg_write("limit_list_d", pg_cols,
                                ["ts_code", "trade_date", "limit_type"], all_rows)
    except Exception as e:
        logger.debug("PG write limit_list_d (intraday) skipped: %s", e)

    # SQLite fallback
    try:
        db = sqlite3.connect(DB_PATH)
        db.executemany(
            "INSERT OR REPLACE INTO limit_list_d(ts_code,trade_date,limit_type,up_limit,down_limit,"
            "first_time,last_time,open_times,up_stat,fd_amount,pct_chg,pre_close,close,open) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)", all_rows)
        db.commit()
        db.close()
    except Exception as e:
        logger.warning("SQLite write limit_list_d (intraday) failed: %s", e)

    elapsed = time.time() - t0
    logger.info("limit_list_d intraday: %d rows (U/D/Z), PG=%d, %.1fs",
               len(all_rows), pg_written, elapsed)
    return {"table": "limit_list_d", "written": len(all_rows),
            "pg_written": pg_written, "elapsed": elapsed}


def sync_moneyflow_hsgt_weekly() -> dict:
    """周级同步沪深港通资金流向 — L3 每周一 08:30.

    从 etl.sync_moneyflow_hsgt 封装, 回补 7 天确保不遗漏。
    """
    try:
        return sync_moneyflow_hsgt(days_back=7)
    except Exception as e:
        logger.warning("moneyflow_hsgt weekly sync failed: %s", e)
        return {"status": "error", "table": "moneyflow_hsgt", "reason": str(e)[:200]}


def _cron_match(cron_expr: str, now: datetime) -> bool:
    """简易 cron 匹配: 'minute hour day_of_month * day_of_week'. 支持 */N 语法.

    fields: minute (0-59), hour (0-23), day_of_month (1-31), *, day_of_week (1-7, Mon=1).
    day_of_month 为 * 时忽略; day_of_week 为 * 时忽略.
    """
    parts = cron_expr.split()
    if len(parts) < 5:
        return False

    def _match(field: str, val: int) -> bool:
        if field == "*":
            return True
        if field.startswith("*/"):
            step = int(field[2:])
            return val % step == 0
        if "-" in field:
            lo, hi = field.split("-")
            return int(lo) <= val <= int(hi)
        if "," in field:
            return val in [int(x) for x in field.split(",")]
        return int(field) == val

    return (_match(parts[0], now.minute) and
            _match(parts[1], now.hour) and
            _match(parts[2], now.day) and
            _match(parts[4], now.isoweekday()))


def _extract_pg_status(result) -> tuple:
    """从 sync 函数返回值中提取 pg_write_status 和 pg_written 总数.

    支持扁平 dict（如 daily_kline）和嵌套 dict
    （如 post_market_core 的 {table: {..., pg_written: N}}）.
    """
    pg_total = 0
    has_pg_field = False
    if isinstance(result, dict):
        # 扁平: {"pg_written": N, ...}
        if "pg_written" in result:
            pg_total += int(result["pg_written"] or 0)
            has_pg_field = True
        # 嵌套: {"table_name": {"pg_written": N, ...}, ...}
        for v in result.values():
            if isinstance(v, dict) and "pg_written" in v:
                pg_total += int(v["pg_written"] or 0)
                has_pg_field = True
    if not has_pg_field:
        return "skipped", 0
    if pg_total > 0:
        return "ok", pg_total
    return "partial", 0


async def _run_job(job: dict):
    """执行单个任务并记录状态, 最多重试3次 (指数退避: 1s, 4s, 16s)."""
    t0 = datetime.now()
    max_retries = 3

    for attempt in range(max_retries):
        try:
            fn = job["fn"]
            result = fn() if not job.get("args") else fn(*job["args"])
            pg_status, pg_total = _extract_pg_status(result)
            _job_status[job["id"]] = {
                "last_run": t0.isoformat(), "last_status": "ok",
                "result": str(result)[:300],
                "pg_write_status": pg_status,
                "pg_written": pg_total,
            }
            if pg_total > 0:
                logger.info("%s: ok (pg=%s, %d rows)", job["id"], pg_status, pg_total)
            return  # success, exit retry loop
        except Exception as e:
            if attempt < max_retries - 1:
                sleep_s = 4 ** attempt  # 1, 4, 16
                logger.warning("%s: retry %d/%d after %.0fs — %s",
                               job["id"], attempt + 1, max_retries, sleep_s, e)
                await asyncio.sleep(sleep_s)
            else:
                _job_status[job["id"]] = {
                    "last_run": t0.isoformat(), "last_status": "error",
                    "error": str(e)[:300],
                    "pg_write_status": "fail",
                    "pg_written": 0,
                }
                logger.warning("%s: FAILED after %d retries — %s",
                               job["id"], max_retries, e)


async def _scheduler_loop():
    """主调度循环: 每 30 秒检查一次是否有任务到时间."""
    global _running, _jobs
    _running = True
    logger.info("Scheduler loop started (%d jobs)", len(_jobs))

    last_run = {}
    while _running:
        now = datetime.now()
        for job in _jobs:
            cron = job["cron"]
            job_id = job["id"]
            # 避免同一分钟重复执行
            if last_run.get(job_id) == now.strftime("%H:%M"):
                continue
            if _cron_match(cron, now):
                last_run[job_id] = now.strftime("%H:%M")
                asyncio.create_task(_run_job(job))

        await asyncio.sleep(30)


def collect_auction_snapshot():
    """9:25 竞价快照 — Tushare stk_auction (实时) → mootdx fallback.

    Priority:
      1. Tushare stk_auction (new API, available 9:25-9:29 daily)
      2. mootdx 9:30 first 5min bar (fallback if Tushare unavailable)

    Writes to PG stk_auction_o for all screener models.
    """
    from datetime import date
    today_str = datetime.now().strftime("%Y%m%d")
    today_dash = date.today().strftime("%Y-%m-%d")

    # ── Path 1: Tushare stk_auction (preferred, real-time 9:25-9:29) ──
    try:
        result = sync_stk_auction_o(trade_date=today_str)
        fetched = result.get("fetched", 0) if isinstance(result, dict) else 0
        if fetched > 0:
            logger.info("Auction snapshot: Tushare stk_auction → %d stocks", fetched)
            return {"status": "ok", "source": "tushare_stk_auction",
                    "date": today_dash, "stocks": fetched}
    except Exception as e:
        logger.warning("Tushare stk_auction failed, falling back to mootdx: %s", e)

    # ── Path 2: mootdx 9:30 first bar (legacy fallback) ──
    import sqlite3, psycopg2
    from app.config import DB_PATH

    try:
        collect_rt_min()
    except Exception as e:
        logger.warning("collect_rt_min failed: %s", e)

    rows = []
    try:
        db = sqlite3.connect(DB_PATH)
        rows = db.execute(
            "SELECT ts_code, open, high, low, close, volume, amount "
            "FROM stk_mins WHERE trade_time LIKE ? AND freq='5min'",
            (f"{today_dash} 09:3%",)
        ).fetchall()
        db.close()
    except Exception as e:
        logger.warning("mootdx stk_mins read failed: %s", e)

    if rows:
        try:
            pg = psycopg2.connect(os.environ.get("KRONOS_PG_URL",
                "postgresql://kronos:kronos@localhost:6432/kronos"))
            pg.autocommit = True
            cur = pg.cursor()
            for r in rows:
                code = r[0].split('.')[0] if '.' in str(r[0]) else r[0]
                cur.execute(
                    "INSERT INTO stk_auction_o (code, trade_date, open, high, low, close, vol, amount, vwap) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (code, trade_date) DO NOTHING",
                    (code, today_dash, r[1], r[2], r[3], r[4], r[5], r[6],
                     r[6]/r[5] if r[5] and float(r[5]) > 0 else r[1]))
            pg.close()
        except Exception as e:
            logger.warning("PG write failed for mootdx auction: %s", e)

    logger.info("Auction snapshot (mootdx fallback): %d stocks", len(rows))
    return {"status": "ok", "source": "mootdx_fallback",
            "date": today_dash, "stocks": len(rows)}


def run_intraday_sync():
    """盘中午间同步 — 交易日 13:00 同步当天上午数据到 SQLite + PG."""
    today = date.today().strftime("%Y-%m-%d")
    core = sync_post_market_core(today)
    ext = sync_post_market_ext(today)
    logger.info("Intraday sync done: core=%s, ext=%s",
                str({k: v.get("written", 0) for k, v in core.items()}),
                str({k: v.get("written", 0) for k, v in ext.items()}))
    return {"core_summary": str({k: v.get("written", 0) for k, v in core.items()}),
            "ext_summary": str({k: v.get("written", 0) for k, v in ext.items()})}


def start_scheduler():
    """注册定时任务并启动后台循环."""
    global _jobs
    today = date.today().strftime("%Y-%m-%d")

    _jobs = [
        # ── L0 实时级 (交易时段) ──
        {"id": "rt_min", "name": "[L0]实时分钟线", "cron": "*/1 9-15 * * 1-5",
         "fn": collect_rt_min},
        {"id": "auction", "name": "[L0]竞价快照", "cron": "25 9 * * 1-5",
         "fn": collect_auction_snapshot},
        # P3 实时日线 — 从 stk_mins 聚合 daily OHLCV (每 5 分钟)
        {"id": "rt_k", "name": "[L0]实时日线OHLCV", "cron": "*/5 9-15 * * 1-5",
         "fn": sync_rt_k},
        # P3 申万实时行情 — 盘中快照 (每 5 分钟)
        {"id": "rt_sw_k", "name": "[L0]申万实时行情", "cron": "*/5 9-15 * * 1-5",
         "fn": sync_rt_sw_k},

        # ── L1 日内级 (交易时段每 30 分钟) ──
        {"id": "limit_list_d_intra", "name": "[L1]涨跌停日内增量", "cron": "*/30 9-15 * * 1-5",
         "fn": sync_limit_list_d_intraday},
        # 盘中午间同步 — 交易日 13:00 同步上午数据
        {"id": "intraday_sync", "name": "[L1]盘中午间同步", "cron": "0 13 * * 1-5",
         "fn": run_intraday_sync},
        # P0 新闻舆情增量 — 盘中每 30 分钟采集最新快讯
        {"id": "stock_news", "name": "[L1]新闻舆情增量", "cron": "*/30 9-15 * * 1-5",
         "fn": sync_stock_news, "args": (7,)},

        # ── L2 盘后级 (每日 16:00 前后) ──
        # P0 核心表 — 15:30 盘后立即采集
        {"id": "post_market_core", "name": "[L2]P0核心盘后", "cron": "30 15 * * 1-5",
         "fn": sync_post_market_core, "args": (today,)},
        # stk_auction_o 在 9:25 竞价快照 job 中一并采集, 不单独调度
        # P1 扩展表 — 15:35 紧跟核心表
        {"id": "post_market_ext", "name": "[L2]P1扩展盘后", "cron": "35 15 * * 1-5",
         "fn": sync_post_market_ext, "args": (today,)},
        # PG 物化视图刷新
        {"id": "pg_refresh", "name": "[L2]PG物化视图刷新", "cron": "37 15 * * 1-5",
         "fn": refresh_materialized_views},
        # 16:00 批次 — 同花顺 + 可转债 + 指数
        # 以下数据源在 18:00 后由 Tushare 发布 (收盘后数据)
        {"id": "cb_daily", "name": "[L2]可转债日线", "cron": "0 18 * * 1-5",
         "fn": sync_cb_daily},
        {"id": "ths_daily", "name": "[L2]同花顺概念板块", "cron": "5 18 * * 1-5",
         "fn": sync_ths_daily},
        {"id": "index_daily", "name": "[L2]指数日线", "cron": "10 18 * * 1-5",
         "fn": sync_index_daily},
        # 16:05 批次 — 申万行业 + 股票技术因子 (新增)
        {"id": "sw_daily", "name": "[L2]申万行业日线", "cron": "5 16 * * 1-5",
         "fn": sync_sw_daily_batch},
        {"id": "stk_factor_pro", "name": "[L2]股票技术因子", "cron": "5 16 * * 1-5",
         "fn": sync_stk_factor_pro_daily},

        # ── P0: L2-P2 风控数据波 (16:00-17:30) ──
        {"id": "hk_hold", "name": "[L2]沪深港通持股明细", "cron": "0 16 * * 1-5",
         "fn": sync_hk_hold},
        {"id": "margin_detail", "name": "[L2]融资融券明细", "cron": "2 16 * * 1-5",
         "fn": sync_margin},
        {"id": "margin_summary", "name": "[L2]融资融券汇总", "cron": "4 16 * * 1-5",
         "fn": sync_margin_summary},
        {"id": "adj_factor", "name": "[L2]复权因子", "cron": "30 16 * * 1-5",
         "fn": sync_adj_factor},
        {"id": "top_list", "name": "[L2]龙虎榜明细", "cron": "0 17 * * 1-5",
         "fn": sync_top_list},
        {"id": "top_inst", "name": "[L2]龙虎榜机构交易", "cron": "3 17 * * 1-5",
         "fn": sync_top_inst},
        {"id": "block_trade", "name": "[L2]大宗交易", "cron": "6 17 * * 1-5",
         "fn": sync_block_trade_data},
        {"id": "holder_trade", "name": "[L2]股东增减持", "cron": "9 17 * * 1-5",
         "fn": sync_stk_holdertrade},
        {"id": "pledge_detail", "name": "[L2]股权质押明细", "cron": "12 17 * * 1-5",
         "fn": sync_pledge_detail},
        {"id": "share_float", "name": "[L2]限售股解禁", "cron": "15 17 * * 1-5",
         "fn": sync_share_float},
        {"id": "cyq_chips", "name": "[L2]每日筹码分布", "cron": "18 17 * * 1-5",
         "fn": sync_cyq_chips},
        {"id": "forecast", "name": "[L2]业绩预告", "cron": "21 17 * * 1-5",
         "fn": sync_forecast_data},
        {"id": "dividend", "name": "[L2]分红送股", "cron": "24 17 * * 1-5",
         "fn": sync_dividend_data},

        # ── P0: L2-P3 财务数据波 (17:25-17:45, 财报季日更, 其余时间 small batch) ──
        {"id": "income", "name": "[L2]利润表", "cron": "25 17 * * 1-5",
         "fn": sync_income},
        {"id": "balancesheet", "name": "[L2]资产负债表", "cron": "28 17 * * 1-5",
         "fn": sync_balancesheet},
        {"id": "cashflow", "name": "[L2]现金流量表", "cron": "31 17 * * 1-5",
         "fn": sync_cashflow},
        {"id": "fina_indicator", "name": "[L2]财务指标100+", "cron": "34 17 * * 1-5",
         "fn": sync_financial_indicator},
        # P1 财务深度 — 主营构成 + 审计意见 (财报季日更)
        {"id": "fina_mainbz", "name": "[L2]主营业务构成", "cron": "37 17 * * 1-5",
         "fn": sync_fina_mainbz},
        {"id": "fina_audit", "name": "[L2]审计意见", "cron": "40 17 * * 1-5",
         "fn": sync_fina_audit},

        # 16:30 批次 — 可转债技术因子
        {"id": "cb_factor", "name": "[L2]可转债技术因子", "cron": "30 18 * * 1-5",
         "fn": sync_cb_factor},
        {"id": "cb_call", "name": "[L2]可转债强赎信息", "cron": "35 18 * * 1-5",
         "fn": sync_cb_call},
        # ── P0: L2-P4 资讯数据波 (18:00-18:55) ──
        {"id": "research_report", "name": "[L2]券商研报", "cron": "38 18 * * 1-5",
         "fn": sync_research_report, "args": (7,)},
        {"id": "announcements", "name": "[L2]上市公司公告", "cron": "42 18 * * 1-5",
         "fn": sync_announcements},
        # P2 资讯深度 — 互动问答 + 新闻联播 (盘后)
        {"id": "interact_qa", "name": "[L2]互动问答", "cron": "45 18 * * 1-5",
         "fn": sync_interact_qa},
        {"id": "cctv_news", "name": "[L2]新闻联播文字稿", "cron": "48 18 * * 1-5",
         "fn": sync_cctv_news},
        # P2 政策法规 — 盘后 19:00
        {"id": "policy_law", "name": "[L2]政策法规库", "cron": "0 19 * * 1-5",
         "fn": sync_policy_law},

        # ── L3 周级 (每周) ──
        # 股票列表全量同步 — 每周六 02:00 (ADR-006 决策 4)
        {"id": "stocks_sync", "name": "[L3]股票列表同步", "cron": "0 2 * * 6",
         "fn": sync_stock_list},
        # 股票增量同步 — 每日盘前 8:00 检测新上市 (ADR-006 决策 4)
        {"id": "stocks_incremental", "name": "[L3]新股增量检测", "cron": "0 8 * * 1-5",
         "fn": sync_stocks_incremental},
        # 沪深港通资金流向 — 每周一 08:30
        {"id": "moneyflow_hsgt", "name": "[L3]沪深港通资金流向", "cron": "30 8 * * 1",
         "fn": sync_moneyflow_hsgt_weekly},
        # P0 周级风控 — 每周一凌晨
        {"id": "weekly_kline", "name": "[L3]周线数据", "cron": "0 1 * * 1",
         "fn": sync_weekly_kline},
        {"id": "holder_number", "name": "[L3]股东人数筹码集中度", "cron": "0 2 * * 1",
         "fn": sync_stk_holdernumber},
        {"id": "repurchase", "name": "[L3]股票回购", "cron": "30 2 * * 1",
         "fn": sync_repurchase},
        {"id": "index_basic", "name": "[L3]指数基本信息", "cron": "0 2 * * 6",
         "fn": sync_index_basic},
        # P1 公司基本信息 — 每周六 03:00 (全量刷新)
        {"id": "stock_profiles", "name": "[L3]公司基本信息", "cron": "0 3 * * 6",
         "fn": sync_stock_profiles},
        # P2 央行货币政策报告 — 每月 5 日 04:00
        {"id": "mp_report", "name": "[L3]央行货币政策报告", "cron": "0 4 5 * *",
         "fn": sync_mp_report},
        # 转股价变动 — 每周一 09:00
        {"id": "cb_price_chg", "name": "[L3]转股价变动", "cron": "0 9 * * 1",
         "fn": sync_cb_price_chg_all},
        # P0 月级 — 每月1日凌晨
        {"id": "monthly_kline", "name": "[L3]月线数据", "cron": "0 2 1 * *",
         "fn": sync_monthly_kline},
        {"id": "broker_recommend", "name": "[L3]券商每月金股", "cron": "30 2 1 * *",
         "fn": sync_broker_recommend},
        # 同花顺概念映射 — 每月1日 03:00
        {"id": "ths_concept_map", "name": "[L3]同花顺概念映射", "cron": "0 3 1 * *",
         "fn": sync_ths_concept_map},

        # ── L4 历史回补 (每日凌晨自动检测 + 回补) ──
        {"id": "data_integrity", "name": "[L4]数据完整性检查+回补", "cron": "0 4 * * *",
         "fn": run_data_integrity_check},
        # 数据质量检查 — 每周六凌晨 4:30
        {"id": "data_quality", "name": "[L4]数据质量周检", "cron": "30 4 * * 6",
         "fn": run_data_quality_report},
    ]

    for j in _jobs:
        _job_status[j["id"]] = {"last_run": None, "last_status": "pending"}

    loop = asyncio.get_event_loop()
    loop.create_task(_scheduler_loop())
    logger.info("Scheduler registered: %d jobs", len(_jobs))


def get_job_status() -> dict:
    """获取所有任务状态."""
    result_jobs = []
    now = datetime.now()
    for j in _jobs:
        status = _job_status.get(j["id"], {})
        result_jobs.append({
            "id": j["id"], "name": j["name"],
            "cron": j["cron"],
            "last_run": status.get("last_run"),
            "last_status": status.get("last_status", "pending"),
            "last_result": status.get("result", ""),
            "pg_write_status": status.get("pg_write_status", "skipped"),
            "pg_written": status.get("pg_written", 0),
        })
    return {"jobs": result_jobs, "scheduler_running": _running}


def stop_scheduler():
    global _running
    _running = False
