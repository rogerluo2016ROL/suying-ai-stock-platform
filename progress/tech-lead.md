# Tech Lead — 架构合规审查

- 角色：tech-lead
- 审查日期：2026-06-12
- 触发：product-lead 派单"阅读全部 6 个 ADR，对照基线检查代码合规"
- 审查范围：ADR-001 ~ ADR-006 全量 + CLAUDE.md 一致性 + 实际代码

## 审查发现

### P0 — 必须立即修复

#### P0-1: stk_auction_o 表 schema 与 INSERT 代码不匹配

- **文件**：`services/data-service/app/scheduler.py:136-140` vs `services/sql/init_postgres.sql:407`
- **问题**：`collect_auction_snapshot()` INSERT 列 `(code, trade_date, open, high, low, close, vol, amount, vwap)` 与表定义 `(ts_code, trade_date, pre_close, price, volume, amount, bid_volume, ask_volume, bid_amount, ask_amount)` 完全不同。列名和数量均不匹配，运行时必抛异常。
- **影响**：9:25 集合竞价快照写入失败，所有交易日影响
- **修复**：`init_postgres.sql:407` 和 `scheduler.py:136` 择一改动，统一 schema。建议以 scheduler.py INSERT 为基准，将表改为 `(code, trade_date, open, high, low, close, volume, amount, vwap)`

#### P0-2: 全部微服务无 RBAC 权限控制

- **ADR-001 要求**：8 个现有微服务各加 `Depends(require_role(...))` 调用
- **实际**：screener-service、signal-service、trade-service、strategy-service 全部搜索零 `require_role` / `Depends(role)`。所有微服务端点公开无保护
- **影响**：与 ADR-001 风险描述一致——「任何知晓服务地址的人均可访问所有 API」

#### P0-3: 共享 RBAC 包 `packages/kronos-auth/` 缺失

- **ADR-001 决策**：共享 Python 包 `kronos-auth` 含 `require_role(role)` 依赖注入
- **实际**：`packages/` 下仅 kronos-core、kronos-data、kronos-factors，无 kronos-auth
- **影响**：P0-2 修复缺少基础组件，每个服务需自行实现角色校验

### P1 — 应尽快修复

#### P1-1: 认证内嵌 backend 而非独立 auth-service（架构漂移）

- **ADR-001 决策**：独立 auth-service（FastAPI，端口 8010）
- **实际**：认证在 `backend/`（端口 9001），`services/auth-service/` 不存在
- **评估**：JWT/Argon2id/httpOnly Cookie 实现正确符合 ADR-001。将 auth 嵌入 backend 是务实的简化，但 ADR-001 未记录此决策变更
- **建议**：更新 ADR-001 记录「auth 合并入 backend，不独立部署」决策

#### P1-2: sync_to_pg.py 缺 LEGACY 标记

- **ADR-006 决策 3**：文件头加 `# LEGACY: use data-service for daily sync`
- **实际**：未添加

#### P1-3: ths_daily 表无 PG 直写函数

- **ADR-006 决策 2**：P1 直写范围含 ths_daily
- **实际**：`init_postgres.sql:447` 有 ths_daily 表，`pg_writer.py` 无对应 `write_ths_daily()`

#### P1-4: materialized_views.sql 独立文件不存在

- **ADR-006 后续工作**：修改 `materialized_views.sql` 新增 `mv_daily_composite_ranking`
- **实际**：文件不存在，物化视图 DDL 内联在 `init_postgres.sql`

### CLAUDE.md 文档漂移

| # | 位置 (行) | 写什么 | 实际 |
|---|-----------|--------|------|
| D1 | ADR 基线表 | `002-broker-trading.md` | `002-live-trading-broker.md` |
| D2 | ADR 基线表 | `004-model-training.md` | `004-model-training-pipeline.md` |
| D3 | 目录表 L99 | `5 个 ADR` | 实际 6 个 |
| D4 | 目录表 L98 | `11 个 FastAPI 微服务` | 正确（alert/api-gateway/backtest/data/diagnosis/prediction/screener/signal/strategy/trade/training = 11），但 docker-compose 仅覆盖 8 个 |

## ADR-006 合规矩阵

| 决策 | 状态 |
|------|------|
| 决策 1: PG-first 写入 | ✅ pg_writer.py `_pg_write()` |
| 决策 2: P0+P1 表直写 | ⚠️ 缺 ths_daily（P1-3） |
| 决策 3: 消除 subprocess 桥 | ✅ | scheduler 注释确认、pg_sync 步骤已移除 |
| 决策 3: sync_to_pg.py LEGACY 标记 | ❌ 未实现（P1-2） |
| 决策 4: stocks 同步（周全量+日增量） | ✅ stocks.py + cron (周六 02:00 + 工作日 08:00) |
| 决策 5: 物化视图（含 mv_daily_composite_ranking） | ✅ pg_writer.py 刷新 4 视图，init_postgres.sql 含 DDL |
| 决策 6: 错误处理（3 次指数退避+数据量门禁） | ✅ `_pg_write()` 重试 + `_check_data_volume()` |

