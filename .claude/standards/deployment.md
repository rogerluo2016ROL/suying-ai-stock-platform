# Deployment Standards

> 本规范聚焦**容器化部署修复的验证门**——适用于全栈 Docker Compose 化项目（典型架构 caddy + frontend + backend + worker + postgres + redis）。任何 `gh issue close` 涉及容器内代码 / 配置变更的 fix，必须满足本规范"容器/服务重建后 curl 实证修复生效"门槛。

**触发来源**：`docs/reviews/issue-audit-2026-05-16.md` Systemic Pattern 2 "Premature Close" — #37 i2i retry 422 修复，**代码 commit (`dc512fa`) 但容器未重建** → close 时修复实际未上线，#39 hot-fix 才含真正容器重建（`fe9ab58`）。本节是防同类 Premature Close 的强制门。

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

**判定原则**：若变更最终要进 docker image 或被容器 process 读取，**必须**容器重建后实证；只动文档 / `.claude/` / 宿主机 dev 工具的，不触发。

## 2. P0 / P1 修复 Close 前的强制门

任何 close `priority:P0` / `priority:P1` 的 bug fix issue 前，product-lead 必须完成以下 3 步并把证据写入 close 公告：

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

- 重建命令必须出现在 `## 1. Setup / 重建命令` 段（贴出实际跑的 `docker compose up -d --build <services>`）
- AC 边界 curl 输出粘贴到 `## 3. Evidence (curl + 时间戳)` 段
- 容器重建 commit-sha 与代码 commit 不同步时在 `## 1.` 段分列两条
- "未覆盖 scope" 写到 `## 5. 已知未覆盖 / 后续 follow-up` 段

完整模板与禁用 Evidence 形式见 [`.claude/standards/qa-close-verify.md`](./qa-close-verify.md) §2.2 / §3。

## 3. cron-driven feature 容器验证（与 testing.md E2E 节配套）

cron / scheduled task 类 feature（如 `fan_out_topics_task` / `enrich_watch_specs` / `materials_archive_cron`）的容器验证额外要求：

1. **cron 注册实证**：`docker compose exec worker python -c "from app.workers import scheduler; print(scheduler.tasks)"` 或等效命令，confirm 新 task 名出现在 registered 列表
2. **手动触发 tick**：用 `docker compose exec backend python -m app.cli ...` 或 taskiq client / Redis enqueue API **手动 push 一次** task，**不要**等真实 cron tick（cron 周期通常 ≥ 1h，等不起也漏不出来）
3. **消费链路 assertion**：tick 后 `docker compose logs worker --since 30s` 或查目标表 / Redis key，confirm 副作用已写入（**正是 #16 漏的层**——schema 通过 SIT 但 cron tick + 消费链路零覆盖）

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
- **运维 SOP**：`docs/runbooks/deploy.md` 是日常部署 runbook，本规范是 close issue 前的验证门，两者不重复
