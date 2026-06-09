"""Alert Service — Multi-channel trade alert & notification.

Usage: python -m uvicorn app.main:app --port 8005 --reload
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

from app.routes import router

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("alert-service")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Alert Service...")
    yield
    logger.info("Alert Service stopped.")


app = FastAPI(
    title="速赢AI - Alert Service",
    description="Multi-channel alert & notification — WeCom/DingTalk/Email/App Push",
    version="0.1.0",
    lifespan=lifespan,
)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])
app.include_router(router)


@app.get("/api/v1/health")
async def health():
    return {"status": "healthy", "service": "alert-service", "version": "0.1.0"}


if __name__ == "__main__":
    import uvicorn; uvicorn.run("app.main:app", host="0.0.0.0", port=8005, reload=True)
