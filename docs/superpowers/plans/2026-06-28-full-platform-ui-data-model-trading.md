# Full Platform Prototype Rollout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring every optimized prototype preview in `docs/design/New design/01 PRD 文档/` into the real React app, then connect frontend, backend, model services, PostgreSQL data, and simulated/QMT-ready trading into one verified product path.

**Architecture:** Use the optimized HTML previews as the visual source of truth, not the older UAT pages. Implement reusable React shell, tabs, cards, charts, workflow controls, and domain panels first, then migrate all 63 preview pages by module while keeping backend contracts explicit and tenant/account scoped. Backend/model/trading work starts only after the UI route contract is stable, with MockBroker/sandbox as the default trading path.

**Tech Stack:** React 18, Vite 6, TypeScript 5.6, Ant Design 5.22, ECharts 5.5, FastAPI, Pydantic v2, PostgreSQL 15, Redis 7, Kronos/LightGBM/CatBoost, Xtquant QMT-compatible broker abstraction.

## Global Constraints

- UI source of truth: optimized HTML previews under `docs/design/New design/01 PRD 文档/`.
- Remove redundant platform-scope/status explainer strips from page bodies; keep account/tenant/trade-mode context compactly in shell/header.
- Preserve page interactions: tabs, filters, dropdowns, forms, drawers, modals, tables, hover/click affordances, and first-screen controls must remain functional.
- Public data: market, factor, model registry, shared universe, shared reference data.
- Private data: tenant/account strategies, plans, orders, positions, risk verdicts, decision contexts.
- Keep trading changes conservative: simulated trading first, QMT sandbox wiring before live broker path.
- Do not revert unrelated dirty worktree changes.
- Verification gate: frontend unit/type/build, backend unit/service tests, API smoke, browser UAT screenshots.

---

### Phase 0: Prototype Inventory, Route Matrix, and Acceptance Gates

**Files:**
- Modify: `docs/superpowers/plans/2026-06-28-full-platform-ui-data-model-trading.md`
- Create: `docs/design/New design/prototype-page-map.md`

**Produces:**
- Canonical 63-page preview inventory.
- Target route/component matrix.
- Phase-level acceptance gates.

- [x] Count optimized preview pages and PRD/detail design documents.
- [x] Identify current React routes in `frontend/src/App.tsx`.
- [ ] Write the route/API matrix in `docs/design/New design/prototype-page-map.md`.
- [ ] Mark Phase 0 complete only after the matrix covers all 63 preview pages.

