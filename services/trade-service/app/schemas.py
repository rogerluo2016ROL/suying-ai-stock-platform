"""Request/Response schemas for trade-service."""

from __future__ import annotations

from pydantic import BaseModel, Field


class PlaceOrderRequest(BaseModel):
    """JSON body for POST /api/v1/trade/order."""
    code: str = Field(..., description="Stock code", examples=["000001"])
    direction: str = Field(..., description="BUY or SELL", examples=["BUY"])
    price: float = Field(0, description="Limit price; 0 = market order")
    volume: int = Field(..., ge=100, description="Shares (lot size 100)")
    trade_mode: str = Field("paper", description="paper | live")
