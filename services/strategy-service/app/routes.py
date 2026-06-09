"""Strategy API routes — plan lifecycle: draft → predict → backtest → confirm → execute."""

from fastapi import APIRouter, Query, HTTPException

router = APIRouter(prefix="/api/v1/strategy", tags=["strategy"])

PLAN_STATUSES = ["draft", "predicting", "backtesting", "confirmed", "active", "archived"]


@router.post("/generate")
async def generate_plan(
    picks: list[dict],
    capital: float = Query(1_000_000, ge=100_000, description="Total capital"),
    risk_tolerance: str = Query("medium", description="low/medium/high"),
    max_positions: int = Query(5, ge=1, le=20),
):
    """Generate a trading plan from screening picks.

    Plan lifecycle: draft → predict → backtest → confirm → active → archived
    """
    if not picks:
        raise HTTPException(status_code=400, detail="picks list cannot be empty")

    return {
        "plan_id": f"plan_{len(picks)}_{capital}",
        "status": "draft",
        "picks_count": len(picks),
        "capital": capital,
        "risk_tolerance": risk_tolerance,
        "max_positions": max_positions,
        "message": f"Plan generated with {len(picks)} stocks. Submit to prediction/backtest for validation.",
    }


@router.post("/optimize")
async def optimize_plan(
    plan_id: str,
    kronos_predictions: list[dict] = None,
):
    """Optimize a draft plan using Kronos predictions.

    - Remove stocks with negative Kronos predictions
    - Adjust position sizing by predicted return
    - Optimize entry timing by predicted inflection points
    """
    return {
        "plan_id": plan_id,
        "status": "optimized",
        "changes": {
            "removed_negative": 0,
            "position_adjusted": 0,
            "timing_optimized": 0,
        },
        "message": "Plan optimization endpoint ready.",
    }


@router.get("/plans")
async def list_plans(status: str = Query(None, description="Filter by status")):
    """List all trading plans."""
    return {"plans": [], "status": "endpoint_ready"}


@router.get("/plans/{plan_id}")
async def get_plan(plan_id: str):
    """Get a specific trading plan with full details."""
    return {"plan_id": plan_id, "status": "draft", "message": "Plan detail endpoint ready."}


@router.post("/plans/{plan_id}/confirm")
async def confirm_plan(plan_id: str):
    """Confirm a plan → generates detailed report + trading signals."""
    return {
        "plan_id": plan_id,
        "status": "confirmed",
        "report_url": f"/reports/{plan_id}.pdf",
        "message": "Plan confirmed. Report generation endpoint ready.",
    }


@router.get("/templates")
async def list_templates():
    """List available plan templates."""
    return {
        "templates": [
            {"id": "aggressive",  "name": "激进型", "risk": "high",   "max_positions": 3, "single_max": 0.20},
            {"id": "balanced",   "name": "均衡型", "risk": "medium", "max_positions": 5, "single_max": 0.12},
            {"id": "conservative","name":"保守型", "risk": "low",    "max_positions": 8, "single_max": 0.08},
        ]
    }
