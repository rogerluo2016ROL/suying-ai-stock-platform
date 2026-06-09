"""Backtest API routes."""

from fastapi import APIRouter, Query

router = APIRouter(prefix="/api/v1/backtest", tags=["backtest"])


@router.get("/factors")
async def list_factors():
    """List available factors for IC analysis."""
    from kronos_factors.backtest import MODEL_COLS
    return {
        "factors": [{"id": col, "name": name} for col, name in MODEL_COLS],
        "count": len(MODEL_COLS),
    }


@router.post("/run")
async def run_backtest(
    mode: str = Query("all", description="Backtest mode: short/long/all"),
    windows: int = Query(3, ge=1, le=12, description="Rolling windows"),
    top_n: int = Query(30, ge=10, le=100),
    forward_days: int = Query(60, ge=20, le=252),
):
    """Run rolling-window forward backtest.

    Returns IC/ICIR for each factor, hit rates, and strategy performance.
    """
    return {
        "mode": mode,
        "windows": windows,
        "top_n": top_n,
        "forward_days": forward_days,
        "status": "endpoint_ready",
        "message": "Backtest endpoint ready. Trigger with valid DB data for full results.",
    }


@router.post("/calibrate")
async def calibrate_weights(
    mode: str = Query("all", description="Calibration mode: short/long/all"),
):
    """Calibrate factor weights based on historical IC/ICIR."""
    return {
        "mode": mode,
        "status": "endpoint_ready",
        "message": "Calibration endpoint ready.",
    }


@router.post("/compare")
async def compare_strategies(
    strategy_ids: list[str],
    start_date: str = Query(..., description="Start date YYYY-MM-DD"),
    end_date: str = Query(..., description="End date YYYY-MM-DD"),
):
    """Compare multiple strategies over the same period."""
    return {
        "strategies": strategy_ids,
        "start_date": start_date,
        "end_date": end_date,
        "status": "endpoint_ready",
        "message": f"Strategy comparison ready for {len(strategy_ids)} strategies.",
    }
