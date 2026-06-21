---
feature: phase0-stabilization
reviewer: code-reviewer
date: 2026-06-21
scope: "阶段 0 止血 T-002 / T-004 / T-005 / T-006 / T-007 全部代码改动 + SIT Audit"
code_verdict: approve with changes
sit_audit_verdict: "⚠️ Pass with concerns"
critical_count: 0   # C-1 Resolved (§8 最终复审)
warning_count: 3   # W-1/W-2 留阶段3, W-4 仍开(非阻断); W-3 已解决
suggestion_count: 4
go_no_go: "CONDITIONAL GO (C-1 Resolved; AC-2 curl 归 UAT 冒烟)"
---

# 阶段 0 止血 — 代码审查 + SIT Audit

> 审查范围：Phase0Stabilization team 阶段 0 五个 task 的全部代码改动（T-002 frontend / T-004 backend / T-005 认证+schema / T-006 trade 审计 / T-007 风控 fail-safe）。
> 审查人：code-reviewer（review-only，未改一行源码）。SIT Audit 为本次审查的一部分，不另起 phase。
> **C-1 修复方案已由 tech-lead 裁定（两层都要做），见 §3**。

---

## 0. 审查方法与独立验证

本审查**独立复跑了关键 SIT 证据**以验证可信度（audit 检查 #3），非依赖 dev 自报：

| 验证项 | 命令 | 结果 |
|---|---|---|
| 全部后端改动语法 | `python3 -c "import ast; ast.parse(...)"` ×9 文件 | ✅ 9/9 OK |
| T-007 fail-safe 单测 | `PYTHONPATH=app backend/.venv/bin/pytest tests/test_fail_safe_db_unreachable.py` | ✅ **3 passed**（与 dev SIT 一致）|
| T-005 认证密钥单测 | `pytest packages/kronos-auth/tests/... + backend/tests/...` | ✅ **6 + 8 = 14 passed**（与 dev SIT 一致）|
| T-002 前端类型 | `cd frontend && npx tsc -b --noEmit` | ✅ exit 0 |
| T-007 forecast schema 修复 | grep `forecast_data` 列定义 in `services/sql/init_postgres.sql` | ✅ `forecast_net_profit` 存在，`change_reason` 不在 forecast_data（属 cb_price_chg）—— 修复正确 |
| T-002 残留裸 fetch | `grep -rn "fetch(" frontend/src` | ⚠️ 8 处残留（见 W-2）|
| `KRONOS_ENV=production` 在部署的设置 | grep 全仓 docker/services/backend | ❌ **零命中**（驱动 C-1）|

> 系统默认 python3.14 无 pytest-asyncio；dev SIT 用 `backend/.venv`（含 pytest-asyncio 1.4.0）复跑成功。该 venv 在仓库外但开发链路内，证据可信。

---

## 1. 逐 task 审查表

| Task | 改动概要 | 审查结论 | 关键证据 file:line |
|---|---|---|---|
| **T-002** frontend | 7 页 fetch→axios、Diagnosis 删 generateMockResult（145 行）、auth-flow cleanup afterEach、vitest forks pool + testTimeout 20s | **P2 / OK with W-2** | Diagnosis.tsx diff −145 行；vitest.config.ts pool:'forks'；auth-flow.test.tsx afterEach(cleanup) |
| **T-004** backend | scheduler.py + pg_writer.py 补 `from psycopg2.sql import SQL, Identifier`；compose 明文密码改 `${VAR:?}` | **OK** | scheduler.py import（grep 4 处 SQL/Identifier 使用）；pg_writer.py（1 处使用，非 dead import）|
| **T-005** 认证+schema | config×2 分级 `_secret()`（prod raise / dev warn + `dev-only-` 前缀）；删 `secrets.token_hex` + `Admin123!`；main.py `_run_migrations()` lifespan 跑 alembic；Dockerfile WORKDIR 修；compose DATABASE_SYNC_URL + **C-1 修复（compose 接线 + deps SERVICE_AUTH_ENABLED 守卫）** | **OK**（C-1 Resolved §8）| `backend/app/config.py:16-34`；`packages/kronos-auth/kronos_auth/config.py:16-34,53`；`deps.py:76`；`backend/app/main.py:16-36` |
| **T-006** trade 审计 | database.py 新增（async engine + URL 适配）；routes.py `_audit_record_safe` async + 4 操作挂 Depends + `/audit-logs` 真查询；audit_log.py `::jsonb`→`CAST(... AS jsonb)` | **OK**（W-1 client_ip 未采集）| routes.py:189/355/427/489 四挂载点；audit_log.py:80-81 CAST 修复；database.py `_resolve_async_url()` |
| **T-007** 风控 fail-safe | executor `_risk_engine` 连接池 + `RiskCheckUnavailable` + 3 风控函数 async + raise + `_run_one_check` catch→pause + forecast schema fix | **OK**（最高风险项通过）| auto_trading_executor.py:50-60 engine；:74 异常类；:479 try；:497 `mgr.pause()`+`return`；:576/:626/:655 三 raise |

