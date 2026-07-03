# deploy-engineer 状态

---

## 2026-07-03 — Batch A (md-ui-overhaul) UAT 部署：✅ 成功（schema 修复 `3e7a13c5` 后复用栈，冒烟全过）

**Task**: 行情决策 Batch A + Batch B #11/#12 — Dashboard/OpenDecision/Screener/Predictions/Signals/SupplyChainBom + watchlist + candidate-pool
**Commit**: `3aa950ff`（首轮 `223189b6` → schema 修复 `3e7a13c5` → 产业链 `aa78d31f` + watchlist 前端 `3aa950ff`）
**Model**: glm-5.2
**完整报告**: `docs/deploy/batch-a-uioverhaul-uat-2026-07-03.md`

### 部署证据（命令 + HTTP 状态码 + 真实输出）

复用栈重建（schema 修复后）：
```
DOCKER_BUILDKIT=0 docker compose -p suying-uat up -d --build backend          # alembic 001→022 全通
DOCKER_BUILDKIT=0 docker compose -p suying-uat up -d --build screener-service  # 补 watchlist REST(610c1c00)
cd frontend && VITE_*_SERVICE_URL=→UAT+900 npm run dev -- --port 3980 --strictPort  # 3000 被 dev worktree 占
```

三信号（backend 修复后）：
```
SIGNAL 1  alembic_version = 022 ✓
SIGNAL 2  roles(4行) + users(admin@suying.ai,role=admin,is_active=t) + watchlist(14列) ✓
SIGNAL 3  backend :8900 /api/health → {"status":"healthy"} HTTP 200 ✓ (RestartCount=0)
```

6 主路由（frontend :3980, HEAD 3aa950ff）：
```
/ /open-decision /screener /predictions /signals /supply-chain-bom → 全 HTTP 200
```

candidate-pool GET（P0，经 proxy，scope 头）→ HTTP 200：`{"total":0,"empty_state":{"hint":"no_visible_pools",...}}`

watchlist 3 端点（直连 :8901，scope 头）→ 全 HTTP 200，优雅降级：
```
GET    → {"total":0,"empty_state":{"hint":"no_visible_stocks",...}}
POST   → {"record":null,"fallback_reason":"persist_failed: FK watchlist_code→stocks (600519 not in stocks)"}
DELETE → {"deleted":0,"code":"600519","fallback_reason":null}
（POST 失败因 stocks 表空=数据问题非代码问题；端点链路通）
```

全栈 health（+900）：backend(8900)/screener(8901)/signal(8904)/prediction(8902)/trade(8906)/gateway(8980) 全 200；postgres(6332)/redis(8279) healthy。

PG 数据：全空（stocks=0 等，fresh 卷）。可验渲染+空态+scope 头链路；watchlist CRUD 完整闭环 + 真实数据链路待 data-service 回填 stocks 后 follow-up。

### 环境问题（已自修）
1. buildkit bake 中文路径 cwd 故障 → `DOCKER_BUILDKIT=0` 绕过
2. Redis 97379>65535 invalid → 改 8279
3. build 时 DNS flake → 用已 build 镜像 up -d 绕过
4. frontend 3000 被 dev worktree 占 → 选 3980 + vite proxy 指 UAT

### Gate
✅ 部署成功（冒烟通过）— 全栈 healthy + 6 路由 200 + candidate-pool/watchlist 可达 + scope 头生效。
首轮 ❌ 因代码 schema 双重定义（bug-020）→ 退回 backend-dev 修 `3e7a13c5` → 复用栈重建 → ✅。

### Hand-off
SendMessage product-lead（附 ✅ + UAT URL 清单）。qa-engineer 入口 `http://localhost:3980` 跑 E2E。

---

## 2026-07-03（首轮）— Batch A UAT 部署：❌ 失败（代码问题，已退回 PL→backend-dev，后修复转 ✅）

**首轮 Commit**: `223189b6` ｜ **首轮报告**：同上完整报告文件"首轮失败归档"段

### 部署证据（命令 + HTTP 状态码 + 真实输出）

起栈（独立 project `suying-uat` + +900 端口带，遵 deployment.md §6.2）：
```
export COMPOSE_PROJECT_NAME=suying-uat
export POSTGRES_PORT=6332 REDIS_PORT=8279 BACKEND_PORT=8900 API_GATEWAY_PORT=8980
export SCREENER_PORT=8901 PREDICTION_PORT=8902 STRATEGY_PORT=8903 SIGNAL_PORT=8904
export ALERT_PORT=8905 TRADE_PORT=8906 BACKTEST_PORT=8907 DIAGNOSIS_PORT=8909 DATA_SERVICE_PORT=8910
DOCKER_BUILDKIT=0 docker compose -p suying-uat --env-file .env.uat up -d \
  postgres redis backend api-gateway screener-service signal-service prediction-service \
  trade-service data-service alert-service backtest-service diagnosis-service
→ postgres/redis healthy；10 app Started；backend Restarting(3)
```

健康（+900）：
```
screener(8901)/signal(8904)/prediction(8902)/trade(8906) /api/v1/health = 200
api-gateway(8980) /health = 200
backend(8900) ❌ crash-loop (ExitCode=3, RestartCount=9)
```

