---
name: team-mode
description: Agent Team mode protocol — when to spawn a team, the trigger phrase, lead role, teammate naming rules. Loaded only when agent definitions / project plan / commands are touched, not on every prompt.
paths:
  - ".claude/agents/**"
  - ".claude/commands/**"
  - "docs/prd/**"
---

# Team Mode 协议（多角色任务必须以 Agent Team 启动）

> 本节是对主 Claude（接到用户请求的入口 session）的硬性指令。

## 启用条件

启用条件 + 不命中时如何处理（直接执行 / 派 subagent / 建 team）由 `.claude/standards/workflow.md` "Session Entry" 节定义，本文件不复述。命中"建 team"路径后，按下文协议执行。

## 启动协议

1. 用官方触发句式：`Create an agent team called <Name>Team to deliver <feature>`。
2. 每个 teammate **必须用 subagent type 名字**（如 `product-lead`、`backend-dev`），**严禁** 用 `@.claude/agents/*.md` 文件引用——definition 已被 Claude Code 自动加载，再 `@` 引用只会浪费 lead 的 token。
3. 每个 teammate 必须给**可立即执行的初始任务**，禁止「待命 / standby」类占位任务（会让 Claude 倾向退化为 subagent）。
4. Lead 固定为 `product-lead`。
5. 显示模式由 `.claude/settings.json` 的 `teammateMode` 控制（当前为 `auto`），不要在 prompt 里指定 pane 行为。
6. 启动后 lead 必须显式确认「这是 agent team 而不是 subagent」，并报告每个 teammate 的 name + agent ID。
7. 并行派发同类型 teammate 时遵循 `.claude/standards/workflow.md` "Parallel Dispatch" 节，且**必须使用 git worktree 隔离**（见同文件 worktree 节）。

## 标准模板入口

普通用户启动用 `/agf-team-start <feature description>`（见 `.claude/commands/agf-team-start.md`），主 Claude 根据本节协议展开实际 spawn 调用。

## 已启用的运行时配置

- `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`：在 `.claude/settings.json` 的 `env` 块声明，用户级 `~/.zshrc` 同时 export 作冗余兜底
- `teammateMode: "auto"`：tmux/iTerm2 可用时走 split panes，否则走 in-process
- `TeammateIdle` hook：`.claude/hooks/teammate-keepalive.sh`，task list 还有 pending 时阻止 teammate 提前 idle

## 反模式

- ❌ 用「待命」/「standby」给 teammate 派初始任务 — Claude Code 会退化成 subagent
- ❌ 用 `@.claude/agents/<role>.md` 文件路径派 teammate — 浪费 token
- ❌ 在 spawn prompt 里硬编码 pane 行为 — 由 `teammateMode` 控制
- ❌ 没有 product-lead 的 team — lead 必须固定为 product-lead
- ❌ 跳过 git worktree 直接并行 ≥2 个 execution-layer teammate — 文件覆盖风险
