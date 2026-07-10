"""Strategy Service — LLM-powered trading plan generation.

Usage: python -m uvicorn app.main:app --port 8003 --reload
"""

import logging, sys, os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

_PACKAGES = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "packages"))
for _pkg in ["kronos-factors", "kronos-core", "kronos-data", "kronos-auth"]:
    _path = os.path.join(_PACKAGES, _pkg)
    if os.path.isdir(_path) and _path not in sys.path:
        sys.path.insert(0, _path)

from app.routes import router

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("strategy-service")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Strategy Service...")
    yield
    logger.info("Strategy Service stopped.")


app = FastAPI(
    title="速赢AI - Strategy Service",
    description="LLM-powered trading strategy generation & optimization",
    version="0.1.0",
    lifespan=lifespan,
)
CORS_ALLOWED_ORIGINS = os.environ.get(
    "CORS_ALLOWED_ORIGINS", "http://localhost:5173,http://localhost:3000"
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)


@app.get("/api/v1/health/live")
async def health_live_contract():
    return {"live": True, "service": "strategy-service", "version": "0.1.0"}

@app.get("/api/v1/health/ready")
async def health_ready_contract():
    from kronos_contracts.health import check_postgres, build_health
    return build_health("strategy-service", "0.1.0", {"postgres": await check_postgres()}).model_dump()
@app.get("/api/v1/health")
async def health():
    return {"status": "healthy", "service": "strategy-service", "version": "0.1.0"}


if __name__ == "__main__":
    import uvicorn; uvicorn.run("app.main:app", host="0.0.0.0", port=8003, reload=True)
