# Industry Chain Template Enhancement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add configurable industry-link templates to the existing supply-chain deconstruct model, starting with `complex_tech`.

**Architecture:** Keep the current L1-L8 BOM hierarchy as the universal framework. Add template configuration and a template response path inside the existing deconstruct API. Extend the current supply-chain workbench with a template selector instead of creating a separate page.

**Tech Stack:** FastAPI, pytest, React 18, TypeScript, Ant Design, local JSON config packaged by `kronos-factors`.

## Global Constraints

- Do not replace the existing L1-L8 BOM hierarchy.
- Do not add a database migration in the first version.
- Do not add an LLM dependency.
- Preserve existing `/api/v1/screener/chain/deconstruct` behavior when `template` is omitted.
- Use low-I/O verification commands from `tools/codex-lowio.sh`.

---

### Task 1: Backend Template Contract

**Files:**
- Create: `packages/kronos-factors/configs/industry_chain_templates.json`
- Modify: `packages/kronos-factors/kronos_factors/engine/chain_deconstruct.py`
- Modify: `services/screener-service/app/routers/screener.py`
- Test: `services/screener-service/tests/test_chain_api.py`

**Interfaces:**
- Consumes: `GET /api/v1/screener/chain/deconstruct`
- Produces: optional `template=complex_tech`, response fields `template`, `tree.children[].tracking_metrics`

- [x] **Step 1: Write failing backend test**

Add `TestChainDeconstruct.test_complex_tech_template_returns_eight_layer_chain_logic`.

- [x] **Step 2: Verify RED**

Run:

```bash
bash tools/codex-lowio.sh py services/screener-service/tests/test_chain_api.py::TestChainDeconstruct::test_complex_tech_template_returns_eight_layer_chain_logic -q
```

Expected: fail because response still returns `view = upstream_downstream`.

- [x] **Step 3: Implement template config and API path**

Add `industry_chain_templates.json`, template loader, template tree builder, and route parameter passthrough.

- [x] **Step 4: Verify GREEN**

Run the same command and expect pass.

### Task 2: Frontend Template Switch

**Files:**
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/pages/supply-chain-bom/SupplyChainResearchWorkbench.tsx`
- Modify or create focused child component under `frontend/src/pages/supply-chain-bom/`

**Interfaces:**
- Consumes: `api.deconstructChain({ theme_id, method, template })`
- Produces: UI selector for `通用层级` and `复杂科技`

- [x] **Step 1: Extend TypeScript API type**

Add `template?: string` to `deconstructChain` params and response fields for `template` and template tree children.

- [x] **Step 2: Add UI state and selector**

Add a compact Ant Design segmented control in the existing workbench.

- [x] **Step 3: Render template chain cards**

Display 8 layer cards with definition, segments, companies, and tracking metrics.

- [x] **Step 4: Verify frontend typecheck**

Run:

```bash
bash tools/codex-lowio.sh fe-typecheck
```

### Task 3: Final Verification

**Files:**
- All touched files above.

**Interfaces:**
- Consumes: backend and frontend changed contracts.
- Produces: verifiable AC checklist.

- [x] **Step 1: Run focused backend tests**

```bash
bash tools/codex-lowio.sh py services/screener-service/tests/test_chain_api.py::TestChainDeconstruct -q
```

- [x] **Step 2: Run frontend typecheck**

```bash
bash tools/codex-lowio.sh fe-typecheck
```

- [x] **Step 3: Inspect git diff**

```bash
git diff -- docs/prd/industry-chain-template-enhancement-2026-07-08.md docs/superpowers/plans/2026-07-08-industry-chain-template-enhancement.md packages/kronos-factors/configs/industry_chain_templates.json packages/kronos-factors/kronos_factors/engine/chain_deconstruct.py services/screener-service/app/routers/screener.py services/screener-service/tests/test_chain_api.py frontend/src/api/client.ts frontend/src/pages/supply-chain-bom
```

- [x] **Step 4: Report actual verification status**

List passed commands and any residual risks.
