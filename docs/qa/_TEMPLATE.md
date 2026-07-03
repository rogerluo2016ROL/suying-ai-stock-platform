---
# 结构化元数据（matrix.sh / 自动化工具解析用；不要删，值可改）
feature: [feature-slug]
stage: E2E                            # E2E | UAT
date: YYYY-MM-DD
tester: qa-engineer                   # pool 模式填实例名如 qa-engineer-1
report_verdict: Promote               # Promote | Block | Conditional promote（QA 报告级词表）
uat_signoff_verdict: ""               # 仅 UAT 阶段填：approve | request changes（product-lead 业务签字词表）
ac_total: 0
ac_passed: 0
ac_failed: 0
ac_blocked: 0
p0_pass2_total: 0                     # P0 case 总数（pass^2 检验对象）
p0_pass2_ok: 0                        # P0 case 中 pass^2 = 2/2 的数量
---

# QA Report — [Feature Name] — [E2E / UAT]

> **This is a template.** 路径命名（含 pool 模式）：
> - 单实例 E2E：`docs/qa/[feature]-e2e-[YYYY-MM-DD].md`
> - 单实例 UAT：`docs/qa/[feature]-uat-[YYYY-MM-DD].md`
> - Pool 模式 E2E 实例 N：`docs/qa/[feature]-e2e-q<N>-[YYYY-MM-DD].md`
> - Pool 模式 UAT 实例 N：`docs/qa/[feature]-uat-q<N>-[YYYY-MM-DD].md`
>
> **保留顶部 YAML frontmatter**——`agf-matrix.sh --type=qa` 等工具依赖它解析 verdict + pass^2 计数（详见 `ADR-001`）。删除本介绍段后再发布。
>
> 完整链路通常产出 2 份：E2E → UAT；SIT 证据由 dev 自跑写入 `progress/<role>.md`，不在本模板范围（详见 skill `agf-running-sit-tests`）。

- **Date**: YYYY-MM-DD
- **Stage**: E2E / UAT
- **Tester**: qa-engineer ([model name]) / 业务方姓名（UAT）
- **Branch**: [branch + commit hash]
- **Environment**: local docker-compose / staging / pre-prod
- **需求来源**: `docs/changes/[change]/`（`tasks.md` 含 AC↔Scenario 映射表；旧流程 fallback：`docs/prd/[feature]-[date].md`）
- **Code review report**: `docs/reviews/[feature]-[date].md`

> **词表说明**：4 套 verdict 互不替代，全名与归属见 [`workflow.md`](../../.claude/standards/workflow.md) §Verdict 词表。本模板自有的是**报告级 Verdict**（`✅ Promote / ❌ Block / ⚠️ Conditional promote`）——qa-engineer 的"是否可进下一阶段"建议，业务签字归 product-lead。

## Summary

- Total AC: N
- Passed: M
- Failed: K
- Blocked: J
- 控件遍历（仅 E2E 且含前端 feature）: 已遍历 N 个主要可交互控件并逐个断言可观测后果（DOM/网络/路由/状态；`.claude/standards/testing.md` 前后端对接强制覆盖项 ③）
- 界面渲染核查（仅 UAT 且含界面 feature）: N/N 界面真渲染 + 截图 + 读图四查通过（矩阵 SSOT 在用例文档；`.claude/standards/testing.md`「UAT 界面渲染核查」）
- 本报告级 Verdict: <填三档之一>（见 frontmatter `report_verdict`）

## Pre-conditions Checked

- [ ] 单元测试 + lint + typecheck 全绿
- [ ] code-reviewer 报告已存在且代码 verdict ≠ `block`（前两档允许进入 E2E）
- [ ] code-reviewer SIT Audit Verdict ∈ {`✅ Pass`, `⚠️ Pass with concerns`}（`❌ Redo SIT` 不允许进入 E2E）
- [ ] 验收来源可访问（变更文件夹 `tasks.md` 的 AC↔Scenario 映射表；或 PRD fallback）
- [ ] 环境就绪（DB 起来 / 迁移已 apply / 服务已启动）
- [ ] **（仅 UAT）用例文档已审核**：`docs/qa/[feature]-uat-cases-[date].md` 存在且 `status: Approved`（MAJOR / MINOR 强制；UAT 报告的 AC/用例证据 SSOT 在用例文档，本报告引用用例 ID 不重复粘贴）
- [ ] **Pool 模式实例隔离**（仅 qa-engineer-N / N≥1 时必填）：本实例已 `export POOL_INSTANCE=<N>` + `docker compose up -d` 启用端口偏移（POSTGRES_PORT=5432+N×100 等），与其他并行实例无端口/数据冲突；单实例（pool=off）保持空。详 `docker-compose.yml` + `ADR-001`

## AC Results

> **E2E**：每条 AC 按下方全量五段写。**UAT**：证据 SSOT 在用例文档 `docs/qa/[feature]-uat-cases-[date].md`（执行时回填）——本节改为「用例 ID + verdict 汇总表 + 链接用例文档」，**不重复粘贴证据**。

### AC-1 (P0): [AC 原文，来自 changes/tasks.md 映射表；PRD fallback]

- **Priority**: P0 / P1 / P2（来自 changes/tasks.md AC↔Scenario 映射表的优先级；旧 PRD 流程取 PRD §4。决定跑几次）
- **Setup**: [起始状态：DB 行 / fixture / 用户登录态]
- **Action**: [触发步骤：UI 点击 / curl / SDK 调用]
- **Expected**: [复制 AC 原文：changes/tasks.md 映射表，或 PRD fallback]
- **Actual (run 1)**:
  ```
  HTTP/1.1 200 OK
  Content-Type: application/json
  {"id": 42, "status": "created"}
  ```
- **Actual (run 2)** [**P0 必填，P1/P2 可空**]:
  ```
  HTTP/1.1 200 OK
  ...（与 run 1 一致或差异点）
  ```
- **Reliability**: `pass^1 = 1/1` / `pass^2 = 2/2`（P0）或 `pass^1 = 1/1`（P1/P2）
- **Verdict**: ✅ Pass / ❌ Fail / ⚠️ Blocked / ⚠️ Flaky（两次不一致 = Flaky，按 fail 处理）

(每个 AC 重复一节，**禁止合并写 'all passed'**)

## Defects Found

| ID | Severity | Title | Repro steps | Suspected file |
|---|---|---|---|---|
| DEF-1 | High | 登录后立即调用 /me 返回 401 | 1. POST /login 拿 token 2. GET /me with Bearer | backend/app/middleware/auth.py |

## Cross-stage notes

- E2E → UAT：UAT 由业务方主导，QA 协助备数据 + 操作手册

## Cost (this QA session)

- Tokens consumed: [from /usage]
- Estimated cost: [CNY]
- 同 feature 累计（E2E + UAT 总和）：[CNY]

## Hand-off

- ✅ Promote → SendMessage product-lead 进下一阶段
- ❌ Block → SendMessage product-lead 列 critical defect，派回 dev
- ⚠️ Conditional → P2 defect 单独建 issue，allow 进下一阶段