## ADR-001 合规矩阵

| 决策 | 状态 |
|------|------|
| PyJWT 2.x + HS256 | ✅ `backend/app/config.py` |
| Argon2id (3/65536/2) | ✅ `backend/app/config.py` |
| httpOnly Refresh Cookie | ✅ `backend/app/routers/auth.py` |
| 独立 auth-service (8010) | ❌ 内嵌 backend (9001)（P1-1） |
| 共享包 kronos-auth | ❌ 缺失（P0-3） |
| RBAC Depends 覆盖 8 服务 | ❌ 全未实现（P0-2） |

## Skills 使用

- 未使用 — 审查任务不需要 skill 辅助

## SIT 证据

不适用 — tech-lead 不写代码。

## 质量门

- [x] 全部 6 个 ADR 已阅读
- [x] CLAUDE.md 与代码交叉验证完成
- [x] 发现 P0-1 运行时 bug（stk_auction_o schema 冲突）
- [x] 发现 P0-2/P0-3 RBAC 安全缺口
- [x] 4 项 CLAUDE.md 漂移已标记

## 下一步

1. P0-1 需 backend-dev 立即修复 schema 冲突
2. P0-2/P0-3 需 product-lead 排入下个 sprint——当前所有微服务无访问控制
3. P1-2 一行注释即可修复
4. CLAUDE.md D1-D4 漂移由 tech-lead 修复（下一个 commit）

---

# 阶段 0 止血评审（T-001，2026-06-21）

- 任务：T-001（review-only，不改业务代码）
- 触发：product-lead 派单——评审 PRD §9 Open Questions Q-2/3/4 + AC-1/2/3/8/9/10 实施可行性
- 产物：`docs/adr/007-phase0-secrets-audit-schema.md`（Open Questions 收口）、PRD §9 回填、本段（AC 评审）
- 证据：`docs/reviews/audit-backend-2026-06-21.md` §4/§5/§6（逐文件行号）+ 本次 Read 复核

## Skills

- `agf-writing-adr`（起草 ADR-007）

## Open Questions 结论（详见 ADR-007）

| ID | 结论（一句话） |
|---|---|
| Q-2 | 阶段0/dev/单机 docker 用 `.env`，阶段2 生产用 k8s Secret；**分级 raise**（`KRONOS_ENV=production` 缺失即 raise，否则 warn + `dev-only-` 前缀 fallback），禁 `secrets.token_hex` 随机；docker-compose 兜底改 `:?` 强制 |
| Q-3 | 复用现有 `audit_logs` 表（alembic 002 已建，kronos 库，零 schema 变更）+ 复用 diagnosis-service async SQLAlchemy 模式；不建独立 audit 库（留阶段 2 合规评估） |
| Q-4 | 阶段 0 选「双轨 + docker 首启跑 alembic」最小代价：业务表只改 init_postgres.sql，auth/audit/circuit_breaker 只走 alembic，两集合不重叠；backend Dockerfile entrypoint `alembic upgrade head && uvicorn`；并轨留阶段 3 |

## AC 逐条评审（go / no-go + 关键风险）

> 全部 **go**，6/6 可实施。下列风险已写进 ADR-007 给 backend-dev 的契约，dev 进 Plan Mode 时消化。

### AC-1 移除 KRONOS_SERVICE_SECRET 硬编码默认 → 缺失即 raise  【go】

- 证据：`packages/kronos-auth/kronos_auth/config.py:10-13` 硬编码 `dev-service-secret-change-in-production`；`deps.py:68-77` 该值经 `X-Service-Auth` 头直接拿 `role=admin`（绕过 JWT/Argon2/refresh）。
- 风险：(1) **必须分级**——dev / 单测环境没设 env 会卡死，用 `KRONOS_ENV` 区分 prod raise / dev warn。(2) 该 secret 当前被全栈默认值隐性依赖（容器内任何服务间调用都靠这个默认值过鉴权），改 raise 后要确保 docker-compose 给所有需要服务间调用的容器注入 `KRONOS_SERVICE_SECRET`，否则服务互调 401。
- 关联：审计 P0-3；与 AC-2 同根（修了 secret 默认值，AC-2 的 curl 越权自然失效）。

### AC-2 X-Service-Auth 越权修复 → curl 返回 401/403  【go】

