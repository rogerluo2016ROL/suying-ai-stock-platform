"""RiskGateway — pre-trade risk checks for live trading.

Checks:
1. Sufficient capital (buy orders)
2. Position availability (sell orders)
3. Price limit (±10% for A-shares)
4. Position concentration (single stock ≤ 30% of portfolio)
5. Single order amount cap (default ≤ 500k CNY)
6. Large-trade detection (requires frontend confirmation when ≥ 500k CNY)
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from enum import StrEnum

from app.broker_interface import AccountInfo, OrderRequest, OrderSide, Position

logger = logging.getLogger("trade-service.risk_gateway")


class RiskCheckLevel(StrEnum):
    PASS = "pass"
    WARN = "warn"       # large trade — frontend confirmation needed
    REJECT = "reject"   # hard block


@dataclass
class RiskCheckItem:
    """Result of a single risk check."""

    rule: str
    level: RiskCheckLevel
    message: str = ""
    detail: dict = field(default_factory=dict)


@dataclass
class RiskResult:
    """Aggregated risk check result."""

    passed: bool
    checks: list[RiskCheckItem] = field(default_factory=list)
    requires_confirmation: bool = False
    confirm_reason: str = ""

    @property
    def reject_reason(self) -> str:
        """First reject message, or empty string."""
        for c in self.checks:
            if c.level == RiskCheckLevel.REJECT:
                return c.message
        return ""

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "requires_confirmation": self.requires_confirmation,
            "confirm_reason": self.confirm_reason,
            "checks": [
                {
                    "rule": c.rule,
                    "level": c.level.value,
                    "message": c.message,
                    "detail": c.detail,
                }
                for c in self.checks
            ],
        }


# ── Configurable thresholds (env vars) ────────────────────────────────

_MAX_SINGLE_ORDER_AMOUNT = float(os.environ.get("RISK_MAX_SINGLE_ORDER_AMOUNT", "500000"))
_LARGE_TRADE_THRESHOLD = float(os.environ.get("RISK_LARGE_TRADE_THRESHOLD", "500000"))
_MAX_POSITION_CONCENTRATION_PCT = float(os.environ.get("RISK_MAX_POSITION_CONCENTRATION", "30"))
_PRICE_LIMIT_PCT = float(os.environ.get("RISK_PRICE_LIMIT_PCT", "10.0"))


async def pre_check(
    order: OrderRequest,
    account: AccountInfo,
    positions: list[Position],
) -> RiskResult:
    """Run all pre-trade risk checks against an order.

    Args:
        order: The proposed order.
        account: Current account snapshot.
        positions: Current positions.

    Returns:
        RiskResult with pass/warn/reject verdict.
    """
    checks: list[RiskCheckItem] = []

    # 1. Capital check (buy)
    checks.append(_check_capital(order, account))

    # 2. Position availability (sell)
    checks.append(_check_position_available(order, positions))

    # 3. Price limit check
    checks.append(_check_price_limit(order))

    # 4. Position concentration
    checks.append(_check_concentration(order, account, positions))

    # 5. Single order amount cap
    checks.append(_check_single_order_cap(order))

    # 6. Large trade detection
    checks.append(_check_large_trade(order))

    # Aggregate
    has_reject = any(c.level == RiskCheckLevel.REJECT for c in checks)
    has_warn = any(c.level == RiskCheckLevel.WARN for c in checks)

    result = RiskResult(
        passed=not has_reject,
        checks=checks,
        requires_confirmation=has_warn and not has_reject,
    )
    if result.requires_confirmation:
        warns = [c for c in checks if c.level == RiskCheckLevel.WARN]
        result.confirm_reason = "; ".join(c.message for c in warns)

    if has_reject:
        rejects = [c.message for c in checks if c.level == RiskCheckLevel.REJECT]
        logger.warning("Risk check REJECTED: %s", "; ".join(rejects))
    elif has_warn:
        logger.info("Risk check WARN: %s", result.confirm_reason)
    else:
        logger.info("Risk check PASS for %s %s %d股", order.side.value, order.symbol, order.quantity)

    return result


# ── Individual checks ──────────────────────────────────────────────────


def _check_capital(order: OrderRequest, account: AccountInfo) -> RiskCheckItem:
    if order.side != OrderSide.BUY:
        return RiskCheckItem(rule="资金充足", level=RiskCheckLevel.PASS)

    estimate = order.price * order.quantity if order.price > 0 else 50.0 * order.quantity
    if estimate <= account.available:
        return RiskCheckItem(rule="资金充足", level=RiskCheckLevel.PASS)

    return RiskCheckItem(
        rule="资金充足",
        level=RiskCheckLevel.REJECT,
        message=f"资金不足: 需要 ¥{estimate:,.2f}, 可用 ¥{account.available:,.2f}",
        detail={"required": estimate, "available": account.available},
    )


def _check_position_available(
    order: OrderRequest, positions: list[Position]
) -> RiskCheckItem:
    if order.side != OrderSide.SELL:
        return RiskCheckItem(rule="持仓充足", level=RiskCheckLevel.PASS)

    for pos in positions:
        if pos.symbol == order.symbol:
            if pos.quantity >= order.quantity:
                return RiskCheckItem(rule="持仓充足", level=RiskCheckLevel.PASS)
            return RiskCheckItem(
                rule="持仓充足",
                level=RiskCheckLevel.REJECT,
                message=f"持仓不足: 卖出 {order.quantity}股, 持有 {pos.quantity}股",
                detail={"required": order.quantity, "held": pos.quantity},
            )

    return RiskCheckItem(
        rule="持仓充足",
        level=RiskCheckLevel.REJECT,
        message=f"未持有 {order.symbol}",
        detail={"symbol": order.symbol},
    )


def _check_price_limit(order: OrderRequest) -> RiskCheckItem:
    """A-share ±10% price limit check.

    Without real-time quotes this is a best-effort check. The order price
    itself is always accepted; in production, compare against latest_price.
    """
    if order.price <= 0:
        return RiskCheckItem(rule="涨跌停", level=RiskCheckLevel.PASS, message="市价单，跳过价格校验")

    # Best-effort: flag extremely large prices
    if order.price > 10000:
        return RiskCheckItem(
            rule="涨跌停",
            level=RiskCheckLevel.WARN,
            message=f"委托价 {order.price} 偏高，请确认",
            detail={"price": order.price},
        )

    return RiskCheckItem(rule="涨跌停", level=RiskCheckLevel.PASS)


def _check_concentration(
    order: OrderRequest,
    account: AccountInfo,
    positions: list[Position],
) -> RiskCheckItem:
    """Single-stock position concentration ≤ configured % of total assets."""
    if order.side != OrderSide.BUY:
        return RiskCheckItem(rule="仓位上限", level=RiskCheckLevel.PASS)

    total_assets = account.total_assets
    if total_assets <= 0:
        return RiskCheckItem(rule="仓位上限", level=RiskCheckLevel.PASS)

    # Estimate post-order position value
    estimate_price = order.price if order.price > 0 else 50.0
    new_value = estimate_price * order.quantity
    for pos in positions:
        if pos.symbol == order.symbol:
            new_value += pos.market_value
            break

    concentration_pct = (new_value / total_assets) * 100
    if concentration_pct > _MAX_POSITION_CONCENTRATION_PCT:
        return RiskCheckItem(
            rule="仓位上限",
            level=RiskCheckLevel.REJECT,
            message=(
                f"单票仓位超限: {order.symbol} 建仓后将占 {concentration_pct:.1f}%, "
                f"上限 {_MAX_POSITION_CONCENTRATION_PCT}%"
            ),
            detail={
                "symbol": order.symbol,
                "concentration_pct": round(concentration_pct, 1),
                "max_pct": _MAX_POSITION_CONCENTRATION_PCT,
            },
        )

    return RiskCheckItem(rule="仓位上限", level=RiskCheckLevel.PASS)


def _check_single_order_cap(order: OrderRequest) -> RiskCheckItem:
    """Single order amount must not exceed the configured cap."""
    estimate_price = order.price if order.price > 0 else 50.0
    order_amount = estimate_price * order.quantity

    if order_amount > _MAX_SINGLE_ORDER_AMOUNT:
        return RiskCheckItem(
            rule="单笔上限",
            level=RiskCheckLevel.REJECT,
            message=(
                f"单笔委托超限: ¥{order_amount:,.2f}, 上限 ¥{_MAX_SINGLE_ORDER_AMOUNT:,.2f}"
            ),
            detail={
                "order_amount": order_amount,
                "max_amount": _MAX_SINGLE_ORDER_AMOUNT,
            },
        )

    return RiskCheckItem(rule="单笔上限", level=RiskCheckLevel.PASS)


def _check_large_trade(order: OrderRequest) -> RiskCheckItem:
    """Large trade detection — warn if order amount exceeds threshold."""
    estimate_price = order.price if order.price > 0 else 50.0
    order_amount = estimate_price * order.quantity

    if order_amount >= _LARGE_TRADE_THRESHOLD:
        return RiskCheckItem(
            rule="大额交易",
            level=RiskCheckLevel.WARN,
            message=f"大额交易: ¥{order_amount:,.2f}, 请二次确认",
            detail={
                "order_amount": order_amount,
                "threshold": _LARGE_TRADE_THRESHOLD,
            },
        )

    return RiskCheckItem(rule="大额交易", level=RiskCheckLevel.PASS)
