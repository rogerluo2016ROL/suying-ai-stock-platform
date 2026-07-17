"""Training Service — FastAPI entry point (port 8008).

Per ADR-004:
- Decision 1: APScheduler for scheduling
- Decision 3: MLflow for model registry
- Decision 5: Weekly factor calibration (Fri 15:30)

Usage:
    cd services/training-service
    python -m uvicorn app.main:app --host 0.0.0.0 --port 8008 --reload
"""
import logging
import os
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import HOST, PORT, DEBUG
from app.routes import router as training_router
from kronos_contracts.app_factory import create_app

logger = logging.getLogger("training-service")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: init scheduler, load jobs. Shutdown: stop scheduler."""
    logger.info("Starting Training Service...")

    # Ensure Kronos packages are importable
    _PROJ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    _kronos = os.path.join(_PROJ, "Kronos")
    if os.path.isdir(_kronos) and _kronos not in sys.path:
        sys.path.insert(0, _kronos)
    _packages = os.path.join(_PROJ, "packages")
    for _pkg in ["kronos-factors", "kronos-core", "kronos-data"]:
        _path = os.path.join(_packages, _pkg)
        if os.path.isdir(_path) and _path not in sys.path:
            sys.path.insert(0, _path)

    # Load persisted training jobs from DB
    try:
        from app.training_engine import _load_jobs_from_db
        await _load_jobs_from_db()
        logger.info("Training jobs loaded from DB")
    except Exception as e:
        logger.warning("Failed to load training jobs: %s", e)

    # Initialize MLflow client
    try:
        from app.mlflow_client import get_mlflow_client
        client = get_mlflow_client()
        logger.info("MLflow client initialized (%s mode)", "live" if hasattr(client, '_tracking_uri') else "mock")
    except Exception as e:
        from app.config import MLFLOW_MODE
        if MLFLOW_MODE == "live":
            raise RuntimeError(f"MLflow live initialization failed: {e}") from e
        logger.warning("MLflow init skipped: %s", e)

    # Initialize scheduler
    try:
        from app.scheduler import init_scheduler, start_scheduler
        await init_scheduler()
        await start_scheduler()
        logger.info("Scheduler initialized")
    except Exception as e:
        logger.warning("Scheduler init skipped: %s", e)

    yield

    # Shutdown
    try:
        from app.scheduler import stop_scheduler
        await stop_scheduler()
    except Exception:
        pass

    logger.info("Training Service stopped.")


app = create_app(
    "training-service",
    "0.1.0",
    [training_router],
    description="Model training pipeline microservice — LightGBM/CatBoost/Kronos training, MLflow registry, factor calibration",
    lifespan=lifespan,
)


# ── Run directly ──
if __name__ == "__main__":
    import uvicorn

    logger.info("Starting on %s:%s", HOST, PORT)
    uvicorn.run("app.main:app", host=HOST, port=PORT, reload=DEBUG)
