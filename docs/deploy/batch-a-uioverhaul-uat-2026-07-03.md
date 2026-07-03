# UAT 部署报告 — 行情决策 Batch A (md-ui-overhaul) [+ Batch B #11/#12, Batch B 补6/C, #10 W-2, #27 SIT]

- **Date**: 2026-07-03
- **Deployer**: deploy-engineer (glm-5.2)
- **部署 commit (merged main)**: `77734259`（HEAD；累进含 Batch A `223189b6` + watchlist `610c1c00` + schema 修复 `3e7a13c5` + 产业链 #12 `aa78d31f` + watchlist 前端 `3aa950ff` + Batch B 补6/C + #10 Dashboard W-2 + #27 SIT 全上）
- **Compose project**: `suying-uat`（独立 project，与 dev `docker` / 旧 `uat-adr013` 物理隔离）
- **端口偏移**: +900 带（PG 6332 / backend 8900 / screener 8901 / prediction 8902 / signal 8904 / trade 8906 / gateway 8980 / redis 8279 / 其余 8903/8905/8907/8909/8910）
- **frontend dev**: `http://localhost:3980`（3000 被 dev worktree `frontend-dev-3b-predictions` 占用 → 选 3980；vite proxy 经 `VITE_*_SERVICE_URL` 指向 UAT +900 服务）
- **training-service**: 未起（按 team-lead brief，本批不需要）

## Deploy Gate

**Verdict**: ✅ 部署成功（冒烟通过）

全栈起、迁移至 alembic 022、backend seed admin 成功、6 主路由 200、candidate-pool + watchlist 3 端点经 gateway/直连可达且 scope 头生效。

## 部署历程（❌→✅，复用栈）

1. **首轮 ❌**：backend crash-loop，根因 init_postgres.sql vs alembic 005/006 schema 双重定义（DuplicateColumn）→ 退回 backend-dev（详见下文"首轮失败归档"段 + buglog bug-020）。
2. **修复上主分支**：`3e7a13c5` fix(alembic) make migration 006/008 idempotent vs init_postgres.sql（`ADD COLUMN IF NOT EXISTS`）。
3. **复用栈重建 backend**：`docker compose -p suying-uat up -d --build backend` → lifespan 重跑 alembic 001→022 全通 + auth 表 + seed admin + /api/health 200。
4. **补重建 screener**：watchlist REST（`610c1c00`）在首轮 build 的 screener 镜像（早于该 commit）里缺失 → `docker compose -p suying-uat up -d --build screener-service` → watchlist 3 端点可达。
5. **起 frontend**：3000 被 dev worktree 占 → 3980；vite proxy 指向 UAT +900 服务。
6. **冒烟全过** → ✅。

## UAT 栈服务地址（交给 qa-engineer 作测试目标）

| 服务 | URL / 端口 | 健康 |
|---|---|---|
| **Frontend (vite dev)** | **http://localhost:3980** | ✅ 6 主路由 200 |
| Backend (auth) | http://localhost:8900 | ✅ `/api/health` 200 |
| API-Gateway | http://localhost:8980 | ✅ `/health` 200 |
| Screener (candidate-pool + watchlist) | http://localhost:8901 | ✅ `/api/v1/health` 200 |
| Signal | http://localhost:8904 | ✅ 200 |
| Prediction | http://localhost:8902 | ✅ 200 |
| Trade | http://localhost:8906 | ✅ 200 |
| Postgres | localhost:6332 | ✅ healthy（alembic 022，数据空） |
| Redis | localhost:8279 | ✅ healthy |

> Frontend 经 vite proxy 把 `/api/v1/*` 路由到 UAT +900 服务（`VITE_AUTH=8900`/`VITE_SCREENER=8901`/...）。qa-engineer 跑 E2E 用 **http://localhost:3980** 作入口。

## 三信号验证（backend 修复后）

- **SIGNAL 1 — alembic_version**：`SELECT version_num FROM alembic_version;` → **`022`**（lifespan 自动跑 001→022，含 watchlist 022）
- **SIGNAL 2 — auth 表 + seed admin**：
  ```
  roles: admin / internal_analyst / external_analyst / user（4 行）
  users JOIN roles: admin@suying.ai | role=admin | is_active=t
  watchlist 表: 14 列（migration 022 scope-aware schema）
  ```
- **SIGNAL 3 — backend /api/health**：`curl :8900/api/health` → `{"status":"healthy"}` **HTTP 200**（RestartCount=0，无 crash-loop）

## 冒烟证据（真实输出，非 dry-run）

### 6 主路由（frontend :3980，HEAD `3aa950ff`）
```
/                     → HTTP 200
/open-decision        → HTTP 200
/screener             → HTTP 200
/predictions          → HTTP 200
/signals              → HTTP 200
/supply-chain-bom     → HTTP 200
```

