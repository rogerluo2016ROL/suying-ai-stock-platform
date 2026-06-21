# ADR-007: 阶段 0 止血 — 密钥注入 / 审计落库 / 双 schema 统一

- 状态：Accepted（product-lead 2026-06-21 确认；AC-10 fail-safe「DB 异常→暂停整轮循环」采纳——禁止 `return True`(全卖) / `return False`(不止损) 二选一）
- 日期：2026-06-21
- 决策者：tech-lead
- 影响范围：全栈（认证密钥链、trade-service 审计、docker-compose 启动链）
- 上游：`docs/prd/phase0-stabilization-2026-06-21.md` §9 Open Questions Q-2/Q-3/Q-4；`docs/reviews/audit-backend-2026-06-21.md` §4 / §5 / §6

## 上下文

阶段 0 止血 PRD 的 AC-1/2/3（认证）/AC-8（schema）/AC-9/10（资金）是 critical path，block 3 个实施 task。这三类项各自有一个未决的架构问题，不先定方向 dev 进不了 Plan Mode：

1. **密钥注入（Q-2）**：`KRONOS_SERVICE_SECRET` / `JWT_SECRET_KEY` / `ADMIN_PASSWORD` 当前都有硬编码默认值（`packages/kronos-auth/kronos_auth/config.py:10-13`、`backend/app/config.py:16-21/33`），AC-1/3/12 要改成「缺失即 raise」。但「谁注入」没定——dev 还是 ops？env file / secret manager / k8s secret？这直接决定「缺失即 raise」要不要分级（dev warn / prod raise），否则 dev 跑单测会因没设 env 而崩。
2. **审计落库（Q-3）**：`trade-service/app/audit_log.py` 已有完整 record/query 实现（200 行），但 `routes.py:525-544` 的 `_audit_record_safe` 只 `logger.info`、`/audit-logs` 返回硬编码空数组（`routes.py:497-520`）。AC-9 要接 DB，但接哪——复用 backend asyncpg 模式放 kronos 库，还是独立 audit 库？
3. **双 schema（Q-4）**：`services/sql/init_postgres.sql`（65 张业务表）与 `backend/alembic/versions/`（6 个迁移，auth/audit/training/diagnosis/legacy/snapshots）割裂，docker-compose 只挂 `init_postgres.sql`（`docker-compose.yml:32`），不跑 alembic → backend lifespan `seed_roles` 因 `roles` 表不存在而崩（`backend/app/main.py:25`）。AC-8 要在 docker 首启跑 alembic，但「长期要不要把 init_postgres.sql 转 alembic baseline」没定。

ADR-001（认证）§49 明示「服务间认证留给上生产前的安全审计 ADR」——本 ADR 就是补这个缺口，并顺带收口 Q-3/Q-4。

## 决策

### Q-2 密钥注入机制（影响 AC-1/3/12）

| 维度 | 选型 | 理由 |
|---|---|---|
| 阶段 0 / dev / 单机 docker | **`.env` file（gitignored）+ docker-compose `env_file`** | 最小代价；项目已有 `.gitignore` + `scan-secrets.sh` + pre-commit 防泄漏（CLAUDE.md Tool Boundaries）；不引新依赖、不改部署形态 |
| 阶段 2 生产（k8s） | **K8s Secret（挂载为 env）** | 与目标编排一致；Secret 在 etcd etcd 加密静态存储，RBAC 可控；阶段 2 接实盘时落地，本 ADR 只锁定方向 |
| 「缺失即 raise」是否分级 | **分级：`KRONOS_ENV=production` 时 raise，否则 warn** | dev 跑单测 / 本地起服务不应被强制设密钥卡死；prod 裸奔是 P0 漏洞（审计 P0-3/4），必须硬失败 |

**实现契约**（给 backend-dev 的约束，不规定具体行号）：

- 三个密钥读法统一为：`SECRET = os.environ.get("X")`；若 `os.environ.get("KRONOS_ENV") == "production"` 且 `X` 为空 → `raise RuntimeError("X must be set in production")`；否则 `warnings.warn(...)` 并给一个**明确非生产**的 fallback（如 `dev-only-<secret>` 前缀，便于日志一眼识别）。
- **绝不**用 `secrets.token_hex` 进程内随机（当前 `config.py:19` 的做法）——那会让多实例/重启 token 互不兼容，比硬编码默认值更隐蔽。
- `docker-compose.yml` 把 `JWT_SECRET_KEY` / `ADMIN_PASSWORD` 的 `:-dev-secret...` / `:-Admin123!` 兜底（`docker-compose.yml:74/76`）**移除**，改 `${JWT_SECRET_KEY:?JWT_SECRET_KEY required}` 形式（compose 原生缺失即报错）；KRONOS_SERVICE_SECRET 同理加入 backend 容器 env。

### Q-3 审计落库（影响 AC-9）