---

## 2. 资金安全专项（T-006 / T-007 — 最高风险）

### T-007 fail-safe 语义 ✅ PASS（核心铁律达成）

逐条核对 ADR-007 AC-10「连接失败=系统性风险→暂停整轮」铁律：

1. **真暂停，非 return True/False**：`auto_trading_executor.py:479` 把卖/买双循环整体包进 `try`，`except RiskCheckUnavailable`（:497）→ `mgr.pause(strategy.id)` + `return`（本轮终止，不下单）。**未出现** `return True`（全卖）或维持 `return False`（不止损继续下单）。✅
2. **3 函数 raise 而非中性默认**：`_check_announcement_risk`（:576）、`_get_atr_stop_loss`（:626，含 `except RiskCheckUnavailable: raise` 防自吞）、`_check_forecast_risk`（:655）DB 失败一律 `raise RiskCheckUnavailable`。**绝无** `return False / return 0.0 / return ""` 静默放行。✅
3. **暂停机制复用既有 AC-202 范式**：`mgr.pause()` 复用 ADR-003 `asyncio.Event`（`_pause_event.clear()` + status="paused"），`_executor_loop` `await state._pause_event.wait()` 自动阻塞。未重造轮子。✅
4. **进程级单例池**：`_risk_engine` 模块级（:50-60），`pool_timeout=5` 防无限阻塞、`pool_pre_ping` 兜底断连。单策略 stop 不关共享池（生命周期正确）。✅
5. **schema fix 正确**：原 `_check_forecast_risk` 查 `change_reason` 列在 `forecast_data` 表不存在（属 `cb_price_chg` 表），被旧 `except:return ""` 静默吞 → 表现为"无风险放行买入"。改为 `forecast_net_profit`（净利<0 视为预亏），grep `services/sql/init_postgres.sql:224` 确认列存在。✅

**独立复跑**：`tests/test_fail_safe_db_unreachable.py` 3 用例 PASSED（mock DB fail → 断言 `status=="paused"` + `orders_placed==0` + `place_order` 从未被调；健康 DB 回归不暂停）。证据可信。

> S-1（suggestion）：`_check_forecast_risk` 的 `except Exception` 比 `_get_atr_stop_loss` 宽（后者有 `except RiskCheckUnavailable: raise` 自保）。forecast 函数把 `float(net_profit)` 数据解析也包进 try → 非 DB 的数据格式异常也会触发暂停。对 fail-safe 是"安全方向偏保守"（宁可暂停不止损），可接受；如要精确化，可对 `OperationalError/DBAPIError` 单独 raise、其他 exception 记 warn 后返回 None。

### T-006 审计落表 ✅ PASS

1. **4 类操作全挂载**：grep 确认 `routes.py:189 (PLACE_ORDER) / :355 (MODE_SWITCH) / :427 (BROKER_CONNECT) / :489 (CIRCUIT_BREAKER)` 四处均 `await _audit_record_safe(db, ...)`。无遗漏旧式同步调用。✅
2. **持久化验证**：dev SIT 提供"kill 重启后 total=4 全部存活"证据，结构可信（真实 PG + 真实 uvicorn）。✅
3. **写失败 best-effort 不阻断**：`_audit_record_safe`（:552）`try/except`：成功 commit，失败 `rollback + logger.exception`（非静默吞、非 re-raise）。dev SIT 用 `127.0.0.1:9999` 强制失败验证主操作仍 200 + traceback 留痕。✅
4. **asyncpg 兼容 bug 修复正确**：`audit_log.py:80-81` `::jsonb`→`CAST(:details AS jsonb)`，asyncpg dialect 不再把 `::jsonb` 当命名占位符。修复是 AC-9 落表的必需项。✅
5. **无 SQL 注入**：`record()` / `query()` 全用 `text()` + bind 参数（`:code`/`:action`/`:mode`），`query_audit` 的 WHERE 子句拼接的是固定列名常量非用户输入。✅

