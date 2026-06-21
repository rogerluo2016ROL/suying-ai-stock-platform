# PRD — 阶段 0 止血（Phase 0 Stabilization）

- **Date**: 2026-06-21
- **Owner**: product-lead
- **Status**: Approved（2026-06-21；tech-lead review 完成 + ADR-007 Accepted，解 block AC-1/2/3/8/9/10 实施）
- **Estimated effort tier**: Large（含资金/认证/schema 项需 tech-lead review + Plan Mode + 全 UAT 链路，非纯编码量）
- **依据审计**: `docs/reviews/platform-audit-2026-06-21.md` §3 P0 清单

## 1. Background

2026-06-21 全栈审计（前端/后端/模型三域并行）结论：平台整体可用性 2.5/5、有效性 1.5/5，存在 **9 条 P0 级问题**会直接导致：首次部署崩溃、核心业务页登录后 401、实盘资金操作不可追溯、最高权限可被硬编码默认值秒破、决策所依赖的回测指标不可信。

本 PRD 收口「阶段 0 止血」——在面向任何真实用户或任何资金操作之前，先把这 9 条堵住。阶段 1（重建回测可信度）/ 阶段 2（接通 LLM/训练/实盘）/ 阶段 3（质量性能）留后续单独 PRD，原因见 §2 Non-Goals。

业务驱动：平台宣称「AI 驱动量化投资」，当前连「登录后看到自己的方案」都做不到（Strategy/Trade/AutoTrade 三页必然 401），更遑论「替代人工盯盘」。止血是兑现任何价值主张的前置。

## 2. Goal & Non-Goals

**目标**: 在一个干净的 docker 环境里 `compose up -d` 全绿、登录后 13 个业务页全部加载成功、扣交易成本后重跑历史回测得到可信收益符号、CI（SIT）24/24 绿、无可被秒破的越权洞、资金操作可追溯——平台达到「可被真实用户试用」的最小可用态。

**KPI（上线后用什么判定成功）**:
1. `docker compose up -d` 后 backend lifespan 不抛异常，`/api/v1/health` 全 service 200（当前会崩在 `seed_roles`）
2. 登录后访问 `/strategy` `/trade` `/auto-trade` 返回业务数据而非 401（当前必然 401）
3. `curl -H "X-Service-Auth: dev-service-secret-change-in-production" .../trade/mode` 返回 401/403（当前返回 200 admin）
4. `cd frontend && npx vitest run` → 24/24 passed（当前 4 failed + worker 崩溃）
5. 重跑 bi_trend 6 个月回测扣成本（往返 0.14%）后的聚合 mean/trade 符号可对外陈述（当前指标建立在零成本假象上）
6. trade-service 切 live mode / 重置熔断 / 下单操作落 `audit_log` 表，重启后仍可查询（当前只进 stdout）

**Non-Goals**（明确不做，留给后续阶段）:
- 不重训 Kronos / 不接 LLM 生成方案（阶段 2）
- 不实现 bi_trend 声明的多日持有 + 止盈 + 移动止损回测引擎（阶段 1）
- 不做 walk-forward 样本外验证（阶段 1）
- 不接 xtquant 实盘（阶段 2，且依赖阶段 1 结论）
- 不把 4 个 in-memory store 迁 PostgreSQL（阶段 2）
- 不做前端 TanStack Query / bundle 优化（阶段 3）
- 不补充全量单元测试（阶段 3）
- **不基于阶段 0 回测新结论修改任何 bi_trend 策略参数**（这是纪律，见 §6）

## 3. User Stories

| ID | As a | I want to | So that |
|---|---|---|---|
| US-1 | 个人投资者 | 登录后正常使用方案/交易/自动交易页 | 不会登录后被踢回登录页死循环 |
| US-2 | 平台运维 | `docker compose up -d` 一次成功 | 不必手动跑 alembic 才能让 backend 起来 |
| US-3 | 平台安全负责人 | 没有硬编码的越权后门 | 攻击者无法用一个写死的字符串拿到 admin 实盘权限 |
| US-4 | 合规审计员 | 查到任何一笔交易/熔断/切 live 的操作记录 | 资金操作可追溯，容器重启不丢 |
| US-5 | 量化研究员 | 看到扣交易成本后的回测收益 | 知道策略到底赚不赚钱，不再被零成本假象误导 |
| US-6 | 前端开发 | CI 绿 | PR 能走 DoD 质量门 |

