"""Prediction Service — Kronos 30-day K-line forecasting.

Usage:
    cd services/prediction-service
    python -m uvicorn app.main:app --host 0.0.0.0 --port 8002 --reload
"""

import logging, sys, os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Ensure packages/ are importable
_PACKAGES = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "packages"))
for _pkg in ["kronos-core", "kronos-factors", "kronos-data"]:
    _path = os.path.join(_PACKAGES, _pkg)
    if os.path.isdir(_path) and _path not in sys.path:
        sys.path.insert(0, _path)

from app.routes import router

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("prediction-service")

_model_loaded = False
_predictor = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _model_loaded, _predictor
    logger.info("Starting Prediction Service...")
    try:
        from kronos.model.kronos import Kronos, KronosTokenizer, KronosPredictor
        tokenizer = KronosTokenizer.from_pretrained("NeoQuasar/Kronos-Tokenizer-base")
        model = Kronos.from_pretrained("NeoQuasar/Kronos-small")
        _predictor = KronosPredictor(model, tokenizer, max_context=512, device="cpu")
        _model_loaded = True
        logger.info("Kronos-small model loaded (CPU)")
    except Exception as e:
        logger.warning("Kronos model not loaded (skip predictions): %s", e)
    yield
    logger.info("Prediction Service stopped.")


app = FastAPI(
    title="速赢AI - Prediction Service",
    description="Kronos K-line prediction — 30-day OHLCV forecasting",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])
app.include_router(router)


@app.get("/api/v1/health")
async def health():
    return {"status": "healthy", "service": "prediction-service",
            "model_loaded": _model_loaded, "version": "0.1.0"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8002, reload=True)
