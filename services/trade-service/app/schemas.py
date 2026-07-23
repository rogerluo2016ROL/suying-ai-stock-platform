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
    decision_context_id: str = Field("", description="DecisionContext id that produced this order")
    candidate_id: str = Field("", description="Candidate id behind this order")
    plan_id: str = Field("", description="Plan id behind this order")
    confirmed: bool = Field(False, description="User confirmed a large-trade WARN (server-enforced second confirmation)")


class BrokerConnectRequest(BaseModel):
    """JSON body for POST /api/v1/trade/broker/connect."""

    broker_name: str = Field("mock_qmt", description="mock_qmt | xtquant")
    account_id: str = Field(..., min_length=1, description="Broker or sandbox account id")
    server_ip: str = Field("127.0.0.1", description="Broker gateway host")
    server_port: int = Field(16001, ge=1, le=65535, description="Broker gateway port")
    environment: str = Field("sandbox", description="sandbox | live")
    trade_password: str = Field("", description="Optional broker password; never persisted")
