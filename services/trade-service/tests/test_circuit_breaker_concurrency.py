"""Concurrency tests for circuit_breaker (audit P0-3).

Verifies the ``asyncio.Lock`` guard + HALF_OPEN probe reservation closes the
TOCTOU race where two concurrent ``can_trade`` calls in HALF_OPEN both observed
``probing_count == 0`` and each returned ``True``, bypassing the "one probe
only" invariant (real-money risk: two probing orders placed).

AC-4 (strict): ``asyncio.gather(can_trade(acct), can_trade(acct))`` in HALF_OPEN
must return exactly one ``True``.

These are unit-level concurrency tests (no DB / no FastAPI). They drive the
public async API directly against the module-level ``_breakers`` store.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from app import circuit_breaker as cb
from app.circuit_breaker import BreakerStatus, BreakerState


@pytest.fixture(autouse=True)
def _isolated_breaker_store():
    """Reset the module-level _breakers dict before each test for isolation."""
    cb._breakers.clear()
    yield
    cb._breakers.clear()


def _seed_half_open(account_id: str) -> None:
    """Inject a HALF_OPEN state that has just exited cooldown.

    We bypass the public API here because reaching HALF_OPEN via check_daily_loss
    requires waiting _COOLDOWN_MINUTES; for a concurrency test we only need the
    state machine's *response* to HALF_OPEN, not the transition into it.
    """
    cb._breakers[account_id] = BreakerState(
        status=BreakerStatus.HALF_OPEN,
        triggered_at=datetime.now(timezone.utc) - timedelta(minutes=cb._COOLDOWN_MINUTES + 1),
        half_open_at=datetime.now(timezone.utc),
        probing_count=0,
        probing_success=0,
        date=cb._today(),
    )


# ── AC-4: the core race-condition fix ───────────────────────────────────


async def test_half_open_concurrent_can_trade_exactly_one_true():
    """AC-4: two concurrent can_trade in HALF_OPEN → exactly one True.

    Before P0-3: both coroutines read probing_count==0, both returned True →
    two probing orders placed (bug). After P0-3: ``_lock`` serialises the two
    calls; the first reserves the slot (probing_count 0→1) and returns True;
    the second observes probing_count==1 and returns False.
    """
    acct = "acct-ac4"
    _seed_half_open(acct)

    results = await asyncio.gather(cb.can_trade(acct), cb.can_trade(acct))
    allowed = [r[0] for r in results]

    assert allowed.count(True) == 1, (
        f"exactly one can_trade must succeed in HALF_OPEN under concurrency, got {allowed}"
    )
    assert allowed.count(False) == 1, (
        f"the other must be blocked, got {allowed}"
    )
    # Slot reserved exactly once.
    assert cb._breakers[acct].probing_count == 1


async def test_half_open_high_concurrency_still_one_true():
    """AC-4 stress: 16 concurrent can_trade in HALF_OPEN → still exactly one True."""
    acct = "acct-ac4-stress"
    _seed_half_open(acct)

    results = await asyncio.gather(*[cb.can_trade(acct) for _ in range(16)])
    allowed = [r[0] for r in results]

    assert allowed.count(True) == 1, (
        f"exactly one probe slot under 16-way concurrency, got {sum(allowed)} trues"
    )
    assert cb._breakers[acct].probing_count == 1


async def test_no_deadlock_can_trade_internal_check_daily_loss():
    """AC-3 regression: can_trade evaluates cooldown via the locked helper, not
    the public check_daily_loss. If it mistakenly awaited the public one,
    asyncio.Lock (non-reentrant) would deadlock. Heavy interleaving surfaces it.
    """
    acct = "acct-deadlock"
    cb._breakers[acct] = BreakerState(status=BreakerStatus.NORMAL, date=cb._today())

    for _ in range(20):
        await asyncio.gather(
            cb.can_trade(acct),
            cb.check_daily_loss(acct, daily_pnl=-100.0, initial_capital=1_000_000.0),
            cb.can_trade(acct),
        )
        # If deadlock, we'd never reach here.

    state = cb._breakers[acct]
    assert state.daily_pnl == -100.0
    # -100 / 1e6 = 0.01% << 5% threshold → stays NORMAL, both can_trade True each iter
    assert state.status == BreakerStatus.NORMAL


# ── AC-3: every mutating entrypoint holds the lock ──────────────────────


async def test_triggered_blocks_concurrent_trades():
    """Concurrent can_trade while TRIGGERED (cooldown not elapsed) → all False."""
    acct = "acct-triggered"
    cb._breakers[acct] = BreakerState(
        status=BreakerStatus.TRIGGERED,
        triggered_at=datetime.now(timezone.utc),
        date=cb._today(),
    )

    results = await asyncio.gather(*[cb.can_trade(acct) for _ in range(8)])
    allowed = [r[0] for r in results]
    assert allowed == [False] * 8, f"all concurrent trades must be blocked, got {allowed}"


async def test_reset_clears_state_under_concurrency():
    """Concurrent reset + can_trade do not corrupt state."""
    acct = "acct-reset"
    cb._breakers[acct] = BreakerState(
        status=BreakerStatus.TRIGGERED,
        triggered_at=datetime.now(timezone.utc),
        probing_count=5,
        date=cb._today(),
    )

    await asyncio.gather(cb.reset(acct), cb.can_trade(acct), cb.reset(acct))

    state = cb._breakers[acct]
    assert state.status == BreakerStatus.NORMAL
    assert state.probing_count == 0


# ── record_probe contract after reservation refactor ────────────────────


async def test_record_probe_does_not_double_count_after_reservation():
    """record_probe must NOT increment probing_count (can_trade already reserved).

    Flow: can_trade reserves (count 0→1) → record_probe(success) transitions
    HALF_OPEN→NORMAL. probing_count stays 1, probing_success becomes 1.
    """
    acct = "acct-probe-contract"
    _seed_half_open(acct)

    allowed, _ = await cb.can_trade(acct)
    assert allowed is True
    assert cb._breakers[acct].probing_count == 1

    await cb.record_probe(acct, success=True)

    state = cb._breakers[acct]
    assert state.status == BreakerStatus.NORMAL
    assert state.probing_count == 1, "record_probe must not re-increment probing_count"
    assert state.probing_success == 1


async def test_record_probe_failed_probe_back_to_triggered():
    """A failed probe reserves-then-reverts: HALF_OPEN → TRIGGERED."""
    acct = "acct-probe-fail"
    _seed_half_open(acct)

    allowed, _ = await cb.can_trade(acct)
    assert allowed is True

    await cb.record_probe(acct, success=False)

    state = cb._breakers[acct]
    assert state.status == BreakerStatus.TRIGGERED
    assert state.probing_count == 1
    assert state.probing_success == 0


async def test_sequential_second_probe_blocked_after_first_reserved():
    """Sequential (non-concurrent) second can_trade in HALF_OPEN is also blocked
    once the slot is reserved — verifies reservation persists across calls."""
    acct = "acct-sequential"
    _seed_half_open(acct)

    first_allowed, first_reason = await cb.can_trade(acct)
    second_allowed, second_reason = await cb.can_trade(acct)

    assert first_allowed is True
    assert first_reason.startswith("HALF_OPEN")
    assert second_allowed is False
    assert "already used" in second_reason


async def test_probe_slot_not_leaked_when_place_order_raises():
    """routes.py try/except contract: if place_order raises after can_trade
    reserved the HALF_OPEN slot, record_probe(success=False) must settle the
    reservation so the slot is not leaked (which would wedge the breaker).

    This test models the routes.py failure path directly against the breaker
    API: reserve → simulate failed probe → status returns to TRIGGERED, and a
    fresh HALF_OPEN (after cooldown) can reserve again.
    """
    acct = "acct-no-leak"
    _seed_half_open(acct)

    # 1) can_trade reserves the slot.
    allowed, _ = await cb.can_trade(acct)
    assert allowed is True
    assert cb._breakers[acct].probing_count == 1

    # 2) place_order "raises" → routes.py calls record_probe(success=False).
    await cb.record_probe(acct, success=False)
    state = cb._breakers[acct]
    assert state.status == BreakerStatus.TRIGGERED, (
        "failed probe must revert HALF_OPEN → TRIGGERED so the slot is settled"
    )

    # 3) Simulate cooldown elapsing again: re-seed HALF_OPEN and confirm a new
    # probe can be reserved (slot was released, not wedged).
    _seed_half_open(acct)
    allowed2, _ = await cb.can_trade(acct)
    assert allowed2 is True, "slot must be re-reservable after failed probe settled"


# ── NORMAL-path sanity (no regression) ──────────────────────────────────


async def test_normal_allows_concurrent_trades():
    """NORMAL state: concurrent can_trade all True (no reservation needed)."""
    acct = "acct-normal"
    cb._breakers[acct] = BreakerState(status=BreakerStatus.NORMAL, date=cb._today())

    results = await asyncio.gather(*[cb.can_trade(acct) for _ in range(5)])
    allowed = [r[0] for r in results]
    assert allowed == [True] * 5
    # NORMAL path does not touch probing_count.
    assert cb._breakers[acct].probing_count == 0


async def test_threshold_trigger_under_concurrency():
    """Concurrent check_daily_loss with a big loss triggers TRIGGERED exactly once
    (no double-trigger / no lost update)."""
    acct = "acct-threshold"
    cb._breakers[acct] = BreakerState(
        status=BreakerStatus.NORMAL,
        initial_capital=1_000_000.0,
        date=cb._today(),
    )

    await asyncio.gather(
        cb.check_daily_loss(acct, daily_pnl=-200_000.0, initial_capital=1_000_000.0),
        cb.check_daily_loss(acct, daily_pnl=-200_000.0, initial_capital=1_000_000.0),
    )

    state = cb._breakers[acct]
    # -200k / 1M = 20% >= 5% → TRIGGERED
    assert state.status == BreakerStatus.TRIGGERED
    assert state.triggered_at is not None