> W-1（warning）：`_audit_record_safe` 新增了 `client_ip` 参数（routes.py:562），但 **4 个调用点全部未传 `client_ip`**（也无 `request: Request` 注入来取 IP）。审计表 `client_ip` 列恒为 NULL，降低了审计追溯力（IP 是资金操作追责的关键字段）。建议：4 个 handler 注入 `request: Request`，传 `request.client.host`。不阻断 UAT（功能可用），但应在正式上线前补。

---

## 3. 认证安全专项（T-005）— ⚠️ 含 C-1

### 机制本身 ✅ 设计正确

`_secret(env_key, dev_fallback)`（`backend/app/config.py:16-34` 与 `packages/kronos-auth/kronos_auth/config.py:16-34` 同构）：
- env 有值 → 用 env 值；
- `KRONOS_ENV=production` 且缺失 → `raise RuntimeError`（进程退出非 0）；
- 否则 `warnings.warn` + `dev-only-` 前缀 fallback（日志一眼识别）。

- ✅ **移除 `secrets.token_hex`**（backend/app/config.py 旧 JWT 路径）—— 进程内随机使多实例/重启 token 互不兼容，比硬编码更隐蔽。AST 单测断言无 `secrets.token_hex` Call。
- ✅ **移除 `Admin123!`** 默认 —— AST 单测断言 ADMIN_PASSWORD 默认非 `Admin123` 字面量。
- ✅ 单测 6 + 8 = 14 全绿，覆盖 prod-raise / dev-warn / fallback 前缀。

### 🔴 C-1（Critical）：分级 raise 的 prod-gate 在部署侧未接线 —— X-Service-Auth 越权后门

**问题**：`packages/kronos-auth/kronos_auth/deps.py:70` 的 `X-Service-Auth` 验证是字符串相等比较：

```python
service_auth = request.headers.get("X-Service-Auth", "")
if service_auth == KRONOS_SERVICE_SECRET:   # ← 字符串比较
    return {"sub": "service", "role": "admin", ...}   # admin-equivalent
```

`KRONOS_SERVICE_SECRET` 的值来自 `_secret()`：**只有当 `KRONOS_ENV=production` 且 env 缺失时才 raise**。但：

- `docker/docker-compose.yml` **既未设 `KRONOS_ENV=production`，也未设 `KRONOS_SERVICE_SECRET`**（grep 确认）；
- **全仓（docker/ + services/ + backend/）grep `KRONOS_ENV` 零命中** —— 没有任何部署清单把它设成 production。

**后果**：在当前 compose 部署下，`KRONOS_SERVICE_SECRET` 恒为 `dev-only-service-secret-change-in-production`（一个**写进源码仓库、全网可见**的常量）。任意攻击者发一个请求：

```
GET /api/v1/.../trade/mode   Headers: X-Service-Auth: dev-only-service-secret-change-in-production
```

即拿到 `role: admin` 的 admin-equivalent 豁免 —— **AC-1 / AC-2 要堵的越权后门实际敞开**。这正是 PL 派单时点名要查的"分级 raise 是否真堵死 X-Service-Auth 越权"。机制是对的，但**只在 `KRONOS_ENV=production` 被设上时才生效，而部署侧没人设它**。

#### 修复方案（tech-lead 已裁定：两层都要做，非二选一）

> tech-lead 评估：reviewer 发现属实，且暴露 ADR-007 契约缺口（只写"KRONOS_ENV=production 即 raise"，未强制部署接线 + 未加纵深防御）。理由：仅 compose 接线把安全性绑死在"运维记得设 KRONOS_ENV"约定上，约定可被忘 / copy-paste 漏掉 / CI 跑临时 compose 又变 dev —— 资金类 admin 越权不该靠单点防线。`deps.py` 硬拒绝是 fail-closed 兜底（与 XtquantBroker"拒绝静默 fallback"同一种防御哲学）。

