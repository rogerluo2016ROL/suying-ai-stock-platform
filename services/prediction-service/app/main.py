import os
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


def _find_kronos_root() -> str:
    """Find Kronos project root for model checkpoints."""
    candidates = [
        os.path.join(os.path.dirname(__file__), "..", "..", "..", "Kronos"),
        os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "Kronos"),
    ]
    for c in candidates:
        if os.path.isdir(os.path.join(c, "outputs", "models")):
            return os.path.abspath(c)
    return ""


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _model_loaded, _predictor
    logger.info("Starting Prediction Service...")
    try:
        import torch
        from kronos.model.kronos import Kronos, KronosTokenizer, KronosPredictor

        kronos_root = _find_kronos_root()
        device = "mps" if torch.backends.mps.is_available() else "cpu"
        model_name = "Kronos-mini"

        # ── Load base architecture from HuggingFace ──
        logger.info("Loading tokenizer: NeoQuasar/Kronos-Tokenizer-base")
        tokenizer = KronosTokenizer.from_pretrained("NeoQuasar/Kronos-Tokenizer-base")
        logger.info("Loading predictor: NeoQuasar/%s", model_name)
        model = Kronos.from_pretrained(f"NeoQuasar/{model_name}")

        # ── Apply fine-tuned weights if available ──
        ft_tok = os.path.join(kronos_root, "outputs", "models",
                              "finetune_tokenizer_demo", "checkpoints", "best_model",
                              "pytorch_model.bin")
        ft_pred = os.path.join(kronos_root, "outputs", "models",
                               "finetune_predictor_demo", "checkpoints", "best_model",
                               "pytorch_model.bin")

        if os.path.exists(ft_tok):
            logger.info("Loading fine-tuned tokenizer weights: %s", ft_tok)
            tokenizer.load_state_dict(torch.load(ft_tok, map_location="cpu"))
            logger.info("Fine-tuned tokenizer loaded (%.1f MB)", os.path.getsize(ft_tok)/1e6)
        else:
            logger.info("Using pre-trained tokenizer (no fine-tuned checkpoint)")

        if os.path.exists(ft_pred):
            logger.info("Loading fine-tuned predictor weights: %s", ft_pred)
            model.load_state_dict(torch.load(ft_pred, map_location="cpu"))
            logger.info("Fine-tuned predictor loaded (%.1f MB)", os.path.getsize(ft_pred)/1e6)
        else:
            logger.info("Using pre-trained predictor (no fine-tuned checkpoint)")

        _predictor = KronosPredictor(model, tokenizer, max_context=512, device=device,
                                      compile_model=True, use_amp=(device != "cpu"))
        _model_loaded = True
        params = sum(p.numel() for p in model.parameters())
        logger.info("%s model loaded on %s (%s params, fine-tuned=%s, compiled=True)",
                    model_name, device, f"{params:,}",
                    "yes" if os.path.exists(ft_pred) else "no")

        # 🔥 V2: 预热模型 — 消除首次推理 JIT 编译延迟
        logger.info("Warming up model (first inference may take 5-30s for JIT compile)...")
        _predictor.warmup(seq_len=60, pred_len=15)
        logger.info("Warmup complete — model ready for real-time inference")
    except Exception as e:
        logger.warning("Kronos model not loaded: %s", e)
    yield
    logger.info("Prediction Service stopped.")


app = FastAPI(
    title="速赢AI - Prediction Service",
    description="Kronos K-line prediction — 30-day OHLCV forecasting",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(CORSMiddleware, allow_origins=os.environ.get("CORS_ALLOWED_ORIGINS","http://localhost:5173,http://localhost:3000").split(","), allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])
app.include_router(router)


@app.get("/api/v1/health")
async def health():
    return {"status": "healthy", "service": "prediction-service",
            "model_loaded": _model_loaded, "version": "0.1.0"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8002, reload=True)
