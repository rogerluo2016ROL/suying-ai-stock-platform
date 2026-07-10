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
# M05 (audit-model-2026-06-22): checkpoint 状态 metric — 区分"加载自研 finetune"
# vs"走公开 Kronos-mini base". 自研 checkpoint 目录当前不存在, 生产路径必走 base 分支.
_model_checkpoint_status = "unknown"  # "finetuned" | "base_public" | "not_loaded"


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
    global _model_loaded, _predictor, _model_checkpoint_status
    logger.info("Starting Prediction Service...")
    try:
        import torch
        from kronos.model.kronos import Kronos, KronosTokenizer, KronosPredictor

        kronos_root = _find_kronos_root()
        device = "mps" if torch.backends.mps.is_available() else "cpu"
        model_name = "Kronos-mini"

        # ── Load base architecture from HuggingFace ──
        # M05: 生产 prediction-service 基于公开 Kronos-mini 托管推理 (见 ADR-005).
        # 自研 fine-tune checkpoint 目录当前不存在, 走 base 分支是预期行为, 不是降级.
        logger.info("Loading tokenizer: NeoQuasar/Kronos-Tokenizer-base")
        tokenizer = KronosTokenizer.from_pretrained("NeoQuasar/Kronos-Tokenizer-base")
        logger.info("Loading predictor: NeoQuasar/%s", model_name)
        model = Kronos.from_pretrained(f"NeoQuasar/{model_name}")

        # ── Apply fine-tuned weights if available ──
        # M05: 显式校验 checkpoint 存在性并记录状态 metric, 区分"自研 finetune"vs"公开 base".
        ft_tok = os.path.join(kronos_root, "outputs", "models",
                              "finetune_tokenizer_demo", "checkpoints", "best_model",
                              "pytorch_model.bin")
        ft_pred = os.path.join(kronos_root, "outputs", "models",
                               "finetune_predictor_demo", "checkpoints", "best_model",
                               "pytorch_model.bin")

        finetune_loaded = False
        if os.path.exists(ft_tok):
            logger.info("Loading fine-tuned tokenizer weights: %s", ft_tok)
            # M07: strict=False + 记录 missing/unexpected keys, 区分"完全加载"vs"shape 不匹配部分加载".
            try:
                missing_t, unexpected_t = tokenizer.load_state_dict(
                    torch.load(ft_tok, map_location="cpu"), strict=False)
                if missing_t:
                    logger.warning("fine-tune tokenizer missing keys (%d): %s",
                                   len(missing_t), missing_t[:5])
                if unexpected_t:
                    logger.warning("fine-tune tokenizer unexpected keys (%d): %s",
                                   len(unexpected_t), unexpected_t[:5])
                logger.info("Fine-tuned tokenizer loaded (%.1f MB, missing=%d unexpected=%d)",
                            os.path.getsize(ft_tok)/1e6, len(missing_t), len(unexpected_t))
            except (FileNotFoundError, RuntimeError) as e:
                logger.warning("fine-tune tokenizer load failed (%s) — falling back to public base", e)
        else:
            logger.info("No fine-tuned tokenizer checkpoint — using public Kronos-Tokenizer-base")

        if os.path.exists(ft_pred):
            logger.info("Loading fine-tuned predictor weights: %s", ft_pred)
            # M07: strict=False + missing/unexpected keys log, 形状不匹配不再静默回退.
            try:
                missing_p, unexpected_p = model.load_state_dict(
                    torch.load(ft_pred, map_location="cpu"), strict=False)
                if missing_p:
                    logger.warning("fine-tune predictor missing keys (%d): %s",
                                   len(missing_p), missing_p[:5])
                if unexpected_p:
                    logger.warning("fine-tune predictor unexpected keys (%d): %s",
                                   len(unexpected_p), unexpected_p[:5])
                logger.info("Fine-tuned predictor loaded (%.1f MB, missing=%d unexpected=%d)",
                            os.path.getsize(ft_pred)/1e6, len(missing_p), len(unexpected_p))
                finetune_loaded = True
            except (FileNotFoundError, RuntimeError) as e:
                logger.warning("fine-tune predictor load failed (%s) — falling back to public base", e)
        else:
            logger.info("No fine-tuned predictor checkpoint — using public %s base", model_name)

        _predictor = KronosPredictor(model, tokenizer, max_context=512, device=device,
                                      compile_model=True, use_amp=(device != "cpu"))
        _model_loaded = True
        _model_checkpoint_status = "finetuned" if finetune_loaded else "base_public"
        params = sum(p.numel() for p in model.parameters())
        logger.info("%s model loaded on %s (%s params, checkpoint=%s, compiled=True)",
                    model_name, device, f"{params:,}", _model_checkpoint_status)

        # 🔥 V2: 预热模型 — 消除首次推理 JIT 编译延迟
        logger.info("Warming up model (first inference may take 5-30s for JIT compile)...")
        _predictor.warmup(seq_len=60, pred_len=15)
        logger.info("Warmup complete — model ready for real-time inference")
    except Exception as e:
        _model_checkpoint_status = "not_loaded"
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


@app.get("/api/v1/health/live")
async def health_live_contract():
    return {"live": True, "service": "prediction-service", "version": "0.1.0"}

@app.get("/api/v1/health/ready")
async def health_ready_contract():
    return {"live": True, "ready": True, "service": "prediction-service", "version": "0.1.0", "checks": {}}
@app.get("/api/v1/health")
async def health():
    return {"status": "healthy", "service": "prediction-service",
            "model_loaded": _model_loaded,
            # M05: checkpoint 来源 metric — finetuned=自研, base_public=公开 Kronos-mini
            "checkpoint_status": _model_checkpoint_status,
            "version": "0.1.0"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8002, reload=True)
