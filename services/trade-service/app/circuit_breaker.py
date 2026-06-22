"""CircuitBreaker — daily-loss auto-pause for live trading.

Per PRD AC-11.8 / ADR-002 Decision 3:
- If daily loss exceeds configurable threshold, all live orders are blocked.
- Resets automatically at the start of the next trading day, or manually via API.
- HALF_OPEN state allows one probing order after cooldown.
- State persisted to PostgreSQL for crash recovery.

Concurrency (audit P0-3): all in-memory state mutations are guarded by a single
module-level ``asyncio.Lock``. FastAPI dispatches concurrent order requests on
one event loop, so ``check_daily_loss`` / ``can_trade`` / ``record_probe`` /
``reset`` / ``get_state`` / ``_get_or_create`` each acquire ``_lock`` before
reading or writing the shared ``_breakers`` dict and its mutable ``BreakerState``
fields.

HALF_OPEN probe reservation: ``can_trade`` atomically reserves the single
HALF_OPEN probe slot by incrementing ``probing_count`` *when it grants access*.
This closes the TOCTOU race where two concurrent ``can_trade`` calls both
observed ``probing_count == 0`` and each returned ``True``, bypassing the
"one probe only" invariant (real-money risk: two probing orders placed).
``record_probe`` no longer increments ``probing_count`` — the slot was already
reserved by ``can_trade``; it only records success/failure and transitions
status. DB-persistence helpers (``ensure_table`` / ``save_to_db`` /
``load_*_from_db``) intentionally do NOT take ``_lock`` — they perform
independent DB I/O outside the in-memory critical section.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from enum import StrEnum

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("trade-service.circuit_breaker")


class BreakerStatus(StrEnum):
    NORMAL = "NORMAL"        # closed — trading allowed
    TRIGGERED = "TRIGGERED"  # open — all live orders blocked
    HALF_OPEN = "HALF_OPEN"  # one probing order allowed after cooldown


# ── Configurable thresholds ────────────────────────────────────────────

_DAILY_LOSS_PCT = float(os.environ.get("CIRCUIT_BREAKER_DAILY_LOSS_PCT", "5.0"))
_COOLDOWN_MINUTES = int(os.environ.get("CIRCUIT_BREAKER_COOLDOWN_MINUTES", "30"))

# ── DB table name ──────────────────────────────────────────────────────
_TABLE_CIRCUIT_BREAKER = "circuit_breaker_state"


@dataclass
class BreakerState:
    """Internal state of one circuit breaker instance."""

    status: BreakerStatus = BreakerStatus.NORMAL
    triggered_at: datetime | None = None
    half_open_at: datetime | None = None
    daily_pnl: float = 0.0
    initial_capital: float = 1_000_000.0
    date: str = ""  # ISO date for automatic daily reset
    probing_count: int = 0  # number of half-open probes reserved/attempted
    probing_success: int = 0  # number of successful probes


# ── In-memory breaker store (keyed by account_id) ──────────────────────
_breakers: dict[str, BreakerState] = {}

# P0-3: single asyncio.Lock guards all in-memory state mutations. asyncio.Lock
# is bound to the running event loop; because trade-service runs one uvicorn
# event loop, this correctly serialises concurrent order requests. asyncio.Lock
# is NON-reentrant, so internal helpers that already hold the lock must call
# the ``_locked`` variants (see _check_daily_loss_locked) — never the public
# ones, which would deadlock.
_lock = asyncio.Lock()


def _today() -> str:
    return date.today().isoformat()


async def _get_or_create(account_id: str) -> BreakerState:
    """Get or create breaker state for an account, resetting daily if needed.

    Caller MUST hold ``_lock`` (this function performs shared-dict mutation).
    """
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
        state.half_open_at = None
        state.daily_pnl = 0.0
        state.date = today
        state.probing_count = 0
        state.probing_success = 0

    return state


async def _check_daily_loss_locked(
    account_id: str,
    daily_pnl: float | None,
    initial_capital: float | None,
) -> BreakerStatus:
    """Threshold + cooldown evaluation. Caller MUST hold ``_lock``.

    Split out of the public ``check_daily_loss`` so ``can_trade`` can invoke it
    without re-acquiring ``_lock`` (which would deadlock — asyncio.Lock is not
    reentrant).
    """
    state = await _get_or_create(account_id)

    if initial_capital is not None and initial_capital > 0:
        state.initial_capital = initial_capital

    if daily_pnl is not None:
        state.daily_pnl = daily_pnl

    # Check threshold — only apply when NORMAL (not already triggered)
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

    # Check cooldown expiry → transition TRIGGERED → HALF_OPEN
    if state.status == BreakerStatus.TRIGGERED and state.triggered_at is not None:
        elapsed = (datetime.now(timezone.utc) - state.triggered_at).total_seconds()
        if elapsed >= _COOLDOWN_MINUTES * 60:
            state.status = BreakerStatus.HALF_OPEN
            state.half_open_at = datetime.now(timezone.utc)
            state.probing_count = 0
            state.probing_success = 0
            logger.info(
                "Circuit breaker → HALF_OPEN for account=%s (cooldown %.0fs elapsed)",
                account_id, elapsed,
            )

    return state.status


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
        Current breaker status (NORMAL, HALF_OPEN, or TRIGGERED).
    """
    async with _lock:
        return await _check_daily_loss_locked(account_id, daily_pnl, initial_capital)


