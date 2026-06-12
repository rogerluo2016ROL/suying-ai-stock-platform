# Code Review — 数据管道重构 (commit 520aea6)

- **Reviewer**: product-lead (via /code-review skill, medium effort)
- **Date**: 2026-06-12
- **Scope**: 17 files, +1358/-101 lines
- **PRD**: docs/prd/data-pipeline-refactor-2026-06-12.md
- **ADR**: docs/adr/006-data-pipeline.md
- **SIT Evidence**: progress/backend-dev.md (audited inline)

## Verdict: Approve with Changes (3 findings requiring fixes)

## AC Verification Matrix

| AC | Priority | Code Review Verdict | Notes |
|---|---|---|---|
| AC-1 | P0 | ✅ PASS | `write_daily_kline` calls `_pg_write` with ON CONFLICT DO NOTHING |
| AC-2 | P0 | ✅ PASS | PG writes wrapped in try/except, SQLite writes in separate try/except |
| AC-3 | P0 | ✅ PASS | `pg_sync` job removed, `sync_daily_to_pg` import removed |
| AC-4 | P1 | ✅ PASS | `sync_stock_list()` writes to PG stocks via ON CONFLICT DO UPDATE |
| AC-5 | P1 | ✅ PASS | `refresh_materialized_views()` returns `{view: {status, rows}}` dict |
| AC-6 | P1 | ✅ PASS | `write_stk_mins` uses `_pg_write` with retry + volume gate |
| AC-7 | P2 | ✅ PASS | `sync_daily_to_pg` fully removed (grep -rn confirms 0 references) |
| AC-8 | P2 | ⚠️ PASS with concerns | `pg_write_status` derived via regex string-parsing (see finding #3) |

## ADR-006 Compliance

| Decision | Status | Notes |
|---|---|---|
| 决策 1: PG-first 写入顺序 | ⚠️ NON-COMPLIANT | `sync_stock_list()` writes SQLite before PG (see finding #1) |
| 决策 2: ON CONFLICT DO UPDATE | ⚠️ PARTIAL | `_pg_write` uses DO NOTHING, stocks write uses DO UPDATE (see finding #2) |
| 决策 3: 消除 subprocess 桥 | ✅ PASS | `sync_daily_to_pg` removed, direct PG writes in all sync functions |
| 决策 4: stocks 同步频率 | ✅ PASS | Saturday 02:00 full + weekday 08:00 incremental |
| 决策 5: 物化视图 | ✅ PASS | 4 views including new mv_daily_composite_ranking |
| 决策 6: 错误处理 | ✅ PASS | 3x exponential backoff retry in `_pg_write` + volume gate |

## SIT Audit

Reviewed progress/backend-dev.md (3 batches):

- **Batch 1** (tasks #1-5): 7 PG write functions tested, idempotency verified (re-write → 0 rows). Syntax check: 5/5 Python files pass.
- **Batch 2** (task #6): `refresh_materialized_views` returns per-view dict, `sync_daily_to_pg` confirmed removed.
- **Batch 3** (task #7): `rate_limiter` sliding window verified (5 calls → 395 remaining), sleep-on-limit behavior confirmed.

**SIT Audit verdict**: ✅ PASS — AC coverage is comprehensive, all integration paths tested. Minor gap: `sync_stocks_incremental` not individually SIT-tested (covered by `sync_stock_list` being the same code path with smaller input).

## Findings

### Finding #1 — Write order violation in sync_stock_list (ADR-006 决策 1)

- **Severity**: Medium
- **File**: `services/data-service/app/sync/stocks.py`, lines 56-91
- **Summary**: `sync_stock_list()` writes SQLite (line 56-68) before PG (line 70-91), violating ADR-006 decision 1 requiring PG-first write order. If PG write succeeds but SQLite write fails, PG has data but function returns `sqlite_written: 0` — data integrity is fine but the reported metrics are misleading.
- **Fix**: Swap the two write blocks — move PG write block (line 70-91) before SQLite write block (line 56-68). `sync_stocks_incremental()` (line 132-166) already follows PG-first order correctly.

### Finding #2 — ON CONFLICT strategy inconsistency (ADR-006 决策 2)

- **Severity**: Low
- **File**: `services/data-service/app/sync/pg_writer.py` line 193 vs `services/data-service/app/sync/stocks.py` line 80
- **Summary**: ADR-006 decision 2 specifies `INSERT ... ON CONFLICT DO UPDATE` (upsert) as the standard strategy. The generic `_pg_write()` function uses `ON CONFLICT DO NOTHING` instead. The stocks sync functions use `DO UPDATE` correctly. The inconsistency means re-running a post-market sync for the same date will silently drop data (DO NOTHING) rather than update it. While DO NOTHING is valid for idempotency of immutable daily data, it differs from the ADR decision.
- **Resolution options**: (a) Accept DO NOTHING for daily_kline/moneyflow/etc. (data for a given date never changes after Tushare publishes it) and update ADR-006 to note the exception; OR (b) Change `_pg_write` to support configurable conflict strategy with a parameter.

### Finding #3 — Fragile pg_write_status derivation via string parsing

- **Severity**: Low
- **File**: `services/data-service/app/routers/data.py`, lines 48-71
- **Summary**: `pg_write_status` is derived by regex-parsing the string representation of job results: `re.findall(r"'pg_written':\s*(\d+)", result_str)`. This is fragile — if the result dict contains nested dicts, or if Python changes repr format, or if the result contains JSON instead of Python repr, the regex silently fails with 0 matches. Additionally, a successful job with 0 PG writes (e.g., ths_daily on a day with no data) is incorrectly classified as "partial".
- **Fix**: Have sync functions return a structured `pg_write_status` field directly (e.g., `return {"pg_write_status": "ok", "pg_written": N, ...}`), then extract it in `_run_job()` or `data_status()` without string parsing.

### Finding #4 — rate_limiter blocks all threads during sleep

- **Severity**: Low (only impacts throughput under high concurrency)
- **File**: `services/data-service/app/sync/rate_limiter.py`, lines 22-34
- **Summary**: `rate_limit()` calls `time.sleep(sleep_for)` while holding `threading.Lock`. When the rate limit is hit, the sleeping thread holds the lock, blocking ALL other ThreadPoolExecutor workers from checking or updating the rate limit state. This effectively serializes all Tushare API calls during the sleep period (~60s) instead of just the calling thread. In practice, the impact is limited because: (a) the current ThreadPoolExecutor size is 2-8 workers, (b) the rate limit of 400/min is rarely hit in normal operation.
- **Fix**: Release the lock before sleeping, re-acquire after: move `time.sleep(sleep_for)` and `_call_times = []` outside the `with _lock:` block.

### Finding #5 — Unused SQLite connection in sync_post_market_core

- **Severity**: Low (waste, not bug)
- **File**: `services/data-service/app/sync/tushare.py`, lines 128-161
- **Summary**: `db = sqlite3.connect(DB_PATH)` is opened at line 128 and closed at line 161 without being used for any SQLite write. The `_sync_one` closures were refactored to only collect data (no longer write to SQLite), and the actual SQLite fallback writes now use separate connections (`mf_db`, `sl_db` at lines 182-195). This is a minor resource waste — one unnecessary connection opened per post_market_core execution.
- **Fix**: Remove lines 128 and 161 (`db = sqlite3.connect(DB_PATH)` and `db.close()`), or move the SQLite fallback writes to use this connection instead of creating new ones.

### Finding #6 — Code duplication between sync_stock_list and sync_stocks_incremental

- **Severity**: Low (maintenance)
- **File**: `services/data-service/app/sync/stocks.py`, lines 20-101 vs 106-168
- **Summary**: Both functions contain ~30 lines of identical logic for: (a) building rows from stock_basic DataFrame, (b) formatting list_date, (c) detecting ST stocks, (d) row-by-row PG write with ON CONFLICT DO UPDATE. The only difference is the Tushare API call and the return value shape. Extracting a shared `_write_stock_rows(rows)` helper would eliminate the duplication and ensure both paths use the same write strategy.
- **Fix**: Extract `_write_stock_rows(rows: list[tuple]) -> dict` that handles both PG and SQLite writes, call it from both functions.

## Review Summary

| Category | Count |
|---|---|
| ✅ PASS | 5 AC + 3 ADR decisions |
| ⚠️ PASS with concerns | 1 AC (AC-8: fragile string parsing) |
| ❌ Needs fix | 2 findings (#1 write order, #3 string parsing) |
| 💡 Suggestion | 4 findings (#2 strategy inconsistency, #4 lock-sleep, #5 unused connection, #6 code duplication) |

**Overall verdict**: ⚠️ **Approve with Changes** — Finding #1 (write order violation in `sync_stock_list`) and finding #3 (fragile pg_write_status derivation) should be fixed before E2E. The remaining 4 suggestions can be addressed in a follow-up PR or noted as known technical debt.

## Changelog

- 2026-06-12: Initial review of commit 520aea6 (17 files, +1358/-101 lines)
