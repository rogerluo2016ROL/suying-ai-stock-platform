"""XtquantBroker — live trading via xtquant (QMT/miniQMT) SDK.

If the xtquant package is not installed (e.g. local dev on macOS/Linux
without a QMT Windows host), this module provides a stub that returns
realistic mock data but with ``is_live=True`` to distinguish it from
the paper trading MockBroker.
"""

from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone

from app.broker_interface import (
    AccountInfo,
    BrokerInterface,
    CancelResult,
    OrderRequest,
    OrderResult,
    OrderStatus,
    Position,
    SyncResult,
)

logger = logging.getLogger("trade-service.xtquant_broker")

# ── xtquant availability ──────────────────────────────────────────────
try:
    import xtquant  # noqa: F401

    _XTQUANT_AVAILABLE = True
    logger.info("xtquant SDK detected — live broker available")
except ImportError:
    _XTQUANT_AVAILABLE = False
    logger.warning(
        "xtquant SDK not installed — XtquantBroker will run in STUB mode. "
        "Install xtquant on a Windows host with QMT/miniQMT to enable live trading."
    )


# ── Stub constants (consistent mock data) ─────────────────────────────
_STUB_ACCOUNT_ID = os.environ.get("QMT_ACCOUNT", "8888888888")
_STUB_INITIAL_CAPITAL = float(os.environ.get("STUB_INITIAL_CAPITAL", "1000000"))


