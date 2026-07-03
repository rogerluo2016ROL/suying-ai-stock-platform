# deploy-engineer 状态

---

## 2026-07-03 — screener 镜像重建（方式2，P0 fix 生效）+ UAT 数据底座缺口实证：❌ D1 仍筛 0（数据问题，非 deploy/代码问题）

**Task**: team-lead 指示方式2 — 用 backend-dev worktree fix（`fix/screener-run-timeout-mdready` @ `fd4d76fc`）build screener 镜像，重建 UAT 容器，验 leader_scalp D1 通否。
**Fix 内容**: leader_scalp/intraday/closing 的 `'000001.SH'`→`'000001'`（PG index_daily.code 存无后缀）+ 板块门硬淘汰→软降权（score_stock F14）。
**Model**: glm-5.2

### 重建执行（方式2，不动主仓）
- worktree `.wolf/worktrees/backend-dev-mdready` 干净、HEAD `fd4d76fc`、build context=仓库根含 packages/kronos-factors。
- `DOCKER_BUILDKIT=0 docker compose -p suying-uat --env-file <主仓>docker/.env.uat build screener-service` → 镜像 `suing-uat-screener-service:latest` @ `f14ab70f1ef6` build 成功。
- **fix 进容器实证**：容器内 leader_scalp.py `ts_code='000001'` 出现 3 次、`ts_code='000001.SH'` 0 次 → 新代码确实打进镜像。
- 重建容器（screener + 把误改的 postgres/redis 拉回 89xx），health 200。

### ⚠️ 过程中的端口混乱与修正（自修，隔离恢复）
首轮 `up -d` 只用了主仓 `.env.uat`（内含 adr013 的 18xxx 端口变量），未 export 89xx 覆盖 → postgres/redis/screener 误跑到 16432/17379/18001。**数据无损**（卷 suying-uat_pgdata 持久化，candidate_pools=2 / daily_kline 07-02 / alembic 022 全在）。修正：export 89xx 端口变量集后 force-recreate，端口回归 6332/8279/8901。**教训**：suying-uat 起栈必须 export 89xx 变量覆盖 .env.uat 的 adr013 默认值（.env.uat 文件本身是 adr013 配置）。

### 冒烟结果：D1 leader_scalp **仍 total_picks=0**（07-01 + 07-02 均如此）
```
POST /run?mode=leader_scalp&trade_date=2026-07-02 → HTTP 200 total_picks=0 fallback=None
POST /run?mode=leader_scalp&trade_date=2026-07-01 → HTTP 200 total_picks=0 fallback=None
```

### 根因（因果闭环，三重实证）—— 数据底座问题，非 deploy/代码问题
- fix 生效确认：容器内 `'000001'` 3 次 / `'000001.SH'` 0 次。
- **但 UAT 库 6332 的 index_daily = 0 行**（host 直连 + 容器内 asyncpg + 容器名核对三重确认）→ fix 的 `'000001'` 查询在 UAT 上仍查不到行 → `get_shanghai_index` 返 0 → sh_pct=0 → 市场环境判定空 → 板块门 + 打分筛 0。
- 对照：backend-dev 本地验 0→20 picks 用的是 **dev 库 6432**（index_daily=10409 行、moneyflow=14M、daily_basic=10M、ths_daily=2M），其 AC5 的 `get_shanghai_index=0.4408` 只可能来自 6432。**fix 从未在 UAT 6332 验过。**
- UAT 6332 数据缺口：index_daily / moneyflow / daily_basic / ths_daily / limit_list_d 全 0（仅 daily_kline 93692 + stocks 5534 + stk_limit 7677 + candidate_pools 2 有）。

### Gate
❌ **D1 验证失败（数据底座问题，非 deploy 失败）**——镜像重建正确（fix 进容器实证）、隔离恢复、数据无损；但 UAT 库缺 index_daily 等表，fix 无法体现效果，leader_scalp 仍筛 0。归类 = **数据问题**（退回 PL 决策补数据），非 deploy/代码问题。

