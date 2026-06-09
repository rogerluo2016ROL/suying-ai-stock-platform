"""Trade API routes — unified Order API for paper & live trading."""

from fastapi import APIRouter, Query, HTTPException

router = APIRouter(prefix="/api/v1/trade", tags=["trade"])

# ── Order ──
@router.post("/order")
async def place_order(
    code: str,
    direction: str = Query(..., description="BUY / SELL"),
    price: float = Query(0, description="0 = market order"),
    volume: int = Query(..., ge=100, description="Shares"),
    order_type: str = Query("LIMIT", description="LIMIT / MARKET"),
):
    """Place an order (paper or live, depending on service mode)."""
    if direction not in ("BUY", "SELL"):
        raise HTTPException(400, "direction must be BUY or SELL")
    return {
        "order_id": f"ord_{code}_{direction}",
        "code": code, "direction": direction, "price": price or "MKT",
        "volume": volume, "order_type": order_type,
        "status": "pending",
        "message": f"Order {direction} {volume} shares of {code} submitted.",
    }


@router.delete("/order/{order_id}")
async def cancel_order(order_id: str):
    """Cancel a pending order."""
    return {"order_id": order_id, "status": "cancelled"}


@router.get("/orders")
async def list_orders(status: str = Query(None, description="pending/filled/cancelled")):
    """List orders."""
    return {"orders": [], "status": "endpoint_ready"}


# ── Position ──
@router.get("/positions")
async def get_positions():
    """Get current positions (paper or live)."""
    return {"positions": [], "status": "endpoint_ready"}


# ── Account ──
@router.get("/account")
async def get_account():
    """Get account info — capital, available, market value, P&L."""
    return {
        "total_capital": 1_000_000,
        "available": 1_000_000,
        "market_value": 0,
        "total_pnl": 0,
        "daily_pnl": 0,
        "status": "endpoint_ready",
    }


@router.get("/pnl")
async def get_pnl(period: str = Query("daily", description="daily/weekly/monthly/yearly")):
    """Get P&L statistics."""
    return {"period": period, "pnl": 0, "trades": 0, "win_rate": 0, "status": "endpoint_ready"}


# ── Mode ──
@router.put("/mode")
async def switch_mode(mode: str = Query("paper", description="paper / live")):
    """Switch between paper trading and live trading."""
    if mode not in ("paper", "live"):
        raise HTTPException(400, "mode must be paper or live")
    return {"mode": mode, "status": "switched", "warning": "Live mode requires broker setup."}


# ── Strategy execution ──
@router.post("/strategy/start")
async def start_quant_strategy(
    plan_id: str,
    execution_mode: str = Query("semi_auto", description="full_auto / semi_auto"),
):
    """Start automated quantitative strategy execution from a confirmed plan."""
    return {
        "plan_id": plan_id,
        "execution_mode": execution_mode,
        "status": "started",
        "message": f"Quant strategy started in {execution_mode} mode.",
    }


@router.post("/strategy/stop")
async def stop_quant_strategy(plan_id: str):
    return {"plan_id": plan_id, "status": "stopped"}
