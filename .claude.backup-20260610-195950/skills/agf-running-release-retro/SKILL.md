---
name: agf-running-release-retro
description: Use when product-lead is about to run a release retrospective after a successful MAJOR or MINOR release push (PATCH skipped). Provides applicability gate, pre-conditions, 7-step execution sequence, anti-patterns, and the verification gate before commit. Pairs with template docs/reviews/retro-_TEMPLATE.md and slash /agf-release-retro.
---

# Running Release Retrospective

Use this skill when:

- product-lead has just pushed a MAJOR (`vX.0.0`) or MINOR (`vX.Y.0`) release tag and created the GitHub release
- The user typed `/agf-release-retro vX.Y.Z` and the slash dispatched here

## Applicability — PATCH is excluded

**Parse `vX.Y.Z`** and gate the execution:

- `Y=0 ∧ Z=0` → **MAJOR**, retro required
- `Y>0 ∧ Z=0` → **MINOR**, retro required
- `Z>0` → **PATCH**, abort with message: "PATCH release — retro not required per versioning.md, exiting."

If the version is PATCH, do not proceed.

## Pre-conditions

All the following **must pass** before starting the execution sequence. If any fails, SendMessage product-lead with the specific failure and do not proceed:

- [ ] CHANGELOG.md contains section `## [vX.Y.Z]`（不再要求"pushed to origin"——下条 `gh release view` 已隐含 release 必须可见于 GitHub）
- [ ] `git tag -l vX.Y.Z` returns the tag
- [ ] `gh release view vX.Y.Z` returns the release

## Execution sequence

### 1. Copy template and pre-fill header

Copy `docs/reviews/retro-_TEMPLATE.md` to `docs/reviews/retro-vX.Y.Z-YYYY-MM-DD.md` (use today's date). Pre-fill:

- Title with version and one-sentence release summary
- Release date (from git tag annotated date or `gh release view --json createdAt`)
- Link to CHANGELOG `[vX.Y.Z](../../CHANGELOG.md)`

### 2. Draft §1 (Progress)

Read CHANGELOG `## [vX.Y.Z]` section and any linked PRD / ADR. Write §1 with:

- 起点（**前一版 release 日期，或本版本 PRD 立项日期，取较晚者**）→ tag 日期：N 天
- 范围调整 / 关键卡点（major diffs from original scope，blockers，why they happened）

### 3. Dispatch self-report tasks

Use `Agent({subagent_type: ..., prompt: ...})` to send parallel self-report prompts to roles that contributed to this release. Include:

- `code-reviewer` — code review severity distribution, rejection rates, **SIT Audit verdicts** (Pass / Pass with concerns / Redo SIT counts)
- `qa-engineer` — E2E / UAT failure counts, AC gaps missed until production (SIT is dev-owned; not in qa scope)
- Contributing execution-layer roles (`backend-dev` / `frontend-dev` / `ai-agent-dev` / `ml-engineer` / any `miniapp-*`) — implementation blockers, rework root causes
- `tech-lead` — **only if this release contains an ADR change**

Each role returns **≤3 highlights / ≤3 pains / ≤3 Action item candidates**.

### 4. Integrate role inputs into §1–§4

Read each returned self-report and integrate findings into:

- §1: update with timeline/blocker insights
- §2: add quality metrics (code-review severity, test failure counts, production gaps)
- §3: 摘录本会话 Claude Code 内置 `/usage` 输出，**4 类 token 字段必填**：`input_tokens` / `output_tokens` / `cache_creation_input_tokens` / `cache_read_input_tokens` + 总 cost + cache hit ratio（cache_read / (input + cache_read + cache_creation)）；并对照 [`cost-budget.md`](../../standards/cost-budget.md) 分档明确写"本 release 落在 Small / Medium / Large 哪档"；或写"本 release 不涉 cost"。这是后续跨 release 对比与 sweet-spot 判定的唯一数据来源。
- §4: note workflow frictions and template improvements

Deduplicate Action item candidates and draft §5 (Action Items table).

### 4.1 Feature cycle time trend (≥3 retros 后强制评估)

> 项目声明不统计 Velocity / Burndown（见 `product-workflow.md §4.4`），但跨 retro 的"起点 → tag 日期"数据天然存在。**累计 ≥3 个 retro 后**，本步骤强制做趋势评估，作为 Velocity 的隐式形式。

执行：

1. `ls docs/reviews/retro-v*.md | sort` 列出全部历史 retro
2. 从每份 retro §1 抽取 "起点 → tag 日期：N 天" + actual work 时长
3. 跨 retro 比对趋势：稳定 / 下降（团队效率提升）/ 上升（出现系统性阻塞）
4. 若 ≥3 retro 显示上升趋势 → 必须列为 §5 Action Item 候选，分析是流程问题 / 工具问题 / 范围问题
5. 若 <3 retro：本节写 "数据点不足（当前 N 个 retro），不下结论"

写入 §1 末尾或 §4 流程协作节，**不另起独立小节**，避免文档膨胀。

### 5. Decide §6 (Public version)

Decide: **是 (public)** or **否 (not public)**.

- If **是**: dispatch `content-writer` to produce `docs/content/internal/[YYYY-MM-DD]-[slug].md` from this retro as source material
- If **否**: mark "否" in §6

### 6. Verification gate

All of the following **must pass** before commit:

- [ ] §0 is written (首个 retro: explicit "首个 retro，无前置项"; subsequent: table filled from prior release §5)
- [ ] §0 **转继承 ≥3 次 trigger** 已应用：扫前 3 个 retro §5，凡同一 AI 已转继承 ≥3 次仍 pending，本轮必须显式 `in-progress`（含具体进展）或 `dropped`（含放弃理由），**不允许第 4 次继承**（信任崩塌防御，详见 `docs/reviews/retro-_TEMPLATE.md` §0 起源说明）
- [ ] §5 has ≥1 Action item **OR** explicit "本轮无显著改进项" + one-line reason
- [ ] Every §5 row has non-empty **Owner** column and non-empty **Due** column

If any check fails, do not proceed to Step 7.

### 7. Commit

```bash
git add docs/reviews/retro-vX.Y.Z-YYYY-MM-DD.md
git commit -m "docs(retro): vX.Y.Z release retrospective"
```

Do **not** push.

## Anti-patterns

- ❌ Action item without owner or without due date
- ❌ §0 missing (首个 retro must explicitly state "首个 retro，无前置项")
- ❌ PATCH release forced into the template (should have aborted at Applicability gate)
- ❌ Retro content duplicates CHANGELOG (changelog = "what was built"; retro = "why and how to improve next time")

## Outputs

- Final file: `docs/reviews/retro-vX.Y.Z-YYYY-MM-DD.md`
- Optional: `docs/content/internal/[YYYY-MM-DD]-[slug].md` (if §6 = 是)
- Action items from §5 become §0 inputs for the next release retro
