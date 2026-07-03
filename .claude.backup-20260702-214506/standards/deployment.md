# Deployment Standards

> 本规范聚焦**容器化部署修复的验证门**——适用于全栈 Docker Compose 化项目（典型架构 caddy + frontend + backend + worker + postgres + redis）。任何 `gh issue close` 涉及容器内代码 / 配置变更的 fix，必须满足本规范"容器/服务重建后 curl 实证修复生效"门槛。

**触发来源**：RolexOps 实战 issue audit（不随模板分发）Systemic Pattern 2 "Premature Close" — 修复代码已 commit 但容器未重建 → close 时修复实际未上线，后续 hot-fix 才含真正容器重建。本节是防同类 Premature Close 的强制门。

## 1. 适用范围

| 类型 | 是否触发本规范 | 备注 |
|---|---|---|
| `backend/app/**` Python 代码 | ✅ 是 | uvicorn / taskiq worker 都在容器内跑 |
| `frontend/src/**` TS/TSX 代码 | ✅ 是 | Vite build 产物烘焙进 caddy 容器 |
| `alembic/versions/**` migration | ✅ 是 | upgrade 必须容器内 `alembic upgrade head` |
| `models.toml` / `prompts/**` | ✅ 是 | 容器 image 内固化或 bind-mount 取决于配置 |
| `docker-compose.yml` / `Dockerfile.*` | ✅ 是 | compose 配置变更必须 `up -d --build` 双验 |
| `.claude/**` / `docs/**` / `progress/**` | ❌ 否 | 纯文档 / agent 配置，不入运行时容器 |
| `e2e/**` Playwright 测试 | ❌ 否 | 宿主机跑，不打容器 image |

**判定原则**：变更最终要进 docker image 或被容器 process 读取的，**必须**容器重建后实证；只动文档 / `.claude/` / 宿主机 dev 工具的不触发。

## 2. P0 / P1 修复 Close 前的强制门

close `priority:P0` / `priority:P1` 的 bug fix issue 前，product-lead 必须完成以下 3 步并把证据写入 close 公告：

### Step 1: 容器重建

```bash
# 全栈重建（保险但慢）
docker compose up -d --build

# 或精确重建受影响服务（更快，确认服务清单后再用）
docker compose up -d --build <service-name>  # backend / worker / frontend / caddy
```

**禁止**：仅 `docker compose restart <service>`——restart 只重启 process 不重建 image，新代码不会进容器（**正是 #37 的失败模式**）。

### Step 2: curl 实证 AC 边界（真实输出，非 dry-run）

对照 issue / PRD AC 边界跑真实 curl，捕获完整响应。常见 AC 边界类型与命令样本：

- **HTTP 状态码边界**（如 #39 cost ¥301.76 触发 422）：
  ```bash
  curl -sS -w "\nHTTP %{http_code}\n" -X POST http://localhost:8000/api/<endpoint> \
    -H "Content-Type: application/json" \
    --cookie cookies.txt \
    -d '{"<edge-case-payload>"}'
  ```
- **错误 detail 文案**（中文 / 业务码）：grep curl 输出含期望文案
- **数据写入 verify**（migration / 业务表）：`docker compose exec backend python -c "from app.db import ..."` 或 `docker compose exec postgres psql -U <user> -d <db> -c "SELECT ..."`
- **cron / worker 触发后果**：见下文 §3 "cron-driven feature 容器验证"
- **前端 fix 边界**：用 chrome-devtools MCP 或 Playwright 跑 happy + edge path，截图存档

**真实输出原则**：close 公告必须贴 curl 实际响应片段（含 HTTP 状态码 / response body 关键字段），**不接受**"dry-run pass" / "本地 unit 已通过" / "代码 grep 看着对" 这类间接证据。

### Step 3: close 公告自报

**强制使用 `qa-close-verify.md §3` 定义的统一模板 `## Close Verify Report — Issue #[N]`**（本文件不再自定义独立段名），并满足以下容器场景额外要求：

- 重建命令必须出现在 `### 容器重建验证` 段（贴出实际跑的 `docker compose up --build -d <services>`）
- AC 边界 curl 输出粘贴到 `### AC 边界验证` 段的"命令输出（重建后）"
- 容器重建 commit-sha 与代码 commit 不同步时在 `### 修复定位` 段分列两条
- "未覆盖 scope" 写到 `### Notes（可选）` 段

