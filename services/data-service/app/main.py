"""Data Service — 后台数据采集 + 定时调度.

Usage:
    cd services/data-service
    python -m uvicorn app.main:app --host 0.0.0.0 --port 8010

Env vars (all optional):
    DATA_SCHEDULE_RT_MIN="*/1 9-15 * * 1-5"
    DATA_SCHEDULE_CORE="30 15 * * 1-5"
    KRONOS_DB_PATH=/path/to/stock_screening.db
    TUSHARE_TOKEN_FILE=/run/secrets/tushare_token
"""
import logging
import os
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI

# Ensure Kronos src is importable
_PROJ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
_KRONOS = os.path.join(_PROJ, "Kronos")
if os.path.isdir(_KRONOS):
    sys.path.insert(0, os.path.join(_KRONOS, "src"))
    sys.path.insert(0, _KRONOS)

from app.routers.data import router as data_router
from app.scheduler import start_scheduler, stop_scheduler
from kronos_contracts.app_factory import create_app

logger = logging.getLogger("data-service")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Data Service...")
    try:
        start_scheduler()
        logger.info("Scheduler running")
    except Exception as e:
        logger.warning("Scheduler not started: %s", e)
    yield
    stop_scheduler()
    logger.info("Data Service stopped.")


app = create_app(
    "data-service",
    "0.1.0",
    [data_router],
    description="后台数据采集 + 定时调度 + 手动触发",
    lifespan=lifespan,
)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8010, reload=True)
