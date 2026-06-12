---
tester: qa-engineer
stage: UAT
report_verdict: Promote
uat_signoff_verdict: pending
ac_total: 8
ac_pass: 8
ac_fail: 0
ac_blocked: 0
p0_total: 8
p0_pass: 8
p0_pass2_total: 8
p0_pass2_ok: 8
feature: repair-sprint-w2-backend
---

# QA Report -- Wave 2 后端修复 (Line A + Line D) -- UAT

- **Date**: 2026-06-12
- **Stage**: UAT
- **Tester**: qa-engineer (deepseek-v4-pro)
- **Branch**: feature/suying-ai-stock-platform
- **Environment**: 静态代码验证（无运行时服务依赖；所有 AC 为代码级静态验证）
- **PRD**: N/A（修复 Sprint，无独立 PRD；AC 由 team-lead 派单指定）
- **Code review (含 SIT Audit)**: docs/reviews/repair-sprint-w2-backend-2026-06-12.md (approve, 0 Critical)

## Summary

- Total AC: 8
- Passed: 8
- Failed: 0
- Blocked: 0
- **Verdict**: Promote

## Pre-conditions Checked

- [x] code-reviewer 报告已存在且 verdict = approve（SIT Audit = Pass for both Line A and Line D）
- [x] AC 由 team-lead 明确列出（8 条）
- [x] 代码静态验证环境就绪（文件系统可读）

## AC Results

### AC-301.1 (P0): ETL CB 函数使用 _Db 封装（非直接 psycopg2）

- **Priority**: P0
- **Setup**: 读取 `packages/kronos-data/kronos_data/etl.py`
- **Action**: 验证 5 个 CB sync 函数是否全部通过 `_insert_rows(db, ...)` 写入，且不直接调用 `psycopg2`
- **Expected**: 5 个 CB sync 函数全部使用 `_Db` 封装 + `_insert_rows`；直接 `import psycopg2` 仅出现在工具函数 `_get_etl_db` 和 `_insert_rows` 内部
- **Actual (run 1)**:
  ```
  $ grep -n "def sync_cb_" etl.py
  1502:def sync_cb_basic(days_back: int = 0) -> dict:
  1569:def sync_cb_daily(days_back: int = 30) -> dict:
  1624:def sync_cb_price_chg(days_back: int = 365) -> dict:
  1677:def sync_cb_call(days_back: int = 365) -> dict:
  1715:def sync_cb_factor(days_back: int = 30) -> dict:

  $ grep -n "_insert_rows(db, .cb_" etl.py
  1561:    written = _insert_rows(db, "cb_basic", cols, rows)
  1616:        written += _insert_rows(db, "cb_daily", cols, rows)
  1669:        written += _insert_rows(db, "cb_price_chg", cols, rows)
  1707:    written = _insert_rows(db, "cb_call", cols, rows)
  1756:        written += _insert_rows(db, "cb_factor", cols, rows)

  $ grep -c "import psycopg2" etl.py
  2
  (仅 _get_etl_db L131 和 _insert_rows L151 内部使用)
  ```
- **Actual (run 2)**:
  ```
  $ grep -c "import psycopg2" etl.py
  2  (一致)
  $ grep -n "_insert_rows(db, .cb_" etl.py | wc -l
  5  (一致)
  ```
- **Reliability**: `pass^2 = 2/2`
- **Verdict**: Pass

---

### AC-301.2 (P0): Gateway 移除 httpx，使用 urllib async wrapper