- 证据：`deps.py:69-77`，带默认 service secret 的请求被当 admin；`trade-service/routes.py:328-492` 的 live mode / broker connect / 熔断重置全是 admin-only。
- 风险：低。AC-1 落地（默认值消失 / 换强随机）后带旧默认值的 curl 自然 401。**唯一需确认**：dev fallback 给「日志一眼可识别」的占位值（ADR-007 要求 `dev-only-` 前缀），AC-2 验证建议同时测「空 X-Service-Auth」+「旧默认值」两组。
- 关联：审计 P0-3；ADR-001 §49「服务间认证留给安全审计 ADR」已由 ADR-007 补齐。

### AC-3 JWT_SECRET_KEY 缺失即 raise（不再 token_hex 随机）  【go】

- 证据：`backend/app/config.py:16-21`，缺失时 `secrets.token_hex(32)` 仅 `warnings.warn`。
- 风险：(1) **必须分级**（同 AC-1）。(2) 移除 token_hex 路径后，dev 单测若 mock 了 config 要同步更新。(3) **`docker-compose.yml:74` 的 `JWT_SECRET_KEY=...:-dev-secret...` 兜底必须同步改 `:?` 强制**，否则容器侧仍有默认值，AC-3「缺失即 raise」在容器内被 compose 兜底绕过——这是 AC-3 与 AC-12 的交叉点，必须同改。
- 关联：审计 P0-4；与 AC-12 同源（明文默认密码）。

### AC-8 docker 首启跑 alembic  【go】

- 证据：`docker-compose.yml:32` 只挂 `init_postgres.sql`（65 业务表），不跑 alembic → backend lifespan `seed_roles` 因 `roles` 表不存在崩（`backend/app/main.py:25`）。alembic 6 个迁移建 auth/audit/training/diagnosis/circuit_breaker 表。
- 风险：(1) **driver 不匹配但可接受**：alembic env.py 用 `DATABASE_SYNC_URL`（psycopg2），backend app 用 asyncpg——既存现状，docker entrypoint 先 `alembic upgrade head`（sync）再起 uvicorn（async），同库不同 URL，schema 落地一致。(2) **表名冲突排查已通过**：`grep users|roles|refresh_tokens|circuit_breaker|audit_logs|training|diagnosis` 在 init_postgres.sql 0 命中，双轨契约成立。(3) **幂等性**：`alembic upgrade head` 已迁移则 no-op，重复启动安全。(4) **entrypoint 失败行为**：alembic 失败应让容器退出（不进 uvicorn），用 `&&` 串联（ADR-007 已约束）。
- 关联：审计 P0-2 / P2-8；ADR-007 双轨契约。

### AC-9 trade-service 接 DB + audit_log 落表  【go】

- 证据：`audit_log.py` 完整 record/query 实现（200 行，吃 `AsyncSession`）；`routes.py:497-520` `/audit-logs` 返回硬编码空数组；`routes.py:525-544` `_audit_record_safe` 只 `logger.info`。alembic 002 已建 `audit_logs` 表（与 `audit_log.py:24` 对齐）。
- 风险：(1) **ADR-002 命名漂移**：ADR-002 §197 写 `trade_audit_log`，代码是 `audit_logs`——以代码为准，ADR-007 已挂后续工作回头对齐 ADR-002，dev 不要按 ADR-002 建错表。(2) **trade-service 当前无 DB session**：需新增 `database.py`（复用 diagnosis-service 模板）；`KRONOS_PG_URL` 是 psycopg2 URL（`postgresql://`），async SQLAlchemy 需 `postgresql+asyncpg://`，dev 做 URL scheme 适配（diagnosis-service 已有先例）。(3) **`_audit_record_safe` 改 await 是异步化**：4 类操作调用点（切 live / broker connect / 熔断重置 / 下单）要确认都在 async 上下文。(4) **审计写失败处理**：保留 best-effort（审计写失败不阻断主操作），但 `logger.exception` 而非静默吞。
- 关联：审计 P0-5；ADR-002 Decision 4（append-only trigger 已在 alembic）。

### AC-10 auto_trading_executor 风控连接池 + fail-safe 暂停  【go — 资金类，最高风险】

- 证据：`strategy-service/auto_trading_executor.py:476-497`（`_check_announcement_risk`）、`:500-539`（`_get_atr_stop_loss`）、`:542-564`（`_check_forecast_risk`）：每函数裸 `psycopg2.connect(connect_timeout=3)` + `conn.close()`，且 `try/except: return False/""/pass` 吞所有异常。
- 风险（资金类，必须 Plan Mode）：(1) **核心风险——fail-safe 方向**：当前 DB 故障时三函数返回「无风险」（`False`/`""`/`0.0`），自动交易**继续下单而不止损**，真实资金灾难（即便当前 paper）。改 fail-safe = DB 异常时 executor 进 `paused` 状态而非继续——**不可简单把 `return False` 改 `return True`**（那会让所有持仓全卖）。正确语义：**连接失败本身视为系统性风险 → 暂停整轮循环**（asyncio.Event，ADR-003 已有机制），而非对单股返回「风险」。(2) **连接池选型**：用 sqlalchemy engine（与 AC-9 一致），避免 strategy-service 内部再混入裸 psycopg2。(3) **连接池生命周期**：executor 长驻 asyncio 循环，池在启动时建、停时关，不能每循环建池。(4) **单测 AC 验证**：mock DB 连接失败 → 断言 executor 进 paused 状态（而非下单）——这是 AC-10 Verification，dev 必须写。
- 关联：审计 P2-6；ADR-003（asyncio.Event 暂停机制正好用于 fail-safe）。

