"""XtquantBroker — live trading via xtquant (QMT/miniQMT) SDK.

If the xtquant package is not installed (e.g. local dev on macOS/Linux
without a QMT Windows host), this module provides a stub that returns
realistic mock data but with ``is_live=True`` to distinguish it from
the paper trading MockBroker.
"""

from __future__ import annotations

import asyncio
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


class BrokerCapabilityError(RuntimeError):
    """Raised when live SDK wiring is incomplete; never fake a fill."""


REQUIRED_LIVE_CAPABILITIES = {
    "place_order", "cancel_order", "query_positions", "query_account", "order_callbacks"
}

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
        # 已接线的实盘能力（place_order / order_callbacks 仍未接线 → live_readiness 保持 blocked）
        self._implemented_capabilities: set[str] = {
            "cancel_order", "query_positions", "query_account",
        }

    def live_readiness(self) -> dict:
        missing = sorted(REQUIRED_LIVE_CAPABILITIES - self._implemented_capabilities)
        if not _XTQUANT_AVAILABLE:
            missing = sorted(REQUIRED_LIVE_CAPABILITIES)
        return {"status": "ready" if not missing else "blocked", "missing_capabilities": missing}

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
        if not _XTQUANT_AVAILABLE:
            raise BrokerCapabilityError("xtquant SDK unavailable; live broker is blocked")
        return await self._connect_real()

    async def disconnect(self) -> bool:
        if not _XTQUANT_AVAILABLE:
            raise BrokerCapabilityError("xtquant SDK unavailable; disconnect is blocked")
        if _XTQUANT_AVAILABLE and self._trader is not None:
            return await self._disconnect_real()
        raise BrokerCapabilityError("xtquant broker is not connected")

    # ── BrokerInterface implementation ────────────────────────────────

    async def place_order(self, order: OrderRequest) -> OrderResult:
        if not _XTQUANT_AVAILABLE:
            raise BrokerCapabilityError("xtquant SDK unavailable; place_order is blocked")
        if _XTQUANT_AVAILABLE:
            if self._trader is None:
                raise RuntimeError(
                    "XtquantBroker: SDK 可用但未连接，拒绝静默 fallback 到 stub（防止虚假成交）。"
                    "请先调用 connect() 连接券商。"
                )
            if "place_order" not in self._implemented_capabilities:
                raise BrokerCapabilityError("xtquant place_order capability is not implemented")
        raise BrokerCapabilityError("xtquant place_order capability is not implemented")

    def _require_connected(self, capability: str) -> None:
        """统一前置检查：SDK 缺失 / 未连接一律 fail-fast，拒绝静默 fallback 到 stub。"""
        if not _XTQUANT_AVAILABLE:
            raise BrokerCapabilityError(f"xtquant SDK unavailable; {capability} is blocked")
        if self._trader is None:
            raise RuntimeError(
                "XtquantBroker: SDK 可用但未连接，拒绝静默 fallback 到 stub（防止虚假成交）。"
                "请先调用 connect() 连接券商。"
            )

    async def cancel_order(self, order_id: str) -> CancelResult:
        self._require_connected("cancel_order")
        from xtquant.xttype import StockAccount  # noqa: PLC0415 (SDK 仅 Windows/QMT 可用)

        try:
            xt_order_id = int(order_id)
        except (TypeError, ValueError):
            return CancelResult(
                order_id=order_id, success=False,
                message=f"非法 xtquant 委托号（需为整数）: {order_id}",
            )
        acc = StockAccount(self._account)
        ret = await asyncio.to_thread(self._trader.cancel_order_stock, acc, xt_order_id)
        if ret == 0:
            logger.info("xtquant cancel ok: order=%s", order_id)
            return CancelResult(order_id=order_id, success=True, message="cancelled (live)")
        logger.warning("xtquant cancel failed: order=%s code=%s", order_id, ret)
        return CancelResult(order_id=order_id, success=False, message=f"cancel failed: code={ret}")

    async def get_positions(self) -> list[Position]:
        self._require_connected("query_positions")
        from xtquant.xttype import StockAccount  # noqa: PLC0415

        acc = StockAccount(self._account)
        raw = await asyncio.to_thread(self._trader.query_stock_positions, acc)
        positions: list[Position] = []
        for p in raw or []:
            qty = int(getattr(p, "m_nVolume", 0) or 0)
            if qty <= 0:
                continue
            # 与风控/下单链路对齐：symbol 用 6 位代码（不带交易所后缀）
            symbol = str(getattr(p, "m_strInstrumentID", "") or "")
            if not symbol:
                continue
            avg_cost = float(getattr(p, "m_dOpenPrice", 0.0) or 0.0)
            market_value = float(getattr(p, "m_dMarketValue", 0.0) or 0.0)
            current_price = round(market_value / qty, 3) if market_value else avg_cost
            pos = Position(
                symbol=symbol,
                quantity=int(getattr(p, "m_nCanUseVolume", qty) or qty),
                avg_cost=avg_cost,
            )
            pos.current_price = current_price
            pos.market_value = round(market_value, 2)
            pos.pnl = round((current_price - avg_cost) * qty, 2)
            if avg_cost > 0:
                pos.pnl_pct = round((current_price - avg_cost) / avg_cost * 100, 2)
            positions.append(pos)
        return positions

    async def get_account(self) -> AccountInfo:
        self._require_connected("query_account")
        from xtquant.xttype import StockAccount  # noqa: PLC0415

        acc = StockAccount(self._account)
        asset = await asyncio.to_thread(self._trader.query_stock_asset, acc)
        if asset is None:
            raise BrokerCapabilityError("xtquant query_stock_asset returned None")
        return AccountInfo(
            total_assets=float(getattr(asset, "m_dBalance", 0.0) or 0.0),
            available=float(getattr(asset, "m_dAvailable", 0.0) or 0.0),
            frozen=float(getattr(asset, "m_dFrozenCash", 0.0) or 0.0),
            market_value=float(getattr(asset, "m_dMarketValue", 0.0) or 0.0),
            total_pnl=float(getattr(asset, "m_dPositionProfit", 0.0) or 0.0),
            daily_pnl=0.0,  # xtquant 资产快照不含当日盈亏，由熔断器按成交回报累计
            account_id=self._account,
        )

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