- **Priority**: P0
- **Setup**: 读取 `services/api-gateway/app/main.py`
- **Action**: 验证 `httpx` 零引用，且使用 `urllib.request` + `loop.run_in_executor` 异步包装
- **Expected**: 无 `import httpx`，使用 `urllib.request.Request` + `urlopen`，通过 `loop.run_in_executor` 实现异步
- **Actual (run 1)**:
  ```
  $ grep "import httpx\|from httpx\|httpx\." services/api-gateway/app/main.py
  (无匹配, EXIT: 1)

  $ grep -n "loop.run_in_executor\|urllib.request\|urllib.error" services/api-gateway/app/main.py
  4:(loop.run_in_executor), not httpx/aiohttp.
  9:from urllib.request import Request as UrlRequest, urlopen
  10:from urllib.error import URLError, HTTPError
  83:        resp = await loop.run_in_executor(None, _proxy)
  ```
  - L78-80 `_proxy()` 构建 `UrlRequest` + `urlopen`
  - L89-96 HTTPError 透传上游状态码，URLError 返回 502
- **Actual (run 2)**:
  ```
  $ grep "import httpx\|from httpx\|httpx\." services/api-gateway/app/main.py
  (无匹配, EXIT: 1 -- 一致)
  ```
- **Reliability**: `pass^2 = 2/2`
- **Verdict**: Pass

---

### AC-301.3 (P0): Gateway 端口 8000→8080

- **Priority**: P0
- **Setup**: 读取 `services/api-gateway/app/main.py`
- **Action**: 验证 health check 和 uvicorn.run 均使用端口 8080
- **Expected**: Gateway 端口统一为 8080
- **Actual (run 1)**:
  ```
  $ grep -n "8080" services/api-gateway/app/main.py
  50:        return {"status": "healthy", "gateway": "api-gateway:8080"}
  101:    uvicorn.run("app.main:app", host="0.0.0.0", port=8080, reload=True)
  ```
  - Health check 声明 `api-gateway:8080`
  - `uvicorn.run` `port=8080`
  - 文件内无 `8000` 引用
- **Actual (run 2)**:
  ```
  $ grep -n "8080" services/api-gateway/app/main.py
  50:        return {"status": "healthy", "gateway": "api-gateway:8080"}
  101:    uvicorn.run("app.main:app", host="0.0.0.0", port=8080, reload=True)
  (一致)
  ```
- **Reliability**: `pass^2 = 2/2`
- **Verdict**: Pass

---

### AC-302.1 (P0): ADR-001 含 auth 内嵌 backend 决策记录

- **Priority**: P0
- **Setup**: 读取 `docs/adr/001-auth-rbac.md`
- **Action**: 验证 ADR-001 包含 auth 合并入 backend 的正式决策记录
- **Expected**: ADR-001 含 "实施变更记录" 节，记录 4 条变更；决策表已更新；后续工作已标记完成
- **Actual (run 1)**:
  ```
  文件: docs/adr/001-auth-rbac.md

  L62-67 "实施变更记录（2026-06-12）" 含 4 条：
  1. auth-service 不独立部署，合并入 backend/（端口 9001）
  2. kronos-auth 不独立发布，合并入 backend/app/
  3. Alembic 迁移位于 backend/alembic/versions/001_add_auth_tables.py
  4. 数据库端口统一为 6432

  L25 决策表 "认证服务" 行：
  "原决策 … 独立 auth-service (FastAPI，端口 8010) → 实施变更为合并入 backend (9001)"

  L54-60 后续工作：5 项全部 [x] 完成
  ```
- **Actual (run 2)**:
  ```
  $ grep -c "实施变更记录" docs/adr/001-auth-rbac.md
  1  (一致)
  $ grep -c "合并入 backend" docs/adr/001-auth-rbac.md
  4  (一致)
  ```
- **Reliability**: `pass^2 = 2/2`
- **Verdict**: Pass

---

### AC-302.2 (P0): materialized_views.sql 独立文件含 4 MV DDL