async def can_trade(account_id: str) -> tuple[bool, str]:
    """Check if trading is currently allowed (atomic check-and-reserve).

    - NORMAL: always allowed.
    - HALF_OPEN: allowed exactly once — the first call reserves the single
      probe slot by incrementing ``probing_count`` and returns True; subsequent
      calls (including concurrent ones serialised by ``_lock``) return False.
    - TRIGGERED: blocked.

    The reservation (not just a read) is what enforces the "one probe only"
    invariant under concurrency: two concurrent calls cannot both observe
    ``probing_count == 0`` because the lock serialises them and the first
    increments before releasing. ``record_probe`` later records the outcome
    and transitions status; it does NOT re-increment ``probing_count``.

    Returns:
        (allowed, reason_string) — reason starts with "HALF_OPEN" when the
        granted trade is a probing order (routes.py uses this prefix).
    """
    async with _lock:
        state = await _get_or_create(account_id)

        # Ensure latest state evaluation (cooldown transition). Inline the
        # locked helper — NOT the public check_daily_loss — to avoid
        # re-acquiring _lock (asyncio.Lock is non-reentrant → deadlock).
        await _check_daily_loss_locked(account_id, None, None)

        if state.status == BreakerStatus.NORMAL:
            return True, ""

        if state.status == BreakerStatus.HALF_OPEN:
            if state.probing_count < 1:
                # Reserve the probe slot atomically under the lock.
                state.probing_count += 1
                return True, "HALF_OPEN probing order allowed"
            return False, "HALF_OPEN: probing order already used, wait for result"

        return False, f"Circuit breaker {state.status.value}: trading blocked"


async def record_probe(account_id: str, success: bool) -> None:
    """Record the result of a HALF_OPEN probing order.

    The probe slot was already reserved by ``can_trade`` (which incremented
    ``probing_count``); this function only records the outcome and transitions
    status. It does NOT increment ``probing_count`` again.

    Args:
        account_id: Account identifier.
        success: True if the probing order executed successfully.
    """
    async with _lock:
        state = await _get_or_create(account_id)

        if state.status != BreakerStatus.HALF_OPEN:
            logger.warning(
                "record_probe called while status=%s for account=%s — ignoring",
                state.status.value, account_id,
            )
            return

        # probing_count already incremented by can_trade's reservation.
        if success:
            state.probing_success += 1
            state.status = BreakerStatus.NORMAL
            state.triggered_at = None
            state.half_open_at = None
            logger.info(
                "Circuit breaker → NORMAL for account=%s (probing order succeeded)",
                account_id,
            )
        else:
            # Probe failed → back to TRIGGERED
            state.status = BreakerStatus.TRIGGERED
            state.triggered_at = datetime.now(timezone.utc)
            state.half_open_at = None
            logger.warning(
                "Circuit breaker → TRIGGERED for account=%s (probing order failed)",
                account_id,
            )


