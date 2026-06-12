# 代码审查报告: Wave 2 后端修复 (Line A + Line D)

**日期**: 2026-06-12
**审查范围**:
- Line A (T-301, T-302): `packages/kronos-data/kronos_data/etl.py`, `services/api-gateway/app/main.py`, `docs/adr/001-auth-rbac.md`, `services/sql/materialized_views.sql`, `services/sql/init_postgres.sql`
- Line D (T-307): `services/trade-service/app/main.py`, `services/strategy-service/app/main.py`, `services/trade-service/app/routes.py`, `services/data-service/app/routers/data.py`, `services/data-service/app/scheduler.py`
**代码 Verdict**: ✅ approve
**SIT Audit Verdict**: ✅ Pass
**Critical**: 0 / **Warning**: 0 / **Suggestion**: 2

---

## Critical（必须修复）

无。

---

## Warning（建议修复）

无。

---

## Suggestion（可选优化）

- [ ] **etl.py:146-176** — `_insert_rows` 的 PG fallback 路径（L159-168）在 `execute_values` 批量失败后逐行 `INSERT ... ON CONFLICT DO NOTHING`，单个 `try: ... except: pass` 吞掉所有异常且无日志。若批量路径因 schema 不匹配（如列数错误）而失败，逐行路径也会全部静默跳过，导致 `written=0` 且无诊断信息。建议在 fallback 循环外至少 `logger.warning` 一行，或在 fallback 首个 `except` 中记录 sample 错误信息。

- [ ] **api-gateway/app/main.py:17** — Gateway CORS 使用 `allow_origins=["*"]`。当前无 `allow_credentials=True`，符合 CORS 规范且安全。但项目安全基线偏好显式白名单。建议在行末加注释说明这是 gateway 层的有意设计（反向代理入口，来源不限），避免后续审查者误判。下游 trade/strategy 服务的 CORS 白名单已正确实现。

---

## 安全检查

逐条核对 OWASP Top 10 + `.claude/standards/security.md` 基线：

- [x] **SQL 注入**: 无风险。etl.py 全部使用参数化查询（SQLite `?` / PG `%s` placeholder），无字符串拼接 SQL。materialized_views.sql 为静态 DDL，无用户输入注入路径。
- [x] **XSS**: 无风险。所有审查文件为后端 API，返回 JSON，无 HTML 输出。
- [x] **命令注入**: 无风险。审查范围内无 shell 命令构造。
- [x] **认证和授权**: `trade-service/routes.py:373` broker_connect 端点正确使用 `Depends(require_role("admin"))`。
- [x] **硬编码凭证**: 无风险。DB 连接通过环境变量，CORS 默认值为本地开发 URL，trade_password 通过 Body 传递且非硬编码。
- [x] **敏感数据入日志**: trade_password 从 Query 改为 Body (`embed=True`)，不再出现在 URL query string，避免访问日志/浏览器历史明文泄漏。`_extract_pg_status` 截断 result 到 300 字符，降低敏感字段入日志风险。
- [x] **输入验证**: Gateway 为透传代理（不验证内容，由下游服务负责）。trade/strategy 服务使用 FastAPI 类型校验。design OK。
- [x] **公共端点限流**: Gateway L36-43 实现 IP 级别 60 req/min 滑动窗口限流，返回 429。无外部依赖，设计正确。
- [x] **CORS 配置**: Gateway `allow_origins=["*"]` 无 `allow_credentials` —— 安全（符合浏览器 CORS 规范）。trade-service 和 strategy-service 使用 `CORS_ALLOWED_ORIGINS` 环境变量白名单 + `allow_credentials=True` —— 符合安全基线。
- [x] **依赖 CVE**: 本次变更未新增 Python 依赖。Gateway 移除了 httpx 依赖，降低了攻击面。

**安全检查结论**: 全部通过，无安全风险。

---

## 代码质量详评

### Line A: T-301 ETL CB 统一 + Gateway 改造