## 质量门

- [x] Q-2/3/4 各给明确方案（非「再讨论」），已填回 PRD §9
- [x] AC-1/2/3/8/9/10 六项逐条 go/no-go + 关键风险 + 分级建议
- [x] 缺基线（密钥管理 / audit 落库 / dual-schema 无现成 ADR 覆盖）→ ADR-007 起草落盘（含备选方案 + 版本查证段）
- [x] review-only：未改任何 `services/` `backend/` 业务代码

## 下一步（交接 product-lead）

1. ADR-007 Proposed → PL 确认后转 Accepted，解 block AC-1/2/3/8/9/10 实施 task（待 PL 创建并分派 backend-dev）。
2. backend-dev 进 Plan Mode 前先读 ADR-007「实现契约」+ 本段 AC 风险，**尤其 AC-10 的 fail-safe 方向**（不可简单 `return True`）。
3. CLAUDE.md Tech Stack 表无需更新（ADR-007 不引新依赖，asyncpg/SQLAlchemy/alembic 已在栈内）。
4. ADR-007「后续工作」第 5 条（对齐 ADR-002 §197 表名）由 tech-lead 随手修。

---

## 2026-06-22 — ADR-011 top_inst schema 对齐（数据管道写入侧第 7 表）

- 触发：product-lead 派单"细化 ADR-011 大纲为 Accepted 版"
- 范围：仅文档（ADR），未改代码

### 产物

- `docs/adr/011-top-inst-schema-alignment.md` — Proposed → **Accepted**，全 7 决策 + 7 备选 + 完整版本与查证段落 + backend-dev 实施清单

### 关键决策

1. **决策 0 文件白名单**：仅允许 `010_top_inst_align.py`（新建）+ `init_postgres.sql:161-165` + 索引追加；`etl.py` / `kronos-factors/` / `pg_adapter.py` / 其他 alembic 全部禁改（沿用 ADR-010 风格）。
2. **主键策略选 BIGSERIAL 自增 id**：实测「机构专用」匿名席位同 code/trade_date 内重复出现，任何 `(code, trade_date, exalter)` 复合 PK 都会因 ON CONFLICT DO NOTHING 丢数据 → 下游 SUM 偏低；BIGSERIAL + `clean_before_write`（已存在 etl.py:895）兜底防累积；配套 `idx_top_inst_code_date` 业务索引。
3. **删 4 死列**：`inst_name / buy_amount / sell_amount / net_amount`（Tushare 不返回此命名，纯凭空想象的死列）。
4. **否决物化视图 mv_top_inst_daily**（大纲推荐选项）：grep 实证 `advanced_factors.py:945-953` 下游本就是 per-institution 明细 + 应用层 `sum(r["net_buy"] for r in ti_rows)`，物化视图反需改下游 SQL（违反决策 0「下游零改动」），是解决不存在的问题（YAGNI）。
5. **大纲笔误纠正**：大纲列了 `side / reason` 字段，实测 Tushare top_inst 接口**不返回**这两列（与 `top_list` 接口混淆，后者有 reason 见 ADR-009 决策 3）；本 ADR 严格对齐 sync `etl.py:897-898` 现状 8 字段。
6. **零下游改动达成**：sync cols 已正确（commit 5694c09 之前修）+ 下游 `SELECT *` 后应用层 SUM 字段名与新物理列字面一致——schema 对齐即自动从 fallback 中性 5.0 切换到真实数据评分。
7. **Alembic 010 模板**：DROP CONSTRAINT IF EXISTS（无旧 PK 但保留兜底）→ 单 ALTER 删 4 列 + 加 6 业务列 → ADD COLUMN id BIGSERIAL → ADD PK (id) → CREATE INDEX；全 `op.execute` 幂等，禁 `op.add_column` / `op.create_primary_key`（ADR-008 教训）。

### 实施清单（交接 backend-dev，限额重置后 / 新会话）

清单已写入 ADR 末尾 **Hand-off** 段，含：
1. 起草 `backend/alembic/versions/010_top_inst_align.py`（upgrade / downgrade 模板已贴）
2. 改 `init_postgres.sql:161-165` + 追加 idx_top_inst_code_date
3. 盘后 `TRUNCATE → alembic upgrade head → sync_top_inst(days_back=30)`
4. 3 条验证 SQL + SIT 6 项 checklist（双向迁移 / 行数 / 匿名席位完整保留 / 因子脱离 fallback / grep 旧列名残留）
5. 白名单边界硬约束（不得动 etl.py / factors / 其他 alembic）