完整模板与禁用 Evidence 形式见 [`.claude/standards/qa-close-verify.md`](./qa-close-verify.md) §2.2 / §3。

## 3. cron-driven feature 容器验证（与 testing.md E2E 节配套）

cron / scheduled task 类 feature（定义与示例见 [`testing.md`](./testing.md) cron-driven feature 节）的容器验证额外要求：

1. **cron 注册实证**：`docker compose exec worker python -c "from app.workers import scheduler; print(scheduler.tasks)"` 或等效命令，confirm 新 task 名出现在 registered 列表
2. **手动触发 tick**：用 `docker compose exec backend python -m app.cli ...` 或 taskiq client / Redis enqueue API **手动 push 一次** task，**不要**等真实 cron tick（cron 周期通常 ≥ 1h，等不起也漏不出来）
3. **消费链路 assertion**：tick 后 `docker compose logs worker --since 30s` 或查目标表 / Redis key，confirm 副作用已写入（**正是 #16 漏的层**——schema 过 SIT 但 cron tick + 消费链路零覆盖）

详细测试规范见 [`.claude/standards/testing.md`](./testing.md) "Cron-Driven Feature E2E" 节。

## 4. 反例 / 历史 incident

> 以下 incident 摘自 RolexOps 项目实战经历（AGF 模板继承的实证教训），具体 issue # / commit hash 仅为来源标识；下游 fork 用户读时关注**失败模式**与**教训**的方法论。

| 日期 | 失败模式 | 教训 |
|---|---|---|
| 2026-05-15 | 代码已 commit 但容器未重建 → close 公告失实，hot-fix PR 才真上线 | close P0/P1 前必须 `docker compose up -d --build` + curl 边界实证；本规范由此立项 |
| 2026-05-14 | BE schema + cron 注册通过 SIT，但 cron tick + worker signature + LLM prompt + FE 接入 4 处端到端零覆盖 → close 公告"SHIPPED"与实际不可用严重背离 | §3 cron-driven feature 必须 tick + 消费链路实证；不允许"BE schema ship 即声明 feature SHIPPED" |

## 5. 与其他规范的关系

- **关 issue 流程**：`.claude/standards/workflow.md` "Issue Close DoD" §3 引用本规范
- **测试规范**：`.claude/standards/testing.md` "Cron-Driven Feature E2E" 节定义测试层；本规范定义部署验证层
- **运维 SOP**：日常部署操作手册（运维 runbook，首个真实部署 feature 时落地）与本规范分工——本规范是 close issue 前的验证门，不替代日常 runbook
- **UAT 环境部署**：下文 §6 "UAT 环境部署" 定义合并到 main 后由 `deploy-engineer` 起隔离 UAT 栈的契约（端口偏移 + 独立 compose project）；与本文件上文「容器重建 + curl 实证」实证原则同源，分步 runbook 在 skill `agf-deploying-uat`

## 6. UAT 环境部署（隔离栈契约）

> 本节是**隔离 UAT 栈契约的单一来源**，由 `deploy-engineer` 在 code review（含 SIT Audit）通过 **+ 合并到 main 后**执行。分步 runbook（前置检查 / 起栈 / 迁移 / 冒烟 / 交接 / 报告骨架）**不在此复述**，见 skill [`agf-deploying-uat`](../skills/agf-deploying-uat/SKILL.md)——单一来源：**契约在此 standard，runbook 在 skill**。交付链路位置与失败回路见 [`workflow.md`](workflow.md) "部署门" 节。

### 6.1 为什么要隔离

E2E / UAT 若跑在开发者本地 worktree 上，dev 常开多个 `git worktree` 并行调试，端口 / 容器 / DB 状态互相污染，QA 对"脏"环境测、结论不可信。故在**合并到 main 后**部署一个与所有 dev worktree **物理隔离**的 UAT 栈，QA 改对这个稳定环境测。

### 6.2 隔离机制（下游 `docker-compose.yml` 必须遵守的约定）

```bash
export COMPOSE_PROJECT_NAME=${APP_NAME}-uat   # 独立 compose project → 容器 / 网络 / 卷全独立
export UAT_PORT_OFFSET=900                     # 端口偏移，避开 dev(base) 与 QA pool(base+100..+700)
docker compose -p "$COMPOSE_PROJECT_NAME" --env-file .env.uat up -d --build
```

