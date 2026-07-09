# Industry Chain Evidence Model Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade the `complex_tech` industry-chain template into a layer-level evidence model with structured metrics, CAPEX evidence, physical metrics, evidence-chain traceability, expectation-gap placeholders, trigger-signal placeholders, and top-level macro context.

**Architecture:** Keep the existing 8-layer `complex_tech` tree and legacy `tracking_metrics`. Add deterministic layer-level evidence objects in `chain_deconstruct.py`, expose them through the existing `/api/v1/screener/chain/deconstruct` endpoint, and extend the existing React workbench card without creating a separate page.

**Tech Stack:** FastAPI, pytest, React 18, TypeScript, Ant Design, local JSON config packaged by `kronos-factors`.

## Global Constraints

- Do not replace the existing L1-L8 BOM hierarchy.
- Do not add a database migration.
- Do not add an LLM dependency.
- Preserve existing `/api/v1/screener/chain/deconstruct` behavior when `template` is omitted.
- Preserve legacy `tracking_metrics` in template responses.
- Unknown macro data must be returned as `unknown`; do not invent inflation or policy states.
- Use existing expectation-gap formula metadata: `actual_progress - market_expectation + evidence_delta*0.35 - risk_penalty*0.45`.
- Use low-I/O verification commands from `tools/codex-lowio.sh`.

---

### Task 1: Product And Data Contract Docs

**Files:**
- Create: `docs/prd/industry-chain-evidence-model-2026-07-08.md`
- Create: `docs/data-dictionary/industry-chain-evidence-schema.md`

**Interfaces:**
- Produces: field contract for `metrics`, `capex_evidence`, `physical_metrics`, `evidence_chain`, `expectation_gap`, `trigger_signal`, and `macro_context`.

- [x] **Step 1: Write PRD**

Capture goals, non-goals, ACs, and constraints for layer-level evidence integration.

- [x] **Step 2: Write data dictionary**

Define each evidence object and required source/evidence fields.

### Task 2: Backend Contract Tests

**Files:**
- Modify: `services/screener-service/tests/test_chain_api.py`

**Interfaces:**
- Consumes: `GET /api/v1/screener/chain/deconstruct?template=complex_tech`
- Produces: failing tests for the new contract.

- [x] **Step 1: Write failing tests**

Add:
- `test_complex_tech_template_returns_structured_metrics`
- `test_complex_tech_layers_include_evidence_chain_gap_and_triggers`
- `test_complex_tech_macro_context_is_top_level_unknown_when_unverified`

- [x] **Step 2: Verify RED**

Run:

```bash
bash tools/codex-lowio.sh py services/screener-service/tests/test_chain_api.py::TestChainDeconstruct::test_complex_tech_template_returns_structured_metrics services/screener-service/tests/test_chain_api.py::TestChainDeconstruct::test_complex_tech_layers_include_evidence_chain_gap_and_triggers services/screener-service/tests/test_chain_api.py::TestChainDeconstruct::test_complex_tech_macro_context_is_top_level_unknown_when_unverified -q
```

Expected: fail because `metrics`, `capex_evidence`, and `macro_context` are missing.

### Task 3: Backend Evidence Model

**Files:**
- Modify: `packages/kronos-factors/kronos_factors/engine/chain_deconstruct.py`

**Interfaces:**
- Produces: enriched template tree children and top-level macro context.

- [x] **Step 1: Add deterministic defaults**

Add default layer metrics, CAPEX evidence samples, physical metrics, and five-region unknown macro context.

- [x] **Step 2: Build evidence-chain adapters**

Convert CAPEX and physical metrics into unified `evidence_chain` objects with `evidence_type`, `impact_direction`, and `confidence`.

- [x] **Step 3: Preserve expectation-gap traceability**

Return `expectation_gap.evidence_ids` and existing formula metadata without calculating unverified values.

- [x] **Step 4: Verify GREEN**

Run the three new tests and expect pass.

### Task 4: Frontend Evidence Display

**Files:**
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/pages/supply-chain-bom/SupplyChainResearchWorkbench.tsx`

**Interfaces:**
- Consumes: enriched `ChainDeconstructResponse`.
- Produces: display of macro context, metric groups, CAPEX evidence, physical metrics, evidence-chain summary, expectation-gap and trigger traceability.

- [x] **Step 1: Extend TypeScript response types**

Add optional fields for `macro_context`, `metrics`, `capex_evidence`, `physical_metrics`, `evidence_chain`, `expectation_gap`, and `trigger_signal`.

- [x] **Step 2: Render evidence fields**

Extend the existing complex-tech template card with compact tags and source/evidence metadata.

- [x] **Step 3: Verify frontend typecheck**

Run:

```bash
bash tools/codex-lowio.sh fe-typecheck
```

### Task 5: Final Verification

**Files:**
- All touched files.

**Interfaces:**
- Produces: final verification evidence.

- [x] **Step 1: Run backend focused tests**

```bash
bash tools/codex-lowio.sh py services/screener-service/tests/test_chain_api.py::TestChainDeconstruct -q
```

- [x] **Step 2: Run frontend typecheck**

```bash
bash tools/codex-lowio.sh fe-typecheck
```

- [x] **Step 3: Run diff whitespace check**

```bash
git diff --check -- docs/prd/industry-chain-evidence-model-2026-07-08.md docs/data-dictionary/industry-chain-evidence-schema.md docs/superpowers/plans/2026-07-08-industry-chain-evidence-model.md packages/kronos-factors/kronos_factors/engine/chain_deconstruct.py services/screener-service/tests/test_chain_api.py frontend/src/api/client.ts frontend/src/pages/supply-chain-bom/SupplyChainResearchWorkbench.tsx
```

- [x] **Step 4: Report actual verification status**

List passed commands and any residual risks.
