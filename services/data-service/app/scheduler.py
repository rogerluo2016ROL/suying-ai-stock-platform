"""内置 asyncio 定时任务调度 — 零外部依赖."""

import asyncio, logging, time
from datetime import datetime, date
from app.sync.rt_min import collect_rt_min
from app.sync.tushare import sync_post_market_core, sync_post_market_ext
from app.sync.pg_writer import sync_daily_to_pg, refresh_materialized_views

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


async def _run_job(job: dict):
    """执行单个任务并记录状态."""
    t0 = datetime.now()
    try:
        fn = job["fn"]
        result = fn() if not job.get("args") else fn(*job["args"])
        _job_status[job["id"]] = {
            "last_run": t0.isoformat(), "last_status": "ok",
            "result": str(result)[:300],
        }
    except Exception as e:
        _job_status[job["id"]] = {
            "last_run": t0.isoformat(), "last_status": "error",
            "error": str(e)[:300],
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


def start_scheduler():
    """注册定时任务并启动后台循环."""
    global _jobs
    today = date.today().strftime("%Y-%m-%d")

    _jobs = [
        {"id": "rt_min", "name": "实时分钟线", "cron": "*/1 9-15 * * 1-5",
         "fn": collect_rt_min},
        {"id": "auction", "name": "竞价快照", "cron": "25 9 * * 1-5",
         "fn": collect_rt_min},
        {"id": "post_market_core", "name": "P0核心盘后", "cron": "30 15 * * 1-5",
         "fn": sync_post_market_core, "args": (today,)},
        {"id": "post_market_ext", "name": "P1扩展盘后", "cron": "35 15 * * 1-5",
         "fn": sync_post_market_ext, "args": (today,)},
        {"id": "pg_sync", "name": "PG增量同步", "cron": "36 15 * * 1-5",
         "fn": sync_daily_to_pg, "args": (today,)},
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
        })
    return {"jobs": result_jobs, "scheduler_running": _running}


def stop_scheduler():
    global _running
    _running = False
