# Supply Chain BOM Workbench Rebuild Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the supply-chain BOM page from a passive industry directory into an actionable stock-selection workbench with BOM drill-down, candidate companies, selection reasons, scoring logic, commercialization stage, and policy/business/performance resonance.

**Architecture:** Keep the existing screener-service and React page. Add one backend workbench payload that joins the existing supply-chain picks with BOM context, then render it as a three-zone frontend: BOM tree, industry graph/theme matrix, and candidate company pool with detail drawer.

**Tech Stack:** FastAPI, kronos-factors, React 18, TypeScript, Ant Design, ECharts, pytest, vitest.

## Global Constraints

- Do not trigger real trading or order placement.
- Use existing screener-service API patterns under `/api/v1/screener/supply-chain`.
- Keep UI focused on research workflow, not marketing content.
- Preserve current `/themes`, `/bom`, `/node/{node_id}`, `/company/{code}`, and `/extract` contracts.
- Use TDD: add failing tests before production changes.

---

### Task 1: Backend Workbench Payload

**Files:**
- Modify: `services/screener-service/app/routers/screener.py`
- Test: `services/screener-service/tests/test_supply_chain_bom_api.py`

**Interfaces:**
- Produces: `GET /api/v1/screener/supply-chain/workbench?top_n=30`
- Produces: enriched `GET /api/v1/screener/supply-chain/company/{code}`

- [ ] Add failing API tests for candidate pool, selection reason, scoring dimensions, commercialization cycle, and resonance fields.
- [ ] Implement candidate enrichment from `run?mode=supply_chain`.
- [ ] Keep response deterministic when live data has sparse evidence.
- [ ] Run screener-service supply-chain tests.

### Task 2: Frontend Workbench

**Files:**
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/pages/SupplyChainBom.tsx`
- Test: `frontend/src/__tests__/SupplyChainBom.test.tsx`

**Interfaces:**
- Consumes: `screenerApi.getSupplyChainWorkbench(topN)`
- Renders: BOM tree, company pool, selection reason, score dimensions, commercialization stage, resonance summary.

- [ ] Add failing frontend tests that require visible candidate companies and scoring/reason fields.
- [ ] Implement API client method.
- [ ] Rebuild page layout around candidate pool and company detail.
- [ ] Run frontend tests, type check, and build.

### Task 3: Browser UAT

**Files:**
- Evidence only under `docs/qa/evidence/` if screenshots are captured.

- [ ] Open `http://127.0.0.1:3002/supply-chain-bom`.
- [ ] Verify company pool is visible without clicking hidden buttons.
- [ ] Verify a company drawer shows products/materials, score dimensions, commercialization stage, and resonance.
- [ ] Report remaining gaps honestly.
