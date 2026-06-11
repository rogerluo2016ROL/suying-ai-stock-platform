# Release 复盘：vX.Y.Z — <一句话标题>

> Release 日期：YYYY-MM-DD｜CHANGELOG: [vX.Y.Z](../../CHANGELOG.md)
> 主持：product-lead｜参与：<实际供材料的角色>

> **Scrum Retrospective 三柱映射**（feature 流变体）：
> - **What went well** → §1 进度（顺利完成项）+ §2 质量（无漏到 release 后的问题）+ §4 帮上忙的 skill
> - **What didn't go well** → §1 范围卡点 + §2 高严重度 finding / 测试失败 / 漏到 release 后的问题 + §3 超预算 + §4 被跳过的 skill / 派工痛点 / 模板改进点
> - **What to improve** → §5 Action Items（每条 Owner + Due 强制，由 §0 闭环兜底）

## 0. 上一轮 Action Items 闭环

> 首个 retro 写"首个 retro，无前置项"。
>
> **Action 继承 Gate：继承次数 ≥2 的 AI 本轮必须二选一——(a) 落地为硬手段（hook / lint 断言 / 模板必填字段 / 带死线的 gh issue，标 done + 证据链接）或 (b) 标 dropped + 一句话放弃理由。禁止第三次继承（§5 不得出现继承次数 ≥3 的行）。**
> （信任崩塌防御：原阈值"≥3 次禁第 4 次"，实践中 /usage 实数、ADR-003 hook 真实验证、假 key squash 决策仍连环空转 2–3 版，故收紧。
> 起源：[retro-v3.2.0](./retro-v3.2.0-2026-05-25.md) §0 AI-2「对账脚本」
> v2.0.0 → v3.0.0 → v3.2.0 三次转继承未落实，直接导致 v3.1.0 漏 retro。）

| 项 | Owner | 状态 | 备注 |
|---|---|---|---|
| <从上次 retro §5 摘抄> | ... | done / in-progress / dropped | <证据链接 或 放弃理由 或 第 N 次继承时的本轮决定> |

## 1. 进度

- 起点（前一版 release 日期，或本版本 PRD 立项日期，取较晚者）→ tag 日期：N 天
- 范围调整 / 关键卡点：

## 2. 质量

- code-review 高严重度：N（中 N，被打回 N 次）
- SIT / E2E / UAT 失败次数：N
- 漏到 release 后的问题：<有则列，无则"无">

## 3. 成本

- `/usage` 4 类 token 实数（**必填；由用户在会话里跑 `/usage` 贴入，agent 无法自跑；缺任一实数本 retro 不得标记完成**）：
  - input: `<N>`｜output: `<N>`｜cache_read: `<N>`｜cache_create: `<N>`
  - 总 cost：`<$>`｜cache hit ratio：`<%>`
- vs cost-budget 档位：明确写"落在 **Small (< 100k) / Medium (100k–500k) / Large (> 500k)** 哪档"，参考 `.claude/standards/cost-budget.md`（跨 release 对比的唯一数据点，必填）

## 4. 流程协作

- 帮上忙的 skill：
- 被跳过的 skill：
- 派工 / 并行 / worktree 合并痛点：
- 模板自身改进点：

## 5. Action Items

| # | 行动项 | Owner | Due | 继承次数 |
|---|---|---|---|---|
| 1 | <具体动作> | <agent / 人> | YYYY-MM-DD | 0（新项）/ 上一轮值 +1 |

> 每条必须 owner + due + 继承次数。无改进项时显式写"本轮无显著改进项"+ 一句理由。
> 继承次数 ≥2 的项禁止再入本表（Action 继承 Gate，见 §0）：必须落地为硬手段或 dropped。

## 6. 公开版？

是 / 否。是 → 派 `content-writer` 按 `docs/content/internal/[YYYY-MM-DD]-[slug].md` 出公开版，retro 文件作素材源、不外发。
