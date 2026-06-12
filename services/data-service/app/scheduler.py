"""内置 asyncio 定时任务调度 — 零外部依赖."""

import asyncio, logging, os, time
from datetime import datetime, date
from app.sync.rt_min import collect_rt_min
from app.sync.tushare import sync_post_market_core, sync_post_market_ext
from app.sync.pg_writer import refresh_materialized_views
from app.sync.stocks import sync_stock_list, sync_stocks_incremental

logger = logging.getLogger("data-service.scheduler")

_job_status: dict = {}
_jobs: list[dict] = []
_running = False


def _cron_match(cron_expr: str, now: datetime) -> bool:
    """简易 cron 匹配: 'minute hour * * day_of_week'. 支持 */N 语法."""
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
    """执行单个任务并记录状态."""
    t0 = datetime.now()
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
    except Exception as e:
        _job_status[job["id"]] = {
            "last_run": t0.isoformat(), "last_status": "error",
            "error": str(e)[:300],
            "pg_write_status": "fail",
            "pg_written": 0,
        }
        logger.warning("%s: %s", job["id"], e)


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
        # 股票列表全量同步 — 每周六 02:00 (ADR-006 决策 4)
        {"id": "stocks_sync", "name": "股票列表同步", "cron": "0 2 * * 6",
         "fn": sync_stock_list},
        # 股票增量同步 — 每日盘前 8:00 检测新上市 (ADR-006 决策 4)
        {"id": "stocks_incremental", "name": "新股增量检测", "cron": "0 8 * * 1-5",
         "fn": sync_stocks_incremental},
        # 实时分钟线 — 自带 PG 双写 (write_stk_mins)
        {"id": "rt_min", "name": "实时分钟线", "cron": "*/1 9-15 * * 1-5",
         "fn": collect_rt_min},
        {"id": "auction", "name": "竞价快照", "cron": "25 9 * * 1-5",
         "fn": collect_auction_snapshot},
        # 盘中午间同步 — 交易日 13:00 同步上午数据 (SQLite + PG 直写)
        {"id": "intraday_sync", "name": "盘中午间同步", "cron": "0 13 * * 1-5",
         "fn": run_intraday_sync},
        # 盘后同步 — 自带 PG 直写 (不再需要 subprocess 桥接)
        {"id": "post_market_core", "name": "P0核心盘后", "cron": "30 15 * * 1-5",
         "fn": sync_post_market_core, "args": (today,)},
        {"id": "post_market_ext", "name": "P1扩展盘后", "cron": "35 15 * * 1-5",
         "fn": sync_post_market_ext, "args": (today,)},
        # PG 物化视图刷新
        {"id": "pg_refresh", "name": "PG物化视图刷新", "cron": "37 15 * * 1-5",
         "fn": refresh_materialized_views},
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