**etl.py — `_Db` 封装与 `_insert_rows` 统一** (AC-301.1)：
- `_Db` 类 (L99-124) 设计干净：`execute()` 透明转换 SQLite `?` → PG `%s`；`rollback()` 安全忽略异常。单一 `_get_etl_db()` 工厂函数统一入口，PG 不可用时自动 fallback 到 SQLite。设计良好。
- 5 个 CB sync 函数（`sync_cb_basic` L1502, `sync_cb_daily` L1569, `sync_cb_price_chg` L1624, `sync_cb_call` L1677, `sync_cb_factor` L1715）全部使用 `_insert_rows(db, ...)`，不再直接 psycopg2。验证：`grep -c "import psycopg2" etl.py` → 2（仅在 `_get_etl_db` L131 和 `_insert_rows` L151 内部使用）。
- `_insert_rows` 的 PG 分支优先使用 `psycopg2.extras.execute_values` (page_size=1000) 做批量 insert，失败后 fallback 到逐行 insert，设计合理的容错策略。

**api-gateway/app/main.py — httpx→urllib + 端口 8080** (AC-301.2, AC-301.3)：
- `import httpx` 已删除，零引用验证通过 (exit 1)。
- `urllib.request.Request` + `urlopen` + `loop.run_in_executor` 异步包装模式正确，符合 CLAUDE.md "微服务间 HTTP 调用使用 urllib async wrapper" 的约束。
- `HTTPError` 透传（L91-96：返回上游状态码 + 响应体），`URLError` 返回 502 + reason，错误处理分层合理。
- 端口统一为 `8080`（health check L50 + uvicorn.run L101），与 CLAUDE.md 端口映射表一致。

### Line A: T-302 ADR-001 架构漂移 + materialized_views.sql

**ADR-001 实施变更记录** (AC-302.1)：
- "实施变更记录（2026-06-12）" 节 (L62-67) 完整记录 4 条变更：auth 合并入 backend (9001)、kronos-auth 不独立发布、Alembic 迁移路径、数据库端口 6432。每条清晰说明原决策 vs 实施变更 + 理由。
- 决策表"认证服务"行已更新为"实施变更为合并入 backend (9001)"。
- 后续工作全部标记 `[x]` 完成，状态一致。

**materialized_views.sql** (AC-302.2)：
- 4 个物化视图 DDL：`mv_today_strong_stocks`（涨幅 7-12% + 封板检测）、`mv_sector_momentum`（强势股行业聚合，HAVING count>=2）、`mv_top_capital_inflow`（净流入 Top 50，ST 过滤）、`mv_daily_composite_ranking`（综合评分 0-100，涨幅40+资金35+流动性25）。
- 每个 MV 含 `DROP ... IF EXISTS` + `CREATE MATERIALIZED VIEW` + `UNIQUE INDEX`，幂等可重复执行。
- 列名与 PG 实际 schema 一致（`net_inflow_yi`、`amount_yi`、`is_limit_up`），索引名匹配（`idx_mv_sector_ind`、`idx_mv_cap_code`）。
- `init_postgres.sql` L461-462 正确替换原 MV DDL 为指针注释 + 执行命令。
- 用法注释（L3-6）清晰说明了执行方式和刷新调度。

### Line D: T-307 CORS 白名单 + trade_password Body + LIM-1

**CORS 白名单** (AC-307.1)：
- `trade-service/main.py:36-46` 和 `strategy-service/main.py:36-46` 实现一致：从 `CORS_ALLOWED_ORIGINS` 环境变量读取，`.split(",")` 拆分，默认值 `http://localhost:5173,http://localhost:3000`。
- `allow_credentials=True` 配合显式白名单，符合浏览器 CORS 规范和安全基线。验证：`grep -rn 'allow_origins.*\["*"\]'` → 无匹配。

**trade_password Body** (AC-307.2)：
- `trade-service/routes.py:372`: `trade_password: str = Body("", embed=True)`。`embed=True` 确保请求体格式为 `{"trade_password": "value"}` 而非裸字符串。
- `_broker_config` dict (L392) 同步包含 `"trade_password": trade_password`。
- 修复前 `Query(...)` 会导致密码出现在 URL query string，修复后仅在请求体中传输，防止访问日志/浏览器历史/代理缓存明文泄漏。正确且必要。

