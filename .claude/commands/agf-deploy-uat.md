---
description: 触发 product-lead 派 deploy-engineer 把合并后的 main 代码部署到隔离 UAT 栈并冒烟自检；冒烟通过后交接 qa-engineer 跑 E2E/UAT
argument-hint: <feature-slug>（必须已通过 code review（含 SIT Audit）且已合并到 main）
---

# 任务

对 feature `$ARGUMENTS` 启动 **UAT 部署门**：把合并后的 main 代码部署到与所有 dev worktree 物理隔离的本地 UAT 栈，冒烟自检通过后交接 qa-engineer。

这是交付链路里 code review 与 E2E 之间新增的部署门，二元 gate（`✅ 部署成功（冒烟通过）` / `❌ 部署失败`），不是测试阶段。

# 执行步骤

1. **检查先决条件**：
   - `docs/reviews/$ARGUMENTS-*.md` 存在（含单实例 `<feat>-<date>.md` 与 pool 实例 `<feat>-r<N>-<date>.md`）；**所有** match 文件 frontmatter `code_verdict` ≠ `block` 且 `sit_audit_verdict` ∈ {`Pass`, `Pass with concerns`}；用 `bash .claude/scripts/agf-matrix.sh --type=review --feature=$ARGUMENTS` 一眼看全部
   - 对应代码**已合并到 main**（`git log main --oneline` 可见该 feature 的合并提交）；记录待部署 commit SHA
   - 目标为 **Web 全栈链路**（docker-compose 化）；若是小程序 feature → **拒绝**：小程序"部署"= 上传体验版，归 miniapp-dev / miniapp-qa-engineer，不走本命令
   - 任一不满足 → **拒绝启动部署**，告诉用户缺什么
2. **派单**（派 `deploy-engineer`；**Pool 上限 = 1，禁 fan-out**——只有一个 UAT 环境，并发部署必撞端口/状态）：
   - **用户授权归因（A-F4 / ADR-019，hook `gate-deploy-release-auth` 强制）**：本 slash 命令由用户显式触发 = 用户授权。派单 task 描述**必须含**一行 `用户授权: /agf-deploy-uat $ARGUMENTS 已触发（用户显式调用）`，否则 TaskCreated 被 hook exit 2 阻断。
   - `deploy-engineer` — initial task: 按 skill `agf-deploying-uat` 把合并后 main 部署到隔离 UAT 栈（独立 `COMPOSE_PROJECT_NAME=${APP_NAME}-uat` + `UAT_PORT_OFFSET=900`），容器内跑 `alembic upgrade head`，冒烟自检（真实 curl 输出，非 dry-run），落部署报告到 `docs/deploy/$ARGUMENTS-uat-[YYYY-MM-DD].md`，SendMessage product-lead 附 UAT 栈 URL
3. **部署门约束**：
   - 部署源必须是**合并后的 main**，不是任何 dev worktree 未合并分支
   - 必走隔离栈（独立 project name + 端口偏移 +900，避开 dev base / QA pool base+100..+700）
   - 冒烟必须真实输出（前端可达 + 后端健康 + 核心 API 真实 200 + DB 连通），禁 dry-run
   - **deploy-engineer 不修源码**：冒烟暴露代码问题 → 退回 product-lead → dev；环境/配置问题 → deploy-engineer 自己重部
4. **完成后**：
   - ✅ 部署成功（冒烟通过）→ product-lead 据部署报告里的 UAT URL 触发 `/agf-uat $ARGUMENTS`（或先 E2E），qa-engineer 对**共享 UAT 栈**测，不再对 dev worktree
   - ❌ 部署失败 → product-lead 决策：环境/配置问题让 deploy-engineer 重部；代码问题回实现层修复，重走后续阶段门

# 任务规模过小怎么办

- 部署门规模固定（起一个隔离栈 + 冒烟），不存在"过小"。
- 若 docker 不可用 / `.env.uat` 缺失 → 不硬启动，告诉用户先补齐前置（docker daemon、UAT 专用 env 文件），再重跑本命令。
- 若代码尚未合并到 main（仍在 review 或未 merge）→ 不启动部署，告诉用户："UAT 部署门要求代码先合并到 main；当前请先完成 code review（含 SIT Audit）并合并。"
