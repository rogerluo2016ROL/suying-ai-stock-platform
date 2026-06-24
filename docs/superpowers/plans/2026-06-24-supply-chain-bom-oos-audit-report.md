# Supply Chain BOM OOS Audit Report Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make BOM V5 OOS validation produce reproducible audit artifacts before the larger no-future universe rebuild.

**Architecture:** Add a pure report utility module under `kronos_factors.backtest`, then wire `tools/bom_oos_ic.py` to emit JSON and per-cutoff CSV files. The report explicitly records the current fixed-current-mapping universe mode and bias warnings so later cutoff-rebuilt universe work has a clear contract to replace.

**Tech Stack:** Python 3.10+, pytest, pandas.

## Global Constraints

- Do not require Tushare or PostgreSQL to test report-building helpers.
- Do not change OOS scoring math in this task.
- Preserve existing console output from `tools/bom_oos_ic.py`.
- Emit machine-readable artifacts under `outputs/bom_oos_reports/` by default.

---

### Task 1: Add Pure Audit Report Utilities

**Files:**
- Create: `packages/kronos-factors/kronos_factors/backtest/bom_oos_report.py`
- Create: `packages/kronos-factors/tests/test_bom_oos_report.py`

**Interfaces:**
- Produces: `hash_file(path: str | Path) -> str`
- Produces: `build_oos_audit_report(...) -> dict`
- Produces: `write_oos_audit_artifacts(report: dict, out_dir: str | Path) -> dict[str, str]`

- [ ] **Step 1:** Write failing tests for hash capture, fixed-universe warnings, and JSON/CSV artifact output.
- [ ] **Step 2:** Implement report helpers.
- [ ] **Step 3:** Run report tests.

### Task 2: Wire BOM OOS Script

**Files:**
- Modify: `tools/bom_oos_ic.py`

**Interfaces:**
- Consumes: `build_oos_audit_report`, `write_oos_audit_artifacts`
- Produces: JSON report and per-cutoff CSV when the script runs.

- [ ] **Step 1:** Add report construction after `all_results` is complete.
- [ ] **Step 2:** Include cache CSV hashes, git commit, universe mode, horizons, train/test ranges, and per-cutoff rows.
- [ ] **Step 3:** Print artifact paths without changing existing result lines.

### Task 3: Verification

**Files:**
- No new source files.

**Interfaces:**
- Consumes: package tests and script syntax.

- [ ] **Step 1:** Run `pytest tests/test_bom_oos_report.py tests/test_supply_chain_bom_v4.py -v`.
- [ ] **Step 2:** Run `python3 -m py_compile tools/bom_oos_ic.py packages/kronos-factors/kronos_factors/backtest/bom_oos_report.py`.
- [ ] **Step 3:** Inspect diff and report outstanding risk.
