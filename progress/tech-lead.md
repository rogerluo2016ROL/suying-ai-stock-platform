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
