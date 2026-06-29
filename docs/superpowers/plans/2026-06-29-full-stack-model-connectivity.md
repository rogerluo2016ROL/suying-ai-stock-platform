# Full Stack Model Connectivity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Suying AI usable end to end across frontend pages, backend APIs, data services, and model services, with real API verification instead of browser mocks.

**Architecture:** Keep the existing React + Vite frontend, unified `/api/v1` gateway, and FastAPI microservice layout. First build a page-to-API truth table and a repeatable smoke suite, then fix the highest-risk pages in batches, and finally run browser + API validation against the real local/UAT service stack.

**Tech Stack:** React 18, Vite, TypeScript, Ant Design, axios API client, FastAPI microservices, PostgreSQL, Redis, Playwright, Vitest, pytest.

## Global Constraints

- Answer and reporting language: Chinese.
- Use CodeGraph before broad grep/read when locating code in this indexed repo.
- Keep reads targeted and avoid generated/heavy directories: `Kronos/`, `node_modules/`, `.venv/`, `backend/.venv/`, `frontend/dist/`, `outputs/`, `output/`, `.playwright-*`, `.pnpm-store/`, `.codegraph/`.
- Trading-related changes are high risk; paper/live mode boundaries must be preserved.
- Default dev admin: `admin@suying.ai` / `Admin123!`.
- PostgreSQL dev DSN uses localhost port `6432`; Redis uses `7379`.
- Prefer low-I/O wrappers: `bash tools/codex-lowio.sh py ...`, `bash tools/codex-lowio.sh fe-test ...`, `bash tools/codex-lowio.sh fe-typecheck`.
- Do not treat mock-based browser UAT as proof of real backend/model connectivity.

---

## Current Findings

Recent docs show the platform has made real progress:

- `docs/reviews/platform-b12-page-connectivity-audit-2026-06-27.md`: frontend API calls largely converge to `/api/v1` through the gateway.
- `docs/reviews/platform-b13-frontend-backend-connectivity-2026-06-28.md`: core read-only API smoke passed for auth, screener, dashboard, data status, strategy, trade, backtest, and diagnosis.
- `docs/reviews/full-platform-new-ui-uat-2026-06-28.md`: 67 frontend routes passed browser smoke, but with browser-level API mocks.

Remaining gap:

- Some pages are stable visually but not truly connected to live backend/model data.
- System/model pages such as `Training.tsx`, `ModelRegistry.tsx`, `RuntimeStatus.tsx`, and `PlatformUpgrade.tsx` still look prototype-heavy.
- `signal/data-status` was previously slow, about 24-28 seconds in UAT.
- `dashboard/summary` previously returned `status=no_data` until pipeline data exists.
- Full-stack smoke currently covers a core chain, but not every page or admin/model function.

## Page Risk Matrix

| Area | Frontend page | Current risk | Target |
|---|---|---|---|
| Login/Auth | `LoginPage`, `RegisterPage`, `AuthContext` | Medium | Login, refresh, logout, role routing all verified through real auth service |
| Dashboard/Open Decision | `Dashboard.tsx`, `OpenDecision.tsx` | Medium | No-data and real-data states both render; pipeline trigger has visible result/error |
| Screener | `Screener.tsx`, `ScreenerV2.tsx` | Medium | Modes, run, sync trigger, score details, and trade date behavior verified |
| Supply Chain | `SupplyChainBom.tsx` and child components | High | Policy interpretation, chain deconstruction, node/company drilldown, mapping review all verified or clearly disabled |
| Predictions | `Predictions.tsx` | Medium | Status, single prediction, fast prediction, and batch/meta behavior verified |
| Signals | `Signals.tsx` | Medium | Live, history, and single-code analysis verified with fallback states |
| Strategy | `Strategy.tsx`, strategy parts of `NewUiModulePage.tsx` | High | Plan list/detail/create/add picks/delete use current strategy API, not stale `/strategy/list` assumptions |
| Trade | `Trade.tsx`, `AuditLog.tsx`, `RiskVerdicts.tsx`, `DecisionContexts.tsx` | High | Paper order, pre-check, account, positions, orders, audit export, risk verdicts verified; live remains gated |
| Auto Trade | `AutoTrade.tsx` | High | Strategy logs/config/monitor either backed by real endpoints or shown as disabled with reason |
| Risk Control | `RiskControl.tsx` | High | Risk overview/positions/strategies/market/audit use real data or explicit unavailable states |
| Backtest | `Backtest.tsx` | Medium | Factors, run, compare/calibrate, lineage review verified |
| Diagnosis | `Diagnosis.tsx` | Medium | Analyze, compare, history, PDF error handling verified |
| Training | `Training.tsx` | High | Replace static queue/cards with training-service list/status/run APIs or disable creation safely |
| Model Registry | `ModelRegistry.tsx` | High | Replace static registry/cards with training-service model registry APIs |
| Data Update | `DataUpdate.tsx` | Medium | Data status, trigger sync, schedules, partial-response fallback verified |
| Runtime Status | `RuntimeStatus.tsx` | High | Replace hard-coded health matrix with `healthApi` checks and actual service status |
| Platform Upgrade/P0 | `PlatformUpgrade.tsx`, `P0Workflow.tsx` | Medium | Keep as progress/control pages, but avoid claiming unavailable automations are live |

