# Auto-Trading Backend Code Review

- **Date**: 2026-06-10
- **Reviewer**: code-reviewer
- **Scope**: `strategy-service` auto_trading_engine.py, auto_trading_executor.py, routes.py
- **Reference**: ADR-003, API contract doc, trade-service routes.py / circuit_breaker.py / engine.py
- **Verdict**: **BLOCK** -- 2 critical bugs must be fixed before merge

---

## Summary

| Severity | Count |
|----------|-------|
| Critical | 2 |
| High | 3 |
| Medium | 4 |
| Low | 3 |

---

## 1. Strategy State Machine Correctness

### 1.1 [CRITICAL] `ExecutorManager.start()` re-starts paused strategies, creating double execution

**File**: `auto_trading_executor.py:117-152`

**Root cause**: The guard at line 124-126 only rejects `running`, not `paused`:

```python
existing = self._executors.get(strategy_id)
if existing and existing.status == "running":
    raise ValueError(f"策略已在运行中: {strategy_id}")
```

When a paused strategy is `start()`-ed (instead of `resume()`-ed):
1. A **second** `ExecutorState` and **second** `asyncio.Task` are created
2. The old paused task is leaked (not cancelled) -- it still waits on `_pause_event`
3. If the old task is ever resumed (e.g., via `mgr.resume()`), BOTH tasks execute in parallel
4. Result: **duplicate orders**, **double position counting**

**Fix**:
```python
if existing and existing.status in ("running", "paused"):
    raise ValueError(f"策略已在执行中 (status={existing.status})，使用 resume 恢复或 stop 终止后重新 start")
```

**ADR alignment**: ADR-003 Decision 2 state diagram shows `stopped --[start]--> active` as valid. The code should enforce this and reject `paused --[start]--> active` (user should call `resume`).

---

### 1.2 [MEDIUM] `ExecutorManager.stop()` guard is too narrow

**File**: `auto_trading_executor.py:184`

```python
if state.status in ("stopped",):
```

Does not guard against `idle`. If a strategy exists in the manager with `idle` status (initialize-only scenario), calling `stop()` would set `stopped` and update the strategy store anyway. The `in ("stopped",)` tuple syntax is also unnecessarily verbose -- prefer `== "stopped"`.

**Fix**: Change to `if state.status in ("stopped", "idle"):` or simply remove the guard since stopping an already-stopped executor is practically harmless at this layer (the `_stop_event.set()` is idempotent).

---

### 1.3 [HIGH] `StrategyStore.update()` allows bypassing executor lifecycle

**File**: `auto_trading_engine.py:188-197`

The `update()` method applies arbitrary kwargs via `setattr`. While `routes.py` `StrategyUpdateRequest` does NOT expose a `status` field (mitigation), the store itself has no transition validation. If any internal code path calls `store.update(id, status="stopped")` without going through `ExecutorManager`, the strategy state desyncs from executor state.

**Proposed**: Add a `_ALLOWED_TRANSITIONS` dict in `StrategyStore.update()` that validates status changes, or at minimum document that status changes MUST go through `ExecutorManager`.

---

### 1.4 [LOW] `_evaluate_sell_conditions` kronos_trend normalization

**File**: `auto_trading_executor.py:441-447`

```python
if cond.field == "kronos_trend":
    field_value = signal.get("kronos_trend", signal.get("components", {}).get("kronos_confidence", {}).get("score", 50))
    field_value = 1 if field_value < 50 else 0
```

The fallback chain for `kronos_trend` nests 4 levels of `.get()` with different semantic meanings (direct flag vs confidence score). If `kronos_trend` is absent AND `components.kronos_confidence.score` is absent, the value defaults to 50, which maps to `field_value = 0` (bullish). This means a missing signal defaults to "trend is bullish" -- potentially inappropriate for a sell condition that wants to detect bearish reversal. Consider logging a warning when all fallbacks are exhausted.

---

## 2. Trade-Service Contract Alignment

### 2.1 [CRITICAL] Paper-mode positions response missing `pnl_pct`

**File**: `trade-service/routes.py:248-251` vs `auto_trading_executor.py:310, 437-439`