**A. 部署侧接线（主防线，`docker/docker-compose.yml` 所有用 kronos-auth 的服务 env 块）**：
- 加 `KRONOS_ENV=production`
- 加 `KRONOS_SERVICE_SECRET=${KRONOS_SERVICE_SECRET:?must be set}`（缺失 compose 即报错退出，与 `JWT_SECRET_KEY` / `ADMIN_PASSWORD` 同款 `:?` 强制）
- 同步 UAT 部署脚本（`/agf-deploy-uat` 走的 compose）—— 否则 UAT 栈又变 dev

**B. 代码侧纵深防御（必做，`packages/kronos-auth/kronos_auth/deps.py` + `config.py`）**：
- `config.py` 暴露布尔：`SERVICE_AUTH_ENABLED = not KRONOS_SERVICE_SECRET.startswith("dev-only-")`（即 secret 仍是 `_secret()` 的 dev fallback 时为 False）
- `deps.py:69` 守卫：`if service_auth and SERVICE_AUTH_ENABLED:` 才走 secret 比较；否则 X-Service-Auth 通道一律拒绝（fall through 到 JWT 校验 / UnauthorizedError），**不返 admin、不返 service**
- dev 下保留旧行为（`SERVICE_AUTH_ENABLED=True` 仅在 secret 已换成非 `dev-only-` 值时；本地联调若用 dev fallback 则通道关闭，迫使联调用 JWT 而非 service secret）
- **单测必加**：prod + dev-fallback secret → 带 X-Service-Auth 仍 401（这是 AC-2 的真正落地验证）

**C. AC-2 收口（C-1 修完后）**：必须在**接线后的 prod 配置**下跑 curl，断言两组都 401：① 带旧默认值 `dev-only-service-secret-change-in-production`；② 空值。**不能在 dev 配置下凑数**。这是 T-005 progress 里 ⏳ pending 的兑现条件。

#### 复审验收清单（C-1 修完后 code-reviewer 只对照这几条）

1. compose 所有 kronos-auth 服务 env 含 `KRONOS_ENV=production` + `KRONOS_SERVICE_SECRET:?`（grep 确认，UAT compose 同步）
2. `config.py` 有 `SERVICE_AUTH_ENABLED` 且语义为"secret 非 dev-only- 前缀"
3. `deps.py` X-Service-Auth 分支前有 `and SERVICE_AUTH_ENABLED` 守卫
4. 单测：prod + dev-fallback secret → 带 X-Service-Auth 断言 401（真实跑通）
5. AC-2 curl 两组（旧默认值 / 空值）在 prod 配置下均 401 的证据落 progress

**风险定级**：Critical（维持）。`role: admin` 豁免 = 资金操作（切 live 模式 / 下单 / 重置熔断）全链路无鉴权可达，且与 T-006/T-007 资金安全整改在同一攻击面。**不修不进 UAT**（UAT 栈若暴露给测试人员，dev fallback 即等于无密码 admin）。

---

## 4. SIT Audit（4 项检查 + 3 档 verdict）

| # | 检查项 | 结果 | 说明 |
|---|---|---|---|
| 1 | progress 完整性（含 `**SIT 证据**` 段） | ⚠️ 部分 | **T-002 缺 SIT 证据段**：`progress/frontend-dev-2.md` 仍是 6/12 的 T-205 旧内容，mtime `Jun 12`，**无 T-002 / AC-4 / AC-5 / AC-6 任何条目**。T-004/005（backend-dev.md）/T-006/007（backend-dev-2.md）SIT 段完整。 |
| 2 | AC 覆盖 | ✅ 主体覆盖 | 后端 T-004/005/006/007 AC 逐条列证据；前端代码改动覆盖（diff 验证 fetch→axios + 删 mock + cleanup），但因 SIT 段缺失，前端 AC-4/5/6 无逐条自验记录。 |
| 3 | 证据可信度 | ✅ 可信（独立复跑）| T-007 3 passed、T-005 14 passed、9 文件语法 OK、tsc exit 0 **均由本审查独立复现**，非"通过/OK/placeholder"。 |
| 4 | 失败/阻塞标记真实性 | ✅ 如实 | T-005 progress 把 AC-2 curl 标 `[ ] ⏳` pending（未伪装 pass），T-002 SIT 段缺失属"未提交"非"伪装"。 |

**SIT Audit verdict：⚠️ Pass with concerns**

