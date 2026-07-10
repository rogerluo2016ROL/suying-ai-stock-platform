import asyncio

import pytest

from app import xtquant_broker
from app.broker_interface import OrderRequest, OrderSide, OrderType


def test_missing_sdk_is_blocked():
    broker = xtquant_broker.XtquantBroker()
    broker._is_live = False
    assert broker.live_readiness()["status"] == "blocked"


@pytest.mark.asyncio
async def test_connected_sdk_without_order_capability_never_stubs(monkeypatch):
    broker = xtquant_broker.XtquantBroker()
    monkeypatch.setattr(xtquant_broker, "_XTQUANT_AVAILABLE", True)
    broker._is_live = True
    broker._trader = object()
    order = OrderRequest(
        symbol="600000.SH", side=OrderSide.BUY,
        order_type=OrderType.LIMIT, quantity=100, price=10.0,
    )
    with pytest.raises(xtquant_broker.BrokerCapabilityError):
        await broker.place_order(order)
