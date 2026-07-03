---
description: UAT 签字后关闭执行层 teammate（dev / reviewer / qa）；PL 与单实例长期角色保留以接续后续需求
argument-hint: 无参数（自动识别 alive teammate）
---

# 任务

关闭已完成本 feature 工作的执行层 teammate，释放 process / 上下文，保留 product-lead 与单实例长期角色待命。

**默认关闭类型**（10 个执行层）：`frontend-dev` / `backend-dev` / `ai-agent-dev` / `ml-engineer` / `miniapp-dev` / `code-reviewer` / `miniapp-code-reviewer` / `qa-engineer` / `miniapp-qa-engineer` / `deploy-engineer`

**默认保留类型**（PL + 4 个单实例长期角色，共 5）：`product-lead` / `tech-lead` / `uiux-designer` / `content-writer` / `growth-analyst`

> 范围设计依据：详见 `CLAUDE.md ## Verified Facts` 的 Pool 上限表 —— 按 feature 周期内 spawn 的执行层角色默认关闭（含 Pool ≥ 3 的 dev / reviewer / qa，以及 Pool=1 但仅在部署阶段 spawn 的 `deploy-engineer`）；PL 与跨 feature 待命的单实例长期角色（`tech-lead` / `uiux-designer` / `content-writer` / `growth-analyst`）保留。

# 执行步骤

1. **确认 UAT 已签字**：
   - 在 `docs/prd/*.md`（active）与 `docs/prd/archive/*.md` 找最近 feature 的 §10 Sign-offs
   - 业务侧 ≥ 1 个 `approve` → 继续
   - 否则 **abort**：`"UAT 未签字（PRD §10 Sign-offs 缺业务侧 approve），先 /agf-uat <feature> 完成验收。"`

2. **读 team config 列出待关 teammate**：
   - team-name 取自当前 session 上下文（agent team 模式下 PL session 必有）；无法确定时 `ls ~/.claude/teams/` 取最近修改
   - Read `~/.claude/teams/<team-name>/config.json`，遍历 `members[]`
   - 过滤 `agentType` ∈ 默认关闭类型清单（pool 实例 `<type>-<N>` 的 `agentType` 字段仍是原 type，自动覆盖）
   - 输出预览：`共 N 个待关：<name1>(<type1>), <name2>(<type2>), ...；保留 M 个：<name>(<type>), ...`

3. **关闭前 task 安全检查**：
   - `bash .claude/scripts/agf-tasks.sh <team-name>` 查共享 task list
   - 待关 teammate 名下 task 必须全部 `status ∈ {completed}`（其它状态都阻断）
   - 若有 `pending` / `in_progress` / `blocked` 命中待关 owner → **abort**：列出残留任务 `T-NNN + owner + status`，要求 PL 先 `TaskUpdate` 完成或重派给保留角色

4. **逐个发 shutdown_request**（按 `name` 升序串行，避免响应错乱）：
   ```
   SendMessage({
     to: "<teammate-name>",
     message: {type: "shutdown_request", reason: "UAT 已签字，本 feature 工作完成"}
   })
   ```
   - 等对方回 `shutdown_response` 带 `approve: true` 再发下一个
   - 若 5 分钟内无响应 → 跳过该 teammate 并在最终报告标 `⚠️ timeout`，不阻断后续

5. **报告**（必须输出，作为闭环证据）：
   - ✅ 已关闭：`<name>`(<agentType>), ... ×N
   - ⚠️ timeout / 拒绝：(如有，列名 + 原因)
   - 🟢 剩余 alive：`<name>`(<agentType>), ...（至少含 `product-lead`）
   - 下一步建议：
     - 若 progress 未归档 → `bash .claude/scripts/archive-progress.sh <feature>`
     - 若 PRD 未 mv → `mv docs/prd/<feature>-*.md docs/prd/archive/`
     - 继续给 PL 派新需求即可

# 任务规模过小怎么办

- 没有命中类型的 teammate alive → `"无可关闭 teammate（PL / 单实例角色不在默认关闭范围）。"` 退出
- 不在 agent team 模式（无 `~/.claude/teams/<team-name>/` 目录）→ `"当前会话不是 agent team 模式，无 teammate 可关闭。"` 退出
- 用户想连 PL / 长期角色一起关 → 不在本命令范围；告诉用户：`"PL 默认保留以接续后续需求；如确需全 team 解散，先手动 SendMessage shutdown_request 给 PL，然后 TeamDelete。"`