## 4. Acceptance Criteria

> 逐条独立可验证。code-reviewer / qa-engineer 据此核对。资金/认证/schema 项标注【需 Plan Mode + tech-lead】。

| ID | Priority | AC | Verification method |
|---|---|---|---|
| AC-1 | P0【认证】 | 移除 `packages/kronos-auth/kronos_auth/config.py` 的 `KRONOS_SERVICE_SECRET` 硬编码默认值，改为 `os.environ["KRONOS_SERVICE_SECRET"]`，缺失即启动失败（raise） | 未设 env 启动 → 进程退出非 0；设了 env → 正常 |
| AC-2 | P0【认证】 | `curl -H "X-Service-Auth: dev-service-secret-change-in-production" http://localhost:8006/api/v1/trade/mode` → 401/403（不再被当 admin） | curl 实测 |
| AC-3 | P0【认证】 | `backend/app/config.py` 的 `JWT_SECRET_KEY` 缺失即 raise（不再 `secrets.token_hex` 随机化 + warn） | 未设 env 启动 → raise；重启进程后已签发 token 仍有效（secret 来自 env） |
| AC-4 | P0【前端】 | 13 个业务页的 40+ 处裸 `fetch()` 全部改走 `client.ts` axios 实例（享受鉴权拦截器）；grep `fetch("/api` 在 `frontend/src/pages/` 下 0 命中 | grep + 登录后实测 Strategy/Trade/AutoTrade 页 200 |
| AC-5 | P0【前端】 | 删除 `Diagnosis.tsx` 的 `generateMockResult` 与所有 `import.meta.env.DEV` fallback，失败统一 `message.error` + Empty | grep `generateMockResult\|import.meta.env.DEV` 在 Diagnosis.tsx 0 命中 |
| AC-6 | P0【前端】 | `cd frontend && npx vitest run` → exit 0，24/24 passed（`auth-flow.test.tsx` 的 `fillRegisterForm` 改 `userEvent.type` 或显式 `validateFields`） | vitest 实测 |
| AC-7 | P0【后端】 | `services/data-service/app/scheduler.py` 与 `sync/pg_writer.py` 顶部加 `from psycopg2.sql import SQL, Identifier`，`detect_data_gaps()` / `refresh_materialized_views()` / `check_table_latest_date()` 不再 NameError | 调用 `refresh_materialized_views()` 返回成功而非异常 |
| AC-8 | P0【schema】 | docker-compose backend 首次启动跑 `alembic upgrade head`（Dockerfile entrypoint 或 init container），`seed_roles` 不再因 `roles` 表不存在抛异常 | 干净环境 `compose up -d` → backend healthy；init_postgres.sql 与 alembic 关系在 ADR/注释中明确 |
| AC-9 | P0【资金】 | trade-service 接 asyncpg session，`_audit_record_safe` 调 `await record(db, ...)`；`/audit-logs` 走真查询；切 live mode / broker connect / 重置熔断 / 下单 4 类操作落 `audit_log` 表 | 触发操作 → 查 `audit_log` 表有记录；重启容器 → 记录仍在 |
| AC-10 | P0【资金】 | `auto_trading_executor` 的 `_check_announcement_risk` / `_get_atr_stop_loss` / `_check_forecast_risk` 改用连接池（asyncpg pool 或 sqlalchemy engine）；DB 异常时 fail-safe 暂停交易而非 `except: return False` 静默继续 | 单测：mock DB 连接失败 → executor 进入 paused 状态而非继续下单 |
| AC-11 | P0【模型】 | `tools/backtest_bi_trend.py` 的 `get_next_day_return` 出口扣交易成本（佣金 0.025% 双边 + 印花税 0.05% 卖单 + 过户费 0.001% 沪市，可配 `--cost-bps`），重跑 6 个月历史回测，输出扣成本后聚合 mean/trade 与逐月表 | 重跑脚本产物 JSON 含 `net_return` 字段；新旧口径并列输出 |
| AC-12 | P0【安全】 | docker-compose.yml 移除明文 `ADMIN_PASSWORD: Admin123!` 等默认，改为 `${ADMIN_PASSWORD}` 强制 env（缺失给明确报错） | 未设 env → 启动失败并提示 |

