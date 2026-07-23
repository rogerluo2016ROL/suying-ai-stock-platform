"""内置 asyncio 定时任务调度 — 零外部依赖."""

import asyncio, logging, os, sys, time
from datetime import datetime, date, timedelta
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
from app.sync.namechange import sync_st_history
from app.sync.global_news import sync_global_news
from app.sync.us_market import sync_us_daily, sync_us_basic, sync_global_index
from app.sync.kr_market import sync_kr_daily
from app.scheduled_research import (
    build_scheduled_research_jobs,
    run_missed_scheduled_research_tasks,
)

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

# tools/ 下的链等权涨幅构建脚本 (build_industry_price_series.py)
_TOOLS_DIR = os.path.join(_PROJ_ROOT, "tools")
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

logger = logging.getLogger("data-service.scheduler")

_job_status: dict = {}
_jobs: list[dict] = []
_active_jobs: set[str] = set()
_compensation: dict[str, dict] = {}
_running = False

# 单次任务内的 1/4/16 秒重试耗尽后，继续在 10 分钟、30 分钟、2 小时补偿。
_COMPENSATION_DELAYS_MINUTES = (10, 30, 120)

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
    # Tushare 当前接口在本地核验中通常滞后约两周，超过 14 个交易日才触发回补。
    "stk_factor_pro": {"date_col": "trade_date", "lookback": 60, "freq": "L2-daily",  "gap_threshold": 14},
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
    "pledge_detail":            {"date_col": "ann_date",   "lookback": 30, "freq": "L2-daily",  "gap_threshold": 3},  # ADR-009: end_date 列已删, 改 ann_date
    "share_float":              {"date_col": "float_date", "lookback": 30, "freq": "L3-weekly", "gap_threshold": 7},
    "cyq_chips":                {"date_col": "trade_date", "lookback": 14, "freq": "L2-daily",  "gap_threshold": 2},
    "forecast_data":            {"date_col": "end_date",   "lookback": 30, "freq": "L2-daily",  "gap_threshold": 3},
    "dividend_data":            {"date_col": "ex_date",    "lookback": 30, "freq": "L3-weekly", "gap_threshold": 7},
    "adj_factor":               {"date_col": "trade_date", "lookback": 14, "freq": "L2-daily",  "gap_threshold": 1},
    # ── P0 新接入: L2 财务数据 (财报季日更, 普通季周更) ──
    # 财务数据按季披露，不能按日频阈值判断缺口；下一季报告通常在季末后数周至数月才发布。
    "financial_indicator":      {"date_col": "end_date",   "lookback": 240,"freq": "L3-quarterly", "gap_threshold": 120},
    "financial_income":         {"date_col": "end_date",   "lookback": 240,"freq": "L3-quarterly", "gap_threshold": 120},
    "financial_balance":        {"date_col": "end_date",   "lookback": 240,"freq": "L3-quarterly", "gap_threshold": 120},
    "financial_cashflow":       {"date_col": "end_date",   "lookback": 240,"freq": "L3-quarterly", "gap_threshold": 120},
    "fina_mainbz":              {"date_col": "end_date",   "lookback": 240,"freq": "L3-quarterly", "gap_threshold": 120},
    "fina_audit":               {"date_col": "ann_date",   "lookback": 365,"freq": "L3-annual", "gap_threshold": 180},
    # ── P0 新接入: L2 资讯数据 ──
    "research_reports_tushare": {"date_col": "pub_date",   "lookback": 30, "freq": "L2-daily",  "gap_threshold": 14},
    "stock_news_tushare":       {"date_col": "pub_time",   "lookback": 7,  "freq": "L1-intra",  "gap_threshold": 1},
    "announcements":            {"date_col": "ann_date",   "lookback": 7,  "freq": "L2-daily",  "gap_threshold": 2},
    # ── P0 新接入: L3 周/月级行情 ──
    "weekly_kline":             {"date_col": "trade_date", "lookback": 14, "freq": "L3-weekly", "gap_threshold": 7},
    "monthly_kline":            {"date_col": "trade_date", "lookback": 60, "freq": "L3-monthly","gap_threshold": 31},
    "stk_holdernumber":         {"date_col": "end_date",   "lookback": 90, "freq": "L3-weekly", "gap_threshold": 14},
    "repurchase":               {"date_col": "ann_date",   "lookback": 30, "freq": "L3-weekly", "gap_threshold": 7},
    # ADR-013 §决策 6 (LD-2): index_basic 是基础元数据 (code/market/name/publisher 等), 非时序数据,
    # 表无 updated_at 列 (validate 检查 2 触发 WARN); 监控价值有限. 从 MONITORED_TABLES 移除 —— 最干净.
    # 若未来加 updated_at 列 (作为元数据漂移监控) 可重新加入此表.
    "broker_recommend":         {"date_col": "month",      "lookback": 90, "freq": "L3-monthly","gap_threshold": 31},
    "stock_profiles":           {"date_col": "updated_at", "lookback": 14, "freq": "L3-weekly", "gap_threshold": 7},
    "interact_qa":              {"date_col": "pub_date",   "lookback": 7,  "freq": "L2-daily",  "gap_threshold": 2},
    "policy_law":               {"date_col": "pub_date",   "lookback": 7,  "freq": "L2-daily",  "gap_threshold": 2},
    "mp_report":                {"date_col": "pub_date",   "lookback": 240,"freq": "L3-quarterly","gap_threshold": 180},
    "cctv_news":                {"date_col": "pub_date",   "lookback": 7,  "freq": "L2-daily",  "gap_threshold": 2},
    # ── 海外市场早报 (morning_brief, 周一~五采集不受 A 股休市影响, 阈值含周末容差) ──
    "global_news_flash":        {"date_col": "pub_time",   "lookback": 7,  "freq": "L2-daily",  "gap_threshold": 2},
    "us_stock_daily":           {"date_col": "trade_date", "lookback": 14, "freq": "L2-daily",  "gap_threshold": 3},
    "kr_stock_daily":           {"date_col": "trade_date", "lookback": 14, "freq": "L2-daily",  "gap_threshold": 3},
    "global_index_daily":       {"date_col": "trade_date", "lookback": 14, "freq": "L2-daily",  "gap_threshold": 3},
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
    # ── 海外市场早报 (morning_brief) ──
    "global_news_flash":        sync_global_news,
    "us_stock_daily":           sync_us_daily,
    "kr_stock_daily":           sync_kr_daily,
    "global_index_daily":       sync_global_index,
    # ── P0 周/月线回补 ──
    "weekly_kline":     sync_weekly_kline,
    "monthly_kline":    sync_monthly_kline,
    "index_basic":      sync_index_basic,
    "broker_recommend": sync_broker_recommend,
    # ── ADR-012 §决策 5.4: 补齐之前缺 handler 的 3 表 ──
    # ths_daily / index_daily: 函数签名 (days_back=int) 已兼容, 注册即生效
    # stk_factor_pro: 见 sync_stk_factor_pro_backfill 下方定义 (新增双轨入口)
    "ths_daily":        sync_ths_daily,
    "index_daily":      sync_index_daily,
    # stk_factor_pro 注册延后到 sync_stk_factor_pro_backfill 定义后 (函数在本文件下方);
    # ADR-013 §决策 5 (S-4): 旧注释提到 "_register_backfill_handlers_late() 调用" 是失效语义
    # (该函数从未实现, 实际由本文件 L773 顶层 `_BACKFILL_MAP["stk_factor_pro"] = sync_stk_factor_pro_backfill`
    # 直接赋值绕过 forward declaration 限制 — Python 模块加载时顺序执行, 函数定义后立即赋值即生效).
}


