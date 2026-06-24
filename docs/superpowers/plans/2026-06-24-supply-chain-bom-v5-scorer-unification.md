# Supply Chain BOM V5 Scorer Unification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Promote the embodied-AI BOM V5 scoring rules from one-off tools into a reusable production module and align API metadata with that scorer.

**Architecture:** Add a pure `supply_chain_bom_v5` scorer module under `packages/kronos-factors`, then make the existing V4 compatibility wrapper and screener workbench metadata read scorer constants from it. Keep persistence and OOS scripts able to import the same functions in later phases without changing their command-line behavior today.

**Tech Stack:** Python 3.10+, pytest, FastAPI screener-service.

## Global Constraints

- Do not touch real-trading code.
- Do not introduce new runtime dependencies.
- Preserve existing API fields and labels.
- Use TDD: write failing package tests before scorer implementation.
- Keep this phase focused on scorer unification; full all-market OOS rebuild is a follow-up.

---

### Task 1: Add Reusable V5 Scorer

**Files:**
- Create: `packages/kronos-factors/kronos_factors/engine/supply_chain_bom_v5.py`
- Modify: `packages/kronos-factors/tests/test_supply_chain_bom_v4.py`

**Interfaces:**
- Produces: `DIM_WEIGHTS: dict[str, float]`
- Produces: `derive_rating(total_score: float) -> str`
- Produces: `derive_trade_signal(total_score: float, dimension_scores: dict[str, float]) -> str`
- Produces: `score_bom_ratio(main_pct: float) -> float`
- Produces: `score_chokepoint_hits(keyword_counts: dict[str, int]) -> float`
- Produces: `score_growth(q_sales_yoy: float | None, netprofit_yoy: float | None, forecast_max: float | None = None, forecast_type: str | None = None) -> tuple[float, str]`
- Produces: `score_profit(gross_margin: float | None) -> tuple[float, str]`
- Produces: `score_company_v5(base_pick: dict, evidence: list[dict] | None = None) -> dict`

- [ ] **Step 1: Write failing tests** for V5 dimensions, diversity weighting, financial mapping, and trade signal.
- [ ] **Step 2: Run package test and verify it fails** because `supply_chain_bom_v5` does not exist.
- [ ] **Step 3: Implement the pure scorer module** with no DB or Tushare calls.
- [ ] **Step 4: Run package tests and verify they pass**.

### Task 2: Align Existing Compatibility Layer And API Metadata

**Files:**
- Modify: `packages/kronos-factors/kronos_factors/engine/supply_chain_bom.py`
- Modify: `services/screener-service/app/routers/screener.py`
- Modify: `services/screener-service/tests/test_supply_chain_bom_api.py`

**Interfaces:**
- Consumes: `DIM_WEIGHTS`, `derive_rating`, `derive_trade_signal`, `score_company_v5`
- Produces: API model payload whose score dimension weights match the scorer.

- [ ] **Step 1: Add failing screener API test** asserting model metadata matches V5 weights.
- [ ] **Step 2: Run screener test and verify it fails** on mismatched metadata.
- [ ] **Step 3: Re-export V5 scorer from `supply_chain_bom.py` and update `_supply_chain_model_payload`** to read `DIM_WEIGHTS`.
- [ ] **Step 4: Run package and screener tests**.

### Task 3: Verification

**Files:**
- No new source files.

**Interfaces:**
- Consumes: package and screener tests from Tasks 1-2.

- [ ] **Step 1: Run focused package tests.**
- [ ] **Step 2: Run focused screener-service tests.**
- [ ] **Step 3: Inspect git diff to confirm unrelated user changes are untouched.**