async def reset(account_id: str, *, reason: str = "") -> BreakerStatus:
    """Manually reset the circuit breaker to NORMAL.

    Args:
        account_id: Account identifier.
        reason: Human-readable reset reason (logged).

    Returns:
        New breaker status (NORMAL).
    """
    async with _lock:
        state = await _get_or_create(account_id)
        prev = state.status
        state.status = BreakerStatus.NORMAL
        state.triggered_at = None
        state.half_open_at = None
        state.probing_count = 0
        state.probing_success = 0
        logger.info(
            "Circuit breaker RESET for account=%s: %s -> NORMAL (reason: %s)",
            account_id, prev.value, reason or "manual reset",
        )
        return BreakerStatus.NORMAL


async def get_state(account_id: str) -> dict:
    """Return the full breaker state as a dict for API responses."""
    async with _lock:
        state = await _get_or_create(account_id)
        loss_pct = (
            abs(state.daily_pnl) / state.initial_capital * 100
            if state.initial_capital > 0
            else 0.0
        )
        can_trade_flag = state.status == BreakerStatus.NORMAL or (
            state.status == BreakerStatus.HALF_OPEN and state.probing_count < 1
        )
        return {
            "account_id": account_id,
            "status": state.status.value,
            "triggered_at": state.triggered_at.isoformat() if state.triggered_at else None,
            "half_open_at": state.half_open_at.isoformat() if state.half_open_at else None,
            "daily_pnl": round(state.daily_pnl, 2),
            "initial_capital": round(state.initial_capital, 2),
            "daily_loss_pct": round(loss_pct if state.daily_pnl < 0 else 0, 2),
            "threshold_pct": _DAILY_LOSS_PCT,
            "cooldown_minutes": _COOLDOWN_MINUTES,
            "can_trade": can_trade_flag,
            "probing_count": state.probing_count,
            "date": state.date,
        }


# ═══════════════════════════════════════════════════════════════════════════
# DB persistence — save/load breaker state from PostgreSQL
# (intentionally NOT guarded by _lock: independent DB I/O outside the
# in-memory critical section; locking here would only slow down DB writes)
# ═══════════════════════════════════════════════════════════════════════════


