# progress/

Self-Reporting Pattern 的持久化目录。每个执行层 teammate 完成任务后 append 一条完整条目到自己的 progress 文件（命名见下）作为底稿；SendMessage 完成报告只是给 product-lead 的摘要。

## 文件命名（SSOT，与 [ADR-001](../docs/adr/001-multi-instance-worker-pool.md) + [`workflow.md` §Multi-instance Worker Pool](../.claude/standards/workflow.md) 对齐）

| 模式 | 文件名 | 触发 |
|---|---|---|
| **单实例**（pool=off / 同 type 仅 1 个 task） | `progress/<role>.md`（如 `progress/backend-dev.md`）| 默认模式 |
| **Pool 模式**（同 type ≥ 2 个 task）| `progress/<role>-<N>.md`（如 `progress/backend-dev-1.md` / `backend-dev-2.md` / `code-reviewer-3.md`）| product-lead 触发 fan-out 时 |

实例编号 N 从 1 单调递增，**同 release 内不重置**（避免 SendMessage 路由歧义）。

## 适用对象

强制写入（5 个执行层 dev type）：
- `progress/backend-dev.md`（或 `backend-dev-N.md` 在 pool 模式下）
- `progress/frontend-dev.md`（或 `frontend-dev-N.md`）
- `progress/ai-agent-dev.md`（或 `ai-agent-dev-N.md`）
- `progress/ml-engineer.md`（或 `ml-engineer-N.md`）
- `progress/miniapp-dev.md`（或 `miniapp-dev-N.md`）

可选写入（这些角色的产物已落盘到 `docs/{prd,reviews,qa,design,content,growth}/`，不强制）：
- `product-lead` / `code-reviewer` / `qa-engineer` / `tech-lead` / `uiux-designer` / `content-writer` / `growth-analyst` / `miniapp-code-reviewer` / `miniapp-qa-engineer`
- Pool 模式下若选择写入，仍按 `progress/<role>-<N>.md` 命名（如 `code-reviewer-2.md`）

## 写入规则

完整条目格式与强制约束见 [`.claude/standards/ac-lifecycle.md`](../.claude/standards/ac-lifecycle.md) 的 "Self-Reporting Pattern" 节，要点：

1. 每完成一个 task append 一段（`## 任务名 - YYYY-MM-DD HH:MM` 开头）
2. **5 段精简格式**：状态 / Skills / SIT 证据（含 AC 自验勾选）/ 质量门 / 下一步
3. **pass 单行扫读、fail/blocked 才展开**：SIT 证据每条 AC 行首 `[x]/[ ]` 兼任 AC 自验勾选；pass ≤ 80 字一句话，fail/blocked 才内嵌命令 + 输出 + 偏差
4. 阻塞场景也写（状态写"阻塞"，"下一步"段说明阻塞点 + 已尝试 + 需要什么）
5. 写完 `progress/<role>.md` 再 SendMessage 完成报告

## Hook 兜底

`SubagentStop` 与 `TeammateIdle` 触发 [`.claude/hooks/check-progress-file.sh`](../.claude/hooks/check-progress-file.sh)：执行层 role 退出/idle 时，若对应 progress 文件（单实例 `progress/<role>.md` 或 pool 模式 `progress/<role>-<N>.md`）不存在或无 `## ` 二级标题条目，则 **exit 2 阻断**。

豁免：当前 team task list 里没有任务分给该 role / 该实例时（standby）放行。

## Git 策略

feature 期间进 git，便于跨机器恢复与 PR review。**UAT 签字时**由 product-lead 跑 [`.claude/scripts/archive-progress.sh`](../.claude/scripts/archive-progress.sh) 归档：

- **单实例**：`progress/<role>.md` → `docs/qa/<feature>-process-log.md` 对应 role 段
- **Pool 模式**：自动合并 `progress/<role>-*.md`（按 N 升序 cat）→ `docs/qa/<feature>-process-log.md` 对应 role 段（保留实例编号便于追溯）

归档完成后 `git rm progress/*.md`，main 分支上 `progress/` 只保留 `.gitkeep` + `README.md`。详见 [`.claude/agents/product-lead.md` Step 5](../.claude/agents/product-lead.md)。

## 模板

参考 `.claude/standards/ac-lifecycle.md` 「完整条目格式」一节复制粘贴。