- 主体通过：后端 4 task SIT 证据完整且可信（独立复跑印证）；代码改动质量达 UAT 前 gate。
- 两点 concern 需 PL 决定补救：
  1. **T-002 progress SIT 段缺失**（检查 #1 fail）—— 前端 AC-4/5/6 无逐条自验证据落 progress，违反 Self-Reporting Pattern。**不构成 Redo**：代码 diff 已独立验证（fetch→axios 全迁移、Diagnosis mock 删除 145 行、cleanup 在位、tsc 绿），仅缺 dev 侧文档化自验。建议：PL 派 frontend-dev-2 把 T-002 SIT 证据补进 `progress/frontend-dev-2.md`（含 AC-6 vitest 结果，见下）。
  2. **AC-6 vitest 结果 pending**：auth-flow.test.tsx 8 用例本审查后台跑中（OOM 风险点，dev 称已用 cleanup + forks pool 修复）。AC-4/5/tsc 已绿，AC-6 待 vitest 回填。

> 不触发 ❌ Redo SIT：证据缺失的是前端"文档化"层，不是测试未跑/AC 漏覆盖/虚假 pass。代码本身已达 gate。

---

## 5. 跨 task 临界区检查（compose 多 task 共改）

`docker/docker-compose.yml` 被 T-004（密码 `:?`）与 T-005（dockerfile 路径 + DATABASE_SYNC_URL）共改：

- diff 仅 1 个 hunk（`@@ -66,14 +66,15 @@ services:` backend 块），**两 task 改的是同一 backend service 的不同行**（密码行 vs dockerfile/env 行），无冲突。
- ✅ T-004 的 `JWT_SECRET_KEY:?` / `ADMIN_PASSWORD:?` + T-005 的 `DATABASE_SYNC_URL` 共存，`docker compose config` 逻辑一致（dev progress 已验证 env 缺失 exit=1）。
- ✅ T-006 / T-007 明确不碰 compose（各自从 `KRONOS_PG_URL` 派生 async URL 绕开临界区），策略正确。

**唯一遗留**：compose backend 块**未接 C-1 的 `KRONOS_ENV` / `KRONOS_SERVICE_SECRET`**（见 §3）—— 这正是要补的，属 C-1 修复范围（A 方案），非跨 task 冲突。

---

## 6. Findings 汇总

### Critical
- **C-1** [T-005 / 认证] `KRONOS_ENV=production` 部署侧未接线 → `X-Service-Auth` 验证恒用仓库内可见的 `dev-only-service-secret-change-in-production` → admin-equivalent 越权后门敞开。位置 `docker/docker-compose.yml`（缺 env）+ `packages/kronos-auth/kronos_auth/deps.py:70`（缺 dev-fallback 拒绝）。复现：`curl -H "X-Service-Auth: dev-only-service-secret-change-in-production" <any admin endpoint>` → 200 admin。修复方案（tech-lead 裁定两层都做）+ 复审验收清单见 §3。

### Warning
- **W-1** [T-006 / 审计] 4 个 handler 未传 `client_ip`，审计表 `client_ip` 列恒 NULL，削弱资金操作 IP 追溯。位置 `services/trade-service/app/routes.py:189/355/427/489`（调用 `_audit_record_safe` 未传 client_ip）。修复：注入 `request: Request` 传 `request.client.host`。
- **W-2** [T-002 / 前端] `frontend/src/` 仍有 8 处裸 `fetch(`：`contexts/AuthContext.tsx`（5 处 login/register/refresh/me/logout）、`App.tsx:112`（alert unread-count）、`hooks/useLiveTrade.ts:204`（order POST）。AC-4 若定义为"业务页全量迁移"则达标（7 页已迁），但 AuthContext 核心鉴权链与 alert 轮询仍是裸 fetch，无统一拦截器（401 刷新 / 错误处理散落）。建议明确 AC-4 边界：是否要求 AuthContext 也走 client.ts；若是，本项升 P1。
- **W-3** [T-002 / 前端 SIT] `progress/frontend-dev-2.md` 缺 T-002 SIT 证据段（mtime 仍 6/12）。见 SIT Audit 检查 #1。
- **W-4** [T-005 / 测试隔离] `packages/kronos-auth/tests/test_config_secrets.py` 与 `backend/tests/test_config_secrets.py` **同模块名 `tests.test_config_secrets`**，pytest 一次性跑两者会 `import file mismatch` 中断（本审查实测复现）。CI 若一次跑全仓测试会 fail。修复：两文件重命名唯一（如 `test_kronos_auth_config.py` / `test_backend_config.py`）或加 `__init__.py`。

