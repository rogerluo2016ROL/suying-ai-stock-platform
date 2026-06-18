import os
"""Data Service — 后台数据采集 + 定时调度.

Usage:
    cd services/data-service
    python -m uvicorn app.main:app --host 0.0.0.0 --port 8010

Env vars (all optional):
    DATA_SCHEDULE_RT_MIN="*/1 9-15 * * 1-5"
    DATA_SCHEDULE_CORE="30 15 * * 1-5"
    KRONOS_DB_PATH=/path/to/stock_screening.db
    TUSHARE_TOKEN=xxx
"""

import logging, sys, os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Ensure Kronos src is importable
_PROJ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
_KRONOS = os.path.join(_PROJ, "Kronos")
if os.path.isdir(_KRONOS):
    sys.path.insert(0, os.path.join(_KRONOS, "src"))
    sys.path.insert(0, _KRONOS)

from app.routers.data import router as data_router
from app.scheduler import start_scheduler, stop_scheduler

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
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


app = FastAPI(
    title="速赢AI - Data Service",
    description="后台数据采集 + 定时调度 + 手动触发",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(CORSMiddleware, allow_origins=os.environ.get("CORS_ALLOWED_ORIGINS","http://localhost:5173,http://localhost:3000").split(","), allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])
app.include_router(data_router)


@app.get("/api/v1/health")
async def health():
    return {"status": "healthy", "service": "data-service", "version": "0.1.0"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8010, reload=True)