### 给 PL 的决策点
D1 要通 = UAT 6332 至少需补 index_daily（市场环境）+ 理想再补 moneyflow/daily_basic/ths_daily（打分维度）。源：dev 库 6432 有全量。补法：`pg_dump -h 127.0.0.1 -p 6432 -U kronos -d kronos -t index_daily -t moneyflow ... | psql -h 127.0.0.1 -p 6332`（deploy 配置操作，不改源码）。等 PL 拍板补哪些表。

---

## 2026-07-03 — 行情决策板块运行时环境收口 (P0)：✅ 部署成功（冒烟通过，suying-uat 为唯一正确环境）

**Task**: team-lead P0 — 三套 docker 并存（suying-uat/uat-adr013/docker）+ 前端默认指向断链的 uat-adr013 → 选定唯一正确环境 + 验证 8 服务健康 + DB/迁移/数据及时性 + 输出前端端口清单
**Commit**: main @ 9f02b734（UAT 栈 suying-uat 已基于此运行，5–11h up）
**Model**: glm-5.2

### 环境选定结论
**唯一正确环境 = `suying-uat`（89xx 带，gateway=8980/screener=8901/postgres=6332）。**
- uat-adr013（180xx）：网络内 **无 postgres 容器** → screener 日志 `could not translate host name "postgres" to address` → DB 依赖服务 liveness 200 但数据查询全断（"service 活≠能用"陷阱）。无 backend/auth。
- suying-uat：自包含 12 容器（PG+Redis+auth 齐全），alembic 022，真实数据回流。

### 服务健康矩阵（suying-uat，逐个 curl /api/v1/health 实证）
```
gateway:8980(/health) 200 | backend:8900(/api/health) 200 | screener:8901 200
prediction:8902 200 (model_loaded=false, base_public 预期) | signal:8904 200
diagnosis:8909 200 | backtest:8907 200 | trade:8906 200 (mode=paper) | alert:8905 200
data-service:8910 200
strategy:8903 / training:8908 → 未起（不在 team-lead 行情决策 8 服务范围）
```

### DB / 迁移 / 数据及时性（suying-uat-postgres @ 6332）
```
alembic_version = 022  | candidate_pools ✓(018) | watchlist ✓(022) | strategy_plans ✓
stocks=5534  | trade_cal=0 行(非阻塞)  | daily_kline_max=2026-07-02  | stk_mins_max=2026-07-03 11:30
stk_mins_today_rows=124925 (vs 昨日 4999) → 日内实时数据正常回流
```
**"candidate_pool 表不存在" 已澄清**: 实际表名复数 `candidate_pools`（`candidate_pool_store.py:18`），表存在；screener GET 200 返回空列表（未跑选股落库），无 DB 连接矛盾。
**"数据停在昨天" 已澄清**: daily_kline 是 EOD 数据，12:20 CST 盘中停在昨日是预期（收盘后才采），stk_mins 今日早盘已采 12.5 万行 → **未停滞，无需回填**。

### 502 根因 — 纠偏（PL + frontend-dev 双向复核后修正；首轮判断有误）

**C1/C2 均非前端代码缺陷，不退回 frontend-dev。** 真因 = 前端默认指向断链 uat-adr013（180xx），切到 suying-uat 后即消失。三方一致实证：
- **C1 POST candidate-pool 422**：screener.py:7400 `CandidatePoolRecordRequest` 强制 `source_module/source_mode/name`。首轮用**自制残缺 body**测 → 422（测试体缺陷）。改完整 body 实测 → HTTP 200 `id=3 fallback_reason=null`（gateway 8980 + 直连 8901 一致）。frontend-dev 确认主仓 3 处调用（Screener.tsx:716/948 + OpenDecision.tsx:753）均发完整强类型 payload（types.ts:1171）。
- **C2 GET /screener/results 404**：screener 确无此路由，但**前端不调**（client.ts:486 用 POST `/screener/run`；全仓 grep `/screener/results` 全空）。404 与前端无关。
- gateway 8980 `/dashboard/overview` 502（上游 404）= 后端 dashboard 聚合路由归属问题，转 backend-dev + PL 对齐。