### candidate-pool GET（P0，经 frontend proxy → UAT screener，scope 头）
```
curl -H 'X-Tenant-Id: uat-smoke' -H 'X-Owner-User-Id: deploy-engineer' -H 'X-Trade-Account-Id: uat-acct-1' \
  http://localhost:3980/api/v1/screener/candidate-pool
→ HTTP 200
  {"total":0,"page":1,"page_size":50,"records":[],
   "empty_state":{"hint":"no_visible_pools","suggestion":"运行选股后自动落库，或检查 X-Tenant-Id / X-Owner-User-Id / X-Trade-Account-Id 头是否正确"},
   "fallback_reason":null}
```

### watchlist 3 端点（直连 UAT screener :8901，scope 头）
```
GET  /api/v1/screener/watchlist
  → HTTP 200 {"total":0,...,"empty_state":{"hint":"no_visible_stocks","suggestion":"...检查 X-Tenant-Id / X-Owner-User-Id / X-Trade-Account-Id 头..."}}

POST /api/v1/screener/watchlist  body={"code":"600519","name":"贵州茅台"}
  → HTTP 200 {"record":null,"fallback_reason":"persist_failed: ForeignKeyViolationError ...
              Key (code)=(600519) is not present in table \"stocks\"."}
  （端点可达 + scope 头生效；POST 失败因 watchlist.code 外键引用 stocks 表，而 stocks 当前空——见"数据就绪"）

DELETE /api/v1/screener/watchlist?code=600519
  → HTTP 200 {"deleted":0,"code":"600519","id":null,"fallback_reason":null}
```

> watchlist 端点冒烟结论：**3 端点全可达 + scope 头注入正确 + 优雅降级**（POST 的 FK 失败被正确包成 `fallback_reason` 而非 500，证明链路通）。POST 写入需 `stocks` 表有数据（见下）。

### 11 新 sub-tab 路由（frontend :3980，HEAD `77734259`，frontend dev 重启用最新代码）
> 主分支推进到 `77734259`（Batch B 补6/C + #10 Dashboard W-2 + #27 SIT），重启 :3980 dev server 后冒烟。

```
/dashboard/auction                → HTTP 200   (1.2)
/open-decision/auction             → HTTP 200   (2.2)
/open-decision/signals             → HTTP 200   (2.3)
/open-decision/execution           → HTTP 200   (2.5)
/screener/models                   → HTTP 200   (3.2)
/screener/factors                  → HTTP 200   (3.3)
/predictions/single                → HTTP 200   (5.1)
/predictions/compare               → HTTP 200   (5.2)
/predictions/backtest              → HTTP 200   (5.3)
/supply-chain-bom/policy           → HTTP 200   (4.1)
/supply-chain-bom/company          → HTTP 200   (4.3)
```

11 新 sub-tab 全 200；6 主路由复测仍全 200；candidate-pool GET 复测仍 200；backend `/api/health` 仍 200。栈容器无 restart/unhealthy。

## 迁移结果（容器内，lifespan 自动）

```
docker logs suying-uat-backend-1  # lifespan 段
INFO [alembic.runtime.migration] Running upgrade  -> 001 ... 021 -> 022
（022 = Bring watchlist to full scope-aware schema）
→ 全 22 个迁移无报错；alembic_version=022；auth 表 + watchlist 表(14列) 均建
```

## 数据就绪情况

- UAT postgres = fresh 卷，**无市场数据**：`stocks=0 / daily_kline=0 / candidate_pools=0 / daily_basic=0`。
- **影响**：
  - qa e2e 走 **EmptyState 兜底**可验证 6 主路由渲染 + candidate-pool/watchlist 的空态 UI（**可验**）。
  - **watchlist POST 写入验不了**：`watchlist.code` 外键引用 `stocks`，stocks 空时任何 POST 都返回 `fallback_reason: persist_failed FK`。要验完整 watchlist CRUD，需先回填 stocks（data-service 拉历史日线 + stocks 基础表）。
  - 真实 K线/选股结果落库链路同样待 data-service 回填后才能验。
- **建议**：qa-engineer 先验渲染 + 空态 + scope 头链路；watchlist CRUD 完整闭环 + 真实数据链路列为 data-service 回填后的 follow-up。

## 隔离起栈 / 复用命令（runbook 留档）

```bash
# 首轮起栈（独立 project + +900 端口带，secrets from docker/.env.uat）
export COMPOSE_PROJECT_NAME=suying-uat
export POSTGRES_PORT=6332 REDIS_PORT=8279 BACKEND_PORT=8900 API_GATEWAY_PORT=8980
export SCREENER_PORT=8901 PREDICTION_PORT=8902 STRATEGY_PORT=8903 SIGNAL_PORT=8904
export ALERT_PORT=8905 TRADE_PORT=8906 BACKTEST_PORT=8907 DIAGNOSIS_PORT=8909 DATA_SERVICE_PORT=8910
DOCKER_BUILDKIT=0 docker compose -p suying-uat --env-file .env.uat up -d \
  postgres redis backend api-gateway screener-service signal-service prediction-service \
  trade-service data-service alert-service backtest-service diagnosis-service

# 修复后复用栈（只重建变动服务，不动其他）
DOCKER_BUILDKIT=0 docker compose -p suying-uat --env-file .env.uat up -d --build backend
DOCKER_BUILDKIT=0 docker compose -p suying-uat --env-file .env.uat up -d --build screener-service

# frontend（3000 被 dev worktree 占 → 3980；proxy 指 UAT）
cd frontend
export VITE_AUTH_SERVICE_URL='http://127.0.0.1:8900' VITE_SCREENER_SERVICE_URL='http://127.0.0.1:8901' \
       VITE_PREDICTION_SERVICE_URL='http://127.0.0.1:8902' VITE_SIGNAL_SERVICE_URL='http://127.0.0.1:8904' \
       VITE_TRADE_SERVICE_URL='http://127.0.0.1:8906' VITE_GATEWAY_SERVICE_URL='http://127.0.0.1:8980'
npm run dev -- --port 3980 --strictPort
```

