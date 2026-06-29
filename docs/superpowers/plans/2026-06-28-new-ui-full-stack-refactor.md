# New UI Full-Stack Refactor Plan

> Implementation instruction: execute with `superpowers:executing-plans`. Track every checkbox. Do not skip verification gates.

## Goal

Rebuild the real application from the optimized prototypes in `docs/design/New design/01 PRD 文档/`, then adapt backend, model services, data contracts, and trading services so the product can connect to real PostgreSQL data and run the full paper-trading decision loop from the frontend.

## Non-Negotiable Decisions

- The optimized HTML previews are the UI source of truth.
- `frontend/src/pages/NewUiModulePage.tsx` is not a final implementation pattern. It may only serve as a temporary fallback during migration.
- Every page must be implemented from its own preview and PRD/detail design.
- The frontend shell owns global context. Page bodies must not repeat role/data/account/broker explainer strips.
- Private objects must be scoped by tenant/user/account.
- Simulated trading ships before live trading. QMT/live remains gated by broker config, risk verdict, and audit.

## Phase 0: Re-Open and Freeze Source of Truth

**Purpose:** Re-audit previous work and freeze the new target before writing feature code.

**Files:**
- `docs/design/New design/00 全站新UI落地改造方案.md`
- `docs/design/New design/00 公共对象字段契约.md`
- `docs/design/New design/prototype-page-map.md`
- this plan file

**Tasks:**

- [x] Audit optimized preview inventory under `docs/design/New design/01 PRD 文档/`.
- [x] Audit reference design spec under `docs/design/New design/02 参考原型/`.
- [x] Audit current frontend shell/routes/pages and identify generic-page gap.
- [x] Audit backend/platform/trade/model interface baseline.
- [x] Document that `NewUiModulePage` is shell-only, not completed page rollout.
- [x] Confirm every target page in `prototype-page-map.md` has owner route, component, API owner, and status.
- [ ] Optional: create implementation issue list from the matrix if GitHub issue workflow is requested later.

**Gate:** Phase 0 passes when docs clearly define target UI, object contract, and route matrix.

## Phase 1: Frontend Foundation and Shell Parity

**Purpose:** Convert preview shell and visual tokens into production React infrastructure.

**Files:**
- `frontend/src/App.tsx`
- `frontend/src/styles/suying-app.css`
- `frontend/src/components/prototype/*`
- `frontend/src/components/layout/*`
- `frontend/src/types/platform.ts`
- `frontend/src/__tests__/AppShellPreview.test.tsx`
- `frontend/src/__tests__/PrototypeComponents.test.tsx`

**Tasks:**

- [x] Replace generic shell assumptions with preview-faithful `AppShell`.
- [x] Keep left nav as first-level modules only.
- [x] Move role/tenant/account/trade mode into compact header context.
- [x] Remove page-body platform explainer strips from all routes.
- [x] Build shared primitives: module tabs, segment tabs, metric card, data table, action bar, right rail, empty state, risk banner, lineage chips.
- [x] Ensure CSS tokens match reference prototype: A-share red up, green down, dense workstation layout, 8px panels, mono numerics.
- [x] Add shell tests for navigation, market ticker, user/account controls, and absence of redundant body strips.

**Verification:**

- [x] `cd frontend && npx vitest run src/__tests__/AppShellPreview.test.tsx src/__tests__/PrototypeComponents.test.tsx`
- [x] `cd frontend && npx tsc -b --noEmit`

## Phase 2: Route and Page Skeleton Rollout

**Purpose:** Give every preview a concrete React route and nonblank page skeleton.

**Files:**
- `frontend/src/App.tsx`
- `frontend/src/pages/*`
- `frontend/src/__tests__/PrototypeRoutes.test.tsx`

**Tasks:**

- [x] Replace generic route rendering with page-specific modules.
- [x] Implement route table for all preview pages in `prototype-page-map.md`.
- [x] Add route tests that render each page under auth.
- [x] Add per-page skeleton with correct module tabs, title, core panels, and fallback state.
- [x] Keep old functional pages only behind the new page adapter when reuse is safe.

**Verification:**

- [x] `cd frontend && npx vitest run src/__tests__/PrototypeRoutes.test.tsx`
- [x] `cd frontend && npx tsc -b --noEmit`

## Phase 3: 行情决策 UI Rebuild

**Purpose:** Rebuild modules 1-6 from prototypes, not from the generic module page.

