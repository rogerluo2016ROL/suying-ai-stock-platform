"""Paper Trading Engine — in-memory order book with T+1 simulation."""

import time, threading, logging
from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("trade-service.engine")


@dataclass
class Order:
    id: str
    code: str
    direction: str  # BUY / SELL
    price: float    # 0 = market
    volume: int
    status: str = "pending"  # pending / filled / cancelled
    filled_price: float = 0
    filled_at: str = ""
    created_at: str = ""

@dataclass
class Position:
    code: str
    volume: int
    avg_cost: float
    current_price: float = 0
    market_value: float = 0
    pnl: float = 0
    pnl_pct: float = 0

@dataclass
class Account:
    total_capital: float = 1_000_000
    available: float = 1_000_000
    market_value: float = 0
    total_pnl: float = 0
    daily_pnl: float = 0


class PaperTradingEngine:
    """In-memory paper trading — single account, thread-safe."""

    def __init__(self):
        self.account = Account()
        self.orders: list[Order] = []
        self.positions: dict[str, Position] = {}
        self._lock = threading.Lock()
        self._order_counter = 0

    def place_order(self, code: str, direction: str, price: float, volume: int) -> Order:
        with self._lock:
            self._order_counter += 1
            order = Order(
                id=f"ORD{self._order_counter:04d}",
                code=code.upper(),
                direction=direction.upper(),
                price=price,
                volume=volume,
                created_at=datetime.now().isoformat(),
            )

            # Simple fill logic: fill immediately at a mock price
            if price == 0:
                # Market order: use a mock reference price
                mock_price = self._mock_price(code)
                order.filled_price = round(mock_price, 2)
            else:
                order.filled_price = round(price, 2)

            order.status = "filled"
            order.filled_at = datetime.now().isoformat()
            self.orders.append(order)

            # Update account & position
            trade_amount = order.filled_price * volume
            if direction.upper() == "BUY":
                self.account.available -= trade_amount
                self._update_position_buy(code, volume, order.filled_price)
            else:
                self.account.available += trade_amount
                self._update_position_sell(code, volume, order.filled_price)

            self._recalc_account()
            logger.info(f"Order filled: {order.direction} {code} {volume}@{order.filled_price}")
            return order

    def cancel_order(self, order_id: str) -> bool:
        with self._lock:
            for o in self.orders:
                if o.id == order_id and o.status == "pending":
                    o.status = "cancelled"
                    return True
            return False

    def get_orders(self) -> list[Order]: return self.orders
    def get_positions(self) -> list[Position]: return list(self.positions.values())
    def get_account(self) -> Account: return self.account

    def _update_position_buy(self, code: str, volume: int, price: float):
        if code in self.positions:
            pos = self.positions[code]
            total_cost = pos.avg_cost * pos.volume + price * volume
            pos.volume += volume
            pos.avg_cost = total_cost / pos.volume if pos.volume > 0 else 0
        else:
            self.positions[code] = Position(code=code, volume=volume, avg_cost=price)

    def _update_position_sell(self, code: str, volume: int, price: float):
        if code in self.positions:
            pos = self.positions[code]
            pnl = (price - pos.avg_cost) * min(volume, pos.volume)
            self.account.total_pnl += pnl
            self.account.daily_pnl += pnl
            pos.volume -= volume
            if pos.volume <= 0:
                del self.positions[code]

    def _recalc_account(self):
        mv = sum(p.avg_cost * p.volume for p in self.positions.values())
        self.account.market_value = round(mv, 2)
        self.account.available = round(self.account.available, 2)
        self.account.total_capital = round(self.account.available + self.account.market_value, 2)

    def _mock_price(self, code: str) -> float:
        """Return a mock price for paper trading. In production, fetch real-time quote."""
        return 50.0  # Default mock price


# Singleton
_engine = PaperTradingEngine()

def get_engine() -> PaperTradingEngine:
    return _engine