The executor's `_evaluate_sell_conditions` (line 437-439) computes:
```python
context["stop_loss"] = abs(position.get("pnl_pct", 0)) if position.get("pnl_pct", 0) < 0 else 0
context["take_profit"] = position.get("pnl_pct", 0) if position.get("pnl_pct", 0) > 0 else 0
```

Trade-service **paper mode** `get_positions` response (line 248-251) serializes only `code, volume, avg_cost, market_value, pnl` -- **`pnl_pct` is missing**. The live mode response (line 237-244) correctly includes `"pnl_pct": round(p.pnl_pct, 2)`.

The `engine.py:Position` dataclass HAS `pnl_pct: float = 0` (line 31), but the route handler omits it from the JSON.

**Impact**: For paper trading, ALL sell conditions based on `stop_loss` or `take_profit` fields will evaluate to `0` (always below threshold), meaning **automatic stop-loss and take-profit never fire in paper mode**.

**Fix**: Add `"pnl_pct": round(p.pnl_pct, 2)` to the paper mode positions response dict in `trade-service/routes.py:248-251`.

---

### 2.2 [Contract Match] Order / Account endpoints

| Executor call | Trade-service endpoint | Fields consumed | Status |
|---|---|---|---|
| `_fetch_positions` | `GET /api/v1/trade/positions?trade_mode=` | `code, volume, market_value, pnl_pct` | **Paper mode: pnl_pct missing (see 2.1)** |
| `_fetch_account` | `GET /api/v1/trade/account?trade_mode=` | `daily_pnl` | OK |
| `_place_order` | `POST /api/v1/trade/order` | `order_id` | OK |

---

### 2.3 [MEDIUM] Signal-service field path mapping is hardcoded

**File**: `auto_trading_executor.py:461-465`

```python
field_map = {
    "signal_strength": "signal.score",
    "kronos_return": "components.kronos_confidence.score",
    "factor_resonance": "components.factor_resonance.score",
}
```

This tight coupling means any signal-service response schema change silently breaks condition evaluation (values fallback to 0 without error). This is acknowledged as Open Question Q5 in the API contract doc.

**Mitigation for Phase A**: Add a WARN log when a mapped field resolves to 0, so operators can detect schema drift.

---

## 3. Runaway Protection (Daily Loss Circuit Breaker)

### 3.1 [MEDIUM] Dual circuit breaker -- strategy-level vs account-level

**ADR-003 Decision 5** states "复用 trade-service CircuitBreaker", but the implementation takes a different approach:

- **Strategy-level** (executor, line 262-278): `abs(daily_pnl)/strategy.capital >= 3%` -> auto-pause
- **Account-level** (trade-service, `circuit_breaker.py:72-120`): `abs(daily_pnl)/initial_capital*100 >= 5%` -> reject orders

The strategy does NOT call `check_daily_loss()` on the trade-service CircuitBreaker. It independently calculates the loss ratio from the account response's `daily_pnl` field.

**Assessment**: This is a **defensible deviation**. The ADR's "implementation details" section actually shows the local calculation approach. The account-level CircuitBreaker (default 5%) provides a higher-threshold safety net. The 3-layer defense-in-depth (strategy 3% -> account 5% -> per-position stop-loss) is preserved. However, the ADR wording "复用" is misleading -- update ADR to clarify "concept reuse, not API call reuse" or actually integrate the API call.

**No code change required** for Phase A, but ADR-003 should be updated to match reality.

---

### 3.2 [OK] Daily loss auto-pause logic

The calculation at line 263:
```python
daily_loss_pct = abs(daily_pnl) / strategy.capital if daily_pnl < 0 else 0
```

Correctly uses strategy.capital as denominator (matching strategy-level risk tolerance) vs trade-service's `initial_capital` (account-level). Auto-pause via `mgr.pause()` correctly sets `_pause_event.clear()`.

---

## 4. Full-Auto / Semi-Auto Mode

### 4.1 [HIGH] `StrategyConfig` missing `execution_mode` field

**ADR-003 Decision 4** specifies `execution_mode: full_auto | semi_auto`. The `StrategyConfig` dataclass in `auto_trading_engine.py:56-78` does NOT have this field. The `CustomStrategyRequest` Pydantic model in `routes.py:215-226` also lacks it.

