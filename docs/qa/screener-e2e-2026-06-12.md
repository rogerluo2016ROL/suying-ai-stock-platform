---
tester: qa-engineer
model: deepseek-v4-pro
stage: e2e
report_verdict: "❌ Block — PG connection pool leak (DEF-SCR-1 fix incomplete)"
ac_total: 11
ac_pass: 3
ac_fail: 0
ac_blocked: 8
p0_total: 6
p0_pass: 2
p0_fail: 0
p0_blocked: 4
p0_pass2_total: 2
p0_pass2_ok: 2
ac_total: 2
ac_pass: 0
ac_fail: 1
ac_conditional: 0
ac_blocked: 1
p0_pass2_total: 1
p0_pass2_ok: 0
feature: screener
date: 2026-06-12
---

# QA Report — Screener Service — E2E

- **Date**: 2026-06-12
- **Stage**: E2E
- **Tester**: qa-engineer (deepseek-v4-pro)
- **Branch**: `feature/suying-ai-stock-platform` (a458b79)
- **Environment**: local docker-compose (screener:8001, PostgreSQL:6432)
- **PRD**: [docs/prd/repair-sprint-wave2-2026-06-12.md](../prd/repair-sprint-wave2-2026-06-12.md)
- **Code review (含 SIT Audit)**: N/A (Wave 2 Line B, code review completed upstream)

## Summary

- Total AC: 2 (1 P0 + 1 P1)
- Passed: 0
- Failed: 1 (AC-303.1)
- Blocked: 1 (AC-303.2 — blocked by AC-303.1 failure)
- **Verdict**: Block — Core screening endpoints hang on PG connection; service cannot fulfill its primary function

## Pre-conditions Checked

- [x] SIT 证据由 dev 自跑 (code review passed upstream)
- [x] PRD AC 可访问 (docs/prd/repair-sprint-wave2-2026-06-12.md)
- [x] PostgreSQL docker-postgres-1 running on 6432
- [x] screener-service started on port 8001 (health returns 200)

## AC Results

### AC-303.1 (P0): screener-service 全部端点 curl E2E 通过 (>= 10 scenarios)

- **Priority**: P0
- **Setup**: screener-service running on port 8001; PostgreSQL on 6432; KRONOS_PG_URL set
- **Action**: Execute curl against all screener endpoints covering 10+ scenarios

- **Expected**: All endpoints return 2xx responses with valid JSON data; screening modes return ranked picks with scores

- **Actual (run 1)**:

  **Scenario 1 — Health Check**: PASS
  ```
  HTTP/1.1 200 OK
  {"status":"healthy","service":"screener-service","version":"0.1.0"}
  ```

  **Scenario 2 — List Modes**: PASS
  ```
  HTTP/1.1 200 OK
  10 modes: leader_auction, leader_scalp, leader_intraday, short, long,
  all, chokepoint, cb_floor, cb_intraday, cb_auction
  ```

  **Scenario 3 — Invalid Mode Error Handling**: PASS
  ```
  HTTP/1.1 400 Bad Request
  {"detail":"Unknown mode 'invalid_xyz'. Available: ['leader_auction', ...]"}
  ```

  **Scenario 4 — Run Screening (mode=all, top_n=5)**: FAIL
  ```
  HTTP/1.1 000 — timeout after 30s, curl exit code 28
  No response body
  ```

  **Scenario 5 — Run Screening (mode=short)**: FAIL
  ```
  HTTP/1.1 000 — timeout after 30s
  ```

  **Scenario 6 — Run Screening (mode=long)**: FAIL
  ```
  HTTP/1.1 000 — timeout after 30s
  ```

  **Scenario 7 — Run Screening (mode=chokepoint)**: FAIL
  ```
  HTTP/1.1 000 — timeout after 30s
  ```

  **Scenario 8 — Run Screening (mode=leader_scalp)**: FAIL
  ```
  HTTP/1.1 000 — timeout after 30s
  ```

  **Scenario 9 — Dashboard Summary**: FAIL
  ```
  HTTP/1.1 000 — timeout after 30s
  ```

  **Scenario 10 — Dashboard Picks**: FAIL
  ```
  HTTP/1.1 000 — timeout after 30s
  ```

  **Scenario 11 — Dashboard Report**: FAIL
  ```
  HTTP/1.1 000 — timeout after 30s
  ```

- **Actual (run 2)**: N/A — run 1 showed consistent timeouts across all 8 DB-dependent endpoints

- **Reliability**: `pass^1 = 3/11` (3 stateless endpoints pass, 8 DB-dependent endpoints hang)

- **Verdict**: Fail — Core screening and dashboard endpoints time out. Service logs show PG adapter injected successfully but all DB queries block. Root cause: PostgreSQL connection pool exhaustion or blocking query. 3/11 scenarios pass (stateless only).