## 5. Design

- **UI**: 阶段 0 无新 UI；前端改动仅限「裸 fetch → axios」机械替换 + 删 DEV mock + 修测试，不涉及视觉/交互设计，uiux-designer 不介入。
- **API 契约**: 阶段 0 不新增/不改接口签名；仅 `/audit-logs` 从硬编码空数组改为真查询（响应 schema 不变）。
- **数据模型**:
  - `audit_log` 表（trade-service）：复用现有 `audit_log.py` 已定义的 schema（已有完整 record/query 实现，仅 routes 未接），不新设计。
  - `circuit_breaker_state` 表已在 alembic 002，AC-8 确保 alembic 在 docker 启动时执行使其存在。
  - 回测产物 JSON 增 `net_return` / `cost_bps` 字段（非 DB schema 变更）。

## 6. Technical Constraints

- **强制 Plan Mode + tech-lead review 的项**：AC-1/2/3（认证密钥）、AC-8（schema migration chain）、AC-9/10（资金相关）。这些项的 dev 在实施前必须先进 Plan Mode 拿 PL 授权，方案经 tech-lead 评审。其余项（AC-4/5/6/7/11/12）可由 dev 直接实施 + 自跑 SIT。
- **回测纪律**（洞察 5）：AC-11 只加成本 + 重跑 + 输出指标，**禁止**借机调整任何 bi_trend 策略参数。是否调参是阶段 1 的决策，依赖扣成本后的真实符号（见 Q-1）。
- 不引入新依赖（除 `userEvent` 已在 devDeps）；连接池用 asyncpg / sqlalchemy（项目已有），不引新 ORM。
- 遵守 `.claude/standards/coding.md`「Verify before assert」、`security.md`、`observability.md`（audit_log 接 DB 后需结构化字段）。
- 微服务间仍用 urllib async wrapper（项目规则，不引 httpx）。

## 7. Cost Estimate

- **LLM token / 月**：阶段 0 无 LLM 功能（strategy 仍 stub），0。
- **Agent Team 开发 token**：tech-lead（认证/schema/资金方案评审）+ frontend-dev（AC-4/5/6）+ backend-dev（AC-1/2/3/7/8/9/10/12）+ ml-engineer（AC-11）+ code-reviewer + qa-engineer（E2E）+ deploy-engineer（UAT 栈）。预估 6-8 个 agent 协作，总 token ~300-500K，落 cost-budget **Large 档**。
- **资金风险**：AC-9/10 触及 trade-service / auto_trading_executor，虽当前无实盘（xtquant stub），仍按 CLAUDE.md 走重流程。

## 8. Out of Scope / Future Work

- 阶段 1（回测可信度重建）：walk-forward、多日持有回测、幸存者偏差修复、加权进产物。独立 PRD。
- 阶段 2（接通真东西）：strategy 接 DeepSeek、training 接真数据 + 真 MLflow、4 store 迁 PG、Kronos 接入选股、xtquant wire。独立 PRD。
- 阶段 3（质量性能）：TanStack Query + orval、bundle 优化、OpenTelemetry、单元测试补全、bi_trend 两份重复代码合并、prediction 统一走 PG。独立 PRD。
- 下游 8 个 service 的 RBAC 依赖补全（洞察 3「前紧后松」）——阶段 0 只堵越权后门（AC-1/2），全面补 `require_role` 留阶段 2。