- **Priority**: P0
- **Setup**: 读取 `services/sql/materialized_views.sql` 和 `services/sql/init_postgres.sql`
- **Action**: 验证独立 SQL 文件包含 4 个物化视图 DDL，且 init_postgres.sql 正确引用
- **Expected**: materialized_views.sql 包含 4 个 MV（今日强势股 / 行业动量 / 资金净流入 Top 50 / 每日综合排名），每个含 DROP + CREATE + UNIQUE INDEX
- **Actual (run 1)**:
  ```
  文件: services/sql/materialized_views.sql (133 行)

  $ grep "DROP MATERIALIZED VIEW\|CREATE MATERIALIZED VIEW" services/sql/materialized_views.sql
  DROP MATERIALIZED VIEW IF EXISTS mv_today_strong_stocks;
  CREATE MATERIALIZED VIEW mv_today_strong_stocks AS
  DROP MATERIALIZED VIEW IF EXISTS mv_sector_momentum;
  CREATE MATERIALIZED VIEW mv_sector_momentum AS
  DROP MATERIALIZED VIEW IF EXISTS mv_top_capital_inflow;
  CREATE MATERIALIZED VIEW mv_top_capital_inflow AS
  DROP MATERIALIZED VIEW IF EXISTS mv_daily_composite_ranking;
  CREATE MATERIALIZED VIEW mv_daily_composite_ranking AS

  $ grep "UNIQUE INDEX" services/sql/materialized_views.sql
  CREATE UNIQUE INDEX idx_mv_strong_code ON mv_today_strong_stocks(code);
  CREATE UNIQUE INDEX idx_mv_sector_ind ON mv_sector_momentum(industry);
  CREATE UNIQUE INDEX idx_mv_cap_code ON mv_top_capital_inflow(code);
  CREATE UNIQUE INDEX idx_mv_composite_code ON mv_daily_composite_ranking(code);

  init_postgres.sql L461-462:
  -- 物化视图 DDL 已独立到 services/sql/materialized_views.sql（含 4 个视图）
  -- 执行: psql -U kronos -d kronos -f services/sql/materialized_views.sql
  ```
- **Actual (run 2)**:
  ```
  $ grep -c "CREATE MATERIALIZED VIEW" services/sql/materialized_views.sql
  4  (一致)
  ```
- **Reliability**: `pass^2 = 2/2`
- **Verdict**: Pass

---

### AC-307.1 (P0): CORS 白名单改为环境变量，无 "*"

- **Priority**: P0
- **Setup**: 读取 `services/trade-service/app/main.py` 和 `services/strategy-service/app/main.py`
- **Action**: 验证两个服务的 CORS 配置使用 `CORS_ALLOWED_ORIGINS` 环境变量，无 `allow_origins=["*"]`
- **Expected**: CORS 白名单从环境变量读取，`.split(",")` 拆分；`allow_credentials=True`；无 `"*"` 通配符
- **Actual (run 1)**:
  ```
  trade-service/app/main.py L36-46:
  CORS_ALLOWED_ORIGINS = os.environ.get(
      "CORS_ALLOWED_ORIGINS", "http://localhost:5173,http://localhost:3000"
  ).split(",")
  app.add_middleware(
      CORSMiddleware,
      allow_origins=CORS_ALLOWED_ORIGINS,
      allow_credentials=True,
      allow_methods=["*"],
      allow_headers=["*"],
  )

  strategy-service/app/main.py L36-46: 同上模式

  $ grep -rn 'allow_origins.*\["*"\]' services/trade-service/ services/strategy-service/
  (无匹配, EXIT: 1)
  ```
- **Actual (run 2)**:
  ```
  $ grep -rn 'allow_origins.*\["*"\]' services/trade-service/ services/strategy-service/
  (无匹配, EXIT: 1 -- 一致)
  ```
- **Reliability**: `pass^2 = 2/2`
- **Verdict**: Pass

---

### AC-307.2 (P0): trade_password Query→Body

