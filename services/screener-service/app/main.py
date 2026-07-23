"""Screener Service — FastAPI entry point.

Usage:
    cd services/screener-service
    python -m uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload
"""
import logging
import os
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI

# 注入共享 packages(须在 import kronos-factors 前)
_PACKAGES = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "packages"))
for _pkg in ["kronos-factors", "kronos-core", "kronos-data", "kronos-auth"]:
    _path = os.path.join(_PACKAGES, _pkg)
    if os.path.isdir(_path) and _path not in sys.path:
        sys.path.insert(0, _path)

from app.config import HOST, PORT, DEBUG, DB_PATH
from app.domains.router import router as screener_router
from app.routers.dashboard import router as dashboard_router
from app.routers.lark import router as lark_router
from kronos_contracts.app_factory import create_app

logger = logging.getLogger("screener-service")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: inject DB adapters. Shutdown: cleanup."""
    logger.info("Starting Screener Service...")
    try:
        # Try PG first. SQLite is legacy-only and must be explicitly enabled.
        pg_url = os.environ.get('KRONOS_PG_URL', '')
        allow_sqlite = os.environ.get("KRONOS_ALLOW_SQLITE_FALLBACK", "").lower() in {"1", "true", "yes", "on"}
        if pg_url:
            import socket
            socket.setdefaulttimeout(5)  # Prevent PG connection from hanging startup
            try:
                from kronos_factors.pg_adapter import create_pg_adapter
                from kronos_factors.scorer._db_stub import set_db_adapter, set_market_data_adapter
                adapter = create_pg_adapter(pg_url)
                if adapter is not None:
                    set_db_adapter(adapter)
                    set_market_data_adapter(adapter)
                    logger.info("Using PostgreSQL: %s", pg_url.split('@')[1] if '@' in pg_url else pg_url)
                else:
                    raise RuntimeError("create_pg_adapter returned None")
            except Exception as e:
                logger.warning("PG unavailable (%s); SQLite fallback disabled unless explicitly enabled", e)
                if allow_sqlite:
                    from app.adapters import inject_adapters
                    inject_adapters(DB_PATH)
                    logger.info("Using SQLite fallback: %s", DB_PATH)
            finally:
                socket.setdefaulttimeout(None)
        elif allow_sqlite:
            from app.adapters import inject_adapters
            inject_adapters(DB_PATH)
            logger.info("Using SQLite fallback: %s", DB_PATH)
        else:
            logger.warning("No KRONOS_PG_URL configured and SQLite fallback disabled")
    except Exception as e:
        logger.warning("DB adapter injection skipped: %s", e)

    # Verify package imports
    try:
        from kronos_factors.scorer import score_five_factor
        from kronos_factors.engine.modes import ShortModeEngine
        logger.info("kronos-factors loaded: v%s", __import__("kronos_factors").__version__)
    except ImportError as e:
        logger.error("kronos-factors not found: %s. Run: pip install -e packages/kronos-factors", e)

    # Start daily backfill scheduler (auto-tracks pick performance after market close)
    try:
        from app.scheduler import start_scheduler
        start_scheduler()
    except Exception as e:
        logger.warning("Scheduler not started: %s", e)

    yield

    logger.info("Screener Service stopped.")


app = create_app(
    "screener-service",
    "0.1.0",
    [screener_router, dashboard_router, lark_router],
    description="Stock screening microservice — 6 strategies, unified API",
    lifespan=lifespan,
)


# ── Run directly ──
if __name__ == "__main__":
    import uvicorn
    logger.info("Starting on %s:%s", HOST, PORT)
    uvicorn.run("app.main:app", host=HOST, port=PORT, reload=DEBUG)