### Suggestion
- **S-1** [T-007] `_check_forecast_risk` 的 `except Exception` 偏宽（见 §2 末），数据格式异常也触发暂停；可按 `OperationalError` 精确 raise，其他 warn+None。fail-safe 方向安全，可不改。
- **S-2** [T-006] `_audit_record_safe` 的 `logger.exception` 文案建议带 `fail_safe`/`audit` 结构化字段，便于日志告警按"审计写失败"单独提阈值。
- **S-3** [T-007] `_risk_engine` 无显式 `dispose()` 钩子，依赖进程退出自动 dispose；如未来引入热重载/多 worker fork，建议在 lifespan shutdown 显式 dispose。
- **S-4** [T-005] `backend/app/main.py:_run_migrations` 用 `asyncio.to_thread` 跑同步 alembic，PG 不可达时 `command.upgrade` 抛异常会冒泡中断 lifespan（符合"宁可启动失败不可带病运行"），但建议捕获后给明确日志（"alembic migrate failed, abort startup"）便于排障。

---

## 7. go / no-go for UAT — 综合判定（C-1 复审后更新）

### 结论：**CONDITIONAL GO（C-1 Resolved → 可进 UAT 部署）**

> 原 NO-GO 因 C-1（X-Service-Auth 越权后门）。C-1 经 tech-lead 裁定（两层都做）+ backend-dev 落地 + code-reviewer 最终复审（§8）已 **Resolved**。AC-2 curl 越权实测由 product-lead 裁决归 UAT 冒烟。故阶段 0 解阻，可进 UAT。

**C-1 Resolved（不再阻断）**：
- 🔴→✅ **C-1**：`X-Service-Auth` 越权后门（dev fallback = admin）。代码层双层修复落地（compose 三服务接线 + deps `SERVICE_AUTH_ENABLED` fail-closed 守卫，对齐 tech-lead 方案 B）+ 4 单测 passed（独立复跑）。核心后门在代码层已堵死，不依赖部署是否设 `KRONOS_ENV=production`。详见 §3 / §8。

**进 UAT 的条件（CONDITIONAL）**：
1. **AC-2 curl 实测（UAT 冒烟必过项）**：UAT 栈 prod-gate 接线后，带 `X-Service-Auth: dev-only-...`（旧默认值）+ 空值两组 header → 均断言 401。由 qa/deploy 在 UAT 冒烟执行（product-lead 裁决归 UAT，不在 code-review gate）。
2. **UAT compose 同步**：`/agf-deploy-uat` 走的 compose 须含 `KRONOS_ENV=production` + `KRONOS_SERVICE_SECRET:${...:?}`（deploy-engineer 核对，strategy/trade 两服务必设）。

**非阻断遗留（已排期，不卡 UAT）**：
- **W-1**（审计 client_ip 未采集）/ **W-2**（AuthContext 8 处裸 fetch 边界）：team-lead 确认留阶段 3。
- **W-3**（前端 progress 缺 T-002 SIT 段）：✅ 已补（frontend-dev-2.md 含 T-002/AC-4/5/6）。
- **W-4**（两 `test_config_secrets.py` 同名 import-mismatch）：⚠️ **仍开**——team-lead 消息称"新单测唯一名避免 mismatch"，但新文件 `test_service_auth_dev_guard.py` 唯一只防了新文件自身，**两个旧的 `test_config_secrets.py`（kronos-auth + backend）仍未重命名**，本审查实测两文件合跑仍 `import file mismatch` 中断。非阻断（单跑都绿），但 CI 全量跑会 fail，建议留 CI 修。

**已达 UAT gate 的部分（代码质量，独立复跑印证）**：
- T-007 fail-safe 语义正确（真暂停、无中性默认、schema fix 对）+ 3 passed；
- T-006 审计 4 类操作落表 + 持久化 + best-effort + 无注入，证据可信；
- T-004 import 修复 + 明文密码移除；
- T-005 认证密钥分级机制正确 + **C-1 越权后门已 Resolved**；
- T-002 前端 7 页 fetch→axios + Diagnosis mock 删除 + tsc 绿 + progress SIT 段已补。

**建议处理路径**：C-1 已闭环 → CONDITIONAL GO 进 UAT 部署（`/agf-deploy-uat`）→ UAT 冒烟实测 AC-2 curl 两组 401 → qa-engineer 跑 E2E/UAT。W-4 留 CI 修，W-1/W-2 留阶段 3。