# ADR-012 §决策 5.4 + ADR-013 §决策 6 (LD-3): _DESIGN_SKIP_BACKFILL 列出"按设计不走 days_back
# 历史回补模型"的表 ── 它们的 sync 函数不接受 days_back 参数 (实时拉取 / 全量元数据), 但被
# trigger_data_backfill 调用时会因签名不匹配 / 业务语义错位而误触发. validator 检查 1 + 检查 3
# 均跳过此集合避免噪音.
# - stocks: 非时序 (全量股票列表), cron 'stocks_sync' (每周六 02:00) + 'stocks_incremental' (每日 08:00) 维护
# - trade_cal: 交易日历, 由其他流程维护 (无独立 sync_trade_cal 入口)
# - rt_k / rt_sw_k (ADR-013 §决策 6 LD-3 新增): 实时数据按 cron 拉, sync_rt_k 签名无 days_back,
#   sync_rt_sw_k 签名虽有 days_back=1 但语义是"今天再拉一次"非"回补 N 天" → 监控失配, 留在监控但不进 backfill
_DESIGN_SKIP_BACKFILL = {"stocks", "trade_cal", "rt_k", "rt_sw_k"}


# ═══════════════════════════════════════════════════════════════
# 数据完整性检测 (L4 历史回补)
# ═══════════════════════════════════════════════════════════════

