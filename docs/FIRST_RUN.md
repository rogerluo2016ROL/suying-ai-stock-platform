# Day-1 — 装好 AGF 之后

> 你是用 `bash setup/install-to-existing.sh <target>`（非交互）把 AGF 装进项目的，随后的 **`/agf-init`** 帮你跑完初始化——体检、合并 CLAUDE.md 团队段、据项目实际技术栈写 ADR-000、建 gh label、清理安装残留。（原 TUI 安装器 `agf-install.sh` 已按 ADR-026 D3 退役，入口统一为「非交互脚本 + Claude 接管」。）
>
> 本文讲三件事：**`/agf-init` 做了什么 + 你要复核什么**（§1）、**怎么跑第一个 feature**（§3）、**常见踩坑**（文末）。
>
> 还没装？在 AGF 仓库根跑 `bash setup/install-to-existing.sh <target>`。完整设计背景见 AGF 仓库 README。

---

## 0. 前置知识

### 必备（缺了跑不通）

| 知识 | 用在哪 | 最低要求 |
|---|---|---|
| **Git** | worktree 强制（≥2 并行 teammate）、`scan-commit` pre-commit hook、PR/merge | `status / diff / log / commit / push / pull / merge` + 懂 working tree / staging / commit 三态；不需要 rebase / cherry-pick |
| **命令行（zsh / bash）** | `setup/*.sh`、`bash .claude/scripts/archive-progress.sh` | 跑命令 + 读 stderr，不需要写脚本 |
| **Claude Code ≥ v2.1.154** | 全套 `.claude/` 依赖 | Agent Teams flag 启用（`setup/init-team.sh` 自检） |
| **Markdown** | 所有 PRD / 报告 / ADR 都是 Markdown | 标题 / 列表 / 表格 / 代码块 |

### 强烈推荐（缺了会反复被打回）

- **变更文件夹 + Acceptance Criteria 概念**（需求入口，[ADR-012](adr/012-spec-driven-change-folders.md)）— 需求入口是 `docs/changes/<change>/`（proposal+delta+design+tasks，skill `agf-writing-change`，取代 PRD）；`product-lead` 强制 `superpowers:brainstorming` 让你回答"AC 怎么验"；AC 源自 delta 的 `#### Scenario`（WHEN/THEN，可选 AND）。PRD 弃用 fallback。
- **三级测试 SIT / E2E / UAT 差别** — 阶段门按顺序走，跳级会被拦
- **Mermaid 流程图阅读** — `team-capability-map.md` §1 全景图必看
- **TDD 思路** — 执行层强制 `superpowers:test-driven-development`，测试和代码同提交不要疑惑
- **Conventional Commits** — `feat(scope): / fix(scope): / docs(scope):` 决定 CHANGELOG 和版本号判定

### 按场景才需要（用到再学）

| 场景 | 需要懂 |
|---|---|
| Review backend 代码 | 项目实际后端栈（默认 Python / FastAPI / SQLAlchemy / Alembic，以你的 ADR-000 为准） |
| Review frontend 代码 | 项目实际前端栈（默认 React + Vite + TypeScript） |
| 走 miniapp 链路 | 微信小程序 + 原生 WXML/WXSS + Taro |
| Review AI agent 输出 | prompt 工程 + RAG 概念 |
| 合并 main 前判定版本号 | SemVer + Keep a Changelog |
| Agent Team split panes 显示（默认 auto） | iTerm2/tmux 会话自动分屏；想强制 iTerm2 fail-loud 需 `it2` |

### 不需要懂

cost-budget 自动核账、hook 实现细节（撞到走 PL 授权）、subagent vs Agent Teams 运行时差异、多 LLM SDK 各家 API 差异（`agf-wiring-multi-llm-sdk` skill 兜底）。

---

## 1. `/agf-init` 帮你做了什么 + 你要复核什么（必须）

`/agf-init` 在安装完成页自动接管了初始化。它做的 + 你装完后**必须复核**的：