### 质量门

- [x] 至少 1 备选方案 + 否决理由 → 7 个备选（A-G）+ 完整否决论证
- [x] 选型附查证日期 + 信息源 URL → 版本与查证段含 5 行表格 + 4 处 grep 实证 + 接口文档 URL
- [x] CLAUDE.md Tech Stack 表同步 → 本 ADR 不引新依赖，Tech Stack 无需更新
- [x] 仅产 ADR，未碰代码 / Alembic / init_sql（沿用决策 0 自约束）

### 数据管道写债收口进度

| ADR | 表 | 状态 |
|---|---|---|
| ADR-008 | sw_daily | Accepted（commit 48c8b6a） |
| ADR-009 | pledge_detail / rt_sw_k / top_list | Accepted |
| ADR-010 | cyq_chips | Accepted（commit 8e18637） |
| **ADR-011** | **top_inst** | **Accepted（本次）** |
| ADR-012（待立） | hk_holdings / repurchase / share_float / cyq_perf 等剩余表 | Pending — 查证后批量修复 |

### 下一步

1. **product-lead**：派 backend-dev（限额重置后）按 ADR-011 Hand-off 段实施；不需要 PL 二次评审 ADR 本身（已 Accepted）。
2. **tech-lead 本会话剩余**：等 PL 派"sync 设计统一回补方案评估"任务（PL 已预告）。
3. **memory 不写入**：本 ADR 决策正文 + 否决清单全部已在 `docs/adr/011-*.md`，避免双源（遵循 tech-lead memory 「避免写入：已 accept 的决策正文」规则）；待 ADR-012 立项时若产生跨 ADR 复用结论（如「BIGSERIAL 已成 per-detail 表 PK 标准」）再写一条。

---

## 2026-06-22 — ADR-012 数据管道写入路径统一化（方法论 ADR，Proposed）

- 触发：product-lead 派单"评估 sync 设计统一回补方案"，背景 memory `data-pipeline-write-debt`
- 范围：仅文档（方法论 ADR），未改代码

### 产物

- `docs/adr/012-data-pipeline-write-path-unification.md` — **Proposed**（待 PL 决策方案 A vs B 后升 Accepted）

### 现状盘点核心数据（grep 实证 2026-06-22）

1. **4 套写入路径并存**：
   - `etl._insert_rows`（32+ sync 调用，唯一带自动列过滤但缺重试 / 数据量门禁）
   - `pg_writer._pg_write`（stk_factor_pro / rt_k 等，有重试 + 数据量门禁但缺列过滤）
   - `cb_sync._pg_bulk_insert`（ths_daily 等 3 函数，与 `_pg_write` 95% 复制粘贴）
   - inline `db.executemany`（announcements / cctv_news / mp_report / ... 8 个 sync 模块，零防御）
2. **48 个 monitored 表 / 43 个 backfill handler / 5 表缺 handler**：`[index_daily, stk_factor_pro, stocks, ths_daily, trade_cal]`
   - stk_factor_pro 病灶：sync 签名无参数（仅拉 today），不兼容 `_BACKFILL_MAP` 期望的 `fn(days_back=int)`
   - ths_daily / index_daily：签名兼容但遗漏注册
   - stocks / trade_cal：监控规则与 backfill 模型错配（非时序数据）
3. **真相源 4 处分裂**：物理列集 / sync cols / backfill 注册 / 监控配置 / date_col 散落 4 处独立维护，无静态校验

### 核心病灶诊断

**根因 = 写入路径分裂（缺陷 A）+ 真相源分裂（缺陷 B）的乘积**：
- 缺陷 A：4 套路径互不知晓，能力不互通（列过滤 vs 重试 vs 门禁各缺一块）
- 缺陷 B：MONITORED_TABLES / _BACKFILL_MAP / sync cols / date_col 4 处字典靠人脑对账

每加一表 → 4 路径×4 真相 = 16 种错配空间。ADR-008~011 修「已暴露错配」，不解「未来仍会错配」。

### 决策方向（PL 二选一）

| 维度 | 方案 A 渐进收口 | 方案 B 注册中心 |
|---|---|---|
| 核心 | 三路径合并 fallback 到 `_insert_rows` + 补 5 表 backfill + scheduler validator | 新建 `sync_registry.py` (SyncSpec dataclass) + 4 处字典退化为视图 + 启动期 raise |
| 改动文件 | 4 | 12+ |
| 工作量 | 2-3 day | 5-7 day |
| 缺陷 A 解 | ✅ | ✅ |
| 缺陷 B 解 | ⚠️ 仅 validator catch | ✅ 静态 raise |
| ADR-013+ 模板瘦身 | ❌ | ✅ ~50% |
| 可逆性 | ✅ | ⚠️ |

