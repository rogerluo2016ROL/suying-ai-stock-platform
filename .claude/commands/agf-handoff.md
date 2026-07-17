---
description: 把某个变更（change）的执行层（写代码 + 自测）手动交接给 Codex / opencode 等外部工具：建隔离 worktree + 生成 stamped AGENTS.md + 出门/回门简报。治理（规格/审查/部署/签字）仍全留 Claude Code。
argument-hint: <change>（docs/changes/<change>/ 四件套齐、proposal 已批准）[role，默认 backend-dev]
---

# 任务

把变更 `$ARGUMENTS` 的**执行层**手动外包给 Codex / opencode：在隔离 worktree 里生成一份 stamped `AGENTS.md`（点名本次 AC + 只读 SSOT + DoD 指针 + 回填格式），并给出出门 / 回门简报。

这是「人工切换工具」的**出门自动化**——只交执行层（写代码 + Unit + SIT 自跑）；规格、code review、部署、E2E、UAT 签字一步不变、全留 Claude Code（依据《AGF 多工具协作指南》§2 / §4 / §6）。

# 前置检查（不通过就停）

1. `docs/changes/$ARGUMENTS/tasks.md` 存在（四件套齐、proposal 已批准）。否则 → 让 PL 先用 skill `agf-writing-change` 补齐，停。
2. **不是高风险变更**：auth / DB schema 迁移 / LLM 提供商切换 / 跨切面（cross-cutting）**一律不外包**——途中三层 hook 护栏失效、来回成本高、风险大（见协作指南 §6）。若 proposal / tasks 命中这些 → **默认拒绝**，除非用户显式接受风险（回复里记一句「已知高风险、用户接受」再继续）。
3. 目标是 Web 全栈 / 后端 / 前端的执行层活；纯治理 / 设计 / 审查类不走本命令。小程序、Apple 轨另有交付链路，也不走本命令。

# 执行步骤

1. **定角色**：读 `docs/changes/$ARGUMENTS/tasks.md` 的实现 checklist，判断这段活归谁（`backend-dev` / `frontend-dev` / `ai-agent-dev`），作为 role 参数。
2. **建 worktree + 生成 AGENTS.md**：跑
   `bash .claude/scripts/agf-handoff.sh "$ARGUMENTS" <role>`
   它会确定性地：① 建隔离 worktree（分支 `feat/$ARGUMENTS`，baseRef=head）；② 本地忽略 `AGENTS.md`（per-handoff 产物、不进版本库）；③ 把 tasks.md 的 AC↔Scenario 表 stamp 进 worktree 根的 `AGENTS.md`，连同只读 SSOT 路径、DoD 指针（指向 `.claude/standards/`，不硬抄防漂移）、progress 回填模板、以及「CLAUDE.md 仅作背景、治理不是你的活」的框定。
3. **出门简报**：把脚本输出的 worktree 路径 + 分支报给用户，并附下面这段「给 Codex 的起手 prompt」。
4. **回门指引**（提醒用户，work 回来时按脚本输出走）：`git fetch` 该分支 → `git diff --name-only main...feat/$ARGUMENTS | grep -E 'docs/(specs|adr|design)'` 应为空（非空=越界改了 SSOT，打回）→ `bash .claude/scripts/agf-advisory.sh progress/<role>.md`（外包路径下这是**强制入口检查**，因为 `check-progress-file.sh` 兜底 hook 不对外部工具触发）→ 通过后派 `code-reviewer` 做 code review + SIT Audit（门 1）→ 再走 `/agf-deploy-uat`、`/agf-uat`。

# 给 Codex 的起手 prompt（连 worktree 一起交给用户）

```
你在实现 docs/changes/$ARGUMENTS/tasks.md 里的 AC（worktree 根的 AGENTS.md 已逐条列出）。
只读、不改：docs/specs/ docs/adr/000 docs/design/ 和 OpenAPI 契约。
遵守 AGENTS.md 的 DoD：test-first；Unit + SIT 全绿（SIT 真连 DB）；每条 AC 贴真实命令+输出；
前后端走生成 client、禁手写 fetch；无硬编码密钥。
完成后按 AGENTS.md 里的 progress 模板回填 progress/<role>.md，再 git commit。
遇到要改规格 / 架构的，停下回来问，别自己改。
```

# 边界

- 本命令只做**出门**（建 worktree + 生成 AGENTS.md + 简报）；**不替代** code review / 部署 / E2E / UAT——回来照常过门，门禁只认证据、不认人。
- `AGENTS.md` 是 per-handoff 产物、本地忽略、不进版本库；每次交接重新生成、点名当次 AC（所以不存在「占位符没填」「与 standards 漂移」问题）。
- 高风险变更不外包（前置检查 2）。
