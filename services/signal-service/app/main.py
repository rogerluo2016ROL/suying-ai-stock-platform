"""Signal Service — Real-time trading signal generation.

Usage: python -m uvicorn app.main:app --port 8004 --reload
"""
import logging
import os
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from starlette.middleware.base import BaseHTTPMiddleware

# 注入共享 packages(须在 import app.routes 前——routes 依赖 kronos-factors/core/data)
_PACKAGES = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "packages"))
for _pkg in ["kronos-factors", "kronos-core", "kronos-data"]:
    _path = os.path.join(_PACKAGES, _pkg)
    if os.path.isdir(_path) and _path not in sys.path:
        sys.path.insert(0, _path)

from app.routes import router, dashboard_router, data_router
from kronos_contracts.app_factory import create_app

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


app = create_app(
    "signal-service",
    "0.1.0",
    [router, dashboard_router, data_router],
    description="Real-time trading signal generation — 5-level buy/sell/hold signals",
    lifespan=lifespan,
)

app.state.deprecated_route_prefixes = {
    "/api/v1/dashboard": "screener-service",
    "/api/v1/data": "data-service",
}


class DeprecatedRouteMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        for prefix, owner in app.state.deprecated_route_prefixes.items():
            if request.url.path == prefix or request.url.path.startswith(prefix + "/"):
                response.headers["Deprecation"] = "true"
                response.headers["X-Deprecated-Route"] = "true"
                response.headers["X-Route-Owner"] = owner
                break
        return response


app.add_middleware(DeprecatedRouteMiddleware)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8004, reload=True)