| /agf-init 自动做了 | 你要复核 |
|---|---|
| 跑 `setup/init-team.sh` 体检（版本 / hook / settings.json）+ 自动修可修项 | 完成页若报体检有失败项，按提示处理 |
| 合并 CLAUDE.md 团队基础设施段（保留你的 Project Overview / Tech Stack） | 打开 `CLAUDE.md`，确认项目段没被覆盖、团队段已并入 |
| **据项目实际栈写 ADR-000**（brownfield 先 `/agf-code-map understand` 扫描 + 逐条 grep 核实；greenfield 问你选型） | ⚠️ **重点：打开 `docs/adr/000-system-architecture.md`，核对语言/框架/DB/版本是不是你项目真实的**——/agf-init 写完会交代"栈据什么定的（扫了哪几个 manifest）"，对不上就让它重写。这是防 AI 编技术栈的最后一道人工关 |
| 建 gh label 核心子集（type/area/priority/severity/phase/status） | （GitHub 仓才有）`gh label list` 看一眼 |
| 清理 `*.agf-template` / `*.backup-*` / NEXT_STEPS | 确认没误删你的东西 |

> **没用 `/agf-init`、想手动？** fallback：`bash setup/init-team.sh`（体检）→ 手动把 `CLAUDE.md.agf-template` 的团队段并进 `CLAUDE.md` → 手动据实际栈写 `docs/adr/000-system-architecture.md`（参考 `CLAUDE.example.md` 与 `agf-writing-adr` skill）。详见 `AGF_INSTALL_NEXT_STEPS.md` 的「手工 fallback」节。

## 2. 校准权限白名单（必须手动 — /agf-init 不改权限）

打开 `.claude/settings.json`，把 `permissions.allow` 改成项目实际用的命令。默认基线：

- 前端：`pnpm test/lint/build/typecheck/install`
- 后端：`pytest`、`ruff`、`black`、`alembic`、`docker compose`
- Git：只读（`status`、`diff`、`log`）

常见调整：用 npm/yarn → 把 `pnpm *` 改成 `npm *` / `yarn *`；不用 alembic → 删 `Bash(alembic*)`；用 poetry → 加 `Bash(poetry*)`。

## 3. 跑第一个 feature（必须 — 验证整套链路）

```text
/agf-team-start <你的第一个 feature 描述>
```

主 Claude 按 `.claude/rules/team-mode.md` 协议 spawn `product-lead` + 必要 teammate，验证整套链路通畅。建议挑一个真实小需求（例如"加个 about 页"），看 `product-lead` 怎么逼你澄清 AC、SIT fail 时怎么回到执行层。

> **MCP（chrome-devtools，qa-engineer 跑 E2E 用）**：已通过项目根 `.mcp.json` 声明（`npx -y chrome-devtools-mcp@latest`），clone 后**直接可用**，前置仅需本机有 `node` + `npx`，所有 agent 路径（含 teammate）都能拿到。不跑浏览器 E2E 的项目可在 `.mcp.json` 删 `chrome-devtools` 条目。
>
> **security-guidance plugin（强烈推荐 · 第 5 层防御）**：Anthropic 原生免费，`PreToolUse` hook 在 Write/Edit 时自动拦代码级危险模式（`eval`/XSS/`pickle`/`os.system` 等，AGF 四层 hook 不覆盖）。装一次：`/plugin install security-guidance@claude-plugins-official`。未装不影响 AGF 四层。

---

## 可选增强

- **OTEL 观测**：长期运维时按 `.claude/standards/observability.md` 把 `.claude/settings.json` 的 `_OTEL_EXAMPLE_*` 占位改成正式键名 + 起 OTEL collector。
- **Agent Team split panes 显示**（macOS）：模板默认 `teammateMode: "auto"`（见 [ADR-022](adr/022-agent-teams-upstream-dependency.md)）——iTerm2 / tmux 会话出原生分屏、其余终端静默 in-process（不影响功能）。想强制 iTerm2 分屏 fail-loud 的用户在**用户级** `~/.claude/settings.json` 设 `"iterm2"`（前置 `pip install it2` + iTerm2 → Settings → General → Magic → Enable Python API + Claude Code ≥ v2.1.186；缺 it2 会显式报错，刻意为之以免"以为开了分屏其实没开"）。模板 min 仍 v2.1.154（Teams 实验功能不抬 min）。细节见 `.claude/rules/team-mode.md`。
- **GitHub Actions**：`.github/workflows/claude-code.yml.template` 是模板，**默认不启用**（`.template` 后缀不被 GitHub 注册）。启用需改名为 `claude-code.yml` + 装 Claude Code GitHub App + 加 `ANTHROPIC_API_KEY` secret；默认只在 PR 加 `claude-review` label 时跑，避免每次 push 烧 token。

