"""XtquantBroker 实盘接线单测 — 用 fake trader + stub xtquant 模块验证字段映射与 fail-fast。

不依赖真实 xtquant SDK / QMT 网关（CI 与 macOS dev 均无 SDK）。
"""

import sys
import types

import pytest

from app import xtquant_broker as xb


class _StockAccount:
    def __init__(self, account_id):
        self.account_id = account_id


class _FakeAsset:
    m_dBalance = 1_000_000.0
    m_dAvailable = 800_000.0
    m_dFrozenCash = 10_000.0
    m_dMarketValue = 190_000.0
    m_dPositionProfit = 5_000.0


class _FakePosition:
    m_nVolume = 300
    m_nCanUseVolume = 200
    m_strInstrumentID = "600000"
    m_strExchangeID = "SH"
    m_dOpenPrice = 10.0
    m_dMarketValue = 3_300.0


class _FakeTrader:
    def __init__(self, cancel_ret=0):
        self.cancel_ret = cancel_ret
        self.cancelled = []

    def query_stock_asset(self, _acc):
        return _FakeAsset()

    def query_stock_positions(self, _acc):
        return [_FakePosition()]

    def cancel_order_stock(self, _acc, order_id):
        self.cancelled.append(order_id)
        return self.cancel_ret


@pytest.fixture
def broker(monkeypatch):
    """SDK 可用 + 已连接的 XtquantBroker（fake trader）。"""
    xt = types.ModuleType("xtquant")
    xttype = types.ModuleType("xtquant.xttype")
    xttype.StockAccount = _StockAccount
    xt.xttype = xttype
    monkeypatch.setitem(sys.modules, "xtquant", xt)
    monkeypatch.setitem(sys.modules, "xtquant.xttype", xttype)
    monkeypatch.setattr(xb, "_XTQUANT_AVAILABLE", True)
    b = xb.XtquantBroker(account="8888888888")
    b._trader = _FakeTrader()
    return b


async def test_get_account_maps_xtasset_fields(broker):
    acct = await broker.get_account()
    assert acct.total_assets == 1_000_000.0
    assert acct.available == 800_000.0
    assert acct.frozen == 10_000.0
    assert acct.market_value == 190_000.0
    assert acct.total_pnl == 5_000.0
    assert acct.account_id == "8888888888"


async def test_get_positions_uses_plain_instrument_id(broker):
    positions = await broker.get_positions()
    assert len(positions) == 1
    pos = positions[0]
    # symbol 必须是 6 位代码（与风控 pos.symbol == order.symbol 对齐），不带 .SH 后缀
    assert pos.symbol == "600000"
    assert pos.quantity == 200  # m_nCanUseVolume
    assert pos.avg_cost == 10.0
    assert pos.market_value == 3_300.0


async def test_cancel_order_success(broker):
    result = await broker.cancel_order("12345")
    assert result.success is True
    assert broker._trader.cancelled == [12345]


async def test_cancel_order_rejects_non_integer_id(broker):
    result = await broker.cancel_order("ORD-abc")
    assert result.success is False
    assert broker._trader.cancelled == []


async def test_cancel_order_propagates_sdk_error_code(monkeypatch, broker):
    broker._trader.cancel_ret = -1
    result = await broker.cancel_order("12345")
    assert result.success is False
    assert "code=-1" in result.message


async def test_unconnected_broker_fails_fast(monkeypatch):
    monkeypatch.setattr(xb, "_XTQUANT_AVAILABLE", True)
    b = xb.XtquantBroker()
    with pytest.raises(RuntimeError, match="未连接"):
        await b.get_account()
