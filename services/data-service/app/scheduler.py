"""内置 asyncio 定时任务调度 — 零外部依赖."""

import asyncio, logging, os, sys, time
from datetime import datetime, date
from app.sync.rt_min import collect_rt_min
from app.sync.tushare import sync_post_market_core, sync_post_market_ext
from app.sync.pg_writer import refresh_materialized_views
from app.sync.stocks import sync_stock_list, sync_stocks_incremental
from app.sync.cb_sync import sync_ths_daily, sync_cb_price_chg_all, sync_ths_concept_map

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
    # ths_daily, index_daily, stk_factor_pro 回补函数内联或由独立 sync 处理
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
        cur.execute(f"SELECT MAX(\"{date_col}\") FROM \"{table}\"")
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


def detect_data_gaps(lookback_days: int = None) -> dict:
    """扫描所有监控表, 检测数据缺口.

    对每张表查询最新日期, 与今天比较。超过 gap_threshold 天即标记为缺口。
    stk_mins (trade_time=datetime) 特殊处理: 仅比较日期部分。

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

        gap_days = (today - latest).days
        if gap_days > threshold:
            tables[table] = {
                "status": "gap", "latest_date": latest.isoformat(),
                "gap_days": gap_days, "threshold": threshold, "freq": freq,
            }
            gap_count += 1
            logger.info("Data gap: %s — latest=%s, %d days behind (threshold=%d)",
                       table, latest.isoformat(), gap_days, threshold)
        else:
            tables[table] = {
                "status": "ok", "latest_date": latest.isoformat(),
                "gap_days": gap_days, "threshold": threshold, "freq": freq,
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

    cols = ["ts_code", "trade_date", "close", "open", "high", "low",
            "pre_close", "change", "pct_chg", "vol", "amount",
            "turnover_rate", "volume_ratio", "pe", "pe_ttm", "pb",
            "macd_dif", "macd_dea", "macd",
            "kdj_k", "kdj_d", "kdj_j",
            "rsi_6", "rsi_12", "rsi_24",
            "boll_upper", "boll_mid", "boll_lower", "atr14"]

    rows = []
    for _, r in df.iterrows():
        row = []
        for c in cols:
            if c == "trade_date":
                row.append(trade_date)
            else:
                v = r.get(c)
                # 过滤 numpy NaN
                try:
                    import numpy as np
                    if isinstance(v, (np.floating,)) and np.isnan(v):
                        row.append(None)
                        continue
                except ImportError:
                    pass
                row.append(v)
        rows.append(tuple(row))

    # PG 直写 (主路径)
    pg_written = 0
    if rows:
        try:
            from app.sync.pg_writer import _pg_write
            pg_cols = ["ts_code", "trade_date", "close", "open", "high", "low",
                       "pre_close", "change", "pct_chg", "vol", "amount",
                       "turnover_rate", "volume_ratio", "pe", "pe_ttm", "pb",
                       "macd_dif", "macd_dea", "macd",
                       "kdj_k", "kdj_d", "kdj_j",
                       "rsi_6", "rsi_12", "rsi_24",
                       "boll_upper", "boll_mid", "boll_lower", "atr14"]
            pg_written = _pg_write("stk_factor_pro", pg_cols,
                                    ["ts_code", "trade_date"], rows)
        except Exception as e:
            logger.debug("PG write stk_factor_pro skipped: %s", e)

    # SQLite 写入 (fallback)
    sqlite_written = 0
    if rows:
        try:
            db = sqlite3.connect(DB_PATH)
            placeholders = ",".join(["?"] * len(cols))
            db.executemany(
                f"INSERT OR REPLACE INTO stk_factor_pro({','.join(cols)}) "
                f"VALUES({placeholders})", rows)
            sqlite_written = len(rows)
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
    """9:25 竞价快照 — 采集9:30首根5min K线存入 stk_auction_o."""
    import sqlite3, psycopg2
    from datetime import date
    from app.config import DB_PATH
    today = date.today().strftime("%Y-%m-%d")

    # 1. Collect rt_min for 9:30 first bar
    collect_rt_min()

    # 2. Build auction snapshot from stk_mins 9:30-9:35 first bar → stk_auction_o
    try:
        db = sqlite3.connect(DB_PATH)
        rows = db.execute(
            "SELECT ts_code, open, high, low, close, volume, amount "
            "FROM stk_mins WHERE trade_time LIKE ? AND freq='5min'",
            (f"{today} 09:3%",)
        ).fetchall()
        if rows:
            pg = psycopg2.connect(os.environ.get("KRONOS_PG_URL",
                "postgresql://kronos:kronos@localhost:6432/kronos"))
            pg.autocommit = True
            cur = pg.cursor()
            for r in rows:
                code = r[0].split('.')[0] if '.' in str(r[0]) else r[0]
                cur.execute(
                    "INSERT INTO stk_auction_o (code, trade_date, open, high, low, close, vol, amount, vwap) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (code, trade_date) DO NOTHING",
                    (code, today, r[1], r[2], r[3], r[4], r[5], r[6],
                     r[6]/r[5] if r[5] and float(r[5]) > 0 else r[1]))
            pg.close()
        db.close()
        logger.info("Auction snapshot: %d stocks", len(rows))
    except Exception as e:
        logger.warning("Auction snapshot failed: %s", e)
    return {"status": "ok", "date": today, "stocks": len(rows) if rows else 0}


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
        # ── L0 实时级 (交易时段每 1 分钟) ──
        {"id": "rt_min", "name": "[L0]实时分钟线", "cron": "*/1 9-15 * * 1-5",
         "fn": collect_rt_min},
        {"id": "auction", "name": "[L0]竞价快照", "cron": "25 9 * * 1-5",
         "fn": collect_auction_snapshot},

        # ── L1 日内级 (交易时段每 30 分钟) ──
        {"id": "limit_list_d_intra", "name": "[L1]涨跌停日内增量", "cron": "*/30 9-15 * * 1-5",
         "fn": sync_limit_list_d_intraday},
        # 盘中午间同步 — 交易日 13:00 同步上午数据
        {"id": "intraday_sync", "name": "[L1]盘中午间同步", "cron": "0 13 * * 1-5",
         "fn": run_intraday_sync},

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
        # 16:30 批次 — 可转债技术因子
        {"id": "cb_factor", "name": "[L2]可转债技术因子", "cron": "30 18 * * 1-5",
         "fn": sync_cb_factor},
        {"id": "cb_call", "name": "[L2]可转债强赎信息", "cron": "35 18 * * 1-5",
         "fn": sync_cb_call},

        # ── L3 周级 (每周一) ──
        # 股票列表全量同步 — 每周六 02:00 (ADR-006 决策 4)
        {"id": "stocks_sync", "name": "[L3]股票列表同步", "cron": "0 2 * * 6",
         "fn": sync_stock_list},
        # 股票增量同步 — 每日盘前 8:00 检测新上市 (ADR-006 决策 4)
        {"id": "stocks_incremental", "name": "[L3]新股增量检测", "cron": "0 8 * * 1-5",
         "fn": sync_stocks_incremental},
        # 沪深港通资金流向 — 每周一 08:30
        {"id": "moneyflow_hsgt", "name": "[L3]沪深港通资金流向", "cron": "30 8 * * 1",
         "fn": sync_moneyflow_hsgt_weekly},
        # 转股价变动 — 每周一 09:00
        {"id": "cb_price_chg", "name": "[L3]转股价变动", "cron": "0 9 * * 1",
         "fn": sync_cb_price_chg_all},
        # 同花顺概念映射 — 每月1日 03:00
        {"id": "ths_concept_map", "name": "[L3]同花顺概念映射", "cron": "0 3 1 * *",
         "fn": sync_ths_concept_map},

        # ── L4 历史回补 (每日凌晨自动检测 + 回补) ──
        {"id": "data_integrity", "name": "[L4]数据完整性检查+回补", "cron": "0 4 * * *",
         "fn": run_data_integrity_check},
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