## Task 1: Build The Connectivity Inventory

**Files:**
- Create: `docs/reviews/full-stack-page-connectivity-audit-2026-06-29.md`
- Create: `tools/page_connectivity_inventory.py`
- Modify: none

**Interfaces:**
- Consumes: frontend route list from `frontend/src/App.tsx`, API client definitions from `frontend/src/api/client.ts`, page API usage from `frontend/src/pages/*`.
- Produces: a page-to-endpoint matrix used by all later tasks.

- [ ] List all protected routes from `frontend/src/App.tsx`.
- [ ] Map each route to its page component.
- [ ] Map each page component to API methods or note `static/prototype`.
- [ ] Mark each endpoint as one of: `verified`, `needs-smoke`, `missing-backend`, `prototype-only`, `disabled-by-design`.
- [ ] Save findings in `docs/reviews/full-stack-page-connectivity-audit-2026-06-29.md`.
- [ ] Run focused checks:

```bash
bash tools/codex-lowio.sh fe-typecheck
```

Expected: TypeScript passes before functional remediation begins.

## Task 2: Expand API Smoke Coverage

**Files:**
- Modify: `tools/full_stack_smoke.py`
- Create: `tools/page_api_smoke.py`
- Create: `tools/tests/test_page_api_smoke.py`

**Interfaces:**
- Consumes: endpoint matrix from Task 1.
- Produces: a repeatable command that verifies auth, page-critical read APIs, and safe write APIs in paper/test mode.

- [ ] Keep existing core chain in `tools/full_stack_smoke.py`: auth -> screener -> diagnosis -> strategy -> backtest -> paper trade.
- [ ] Add page-level smoke in `tools/page_api_smoke.py` for dashboard, signal, data update, supply chain, prediction, audit log, risk verdicts, decision contexts, training, model registry, and health.
- [ ] Mark destructive or costly operations as opt-in flags.
- [ ] Add tests for URL construction, auth header forwarding, and safe skip behavior.
- [ ] Run:

```bash
bash tools/codex-lowio.sh py tools/tests/test_page_api_smoke.py -q
```

Expected: tests pass without requiring live services.

## Task 3: Fix Stale Frontend API Contracts