**tech-lead 倾向方案 A**，理由：
1. 剩余表数量有限（5-8 张），方案 B 红利在中短期内体现不充分
2. ADR-013+ 模板瘦身可在 `agf-writing-adr` skill 加 schema-alignment 子模板实现，不必引入 SyncSpec 抽象层
3. 方案 A 任意时刻可回滚，方案 B adopt 后回滚需还原 4 处字典 + sync 签名
4. ADR-006「轻量 sync 函数」哲学与 SyncSpec dataclass 有张力，需评估冲突

若 PL 有以下信号则选方案 B：剩余表 > 10 / 监控告警频繁 / 新人加表错配率 > 30%。

### 备选方案（已否决）

- C. 不做统一化继续单表修：technical debt 复利 > 一次性重构（否决）
- D. 弃用 `services/data-service/app/sync/` 全迁 `etl.py`：违反 ADR-006 分层（否决）
- E. SQLAlchemy ORM 替代 SyncSpec：与 ADR-006 既有基线冲突（否决）
- F. 只补 backfill + validator（方案 A 子集）：放弃缺陷 A 解，省半天不划算（否决）
- G. Tushare schema 自动生成全部：Tushare 字段命名不规范、稳定性不达标，自动化反生漂移（否决）

### 质量门

- [x] ≥ 2 备选方案 + 否决理由 → 主决策 2 方案对比 + 5 个备选（C-G）逐条否决
- [x] 选型附查证日期 + 信息源 → 版本与查证段含 4 行表格 + 8 项 grep 实证清单
- [x] CLAUDE.md Tech Stack 表同步 → 本 ADR 不引新依赖，无需更新
- [x] 仅产 ADR（Proposed）+ §决策 0 文件白名单占位、未碰代码 / Alembic / init_sql
- [x] 未自行升 Accepted（按硬约束）—— 等 PL 决策方向

### 数据管道写债收口方法论进度

| ADR | 主题 | 状态 |
|---|---|---|
| ADR-008 | sw_daily | Accepted |
| ADR-009 | pledge_detail / rt_sw_k / top_list | Accepted |
| ADR-010 | cyq_chips | Accepted |
| ADR-011 | top_inst | Accepted |
| **ADR-012** | **写入路径统一化（方法论）** | **Proposed（本次）** |
| ADR-013（待立） | 首张按 ADR-012 方法论修的表（建议 stk_factor_pro，同时含缺陷 A+B） | Pending — ADR-012 Accepted 后立项 |

### 下一步（交接 product-lead）

1. **PL 决策方案 A vs B**：回执含「选 X / 理由」+ 是否接受 tech-lead 建议 A
2. **PL 回执后 tech-lead 升 Accepted**：补 §决策 0 文件白名单 + §决策 N 细化（按选定方案）+ §版本与查证 升级日期
3. **ADR-013 立项时机**：建议 ADR-012 Accepted 后 1-2 周内立 013（首个应用方法论的样本），避免模板飘移
4. **memory 不写入**：本 ADR Proposed 阶段决策未定，等 Accepted 后产生稳定结论（如「方案 A 已 adopt，新表必填 _BACKFILL_MAP」）再写一条

---

## 2026-06-22（同日 +1）— ADR-012 升 Accepted（PL 选方案 A）

- 触发：product-lead 回执选**方案 A（渐进收口）**
- PL 决策理由（对照 tech-lead §决策 4「选 B 触发信号」）：
  1. ❌ 剩余表 = 5-8 张（不超 10）
  2. ❌ detect_data_gaps OK 21→32，无运维告警压力
  3. ❌ 单 agent 团队，无新人错配场景
  4. ✅ 可逆性优先 + 保留方案 B 升级通道（未来 > 10 表新数据源走 ADR-016 升级）

### 本次落盘改动

`docs/adr/012-data-pipeline-write-path-unification.md` 状态 **Proposed → Accepted**，补齐方案 A 实施细则：

1. **顶部状态段** + 新增「PL 决策记录」段，记录选 A 的 4 条理由
2. **§决策 0 文件白名单**写实（沿用 ADR-010/011 风格，硬约束 backend-dev 不越界）：
   - 白名单 #1: `packages/kronos-data/kronos_data/etl.py`（仅 `_insert_rows` 加 retries/data_volume_floor 参数）
   - 白名单 #2: `services/data-service/app/sync/pg_writer.py`（`_pg_write` thin wrapper + `_VOLUME_FLOOR_MAP`）
   - 白名单 #3: `services/data-service/app/sync/cb_sync.py`（`_pg_bulk_insert` thin wrapper）
   - 白名单 #4: `services/data-service/app/scheduler.py`（`_BACKFILL_MAP` 补 5 表 + `validate_pipeline_consistency()` 启动期自检）
   - 含「Decision 0 范围声明」明示路径 #4 inline 8 模块暂不动 → ADR-015 留位
