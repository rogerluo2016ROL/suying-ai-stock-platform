# OpenWolf

@.wolf/OPENWOLF.md

This project uses OpenWolf for context management. Read and follow .wolf/OPENWOLF.md every session. Check .wolf/cerebrum.md before generating code. Check .wolf/anatomy.md before reading files.


# 速赢AI — 证券投资管理平台

> Agent 角色用裸名（`product-lead` / `backend-dev` …），项目 skill / slash command 保留 `agf-` 前缀。模板版本以根目录 `CHANGELOG.md` 为准；协议详见 `.claude/rules/team-mode.md`。

## Project Overview

速赢AI（Suying AI）是一站式 AI 驱动量化证券投资管理平台。覆盖 **选股发现 → 方案生成 → 回测验证 → 自动交易执行 → 个股诊断** 全链路量化工作流。核心用户为证券分析师、量化交易员与个人投资者，价值主张是"AI 替代人工盯盘与主观决策"。

## Tech Stack

> 由 tech-lead 在项目启动时维护，每次技术选型变更必须新开 ADR + 同步此处。详细基线见各 ADR。

| 类别 | 选型 | ADR |
|---|---|---|
| 前端框架 | React 18 + Vite 6 + TypeScript 5.6 + Ant Design 5.22 + ECharts 5.5 | — |
| 后端框架 | FastAPI (Python ≥3.10) + uvicorn + Pydantic v2 | — |
| 数据库 | PostgreSQL 15 (primary, docker) + SQLite (fallback/kronos legacy) + Redis 7 (cache) | ADR-001 |
| AI/ML | Kronos-mini (公开模型托管推理, 非自研 — 见 ADR-005/M05) + LightGBM + CatBoost | ADR-004 (model-training-pipeline), ADR-005 |
| LLM SDK | DeepSeek (方案生成, strategy-service) | — |
| 认证 | PyJWT (HS256) + Argon2id + RBAC 4 角色 + httpOnly Refresh Cookie | ADR-001 |
| 实盘交易 | Xtquant (QMT) 券商接口 + MockBroker (模拟) | ADR-002 (live-trading-broker) |
| 自动交易 | asyncio 定时轮询 + APScheduler (训练调度) | ADR-003, ADR-004 |
| 测试框架 | pytest (Python) + vitest (前端) | — |
| 数据管道 | data-service (asyncio 调度 + PG-first 直写 + Tushare 1.4.29) + SQLite fallback | ADR-006 |
| 部署 | Docker Compose (dev, postgres:15-alpine + redis:7-alpine + 8 微服务; 另有 3 个手动启动: backend/data-service/training-service) | — |

## Verified Facts (Quick Reference)

> 跨 session 复用的"硬事实"缓存，引用前优先看此节；不在此节则 **grep 实际代码 verify 后再断言**（参见 `.claude/standards/coding.md` "Verify before assert"）。

### 微服务端口映射

| 服务 | 端口 | 功能 | 启动命令 |
|---|---|---|---|
| api-gateway | 8080 | 统一 API 网关 | `uvicorn app.main:app --port 8080` |
| backend (auth) | 9001 | JWT 认证 + RBAC + 用户管理 | `uvicorn app.main:app --port 9001` |
| screener-service | 8001 | 7 模式选股 + 多因子排序 | `uvicorn app.main:app --port 8001` |
| prediction-service | 8002 | Kronos 30日 K线预测 | `uvicorn app.main:app --port 8002` |
| strategy-service | 8003 | 方案管理 + 自动交易策略引擎 + 执行器 | `uvicorn app.main:app --port 8003` |
| signal-service | 8004 | 综合交易信号分析 (50维) | `uvicorn app.main:app --port 8004` |
| alert-service | 8005 | 预警规则 + 实时提醒 | `uvicorn app.main:app --port 8005` |
| trade-service | 8006 | 模拟/实盘交易 + 持仓/账户管理 | `uvicorn app.main:app --port 8006` |
| backtest-service | 8007 | 历史回测 + IC/ICIR 分析 | `uvicorn app.main:app --port 8007` |
| training-service | 8008 | 模型训练 + MLflow 实验追踪 | `uvicorn app.main:app --port 8008` |
| diagnosis-service | 8009 | 五维个股诊断 (技术/资金/基本面/AI/情绪) | `uvicorn app.main:app --port 8009` |
| PostgreSQL | 6432 | docker: `postgres:15-alpine`, 用户 `kronos/kronos`, 库 `kronos` | `docker start docker-postgres-1` |
| Redis | 7379 | docker: `redis:7-alpine` | `docker start docker-redis-1` |
| Frontend | 3000 | Vite dev server | `cd frontend && npm run dev` |

