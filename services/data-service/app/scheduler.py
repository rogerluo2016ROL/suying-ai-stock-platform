"""APScheduler 定时任务定义."""

import logging
from datetime import date
from apscheduler.schedulers.background import BackgroundScheduler

from app.config import SCHEDULES
from app.sync.rt_min import collect_rt_min
from app.sync.tushare import sync_post_market_core, sync_post_market_ext

logger = logging.getLogger("data-service.scheduler")

_scheduler: BackgroundScheduler = None
_job_status: dict = {}  # job_name → {last_run, last_status, next_run}


def _wrap(job_name: str, fn, *args):
    """Wrapper to update job status and handle exceptions."""
    from datetime import datetime

    def _run():
        t0 = datetime.now()
        try:
            result = fn(*args)
            _job_status[job_name] = {
                "last_run": t0.isoformat(), "last_status": "ok",
                "result": str(result)[:200], "next_run": None,
            }
            logger.info("%s: ok", job_name)
        except Exception as e:
            _job_status[job_name] = {
                "last_run": t0.isoformat(), "last_status": "error",
                "error": str(e)[:200], "next_run": None,
            }
            logger.error("%s: %s", job_name, e)

    return _run


def start_scheduler():
    global _scheduler
    _scheduler = BackgroundScheduler(timezone="Asia/Shanghai")
    today = date.today().strftime("%Y-%m-%d")

    # 实时分钟线 (每1分钟, 盘中)
    _scheduler.add_job(
        _wrap("rt_min", collect_rt_min),
        trigger="cron", minute="*/1", hour="9-15", day_of_week="mon-fri",
        id="rt_min", name="实时分钟线",
    )

    # 竞价快照 (9:25)
    _scheduler.add_job(
        _wrap("auction", collect_rt_min),
        trigger="cron", minute=25, hour=9, day_of_week="mon-fri",
        id="auction", name="竞价快照",
    )

    # P0 核心盘后 (15:30)
    _scheduler.add_job(
        _wrap("post_market_core", sync_post_market_core, today),
        trigger="cron", minute=30, hour=15, day_of_week="mon-fri",
        id="post_market_core", name="P0核心盘后",
    )

    # P1 扩展盘后 (15:35)
    _scheduler.add_job(
        _wrap("post_market_ext", sync_post_market_ext, today),
        trigger="cron", minute=35, hour=15, day_of_week="mon-fri",
        id="post_market_ext", name="P1扩展盘后",
    )

    _scheduler.start()
    logger.info("Scheduler started: %d jobs", len(_scheduler.get_jobs()))


def get_job_status() -> dict:
    """Get all job statuses for API."""
    jobs = []
    for job in _scheduler.get_jobs() if _scheduler else []:
        status = _job_status.get(job.id, {})
        jobs.append({
            "id": job.id, "name": job.name,
            "next_run": str(job.next_run_time) if job.next_run_time else None,
            "last_run": status.get("last_run"),
            "last_status": status.get("last_status", "pending"),
            "last_result": status.get("result", ""),
        })
    return {"jobs": jobs, "scheduler_running": _scheduler is not None and _scheduler.running}


def stop_scheduler():
    if _scheduler:
        _scheduler.shutdown(wait=False)
