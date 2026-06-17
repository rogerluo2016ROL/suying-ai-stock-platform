"""Daily backfill scheduler — 每个交易日盘后自动回填选股绩效.

在 screener-service 启动时通过 lifespan 注册, 无需额外进程.
Usage (in app/main.py lifespan):
    from app.scheduler import start_scheduler
    start_scheduler()
"""
import asyncio
import logging
from datetime import datetime, time

logger = logging.getLogger("screener.scheduler")


async def _backfill_job():
    """盘后回填任务: 回写 T+1/3/5/10/20 实际收益."""
    try:
        from kronos_factors.recorder import backfill_outcomes, backfill_multi_horizon

        # Step 1: T+1 backfill (fast, SQL subquery)
        t1 = backfill_outcomes(days_back=10)
        if t1:
            logger.info("Scheduler: T+1 backfill — %d snapshots", t1)

        # Step 2: Multi-horizon backfill (T+3/5/10/20)
        t_multi = backfill_multi_horizon(days_back=60)
        if t_multi:
            logger.info("Scheduler: Multi-horizon backfill — %d snapshots", t_multi)

    except Exception as e:
        logger.warning("Scheduler: backfill failed — %s", e)


async def _daily_loop():
    """Wait until after market close, then run backfill once per day."""
    last_run_date = None

    while True:
        now = datetime.now()
        today = now.date()

        # Run once per trading day, after 16:00
        if now.time() >= time(16, 0) and last_run_date != today:
            logger.info("Scheduler: starting daily backfill for %s", today)
            await _backfill_job()
            last_run_date = today

        # Check every 10 minutes
        await asyncio.sleep(600)


def start_scheduler():
    """Start the daily backfill scheduler as a background task."""
    try:
        # Quick initial backfill on startup
        asyncio.create_task(_backfill_job())
    except Exception:
        pass

    asyncio.create_task(_daily_loop())
    logger.info("Scheduler: daily backfill loop started (runs after 16:00 each trading day)")