**Files:**
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/api/liveTrade.ts`
- Modify: `frontend/src/pages/Strategy.tsx`
- Modify: `frontend/src/pages/AutoTrade.tsx`
- Modify: `frontend/src/pages/NewUiModulePage.tsx`
- Test: existing focused Vitest files plus new tests if stale contracts are found.

**Interfaces:**
- Consumes: API routes from strategy/trade/backtest/diagnosis services.
- Produces: frontend calls that match real backend endpoints under `/api/v1`.

- [ ] Replace stale direct paths such as `/strategy/list`, `/strategy/{id}`, and `/strategy/{id}/log` if the backend exposes different route names.
- [ ] Add typed API helpers instead of calling the default axios client directly from pages.
- [ ] Ensure failed optional calls render an actionable unavailable state, not fake success.
- [ ] Run:

```bash
bash tools/codex-lowio.sh fe-test StrategyLineage AutoTradeLineageLog
bash tools/codex-lowio.sh fe-typecheck
```

Expected: focused frontend tests and typecheck pass.

## Task 4: Connect System And Model Pages To Real Services

**Files:**
- Modify: `frontend/src/pages/Training.tsx`
- Modify: `frontend/src/pages/ModelRegistry.tsx`
- Modify: `frontend/src/pages/RuntimeStatus.tsx`
- Modify: `frontend/src/api/client.ts`
- Test: `frontend/src/__tests__/Phase5SystemPages.test.tsx`

**Interfaces:**
- Consumes: training-service routes, model registry schemas, health API.
- Produces: real status views for training jobs, model registry, and service health.

- [ ] Add `trainingApi` helpers for job list/status/run only after confirming existing backend paths.
- [ ] Add `modelRegistryApi` helpers for model list/detail/stage changes only after confirming existing backend paths.
- [ ] Replace hard-coded runtime services with `healthApi.gateway()` and `healthApi.checkOnline(service)`.
- [ ] Keep model training write actions disabled unless the backend and data prerequisites are healthy.
- [ ] Run:

```bash
bash tools/codex-lowio.sh fe-test Phase5SystemPages
bash tools/codex-lowio.sh fe-typecheck
```

Expected: system pages render real loading/success/error states.

## Task 5: Verify Data And Model Service Reality

**Files:**
- Modify only if needed after smoke results:
  - `services/prediction-service/app/routes.py`
  - `services/training-service/app/routes.py`
  - `services/signal-service/app/routes.py`
  - `services/screener-service/app/routers/screener.py`
- Create/modify focused service tests as needed.

**Interfaces:**
- Consumes: PostgreSQL data freshness, prediction status, training/model registry endpoints.
- Produces: backend services that return honest status and structured fallback reasons.

- [ ] Verify latest daily/intraday data dates before judging model output.
- [ ] Verify prediction service can return a real prediction or a clear unavailable reason.
- [ ] Verify training service can list jobs/models even when no active training exists.
- [ ] Verify signal/data-status latency; if still slow, add a cached/lightweight summary endpoint or cache layer.
- [ ] Run focused pytest commands against changed services only.

Expected: no page depends on silent fake model data.

## Task 6: Browser UAT Without API Mocks

**Files:**
- Create: `tools/browser_full_platform_real_api_smoke.py` or Playwright test under the existing frontend test structure.
- Create: `docs/qa/full-platform-real-api-uat-2026-06-29.md`

**Interfaces:**
- Consumes: real local/UAT services, default dev admin.
- Produces: screenshot/evidence-backed page UAT report.

- [ ] Start or target the existing local/UAT service stack.
- [ ] Login as `admin@suying.ai`.
- [ ] Visit every protected route from the route matrix.
- [ ] For each page, check app shell, main content, console errors, failed network requests, and one primary user action where safe.
- [ ] Capture screenshots and JSON result summary.
- [ ] Run final checks:

```bash
bash tools/codex-lowio.sh fe-typecheck
bash tools/codex-lowio.sh fe-test
python tools/full_stack_smoke.py
python tools/page_api_smoke.py
```

Expected: all critical routes pass, high-risk unavailable items are documented with exact backend/data blockers.

## Execution Order

1. Inventory first: do not fix blindly.
2. API smoke second: prove backend gaps separately from UI gaps.
3. Stale frontend contracts third: remove broken assumptions.
4. System/model pages fourth: turn prototype pages into real status pages.
5. Data/model verification fifth: make fallback reasons honest.
6. Browser UAT last: validate the real user path.

## Confirmation Needed

Recommended execution after approval:

1. Inline execution for Task 1 and Task 2, because they are audit/smoke scaffolding and will refine the exact fix list.
2. Subagent-driven execution for Tasks 3-5 if the inventory finds independent frontend/backend/model gaps.
3. Inline final verification for Task 6 so the evidence stays in one place.