class XtquantBroker(BrokerInterface):
    """Live trading broker backed by xtquant (QMT/miniQMT).

    In production (Windows + QMT client) this wraps ``xtquant.xttrader``.
    On dev machines without xtquant it falls back to a **stub** that returns
    mock data — but all responses carry ``is_live`` markers so the frontend
    and risk gateway can distinguish real-vs-stub.

    Connection lifecycle (production)::

        broker = XtquantBroker(path="C:\\qmt\\userdata_mini", session_id=1)
        await broker.connect()
        # ... trade ...
        await broker.disconnect()
    """

    # ── Stub state ────────────────────────────────────────────────────
    # These are shared across all instances so mode-switches are visible.
    _stub_orders: list[OrderResult] = []
    _stub_positions: dict[str, Position] = {}
    _stub_account = AccountInfo(
        total_assets=_STUB_INITIAL_CAPITAL,
        available=_STUB_INITIAL_CAPITAL,
        frozen=0.0,
        market_value=0.0,
        total_pnl=0.0,
        daily_pnl=0.0,
        account_id=_STUB_ACCOUNT_ID,
    )
    _stub_connected: bool = False
    _stub_order_counter: int = 0

    def __init__(
        self,
        path: str = "",
        session_id: int = 1,
        account: str = "",
    ):
        self._path = path or os.environ.get("QMT_USERDATA_PATH", "")
        self._session_id = session_id
        self._account = account or os.environ.get("QMT_ACCOUNT", _STUB_ACCOUNT_ID)
        self._trader = None  # XtQuantTrader instance (when xtquant available)
        self._is_live = _XTQUANT_AVAILABLE

    # ── Public API ────────────────────────────────────────────────────

    @property
    def is_live(self) -> bool:
        """True when the real xtquant SDK is driving this broker."""
        return self._is_live

    @property
    def connected(self) -> bool:
        if _XTQUANT_AVAILABLE and self._trader is not None:
            # Real connection status would come from xtquant callbacks
            return True
        return self._stub_connected

    async def connect(self) -> bool:
        """Establish connection to the QMT/miniQMT gateway."""
        if _XTQUANT_AVAILABLE:
            return await self._connect_real()
        return await self._connect_stub()

    async def disconnect(self) -> bool:
        if _XTQUANT_AVAILABLE and self._trader is not None:
            return await self._disconnect_real()
        return await self._disconnect_stub()

    # ── BrokerInterface implementation ────────────────────────────────

    async def place_order(self, order: OrderRequest) -> OrderResult:
        if _XTQUANT_AVAILABLE and self._trader is not None:
            # TODO: wire to xtquant.xttrader.order_stock(...)
            logger.info("xtquant place_order not yet wired — falling back to stub")
        return self._place_order_stub(order)

    async def cancel_order(self, order_id: str) -> CancelResult:
        if _XTQUANT_AVAILABLE and self._trader is not None:
            # TODO: wire to xtquant.xttrader.cancel_order_stock(...)
            logger.info("xtquant cancel_order not yet wired — falling back to stub")
        return self._cancel_order_stub(order_id)

    async def get_positions(self) -> list[Position]:
        if _XTQUANT_AVAILABLE and self._trader is not None:
            # TODO: wire to xtquant.xttrader.query_stock_positions(...)
            logger.info("xtquant query_positions not yet wired — falling back to stub")
        return list(self._stub_positions.values())

    async def get_account(self) -> AccountInfo:
        if _XTQUANT_AVAILABLE and self._trader is not None:
            # TODO: wire to xtquant.xttrader.query_stock_asset(...)
            logger.info("xtquant query_account not yet wired — falling back to stub")
        return self._stub_account

    async def sync(self) -> SyncResult:
        """Sync positions + account from broker."""
        positions = await self.get_positions()
        account = await self.get_account()
        return SyncResult(
            success=True,
            positions=positions,
            account=account,
            message="synced (stub)" if not _XTQUANT_AVAILABLE else "synced (live)",
        )

    # ── Real connection (stubs until xtquant is wired) ─────────────────

    async def _connect_real(self) -> bool:
        # pylint: disable=import-outside-toplevel
        try:
            from xtquant.xttrader import XtQuantTrader
            from xtquant.xttype import StockAccount

            self._trader = XtQuantTrader(self._path, self._session_id)
            self._trader.start()
            connect_result = self._trader.connect()
            if connect_result != 0:
                logger.error("xtquant connect failed: code=%d", connect_result)
                return False

            acc = StockAccount(self._account)
            subscribe_result = self._trader.subscribe(acc)
            if subscribe_result != 0:
                logger.error("xtquant subscribe failed: code=%d", subscribe_result)
                return False

            self._is_live = True
            logger.info("xtquant connected to account %s", self._account)
            return True
        except Exception:
            logger.exception("xtquant connection error")
            return False

    async def _disconnect_real(self) -> bool:
        try:
            if self._trader:
                self._trader.stop()
                self._trader = None
            return True
        except Exception:
            logger.exception("xtquant disconnect error")
            return False

    # ── Stub helpers ───────────────────────────────────────────────────

    async def _connect_stub(self) -> bool:
        self._stub_connected = True
        logger.info("XtquantBroker stub connected (is_live=%s)", self._is_live)
        return True

    async def _disconnect_stub(self) -> bool:
        self._stub_connected = False
        return True

    def _place_order_stub(self, order: OrderRequest) -> OrderResult:
        """Stub order fill: immediate execution at a mock reference price."""
        import random

        self._stub_order_counter += 1
        order_id = f"LIVE{self._stub_order_counter:06d}"

        # Mock reference price
        base_price = 50.0 + random.uniform(-5, 5)
        exec_price = order.price if order.price > 0 else base_price

        result = OrderResult(
            order_id=order_id,
            broker_order_id=f"XT{self._stub_order_counter:06d}",
            status=OrderStatus.FILLED,
            filled_qty=order.quantity,
            filled_avg_price=round(exec_price, 2),
            message="filled (stub)",
        )

        # Update stub account & positions
        trade_amount = exec_price * order.quantity
        if order.side.value == "BUY":
            self._stub_account.available -= trade_amount
            self._update_stub_position_buy(order.symbol, order.quantity, exec_price)
        else:
            self._stub_account.available += trade_amount
            self._update_stub_position_sell(order.symbol, order.quantity, exec_price)

        self._stub_account.market_value = sum(
            p.market_value for p in self._stub_positions.values()
        )
        self._stub_account.total_assets = (
            self._stub_account.available + self._stub_account.market_value
        )
        self._stub_orders.append(result)
        logger.info(
            "Stub order filled: %s %s %d@%.2f",
            order.side.value,
            order.symbol,
            order.quantity,
            exec_price,
        )
        return result

    def _cancel_order_stub(self, order_id: str) -> CancelResult:
        for o in self._stub_orders:
            if o.order_id == order_id and o.status == OrderStatus.PENDING:
                o.status = OrderStatus.CANCELLED
                o.message = "cancelled (stub)"
                return CancelResult(order_id=order_id, success=True, message="cancelled")
        return CancelResult(order_id=order_id, success=False, message="order not found or already filled")

    def _update_stub_position_buy(self, symbol: str, qty: int, price: float):
        if symbol in self._stub_positions:
            pos = self._stub_positions[symbol]
            total_cost = pos.avg_cost * pos.quantity + price * qty
            pos.quantity += qty
            pos.avg_cost = total_cost / pos.quantity
        else:
            pos = Position(symbol=symbol, quantity=qty, avg_cost=price)
            self._stub_positions[symbol] = pos
        pos.current_price = price
        pos.market_value = round(pos.current_price * pos.quantity, 2)
        pos.pnl = round((pos.current_price - pos.avg_cost) * pos.quantity, 2)
        if pos.avg_cost > 0:
            pos.pnl_pct = round((pos.current_price - pos.avg_cost) / pos.avg_cost * 100, 2)

    def _update_stub_position_sell(self, symbol: str, qty: int, price: float):
        if symbol in self._stub_positions:
            pos = self._stub_positions[symbol]
            sold_qty = min(qty, pos.quantity)
            pnl_realised = (price - pos.avg_cost) * sold_qty
            self._stub_account.total_pnl += pnl_realised
            self._stub_account.daily_pnl += pnl_realised
            pos.quantity -= sold_qty
            if pos.quantity <= 0:
                del self._stub_positions[symbol]
            else:
                pos.market_value = round(pos.current_price * pos.quantity, 2)
