"""Backtest Service — Rolling-window IC validation & strategy backtesting.

Usage:
    cd services/backtest-service
    python -m uvicorn app.main:app --host 0.0.0.0 --port 8007 --reload
"""
import logging
import os
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI

# 注入共享 packages(须在 import app.routes 前——routes 依赖 kronos-factors/core/data)
_PACKAGES = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "packages"))
for _pkg in ["kronos-factors", "kronos-core", "kronos-data"]:
    _path = os.path.join(_PACKAGES, _pkg)
    if os.path.isdir(_path) and _path not in sys.path:
        sys.path.insert(0, _path)

from app.routes import router
from kronos_contracts.app_factory import create_app

logger = logging.getLogger("backtest-service")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Backtest Service...")
    try:
        from app.db_adapters import inject_adapters
        inject_adapters()
        logger.info("DB adapters injected")
    except Exception as e:
        logger.warning("DB adapter injection skipped: %s", e)
    yield
    logger.info("Backtest Service stopped.")


app = create_app(
    "backtest-service",
    "0.1.0",
    [router],
    description="Rolling-window IC validation, strategy backtest, factor calibration",
    lifespan=lifespan,
)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8007, reload=True)