candidate-pool GET（P0，经 gateway，带 scope 头）→ **HTTP 200**：
```
{"total":0,"page":1,"page_size":50,"records":[],
 "empty_state":{"hint":"no_visible_pools","suggestion":"...检查 X-Tenant-Id / X-Owner-User-Id / X-Trade-Account-Id 头..."},
 "fallback_reason":null}
```

迁移（失败，真因）：
```
alembic_version 表不存在（迁移从未 stamp）。手动 alembic upgrade head 暴露：
  006_multi_horizon_snapshots.py:46 op.add_column('screening_snapshots','outcome_at')
  → DuplicateColumn: init_postgres.sql:594 已建该列；migration 无条件 add_column 撞车
反向印证（fresh db 无 init SQL）：alembic 崩在 005 UndefinedTable: screening_scores（依赖 init SQL 建的表）
→ init SQL 与 alembic 005/006 schema 双重定义/排序冲突 = 代码问题
```

PG 数据（fresh 卷，全空）：`stocks=0 daily_kline=0 candidate_pools=0 daily_basic=0`（空数据可接受，QA 走 EmptyState 兜底）

### 环境问题（已自修）
1. buildkit bake 中文路径 cwd 故障（`x-docker-expose-session-sharedkey non-printable ASCII`）→ `DOCKER_BUILDKIT=0` 绕过
2. Redis 97379>65535 invalid → 改 8279
3. build 时 DNS flake（trade-service pypi 拉不到）→ 用已 build 镜像 up -d 绕过

### Gate
❌ 部署失败 — backend(P0 认证依赖) crash-loop。代码问题（schema 双重定义）→ 退回 PL → backend-dev 修。
遵铁律 #1（deploy-only），未改 `backend/` 或 `services/sql/` 源码。

### 下一步
- backend-dev 修 init SQL vs alembic 005/006 冲突（建议 006 `add_column`→`ADD COLUMN IF NOT EXISTS`，或 init SQL 不预建 screening_snapshots/scores）
- 修复后复用本栈：`docker compose -p suying-uat up -d --build backend` + 重跑 alembic，无需重起全栈

---

## 2026-06-22 — ADR-013 UAT 隔离栈（历史，已完成签字）

**Task**: #5 — 起 ADR-013 UAT 隔离栈
**Status**: ✅ COMPLETED（PL 已签字 Conditional Promote, ADR-013 merged @ 2180fa7）
**Commit**: 0ba2a3e → 2180fa7
**Model**: deepseek-v4-pro

## 已完成

- [x] 拆除旧 suying-uat 栈（alembic 007 pre-ADR-013，含 pgdata 卷）
- [x] `.env.uat` 创建（端口偏移 +10000，PG 16432 / Redis 17379 / API 18080 / backend 19001 / 8001-8009→18001-18009）— **未入库**（gitignore `docker/.env.*`，host shell 注入 TUSHARE_TOKEN）
- [x] Postgres (16432) + Redis (17379) up & healthy
- [x] ths_daily 17 列 + BIGSERIAL PK + UNIQUE(code,trade_date) + idx_ths_daily_code_date — AC #2
- [x] **Retag 旧 suying-uat 镜像 → uat-adr013**（10 服务节省 30-60min build）
- [x] **`docker compose -p uat-adr013 --env-file .env.uat up -d` 起栈**
- [x] **冒烟各服务 `/health`**（PL 主导 round 2，10/10 health pass）
- [x] **data-service 宿主进程启动 → cb_sync 实跑** → ths_daily 3015 行 change_pct 100% 非 NULL
- [x] **`docker/uat-adr013-deploy.sh` 入库**（commit 2180fa7，复用脚本）
- [x] **部署报告**：QA round 2 报告 `docs/reviews/adr-013-e2e-uat-report-2026-06-22.md` 含部署证据

## 双轨部署教训（→ tech-lead memory）

- **Root cause 1**: retag 旧镜像导致 backend Alembic 008-011 缺失 → exit 3 restart loop
- **Root cause 2**: rebuild 后 init_postgres.sql 已含 post-011 schema, alembic 从 001 跑会 `multiple primary keys for table pledge_detail`
- **修复（4 步）**：(1) rebuild backend, (2) 手动跑 alembic 001→007（建 auth tables, init_sql 无）, (3) `alembic stamp 011`, (4) restart backend → lifespan no-op → seed_roles OK
- **永久教训**：`.claude/agent-memory/tech-lead/data-pipeline-dual-track-deployment.md`

## 已知风险（pre-existing, 不阻断 ADR-013）

- **DEF-3 Medium**: api-gateway:18080 路由到 `localhost:9001` 错（容器内寻址）→ follow-up issue
- **DEF-4 Medium**: docker-compose.yml 业务微服务缺 `JWT_SECRET_KEY` env → follow-up issue
- data-service 不在 docker-compose.yml，需宿主进程启动（按 ADR-006 设计）

## 质量门

- [x] UAT 栈 up & healthy（10/10 health pass round 2）
- [x] ADR-013 核心 AC pass^2 (AC-1/3/4/8 P0)
- [x] PL 签字 Conditional Promote (2026-06-22)
- [x] 部署证据落 progress/qa-engineer.md + docs/reviews/adr-013-e2e-uat-report-2026-06-22.md