### 前端应指向的端口清单（已 SendMessage frontend-dev）
```
VITE_AUTH_SERVICE_URL=http://127.0.0.1:8900
VITE_GATEWAY_SERVICE_URL=http://127.0.0.1:8980
VITE_SCREENER_SERVICE_URL=http://127.0.0.1:8901
VITE_PREDICTION_SERVICE_URL=http://127.0.0.1:8902
VITE_SIGNAL_SERVICE_URL=http://127.0.0.1:8904
VITE_ALERT_SERVICE_URL=http://127.0.0.1:8905
VITE_TRADE_SERVICE_URL=http://127.0.0.1:8906
VITE_BACKTEST_SERVICE_URL=http://127.0.0.1:8907
VITE_DIAGNOSIS_SERVICE_URL=http://127.0.0.1:8909
VITE_STRATEGY_SERVICE_URL=http://127.0.0.1:8903   # 未起，策略页才需要
VITE_TRAINING_SERVICE_URL=http://127.0.0.1:8908   # 未起，训练页才需要
```
附 vite 进程收口（frontend-dev 处理）：`:3000` 被 worktree 残留 PID 45464(`frontend-dev-3b-predictions`)/75974(`frontend-dev-1b-predc`) 占用，主仓 frontend/(86012) 被挤到 `:3980` → 用户访问 :3000 命中 worktree。需 kill worktree vite 后重启主仓占 :3000。

### 退回 dev 的问题（deploy-only 硬边界，不修源码）
| C1 | ~~前端 POST candidate-pool 缺必填字段~~ **撤回** — 测试体缺陷，前端无此 bug（见 502 纠偏段） | — |
| C2 | ~~前端 GET /screener/results 调不存在路由~~ **撤回** — 前端不调此路径（见 502 纠偏段） | — |
| C3 | data-service daily_kline FK daily_kline_code_fkey（部分 code 不在 stocks）| backend-dev/data |
| C4 | data-service stk_mins 批次低量（Tushare 权限/API）| backend-dev/data |
| C5 | data-service stock_news_tushare code null | backend-dev/data |
| C6 | gateway `/dashboard/overview` 502（上游 404）— dashboard 聚合路由历史残留；**前端不调此路径**（client.ts L630/L633 只调 `/dashboard/summary` + `/dashboard/auction`，PL codegraph+grep 双确认）。PL 裁定：开 follow-up issue 记录，**不阻断本 task，不派 backend 修** | follow-up issue |

### uat-adr013 下线（PL 授权，已执行）
前置检查：180xx 无 ESTABLISHED 客户端连接（frontend-dev 已 kill worktree vite，主仓切 89xx）。执行 `docker rm -f $(docker ps -aq --filter name=uat-adr013-)` → 11 容器(+3 exited) 全移除。`docker compose ls` 不再有 uat-adr013；18001/18080 LISTEN=0（端口释放）。suying-uat 复核仍 12 容器全活。
残留：`uat-adr013_default` 网络未删（`docker-redis-1` 仍挂载，属 `docker` 项目跨网遗留，无害；如需清：`docker network disconnect uat-adr013_default docker-redis-1 && docker network rm uat-adr013_default`）。

### follow-up
- strategy-service(8903)/training-service(8908) suying-uat 未起容器；行情决策板块前端不调（client.ts 无 strategy/training 调用），不阻断。需时补起（strategy=方案生成 DeepSeek，training=模型训练）。

### Gate
✅ 部署成功（冒烟通过）— suying-uat 行情决策 8 服务全活，PG/Redis/auth 齐全，迁移 022，日内实时数据回流（signal/live 返回真实盘中信号 920221 易实精密 16.62）。前端"无法使用"根因 = proxyTargets 默认指向断链 uat-adr013（已由 frontend-dev 切 89xx 落地）；非环境/前端代码问题。uat-adr013 已下线。dashboard/overview 502 为历史聚合路由残留，前端不调，开 follow-up issue，不阻断。

### Hand-off
已 SendMessage team-lead（状态 + 产物路径）+ frontend-dev（端口清单 89xx，已落地）。deploy 侧 P0 环境收口闭环，待命。完整 SIT 证据见本节。

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
