"""Training Scheduler — APScheduler-managed auto training and calibration.

Per ADR-004 Decision 1:
- APScheduler 3.x (AsyncIOScheduler) for lightweight in-process scheduling
- PostgreSQL job_store for persistence
- CronTrigger for weekly training (Sat 02:00) and calibration (Fri 15:30)

Provides:
- Create/update/delete scheduled jobs
- Start/stop scheduler
- List current schedules
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from croniter import croniter

from app.schemas import ModelType, ScheduleConfig, TrainingParams

logger = logging.getLogger("training-service.scheduler")

_scheduler: Optional[Any] = None
_schedule_config: Optional[ScheduleConfig] = None
_job_ids: Dict[str, str] = {}  # name -> apscheduler job_id


async def init_scheduler():
    """Initialize APScheduler with PostgreSQL job store on service startup."""
    global _scheduler

    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
        from app.config import DATABASE_SYNC_URL
    except ImportError:
        logger.warning("APScheduler not installed — scheduler disabled")
        return

    jobstores = {
        "default": SQLAlchemyJobStore(url=DATABASE_SYNC_URL)
    }

    _scheduler = AsyncIOScheduler(
        jobstores=jobstores,
        timezone="Asia/Shanghai",
    )

    logger.info("APScheduler initialized with PostgreSQL job store")

    # Load persisted schedule from DB
    await _load_schedule_from_db()


async def start_scheduler():
    """Start the scheduler."""
    if _scheduler is None:
        await init_scheduler()

    if _scheduler and not _scheduler.running:
        _scheduler.start()
        logger.info("APScheduler started")


async def stop_scheduler():
    """Stop the scheduler gracefully."""
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("APScheduler stopped")


async def _load_schedule_from_db():
    """Load training schedule configuration from PostgreSQL."""
    global _schedule_config
    try:
        from app.database import AsyncSessionLocal
        from sqlalchemy import text as sa_text
        import json

        async with AsyncSessionLocal() as db:
            result = await db.execute(
                sa_text("SELECT * FROM training_schedule WHERE id = 1")
            )
            row = result.fetchone()
            if row:
                d = dict(row._mapping)
                params_dict = d["params"] if isinstance(d["params"], dict) else json.loads(d["params"])
                _schedule_config = ScheduleConfig(
                    enabled=d["enabled"],
                    cron=d["cron"],
                    model_type=ModelType(d["model_type"]),
                    params=TrainingParams(**params_dict),
                    auto_deploy=d["auto_deploy"],
                    notify_on_complete=d["notify_on_complete"],
                    notify_channels=d["notify_channels"] if isinstance(d["notify_channels"], list) else json.loads(d["notify_channels"]),
                )

                if d["enabled"]:
                    await _register_scheduled_jobs(_schedule_config)
                    logger.info("Schedule loaded from DB: cron=%s", d["cron"])
            else:
                _schedule_config = None
    except Exception as e:
        logger.warning("Failed to load schedule from DB: %s", e)
        _schedule_config = None


async def _register_scheduled_jobs(config: ScheduleConfig):
    """Register APScheduler jobs for training and calibration."""
    if _scheduler is None:
        return

    # Parse cron expression
    cron_parts = config.cron.strip().split()
    if len(cron_parts) != 5:
        logger.error("Invalid cron expression: %s", config.cron)
        return

    minute, hour, day, month, day_of_week = cron_parts

    # Store config reference for the job functions
    global _schedule_config
    _schedule_config = config

    # Remove existing jobs
    for name, job_id in list(_job_ids.items()):
        try:
            _scheduler.remove_job(job_id)
        except Exception:
            logger.debug("Failed to remove job %s (%s)", name, job_id, exc_info=True)
    _job_ids.clear()

    # Schedule training job
    from apscheduler.triggers.cron import CronTrigger

    training_trigger = CronTrigger(
        minute=minute,
        hour=hour,
        day=day if day != "*" else None,
        month=month if month != "*" else None,
        day_of_week=day_of_week if day_of_week != "*" else None,
        timezone="Asia/Shanghai",
    )

    training_job = _scheduler.add_job(
        _scheduled_training,
        trigger=training_trigger,
        id=f"training-{config.model_type.value}",
        name=f"Scheduled training ({config.model_type.value})",
        replace_existing=True,
    )
    _job_ids["training"] = training_job.id

    # Schedule calibration job: Friday 15:30
    calibration_trigger = CronTrigger(
        day_of_week="fri",
        hour=15,
        minute=30,
        timezone="Asia/Shanghai",
    )
    cal_job = _scheduler.add_job(
        _scheduled_calibration,
        trigger=calibration_trigger,
        id="calibration-weekly",
        name="Weekly factor calibration",
        replace_existing=True,
    )
    _job_ids["calibration"] = cal_job.id

    logger.info("Scheduled jobs registered: training=%s, calibration=%s",
                _job_ids.get("training"), _job_ids.get("calibration"))


async def _scheduled_training():
    """Execute scheduled training job."""
    logger.info("Scheduled training triggered")

    if _schedule_config is None:
        logger.warning("No schedule config available")
        return

    try:
        from app.training_engine import run_training

        job_id = await run_training(
            params=_schedule_config.params,
            created_by="schedule",
            auto_deploy=_schedule_config.auto_deploy,
        )
        logger.info("Scheduled training started: job_id=%s", job_id)

        # Update last_run in DB
        await _update_schedule_last_run(job_id)
    except Exception as e:
        logger.error("Scheduled training failed: %s", e)


async def _scheduled_calibration():
    """Execute scheduled factor calibration."""
    logger.info("Scheduled calibration triggered")

    try:
        from app.factor_calibration import latest_ready_evaluation_id, run_calibration

        evaluation_id = await latest_ready_evaluation_id()
        result = await run_calibration(
            mode="all",
            window_days=90,
            min_samples=30,
            apply=True,
            evaluation_id=evaluation_id,
        )
        if result.get("status") != "ready":
            logger.warning("Scheduled calibration skipped apply: %s", result.get("status"))
            return
        logger.info("Scheduled calibration complete: %s", result.get("summary", ""))
    except Exception as e:
        logger.error("Scheduled calibration failed: %s", e)


async def _update_schedule_last_run(job_id: str):
    """Update last_run and last_job_id in training_schedule table."""
    try:
        from app.database import AsyncSessionLocal
        from sqlalchemy import text as sa_text

        async with AsyncSessionLocal() as db:
            await db.execute(
                sa_text(
                    "UPDATE training_schedule SET "
                    "last_run = NOW(), last_job_id = :job_id, updated_at = NOW() "
                    "WHERE id = 1"
                ),
                {"job_id": job_id},
            )
            await db.commit()
    except Exception as e:
        logger.warning("Failed to update schedule last_run: %s", e)


async def update_schedule(config: ScheduleConfig) -> Dict[str, Any]:
    """Update training schedule configuration (AC-6.2).

    Persists to DB and updates APScheduler jobs.
    """
    global _schedule_config

    # Persist to DB
    try:
        from app.database import AsyncSessionLocal
        from sqlalchemy import text as sa_text
        import json

        async with AsyncSessionLocal() as db:
            # Upsert
            await db.execute(
                sa_text(
                    "INSERT INTO training_schedule (id, enabled, cron, model_type, "
                    "params, auto_deploy, notify_on_complete, notify_channels, updated_at) "
                    "VALUES (1, :enabled, :cron, :model_type, :params, :auto_deploy, "
                    ":notify_on_complete, :notify_channels, NOW()) "
                    "ON CONFLICT (id) DO UPDATE SET "
                    "enabled=:enabled, cron=:cron, model_type=:model_type, "
                    "params=:params, auto_deploy=:auto_deploy, "
                    "notify_on_complete=:notify_on_complete, "
                    "notify_channels=:notify_channels, updated_at=NOW()"
                ),
                {
                    "enabled": config.enabled,
                    "cron": config.cron,
                    "model_type": config.model_type.value,
                    "params": json.dumps(config.params.model_dump(), default=str),
                    "auto_deploy": config.auto_deploy,
                    "notify_on_complete": config.notify_on_complete,
                    "notify_channels": json.dumps(config.notify_channels),
                },
            )
            await db.commit()
        logger.info("Schedule config saved to DB: cron=%s enabled=%s", config.cron, config.enabled)
    except Exception as e:
        logger.error("Failed to save schedule to DB: %s", e)
        raise

    _schedule_config = config

    # Update APScheduler jobs
    if config.enabled:
        await _register_scheduled_jobs(config)
    else:
        # Remove all scheduled jobs
        for name, job_id in list(_job_ids.items()):
            if _scheduler:
                try:
                    _scheduler.remove_job(job_id)
                except Exception:
                    logger.debug("Failed to remove job %s (%s)", name, job_id, exc_info=True)
            del _job_ids[name]

    # Calculate next run
    next_run = None
    if config.enabled:
        try:
            now = datetime.now()
            cit = croniter(config.cron, now)
            next_run = cit.get_next(datetime).isoformat()
        except Exception:
            logger.debug("Failed to compute next_run for cron %s", config.cron, exc_info=True)

    return {
        "enabled": config.enabled,
        "cron": config.cron,
        "next_run": next_run,
        "message": f"自动训练调度已{'启用' if config.enabled else '禁用'}: {config.cron}",
    }


async def get_schedule_status() -> Dict[str, Any]:
    """Get current schedule status (AC-6.2)."""
    global _schedule_config

    if _schedule_config is None:
        await _load_schedule_from_db()

    if _schedule_config is None:
        return {
            "enabled": False,
            "cron": "0 2 * * 6",
            "model_type": "lightgbm",
            "params": None,
            "auto_deploy": False,
            "next_run": None,
            "last_run": None,
            "last_job_id": None,
            "last_job_status": None,
        }

    # Calculate next run
    next_run = None
    if _schedule_config.enabled:
        try:
            now = datetime.now()
            cit = croniter(_schedule_config.cron, now)
            next_run = cit.get_next(datetime).isoformat()
        except Exception:
            logger.debug("Failed to compute next_run for cron %s", _schedule_config.cron, exc_info=True)

    # Get last run info from DB
    last_run = None
    last_job_id = None
    last_job_status = None
    try:
        from app.database import AsyncSessionLocal
        from sqlalchemy import text as sa_text
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                sa_text("SELECT last_run, last_job_id FROM training_schedule WHERE id = 1")
            )
            row = result.fetchone()
            if row:
                last_run = row[0].isoformat() if row[0] else None
                last_job_id = row[1]
                if last_job_id:
                    from app.training_engine import get_job
                    job = get_job(last_job_id)
                    if job:
                        last_job_status = job.status.value
    except Exception:
        logger.debug("Failed to fetch last run info from DB", exc_info=True)

    return {
        "enabled": _schedule_config.enabled,
        "cron": _schedule_config.cron,
        "model_type": _schedule_config.model_type.value if _schedule_config.model_type else "lightgbm",
        "params": _schedule_config.params.model_dump() if _schedule_config.params else None,
        "auto_deploy": _schedule_config.auto_deploy,
        "next_run": next_run,
        "last_run": last_run,
        "last_job_id": last_job_id,
        "last_job_status": last_job_status,
    }