async def ensure_table(db: AsyncSession) -> None:
    """Create the circuit_breaker_state table if it does not exist."""
    await db.execute(
        text(
            f"""
            CREATE TABLE IF NOT EXISTS {_TABLE_CIRCUIT_BREAKER} (
                account_id      TEXT PRIMARY KEY,
                status          TEXT NOT NULL DEFAULT 'NORMAL',
                triggered_at    TIMESTAMPTZ,
                half_open_at    TIMESTAMPTZ,
                daily_pnl       DOUBLE PRECISION NOT NULL DEFAULT 0,
                initial_capital DOUBLE PRECISION NOT NULL DEFAULT 1000000,
                date            TEXT NOT NULL,
                probing_count   INTEGER NOT NULL DEFAULT 0,
                probing_success INTEGER NOT NULL DEFAULT 0,
                updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
    )
    await db.commit()


async def save_to_db(db: AsyncSession, account_id: str) -> bool:
    """Persist the in-memory breaker state to PostgreSQL.

    Returns:
        True on success, False on failure.
    """
    state = _breakers.get(account_id)
    if state is None:
        logger.debug("No in-memory state for account=%s — skipping DB save", account_id)
        return False

    try:
        await db.execute(
            text(
                f"""
                INSERT INTO {_TABLE_CIRCUIT_BREAKER}
                    (account_id, status, triggered_at, half_open_at,
                     daily_pnl, initial_capital, date,
                     probing_count, probing_success, updated_at)
                VALUES
                    (:account_id, :status, :triggered_at, :half_open_at,
                     :daily_pnl, :initial_capital, :date,
                     :probing_count, :probing_success, NOW())
                ON CONFLICT (account_id) DO UPDATE SET
                    status          = EXCLUDED.status,
                    triggered_at    = EXCLUDED.triggered_at,
                    half_open_at    = EXCLUDED.half_open_at,
                    daily_pnl       = EXCLUDED.daily_pnl,
                    initial_capital = EXCLUDED.initial_capital,
                    date            = EXCLUDED.date,
                    probing_count   = EXCLUDED.probing_count,
                    probing_success = EXCLUDED.probing_success,
                    updated_at      = NOW()
                """
            ),
            {
                "account_id": account_id,
                "status": state.status.value,
                "triggered_at": state.triggered_at,
                "half_open_at": state.half_open_at,
                "daily_pnl": state.daily_pnl,
                "initial_capital": state.initial_capital,
                "date": state.date,
                "probing_count": state.probing_count,
                "probing_success": state.probing_success,
            },
        )
        await db.commit()
        logger.debug("Circuit breaker state saved to DB for account=%s", account_id)
        return True
    except Exception:
        logger.exception("Failed to persist circuit breaker state for account=%s", account_id)
        await db.rollback()
        return False


async def load_from_db(db: AsyncSession, account_id: str) -> BreakerState | None:
    """Restore breaker state from PostgreSQL into memory.

    Returns:
        BreakerState if found, None otherwise.
    """
    try:
        result = await db.execute(
            text(
                f"""
                SELECT account_id, status, triggered_at, half_open_at,
                       daily_pnl, initial_capital, date,
                       probing_count, probing_success
                FROM {_TABLE_CIRCUIT_BREAKER}
                WHERE account_id = :account_id
                """
            ),
            {"account_id": account_id},
        )
        row = result.fetchone()
        if row is None:
            return None

        # Cross-date check: if DB has yesterday's date, auto-reset
        today = _today()
        db_date = row[6]  # date column
        if db_date != today:
            logger.info(
                "Stale breaker state for account=%s (date=%s vs today=%s) — auto-resetting",
                account_id, db_date, today,
            )
            state = BreakerState(date=today)
        else:
            state = BreakerState(
                status=BreakerStatus(row[1]),
                triggered_at=row[2],
                half_open_at=row[3],
                daily_pnl=row[4],
                initial_capital=row[5],
                date=db_date,
                probing_count=row[7],
                probing_success=row[8],
            )

        _breakers[account_id] = state
        logger.info(
            "Circuit breaker state loaded from DB for account=%s: status=%s",
            account_id, state.status.value,
        )
        return state
    except Exception:
        logger.exception("Failed to load circuit breaker state for account=%s", account_id)
        return None


async def load_all_from_db(db: AsyncSession) -> int:
    """Restore all breaker states from PostgreSQL into memory.

    Returns:
        Number of states loaded.
    """
    try:
        result = await db.execute(
            text(
                f"""
                SELECT account_id, status, triggered_at, half_open_at,
                       daily_pnl, initial_capital, date,
                       probing_count, probing_success
                FROM {_TABLE_CIRCUIT_BREAKER}
                """
            ),
        )
        count = 0
        today = _today()
        for row in result.fetchall():
            account_id = row[0]
            db_date = row[6]
            if db_date != today:
                state = BreakerState(date=today)
            else:
                state = BreakerState(
                    status=BreakerStatus(row[1]),
                    triggered_at=row[2],
                    half_open_at=row[3],
                    daily_pnl=row[4],
                    initial_capital=row[5],
                    date=db_date,
                    probing_count=row[7],
                    probing_success=row[8],
                )
            _breakers[account_id] = state
            count += 1

        logger.info("Loaded %d circuit breaker states from DB", count)
        return count
    except Exception:
        logger.exception("Failed to load circuit breaker states from DB")
        return 0