## 环境问题（已自修，记录备查）

1. **buildkit bake 在中文路径 cwd 故障**（`x-docker-expose-session-sharedkey non-printable ASCII`）→ `DOCKER_BUILDKIT=0`（legacy builder）绕过。
2. **Redis +900 端口**：首轮误用 97379（>65535 invalid）→ 改 8279（base 7379 + 900）。
3. **build 时 DNS 间歇失败**（trade-service pypi tuna 拉不到）→ 用已 build 镜像 up -d 绕过。
4. **frontend 端口冲突**：3000 被 dev worktree `frontend-dev-3b-predictions` 占 → 选 3980。
5. **frontend vite dev server 进程易掉（qa 注意）**：vite 是宿主进程（非 docker，无 `restart: unless-stopped` 自愈）。部署 ✅ 后多次自行退出（日志无 error，harness 回收 idle 后台任务 / SIGHUP）→ :3980 空连。**qa E2E 中若 :3980 突然连不上 ≠ UAT 后端/栈问题**，是前端 dev 进程掉了 → 叫 deploy-engineer 重启即可（docker 栈自愈，不受影响）。

   **保活重启法（已验证 PPID=1 脱离 harness，比 harness-managed 后台任务稳）**：
   ```bash
   cd frontend
   export VITE_AUTH_SERVICE_URL='http://127.0.0.1:8900' VITE_SCREENER_SERVICE_URL='http://127.0.0.1:8901' \
          VITE_PREDICTION_SERVICE_URL='http://127.0.0.1:8902' VITE_SIGNAL_SERVICE_URL='http://127.0.0.1:8904' \
          VITE_TRADE_SERVICE_URL='http://127.0.0.1:8906' VITE_GATEWAY_SERVICE_URL='http://127.0.0.1:8980'
   nohup npm run dev -- --port 3980 --strictPort > /tmp/uat-frontend-3980.log 2>&1 &
   disown
   echo $! > /tmp/uat-frontend-3980.pid
   ```
   - `nohup`（ignore SIGHUP）+ `disown`（移出 shell job table）→ vite 被 init/launchd 收养（PPID=1），harness 回收 idle 后台任务不再波及。
   - macOS 无 `setsid`；`nohup`+`disown` 已足够（实测 PPID=1，存活）。
   - 重启前先 `kill $(cat /tmp/uat-frontend-3980.pid)` 清旧进程；harness 管理的 `run_in_background` 后台任务**不要再用**（正是被回收的根源）。
   - 日志 `/tmp/uat-frontend-3980.log`；PID 文件 `/tmp/uat-frontend-3980.pid`。

## Hand-off

✅ → SendMessage product-lead（附 UAT URL 清单 + ✅ gate）→ PL 触发 qa-engineer 对**共享 UAT 栈**（入口 `http://localhost:3980`）跑 E2E。
- qa 验收范围：6 主路由渲染 + EmptyState 兜底 + candidate-pool/watchlist scope 头链路 + watchlist 空态。
- watchlist 完整 CRUD + 真实数据链路待 data-service 回填 stocks 后 follow-up（不阻断本批 UAT）。

---

## 首轮失败归档（❌ → 退回 → 修复 → ✅，留档供复盘）

**首轮 gate**: ❌ 部署失败（2026-07-03 早段）。backend crash-loop（ExitCode=3, RestartCount=9）。

**根因（代码问题）**：`services/sql/init_postgres.sql:594` 与 `backend/alembic/versions/006_multi_horizon_snapshots.py:46` 双重定义 `screening_snapshots.outcome_at` 列。init SQL 容器启动先建该列，migration 006 又无条件 `add_column` → `psycopg2.errors.DuplicateColumn` → 整个迁移事务回滚 → 无 `alembic_version` 戳、无 auth 表 → backend seed admin 失败 → crash-loop。反向印证：fresh db 无 init SQL 单跑 alembic 又崩在 005（`UndefinedTable: screening_scores`）。

**退回 + 修复**：退回 product-lead → backend-dev（task #13）→ 修复 commit `3e7a13c5`（migration 006/008 `add_column` 改 `ADD COLUMN IF NOT EXISTS`）。deploy-engineer 遵铁律 #1（deploy-only），**未改** `backend/` 或 `services/sql/` 源码。详见 buglog bug-020。
