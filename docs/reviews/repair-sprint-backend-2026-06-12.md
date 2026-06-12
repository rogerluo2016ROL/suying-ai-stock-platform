---
reviewer: code-reviewer
code_verdict: approve
sit_audit_verdict: "✅ Pass"
critical_count: 0
warning_count: 3
suggestion_count: 3
date: 2026-06-12
scope: "T-201 data-pipeline-refactor fix, T-202 auto-trading+live-trading, T-203 kronos-auth+RBAC Phase 1"
---

# 代码审查报告: Repair Sprint — 后端 3 项修复

**日期**: 2026-06-12
**审查范围**: 12+ 文件，覆盖 data-service / trade-service / strategy-service / kronos-auth 包
**代码 Verdict**: approve（3/3 任务全部通过，零 Critical）
**SIT Audit Verdict**: Pass

---

## T-201: data-pipeline-refactor 修复包

**审查文件**: `pg_writer.py`, `stocks.py`, `scheduler.py`, `tushare.py`, `data.py`, `sync_to_pg.py`, `migrate_data.py`, `init_postgres.sql`

### AC 覆盖验证矩阵

| AC | 状态 | 验证 |
|---|---|---|
| AC-201.1 | Pass | `init_postgres.sql:407` schema 与 `scheduler.py:136-140` INSERT 列完全一致: `(code, trade_date, open, high, low, close, vol, amount, vwap)` + `UNIQUE(code, trade_date)` |
| AC-201.2 | Pass | `stocks.py:56-79` PG 写入块（注释 `PG 写入 (主路径)`）在 `stocks.py:81-93` SQLite fallback 之前；`sync_stocks_incremental` 同样 PG-first (`132-154` → `156-167`) |
| AC-201.3 | Pass | `scheduler.py:41-63` `_extract_pg_status(result)` 使用纯 dict 遍历提取 `pg_written`，零 regex；`data.py:40-46` 从结构化字段 `job["pg_written"]`/`job["pg_write_status"]` 读取 |
| AC-201.4 | Pass | `Kronos/tools/sync_to_pg.py:1` — `# LEGACY: use data-service for daily sync` |
| AC-201.5 | Pass | `pg_writer.py:151-165` `write_ths_daily()` — 交换 trade_date/ts_code 位置 + YYYYMMDD→YYYY-MM-DD + executemany；`tushare.py:254-256` `elif table=="ths_daily"` 分支 |
| AC-201.6 | Pass | `migrate_data.py:11` docstring 端口 6432 + `migrate_data.py:113` argparse default 6432；`migrate_data.py:31` TABLE_ORDER 包含 `rt_k, stk_auction_o, stk_mins, limit_list_d, ths_daily` 五表 |
| AC-201.7 | Pass | `grep -rn sync_daily_to_pg services/ packages/ Kronos/tools/` → `NO_CODE_REFERENCES_FOUND` |

### 前次 Review Findings 修复状态

| 前次 Finding | 本次状态 |
|---|---|
| #1 Write order violation (stocks.py) | **已修复** — PG 写入块在 SQLite 之前 |
| #2 ON CONFLICT strategy 不一致 | **未改** — `_pg_write` 仍用 `DO NOTHING`，对不可变日线数据合理；原始 review 标记为 Low |
| #3 Fragile regex string parsing | **已修复** — 改为结构化 dict 提取 `_extract_pg_status()` |
| #4 rate_limiter lock-sleep | **未改** — 原始 review 标记为 Low，建议 follow-up |
| #5 Unused SQLite connection (tushare.py:128,161) | **未改** — `db = sqlite3.connect(DB_PATH)` 打开后未使用就被 close；`mf_db`/`sl_db` 各自新建连接 |
| #6 Code duplication (stocks.py) | **未改** — `sync_stock_list` 与 `sync_stocks_incremental` 仍有 ~30 行重复 PG 写入逻辑 |

### T-201 Verdict: approve