### Phase 1: Shared Design System and Application Shell

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/styles/suying-app.css`
- Create: `frontend/src/components/prototype/PrototypeLayout.tsx`
- Create: `frontend/src/components/prototype/PrototypeTabs.tsx`
- Create: `frontend/src/components/prototype/MetricCard.tsx`
- Test: `frontend/src/__tests__/AppShellPreview.test.tsx`

**Produces:**
- Shell matching optimized previews: left navigation, market ticker header, compact user/account controls, light default style.
- Shared page header, workflow tabs, status chips, cards, table wrappers, metric strips, and empty-state pattern.

- [ ] Add tests asserting shell labels, market ticker, no redundant platform explainer strip, and light preview classes.
- [ ] Add reusable prototype components with typed props.
- [ ] Move repeated visual rules from previews into `suying-app.css` without breaking existing Ant Design pages.
- [ ] Run `cd frontend && npx vitest run src/__tests__/AppShellPreview.test.tsx`.
- [ ] Run `cd frontend && npx tsc -b --noEmit`.

### Phase 2: Full Route and Module Tab Structure

**Files:**
- Modify: `frontend/src/App.tsx`
- Create/modify page modules under `frontend/src/pages/`
- Test: `frontend/src/__tests__/PrototypeRoutes.test.tsx`

**Produces:**
- Every preview page has a real React route or a real module sub-tab route.
- Main navigation groups match the prototype taxonomy: 行情决策, 交易执行, 模型/系统.

- [ ] Add route tests for all 63 preview targets from the page matrix.
- [ ] Expand menu items and route-title resolution.
- [ ] Add module-level tab routes for duplicated prototype groups instead of repeated page-body nav strips.
- [ ] Run route tests and TypeScript.

### Phase 3: 行情决策 Pages

**Files:**
- Modify/create: `frontend/src/pages/Dashboard.tsx`
- Modify/create: `frontend/src/pages/OpenDecision.tsx`
- Modify/create: `frontend/src/pages/Screener.tsx`
- Modify/create: `frontend/src/pages/SupplyChainBom.tsx`
- Modify/create: `frontend/src/pages/Predictions.tsx`
- Modify/create: `frontend/src/pages/Signals.tsx`
- Tests: page tests for modules 1.x, 2.x, 3.x, 4.x, 5.x, 6.x.

**Preview coverage:**
- `1.1` to `1.4`: 智能看板.
- `2.1` to `2.5`: 开盘决策.
- `3.1` to `3.3`: 智能选股.
- `4.1` to `4.3`: 产业链拆解.
- `5.0` to `5.3`: K线预测.
- `6.0` to `6.3`: 交易信号.

- [ ] Replace old `Dashboard.tsx` first with the `1.1 sentiment-dashboard-preview.html` structure.
- [ ] Implement tabbed dashboards for 1.x without duplicate body-level nav.
- [ ] Rebuild 开盘决策 pages, including 竞价分析 content that is no longer an abnormal empty grid.
- [ ] Restore 产业链解构 three modes: 上下游拆解, 价值链拆解, 竞争格局.
- [ ] Split K线预测 overview and single-stock content so `5.0` and `5.1` are not duplicates.
- [ ] Run targeted page tests, TypeScript, and browser smoke.

### Phase 4: 交易执行 Pages

**Files:**
- Modify/create: `frontend/src/pages/Trade.tsx`
- Modify/create: `frontend/src/pages/AutoTrade.tsx`
- Modify/create: `frontend/src/pages/Strategy.tsx`
- Modify/create: `frontend/src/pages/Backtest.tsx`
- Modify/create: `frontend/src/pages/RiskVerdicts.tsx`
- Modify/create: `frontend/src/pages/DecisionContexts.tsx`
- Tests: P0 chain and trade page tests.

**Preview coverage:**
- `7.0` to `7.5`: 交易中心.
- `8.1` to `8.4`: 量化交易.
- `9.1` to `9.4`: 方案管理.
- `10.0` to `10.5`: 风控中心.
- `11.0` to `11.3`: 回测分析.

- [ ] Implement P0 main chain: 候选池 -> 方案管理 -> 下单面板 -> 风控闸门 -> 回测复盘.
- [ ] Keep live trading disabled unless explicit broker config and risk verdict allow it.
- [ ] Ensure every order links to DecisionContext and RiskVerdict.
- [ ] Run trade/strategy/backtest tests plus paper-trade API smoke.

### Phase 5: 模型/系统 Pages

**Files:**
- Modify/create: `frontend/src/pages/Diagnosis.tsx`
- Modify/create: `frontend/src/pages/Training.tsx`
- Modify/create: `frontend/src/pages/ModelRegistry.tsx`
- Modify/create: `frontend/src/pages/DataUpdate.tsx`
- Create: `frontend/src/pages/RuntimeStatus.tsx`
- Tests: system/model page tests.

**Preview coverage:**
- `12.0` to `12.4`: 个股诊断.
- `13.0` to `13.2`: 模型训练.
- `14.0`: 模型注册.
- `15.0` to `15.3`: 数据更新.
- `16.0`: 运行状态.

- [ ] Implement diagnosis overview/perspective/compare/risk pages.
- [ ] Implement model training and MLflow experiment pages.
- [ ] Implement model registry and data update sub-pages.
- [ ] Add runtime status page and route.
- [ ] Run model/system page tests and TypeScript.

### Phase 6: Backend API Contract and Tenant Boundary

**Files:**
- Modify: `frontend/src/api/types.ts`
- Modify: `frontend/src/api/client.ts`
- Modify: `services/api-gateway/app/main.py`
- Modify: `services/trade-service/app/schemas.py`
- Modify service route/store files as required.
- Tests: backend/service/API contract tests.

**Produces:**
- Stable object contracts: `DecisionContext`, `Candidate`, `Plan`, `Order`, `RiskVerdict`.
- Tenant/account data isolation for private objects.
- Shared public data for market/model/reference tables.

- [ ] Add tests for serialization and tenant/account scoping.
- [ ] Align gateway routes to frontend page data needs.
- [ ] Add or fix stores for private objects with `tenant_id`, `user_id`, `account_id`.
- [ ] Run backend and changed service tests.

### Phase 7: Model Service Real Data Adaptation

**Files:**
- Modify: `services/prediction-service`
- Modify: `services/screener-service`
- Modify: `services/signal-service`
- Modify: `services/training-service`
- Modify: `packages/kronos-*` only where response shape or runtime adapter requires it.
- Tests: model service tests and smoke.

**Produces:**
- Prediction, screener, signal, diagnosis, and training pages can consume real service payloads.
- Model responses include model id/version, confidence, lineage, and fallback state.

- [ ] Add failing API smoke checks for model-backed page endpoints.
- [ ] Fix response shape drift between services and UI contracts.
- [ ] Verify minimal inference path with available local checkpoints or documented fallback.

### Phase 8: Trading and Broker Integration

**Files:**
- Modify: `services/trade-service`
- Modify: `services/strategy-service/app/auto_trading_executor.py`
- Modify: `frontend/src/hooks/useLiveTrade.ts`
- Modify: trading pages from Phase 4 as needed.
- Tests: broker/risk/order tests and paper-trade smoke.

**Produces:**
- MockBroker/paper trading usable from UI.
- QMT/Xtquant adapter remains gated behind sandbox/live config and risk verdict.
- Broker abstraction ready for additional brokers.

- [ ] Require risk verdict before submit.
- [ ] Verify simulated order creation, audit log, and position/account refresh.
- [ ] Verify QMT path is config-gated and does not submit live orders by default.

### Phase 9: End-to-End Verification and UAT Evidence

**Files:**
- Create: `docs/reviews/full-platform-prototype-rollout-2026-06-28.md`
- Optional: browser screenshots under an existing review/evidence folder.

**Commands:**
- `cd frontend && npx vitest run`
- `cd frontend && npx tsc -b --noEmit`
- `cd frontend && npm run build`
- `cd backend && .venv/bin/pytest tests/ -v`
- Changed service tests under `services/*/tests`.
- Gateway API smoke through UAT ports.
- Browser UAT smoke for every route in `prototype-page-map.md`.

- [ ] Capture actual command outputs and failures.
- [ ] Fix regressions until the verification gate passes or a true external dependency is isolated.
- [ ] Record final route coverage, known limits, and live-trading safety status.
