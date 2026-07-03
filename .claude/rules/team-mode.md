---
name: team-mode
description: Agent Team mode protocol — when to spawn a team, the trigger phrase, lead role, teammate naming rules. Loaded only when agent definitions / project plan / commands are touched, not on every prompt.
paths:
  - ".claude/agents/**"
  - ".claude/commands/**"
  - "docs/changes/**"
  - "docs/prd/**"
---

# Team Mode 协议（多角色任务必须以 Agent Team 启动）

> 本节是对主 Claude（接到用户请求的入口 session）的硬性指令。

## 启用条件

启用条件 + 不命中时如何处理（直接执行 / 派 subagent / 建 team）由 `.claude/standards/workflow.md` "Session Entry" 节定义，本文件不复述。命中"建 team"路径后按下文协议执行。

## 启动协议

1. 用官方触发句式：`Create an agent team called <Name>Team to deliver <feature>`。
2. 每个 teammate **必须用 subagent type 名字**（如 `product-lead`、`backend-dev`），**严禁** 用 `@.claude/agents/*.md` 文件引用——definition 已被 Claude Code 自动加载，再 `@` 引用只浪费 lead 的 token。
3. 每个 teammate 必须给**可立即执行的初始任务**，禁止「待命 / standby」类占位任务（会让 Claude 倾向退化为 subagent）。
4. Lead 固定为 `product-lead`，且 **lead = 主 session 本身**：由 `agf-team-start.sh`（或手动 `claude --agent product-lead`）以 `--agent product-lead` 启动。PL 走 `--agent` 路径，其 frontmatter（`permissionMode: acceptEdits` / `skills` / `memory`）**全生效**，团队权限基线 = PL 的 `acceptEdits`（**默认不再用 `--dangerously-skip-permissions`**）。**因此不要再把 `product-lead` 作为 teammate spawn**——PL 自身的首个任务（如起 PRD）由本 session 直接执行。前提：`product-lead.md` 的 `tools` 须含 `Agent`（spawn teammate 必需）。
5. 显示模式由 `.claude/settings.json` 的 `teammateMode` 控制（当前 `iterm2`；无 it2 / 非 iTerm2 用户在用户级改 `tmux`/`auto`），不要在 prompt 里指定 pane 行为。
6. 启动后 lead 必须显式确认「这是 agent team 而不是 subagent」，并报告每个 teammate 的 name + agent ID。
7. 并行派发同类型 teammate 遵循 `.claude/standards/workflow.md` "Parallel Dispatch" 节，且**必须用 git worktree 隔离**（见同文件 worktree 节）。

## 标准模板入口

普通用户用 `/agf-team-start <feature description>` 启动（见 `.claude/commands/agf-team-start.md`），主 Claude 据本节协议展开实际 spawn 调用。

## 已启用的运行时配置

