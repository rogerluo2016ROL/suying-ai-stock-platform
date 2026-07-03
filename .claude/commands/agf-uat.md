---
description: 触发 product-lead + qa-engineer 联跑 UAT（用户验收测试）；UAT 是业务签字阶段，不是技术测试
argument-hint: <feature-slug>（必须已通过 code review（含 SIT Audit）与 E2E）
---

# 任务

对 feature `$ARGUMENTS` 启动 UAT（User Acceptance Test）阶段。

# 执行步骤

1. **检查先决条件**（pool 模式 / 单实例 自动兼容；glob 同时匹配两种命名）：
   - `docs/reviews/$ARGUMENTS-*.md` 存在（含单实例 `<feat>-<date>.md` 与 pool 实例 `<feat>-r<N>-<date>.md`）；**所有** match 文件的 frontmatter `code_verdict` ≠ `block` 且 `sit_audit_verdict` ∈ {`Pass`, `Pass with concerns`}；用 `bash .claude/scripts/agf-matrix.sh --type=review --feature=$ARGUMENTS` 一眼看全部
   - `docs/qa/$ARGUMENTS-e2e-*.md` 存在（含单实例 与 pool 实例 `-e2e-q<N>-`）；**所有** match 文件 frontmatter `report_verdict` ∈ {`Promote`, `Conditional promote`}；用 `bash .claude/scripts/agf-matrix.sh --type=qa --feature=$ARGUMENTS` 验
   - 变更文件夹 `docs/changes/$ARGUMENTS/tasks.md`（或 PRD fallback `docs/prd/$ARGUMENTS-*.md`）的 P0/P1 AC 全部 Pass（含 P0 case `pass^2 = 2/2`）
   - 任一不满足 → **拒绝启动 UAT**，告诉用户缺什么（pool 模式下任一实例 ❌ 即整 batch fail）
2. **派单**（agent team 模式，因为 UAT 涉及多角色协作；多 task 触发 pool 时按 ADR-001 spawn N 个 qa-engineer-<N>）：
   - `product-lead` — initial task: 组织 UAT 演练 + 业务方沟通；确认 AC 业务签字态（变更文件夹 proposal/tasks；PRD §10 Sign-offs 为 fallback）谁还没签；准备业务侧操作手册
   - `qa-engineer`（pool 触发时 spawn 多实例 `qa-engineer-<N>`）— initial task: 准备 UAT 数据 + 环境（staging / pre-prod）+ 协助业务方复现 AC；落到 `docs/qa/$ARGUMENTS-uat-[YYYY-MM-DD].md`（单实例）或 `docs/qa/$ARGUMENTS-uat-q<N>-[YYYY-MM-DD].md`（pool 实例 N），用 skill `agf-writing-qa-report`（stage = uat）+ YAML frontmatter
3. UAT 执行约束：
   - **业务方主导**，QA 只协助；qa-engineer 不得替业务方判断 Pass/Fail
   - 每条 AC 必须由业务方人工触发并书面确认
   - Sign-offs 必须有业务方签字（数字签名 / 邮件 / 工单系统截图）
4. **完成后** product-lead 把对应 Task 在 `TaskUpdate` 中翻 done，并归档需求入口：`bash .claude/scripts/agf-spec-archive.sh $ARGUMENTS <YYYY-MM-DD>`（先 `--dry-run` 核查 → delta merge 进活规格 `docs/specs/` + change 移 `docs/changes/archive/`，ADR-012）；PRD fallback 路径才 `mv docs/prd/$ARGUMENTS-*.md docs/prd/archive/`

# 任务规模过小怎么办

UAT 阶段规模总是 ≥ 中等（涉及业务方），不存在"过小"。但若业务方暂未就位 → 不要硬启动 UAT，告诉用户："UAT 需要业务方在场，请先和 [业务方角色] 排时间；当前 code review（含 SIT Audit）与 E2E 已完成，可把对应 Task 通过 `TaskUpdate` 标记为 `blocked: pending UAT`。"