def _parse_date(val) -> date | None:
    """将 DB 返回值统一解析为 date 对象.

    兼容 datetime / date / 'YYYY-MM-DD' / 'YYYYMMDD' (紧凑格式)。
    注意 datetime 是 date 的子类, 必须先判断 —— 否则会被 isinstance(val, date)
    捕获后直接返回 datetime, 导致后续 date-datetime 运算报错。
    """
    if val is None:
        return None
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, date):
        return val
    s = str(val)[:10].strip()
    for fmt in ("%Y-%m-%d", "%Y%m%d", "%Y%m"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
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
        # 用 psycopg2.sql.Identifier 防注入 (table/column 不可参数化)。
        # 必须用 SQL(...).format() 而非 Python str.format —— 后者会把 Identifier 转成 repr
        # 生成非法 SQL (如 "SELECT MAX(Identifier('trade_date'))"), 导致查询全部抛异常被吞。
        # 且原写法漏了 FROM 子句。
        cur.execute(SQL("SELECT MAX({}) FROM {}").format(Identifier(date_col), Identifier(table)))
        row = cur.fetchone()
        conn.close()
        parsed = _parse_date(row[0]) if row else None
        if parsed:
            return parsed
    except Exception:
        logger.debug("PG check %s.%s failed, trying SQLite", table, date_col)

    # Fallback: SQLite (SQLite 无 Identifier API, 用 isidentifier() 校验防注入 + 双引号引用)
    if not (isinstance(table, str) and isinstance(date_col, str)
            and table.isidentifier() and date_col.isidentifier()):
        logger.debug("SQLite check skipped: invalid identifier %s.%s", table, date_col)
        return None
    try:
        from app.config import DB_PATH
        import sqlite3
        db = sqlite3.connect(DB_PATH)
        row = db.execute(f'SELECT MAX("{date_col}") FROM "{table}"').fetchone()
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
        # cnt=0 是有效结果 (区间内确无交易日, 如收盘后/周末/节假日),
        # 不应 fallback —— 否则周末会把"最近交易日的最新数据"误判为 gap=自然日差,
        # 进而触发 trigger_data_backfill 对已是最新数据的表做无谓回补 (浪费 Tushare 配额)。
        # 仅当 trade_cal 查询本身失败 (except) 才保守 fallback 到自然日。
        return cnt
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
    from app.config import DB_PATH, TUSHARE_TOKEN, SQLITE_FALLBACK_ENABLED
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
    if rows and SQLITE_FALLBACK_ENABLED:
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


def sync_stk_factor_pro_backfill(days_back: int = 7) -> dict:
    """ADR-012 §决策 5.4: stk_factor_pro 双轨入口 — 接受 days_back 参数支持 backfill 注册.

    原 sync_stk_factor_pro_daily() 是无参数 cron 入口 (只拉今日), 与 _BACKFILL_MAP 期望的
    fn(days_back=int) 签名不兼容, 导致 detect_data_gaps 标记 stk_factor_pro gap 时
    trigger_data_backfill 返回 {status: "no_handler"} 静默跳过.

    本函数循环近 N 个交易日逐日调用 pro.stk_factor_pro(trade_date=YYYYMMDD), 写入
    PG (主) + SQLite (fallback), 与 sync_stk_factor_pro_daily 的字段映射 / column rename
    逻辑保持完全一致 (复用相同写入路径 _pg_write).

    Args:
        days_back: 回补天数 (默认 7; trigger_data_backfill 会传 gap_days + 3 缓冲)

    Returns:
        {"table": "stk_factor_pro", "written": N, "pg_written": N, "sqlite_written": N,
         "days_processed": N, "elapsed": S}
    """
    import sqlite3
    from datetime import date, timedelta
    from app.config import DB_PATH, TUSHARE_TOKEN, SQLITE_FALLBACK_ENABLED
    from app.sync.rate_limiter import rate_limit

    t0 = time.time()
    if not TUSHARE_TOKEN:
        return {"status": "skipped", "reason": "no Tushare token"}

    try:
        import tushare as ts
        ts.set_token(TUSHARE_TOKEN)
        pro = ts.pro_api()
    except Exception as e:
        return {"status": "error", "reason": str(e)[:200]}

    today = date.today()
    # 列名映射与 sync_stk_factor_pro_daily 保持完全一致 (单一来源 by copy, 因 sync_daily
    # 字段映射是脱敏 inline 写死, 没有 helper 可抽; 改 helper 超出本 ADR 白名单)
    api_cols = ["ts_code", "macd_dif", "macd_dea", "macd",
                "kdj_k", "kdj_d", "kdj_j",
                "rsi_6", "rsi_12", "rsi_24",
                "boll_upper", "boll_mid", "boll_lower",
                "turnover_rate", "volume_ratio"]
    pg_col_map = {"volume_ratio": "vol_ratio"}
    pg_cols = [pg_col_map.get(c, c) for c in api_cols]

    total_written, total_pg, total_sqlite, days_processed = 0, 0, 0, 0

    for offset in range(days_back, -1, -1):  # 含今日; offset=days_back ... 0
        d = today - timedelta(days=offset)
        ymd = d.strftime("%Y%m%d")
        trade_date_iso = d.strftime("%Y-%m-%d")

        rate_limit()
        try:
            df = pro.stk_factor_pro(trade_date=ymd)
        except Exception as e:
            logger.debug("stk_factor_pro backfill fetch %s failed: %s", ymd, str(e)[:120])
            continue
        if df is None or len(df) == 0:
            continue  # 非交易日 / 数据未到 (盘后未结算)

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

        if not rows:
            continue

        # PG 直写 (主路径) — 走改造后的 thin wrapper, 自动列过滤 + 重试
        # ADR-013 §决策 5 (S-3): pg_w 显式初始化, 用 try/except 包裹 PG 写入; 删除原 L761
        # "pg_w if 'pg_w' in dir() else 0" 反模式 (依赖 dir() introspection 检测变量存在性
        # 是脆弱写法 — pg_w 在异常分支若未初始化会 NameError; 显式 pg_w=0 是 PEP 8 推荐).
        pg_w = 0
        try:
            from app.sync.pg_writer import _pg_write
            pg_w = _pg_write("stk_factor_pro", pg_cols,
                             ["ts_code", "trade_date"], rows)
            total_pg += pg_w
        except Exception as e:
            logger.debug("PG write stk_factor_pro %s skipped: %s", ymd, str(e)[:120])

        # SQLite fallback — 使用 pg_cols (PG 兼容列名) + 显式 prepend trade_date
        if SQLITE_FALLBACK_ENABLED:
            try:
                db = sqlite3.connect(DB_PATH)
                sqlite_cols = ["ts_code", "trade_date"] + pg_cols[1:]
                placeholders = ",".join(["?"] * len(sqlite_cols))
                sqlite_rows = [(row[0], trade_date_iso) + tuple(row[1:]) for row in rows]
                db.executemany(
                    f"INSERT OR REPLACE INTO stk_factor_pro({','.join(sqlite_cols)}) "
                    f"VALUES({placeholders})", sqlite_rows)
                total_sqlite += len(sqlite_rows)
                db.commit()
                db.close()
            except Exception as e:
                logger.debug("SQLite write stk_factor_pro %s failed: %s", ymd, str(e)[:120])

        total_written += len(rows)
        days_processed += 1
        logger.debug("stk_factor_pro backfill %s: %d rows (PG=%d, SQLite=%d)",
                     ymd, len(rows), pg_w, len(rows))

    elapsed = time.time() - t0
    logger.info("stk_factor_pro backfill: %d days processed, %d rows total, PG=%d, SQLite=%d, %.1fs",
                days_processed, total_written, total_pg, total_sqlite, elapsed)
    # ADR-013 §决策 5 (W-3): "written" 语义修复 — 旧实现 written=total_written (累计 fetched, 含 ON CONFLICT
    # 跳过的重复行) 与 detect_data_gaps 期望的"实际 PG 落库行数"语义错位 (~10x 监控误导).
    # 新约定: written = pg_written = PG 实际新增行数 (与 detect_data_gaps 一致); fetched = 累计 fetch 行数
    # (监控/调试用, 未去重). pg_written 显式别名向后兼容 (SIT 7 evidence / 历史 stk_factor_pro_daily 输出).
    return {"table": "stk_factor_pro",
            "written": total_pg,             # ← 语义对齐 detect_data_gaps (PG 实际落库)
            "fetched": total_written,        # ← 累计 fetch (含去重前重复)
            "pg_written": total_pg,          # ← 向后兼容别名
            "sqlite_written": total_sqlite,
            "days_processed": days_processed, "days_back": days_back,
            "elapsed": round(elapsed, 1)}


# ADR-012 §决策 5.4: 注册 stk_factor_pro backfill handler (函数定义后立刻补登记)
_BACKFILL_MAP["stk_factor_pro"] = sync_stk_factor_pro_backfill


def sync_sw_daily_batch(days_back: int = 7) -> dict:
    """同步申万行业日线 — 从 etl.sync_sw_daily 封装.

    原 etl.py 的 sync_sw_daily 默认拉 10 年数据, 此处供日常增量使用。
    """
    try:
        return sync_sw_daily(days_back=min(days_back, 30))
    except Exception as e:
        logger.warning("sw_daily batch sync failed: %s", e)
        return {"status": "error", "table": "sw_daily", "reason": str(e)[:200]}


def sync_chain_price_series_daily() -> dict:
    """链成分股等权日涨幅 → industry_price_series (盘后 16:40).

    复用 tools/build_industry_price_series.py 的 refresh_chain_equal_weight_series,
    每日更新近 3 个交易日(容错漏跑),供供应链景气评分 (prosperity) 使用。
    """
    try:
        from build_industry_price_series import refresh_chain_equal_weight_series
        stats = refresh_chain_equal_weight_series(_PG_URL, trade_days=3, apply=True)
        return {"table": "industry_price_series",
                "written": stats.get("rows_written", 0),
                "chains": len(stats.get("chains", {})),
                "status": "ok"}
    except Exception as e:
        logger.warning("chain price series daily refresh failed: %s", e)
        return {"status": "error", "table": "industry_price_series", "reason": str(e)[:200]}


def sync_limit_list_d_intraday() -> dict:
    """日内 limit_list_d 增量 — L1 每 30 分钟采集当日涨跌停数据.

    与盘后的 sync_post_market_ext 互补: 盘后只有 U (涨停),
    此处采集 U + D (跌停) + Z (炸板) 完整数据, 支持盘中选股决策。
    """
    import sqlite3
    from datetime import date
    from app.config import DB_PATH, TUSHARE_TOKEN, SQLITE_FALLBACK_ENABLED
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
    if SQLITE_FALLBACK_ENABLED:
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
    if isinstance(result, dict) and result.get("status") == "skipped":
        return "skipped", 0

    pg_total = 0
    has_pg_field = False
    if isinstance(result, dict):
        # 扁平: {"pg_written": N, ...}
        if "pg_written" in result:
            pg_total += int(result["pg_written"] or 0)
            has_pg_field = True
        # kronos_data.etl 的 PG-aware 通用写入函数历史上只返回 written。
        # data-service 运行态设置 KRONOS_PG_URL 时，written 即为 PG 落库数。
        elif os.environ.get("KRONOS_PG_URL") and "written" in result:
            pg_total += int(result["written"] or 0)
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


def _schedule_compensation(job: dict, reason: str) -> None:
    """为异常/降级任务登记下一次补偿时间，避免同一任务重复排队。"""
    job_id = job["id"]
    state = _compensation.get(job_id, {"attempt": 0})
    attempt = int(state.get("attempt", 0))
    if attempt >= len(_COMPENSATION_DELAYS_MINUTES):
        _job_status.setdefault(job_id, {})["compensation_status"] = "exhausted"
        logger.error("%s: compensation exhausted after %d rounds", job_id, attempt)
        return
    delay = _COMPENSATION_DELAYS_MINUTES[attempt]
    next_at = datetime.now() + timedelta(minutes=delay)
    _compensation[job_id] = {"attempt": attempt + 1, "next_at": next_at, "reason": reason[:200]}
    status = _job_status.setdefault(job_id, {})
    status.update({
        "compensation_status": "scheduled",
        "compensation_attempt": attempt + 1,
        "next_compensation_at": next_at.isoformat(),
        "compensation_reason": reason[:200],
    })
    logger.warning("%s: compensation %d/%d scheduled at %s (%s)",
                   job_id, attempt + 1, len(_COMPENSATION_DELAYS_MINUTES),
                   next_at.isoformat(timespec="seconds"), reason[:120])


def _clear_compensation(job_id: str) -> None:
    if job_id in _compensation:
        _compensation.pop(job_id, None)
        status = _job_status.setdefault(job_id, {})
        status.update({"compensation_status": "clear", "next_compensation_at": None})


def _result_needs_compensation(result, pg_status: str) -> bool:
    if not isinstance(result, dict):
        return False
    result_status = result.get("status")
    return result_status in {"error", "failed", "degraded"} or pg_status == "fail"


async def _run_job(job: dict):
    """执行任务：立即重试 3 次，仍失败则进入 10/30/120 分钟补偿队列。"""
    t0 = datetime.now()
    max_retries = 3
    job_id = job["id"]
    _active_jobs.add(job_id)

    try:
        for attempt in range(max_retries):
            try:
                fn = job["fn"]
                result = fn() if not job.get("args") else fn(*job["args"])
                pg_status, pg_total = _extract_pg_status(result)
                result_status = result.get("status") if isinstance(result, dict) else None
                preserved_statuses = {
                    "ok", "skipped", "degraded", "failed",
                    "success", "partial_delivery", "failed_delivery",
                    "skipped_non_trading_day", "skipped_duplicate",
                    "failed_trade_calendar",
                }
                last_status = result_status if result_status in preserved_statuses else "ok"
                _job_status[job_id] = {
                    "last_run": t0.isoformat(), "last_status": last_status,
                    "result": str(result)[:300],
                    "pg_write_status": pg_status,
                    "pg_written": pg_total,
                }
                if _result_needs_compensation(result, pg_status):
                    _schedule_compensation(job, str(result))
                else:
                    _clear_compensation(job_id)
                if pg_total > 0:
                    logger.info("%s: ok (pg=%s, %d rows)", job_id, pg_status, pg_total)
                return
            except Exception as e:
                if attempt < max_retries - 1:
                    sleep_s = 4 ** attempt
                    logger.warning("%s: retry %d/%d after %.0fs — %s",
                                   job_id, attempt + 1, max_retries, sleep_s, e)
                    await asyncio.sleep(sleep_s)
                else:
                    _job_status[job_id] = {
                        "last_run": t0.isoformat(), "last_status": "error",
                        "error": str(e)[:300], "pg_write_status": "fail", "pg_written": 0,
                    }
                    _schedule_compensation(job, str(e))
                    logger.warning("%s: FAILED after %d retries — %s", job_id, max_retries, e)
    finally:
        _active_jobs.discard(job_id)


async def _scheduler_loop():
    """主调度循环: 每 30 秒检查一次是否有任务到时间."""
    global _running, _jobs
    _running = True
    logger.info("Scheduler loop started (%d jobs)", len(_jobs))

    last_run = {}
    while _running:
        now = datetime.now()
        minute_key = now.strftime("%Y-%m-%d %H:%M")
        for job in _jobs:
            cron = job["cron"]
            job_id = job["id"]
            if job_id in _active_jobs:
                continue
            # 避免同一分钟重复执行
            if last_run.get(job_id) == minute_key:
                continue
            if _cron_match(cron, now):
                last_run[job_id] = minute_key
                asyncio.create_task(_run_job(job))

        # 补偿只复用原任务定义，不创建第二套采集逻辑。
        for job in _jobs:
            job_id = job["id"]
            state = _compensation.get(job_id)
            if state and state["next_at"] <= now and job_id not in _active_jobs:
                state["next_at"] = datetime.max
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

    from app.config import is_tushare_configured
    if not is_tushare_configured():
        return {"status": "skipped", "source": "tushare_stk_auction",
                "reason": "TUSHARE_TOKEN not configured",
                "requires": "TUSHARE_TOKEN", "date": today_dash, "stocks": 0}

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
    # B2: PG-only 部署 (SQLITE_FALLBACK_ENABLED=false) 下整段跳过 —
    # Path2 依赖 SQLite stk_mins (由 collect_rt_min 在 fallback 模式下填), PG-only 时恒空且产只读报错噪音.
    # Path1 (Tushare→PG) 已足够; 失败时返回 degraded 而非走废弃 SQLite 链路.
    from app.config import SQLITE_FALLBACK_ENABLED
    if not SQLITE_FALLBACK_ENABLED:
        logger.warning("Auction Path1 empty/failed and SQLite fallback disabled; skip mootdx Path2")
        return {"status": "degraded", "source": "tushare_only",
                "date": today_dash, "stocks": 0}

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


def run_morning_overseas_refresh() -> dict:
    """海外市场早报数据波 — 每工作日 7:50, 在 8:00 早报生成前更新全部资讯 + 海外数据.

    覆盖: 全球快讯 (新浪7x24/金十) + 美股日线 (Tushare VIP) + 全球指数
          + A股资讯增量 (新闻/公告/新闻联播).
    海外市场不受 A 股休市影响, cron 固定周一~周五触发, 不走 trade_cal 判断.
    """
    results = {}
    for name, fn in [
        ("global_news", sync_global_news),
        ("us_daily", sync_us_daily),
        ("global_index", sync_global_index),
        ("stock_news", lambda: sync_stock_news(7)),
        ("announcements", sync_announcements),
        ("cctv_news", sync_cctv_news),
    ]:
        try:
            r = fn()
            results[name] = (r.get("written", r.get("pg_written", 0))
                             if isinstance(r, dict) else str(r))
        except Exception as e:
            logger.warning("morning_overseas %s failed: %s", name, e)
            results[name] = f"error: {e}"
    logger.info("Morning overseas refresh: %s", results)
    return results


def validate_pipeline_consistency() -> dict:
    """ADR-012 §决策 5.5: 启动期数据管道一致性自检 — WARN 不 raise (方案 A 可逆性优先).

    检查项 (任一不一致仅 logger.warning, 不阻断启动):
      1. MONITORED_TABLES 中的每个表, _BACKFILL_MAP 是否注册了 handler
         (例外: stocks/trade_cal 在 _DESIGN_SKIP_BACKFILL 中显式跳过)
      2. MONITORED_TABLES[table].date_col 是否在表实际列集内 (PG introspect information_schema)
      3. _BACKFILL_MAP 的每个 handler 是否 callable + 签名含 days_back 参数 (inspect.signature)

    Returns:
        {"checked": N, "warnings": [{"table": ..., "issue": ..., "fix_hint": ...}, ...],
         "errors": [...]} — errors 列存 PG introspect 异常等不可恢复信息 (不阻断)
    """
    import inspect
    warnings_list = []
    errors_list = []

    # ── 检查 1: 监控表缺 backfill (排除 design-skip) ──
    for table in MONITORED_TABLES:
        if table in _DESIGN_SKIP_BACKFILL:
            continue
        if table not in _BACKFILL_MAP:
            warnings_list.append({
                "table": table,
                "issue": "monitored but no backfill handler",
                "fix_hint": f"add _BACKFILL_MAP['{table}'] = sync_<fn> in scheduler.py",
            })

    # ── 检查 2: date_col 实际存在 (PG introspect) ──
    try:
        import psycopg2
        conn = psycopg2.connect(_PG_URL)
        cur = conn.cursor()
        for table, cfg in MONITORED_TABLES.items():
            try:
                cur.execute(
                    "SELECT column_name FROM information_schema.columns WHERE table_name=%s",
                    (table,)
                )
                actual_cols = {r[0] for r in cur.fetchall()}
            except Exception as e:
                # 单表 introspect 失败不阻断其他表; 记录后继续
                errors_list.append({"table": table, "phase": "introspect", "error": str(e)[:120]})
                continue
            if not actual_cols:
                # 表不存在 (pre-migration / 待 alembic upgrade), 不算 warning
                continue
            date_col = cfg.get("date_col")
            if date_col and date_col not in actual_cols:
                warnings_list.append({
                    "table": table,
                    "issue": f"date_col '{date_col}' not in PG columns",
                    "fix_hint": f"update MONITORED_TABLES['{table}'].date_col "
                                f"(actual sample: {sorted(actual_cols)[:5]}) "
                                f"or run alembic upgrade",
                })
        conn.close()
    except Exception as e:
        errors_list.append({"table": "*", "phase": "pg_connect", "error": str(e)[:120]})
        logger.debug("validate_pipeline_consistency: PG introspect skipped (%s)", e)

    # ── 检查 3: handler 签名 ──
    # ADR-013 §决策 6 (LD-3): _DESIGN_SKIP_BACKFILL 内的 handler 按设计不走 days_back 历史回补,
    # 跳过签名检查避免误报 (如 sync_rt_k 实时拉取无 days_back 参数). validator 检查 1 已跳过 monitored
    # 列表里的 design-skip 表, 此处补检查 3 的对称跳过.
    for table, fn in _BACKFILL_MAP.items():
        if table in _DESIGN_SKIP_BACKFILL:
            continue
        try:
            sig = inspect.signature(fn)
        except (TypeError, ValueError):
            warnings_list.append({
                "table": table,
                "issue": "handler not introspectable",
                "fix_hint": "ensure backfill is a plain function, not partial/lambda",
            })
            continue
        if "days_back" not in sig.parameters:
            warnings_list.append({
                "table": table,
                "issue": f"backfill handler {fn.__name__} missing 'days_back' param",
                "fix_hint": "add `days_back: int = N` to function signature",
            })

    # ── 输出 ──
    for w in warnings_list:
        logger.warning("Pipeline validate [%s]: %s | hint: %s",
                       w["table"], w["issue"], w["fix_hint"])
    logger.info("Pipeline validate: checked %d monitored tables, %d warnings, %d errors",
                len(MONITORED_TABLES), len(warnings_list), len(errors_list))
    return {"checked": len(MONITORED_TABLES),
            "warnings": warnings_list, "errors": errors_list}


def _current_date_string() -> str:
    return date.today().strftime("%Y-%m-%d")


def run_post_market_core_daily() -> dict:
    return sync_post_market_core(_current_date_string())


def run_post_market_ext_daily() -> dict:
    return sync_post_market_ext(_current_date_string())


def run_supply_chain_expectation_gap_daily() -> dict:
    """盘后 17:30: 预期差模型每日链路 — refresh 当日分数 → 重估证据质量 → 快照落库。

    三步串联,单步失败记 warning 不阻断后续(返回 degraded 由补偿队列 10/30/120
    分钟重跑,复用现有重试机制)。复用 tools/ 下三个已 as-of 化的脚本:
    - refresh-expectation-scores(当日分数,全宇宙,每天自然积累逐日分数)
    - reevaluate(assessment_date=当日,as-of 同日截止,require-evidence 宇宙)
    - register(fetch_picks 快照,默认 strong_confirmed/watch_review 档)
    """
    today = _current_date_string()
    steps: dict[str, dict] = {}

    try:
        from supply_chain_data_collection_center import (
            refresh_expectation_and_prosperity_scores,
        )
        result = refresh_expectation_and_prosperity_scores(_PG_URL, limit=6000, trade_date=today)
        steps["refresh_scores"] = {
            "status": "ok",
            "written": result.get("written_expectation_gap_scores", 0),
        }
    except Exception as e:
        logger.warning("expectation-gap daily: refresh scores failed: %s", e)
        steps["refresh_scores"] = {"status": "error", "reason": str(e)[:200]}

    try:
        import reevaluate_supply_chain_evidence_quality as reevaluate
        result = reevaluate.run(
            _PG_URL, today, today, None, as_of_date=today, require_evidence=True,
        )
        steps["reevaluate"] = {
            "status": "ok",
            "written": result.get("written", 0),
            "status_counts": result.get("review_status_counts", {}),
        }
    except Exception as e:
        logger.warning("expectation-gap daily: reevaluate failed: %s", e)
        steps["reevaluate"] = {"status": "error", "reason": str(e)[:200]}

    try:
        import register_supply_chain_expectation_gap_model as expectation_gap_model
        result = expectation_gap_model.register_and_snapshot(_PG_URL, today, 30, 8.0, "close")
        steps["snapshot"] = {
            "status": "ok",
            "snapshot_count": result.get("snapshot_count", 0),
            "version_tag": result.get("version_tag"),
        }
    except Exception as e:
        logger.warning("expectation-gap daily: snapshot failed: %s", e)
        steps["snapshot"] = {"status": "error", "reason": str(e)[:200]}

    failed = [name for name, step in steps.items() if step["status"] != "ok"]
    if failed:
        logger.warning("expectation-gap daily: degraded, failed steps=%s", failed)
    return {
        "status": "degraded" if failed else "ok",
        "table": "screening_snapshots",
        "trade_date": today,
        "steps": steps,
        "failed_steps": failed,
        "written": steps.get("snapshot", {}).get("snapshot_count", 0),
    }


def start_scheduler():
    """注册定时任务并启动后台循环."""
    global _jobs
    # ADR-012 §决策 5.5: 启动期自检数据管道一致性 (WARN 不 raise, 方案 A 可逆性优先)
    try:
        validate_pipeline_consistency()
    except Exception as e:
        # 自检本身异常不阻断 scheduler 启动
        logger.warning("validate_pipeline_consistency raised (ignored): %s", e)

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

        # ── 海外市场早报数据波 (周一~五, 不受 A 股交易日限制) ──
        # 7:50 更新全部资讯+海外数据, 供 8:00 美股早报 / 9:05 韩股早报生成
        {"id": "morning_overseas", "name": "[L1]海外早报数据刷新", "cron": "50 7 * * 1-5",
         "fn": run_morning_overseas_refresh},
        # 9:02 韩股开盘首小时快照 (韩国 9:00 开盘 = 北京 8:00), 供 9:05 早报
        {"id": "kr_snapshot", "name": "[L1]韩股盘中快照", "cron": "2 9 * * 1-5",
         "fn": sync_kr_daily},

        # ── L2 盘后级 (每日 16:00 前后) ──
        # P0 核心表 — 15:30 盘后立即采集
        {"id": "post_market_core", "name": "[L2]P0核心盘后", "cron": "30 15 * * 1-5",
         "fn": run_post_market_core_daily},
        # stk_auction_o 在 9:25 竞价快照 job 中一并采集, 不单独调度
        # P1 扩展表 — 15:35 紧跟核心表
        {"id": "post_market_ext", "name": "[L2]P1扩展盘后", "cron": "35 15 * * 1-5",
         "fn": run_post_market_ext_daily},
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
        {"id": "chain_price_series", "name": "[L2]链等权日涨幅(景气)",
         "cron": "40 16 * * 1-5", "fn": sync_chain_price_series_daily},
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
        # 预期差模型每日链路 — refresh 分数 → 重估 → 快照 (履历逐日积累)
        {"id": "expectation_gap_daily", "name": "[L2]预期差模型每日链路",
         "cron": "30 17 * * 1-5", "fn": run_supply_chain_expectation_gap_daily},

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
        # P0 周线 — 每个交易日 16:00 同步 (节前最后交易日当天即可补本周周K;
        # 旧调度 0 1 * * 1=每周一凌晨, 导致本周周K要拖到下周一才入库, 修复见 docs/reviews)
        # 窗口缩到 21 天 (clean_before_write 按此清表重拉, 控制配额)
        {"id": "weekly_kline", "name": "[L2]周线数据", "cron": "0 16 * * 1-5",
         "fn": sync_weekly_kline, "args": (21,)},
        {"id": "holder_number", "name": "[L3]股东人数筹码集中度", "cron": "0 2 * * 1",
         "fn": sync_stk_holdernumber},
        {"id": "repurchase", "name": "[L3]股票回购", "cron": "30 2 * * 1",
         "fn": sync_repurchase},
        {"id": "index_basic", "name": "[L3]指数基本信息", "cron": "0 2 * * 6",
         "fn": sync_index_basic},
        # P1 公司基本信息 — 每周六 03:00 (全量刷新)
        {"id": "stock_profiles", "name": "[L3]公司基本信息", "cron": "0 3 * * 6",
         "fn": sync_stock_profiles},
        # 美股基础信息 (us_basic 名称映射) — 每周六 03:20
        {"id": "us_basic_sync", "name": "[L3]美股基础信息", "cron": "20 3 * * 6",
         "fn": sync_us_basic},
        # 阶段 1 AC-2 — ST 历史增量同步 (幸存者偏差修复, 供回测 JOIN 剔除戴帽股)
        # 周六 03:30 增量拉 namechange 解析戴帽/摘帽区间写 st_history
        {"id": "st_history_sync", "name": "[L3]ST历史同步", "cron": "30 3 * * 6",
         "fn": sync_st_history},
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
    _jobs.extend(build_scheduled_research_jobs())

    for j in _jobs:
        _job_status[j["id"]] = {"last_run": None, "last_status": "pending"}

    loop = asyncio.get_event_loop()
    loop.create_task(_scheduler_loop())
    loop.create_task(asyncio.to_thread(run_missed_scheduled_research_tasks))
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
            "compensation_status": status.get("compensation_status", "none"),
            "compensation_attempt": status.get("compensation_attempt", 0),
            "next_compensation_at": status.get("next_compensation_at"),
        })
    return {"jobs": result_jobs, "scheduler_running": _running}


def stop_scheduler():
    global _running
    _running = False