P0 fix items (#1 write order + #3 regex parsing) 均已正确修复并通过 AC 验证。剩余 #4-6 为 Low 级别 follow-up 项，不阻塞合并。

---

## T-202: auto-trading + live-trading backend

**审查文件**: `auto_trading_executor.py`, `xtquant_broker.py`, `circuit_breaker.py`, `trade-service/routes.py`

### AC 覆盖验证矩阵

| AC | 状态 | 验证 |
|---|---|---|
| AC-202.1 | Pass | `auto_trading_executor.py:59` — 初始 `status: str = "stopped"`；`:118-131` — start() 三态检查: running→拒绝, paused→拒绝(提示 resume), stopped→允许 |
| AC-202.2 | Pass | `auto_trading_executor.py:272` — `daily_loss_pct = abs(daily_pnl) / strategy.capital if daily_pnl < 0 and strategy.capital > 0 else 0` |
| AC-202.3 | Pass | `xtquant_broker.py:122-126, 133-137, 144-148, 155-159` — place_order/cancel_order/get_positions/get_account 四方法均当 `_XTQUANT_AVAILABLE=True` 且 `self._trader is None` 时 `raise RuntimeError("SDK 可用但未连接，拒绝静默 fallback 到 stub")` |
| AC-202.4 | Pass | `routes.py:499` — `@router.get("/audit-logs")` 复数形式，与 DB 表名 `audit_logs` 一致 |
| AC-202.5 | Pass | `circuit_breaker.py` 完整 HALF_OPEN 状态机: `can_trade()` 允许 1 次试探订单、`record_probe()` 记录结果并驱动状态转移；`ensure_table()` + `save_to_db()` (UPSERT) + `load_from_db()` / `load_all_from_db()` 实现 DB 持久化；`routes.py:167-177,183-185` place_order 集成 `can_trade()` + `record_probe()` |

### 代码质量亮点

- **ExecutorManager 状态机设计精良**: 三态检查 + 明确错误消息（running→拒绝提示 stop、paused→拒绝提示 resume）防止操作失误
- **CircuitBreaker HALF_OPEN 实现完整**: cooldown 到期自动→HALF_OPEN，仅允许 1 次试探，probe 失败→回 TRIGGERED（重置 cooldown），成功→回 NORMAL；跨日自动复位；DB 持久化支持 crash recovery
- **错误消息清晰可操作**: XtquantBroker RuntimeError 直接指引调用 connect()，防止"静默 stub 成交"的虚假交易风险

### Warning

- [ ] `services/trade-service/app/routes.py:375` — `trade_password` 作为 Query 参数传递，标记为"(encrypted)"但未验证加密。若实际传入明文或弱加密，可能出现在访问日志/浏览器历史中。建议改为 Request Body 或 `Header` 传递

### T-202 Verdict: approve

全部 5 AC 验证通过。代码质量高，状态机逻辑清晰，错误消息明确。1 个 Warning 不影响功能正确性。

---

## T-203: kronos-auth 包 + RBAC Phase 1

**审查文件**: `packages/kronos-auth/` (6 文件新增), `trade-service/routes.py`, `strategy-service/routes.py`, `trade-service/main.py`, `strategy-service/main.py`

### AC 覆盖验证矩阵

| AC | 状态 | 验证 |
|---|---|---|
| AC-203.1 | Pass | `packages/kronos-auth/` 含 `__init__.py`, `config.py`, `deps.py`, `exceptions.py`, `pyproject.toml`, `tests/`；`pyproject.toml` 依赖 `PyJWT>=2.8, fastapi>=0.100` |
| AC-203.2 | Pass | `deps.py:40-56` `_decode_and_validate()` — HS256 解码 + `type=="access"` 校验；`deps.py:86-112` `require_role(*roles)` — `user_role = user.get("role", "")` 直接从 JWT payload 读，零 DB 查询 |
| AC-203.3 | Pass | `deps.py:68-79` — `X-Service-Auth` header 检查在 JWT Bearer 之前；有效 secret→返回 `role="admin"` 等效用户；无效→401；同时存在时 service auth 优先生效 |
| AC-203.4 | Pass | trade-service 12 端点全部加 `Depends(require_role(...))`：写操作(admin/internal_analyst/user)、mode/broker connect/circuit-breaker reset(admin only)、broker status(4 角色)、circuit-breaker GET/audit-logs(admin/internal_analyst) |
| AC-203.5 | Pass | strategy-service 22 端点全部加 `Depends(require_role(...))`：Plan CRUD 写操作(admin/internal_analyst/user)、只读端点(4 角色)、POST /optimize(admin/internal_analyst)、start/pause/resume/stop(admin/internal_analyst/user)、status/log(4 角色) |
| AC-203.6 | Pass | SIT 证据含 Python 内联测试: 有效 token→200(payload 解码成功)、过期 token→401(ExpiredSignatureError)、错 role→403 |
| AC-203.7 | Pass | `packages/kronos-auth/tests/test_deps.py` — 18/18 通过，覆盖: 有效 token(2)、错 role(2)、缺 token(4)、过期 token(2)、X-Service-Auth(3)、refresh 拒绝(1)、篡改拒绝(1)、service auth 覆盖 JWT(1)、multi-role(1)、open route(1) |

### 代码质量亮点

- **包设计简洁且职责清晰**: `config.py`(env→配置) / `deps.py`(FastAPI Depends) / `exceptions.py`(HTTPException) — 三层分离，无冗余
- **`require_role` 工厂模式优雅**: 可变参数 `*roles` 让调用方直接写 `require_role("admin", "internal_analyst")`，语义清晰
- **X-Service-Auth 豁免逻辑正确**: 在 `get_current_user_jwt` 最前面检查，确保 service-to-service 调用不受 JWT 过期影响
- **测试覆盖全面**: 18 用例覆盖 happy path + edge cases + 安全边界（篡改/过期/refresh type/双 header），FastAPI TestClient 用法规范

### Warning

- [ ] `packages/kronos-auth/kronos_auth/config.py:10-13` — `KRONOS_SERVICE_SECRET` 默认值 `"dev-service-secret-change-in-production"` 是硬编码回退值。虽然与 `JWT_SECRET_KEY` 默认值模式一致，但 service auth 豁免赋予 admin 等效权限，若生产环境忘记设置环境变量，任何知道该默认值的微服务都可通过 X-Service-Auth 获得 admin 权限。建议: (a) 生产部署文档中明确标注必须设置 `KRONOS_SERVICE_SECRET`，或 (b) 当检测到仍为默认值时拒绝启动

- [ ] `services/trade-service/app/main.py:36` / `services/strategy-service/app/main.py:36` — `allow_origins=["*"]` 搭配 `allow_credentials=True` 违反 `.claude/standards/security.md` 第 9 条 CORS 基线。该问题在 RBAC 集成前已存在，但 RBAC 保护后凭证泄露影响面扩大。建议后续统一改为配置驱动的白名单

### Suggestion

- [ ] `packages/kronos-auth/kronos_auth/deps.py:76` — service auth 合成用户 `"jti": ""` 为空字符串。下游 auditing 代码如果依赖 jti 做操作去重/追踪，空 jti 可能导致日志无法关联。建议使用固定格式 `f"svc-{uuid4().hex[:8]}"` 标识服务调用

### T-203 Verdict: approve

全部 7 AC 验证通过。包设计简洁，测试覆盖全面，RBAC 集成无遗漏。2 个 Warning 不影响功能正确性，建议 follow-up 处理。

---

## 安全检查

按 `.claude/standards/security.md` 逐条核对：

| # | 检查项 | T-201 | T-202 | T-203 |
|---|---|---|---|---|
| 1 | SQL 注入 | Pass — `_pg_write` 使用 `%s` 参数化 + `executemany`；`circuit_breaker.py` 使用 `:named_params` | Pass | N/A (auth 包无 SQL) |
| 2 | XSS | N/A (纯后端) | N/A | N/A |
| 3 | 命令注入 | Pass — 无 shell 命令调用 | Pass | Pass |
| 4 | 认证授权 | Pass — 无新增端点 | Pass — 新增端点有 `require_role` | Pass — 全部端点均加 RBAC |
| 5 | 硬编码凭证 | Pass — PG_URL 从 env 读取(有 fallback default) | Pass | **Warning** — `KRONOS_SERVICE_SECRET` 有 dev 回退值 |
| 6 | 敏感数据日志 | Pass — logger.debug 级别 | Pass — `trade_password` 未直接日志输出 | Pass |
| 7 | 输入验证 | Pass — FastAPI Query 参数验证 | Pass — FastAPI Query/Body 验证 | Pass — FastAPI 依赖注入验证 |
| 8 | 限流 | Pass — `rate_limiter.py` 400次/分钟 | Pass — 无公开暴力端点 | Pass |
| 9 | CORS | N/A | **Warning** — pre-existing `*` + `credentials=True` | **Warning** — pre-existing `*` + `credentials=True` |
| 10 | 依赖 CVE | Pass — 无新增依赖 | Pass — 无新增依赖 | Pass — `PyJWT>=2.8` 是现有依赖 |

---

## SIT Audit

**Audit 对象**: `progress/backend-dev-1.md`, `progress/backend-dev-2.md`, `progress/backend-dev-3.md`

### Audit 结果

| 检查项 | backend-dev-1 (T-201) | backend-dev-2 (T-202) | backend-dev-3 (T-203) |
|---|---|---|---|
| 1. progress 完整性 | Pass — 含 7 AC `[x]/[ ]` 内联 + 验证命令 + 位置引用 | Pass — 含 5 AC 分节 + `[x]` 勾选 | Pass — 含 7 AC 分节 + Python 内联测试 + pytest 输出 |
| 2. AC 覆盖 | Pass — 全部 7 AC 覆盖，无遗漏 | Pass — 全部 5 AC 覆盖 | Pass — 全部 7 AC 覆盖 |
| 3. 证据可信度 | Pass — diff/grep/ast.parse 真实命令输出 | Pass — Python syntax check + 行号引用，可定位验证 | Pass — pytest 18/18 真实输出 + Python 内联断言验证 |
| 4. 失败/阻塞标记 | Pass — 无 fail 用例（全部 pass） | Pass — 无 fail 用例（全部 pass） | Pass — 无 fail 用例；AC-203.6 标记"需 product-lead 协调重启"属合理依赖声明 |

### SIT Audit Verdict: Pass

三个 progress 文件均具备完整的 SIT 证据段，AC 覆盖无遗漏，证据来自 diff/grep/ast.parse/pytest 等真实工具输出，可信度高。

---

## 总体评估

| Task | 代码 Verdict | SIT Audit | Critical | Warning | Suggestion |
|---|---|---|---|---|---|
| T-201 data-pipeline-refactor fix | approve | Pass | 0 | 0 | 3 |
| T-202 auto-trading+live-trading | approve | Pass | 0 | 1 | 0 |
| T-203 kronos-auth+RBAC | approve | Pass | 0 | 2 | 1 |

**综合 Verdict**: **approve** — 三个 Task 全部通过，零 Critical。Warning 均为 follow-up 级别，不阻塞合并。建议在下次 sprint 统一处理 CORS 白名单和安全默认值问题。

---

## Changelog

- 2026-06-12: 初始审查 — T-201/T-202/T-203 三项修复包
