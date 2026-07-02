# Market Decision Live Data Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace static demonstration data across the market-decision pages with real service data or explicit empty states.

**Architecture:** Keep existing page structure and API clients. Remove hardcoded market examples from page render paths; where a backend field is missing, display "暂无实时数据" instead of fabricated values. Existing live services remain the source of truth.

**Tech Stack:** React 18, Vite, TypeScript, Ant Design, existing `signalApi`, `screenerApi`, `predictionApi`, `chainApi`, `marketApi`.

## Global Constraints

- 永远用中文回答用户。
- 不能通过作弊用模型欺骗用户。
- 行情决策页面只展示真实接口数据；接口失败或字段缺失时显示空态。
- 不改模型逻辑，不改交易逻辑。
- 保持前端可在 `http://127.0.0.1:3002` 使用。

---

### Task 1: 智能看板去静态化

**Files:**
- Modify: `frontend/src/pages/Dashboard.tsx`
- Test: `frontend/src/__tests__/Dashboard.test.tsx`

**Interfaces:**
- Consumes: `signalApi.getDashboardSummary()`, `signalApi.getScreeningDashboardSummary()`, `signalApi.getDashboardAuction()`.
- Produces: Dashboard UI that shows real metrics or empty states.

- [ ] Replace fake sentiment, sector, fund, limit, and signal trend fallback values with zeros or empty arrays.
- [ ] Remove static AI-generated wording; use data-derived status text.
- [ ] Show explicit empty state for missing fund flow, sector heat, and historical trend data.
- [ ] Run `bash tools/codex-lowio.sh fe-test Dashboard`.

### Task 2: 开盘决策去静态化

**Files:**
- Modify: `frontend/src/pages/OpenDecision.tsx`
- Test: `frontend/src/__tests__/OpenDecision.test.tsx`

**Interfaces:**
- Consumes: `signalApi.getDashboardAuction()`, `signalApi.getLive('intra')`, trade service state.
- Produces: Open-decision UI without overnight-news or candidate demo rows.

- [ ] Remove hardcoded overnight news rows.
- [ ] Ensure empty auction, signal, candidate, order, and position sections show "暂无实时数据".
- [ ] Run `bash tools/codex-lowio.sh fe-test OpenDecision`.

### Task 3: Remaining market-decision pages

**Files:**
- Modify if needed: `frontend/src/pages/Screener.tsx`, `frontend/src/pages/SupplyChainBom.tsx`, `frontend/src/pages/Predictions.tsx`, `frontend/src/pages/Signals.tsx`
- Test: relevant page tests.

**Interfaces:**
- Consumes: existing service APIs only.
- Produces: no demo stock rows or fake realtime labels.

- [ ] Confirm pages do not render hardcoded stock lists as live data.
- [ ] Replace any remaining fallback demo output with empty states.
- [ ] Run focused frontend tests and typecheck.

### Task 4: Runtime verification

**Files:**
- No code files unless a defect is found.

**Interfaces:**
- Consumes: running frontend and local services.
- Produces: verified page behavior.

- [ ] Run `bash tools/codex-lowio.sh fe-typecheck`.
- [ ] Run focused tests for changed pages.
- [ ] Keep frontend running on port `3002`.
- [ ] Verify the screener run endpoint still returns live results for today.
