# Tasks: <change 名>

<!--
实现 checklist（人类可读）+ AC↔scenario 映射。
注意：tasks.md 是**计划**；真实派工仍由 PL 按 6 段 schema 建 Agent Teams task（引用本文件）。
二者互补不冲突（ADR-012 决策 2）。
-->

## AC ↔ Scenario 映射（验证脊柱锚点）

每条 AC 仍是 `AC-N`（编号 / 优先级不变，dev 在 progress/<role>.md 写 `[x] AC-N`、qa 逐条测、PL 逐条签字）；
语义来源是 delta 里的 scenario（ADR-012 决策 4）。

| AC | 优先级 | Capability / Requirement / Scenario | 验证方式 |
|---|---|---|---|
| AC-1 | P0 | `<cap>` / 示例行为名 / 示例场景名 | curl / SIT / chrome-devtools |
| AC-2 | P1 | … | … |

## 实现 checklist

- [ ] T1: <做什么>（涉及 `backend/...` / `frontend/...`）
- [ ] T2: <做什么>
- [ ] T3: <做什么>