**Pages:**
- 1.x 智能看板
- 2.x 开盘决策
- 3.x 智能选股
- 4.x 产业链拆解
- 5.x K线预测
- 6.x 交易信号

**Tasks:**

- [x] Rebuild `Dashboard` from `1.1` to `1.4`, including market sentiment, auction intent, signal overview, watchlist tracking.
- [x] Rebuild `OpenDecision` from `2.1` to `2.5`, including candidate pool and execution monitor.
- [x] Fix `2.2 auction-analysis` abnormal empty-column layout with real auction cards, sector resonance, candidate preview, and lock actions.
- [x] Rebuild `Screener` from `3.1` to `3.3`, including strategy mode tabs, model comparison, factor analysis.
- [x] Rebuild `SupplyChainBom` from `4.1` to `4.3`; `4.2` must include 上下游拆解, 价值链拆解, 竞争格局.
- [x] Rebuild `Predictions` from `5.0` to `5.3`; prediction overview and single-stock prediction must be distinct.
- [x] Rebuild `Signals` from `6.0` to `6.3`, including signal detail, history, risk scan.
- [x] Add page-level interaction tests for tabs, filters, selections, and fallback states.

**Verification:**

- [x] `cd frontend && npx vitest run src/__tests__/Dashboard.test.tsx src/__tests__/OpenDecision.test.tsx src/__tests__/Predictions.test.tsx`
- [x] Add and run missing module tests for Screener, SupplyChain, Signals.
- [ ] Browser smoke screenshots for representative 1.x-6.x routes.

## Phase 4: 交易执行 UI Rebuild

**Purpose:** Rebuild P0 decision loop and trading pages with risk gates.

**Pages:**
- 7.x 交易中心
- 8.x 量化交易
- 9.x 方案管理
- 10.x 风控中心
- 11.x 回测分析
- `0.2 p0-main-flow-preview.html`

**Tasks:**

- [x] Rebuild `P0Workflow` around Candidate -> Plan -> Order -> RiskVerdict -> BacktestReview.
- [x] Rebuild `Trade` from `7.0` to `7.5`, including order panel, positions, orders, account overview, broker management.
- [x] Rebuild `AutoTrade` from `8.1` to `8.4`, including strategy market/config/monitor/logs.
- [x] Rebuild `Strategy` from `9.1` to `9.4`, including plan list/detail/compare/settlement report.
- [x] Rebuild `RiskControl` from `10.0` to `10.5`, including account, position, strategy, market, audit risk.
- [x] Rebuild `Backtest` from `11.0` to `11.3`, including run, compare, trade detail.
- [x] Ensure every trade action shows disabled/reason state until risk and broker preconditions pass.

**Verification:**

- [x] `cd frontend && npx vitest run src/__tests__/P0WorkflowPageIntegration.test.tsx src/__tests__/TradeFormValidation.test.tsx`
- [x] Add and run tests for Strategy, RiskControl, Backtest route interactions.
- [ ] Browser smoke for full P0 path.

## Phase 5: 模型与系统 UI Rebuild

**Purpose:** Rebuild admin/model/data/runtime pages without exposing them to roles that should not use them.

**Pages:**
- 12.x 个股诊断
- 13.x 模型训练
- 14.x 模型注册
- 15.x 数据更新
- 16.x 运行状态
- `0.3 platform-upgrade-preview.html`

**Tasks:**

- [x] Rebuild `Diagnosis` from `12.0` to `12.4`.
- [x] Rebuild `Training` from `13.0` to `13.2`.
- [x] Rebuild `ModelRegistry` from `14.0`.
- [x] Rebuild `DataUpdate` from `15.0` to `15.3`.
- [x] Rebuild `RuntimeStatus` from `16.0`.
- [x] Rebuild `PlatformUpgrade` from `0.3`.
- [x] Hide admin-only routes from investor/trader roles.

**Verification:**

- [x] `cd frontend && npx vitest run src/__tests__/DataUpdate.test.tsx`
- [x] Add and run tests for Diagnosis, Training, ModelRegistry, RuntimeStatus.
- [ ] Browser smoke for admin role routes.

## Phase 6: BFF and API Contract Layer

**Purpose:** Make the new UI consume page contracts instead of stitching raw services ad hoc.

**Files:**
- `frontend/src/api/types.ts`
- `frontend/src/api/client.ts`
- `services/api-gateway/app/main.py`
- service route files as needed

**Tasks:**

