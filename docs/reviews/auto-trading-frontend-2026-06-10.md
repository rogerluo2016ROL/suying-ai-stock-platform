# Auto-Trading Frontend Code Review

- **Date**: 2026-06-10
- **Reviewer**: code-reviewer
- **Scope**: `frontend/src/pages/AutoTrade.tsx`, `frontend/src/pages/Strategy.tsx`, `frontend/src/App.tsx`
- **Reference**: ADR-003, API contract doc, backend routes.py
- **Verdict**: **BLOCK** -- API path mismatch prevents all AutoTrade functionality

---

## Summary

| Severity | Count |
|----------|-------|
| Critical | 1 |
| High | 3 |
| Medium | 3 |
| Low | 2 |

---

## 1. Frontend-Backend API Consistency

### 1.1 [CRITICAL] AutoTrade API base path mismatch -- all calls fail

**File**: `AutoTrade.tsx:141,152,195,219,233,241`
**Root cause**: Frontend uses `/api/v1/auto-trade/*` but backend routes are on `/api/v1/strategy/*`

The Vite proxy config (`vite.config.ts`) has NO entry for `/api/v1/auto-trade`:

```js
// vite.config.ts -- only these proxy entries exist:
'/api/v1/strategy':    { target: 'http://localhost:8003', changeOrigin: true },
// NO '/api/v1/auto-trade' entry!
```

**Every fetch call in AutoTrade.tsx will 404**:

| Frontend call | Expected backend | Actual match? |
|---|---|---|
| `GET /api/v1/auto-trade/strategies` | `GET /api/v1/strategy/list` | **MISMATCH** |
| `POST /api/v1/auto-trade/strategies` | `POST /api/v1/strategy/custom` | **MISMATCH** |
| `PUT /api/v1/auto-trade/strategies/{id}` | `PUT /api/v1/strategy/{id}` | **MISMATCH** |
| `DELETE /api/v1/auto-trade/strategies/{id}` | `DELETE /api/v1/strategy/{id}` | **MISMATCH** |
| `POST /api/v1/auto-trade/strategies/{id}/start` | `POST /api/v1/strategy/{id}/start` | **MISMATCH** |
| `POST /api/v1/auto-trade/strategies/{id}/pause` | `POST /api/v1/strategy/{id}/pause` | **MISMATCH** |
| `POST /api/v1/auto-trade/strategies/{id}/resume` | `POST /api/v1/strategy/{id}/resume` | **MISMATCH** |
| `POST /api/v1/auto-trade/strategies/{id}/stop` | `POST /api/v1/strategy/{id}/stop` | **MISMATCH** |
| `GET /api/v1/auto-trade/strategies/{id}` | `GET /api/v1/strategy/{id}` | **MISMATCH** |
| `GET /api/v1/auto-trade/strategies/{id}/logs` | `GET /api/v1/strategy/{id}/log` | **MISMATCH** (path: `logs` vs `log`) |

**By contrast**, `Strategy.tsx:72` correctly calls `POST /api/v1/strategy/generate-from-scheme/{id}`.

**Fix**: Option A (preferred) -- Change all AutoTrade.tsx fetch calls to use `/api/v1/strategy/...` path matching the backend. Option B -- Add `/api/v1/auto-trade` proxy in vite.config.ts AND add an `auto-trade` router prefix in the backend.

---

## 2. API Contract Alignment

### 2.1 [HIGH] Request body shape does not match backend expectations

**File**: `AutoTrade.tsx:191-201`

The `handleSubmit` function sends the form values directly as JSON:

```typescript
body: JSON.stringify(values),
```

But the form fields collected (line 163-170, 177-186) use different field names and structure than the backend expects:

| Form field | Backend field (`CustomStrategyRequest`) | Match? |
|---|---|---|
| `execution_mode` | Not in backend model | **MISMATCH** (field doesn't exist in backend) |
| `max_position_pct` | `position_rules.total_position_cap_pct` | **MISMATCH** |
| `max_single_pct` | `position_rules.single_max_pct` | **MISMATCH** |
| `buy_conditions[].indicator` | `buy_conditions[].field` | **MISMATCH** |
| `sell_conditions[].indicator` | `sell_conditions[].field` | **MISMATCH** |
| `buy_conditions[].enabled` | Not in backend model | **EXTRA FIELD** |
| `risk_rules[].rule_type` | `risk_rules` is an object, not an array | **MISMATCH** |

The backend `CustomStrategyRequest` expects:
```python
{
  "name": str, "description": str,
  "buy_conditions": [{"field": ..., "operator": ..., "threshold": ..., "description": ...}],
  "sell_conditions": [...],
  "position_rules": {"max_positions": ..., "single_max_pct": ..., "total_position_cap_pct": ...},
  "risk_rules": {"daily_max_loss_pct": ..., "stop_loss_pct": ..., "take_profit_pct": ..., "trailing_stop_pct": ...},
  "trade_mode": str, "check_interval_sec": int, "capital": float, "picks": [...]
}
```

The frontend form shape **completely diverges** from this contract. The `buy_conditions` and `sell_conditions` have `indicator`/`operator`/`value`/`period`/`enabled` fields, while the backend expects `field`/`operator`/`threshold`/`description`.

The `risk_rules` is modeled as a `Form.List` (array of objects) in the frontend, but the backend expects a single nested object.

**Fix**: Either (A) transform form values to match the backend schema in `handleSubmit` before sending, or (B) make a dedicated submit handler that maps fields. Alternatively, align the form field structure with the backend Pydantic model directly.

---

### 2.2 [HIGH] Strategy status values don't match backend

**File**: `AutoTrade.tsx:43, 70-74`

Frontend uses these status values:
```typescript
status: 'running' | 'paused' | 'terminated' | 'completed'
```

Backend `StrategyConfig.status` uses:
```python
status: "draft" | "active" | "paused" | "stopped" | "archived"
```

Mapping mismatch:
| Frontend | Backend | Issue |
|---|---|---|
| `running` | `active` | Different name: status badge shows wrong label |
| `terminated` | `stopped` | Different name |
| `completed` | (none) | Doesn't exist in backend |
| (missing) | `draft` | No handling for draft strategies |
| (missing) | `archived` | Not represented |

The `statusConfig` map at line 70-74 will fail to render for `draft`/`active`/`stopped`/`archived`, and the action button visibility logic (lines 324-348) uses `running`/`paused`/`terminated`/`completed` which won't match any actual backend status.

**Fix**: Align the frontend `QuantStrategy.status` type and `statusConfig` with the backend values: `draft`, `active`, `paused`, `stopped`, `archived`. Update action button conditions accordingly:

- `draft`: show "Start" button
- `active`: show "Pause" + "Stop"
- `paused`: show "Resume" + "Stop"
- `stopped`: show "Re-start" (maps to start API)
- `archived`: no actions

---

### 2.3 [MEDIUM] `execution_mode` not in backend but used throughout frontend

**File**: `AutoTrade.tsx:46, 276-278, 434, 562-568`

The frontend has first-class support for `execution_mode` (`full_auto` / `semi_auto`) including:
- A Radio group in the create/edit form (line 562-568)
- Display tags in table (line 276-278) and detail drawer (line 434)
- Default value set in `openCreate` (line 165)

But the backend `StrategyConfig` dataclass does NOT have this field. The field will be silently dropped when saving/loading strategies. This means the user's mode selection is never persisted.

**Fix**: Add `execution_mode` to backend `StrategyConfig` and `CustomStrategyRequest` (see backend review 4.1), then the frontend must include it in the submit body.

---

## 3. Data Model Mismatches

### 3.1 [MEDIUM] `QuantStrategy` interface diverges from `StrategyConfig`

**File**: `AutoTrade.tsx:38-57`

The frontend `QuantStrategy` interface includes fields that don't exist in the backend's `StrategyConfig.to_dict()`:

| Frontend field | Backend equivalent | Issue |
|---|---|---|
| `plan_id`, `plan_name` | `source_scheme_id` (no plan_name) | Extra -- not in backend response |
| `pnl`, `pnl_pct` | Not in strategy response | Need separate API call (trade-service PnL) |
| `today_return`, `today_return_pct` | Not in strategy response | Need separate API call |
| `current_positions` | Not in strategy response | Need trade-service /positions |
| `next_rebalance_at` | Not in strategy response | Not computed by backend |
| `execution_mode` | Not in backend model (4.1) | Will be null |
| `max_position_pct` | `position_rules.total_position_cap_pct` | Nested vs flat |
| `max_single_pct` | `position_rules.single_max_pct` | Nested vs flat |
| `created_at` | `created_at` | Match |

The frontend renders `plan_name` in the table (line 271) and detail views, but the backend only returns `source_scheme_id` (a plan ID, not name). To display plan names, the frontend would need to cross-reference the plans list or have the backend include the name.

**Fix**: Either (A) update the backend `to_dict()` to include `plan_name` by looking it up from PlanStore, or (B) have the frontend fetch plans separately and join by `source_scheme_id`.

---

### 3.2 [MEDIUM] Log entry shape mismatch

**File**: `AutoTrade.tsx:59-65, 506-528`

Frontend `LogEntry` expects:
```typescript
{ id: string, time: string, action: string, detail: string, level: 'info'|'success'|'warning'|'error' }
```

Backend `ExecutionLogEntry` returns:
```python
{ timestamp: str, level: "INFO"|"WARN"|"ERROR"|"BUY"|"SELL", message: str, details: dict }
```

The field names are completely different: `time` vs `timestamp`, `action`+`detail` vs `message`+`details`. The level values also differ (lowercase vs uppercase, different set). The log timeline at line 518 accesses `log.action`, `log.detail`, `log.time` -- all will be `undefined`.

**Fix**: Update the `LogEntry` interface and rendering to match the backend's `ExecutionLogEntry` shape:
```typescript
interface LogEntry {
  timestamp: string
  level: string  // "INFO" | "WARN" | "ERROR" | "BUY" | "SELL"
  message: string
  details: Record<string, unknown>
}
```

Update the timeline rendering at line 510-528 to use `log.message` instead of `log.action`+`log.detail`, and `log.timestamp` instead of `log.time`.

---

## 4. Frontend Routing and Integration

### 4.1 [OK] App.tsx routing and menu

**File**: `App.tsx:47-48, 67`

The AutoTrade route and menu item are correctly configured:
- Menu item: key=`/auto-trade`, icon=`RobotOutlined`, label=`量化交易` (line 48)
- Route: path=`/auto-trade`, element=`<AutoTrade />`, roles=`admin`, `internal_analyst`, `user` (line 67)

The `Strategy.tsx` `generateQuantStrategy` function (line 69-83) correctly:
- Calls `POST /api/v1/strategy/generate-from-scheme/{id}` (matches backend route)
- Navigates to `/auto-trade` on success (line 75)
- This integration path is CORRECT

### 4.2 [HIGH] No `trade_mode`/`check_interval_sec`/`capital` in form

**File**: `AutoTrade.tsx:553-579`

The create/edit form is missing these backend-required fields:
- `trade_mode` (`paper` / `live`)
- `check_interval_sec` (default 300)
- `capital` (initial capital)
- `picks` (stock selection)

These are critical for the strategy to execute. Without them, the backend uses defaults, but the user has no visibility or control.

**Fix**: Add form fields for `trade_mode` (Select with paper/live options), `check_interval_sec` (InputNumber), and `capital` (InputNumber). For `picks`, integrate with the plan/screener flow.

---

## 5. UX and Implementation Quality

### 5.1 [OK] State management and countdown timer

The `loadStrategies` polling (manual refresh + useEffect on mount) is appropriate for Phase A. The countdown timer at line 253-256 uses a 1-second `setInterval` to update `next_rebalance_at` display -- this is lightweight and appropriate.

### 5.2 [OK] Edit/Create Drawer structure

The Form.List approach for buy/sell conditions and risk rules is well-structured. The `enabled` Switch per condition is a UX convenience not present in the backend model -- it would need to be stripped or translated before sending.

### 5.3 [LOW] Delete strategy operation silent on failure

**File**: `AutoTrade.tsx:232-236`

```typescript
const deleteStrategy = async (id: string) => {
    await fetch(`/api/v1/auto-trade/strategies/${id}`, { method: 'DELETE' })
    message.success('策略已删除')
    loadStrategies()
}
```

No error handling on the delete response -- even if the server returns 404/500, the frontend shows "策略已删除" and refreshes. Compare with `actionStrategy` which properly checks `r.ok`.

**Fix**: Add `if (!r.ok)` error handling matching the pattern in `actionStrategy`.

### 5.4 [LOW] Detail view closes drawer on action

**File**: `AutoTrade.tsx:407, 412`

When the user clicks pause/resume/stop from the detail drawer, the drawer closes (`setDetailStrategy(null)`). This is disorienting -- the user loses context. A better UX would keep the drawer open and refresh the detail data.

---

## Audit Checklist

| Check | Result |
|-------|--------|
| API base path matches backend | **BLOCKED** -- `/api/v1/auto-trade/` vs `/api/v1/strategy/` |
| Request body shape matches Pydantic schema | **BLOCKED** -- completely different structure (2.1) |
| Status values match backend enum | **BLOCKED** -- `running/terminated/completed` vs `active/stopped/draft` |
| Log entry fields match backend shape | **FAIL** -- field names differ (3.2) |
| Route registration in App.tsx | OK |
| Strategy.tsx → AutoTrade navigation | OK |
| execution_mode in sync with backend | Missing (backend doesn't have it) |
| Error handling pattern consistency | Partial (delete path missing) |
| Form covers all required fields | Missing trade_mode, capital, picks |

---

## Verdict: BLOCK

**Must fix before merge:**
1. Change all API calls from `/api/v1/auto-trade/` to `/api/v1/strategy/` (1.1)
2. Align status values: `running` -> `active`, `terminated` -> `stopped`, add `draft` (2.2)
3. Transform form values to match backend `CustomStrategyRequest` schema before submit (2.1)
4. Fix log rendering to use backend `ExecutionLogEntry` field names (3.2)

**Should fix before merge:**
5. Add `trade_mode`, `check_interval_sec`, `capital`, `picks` form fields (4.2)
6. Add error handling to `deleteStrategy` (5.3)
7. Update `QuantStrategy` interface to match `StrategyConfig.to_dict()` response or add a data transform layer (3.1)

**Can defer to Phase B:**
8. Integration with picks from plans/screener
9. Real-time position/PnL display (separate trade-service calls)
10. Detail drawer stay-open-on-action UX improvement
