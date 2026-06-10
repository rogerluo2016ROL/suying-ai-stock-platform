---
name: repo-layout
description: Repository directory map for AppGenesisForge — what lives where. Loaded on demand when an agent is about to create/modify project structure or unsure where to put a new artifact.
paths:
  - "**/*.md"
  - ".claude/**"
  - "docs/**"
  - "evals/**"
  - ".github/**"
---

# Repository Layout

> 这是 AppGenesisForge 的目录地图。新建文件 / 不确定某产物归属时查这里；修改本表后须同步 CLAUDE.md 里的指针。

## .claude/

| 路径 | 内容 |
|---|---|
| `.claude/agents/*.md` | 14 个团队角色 agent 定义（9 通用 + 3 `miniapp-*` + 2 post-launch；小程序设计由 `uiux-designer` 在 MiniApp Mode 下覆盖） |
| `.claude/standards/*.md` | 团队通用规范（角色、工作流、测试、安全、观测、成本预算、轻量化 plan 格式等），跨项目复用 |
| `.claude/commands/*.md` | 项目级 slash commands：`agf-team-start` `agf-team-stop` `agf-uat` `agf-tasks` `agf-release-retro` |
| `.claude/scripts/*.sh` | 项目工具脚本（非 hook，由 product-lead 等手动调用）共 4 个：`agf-tasks.sh`（task list 表格视图）/ `archive-progress.sh`（UAT 后归档 `progress/<role>-*.md` 到 `docs/qa/<feature>-process-log.md`，支持 pool 多实例合并）/ `agf-matrix.sh --type=progress\|review\|qa`（PL 聚合 N 份报告为 1 张表）/ `lint-all.sh`（全仓 bash/JSON/YAML lint 入口，pre-commit hook 自动链调）；ADR-001 + Multi-instance Worker Pool 详 [`workflow.md`](../standards/workflow.md) |
| `.claude/skills/*/SKILL.md` | **9 个项目自有 skill**：`agf-wiring-multi-llm-sdk`、`agf-running-sit-tests`（dev 跑 SIT 用）、`agf-writing-prd`、`agf-writing-adr`、`agf-writing-qa-report`（qa 写 E2E/UAT 报告用）、`agf-running-release-retro`、`agf-writing-docx-reports`（docx-js 高密度中文报告）、`agf-writing-pptx-reports`（python-pptx 现代化中文 deck）、`agf-writing-github-issue`（在仓库提 issue，含 dev SIT 自动 path + qa E2E/UAT 自动 path + 标签锁定）；**2 个外部第三方 skill**：`docx`、`pptx`（Anthropic 提供的低层 .docx / .pptx 读写脚本与 schema，供上面两个 writing-* skill 依赖调用 `scripts/office/soffice.py`） |
| `.claude/hooks/*.sh` | 四层防御 + 工作流 hook + git pre-commit；详见本目录与 `.claude/standards/security.md` |
| `.claude/rules/*.md` | path-scoped 规则（本文件 + `team-mode.md`），由 Claude Code 按文件路径自动加载 |
| `.claude/settings.json` | 项目配置：Agent Teams 启用、permissions allow/deny、hooks 注册、autoMemoryEnabled、worktree.baseRef |
| `.mcp.json` | 项目级 MCP server 注册（当前：`chrome-devtools-mcp@latest` 供 `qa-engineer` 跑 E2E）；与 `.claude/settings.json` 分文件（前者是 MCP 协议规范文件，后者是 Claude Code 私有配置） |

## docs/

