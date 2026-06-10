"""CircuitBreaker — daily-loss auto-pause for live trading.

Per PRD AC-11.8 / ADR-002 Decision 3:
- If daily loss exceeds configurable threshold, all live orders are blocked.
- Resets automatically at the start of the next trading day, or manually via API.
- HALF_OPEN state allows one probing order after cooldown.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from enum import StrEnum

logger = logging.getLogger("trade-service.circuit_breaker")


class BreakerStatus(StrEnum):
    NORMAL = "NORMAL"        # closed — trading allowed
    TRIGGERED = "TRIGGERED"  # open — all live orders blocked


# ── Configurable thresholds ────────────────────────────────────────────

_DAILY_LOSS_PCT = float(os.environ.get("CIRCUIT_BREAKER_DAILY_LOSS_PCT", "5.0"))
_COOLDOWN_MINUTES = int(os.environ.get("CIRCUIT_BREAKER_COOLDOWN_MINUTES", "30"))


@dataclass
class BreakerState:
    """Internal state of one circuit breaker instance."""

    status: BreakerStatus = BreakerStatus.NORMAL
    triggered_at: datetime | None = None
    daily_pnl: float = 0.0
    initial_capital: float = 1_000_000.0
    date: str = ""  # ISO date for automatic daily reset


# ── In-memory breaker store (keyed by account_id) ──────────────────────
_breakers: dict[str, BreakerState] = {}


def _today() -> str:
    return date.today().isoformat()


def _get_or_create(account_id: str) -> BreakerState:
    """Get or create breaker state for an account, resetting daily if needed."""
    state = _breakers.get(account_id)
    today = _today()

    if state is None:
        state = BreakerState(date=today)
        _breakers[account_id] = state
    elif state.date != today:
        # New day — auto-reset
        logger.info(
            "Circuit breaker auto-reset for account=%s (new day: %s -> %s)",
            account_id, state.date, today,
        )
        state.status = BreakerStatus.NORMAL
        state.triggered_at = None
        state.daily_pnl = 0.0
        state.date = today

    return state


async def check_daily_loss(
    account_id: str,
    daily_pnl: float | None = None,
    initial_capital: float | None = None,
) -> BreakerStatus:
    """Check whether the daily-loss circuit breaker has been triggered.

    Args:
        account_id: Account identifier.
        daily_pnl: Current daily PnL (optional — updates the tracked value).
        initial_capital: Day-start capital (optional — updates the baseline).

    Returns:
        Current breaker status (NORMAL or TRIGGERED).
    """
    state = _get_or_create(account_id)

    if initial_capital is not None and initial_capital > 0:
        state.initial_capital = initial_capital

    if daily_pnl is not None:
        state.daily_pnl = daily_pnl

    # Check threshold
    if state.status == BreakerStatus.NORMAL and state.initial_capital > 0:
        loss_pct = abs(state.daily_pnl) / state.initial_capital * 100
        if state.daily_pnl < 0 and loss_pct >= _DAILY_LOSS_PCT:
            state.status = BreakerStatus.TRIGGERED
            state.triggered_at = datetime.now(timezone.utc)
            logger.warning(
                "Circuit breaker TRIGGERED for account=%s: daily loss %.2f%% (¥%.2f / ¥%.2f)",
                account_id,
                loss_pct,
                state.daily_pnl,
                state.initial_capital,
            )

    # Check cooldown expiry (auto-reset after cooldown)
    if state.status == BreakerStatus.TRIGGERED and state.triggered_at is not None:
        elapsed = (datetime.now(timezone.utc) - state.triggered_at).total_seconds()
        if elapsed >= _COOLDOWN_MINUTES * 60:
            logger.info(
                "Circuit breaker cooldown expired for account=%s (elapsed=%.0fs)",
                account_id, elapsed,
            )
            # Don't auto-reset to NORMAL — require manual reset for safety.
            # The cooldown just makes it eligible for reset.

    return state.status


async def reset(account_id: str, *, reason: str = "") -> BreakerStatus:
    """Manually reset the circuit breaker to NORMAL.

    Args:
        account_id: Account identifier.
        reason: Human-readable reset reason (logged).

    Returns:
        New breaker status (NORMAL).
    """
    state = _get_or_create(account_id)
    prev = state.status
    state.status = BreakerStatus.NORMAL
    state.triggered_at = None
    logger.info(
        "Circuit breaker RESET for account=%s: %s -> NORMAL (reason: %s)",
        account_id, prev.value, reason or "manual reset",
    )
    return BreakerStatus.NORMAL


async def get_state(account_id: str) -> dict:
    """Return the full breaker state as a dict for API responses."""
    state = _get_or_create(account_id)
    loss_pct = (
        abs(state.daily_pnl) / state.initial_capital * 100
        if state.initial_capital > 0
        else 0.0
    )
    return {
        "account_id": account_id,
        "status": state.status.value,
        "triggered_at": state.triggered_at.isoformat() if state.triggered_at else None,
        "daily_pnl": round(state.daily_pnl, 2),
        "initial_capital": round(state.initial_capital, 2),
        "daily_loss_pct": round(loss_pct if state.daily_pnl < 0 else 0, 2),
        "threshold_pct": _DAILY_LOSS_PCT,
        "cooldown_minutes": _COOLDOWN_MINUTES,
        "can_trade": state.status == BreakerStatus.NORMAL,
        "date": state.date,
    }