- **Priority**: P0
- **Setup**: 读取 `services/trade-service/app/routes.py`
- **Action**: 验证 `broker_connect` 端点的 `trade_password` 参数使用 `Body` 而非 `Query`
- **Expected**: `trade_password` 使用 `Body("", embed=True)`，密码不出现在 URL query string
- **Actual (run 1)**:
  ```
  trade-service/app/routes.py L372:
  trade_password: str = Body("", embed=True),

  L392 broker_config 同步包含:
  "trade_password": trade_password,

  无 Query 参数通过 URL 传输密码
  embed=True 确保请求体格式为 {"trade_password": "value"}
  ```
- **Actual (run 2)**:
  ```
  $ grep "trade_password" services/trade-service/app/routes.py
      trade_password: str = Body("", embed=True),
              "trade_password": trade_password,
  (一致, 无 Query 引用)
  ```
- **Reliability**: `pass^2 = 2/2`
- **Verdict**: Pass

---

### AC-307.3 (P0): LIM-1 POST /sync 后 status 正确更新

- **Priority**: P0
- **Setup**: 读取 `services/data-service/app/routers/data.py` 和 `services/data-service/app/scheduler.py`
- **Action**: 验证 `POST /sync/post_market` 通过 `_run_job` 执行，并在响应中返回 `_job_status`
- **Expected**: `trigger_post_market` 通过 `_run_job` 执行同步任务，`_run_job` 更新 `_job_status`；API 响应包含 `last_run` / `pg_write_status` / `pg_written`
- **Actual (run 1)**:
  ```
  data.py L71-86:
  @router.post("/sync/post_market")
  async def trigger_post_market(date_param: str = Query(None, alias="date")):
      """手动触发盘后同步 (P0+P1) — 经 _run_job 更新 _job_status."""
      ...
      core_job = {"id": "post_market_core", "fn": sync_post_market_core, ...}
      ext_job = {"id": "post_market_ext", "fn": sync_post_market_ext, ...}
      await _run_job(core_job)
      await _run_job(ext_job)
      return {"status": "ok",
              "core": _job_status.get("post_market_core", {}),
              "ext": _job_status.get("post_market_ext", {})}

  scheduler.py L66-86:
  async def _run_job(job: dict):
      """执行单个任务并记录状态."""
      ...
      _job_status[job["id"]] = {
          "last_run": t0.isoformat(), "last_status": "ok",
          "result": str(result)[:300],
          "pg_write_status": pg_status,
          "pg_written": pg_total,
      }
  ```
- **Actual (run 2)**:
  ```
  $ grep -c "_run_job" services/data-service/app/routers/data.py
  3  (一致)
  $ grep -c "_job_status\[" services/data-service/app/scheduler.py
  2  (一致)
  ```
- **Reliability**: `pass^2 = 2/2`
- **Verdict**: Pass

---

## Defects Found

无。

## Cross-stage Notes

- 本 UAT 为静态代码验证，所有 8 个 AC 为代码级 AC（非运行时行为 AC）
- 运行时验证（SIT）已由 dev 自跑并通过 code reviewer audit，证据见 `progress/backend-dev-w2.md` 和 `progress/backend-dev-w2-d.md`
- Line D (T-307) 3 个 AC 为前置 sprint 已实现，本次仅验证确认，无新增代码变更
- materialized_views.sql 已修正为与 PG 实际 DDL 一致（涨幅阈值 7-12%、LIMIT 50 等），SIT 阶段 PG 视图 count 返回 (3,0,0,3)

## Cost (this QA session)

- Tokens consumed: N/A（无 `/usage` 工具在当前 session）
- Estimated cost: ~CNY 0.50
- 同 feature 累计（E2E + UAT 总和）：N/A（本次无 E2E，仅 UAT）

## Hand-off

Promote -- SendMessage product-lead 进业务签字阶段。全部 8 条 AC pass^2 确认，代码级静态验证通过，无 defect。

---

### PL 业务签字

- [ ] 签字人: _______________
- [ ] 日期: _______________
- [ ] 业务判定: approve / request changes
- [ ] 备注: _______________