- **独立 compose project name** `${APP_NAME}-uat`：`-p` 让容器 / 网络 / 卷全部带 `<app>-uat` 前缀，与 dev / QA 栈物理隔离。
- **端口偏移 `UAT_PORT_OFFSET=900`**——本节是这些**字面端口值的权威来源**；**非 runbook 文档**只引用语义或指向本节、不复述数字，而 skill `agf-deploying-uat` / `deploy-engineer` 的运维命令（起栈、curl 冒烟）按需带字面端口属正常 runbook 用法：

  | 服务 | UAT 端口（base + 900） |
  |---|---|
  | Postgres | 6332 |
  | Backend (API) | 8900 |
  | Frontend (caddy) | 8980 |

- **端口带不重叠**：dev 用 base、QA pool 用 base+N×100（N=1..7，见 [`workflow.md` §Worktree 与 Docker 隔离](workflow.md)）、**UAT 固定 +900**，三者互不重叠（即便 QA pool 升到 Large=7，base+700 仍 < +900，安全）。
- **下游约定**：当前模板无 app 代码 → 上述是未来 `docker-compose.yml` 必须满足的契约——**端口由 env 驱动**（消费 `UAT_PORT_OFFSET`）+ **支持 `-p` project name 隔离**。

### 6.3 `.env.uat`（UAT 专用环境变量，不入库）

- UAT 专用环境变量文件（DB 连接、LLM key、端口偏移消费等，**含密钥**）。
- **必须 gitignore，不入库**（根 `.gitignore` 的 `.env*` 规则已覆盖；坐实"密钥不进仓库"）。
- 部署前置检查必须确认其存在；缺失 → 阻断，由 product-lead 协调补齐（见 skill 前置检查段）。

### 6.4 远程 SSH 部署（未来变体）

本节契约聚焦**本地隔离 Docker Compose**。远程 SSH 部署（staging / prod 拓扑、密钥分发、回滚策略等）属未来扩展，**变体见未来 ADR**（届时由 `tech-lead` 撰写），本规范不预先约束。

## 7. Apple 发布（签名分发契约，与 §6 docker UAT 并列）

> Apple 轨的"部署"是**构建签名分发包**，不是起容器栈。本节是该契约的单一来源；流水线选型与渠道矩阵见 [ADR-009](../../docs/adr/009-apple-release-pipeline.md)，分步 runbook 在 skill [`agf-releasing-apple`](../skills/agf-releasing-apple/SKILL.md)——单一来源：**契约在此 standard，决策在 ADR，runbook 在 skill**。

### 7.1 触发与责任

- 触发时机与 §6 同位：code review（含 SIT Audit）通过 + 合并到 main 后，由 `apple-release-engineer` 执行（Pool=1，唯一签名身份）。
- 手动触发：`/agf-apple-release`。

### 7.2 渠道 → lane 映射（PRD 声明渠道，release task 按表选 lane）

| 渠道 | fastlane lane | QA 测试目标 |
|---|---|---|
| TestFlight 内测（iOS / macOS） | `beta` | TestFlight build 号 |
| App Store 上架 | `release_appstore` | 提审前的 TestFlight build |
| macOS 直发 | `release_dmg` | 公证后的 DMG（本地路径） |
| 企业 / 内部 | `release_internal` | 内部分发包路径 |

### 7.3 硬约束

- **签名材料不入库**：`.p8` API key / `.p12` 证书 / match 仓密码走环境变量或 Keychain（`scan-secrets.sh` + `pre-commit` 已扩展 Apple 模式拦截）。
- **二元 gate**：`✅ 构建成功（冒烟通过）` / `❌ 构建失败`，不发明新 verdict；冒烟 = 装包启动 + 关键路径点查。
- **报告**：`docs/deploy/<feature>-apple-<YYYY-MM-DD>.md`（含分发包定位 / 冒烟证据 / 构建 commit SHA / gate 结论）；`apple-qa-engineer` 读它拿测试目标。
- **失败回路**：代码层失败 → product-lead → apple-dev；签名 / 公证 / 构建配置层 → apple-release-engineer 自己重跑。