## 8. C-1 修复复审（最终 — team-lead 正式复审请求）

> team-lead 正式请求"复审只看 C-1"后的最终复审。本次独立重新验证当前代码态（非凭上次 in-progress 记忆）：实现已对齐 tech-lead 原始方案 B（独立 SERVICE_AUTH_ENABLED 布尔），AC-2 curl 已由 product-lead 裁决归 UAT 冒烟。**C-1 复审 PASS，解阻 UAT 部署（CONDITIONAL GO）**。

**改动范围**（working tree，未 commit）：`packages/kronos-auth/kronos_auth/deps.py`(+15)、`config.py`(+45)、`docker/docker-compose.yml`(+13)、新增 `packages/kronos-auth/tests/test_service_auth_dev_guard.py`。

### 验收清单逐条核对

| # | 验收项 | 状态 | 证据 |
|---|---|---|---|
| 1 | compose 所有 kronos-auth 服务 env 含 `KRONOS_ENV=production` + `KRONOS_SERVICE_SECRET:?` | ✅ | `docker/docker-compose.yml:78-79`(backend) / `:133-134`(strategy-service) / `:181-182`(trade-service)。仅 strategy + trade 真正消费 kronos-auth（grep `from kronos_auth` 全仓仅此 2 服务），backend 多设无害。UAT compose 同步需 deploy-engineer 在 `/agf-deploy-uat` 走的 compose 核对。 |
| 2 | `config.py` 有 `SERVICE_AUTH_ENABLED` | ✅ 已对齐 tech-lead 方案 B | `config.py:53` `SERVICE_AUTH_ENABLED = not KRONOS_SERVICE_SECRET.startswith("dev-only-")`（独立布尔，正是 tech-lead 方案 B 原文）。上次 in-progress 是 startswith 内联判断的"变体"，本次复验发现已优化为独立布尔——实现与方案 B 完全一致。 |
| 3 | `deps.py` X-Service-Auth 分支前有守卫 | ✅ | `deps.py:76` `if not SERVICE_AUTH_ENABLED: logger.error(...); raise UnauthorizedError("Service auth not configured (dev fallback)")`。fail-closed（raise 不返 admin / 不 fall-through）。注释显式引用 code-reviewer 验收清单 §3-3。`require_role` 委托 `get_current_user_jwt`（:118），守卫覆盖所有调用路径。 |
| 4 | 单测：prod + dev-fallback secret → 带 X-Service-Auth 断言 401 | ✅ 独立复跑 | `test_service_auth_dev_guard.py` 4 passed（含 `test_dev_fallback_secret_rejected_even_if_value_matches`——即使 header 值完全等于 dev fallback 也 raise）。本审查用 `backend/.venv`(pytest-asyncio 1.4.0) 独立复跑确认。断言真实（`pytest.raises(UnauthorizedError, match="dev fallback")`），非虚假 pass。 |
| 5 | AC-2 curl（旧默认值 / 空值）prod 配置下 401 | 🔒 **UAT 必过门**（tech-lead + product-lead 裁决） | AC-2 是 e2e 黑盒验证，价值不在"再跑一次 401"，而在**证明部署侧接线真的激活了代码**（compose 的 `KRONOS_ENV=production` + `KRONOS_SERVICE_SECRET` 真传进容器、`_secret()` 真走真实值路径、deps 守卫真在 prod 配置生效）——这一层单测（mock env）覆盖不到。**C-1 根因恰是"代码对但部署没接线"**，故 e2e 正打根因。tech-lead 技术判定：**必须列为 UAT 冒烟必过门（fail 则 UAT 栈 NO-GO），非可选项**。deploy/qa 在 UAT 栈实测两组（旧默认 `dev-only-service-secret-change-in-production` + 空值），断言 401/403，证据落 UAT 报告。单元 4 passed 作代码层证据留 progress，e2e curl 作部署层证据落 UAT 报告，互补不替代。 |

### 复审结论 — **C-1 PASS（解阻 UAT，CONDITIONAL GO）**