> 启动所有基础设施: `docker start docker-postgres-1 docker-redis-1`
> 一键启动全部: `cd docker && docker compose up -d`

### 认证机制

- **JWT**: HS256 算法, Access Token 15min, Refresh Token 7d
- **Refresh Token**: 存储在 `httpOnly + Secure + SameSite=Strict` cookie（key: `refresh_token`），防 XSS/CSRF
- **密码哈希**: Argon2id (time_cost=3, memory_cost=65536 KiB, parallelism=2)
- **RBAC**: 4 角色 — `admin` / `internal_analyst` / `external_analyst` / `user`
- **默认管理员**: `admin@suying.ai` / `Admin123!`（由 `backend/app/config.py` 定义，`main.py` lifespan 自动 seed）
- **实证**: `backend/app/config.py:16-32`, `backend/app/routers/auth.py:35-50`, ADR-001

### 数据库连接

- **PostgreSQL (async)**: `postgresql+asyncpg://kronos:kronos@localhost:6432/kronos`
- **PostgreSQL (sync)**: `postgresql+psycopg2://kronos:kronos@localhost:6432/kronos`
- **Kronos PG**: 环境变量 `KRONOS_PG_URL`，经 `kronos_factors.pg_adapter.create_pg_adapter()` 注入
- **SQLite fallback**: 环境变量 `KRONOS_SQLITE_PATH`，指向 `Kronos/data/kronos.db`
- **Alembic 迁移**: `cd backend && alembic upgrade head`
- **实证**: `backend/app/config.py:6-12`, `backend/alembic.ini`, `docker/docker-compose.yml:21-32`

### 关键环境变量

| 变量 | 默认值 | 说明 |
|---|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://kronos:kronos@localhost:6432/kronos` | 异步数据库连接 |
| `JWT_SECRET_KEY` | dev-secret (勿用于生产) | JWT 签名密钥, 生产≥32字符 |
| `ADMIN_EMAIL` / `ADMIN_PASSWORD` | `admin@suying.ai` / `Admin123!` | 自动 seed 的管理员 |
| `KRONOS_PG_URL` | **必设** `postgresql://kronos:kronos@localhost:6432/kronos` | screener/signal/backtest 的 PG 连接，不设则 fallback 到空的 SQLite 导致 "no such table: stocks" |
| `TUSHARE_TOKEN` | — | Tushare 数据源 token (选股/回测需要) |
| `DEEPSEEK_API_KEY` | — | DeepSeek LLM API key (strategy-service 方案生成) |
| `TRADE_SERVICE_URL` | `http://localhost:8006` | 自动交易引擎调用的交易服务地址 |
| `SIGNAL_SERVICE_URL` | `http://localhost:8004` | 自动交易引擎调用的信号服务地址 |
| `CORS_ALLOWED_ORIGINS` | `http://localhost:5173,http://localhost:3000` | CORS 白名单 |
| `DEBUG` | `false` | 开启后 uvicorn reload + verbose logging |

### 项目目录结构

| 路径 | 内容 |
|---|---|
| `backend/` | FastAPI 主应用 (认证 + 用户管理 + Alembic 迁移) |
| `frontend/` | React + Vite 前端 (src/pages/ 按功能分页) |
| `services/<name>/app/` | 11 个 FastAPI 微服务 |
| `packages/kronos-factors/` | Kronos 因子计算引擎 (Python 包) |
| `packages/kronos-core/` | Kronos Transformer 模型核心 |
| `packages/kronos-data/` | 数据管道与 Tushare 适配 |
| `Kronos/` | Kronos 模型训练工具 + WebUI (Flask legacy) + 数据/模型输出 |
| `docker/` | Docker Compose 编排 + 每个服务的 Dockerfile |
| `services/sql/` | PostgreSQL 初始化 SQL + 数据迁移脚本 |
| `docs/adr/` | 6 个 ADR: 认证/券商交易/自动交易/训练/诊断/数据管道 |
| `docs/prd/` | PRD 文档 (auto-trading / live-trading) |

### ADR 基线

| ADR | 主题 | 状态 |
|---|---|---|
| ADR-001 | 用户认证与 RBAC — JWT + Argon2id + httpOnly Cookie | Proposed |
| ADR-002 | 券商实盘交易 — BrokerInterface 抽象 + Xtquant + CircuitBreaker (live-trading-broker) | Proposed |
| ADR-003 | 量化自动交易策略引擎 — asyncio 轮询 + ExecutorManager | Proposed |
| ADR-004 | 模型训练管线 — APScheduler + MLflow + A/B 上线 (model-training-pipeline) | Proposed |
| ADR-005 | 个股诊断 — 五维加权评分 + PDF 导出 + 多股对比 | Proposed |
| ADR-006 | 数据管道 — PG-first 直写 + 消除 subprocess 桥 + stocks 同步 + 物化视图 | Proposed |