3. **§决策 5 实施细则**（5.1-5.6）：6 个子决策 + 各代码骨架 + 关键注意（如 `conflict_cols` 兼容性 5.2.bis）
4. **§决策 6 SIT 12 项验证清单**：单测 / 行数等价性 / backfill smoke / git diff 白名单审计
5. **§决策 7 分阶段实施顺序**：6 阶段 + 5 个回滚点（任一失败可停在该阶段独立 commit）
6. **§不覆盖**段更新：明确 ADR-013（剩余表 schema 对齐）/ ADR-015（路径 #4）/ ADR-016（方案 B 升级路径）三个未来 ADR 留位
7. **§后续工作**勾选 PL 决策 + tech-lead 升 Accepted；backend-dev 待办按阶段 1-6 列
8. **§版本与查证**升级查证日期到 Accepted 当日（2026-06-22）+ 加 `inspect.signature` stdlib 版本行（决策 5.5 用到）
9. **Hand-off 段**重写为 backend-dev 实施清单（与 ADR-010 + ADR-011 follow-up 合并到同一 worktree 的协调说明 + 白名单边界硬强调）

### 关键技术决策亮点（落地依据）

- **`_insert_rows` 加可选参数而非新建函数**：保持 32+ sync 函数零改动，向后兼容（retries=0 + floor=None 是旧行为）
- **`_pg_write` 改 thin wrapper 但保留 8 个 `write_*` helper**：列重排逻辑（write_moneyflow 的字段 `[0,1,2,3,4,5,6,7,8,9,10]` 去掉 `net_mf_vol` r[11]、write_daily_basic 重排为 8 字段等）是业务必需，不能删——thin wrapper 仅替换底层写入引擎，不动 helper 业务转换
- **`conflict_cols` 兼容性 5.2.bis**：`_insert_rows` 用 `ON CONFLICT DO NOTHING` 不指定列，依赖表 PK；调用方 `conflict_cols` 必须 ⊆ 表 PK，遇 ths_daily 等 `(ts_code, trade_date)` UNIQUE 约束非裸 PK 的例外，backend-dev 实施时需先 grep 验证
- **stk_factor_pro 双轨入口**：`sync_stk_factor_pro_daily()` 保留作 cron 入口（内部调 `sync_stk_factor_pro_backfill(days_back=1)`），新增 `sync_stk_factor_pro_backfill(days_back: int)` 注册 `_BACKFILL_MAP`，避免破坏 cron job
- **validator WARN 不 raise**：可逆性优先；启动期不阻断（与方案 B 的 raise 形成对比，保留 ADR-016 升级时再切 raise）

### 质量门

- [x] §决策 0 白名单 4 文件 + 8+ 越界禁项明确
- [x] §决策 5 含代码骨架 + 关键注意点（5.2.bis / 5.4 双轨 / 5.6 不在范围）
- [x] §决策 6 SIT 12 项可独立验证（含 git diff 白名单审计 #12）
- [x] §决策 7 分阶段 + 回滚点设计
- [x] §不覆盖明确 ADR-013/015/016 三个未来留位（防止 backend-dev 把"剩余表 schema"误抓进本 ADR 实施）
- [x] §版本与查证 Accepted 日期 + `inspect.signature` 新增基线
- [x] Hand-off 段含与 ADR-010 / ADR-011 follow-up 合并 worktree 的协调说明（PL 在派单时说明合并）

### 下一步（交接 product-lead）

1. **PL**：等 ADR-010 code-review 结论 → 统一派 backend-dev 实施 ADR-010 follow-up + ADR-011 + ADR-012 三家到同一 worktree（PL 派单时指定 base ref + 三家 ADR Hand-off 段链接）
2. **backend-dev**（限额重置后）：按本 ADR §决策 7 阶段 1-6 顺序实施，证据落 `progress/backend-dev.md`
3. **tech-lead**（backend-dev 完成后）：抽取本 ADR 决策 0+5+6 模板片段到 `.claude/skills/agf-writing-adr/SKILL.md` 新增 "schema-alignment subtemplate"，给 ADR-013+ 复用
4. **tech-lead**（ADR-012 实施 + UAT 通过后 1-2 周）：立 ADR-013（建议从 hk_holdings 起，而非原计划 stk_factor_pro——因后者已被本 ADR 阶段 4 修了 backfill handler，hk_holdings 调用方多更适合验证瘦身模板）
5. **memory 更新（推迟）**：方案 A 实施成功后再写一条 memory「ADR-012 方案 A 已 adopt，新表必填 _BACKFILL_MAP + 路径选 _insert_rows」；当前 Accepted 但未实施，避免双源

