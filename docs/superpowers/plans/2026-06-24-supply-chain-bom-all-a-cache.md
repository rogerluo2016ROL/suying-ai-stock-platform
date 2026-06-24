# Supply Chain BOM All-A Cache Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend BOM OOS cache generation from the fixed 36-company PG mapping to a configurable universe, including all listed A-share stocks.

**Architecture:** Move cache-fetching logic into a pure-ish package helper with injectable Tushare and PG boundaries, then keep `tools/bom_oos_cache.py` as a small CLI wrapper. The OOS scorer continues reading the same CSV schema, so the cutoff-rebuilt universe mode works without changes once full-market cache files exist.

**Tech Stack:** Python 3.11+, pandas, Tushare SDK, pytest.

## Global Constraints

- Do not read `.env*`; require `TUSHARE_TOKEN` from process environment at runtime.
- Keep existing CSV names: `fina_indicator.csv`, `forecast.csv`, `irm_qa.csv`, `research_report.csv`, `fina_mainbz.csv`.
- Preserve `bom36` as the default universe for backward-compatible reproducibility.
- Use TDD for helper behavior before modifying production code.

---

### Task 1: Extract Cache Helpers

**Files:**
- Create: `packages/kronos-factors/kronos_factors/backtest/bom_oos_cache.py`
- Create: `packages/kronos-factors/tests/test_bom_oos_cache.py`
- Modify: `tools/bom_oos_cache.py`

**Interfaces:**
- Produces: `to_ts_code(code6: str) -> str`
- Produces: `fetch_all_a_codes(pro) -> list[tuple[str, str]]`
- Produces: `fetch_company_frames(pro, code6: str, ts_code: str, start: str, end: str) -> dict[str, pd.DataFrame]`

- [x] **Step 1: Write failing tests for code conversion and all-A universe fetch.**
- [x] **Step 2: Run `pytest tests/test_bom_oos_cache.py -v` and confirm missing module failure.**
- [x] **Step 3: Implement minimal helper module.**
- [x] **Step 4: Run `pytest tests/test_bom_oos_cache.py -v` and confirm pass.**

### Task 2: Add CLI Universe Selection

**Files:**
- Modify: `tools/bom_oos_cache.py`
- Test: `packages/kronos-factors/tests/test_bom_oos_cache.py`

**Interfaces:**
- Produces CLI args: `--universe bom36|all_a`, `--start`, `--end`, `--sleep-seconds`, `--limit`, `--out-dir`, `--overwrite`.

- [x] **Step 1: Write failing tests for `parse_args` defaults and all-A option.**
- [x] **Step 2: Implement the CLI wrapper using package helpers.**
- [x] **Step 3: Run helper tests and py_compile.**
- [x] **Step 4: Add output-directory and overwrite protection for safe all-A smoke runs.**

### Task 3: Optional Full-Run Verification

**Files:**
- Generated: `outputs/bom_oos_cache/*.csv`

- [ ] **Step 1: If `TUSHARE_TOKEN` is present and user approves the API budget, run a small smoke subset first.**
- [ ] **Step 2: Run all-A cache outside sandbox only if required by network access.**
- [ ] **Step 3: Re-run `tools/bom_oos_ic.py --universe-mode cutoff_rebuilt_cache` against the expanded cache.**

### Task 4: OOS Cache Directory Selection

**Files:**
- Modify: `tools/bom_oos_ic.py`
- Modify: `packages/kronos-factors/kronos_factors/backtest/bom_oos_cache.py`
- Test: `packages/kronos-factors/tests/test_bom_oos_cache.py`

**Interfaces:**
- Produces OOS CLI arg: `--cache-dir <path>`.
- Produces helper: `load_cache_frames(cache_dir: str | Path) -> dict[str, pd.DataFrame]`.
- Produces helper: `cache_input_paths(cache_dir: str | Path) -> dict[str, Path]`.

- [x] **Step 1: Add failing tests for loading required cache CSVs and normalizing `code6`.**
- [x] **Step 2: Implement cache input path discovery and cache frame loading.**
- [x] **Step 3: Wire `tools/bom_oos_ic.py` to load cache at runtime from `--cache-dir`.**
- [x] **Step 4: Verify missing cache fails before PG access, and default cache OOS still runs.**

### Task 5: Resumable All-A Cache Runs

**Files:**
- Modify: `tools/bom_oos_cache.py`
- Modify: `packages/kronos-factors/kronos_factors/backtest/bom_oos_cache.py`
- Test: `packages/kronos-factors/tests/test_bom_oos_cache.py`

**Interfaces:**
- Produces CLI arg: `--resume`.
- Produces manifest file: `manifest.csv`.
- Produces helper: `append_cache_frames(output_paths: dict[str, Path], frames: dict[str, pd.DataFrame]) -> None`.
- Produces helper: `load_processed_codes(manifest_path: str | Path) -> set[str]`.
- Produces helper: `mark_code_processed(manifest_path: str | Path, *, code6: str, ts_code: str, frame_counts: dict[str, int], status: str = "ok") -> None`.

- [x] **Step 1: Add failing tests for append-only CSV writing and processed-code manifest.**
- [x] **Step 2: Implement append helpers and manifest helpers.**
- [x] **Step 3: Wire `tools/bom_oos_cache.py` to append per company instead of holding all frames in memory.**
- [x] **Step 4: Wire `--resume` to skip completed codes from `manifest.csv`.**
- [x] **Step 5: Verify helper tests, script compilation, and CLI help.**