The executor has no conditional logic for semi_auto mode (ADR acknowledges this is Phase B). However, without the field on the dataclass, the frontend cannot persist the user's mode preference.

**Fix**: Add `execution_mode: str = "full_auto"` to `StrategyConfig`, `CustomStrategyRequest`, `StrategyUpdateRequest`, and `to_dict()`.

---

## 5. Additional Findings

### 5.1 [HIGH] `generate_strategy_from_scheme` shallow-copies picks

**File**: `auto_trading_engine.py:281`

```python
picks=plan.picks.copy() if plan.picks else [],
```

`list.copy()` is shallow -- dicts inside the list are shared between plan and strategy. If plan.picks are later modified (e.g., entry_price updated), the strategy's picks silently change.

**Fix**: `copy.deepcopy(plan.picks)` to fully isolate strategy picks from plan.

---

### 5.2 [MEDIUM] Thread safety -- `get()` methods not locked

**File**: `auto_trading_engine.py:181-182`, `plan_store.py:37`

Both `StrategyStore.get()` and `PlanStore.get()` access the internal dict **without** acquiring the lock. While CPython's GIL makes dict reads atomic for simple types, this is not guaranteed across Python implementations and creates a pattern violation since `list_all()` does hold the lock.

**Fix**: Wrap `get()` with `self._lock` for consistency, or remove the lock from `list_all()` if reads are considered safe.

---

### 5.3 [MEDIUM] `auto_trading_executor.py:147` -- new event loop leak

**File**: `auto_trading_executor.py:143-147`

```python
try:
    loop = asyncio.get_running_loop()
except RuntimeError:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
```

When no event loop is running (e.g., called from a sync context or thread), a new event loop is created but **never started** (`loop.run_forever()` not called). The task scheduled on it at line 148 (`loop.create_task(...)`) will never execute. This silently fails -- the executor appears "started" but never runs checks.

**Fix**: Raise a clear error if no running loop exists, or ensure the caller always has an active loop. In a FastAPI context, `asyncio.get_running_loop()` should always succeed.

---

### 5.4 [LOW] `_executor_loop` interval reset on resume preserves old interval

**File**: `auto_trading_executor.py:242`

```python
waited = 0  # reset interval after resume
```

After resume, the full interval restarts from 0. This can defer the next check by up to `interval` seconds from resume. Intentional design to avoid immediately checking after resume (giving time for state to settle), but undocumented.

---

### 5.5 [LOW] Log truncation loses newest entries

**File**: `auto_trading_executor.py:81-82`

```python
if len(self.logs) > 1000:
    self.logs = self.logs[-500:]
```

Keeping the last 500 when overflowing from 1000 means **the most recent 500 are kept, but the middle ~500 are lost**. For debugging, the middle entries (neither oldest nor newest) are typically the least interesting, so this is acceptable. Consider `[-800:]` to retain more context.

---

## Audit Checklist

| Check | Result |
|-------|--------|
| Strategy status transitions enforced | Partial -- `start()` on paused bypasses (1.1) |
| Executor status sync with StrategyConfig | OK (but can be bypassed via store.update) |
| Trade-service contract alignment | Blocked -- pnl_pct missing in paper mode (2.1) |
| Circuit breaker reuse per ADR | Partial deviation (3.1) -- update ADR |
| execution_mode field present | Missing (4.1) |
| Picks deep-copy isolation | Bug -- shallow copy (5.1) |
| Thread safety | Minor inconsistency (5.2) |
| Error handling on HTTP failures | OK -- all wrapped with try/except returning error dicts |
| Log capacity management | OK -- 1000 cap with 500 retention |

---

## Verdict: BLOCK

**Must fix before merge:**
1. `ExecutorManager.start()` must reject paused strategies (1.1)
2. Trade-service paper mode `get_positions` must include `pnl_pct` (2.1)

**Should fix before merge:**
3. Add `execution_mode` to `StrategyConfig` dataclass (4.1)
4. Deep-copy picks in `generate_strategy_from_scheme` (5.1)
5. Fix or raise on missing event loop in `start()` (5.3)

**Can defer to Phase B:**
6. Semi-auto mode confirmation UI and executor logic
7. Field mapping schema versioning
8. Thread-safety hardening for `get()`