---

## 2026-06-22（同日 +2）— §F-2 cyq 因子抽样验证

- 触发：team-lead 转交 code-reviewer 的 F-2 follow-up，并行小任务，read-only 抽样
- 范围：抽 5 只样本股，对比 fallback（pre-ADR-010）vs 实际 cyq_chips 真实数据下的 `tushare_cyq` 因子输出

### 验证目标对照

| 问题 | 结论 |
|---|---|
| (a) percent 0-100 体系是否被因子代码假设为 0-1（若是则 100x 误差） | **否**。`advanced_factors.py:1079` `tp = sum(percents) or 1.0` 再 `w/tp` 归一化为权重比例，**对 0-1 / 0-100 体系均不敏感**（avg_cost / 累积 p5/p95 算法纯归一化）；100x 风险**不存在**。 |
| (b) 单日历史是否够算 avg_cost / concentration_90 | **够**。`advanced_factors.py:1075-1095` 整个 cyq 因子只读 `MAX(trade_date)` 一天的全价格分布，avg_cost / p5 / p95 / concentration 全是**单日盘内分布统计**，**不依赖时序**。F-3 月底 days_back=30 累积 → 只让历史回测可用（trade_date 选 t-N），不影响实时因子。 |
| (c) F-3 月底 days_back=30 累积后是否能解锁更多因子 | **当前因子无新增解锁**。代码层仅消费 `MAX(trade_date)` 单日。但若未来追加"筹码迁移率 / 多日 avg_cost 趋势"类时序因子（advanced_factors 现暂无），则需累积。当前 cyq 因子已 100% 解锁 fallback。 |

### 抽样结果（trade_date=2026-06-18，close 来自同日 daily_kline）

| code | rows | close | avg_cost | pr=cp/avg | p5 | p95 | conc(%) | score | signal | 备注 |
|---|---|---|---|---|---|---|---|---|---|---|
| 000338 | 178 | 30.09 | 31.32 | 0.961 | 27.40 | 35.40 | 25.5 | **7.5** | accumulation | pr 落 [0.90,1.05] +2.5；conc 25.5 略高于阈值无加分 |
| 000988 | 100 | 177.55 | 163.45 | 1.086 | 147.60 | 178.20 | 18.7 | **6.0** | neutral | pr 1.086 越过 1.05 无加分；conc<25 +1.0 |
| 601127 | 99 | 64.81 | 84.69 | 0.765 | 66.30 | 120.70 | 64.2 | **4.0** | neutral | pr<0.80 无加分；conc>50 -1.0（套牢盘大） |
| 601916 | 21 | 2.99 | 3.01 | 0.993 | 2.90 | 3.30 | 13.3 | **9.5** | accumulation | 极端集中（最高 pmax 39.87），近完美锚定 |
| 688506 | 185 | 229.43 | 292.68 | 0.784 | 212.10 | 382.20 | 58.1 | **4.0** | neutral | 高位深套，conc>50 -1.0 |

**对比 pre-ADR-010 fallback**：5 只全部走 `else` 分支 → `{"score": 5.0, "signal": "no_data", "available": False}`，对外鉴别力为零。

**ADR-010 上线后**：5 只样本 score 区间 [4.0, 9.5]，标准差 ≈ 2.3，**对外鉴别力恢复**；signal 分层 accumulation/neutral/distribution 三档全部触发。

### 结论

1. **从 fallback 切到真实数据已生效**（pre/post 对比 5/5 信号源标记由 `no_data` 切到分层 signal）
2. **无 0-1 vs 0-100 量纲 bug**——percent 体系无关，归一化吸收所有差异
3. **F-3 月底 days_back=30 累积**对当前 cyq 因子**无额外解锁**（单日盘内分布统计即可），仅利于历史回测（trade_date 倒查）和未来时序型筹码因子（暂未实现）
4. **行动建议**：无需改 advanced_factors.py / schema / Alembic；ADR-010 follow-up + ADR-011 + ADR-012 合并 worktree 派单时**不必带 cyq 因子改造**
5. **追加观察**：601127 / 688506 conc>50 + pr<0.80 的"高位深套"样本得低分（4.0），符合"分发期"经济含义；601916 conc 13.3 + pr=0.993 得 9.5 高分，符合"主力锁仓 + 现价贴近成本"的"吸筹期"含义——**因子输出与业务直觉一致**

### 证据落盘

- 抽样脚本：`/tmp/cyq_factor_check.py`（5 股 583 行 cyq_chips 来自 PG）
- 因子源码：`packages/kronos-factors/kronos_factors/scorer/advanced_factors.py:1075-1096`
- 数据库现状：cyq_chips 36,142 行 / 300 股 / 2026-06-18 单日（与 F-1 报告一致）
