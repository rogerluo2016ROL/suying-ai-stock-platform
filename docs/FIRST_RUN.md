# Day-1 Checklist — 接手这个模板的第一天

> 15 个角色（10 通用 + 3 小程序 + 2 post-launch）的 Claude Code Agent Team 模板。把 `.claude/` 整套搬到新仓库后，按本文逐项过一遍即可上路。完整设计背景见仓库根 [`README.md`](../README.md)。

---

## 0. 前置知识

### 必备（缺了跑不通）

| 知识 | 用在哪 | 最低要求 |
|---|---|---|
| **Git** | worktree 强制（≥2 并行 teammate）、`scan-commit` pre-commit hook、PR/merge | `status / diff / log / commit / push / pull / merge` + 懂 working tree / staging / commit 三态；不需要 rebase / cherry-pick |
| **命令行（zsh / bash）** | `setup/init-team.sh`、`bash .claude/scripts/archive-progress.sh` | 跑命令 + 读 stderr，不需要写脚本 |
| **Claude Code ≥ v2.1.154** | 全套 `.claude/` 依赖 | Agent Teams flag 启用（`setup/init-team.sh` 自检） |
| **Markdown** | 所有 PRD / 报告 / ADR 都是 Markdown | 标题 / 列表 / 表格 / 代码块 / 链接 |

### 强烈推荐（缺了会反复被打回）

- **PRD + Acceptance Criteria 概念** — `product-lead` 强制 `superpowers:brainstorming` 让你回答"AC 怎么验"
- **三级测试 SIT / E2E / UAT 差别** — 阶段门按顺序走，跳级会被拦
- **Mermaid 流程图阅读** — [`docs/team-capability-map.md` §1 全景图](./team-capability-map.md) 必看
- **TDD 思路** — 执行层强制 `superpowers:test-driven-development`，测试和代码同提交不要疑惑
- **Conventional Commits** — `feat(scope): / fix(scope): / docs(scope):` 决定 CHANGELOG 和版本号判定

### 按场景才需要（用到再学）

| 场景 | 需要懂 |
|---|---|
| Review backend 代码 | Python / FastAPI / SQLAlchemy / Alembic |
| Review frontend 代码 | React + Vite + TypeScript |
| 走 miniapp 链路 | 微信小程序 + 原生 WXML/WXSS + Taro |
| Review AI agent 输出 | prompt 工程 + RAG 概念 |
| 走多模态推理 | 豆包 / 可灵 / MiniMax Video API |
| 合并 main 前判定版本号 | SemVer + Keep a Changelog |
| 跑 evals 漂移巡检 | `jq` |
| Agent Team split panes 显示 | macOS + iTerm2 / tmux |

### 不需要懂

cost-budget 自动核账、hook 实现细节（撞到走 PL 授权）、subagent vs Agent Teams 运行时差异、多 LLM SDK 各家 API 差异（`agf-wiring-multi-llm-sdk` skill 兜底）。

### 推荐入职路径（半天）

1. **30 min** — 装 Claude Code，跑 `bash setup/init-team.sh`，看 10 项校验过完
2. **30 min** — 读 [`README.md`](../README.md)（300 行）+ [`team-capability-map.md` §1 全景图](./team-capability-map.md)（看图就行）
3. **1 h** — 跑 `/agf-team-start <一个真实小需求>`，看 `product-lead` 怎么逼你澄清 AC
4. **1 h** — 故意让 SIT fail（改测试预期值），看失败回路如何回到执行层
5. **1 h** — 看 [`docs/training/samples/postcard-feature/`](training/samples/postcard-feature/) 端到端走通的产物（PRD / ADR / Dispatch / Progress / Review (含 SIT Audit) / UAT / Retro / Release notes 全套；SIT 证据落 `progress/<role>.md`，不再独立成 SIT 报告；路径为教学示意）

---

## 1. 一键初始化（必须）

```bash
bash setup/init-team.sh
```