- **代码层修复完整正确**（验收清单 1-4 全 ✅，独立重新复跑印证）：A 部署接线（compose 3 服务）+ B deps 硬拒绝（独立 `SERVICE_AUTH_ENABLED` 布尔 + fail-closed `raise`，完全对齐 tech-lead 方案 B）+ 4 单测 passed（含 dev fallback 值匹配也拒绝的关键用例）。核心后门（dev fallback = admin）在代码层已堵死，**不依赖部署是否设 `KRONOS_ENV=production`**——即便 compose 遗漏接线，dev fallback secret 也不能越权。
- **第 5 项 AC-2 curl** 不阻塞进 UAT 部署，但 tech-lead 技术判定为 **UAT 冒烟必过门（fail 则 UAT NO-GO，非可选项）**——因 e2e 正好验证 C-1 根因"代码对但部署接线是否真激活"。C-1 在 code-review 维度闭环，部署层验证移交 UAT（见 §7 前置条件 1）。
- **C-1 最终定级**：从 Critical 降为 **Resolved**（代码层已修 + 单测固化 + 部署接线）。不再阻断 UAT 部署。
- **非阻断遗留（供 PL 排期，阶段 3）**：W-1（审计 client_ip 未采集）/ W-2（AuthContext 8 处裸 fetch 边界）— team-lead 已确认留阶段 3，不阻断本次 UAT。
- **S-5（tech-lead 点名的唯一脆弱点，文档化即可）**：`deps.py:30-31` 的注释**单向**锁定了 `_DEV_SECRET_PREFIX` 与 `config._secret()` dev fallback 前缀的耦合（已写明"must match"），但 `config.py` 侧 dev fallback（:42/:47/:53）**缺反向注释**指向 deps.py 的常量。tech-lead 判定不值得抽共享常量（违背简单优于巧妙），但建议 backend-dev 在 config.py 那几处加反向注释"改动此前缀必须同步 deps.py:_DEV_SECRET_PREFIX，否则纵深防御失效"。非阻断，补文档即可。


---

## SIT Audit

- **verdict**: ⚠️ Pass with concerns
- **检查 #1 progress 完整性**: ⚠️ T-002 progress 缺 SIT 段（前端代码已 diff 独立验证）
- **检查 #2 AC 覆盖**: ✅ 后端 4 task 逐条覆盖；前端代码层覆盖（文档层缺自验）
- **检查 #3 证据可信度**: ✅ 独立复跑印证（T-007 3p / T-005 14p / 语法 / tsc）
- **检查 #4 失败标记真实性**: ✅ AC-2 如实标 pending，无虚假 pass
- **concern**: T-002 progress 缺段 + AC-6 vitest pending → 需 PL 决定是否要求 frontend-dev-2 补 SIT 文档；不构成 Redo

## agf-verdict

```yaml
# validate-review-verdict.sh 守门机读块
code_verdict: approve with changes
code_verdict_rationale: >
  6 task 代码质量达 UAT gate（fail-safe/审计/认证机制/前端迁移均正确且独立复跑印证）。
  C-1（X-Service-Auth 越权后门）最终复审 Resolved（§8 验收清单 1-4 ✅ + 第 5 项 AC-2 curl 由 PL 裁决归 UAT 冒烟）：
  compose 三服务接线 + deps SERVICE_AUTH_ENABLED fail-closed 守卫（完全对齐 tech-lead 方案 B）+ 4 单测 passed。
  W-3（前端 progress 缺段）已补。W-4（两 test_config_secrets.py 同名 import-mismatch）仍开——非阻断，留 CI 修。
  W-1/W-2 留阶段 3（team-lead 确认）。
sit_audit_verdict: "⚠️ Pass with concerns"
sit_audit_rationale: >
  后端 4 task SIT 证据完整可信（独立复跑印证）；T-002 progress 缺 SIT 段 + AC-6 vitest pending
  属文档/pending 非虚假证据，不构成 Redo SIT。
critical_count: 0   # C-1 Resolved (§8 最终复审)
warning_count: 3    # W-1 client_ip(阶段3) / W-2 AuthContext fetch(阶段3) / W-4 测试同名(仍开,非阻断)   # W-3 已解决
suggestion_count: 4 # S-1..S-4
go_no_go: GO (conditional)
go_no_go_rationale: "C-1 Resolved（§8 最终复审 1-4 ✅ + AC-2 curl 归 UAT 冒烟）。CONDITIONAL GO → 进 UAT 部署。条件：UAT 冒烟实测 AC-2 curl 两组（旧默认值+空值）均 401；W-4 留 CI 修（非阻断）；W-1/W-2 留阶段 3。"
blocking_findings: []   # C-1 Resolved
```