| 维度 | 选型 | 理由 |
|---|---|---|
| 落库位置 | **复用现有 `audit_logs` 表（kronos 库）** | alembic 002 已建该表（`backend/alembic/versions/002_add_audit_logs.py`），与 `audit_log.py:24 TABLE_AUDIT_LOGS="audit_logs"` 完全对齐；INSERT-only trigger 已在 alembic 里。零 schema 变更 |
| session 接入 | **复用 diagnosis-service 的 async SQLAlchemy 模式**（`services/diagnosis-service/app/database.py`：`create_async_engine` + `async_sessionmaker` + `get_db` dependency） | 项目已有可复制模板（ADR-005 已用），不引新依赖；与 backend 同一套 asyncpg driver；符合 CLAUDE.md「不引新 ORM」约束 |
| `/audit-logs` 路由 | 改 `audit_log.query(db, ...)` 真查询 | `audit_log.py:102-200` 已实现完整分页/过滤，仅 routes 未接（`routes.py:497-520` 硬编码空数组） |

> **ADR-002 命名漂移已记录**：ADR-002 §197 Decision 4 把表命名为 `trade_audit_log`，但实际落地（alembic 002 + audit_log.py）统一用 `audit_logs`。**以代码为准（`audit_logs`）**，本 ADR 在「后续工作」挂一条：ADR-002 该处文字需回头对齐，避免后续读者按 ADR-002 建错表名。

### Q-4 双 schema 统一方向（影响 AC-8）

| 维度 | 选型 | 理由 |
|---|---|---|
| 阶段 0 | **「业务表 SQL / auth+training+audit alembic」双轨 + docker 首启跑 alembic**（PRD §9 已倾向的最小代价方案） | 阶段 0 只为止血（让 docker 能起来），把 65 张业务表转 alembic baseline 是 L 级工作量（审计 P2-8），与止血目标不匹配 |
| 落地方式 | **backend Dockerfile entrypoint：`alembic upgrade head && uvicorn ...`** | init_postgres.sql（PG entrypoint，只建业务表）+ alembic upgrade head（backend entrypoint，建 auth/audit/training/diagnosis/circuit_breaker 表）两段职责清晰；alembic 幂等，重复启动安全 |
| 长期统一 | 留阶段 3（质量性能） | 阶段 3 做 schema 治理时再把 init_postgres.sql 反向生成 alembic baseline（`alembic stamp head` 后拆分），届时双轨并轨 |

**双轨契约**（写进 ADR 即为约定，dev 不得自行打破）：

- 业务表（`daily_kline` / `moneyflow` / `announcements` / `forecast_data` 等 65 张）schema 变更 → **只改 `services/sql/init_postgres.sql`**，不走 alembic。
- auth / `audit_logs` / `circuit_breaker_state` / training / diagnosis / legacy / snapshots 表 schema 变更 → **只走 alembic**。
- 两套表集合**不重叠**（已校验：`grep users|roles|refresh_tokens|circuit_breaker|audit_logs|training|diagnosis` 在 init_postgres.sql 0 命中，见审计 P0-2）。

## 备选方案

- **Q-2 A. 统一不分级，永远 raise（缺失即崩）** — pros：最安全，无歧义；cons：dev / 单测环境每次都要 export 一堆 env，CI 也要塞 mock 值，摩擦大；否决理由：与阶段 0「让 docker 一次起来」目标冲突，且 dev 流程被卡死会拖慢交付。
- **Q-2 B. 直接上 Vault / AWS Secrets Manager** — pros：生产级密钥轮换、审计；cons：引入新基础设施 + 网络/认证依赖，阶段 0 是止血不是建基座；否决理由：over-engineering，阶段 2 接实盘时再评估。
- **Q-3 A. 独立 audit 库（`kronos_audit`）** — pros：审计与业务库物理隔离，合规更干净；cons：多一个 DB / 连接池 / 备份策略，且 audit_logs 表已在 kronos 库里建好；否决理由：阶段 0 复用现成 schema 代价最低，物理隔离留阶段 2（若合规要求）。
- **Q-3 B. trade-service 自己写 asyncpg 裸 SQL（不走 SQLAlchemy）** — pros：少一层 ORM；cons：项目其余服务（backend / diagnosis）都是 SQLAlchemy async，再引一套裸 asyncpg 会分裂风格；否决理由：违反「简单 + 一致」，且 `audit_log.py` 本来就设计成吃 `AsyncSession`。
- **Q-4 A. 立刻把 init_postgres.sql 转 alembic baseline** — pros：单一 schema 来源，最干净；cons：L 级工作量，要为 65 张表逐张 stamp + 拆分迁移，阶段 0 止血不值得；否决理由：留阶段 3，本 ADR 已明确双轨契约兜底。
- **Q-4 B. 让 alembic `import` / source init_postgres.sql** — pros：一条链路；cons：alembic env.py 用 psycopg2 sync driver（`DATABASE_SYNC_URL`），init_postgres.sql 是 PG 方言 DDL，混进 alembic 迁移会让 downgrade / 依赖管理失控；否决理由：职责混淆，Dockerfile entrypoint 两段式更清晰。