自动验证：
- ✅ Claude Code 版本 ≥ v2.1.154
- ✅ Hook 可执行权限 + 回归测试（`.claude/hooks/tests/` 全部 `test-*.sh`）
- ✅ `.claude/settings.json` JSON 合法性
- ✅ `CLAUDE.md` / `docs/adr/000-system-architecture.md` / git 状态
- ⚠️ 列出待人工处理项（见下文 §2-§4）

跑完后版本检查 + Hook 验证已覆盖；§2、§3、§4、§5 仍需人工。

> **chrome-devtools-mcp（项目级，已在 `.mcp.json` 声明）**：`qa-engineer` 跑 E2E 浏览器测试需要的 `chrome-devtools` MCP server 已通过项目根 `.mcp.json` 自动加载（`npx -y chrome-devtools-mcp@latest`），团队 clone 后**直接可用**，前置仅需本机有 `node` + `npx`。所有 agent 路径（含 Agent Team teammate）都能拿到该 server。
>
> 不跑 E2E 浏览器测试（只跑 SIT API 测试 / UAT 业务签字）的项目，可在 `.mcp.json` 删除 `chrome-devtools` 条目，qa-engineer 其他能力不受影响。
>
> 如需 plugin 形态的 `/chrome-devtools-mcp:*` slash command（独立于本 MCP server），另行 `/plugin install chrome-devtools-mcp`；plugin 不装不影响 `.mcp.json` 提供的 server。

> **security-guidance plugin（强烈推荐 · 第 5 层防御）**：Anthropic 原生免费，`PreToolUse` hook 在 Write/Edit 时自动拦**代码级危险模式**（`eval`/XSS/`pickle`/`os.system`/`child_process`/GH Actions 注入等，AGF 四层 hook 不覆盖）。装一次：`/plugin install security-guidance@claude-plugins-official`。优雅降级——未装不影响 AGF 四层 + 手工 OWASP，详 [`security.md`](../.claude/standards/security.md) "第 5 层"。

## 2. 校准权限白名单（必须）

打开 `.claude/settings.json`，把 `permissions.allow` 改成项目实际用的命令。默认基线：

- 前端：`pnpm test/lint/build/typecheck/install`
- 后端：`pytest`、`ruff`、`black`、`alembic`、`docker compose`
- Git：只读（`status`、`diff`、`log`）

常见调整：
- 用 npm/yarn → 把 `pnpm *` 改成 `npm *` 或 `yarn *`
- 不用 alembic → 删 `Bash(alembic*)`
- 用 poetry → 加 `Bash(poetry*)`

## 3. 写 CLAUDE.md（必须）

复制 `CLAUDE.example.md` 为根目录 `CLAUDE.md`，按项目内容填。`Tech Stack` 节只放版本号摘要 + ADR 链接，决策理由由 ADR 承载（单一来源原则）。

> Team Mode 协议、仓库目录约定不在 `CLAUDE.md` 描述 — 它们在 [`.claude/rules/team-mode.md`](../.claude/rules/team-mode.md) 和 [`.claude/rules/repo-layout.md`](../.claude/rules/repo-layout.md)，按 path 自动加载，无需在 `CLAUDE.md` 重复。

## 4. 处理 ADR-000（必须三选一）

`docs/adr/000-system-architecture.md` 是模板示例，三种处理方式：

- **A 方案（新项目，推荐）**：让 `tech-lead` 起新版
  ```
  请启动 tech-lead，为本项目起 ADR-000 固化技术栈
  ```
- **B 方案（接手老代码库）**：让 `tech-lead` 基于现有代码识别基线
  ```
  请启动 tech-lead，本项目已有代码：
  1. 扫描仓库识别实际技术栈
  2. 输出 ADR-000 固化「现状基线」而非「理想选型」
  3. 同步更新 CLAUDE.md 的 Tech Stack 表
  ```
- **C 方案**：直接删除该文件（首个 feature 启动时 `tech-lead` 会按需补）

## 5. 试跑 `/agf-team-start`（必须）

