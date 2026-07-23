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


async def _crowding_watch_loop():
    """盘中拥挤度预警: 每 N 分钟调 alert-service /crowding-scan (科创板 high).

    通过 CROWDING_WATCH_ENABLED=1 启用 (默认关). 间隔 CROWDING_WATCH_INTERVAL_SEC (默认 300s).
    仅交易时段 (周一-五 9:30-15:00) 运行. 微服务间 HTTP 用 urllib (CLAUDE.md 约定).
    """
    import os, urllib.request
    interval = int(os.environ.get("CROWDING_WATCH_INTERVAL_SEC", "300"))
    alert_url = os.environ.get("ALERT_SERVICE_URL", "http://localhost:8005").rstrip("/")
    loop = asyncio.get_event_loop()
    while True:
        now = datetime.now()
        in_session = now.weekday() < 5 and time(9, 30) <= now.time() <= time(15, 0)
        if in_session:
            try:
                def _scan():
                    url = (f"{alert_url}/api/v1/alert/crowding-scan"
                           f"?level=high&board=688&channel=app,feishu")
                    with urllib.request.urlopen(
                        urllib.request.Request(url, method="POST"), timeout=180) as resp:
                        return resp.read()
                body = await loop.run_in_executor(None, _scan)
                logger.info("Crowding watch: %s", body[:200])
            except Exception as e:
                logger.warning("Crowding watch failed: %s", e)
        await asyncio.sleep(interval)


def start_scheduler():
    """Start the daily backfill scheduler as a background task."""
    import os
    try:
        # Quick initial backfill on startup
        asyncio.create_task(_backfill_job())
    except Exception:
        pass

    asyncio.create_task(_daily_loop())
    logger.info("Scheduler: daily backfill loop started (runs after 16:00 each trading day)")
    # 拥挤度盘中预警 (可选, env 启用; 服务运行时生效)
    if os.environ.get("CROWDING_WATCH_ENABLED") == "1":
        asyncio.create_task(_crowding_watch_loop())
        logger.info("Scheduler: crowding watch loop started (科创板 high, 每 %ss)",
                    os.environ.get("CROWDING_WATCH_INTERVAL_SEC", "300"))