### AC-303.2 (P1): UAT 报告提交，含 RBAC 角色测试

- **Priority**: P1
- **Setup**: Requires AC-303.1 to pass first
- **Action**: Execute RBAC role-based screening tests (admin/internal/external/user)
- **Expected**: Each role can access screening modes per RBAC policy
- **Actual**: Not executed — blocked by AC-303.1 failure
- **Verdict**: Blocked

## Defects Found

| ID | Severity | Title | Repro steps | Suspected file |
|---|---|---|---|---|
| DEF-SCR-1 | Critical | All DB-dependent screener endpoints hang indefinitely | 1. Start screener on 8001 with PG adapter 2. POST /api/v1/screener/run?mode=all 3. Request hangs until timeout | services/screener-service/app/routers/screener.py / app/main.py (PG adapter connection blocking) |

## Cost (this QA session)

- Tokens consumed: part of Wave 2 Line B batch (5 services)
- Estimated cost: part of batch
- 同 feature 累计: TBD

## Hand-off

❌ Block → SendMessage product-lead: screener-service core screening endpoints all hang. Only 3/11 E2E scenarios pass (stateless: health, modes, error handling). Critical defect DEF-SCR-1 in PG adapter connection blocking.

---

## Re-run 1 — 2026-06-12 15:00 (T-308: ThreadedConnectionPool fix)

**Trigger**: T-308 修复 DEF-SCR-1 (PG adapter 单连接 → ThreadedConnectionPool 2..10 + autocommit)
**Commit**: 7f110a7 (盘中选股快照 + 预测服务路由优化)

### Re-run Results

| # | Test | Result | Evidence |
|---|------|:---:|------|
| R1-1 | GET /modes | ✅ 200 | 10 modes returned |
| R1-2 | POST /run?mode=short&top_n=5 | ✅ 200 | 863 scored, 5 picks (绿的谐波/奥比中光/...), 54.5s |
| R1-3 | POST /run?mode=long&top_n=5 | ❌ TIMEOUT | 120s no response — PG pool exhausted |
| R1-4 | POST /run?mode=all&top_n=5 | ❌ EMPTY | Body empty — PG pool dead |
| R1-5 | POST /run?mode=chokepoint&top_n=5 | ❌ EMPTY | Body empty — PG pool dead |
| R1-6 | POST /run?mode=leader_scalp&top_n=5 | ❌ EMPTY | Body empty — PG pool dead |
| R1-7 | POST /run?mode=leader_auction&top_n=5 | ❌ EMPTY | Body empty — PG pool dead |
| R1-8 | POST /run?mode=cb_floor&top_n=5 | ❌ EMPTY | Body empty — PG pool dead |
| R1-9 | POST /run?top_n=5 (valid bounds) | ✅ 200 | short mode accepted top_n=5 (was >= 5 validation) |
| R1-10 | POST /run?top_n=3 (below min) | ✅ 422 | `Input should be >= 5` |

### Evidence

```
--- short mode (R1-2, PASS) ---
HTTP/1.1 200 OK
{"mode":"short","market_env":"未知","total_scored":863,"total_excluded":4423,
 "picks":[
   {"code":"688017","name":"绿的谐波","price":373.73,"score":20.3,"grade":"S",
    "entry_price":364.18,"rationale":"当前价373.73高于MA10入场点364.18..."},
   {"code":"688322","name":"奥比中光","price":133.06,"score":19.7,"grade":"S",...},
   {"code":"001896","name":"豫能控股","price":21.38,"score":19.6,"grade":"S",...},
   {"code":"300814","name":"中富电路","price":166.79,"score":19.5,"grade":"S",...},
   {"code":"600498","name":"烽火通信","price":65.05,"score":19.5,"grade":"S",...}],
 "factor_weights":{"short_term":0.3,"volume_factor":0.1,...},
 "elapsed":54.5}

--- long mode (R1-3, FAIL) ---
TIMEOUT after 120s — service accepts connection but never responds

--- all/chokepoint/leader_scalp/leader_auction/cb_floor (R1-4~8, FAIL) ---
ALL return empty body — PG connection pool exhausted after short query.
Service must be restarted to recover.
```

### Root Cause

**DEF-SCR-1 fix incomplete**: ThreadedConnectionPool(2..10) connections are NOT properly released after each request. The `short` mode query (54.5s, 863 stocks) exhausts all pool connections. No connection return to pool → subsequent requests hang. 100% reproducible on fresh restart.

### Re-run Verdict

**❌ Block** — PG pool leak confirmed. Service becomes unusable after 1 query. T-308 fix must add connection release/cleanup per-request.