```text
/agf-team-start <你的第一个 feature 描述>
```

主 Claude 会按 [`team-mode.md`](../.claude/rules/team-mode.md) 协议 spawn `product-lead` + 必要的 teammate，验证整套链路通畅。建议挑一个真实小需求（例如"加个 about 页"）。

---

## 6. （可选）启用 OTEL 观测

做 Agent Team 长期运维时，按 [`observability.md`](../.claude/standards/observability.md) 把 `.claude/settings.json` 的 `_OTEL_EXAMPLE_*` 占位改成正式键名 + 起 OTEL collector。

## 7. （可选）启用 MCP server

`.claude/settings.json` 末尾有 MCP server 范本（`gh` + `postgres`），按需启用：
- 装 `gh-mcp-server` / `@modelcontextprotocol/server-postgres`
- 把 `_mcpServers_example` 块改名为 `mcpServers`

## 8. （可选）Agent Team 显示模式

macOS：装 [iTerm2 + `it2` CLI](https://github.com/mkusaka/it2) 或 tmux，让 `teammateMode: "auto"` 自动用 split panes 展示多个 teammate。不装也能跑，回退 in-process 模式。

## 9. （可选）GitHub Actions

`.github/workflows/claude-code.yml` 是模板，**默认不启用**。要启用：
1. 安装 [Claude Code GitHub App](https://github.com/apps/claude-code)
2. Settings → Secrets → 添加 `ANTHROPIC_API_KEY`
3. 默认配置只在 PR 加 `claude-review` label 时跑 PR review，避免每次 push 都烧 token

---

## 常见踩坑

| 现象 | 原因 | 解决 |
|---|---|---|
| `/agf-team-start` 没反应 | 没启用 `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` | 检查 `.claude/settings.json` 的 `env` 块 |
| Hook 不拦截危险命令 | `.claude/settings.json` 没注册 `PreToolUse` | 看 `hooks` 块是否有 `block-dangerous-bash.sh` 注册 |
| 密钥粘进 prompt 没被拦 | `jq` 未安装 / hook 没可执行权限 | `chmod +x .claude/hooks/*.sh` + `which jq` |
| `product-lead` 自己开始写代码 | 角色漂移 | 跑 `bash evals/run.sh checklist 5 --role product-lead` 抽检 |
| token 消耗远超预期 | cache hit < 50% | 看 [`cost-budget.md`](../.claude/standards/cost-budget.md) 的优化建议 |
| Agent Team 和 subagent 该选哪个 | 跨角色/跨链路用 team；单点小事用 subagent | 看 [`workflow.md`](../.claude/standards/workflow.md) "Session Entry" 节 |
| teammate 提前 idle | `TeammateIdle` hook 阻断（task list 还有 pending） | 把 task 标记完成或调整状态 |
| 执行层完成报告被 hook 拦 | `progress/<role>.md` 没 append 完整条目 | 按 [`ac-lifecycle.md` Self-Reporting Pattern](../.claude/standards/ac-lifecycle.md) 补写 |
| 项目 task / 历史 / 缓存乱了想重置 | 多次失败 dispatch 残留 task list / shell snapshots / file history | `claude project purge .` 清除本项目所有 Claude Code 状态（transcripts / tasks / file history / config 入口）；可先 `--dry-run` 查看影响，确认后 `-y` |

## 相关文档

- 模板说明 + 15 角色一览：[`README.md`](../README.md)
- 端到端管道全景图：[`team-capability-map.md` §1](./team-capability-map.md)
- 角色与能力基线：[`team-roles.md`](../.claude/standards/team-roles.md)
- 工作流 + Session Entry 判断：[`workflow.md`](../.claude/standards/workflow.md)
- LLM 行为铁律：[`coding.md`](../.claude/standards/coding.md)
- 测试规范：[`testing.md`](../.claude/standards/testing.md) + [`ac-lifecycle.md`](../.claude/standards/ac-lifecycle.md)
