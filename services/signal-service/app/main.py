import os
"""Signal Service — Real-time trading signal generation.

Usage: python -m uvicorn app.main:app --port 8004 --reload
"""

import logging, sys, os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

_PACKAGES = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "packages"))
for _pkg in ["kronos-factors", "kronos-core", "kronos-data"]:
    _path = os.path.join(_PACKAGES, _pkg)
    if os.path.isdir(_path) and _path not in sys.path:
        sys.path.insert(0, _path)

from app.routes import router, dashboard_router, data_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("signal-service")


_DB_PATH = os.environ.get("KRONOS_DB_PATH",
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "Kronos", "webui", "stock_screening.db"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Signal Service...")
    try:
        pg_url = os.environ.get('KRONOS_PG_URL', '')
        allow_sqlite = os.environ.get("KRONOS_ALLOW_SQLITE_FALLBACK", "").lower() in {"1", "true", "yes", "on"}
        if pg_url:
            from kronos_factors.pg_adapter import create_pg_adapter
            from kronos_factors.scorer._db_stub import set_db_adapter, set_market_data_adapter
            adapter = create_pg_adapter(pg_url)
            if adapter is None:
                raise RuntimeError("create_pg_adapter returned None")
            set_db_adapter(adapter)
            set_market_data_adapter(adapter)
            logger.info("Using PostgreSQL")
        elif allow_sqlite:
            from app.adapters import inject_adapters
            inject_adapters(_DB_PATH)
            logger.info("Using SQLite fallback: %s", _DB_PATH)
        else:
            logger.warning("No KRONOS_PG_URL configured and SQLite fallback disabled")
    except Exception as e:
        logger.warning("DB adapter injection skipped: %s", e)
    yield
    logger.info("Signal Service stopped.")


app = FastAPI(
    title="速赢AI - Signal Service",
    description="Real-time trading signal generation — 5-level buy/sell/hold signals",
    version="0.1.0",
    lifespan=lifespan,
)
app.add_middleware(CORSMiddleware, allow_origins=os.environ.get("CORS_ALLOWED_ORIGINS","http://localhost:5173,http://localhost:3000").split(","), allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])
app.state.deprecated_route_prefixes = {
    "/api/v1/dashboard": "screener-service",
    "/api/v1/data": "data-service",
}

# Compatibility aliases remain available during migration, but ownership is
# explicit so clients can move to the gateway's canonical services.
app.include_router(router)
app.include_router(dashboard_router)
app.include_router(data_router)


@app.get("/api/v1/health")
async def health():
    return {"status": "healthy", "service": "signal-service", "version": "0.1.0"}


if __name__ == "__main__":
    import uvicorn; uvicorn.run("app.main:app", host="0.0.0.0", port=8004, reload=True)