## 9. Open Questions

| ID | 问题 | Owner | Due | 备注 |
|---|---|---|---|---|
| Q-1 | AC-11 扣成本后回测聚合 mean/trade 的符号是什么？若为负，阶段 1/2 的产品优先级（接 Kronos / 接 LLM）需重估 | ml-engineer → product-lead | 2026-06-21（提前完成） | **已答**：扣 14bp 往返后聚合净均值 **+0.0526%/trade（正）**，但毛 +0.1926% 被吃 73%，净胜率 46.6%，逐月 3 正 3 负。**关键风险（PL 补充）**：净**中位数 -0.22%**（右偏，正期望靠少数大赢，典型交易净亏）；去掉调参期 6 月（净 sum +74.65，n=51 异常少）后 1-5 月净 sum **-34.18（负）** → 非调参期亏损，样本外大概率亏损。**阶段优先级调整**：阶段 1（walk-forward 样本外验证）比阶段 2（接 Kronos/LLM）更紧迫；阶段 2 若推进须以净均值为目标、禁再用 6 月数据调参。产物 outputs/backtest_bi_trend_6m_cost14_summary.json |
| Q-2 | 生产环境 `KRONOS_SERVICE_SECRET` / `JWT_SECRET_KEY` / `ADMIN_PASSWORD` 由谁、用什么机制注入（env file / secret manager / k8s secret）？ | tech-lead | 2026-06-23 | **已定（ADR-007）**：阶段0/dev/单机 docker 用 `.env`（gitignored，提供 `.env.example`）；阶段2 生产用 k8s Secret 挂 env。**分级 raise**：`KRONOS_ENV=production` 时三密钥缺失即 `raise`，否则 `warn` + 带 `dev-only-` 前缀的明确 fallback；禁用 `secrets.token_hex` 进程内随机。docker-compose 把 `:-` 兜底改 `:?` 强制。 |
| Q-3 | `audit_log` 落 trade-service 自己的 PG session，还是复用 backend 的 asyncpg 模式？表放 kronos 库还是独立 audit 库？ | tech-lead | 2026-06-23 | **已定（ADR-007）**：复用现有 `audit_logs` 表（alembic 002 已建，kronos 库，与 `audit_log.py:24` 对齐，零 schema 变更）；trade-service 新增 `database.py` 复用 diagnosis-service 的 async SQLAlchemy 模式；`_audit_record_safe` → `await record(db,...)`，`/audit-logs` → `query(db,...)`。独立 audit 库留阶段 2 合规要求时再评。ADR-002 §197 的 `trade_audit_log` 表名与代码漂移，以 `audit_logs` 为准。 |
| Q-4 | AC-8 双 schema 统一方向：把 init_postgres.sql 转 alembic baseline，还是明确「业务表 SQL / auth-training alembic」双轨并写进 ADR？ | tech-lead | 2026-06-23 | **已定（ADR-007）**：阶段 0 选「双轨 + docker 跑 alembic」。业务表 65 张只改 init_postgres.sql；auth/audit/circuit_breaker/training/diagnosis 只走 alembic，两集合不重叠。落地：backend Dockerfile entrypoint `alembic upgrade head && uvicorn ...`（幂等）。业务表转 alembic baseline 留阶段 3 schema 治理。 |

## 10. Sign-offs

- [x] product-lead: 初稿（本文件）
- [x] tech-lead: 技术可行性 review 完成（ADR-007 Accepted，6/6 go，AC-10 fail-safe 方向已约束）
- [ ] frontend-dev: 实现可行性确认（AC-4/5/6）
- [ ] backend-dev: 实现可行性确认（AC-1/2/3/7/8/9/10/12）
- [ ] ml-engineer: 实现可行性确认（AC-11）
- [ ] qa-engineer: AC 可测性确认（全部 AC）
- [ ] uiux-designer: N/A（阶段 0 无 UI 改动）

## Changelog

- 2026-06-21: 初稿（基于 2026-06-21 全栈审计 §3 P0 清单）