- [x] Define TypeScript ViewModel types for each module group.
- [x] Add BFF routes under `/api/v1/workbench/*`.
- [x] Add response envelope: page, context, data_domain, freshness, lineage, sections, actions.
- [x] Preserve direct service APIs for existing tests and specialized pages.
- [x] Normalize empty/fallback states server-side.
- [x] Add contract tests for BFF response shape.

**Verification:**

- [x] `cd frontend && npx vitest run src/__tests__/apiClientPlatformContext.test.ts`
- [x] `cd services/api-gateway && pytest tests/ -v`
- [x] Changed service route tests.

## Phase 7: Persistence and Tenant Isolation

**Purpose:** Move formal private objects away from memory stores into PostgreSQL-backed tables.

**Files:**
- `backend/alembic/versions/*`
- `backend/app/models/*`
- `services/strategy-service/app/plan_store.py`
- `services/trade-service/app/*store.py`
- `services/screener-service/app/*`

**Tasks:**

- [x] Persist CandidatePool with tenant/user/account scope.
- [x] Persist Plan lifecycle and candidate snapshots.
- [x] Persist DecisionContext, Order, RiskVerdict, and audit events.
- [x] Keep memory stores only as test/fallback implementations.
- [x] Add tenant/account filtering to list/get/update/delete.
- [x] Ensure frontend never chooses unauthorized tenant/account scope.

**Verification:**

- [x] `cd backend && .venv/bin/pytest tests/test_platform_context.py tests/test_platform_models.py -v`
- [x] `cd services/strategy-service && pytest tests/ -v`
- [x] `cd services/trade-service && pytest tests/ -v`
- [x] `cd services/screener-service && pytest tests/ -v`

## Phase 8: Model/Data Adaptation

**Purpose:** Adapt models and data services to the new pages and contracts.

**Services:**
- prediction-service
- screener-service
- signal-service
- diagnosis-service
- training-service
- data-service
- packages/kronos-*

**Tasks:**

- [x] Add model metadata to prediction/signal/diagnosis outputs.
- [x] Split prediction overview, single-stock, multi-compare, and accuracy backtest endpoints.
- [x] Add data freshness and quality fields consumed by every page.
- [x] Align supply-chain modes with upstream/downstream, value chain, and competitive landscape.
- [x] Add fallback_reason for missing model checkpoint or missing source data.
- [x] Add service tests for response compatibility.

**Verification:**

- [x] `cd services/prediction-service && pytest tests/ -v`
- [x] `cd services/screener-service && pytest tests/ -v`
- [x] `cd services/diagnosis-service && pytest tests/ -v`
- [x] `cd services/training-service && pytest tests/ -v`
- [x] `cd services/signal-service && pytest tests/ -v`
- [x] `cd frontend && npx tsc -b --noEmit`

## Phase 9: Trading, Broker, and End-to-End UAT

**Purpose:** Finish usable paper-trading loop and gated broker-live path.

**Files:**
- `services/trade-service/app/*`
- `services/strategy-service/app/auto_trading_executor.py`
- `frontend/src/hooks/useLiveTrade.ts`
- trading UI pages

**Tasks:**

- [x] Paper trading E2E: candidate -> plan -> risk precheck -> order -> position/order refresh -> backtest review.
- [x] QMT adapter remains config-gated and never auto-submits live orders by default.
- [x] Add broker account status to header and trade pages.
- [x] Add audit log for risk pass/reject, manual review, order submit, order cancel.
- [x] Run browser UAT for all routes in `prototype-page-map.md`.
- [x] Record evidence in `docs/reviews/full-platform-new-ui-uat-2026-06-28.md`.

**Verification:**

- [x] `cd frontend && npx vitest run`
- [x] `cd frontend && npx tsc -b --noEmit`
- [x] `cd frontend && npm run build`
- [x] `cd backend && .venv/bin/pytest tests/ -v`
- [x] Changed service tests under `services/*/tests`
- [x] API smoke through gateway
- [x] Browser UAT screenshots for route matrix

## Final Acceptance

The work is complete only when:

- every preview route in `prototype-page-map.md` is `Verified`;
- generic `NewUiModulePage` is removed from final page routes or retained only as an unreachable development fallback;
- frontend matches new prototype pages, not older UAT pages;
- BFF/page contracts are stable and typed;
- PostgreSQL-backed private objects are tenant/user/account isolated;
- paper trading works end-to-end from the UI;
- live/QMT path is gated and auditable;
- full verification commands pass or a true external dependency blocker is documented.