---

## 常见踩坑

| 现象 | 原因 | 解决 |
|---|---|---|
| `/agf-team-start` 没反应 | 没启用 `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` | 检查 `.claude/settings.json` 的 `env` 块 |
| `/agf-code-map` 找不到 | `tools/codemap/` 没装入或未 `uv sync`（老版本 install 漏拷） | 从 AGF 仓库补拷 `tools/codemap/`，`cd tools/codemap && uv sync` |
| Hook 不拦截危险命令 / 不校验 task / 不守 verdict | `.claude/settings.json` 的 `hooks` 块注册缺失 | 对照 [`security.md`](../.claude/standards/security.md) 四层防御表 + CLAUDE.md「Tool Boundaries」9 个 hook 清单，逐个核 `settings.json` 是否注册（`block-dangerous-bash` / `block-config-edit` / `enforce-write-scope` / `scan-secrets` / `sanitize-tool-output` / `scan-commit` / `validate-task-schema` / `gate-deploy-release-auth` / `gate-redo-fuse` / `validate-verdict` 等）；缺则从 AGF 仓库补拷 `hooks` 块 |
| 密钥粘进 prompt 没被拦 | `jq` 未安装 / hook 没可执行权限 | `chmod +x .claude/hooks/*.sh` + `which jq` |
| `lint-all` / `git commit` 被**诚实层门**挡（`claims-audit` / `deny-baseline` 报 exit 2） | CLAUDE.md 点名的脚本不存在 / 已注册 hook 缺脚本（幽灵声称）；或 `permissions.deny` 被改小 / baseline 未签 | 按门的 stderr 提示修 doc-drift 或补脚本；deny 有意变更后跑 `bash .claude/scripts/agf-deny-baseline.sh --update` 重签（[ADR-023](adr/023-honesty-layer-claims-and-baseline.md)；保守 fail-open：缺 jq / 文件即放行）。模板各 gate 真实强度见 [`docs/known-limitations.md`](known-limitations.md) |
| ADR-000 技术栈不对 | /agf-init 写 ADR-000 时识别错（罕见，但 AI 会编） | 打开 `docs/adr/000-system-architecture.md` 核对，让 `tech-lead` 据实际 manifest 重写 |
| `product-lead` 自己开始写代码 | 角色漂移 | 提醒 PL 重派执行层；角色写边界由 `enforce-write-scope` hook 机械拦（review/qa/deploy 只读写各自 docs 域） |
| token 消耗远超预期 | cache hit < 50% | 看 `.claude/standards/cost-budget.md` 的优化建议 |
| Agent Team 和 subagent 该选哪个 | 跨角色/跨链路用 team；单点小事用 subagent | 看 `.claude/standards/workflow.md` "Session Entry" 节 |
| teammate 提前 idle | `TeammateIdle` hook 阻断（task list 还有 pending） | 把 task 标记完成或调整状态 |
| 执行层完成报告被 hook 拦 | `progress/<role>.md` 没 append 完整条目 | 按 `.claude/standards/ac-lifecycle.md` Self-Reporting Pattern 补写 |
| 项目 task / 历史 / 缓存乱了想重置 | 多次失败 dispatch 残留 task list / shell snapshots | `claude project purge .`（先 `--dry-run` 看影响，确认后 `-y`） |

## 相关文档（项目内）

- 端到端管道全景图：`docs/team-capability-map.md` §1
- 产品交付工作流 + 术语词典：`docs/product-workflow.md`
- 角色与能力基线：`.claude/standards/team-roles.md`
- 工作流 + Session Entry 判断：`.claude/standards/workflow.md`
- LLM 行为铁律：`.claude/standards/coding.md`
- 测试规范：`.claude/standards/testing.md` + `.claude/standards/ac-lifecycle.md`

> AGF 模板本身的完整说明在 **AGF 上游仓**（README + `docs/` 各文档），随模板分发的项目副本不含开发期材料。
