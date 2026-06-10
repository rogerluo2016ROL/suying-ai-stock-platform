"""BrokerInterface ABC — unified broker abstraction for paper/live trading."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import StrEnum


class OrderSide(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(StrEnum):
    LIMIT = "LIMIT"
    MARKET = "MARKET"


class OrderStatus(StrEnum):
    PENDING = "pending"
    SUBMITTED = "submitted"
    PARTIAL = "partial"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


@dataclass
class OrderRequest:
    """Standardised order request across all brokers."""

    symbol: str                 # e.g. "000001.SZ" / "600519.SH"
    side: OrderSide
    order_type: OrderType
    quantity: int               # shares
    price: float = 0.0          # 0 = market order


@dataclass
class OrderResult:
    """Standardised order result from broker."""

    order_id: str               # local order ID
    broker_order_id: str = ""   # broker-side order ID (if live)
    status: OrderStatus = OrderStatus.PENDING
    filled_qty: int = 0
    filled_avg_price: float = 0.0
    message: str = ""


@dataclass
class CancelResult:
    """Result of a cancel-order request."""

    order_id: str
    success: bool
    message: str = ""


@dataclass
class Position:
    """Standardised position from broker."""

    symbol: str
    quantity: int
    avg_cost: float
    current_price: float = 0.0
    market_value: float = 0.0
    pnl: float = 0.0
    pnl_pct: float = 0.0


@dataclass
class AccountInfo:
    """Standardised account snapshot from broker."""

    total_assets: float = 0.0
    available: float = 0.0
    frozen: float = 0.0
    market_value: float = 0.0
    total_pnl: float = 0.0
    daily_pnl: float = 0.0
    account_id: str = ""


@dataclass
class SyncResult:
    """Result of syncing positions/account from broker."""

    success: bool
    positions: list[Position] = field(default_factory=list)
    account: AccountInfo | None = None
    message: str = ""


class BrokerInterface(ABC):
    """Abstract broker interface for paper/live trading.

    All broker implementations (MockBroker, XtquantBroker, etc.) must
    implement this interface. The trade router calls these methods without
    knowing which concrete broker is in use.
    """

    @abstractmethod
    async def place_order(self, order: OrderRequest) -> OrderResult:
        """Submit an order to the broker.

        Args:
            order: Standardised order request.

        Returns:
            OrderResult with execution status.
        """
        ...

    @abstractmethod
    async def cancel_order(self, order_id: str) -> CancelResult:
        """Cancel a pending order.

        Args:
            order_id: Local order ID to cancel.

        Returns:
            CancelResult indicating success/failure.
        """
        ...

    @abstractmethod
    async def get_positions(self) -> list[Position]:
        """Get current positions from the broker.

        Returns:
            List of Position objects.
        """
        ...

    @abstractmethod
    async def get_account(self) -> AccountInfo:
        """Get current account information from the broker.

        Returns:
            AccountInfo snapshot.
        """
        ...

    @abstractmethod
    async def sync(self) -> SyncResult:
        """Synchronise positions and account from the broker.

        Returns:
            SyncResult with latest positions and account data.
        """
        ...