| 路径 | 内容 |
|---|---|
| `docs/FIRST_RUN.md` | 接手模板的 Day-1 清单 + 前置知识 + 常见踩坑 |
| `docs/team-capability-map.md` | §1 端到端全景图（角色 + 阶段门 + hook + skill 叠加）+ 14 角色协作 Mermaid + 能力对照表，改 agent 时必须同步 |
| `docs/product-workflow.md` | 产品交付工作流 + 全量术语词典；写 PRD / 拆 Task / 用术语前先查这里 |
| `docs/prd/*.md` | product-lead 产出（命名 `[feature]-[YYYY-MM-DD].md`，写时用 skill `agf-writing-prd`） |
| `docs/design/[feature]/` | uiux-designer 产出（`spec.md` + `index.html`，资源放 `assets/`） |
| `docs/reviews/*.md` | code-reviewer 产出 + release retro（`retro-vX.Y.Z-YYYY-MM-DD.md`）+ 季度 eval 漂移记录 |
| `docs/qa/*.md` | qa-engineer 产出（E2E / UAT 报告，写时用 skill `agf-writing-qa-report`；SIT 不再独立成 `docs/qa/*-sit-*.md`，证据写入 `progress/<role>.md` 由 code-reviewer 在 review 时 audit）+ `<feature>-process-log.md`（progress/ 归档，UAT 签字后由 product-lead 写入） |
| `docs/adr/*.md` | 架构决策记录（命名 `NNN-[slug].md`，写时用 skill `agf-writing-adr`；ADR-000 是基线） |

## progress/（Self-Reporting Pattern 持久化）

| 路径 | 内容 |
|---|---|
| `progress/<role>.md` | 执行层 teammate 完成任务的底稿（5 段格式：状态 / Skills / SIT 证据 [含 AC `[x]/[ ]` 内联] / 质量门 / 下一步）；feature 期间进 git，UAT 签字后由 product-lead 归档到 `docs/qa/<feature>-process-log.md` 并从 main 移除 |
| `progress/README.md` | 写入规则、Hook 兜底、Git 策略说明 |
| `progress/.gitkeep` | 保持空目录在 git 中存在 |

强制对象、写入格式与归档流程见 [`.claude/standards/ac-lifecycle.md`](../standards/ac-lifecycle.md) "Self-Reporting Pattern" 节；hook 兜底由 [`.claude/hooks/check-progress-file.sh`](../hooks/check-progress-file.sh) 在 `SubagentStop` / `TeammateIdle` 触发。

## 应用代码（首个 feature 启动时由执行层创建）

| 路径 | 内容 |
|---|---|
| `backend/` | FastAPI 应用（按 ADR-000）；agents 在 `backend/app/agents/` |
| `frontend/` | React + Vite 应用（按 ADR-000） |
| `miniapp/` | 微信小程序（按 `.claude/standards/miniapp.md`） |
| `docker-compose.yml` | 仅编排 Postgres |

## 工程配套

| 路径 | 内容 |
|---|---|
| `evals/*.jsonl` | 角色漂移检测用例（按 role 分文件 JSONL）；`evals/run.sh` 是 runner |
| `.github/workflows/claude-code.yml` | Claude Code GitHub Action 模板（默认未启用） |
| `init-team.sh` | 接手模板 Day-1 验证脚本（hook 测试 + JSON 语法 + 必备文件存在性） |
| `agf-team-start.sh` | 交互式 Agent Team 启动器（预检 + teammate 多选菜单），等价 slash command `/agf-team-start`；本身不复述启动协议，只做 UX + 调用 slash 命令保 SSOT |
| `tools/team-dashboard/` | 单任务只读 web 看板（FastAPI SSE + React/Vite），手动 `./start.sh` 启动；零侵入观察当前 `agf-team-start` 会话 |

## 单一来源原则

每类内容**只在一个地方维护**——其他地方只放指针：

- 技术栈唯一来源：`docs/adr/000-system-architecture.md`（CLAUDE.md 只放一句"详见 ADR-000"）
- 角色清单唯一来源：`.claude/agents/*.md` + `.claude/standards/team-roles.md`（`docs/team-capability-map.md` 是视图，需同步）
- 工作流唯一来源：`.claude/standards/workflow.md`（CLAUDE.md 不重复；本文件 + `.claude/rules/team-mode.md` 按场景指针）