## Project-Specific Rules

- 本文件只放项目特有规则，团队通用规则统一放在 `.claude/standards/`，结构性指引在 `.claude/rules/`。
- 微服务间 HTTP 调用使用 `urllib` async wrapper (`loop.run_in_executor`)，不引入 `httpx`/`aiohttp` 额外依赖。
- 自动交易引擎的状态管理使用 `asyncio.Event`（暂停/停止信号），与 `threading.Lock`（StrategyStore）分层隔离。
- PG 与 SQLite 列名差异（`pct_chg` vs `change_pct`, `ts_code` vs `code`）由 `pg_adapter._PgCursor._KEY_MAP` 和 `_COLUMN_MAP` 透明转换，代码层应始终使用 SQLite/engine 命名。
- 预测服务 (8002) 基于公开 `NeoQuasar/Kronos-mini` 托管推理（非自研，详见 ADR-005）；自研 fine-tune checkpoint 目录 `Kronos/outputs/models/` 当前不存在，启动走 base 分支是预期行为，`/api/v1/health` 的 `checkpoint_status` 字段标注来源（`base_public` / `finetuned`）。
- 涉及多 LLM SDK 接入（DeepSeek/Doubao/Qwen/MiniMax 切换、fallback、env 变量）→ 必须先看 skill `agf-wiring-multi-llm-sdk`。
- 写 PRD → skill `agf-writing-prd`；写 ADR → skill `agf-writing-adr`。
- SIT 由执行层 dev 自跑（按 skill `agf-running-sit-tests`），证据落 `progress/<role>.md` 的 `**SIT 证据**` 段，由 `code-reviewer` 在 code review 时 audit。
- 写 E2E / UAT 报告 → skill `agf-writing-qa-report`（SIT 不再单独成报告）。
- 程序化生成中文 docx 报告（决议书 / 评审 / 投标书等高密度文档）→ skill `agf-writing-docx-reports`（docx-js）；程序化生成中文 pptx（制度 / 党政 / 宣贯 deck）→ skill `agf-writing-pptx-reports`（python-pptx）。两者依赖外部第三方 skill `docx` 与 `pptx`。
- 在仓库提 GitHub issue（手工创建 / 报 bug / dev 在 SIT 中发现 P0/P1 自动 path / qa-engineer 在 E2E/UAT 中发现 P0/P1 自动 path）→ skill `agf-writing-github-issue`（含标签锁定 + 最小输入模式）。
- Release 推 tag + `gh release create` 完成后（仅 MAJOR / MINOR）→ 必须 `/agf-release-retro vX.Y.Z` 触发，按 skill `agf-running-release-retro`，产物归档到 `docs/reviews/retro-vX.Y.Z-YYYY-MM-DD.md`；PATCH 跳过。
- 交易相关代码修改涉及真实资金风险，修改 `trade-service`、`auto_trading_executor`、BrokerInterface 实现时必须谨慎且完整测试。

## Test Commands

> 项目测试入口固化在此，agent 跑测试时优先查此节，避免重新探索目录结构。

- **backend unit**: `cd backend && .venv/bin/pytest tests/ -v`
- **backend integration**: 需要 Docker PostgreSQL + Redis 运行中 (`docker start docker-postgres-1 docker-redis-1`)
- **frontend unit**: `cd frontend && npx vitest run`
- **frontend SIT**: `cd frontend && npx vitest run tests/sit/`
- **Python package tests**: `cd packages/<name> && pytest tests/ -v`
- **Service tests**: `cd services/<name> && pytest tests/ -v`
- **E2E**: 需全服务启动 (`cd docker && docker compose up -d`) + `npx playwright test`（chrome-devtools MCP 提供浏览器自动化）
- **TypeScript check**: `cd frontend && npx tsc -b --noEmit`
- **Build**: `cd frontend && npm run build`
- **Python syntax**: `.venv/bin/python -c "import ast; ast.parse(open('<file>').read())"`
- **Docker 全部启动**: `cd docker && docker compose up -d`
- **Docker 停止**: `cd docker && docker compose down`

> ⚠️ 命令变化时必须同步本节，否则下一个 agent 会按过时命令跑，浪费一整轮交接。

## Tool Boundaries

四层 hook 防御（注册位置：`.claude/settings.json` + `.git/hooks/pre-commit`，文档：`.claude/standards/security.md`）：

