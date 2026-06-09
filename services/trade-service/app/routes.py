"""Trade API routes — paper trading with real in-memory engine."""

from fastapi import APIRouter, Query, HTTPException
from app.engine import get_engine

router = APIRouter(prefix="/api/v1/trade", tags=["trade"])
engine = get_engine()


@router.post("/order")
async def place_order(
    code: str = Query(..., description="Stock code"),
    direction: str = Query(..., description="BUY / SELL"),
    price: float = Query(0, description="0 = market order"),
    volume: int = Query(..., ge=100, description="Shares"),
):
    """Place a paper trading order. Filled immediately at mock price."""
    if direction.upper() not in ("BUY", "SELL"):
        raise HTTPException(400, "direction must be BUY or SELL")

    order = engine.place_order(code, direction, price, volume)
    return {
        "order_id": order.id,
        "code": order.code,
        "direction": order.direction,
        "price": order.filled_price,
        "volume": order.volume,
        "status": order.status,
        "filled_at": order.filled_at,
        "message": f"{'买入' if order.direction == 'BUY' else '卖出'} {order.code} {order.volume}股 @ {order.filled_price}",
    }


@router.delete("/order/{order_id}")
async def cancel_order(order_id: str):
    ok = engine.cancel_order(order_id)
    return {"order_id": order_id, "status": "cancelled" if ok else "not_found"}


@router.get("/orders")
async def list_orders():
    return {"orders": [{"id": o.id, "code": o.code, "direction": o.direction,
            "price": o.filled_price, "volume": o.volume, "status": o.status,
            "created": o.created_at} for o in engine.get_orders()]}


@router.get("/positions")
async def get_positions():
    return {"positions": [{"code": p.code, "volume": p.volume, "avg_cost": round(p.avg_cost, 2),
            "market_value": p.market_value, "pnl": round(p.pnl, 2)}
            for p in engine.get_positions()]}


@router.get("/account")
async def get_account():
    acct = engine.get_account()
    return {
        "total_capital": acct.total_capital,
        "available": acct.available,
        "market_value": acct.market_value,
        "total_pnl": round(acct.total_pnl, 2),
        "daily_pnl": round(acct.daily_pnl, 2),
    }


@router.get("/pnl")
async def get_pnl():
    acct = engine.get_account()
    return {"total_pnl": round(acct.total_pnl, 2), "daily_pnl": round(acct.daily_pnl, 2)}


@router.put("/mode")
async def switch_mode(mode: str = Query("paper")):
    if mode not in ("paper", "live"): raise HTTPException(400, "mode must be paper or live")
    return {"mode": mode, "status": "ok"}