## 影响

- **现有代码**：
  - `packages/kronos-auth/kronos_auth/config.py`（KRONOS_SERVICE_SECRET 分级 raise）— AC-1
  - `backend/app/config.py`（JWT_SECRET_KEY 分级 raise，移除 token_hex 路径；ADMIN_PASSWORD 移除 `Admin123!` 默认）— AC-3 / AC-12
  - `docker/docker-compose.yml`（移除 `JWT_SECRET_KEY` / `ADMIN_PASSWORD` 的 `:-` 兜底，加 `:?` 强制；加 KRONOS_SERVICE_SECRET / KRONOS_ENV env）— AC-8 / AC-12
  - `backend/Dockerfile`（entrypoint 加 `alembic upgrade head`）— AC-8
  - `services/trade-service/`（新增 `database.py` 复用 diagnosis 模式；`routes.py` 的 `_audit_record_safe` → `await record(db,...)`、`/audit-logs` → `query(db,...)`；4 类操作挂审计）— AC-9
  - `services/strategy-service/app/auto_trading_executor.py`（3 个风控函数改连接池 + fail-safe 暂停）— AC-10
- **团队**：backend-dev 需熟悉「分级 raise」模式与 alembic 双轨契约；dev 本地需准备 `.env`（提供 `.env.example` 模板）。
- **成本**：零新增依赖（asyncpg / SQLAlchemy / alembic 均已在栈内）。token 增量 0。生产 k8s Secret 留阶段 2。
- **运维**：新增监控点——backend / 各服务启动失败原因（密钥缺失）应进日志聚合；`audit_logs` 表需纳入 PG 备份策略（与 kronos 库一同备份即可，无独立需求）。

## 本 ADR 不覆盖的决策

- **K8s Secret 的具体接入方式 / RBAC 策略 / 密钥轮换周期** —— 留阶段 2 生产化 ADR。
- **Vault / Secrets Manager 是否引入** —— 同上，阶段 2 评估。
- **业务表 65 张转 alembic baseline 的拆分方案** —— 留阶段 3 schema 治理。
- **`audit_logs` 物理隔离到独立库（合规要求）** —— 若阶段 2 合规审计要求则新开 ADR。
- **多 LLM SDK 密钥（DEEPSEEK / TUSHARE）注入** —— 已由 CLAUDE.md 规则 + skill `agf-wiring-multi-llm-sdk` 覆盖，本 ADR 不重复。

## 后续工作

- [ ] backend-dev：按 Q-2 契约实现分级 raise（AC-1/3/12），提供 `.env.example`（触发条件：本 ADR Accepted 后 Plan Mode）
- [ ] backend-dev：backend Dockerfile entrypoint 加 `alembic upgrade head`（AC-8）
- [ ] backend-dev：trade-service 接 async SQLAlchemy session + audit_log record/query 接通（AC-9）
- [ ] backend-dev：auto_trading_executor 3 风控函数连接池化 + fail-safe 暂停（AC-10）
- [ ] tech-lead：回头对齐 ADR-002 §197 的 `trade_audit_log` → `audit_logs` 命名（触发条件：本 ADR Accepted 后随手修，避免表名漂移）
- [ ] （阶段 2）tech-lead：k8s Secret 接入 ADR
- [ ] （阶段 3）tech-lead：业务表转 alembic baseline / 双轨并轨 ADR

## 版本与查证

**查证基线日期**：2026-06-21

> 本 ADR 不引入新技术选型（asyncpg / SQLAlchemy / alembic / docker-compose 均在 ADR-000/001/006 栈内），故无新增依赖版本行。仅对「docker-compose `${VAR:?msg}` 强制语法」与「alembic upgrade head 幂等性」做事实核对：

| 核对项 | 结论 | 信息来源 |
|---|---|---|
| docker compose `${VAR:?error}` 缺失即报错语义 | 支持（compose spec 原生，v2/Compose CLI） | [Compose spec — Variable interpolation](https://github.com/compose-spec/compose-spec/blob/main/spec.md#interpolation) — "`${VAR:?err}`: if VAR is unset or empty, compose exits with an error" |
| `alembic upgrade head` 幂等（已迁移则 no-op） | 是 | alembic 设计：`alembic_version` 表追踪，重复 upgrade 不重跑迁移 |
| `services/diagnosis-service/app/database.py` 为可复用 async SQLAlchemy 模板 | 已验证（本 ADR 调研时 Read 确认 `create_async_engine` + `async_sessionmaker` + `get_db`，与 backend 同源） | 仓库内 `services/diagnosis-service/app/database.py` |
