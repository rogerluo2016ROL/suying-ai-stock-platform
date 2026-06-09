"""Prediction API routes."""

from typing import Optional
from fastapi import APIRouter, Query, HTTPException
import pandas as pd
import numpy as np

# Avoid circular import: access model state via app.main module
import app.main as _m

router = APIRouter(prefix="/api/v1/prediction", tags=["prediction"])


@router.get("/status")
async def model_status():
    """Check if Kronos model is loaded and ready."""
    return {"model_loaded": _model_loaded, "model": "Kronos-small", "device": "cpu"}


@router.post("/predict/{code}")
async def predict_stock(
    code: str,
    pred_days: int = Query(30, ge=5, le=60, description="Prediction horizon (trading days)"),
):
    """Predict 30-day price trajectory for a single stock.

    Requires the screener-service or data pipeline to provide K-line data.
    """
    if not _m._model_loaded or _m._predictor is None:
        raise HTTPException(status_code=503, detail="Kronos model not loaded")

    # In production, fetch K-line from the data service or DB adapter
    # For now, return a placeholder demonstrating the API contract
    return {
        "code": code,
        "pred_days": pred_days,
        "status": "model_ready",
        "message": "Prediction endpoint ready. Integrate with data pipeline for live predictions.",
    }


@router.post("/predict-batch")
async def predict_batch(
    codes: list[str],
    pred_days: int = Query(30, ge=5, le=60),
):
    """Batch predict 30-day trajectories for multiple stocks (up to 30)."""
    if not _m._model_loaded or _m._predictor is None:
        raise HTTPException(status_code=503, detail="Kronos model not loaded")

    if len(codes) > 30:
        raise HTTPException(status_code=400, detail="Max 30 stocks per batch")

    return {
        "codes": codes,
        "pred_days": pred_days,
        "status": "model_ready",
        "message": f"Batch prediction ready for {len(codes)} stocks.",
    }