- `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`：在 `.claude/settings.json` 的 `env` 块声明，用户级 `~/.zshrc` 同时 export 作冗余兜底
- **隐式团队（v2.1.178+）**：设上面 flag 后每个 session 自动拥有一个隐式团队——直接 spawn teammate（Agent 工具 `name` 参数）即可、无需建团步骤；PL session 退出时 team 目录（`~/.claude/teams/session-<id前8位>/`）随之自动清理。**v2.1.178 起 `TeamCreate` / `TeamDelete` 工具已移除**：启动协议第 1 条 `Create an agent team called <Name>Team` 触发句式仍有效（Claude 据此 spawn），但你传的 team name 现被忽略（改 session-derived）。「一 session 一 team / teammate 不能 spawn teammate / lead 固定 PL」不变。**模板 min 维持 v2.1.154 不上抬**——该下限由 Dynamic Workflows GA 决定（ADR-002）、与 Teams 无关，Agent Teams 是实验 flag 功能、不构成 min 下限；隐式团队（v2.1.178+）是模板**目标运行版本**（macOS + CC ≥ v2.1.186 + it2，见下 `iterm2` 条）下的行为，降到 v2.1.154–177 的 fork 仍会回到旧 `TeamCreate` / `TeamDelete` 流程（`init-team.sh` warn 不 block）
- `teammateMode: "tmux"`（**推荐 fallback，模板默认已改 `"iterm2"`**）：请求 split panes（官方语义：启用 split-pane 并按终端自动判别走 tmux 还是 iTerm2）。**无 it2 / 非 iTerm2 / 跨平台的团队用户改设此值即恢复优雅降级**（不报错）。**曾为模板默认、更早改自 `"auto"`**——`"auto"` 仅当**已身处 tmux 会话内**（`TMUX` 已设）才走 split panes，"光装了 tmux / 在 iTerm2 里"都不算，否则回退 in-process。✅ **iTerm2 回退缺陷已实测确认修复**：CC v2.1.170 + 纯 iTerm2（无 tmux server），`"tmux"` 设置成功 spawn 8 个 iTerm2 原生分屏 teammate（team config 记 `backendType:"iterm2"` + pane GUID，超出单 tab 容量自动溢出到第 2 个 tab——**找不到 teammate 时先翻 tab**）；历史缺陷见官方 issue #24292 / #23815（均已关，CHANGELOG v2.1.77 对应条目），ADR-004 该项待办可销。tmux 路径（先 `tmux new -s claude` 再 `claude`）仍为备选。非 macOS / 无 tmux / VS Code 内置终端 / Windows Terminal / Ghostty 一律不支持 split panes → 静默 in-process。本项目默认值与降级取舍记录见 ADR-004
- `teammateMode: "iterm2"`（**v2.1.186 新增 · 模板默认（见 ADR-004）**）：强制走 iTerm2 原生分屏，**硬依赖 `it2` CLI**——缺 it2 即报错并打印安装命令（区别于 `"tmux"` 的静默降级；fail-loud 正是选它作默认的理由）。前置：`pip install it2` + iTerm2 → Settings → General → Magic → Enable Python API，且 Claude Code ≥ v2.1.186（**`"iterm2"` 值的渲染前置**——但**模板 min 维持 v2.1.154 不上抬**：Teams 实验功能不构成 min 下限，无 it2 / 老版本走 `"tmux"`/`"auto"` fallback，见 ADR-004 状态行 + 上「隐式团队」条）。**无 it2 / 非 iTerm2 / 跨平台的团队用户**：把 `teammateMode` 改回 `"tmux"`/`"auto"`（见上一条 fallback + CHANGELOG `Migration steps`）。另：v2.1.186 起 `"auto"` 语义已放宽为「tmux 会话内 **或** iTerm2 终端」均走 split panes（故上一条"auto 仅 tmux 会话内"为 ≤v2.1.185 旧语义）；`"auto"`/`"tmux"` 在 iTerm2 且 tmux 可作 fallback 时会弹"装 it2 或切 tmux"的 setup prompt。选型权衡见 ADR-004 备选 D
- **effort 继承（v2.1.186+）**：经 tmux/pane backend spawn 的 teammate 自动继承 lead 的 `--effort` 档——PL 用 `--effort` 启动时无需逐 teammate 指定，effort 随 spawn 下传
- `TeammateIdle` hook：`.claude/hooks/teammate-keepalive.sh`，task list 还有 pending 时阻止 teammate 提前 idle

## 反模式

- ❌ 用「待命」/「standby」派 teammate 初始任务 — Claude Code 会退化成 subagent
- ❌ 用 `@.claude/agents/<role>.md` 文件路径派 teammate — 浪费 token
- ❌ 在 spawn prompt 里硬编码 pane 行为 — 由 `teammateMode` 控制
- ❌ 没有 product-lead 的 team — lead 必须固定为 product-lead
- ❌ 跳过 git worktree 直接并行 ≥2 个 execution-layer teammate — 文件覆盖风险
- ❌ 把 `product-lead` 当 teammate spawn — 它是 `--agent` 主 session lead，重复 spawn 会出现两个 PL；只 spawn 其余角色
- ❌ 用 `--dangerously-skip-permissions` 启动 lead（除非显式自担风险）— 它会传染给所有 teammate，使 per-role 权限分级全失效