1. **`PreToolUse` (Bash) — `block-dangerous-bash.sh`**：硬阻断 `rm -rf` / `DROP TABLE` / `git push --force` / `git reset --hard`。
2. **`UserPromptSubmit` — `scan-secrets.sh`**：硬阻断 AWS/GitHub/OpenAI/Anthropic/Google/Slack/DeepSeek/Doubao/Qwen/MiniMax 密钥 + PEM/SSH/PuTTY 私钥 + BIP39 助记词。
3. **`PostToolUse` (WebFetch/WebSearch/Read/Bash/mcp__*) — `sanitize-tool-output.sh`**：软告警外部内容里的 prompt-injection 指令（含所有 MCP 工具输出）。
4. **`pre-commit` (git) — `scan-commit.sh`**：commit 前对 staged diff 跑同套 secret 正则，防 Edit/Write 绕过 prompt 扫描。安装：`ln -sf ../../.claude/hooks/scan-commit.sh .git/hooks/pre-commit`（`init-team.sh` 会自动安装）。

`.claude/settings.json` 的 `permissions.deny` 已禁读 `.env*`、`~/.ssh/**`、`~/.aws/**`、`~/.gnupg/**` 等敏感路径，并禁 `curl|sh` / `eval` 等远程执行链路。

附加 workflow hooks（**不属于安全防御**，仅维护团队工作流）：

5. **`TeammateIdle` — `teammate-keepalive.sh`**：task list 还有 pending 时阻止 teammate 提前 idle。
6. **`SubagentStop` / `TeammateIdle` — `check-progress-file.sh`**：执行层 role 退出时若 `progress/<role>.md` 缺 SIT 证据段则阻断。
7. **`PreToolUse` (TaskCreate) — `validate-task-schema.sh`**：派单前校验 task 6 段齐全（description / 上下游产物 / AC 等），漏字段阻断。

撞到硬阻断时按 `.claude/standards/security.md` "No Equivalent Bypass" 处理（不得寻找等价绕过）。

## Team Runtime Contract

本项目复用 `.claude/` 中的 AI 团队模板。权威来源：
- 角色与协作边界：`.claude/standards/team-roles.md`
- 工作流（含 Parallel Dispatch + worktree 强制）：`.claude/standards/workflow.md`
- 文档与单一来源原则：`.claude/standards/document-rules.md`
- Superpowers 使用规范：`.claude/standards/superpowers.md`
- 测试与验收：`.claude/standards/testing.md`、`.claude/standards/ac-lifecycle.md`
- 编码与安全：`.claude/standards/coding.md`、`.claude/standards/security.md`
- 观测与成本：`.claude/standards/observability.md`、`.claude/standards/cost-budget.md`
- 版本与发布：`.claude/standards/versioning.md`（SemVer 应用细则 + release 流程）
- 对话回复风格：`.claude/standards/communication.md`（所有 agent 面向人的回复精简，docs 产出物不受影响）

仓库目录约定见 `.claude/rules/repo-layout.md`；Team Mode 启动协议（≥2 角色 / 跨链路任务必须 spawn agent team）见 `.claude/rules/team-mode.md`——两者按 path 自动加载。

运行时关键约束（摘要，细则以权威来源为准）：

- `.claude/standards/team-roles.md` 是角色额外工具与预加载 skills 的唯一团队级能力基线；表中 `Permission` 列是**团队约定的"推荐运行模式"**，并非 Claude Code 官方 sub-agent frontmatter 字段。
- `product-lead` 是唯一流程编排者；`tech-lead` 仅在缺少基线、新技术选型或架构风险升级时强制介入。
- 会话入口判断（直接执行 vs 派给 `product-lead`）见 `.claude/standards/workflow.md` "Session Entry" 节。
- 交付链路固定为 `代码实现 + Unit + SIT 自跑 → code review (含 SIT Audit) → E2E → UAT`；任一阶段失败后由 `product-lead` 重新分派执行层修复。
- `code-reviewer` 为 review-only 角色；`qa-engineer` 负责执行 E2E / UAT 并提交报告（集成层 SIT 由 dev 自跑、reviewer 审证据），最终业务签字由 `product-lead` 完成。
- `backend-dev` / `ai-agent-dev` 在高风险变更（schema 迁移、认证逻辑、LLM 提供商切换、生产 prompt 变更等）必须先进 Plan Mode 拿 product-lead 授权。
- token 消耗与成本按 `.claude/standards/cost-budget.md` 分级（含会话规模上限、cache 利用率 ≥ 60% 与全 agent 默认 model 路由）；如需查看本次会话用量，跑 Claude Code 内置 `/usage`。
- 对话回复一律按 `.claude/standards/communication.md` 执行；写入 `docs/` 的产出物不压缩。
- 交易相关代码修改涉及真实资金风险 → 修改前必须 Plan Mode + tech-lead review。

若本文件中的项目规则与团队规范冲突，以本文件为准。