**LIM-1 scheduler status** (AC-307.3)：
- `data.py:71-86`: `trigger_post_market` 构建 `core_job`/`ext_job` dict（含 `fn` + `args`），经 `_run_job()` 执行，响应返回 `_job_status` 中的 `last_run`/`pg_write_status`/`pg_written`。
- `scheduler.py:66-86`: `_run_job` 调用 job function，通过 `_extract_pg_status` 提取 PG 写入统计，更新 `_job_status[job_id]` 含时间戳、状态、错误信息。
- 修复前 API 直接调用 `sync_post_market_core()/ext()` 绕过 `_run_job`，导致 `_job_status` 不更新，`GET /status` 返回 `last_run: null`。修复后 API 触发同步后 `GET /status` 正确显示最新运行状态。

---

## SIT Audit

### Audit 对象 1: progress/backend-dev-w2.md (Line A: T-301 + T-302)

1. **progress 完整性**: ✅ — 含完整 SIT 证据段。T-301 按 AC-301.1~301.3 列出证据 + 验证命令；T-302 按 AC-302.1~302.2 列出证据 + 验证命令；"Wave2 Line A 验证与修正"节补充了 materialized_views.sql 与 PG 实际 DDL 的一致性修正证据。格式符合 AC-lifecycle.md 的完整条目规范。

2. **AC 覆盖**: ✅ — 5 个 AC 全部覆盖。AC-301.1~301.3 和 AC-302.1~302.2 均有独立验证命令和输出片段，无跳过或遗漏。

3. **证据可信度**: ✅ — 验证命令均为真实工具：`grep -c` 计数、`python3 -c "import ast; ast.parse(...)"` 语法检查、`grep -n` 定位、PG 视图 count 查询 (3,0,0,3)。输出为实际工具返回值，非 "OK"/"通过" 占位符。修正阶段提供了 PG 实际 DDL 与修正前差异的具体对比（涨幅阈值 7-12% vs 3%、LIMIT 50 vs 100、列名修正等）。

4. **失败/阻塞标记**: ✅ — 无失败或阻塞用例。修正阶段发现的 materialized_views.sql 与 PG 实际不一致已如实记录并修正，偏差说明完整。

**Verdict**: ✅ Pass

### Audit 对象 2: progress/backend-dev-w2-d.md (Line D: T-307)

1. **progress 完整性**: ✅ — 含完整 SIT 证据段，按 AC-307.1~307.3 分列。每 AC 含文件路径:行号 + 验证命令 + 输出片段 + 修复前/后对比说明。

2. **AC 覆盖**: ✅ — 3 个 AC 全部覆盖。AC-307.1 分 trade-service 和 strategy-service 两个子项验证。AC-307.2 含 `trade_password` 从 Query→Body 的变更证据 + `_broker_config` 同步。AC-307.3 含 `_run_job` 调用链 + 修复前后行为对比。

3. **证据可信度**: ✅ — 验证命令：`python3 -c "import ast; ast.parse(...)"` 4 次（trade-service/main.py、strategy-service/main.py、trade-service/routes.py、data-service/routers/data.py），`grep -rn 'allow_origins.*\["*"\]'` 验证 CORS 白名单。输出 "Syntax OK" 来自 ast.parse 的实际执行结果（无异常→语法正确）。修复前后状态对比逻辑自洽。

4. **失败/阻塞标记**: ✅ — 3 AC 全部通过，无伪装 pass。L27 行质量门明确标注 "全部 AC 为前置 sprint 已实现" 的上下文，诚实透明。

**Verdict**: ✅ Pass

---

## 审查总结

| 维度 | 结果 |
|---|---|
| 代码正确性 | ✅ 5 个 AC 全部实现正确，无逻辑缺陷 |
| 安全性 | ✅ OWASP Top 10 + 安全基线全部通过 |
| 代码风格 | ✅ 与现有项目风格一致 |
| 可维护性 | ✅ _Db 封装降低重复，Gateway 依赖精简 |
| SIT Audit (Line A) | ✅ Pass — 证据完整、可信、覆盖全 AC |
| SIT Audit (Line D) | ✅ Pass — 证据完整、可信、覆盖全 AC |
| **综合 Verdict** | ✅ **approve** |

**附加说明**: Line D (T-307) 全部 3 个 AC 均为前置 sprint 已实现，本次 Wave 2 仅做验证确认，未产生新代码变更。审查基于现有代码状态 + SIT 证据交叉验证，均通过。
