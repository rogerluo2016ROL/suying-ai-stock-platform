# PRD — [Feature Name]

> **This is a template.** Copy to `docs/prd/[feature]-[YYYY-MM-DD].md`，填写后删除本介绍段再发布。

- **Date**: YYYY-MM-DD
- **Owner**: product-lead
- **Status**: Draft / Review / Approved / In Progress / Done / Archived
- **Estimated effort tier**: Small / Medium / Large（参考 `.claude/standards/cost-budget.md` 的 token 预算分级）

## 1. Background

为什么做？解决什么用户痛点 / 业务需求？引用相关内部文档、Linear 工单、Slack 讨论、用户访谈记录。

## 2. Goal & Non-Goals

**目标**：

- 一句话目标声明
- 关键成功指标（KPI）—— 上线后用什么数据判断做对了

**Non-Goals**：

- 明确不做什么，防范围蔓延

## 3. User Stories

| ID | As a | I want to | So that |
|---|---|---|---|
| US-1 | 终端用户 | ... | ... |
| US-2 | 管理员 | ... | ... |

## 4. Acceptance Criteria

每条 AC 必须可独立验证，code-reviewer / qa-engineer **逐条核对**。

| ID | Priority | AC | Verification method |
|---|---|---|---|
| AC-1 | P0 | 用户提交邮箱 + 密码后，POST /api/auth/login 返回 200 + JWT token | curl + 检查响应体 |
| AC-2 | P0 | 错误密码返回 401，错误信息不暴露"邮箱不存在" vs "密码错误"的区别 | 手工 / SIT |
| AC-3 | P1 | 失败 5 次后触发限流，返回 429 | SIT |

## 5. Design

- UI 设计：链接到 `docs/design/[feature]/spec.md` + `index.html` 原型
- API 契约：列出新增/变更的接口签名（路径、请求体、响应体、错误码）
- 数据模型：列出新增/变更的表结构（字段、类型、索引）

## 6. Technical Constraints

- 必须遵守 `.claude/standards/coding.md`、`security.md`、`observability.md`
- LLM 集成：参考 skill `agf-wiring-multi-llm-sdk`
- 性能预算：API P95 ≤ 500ms / LLM P95 ≤ 5s
- 不引入新依赖（除非 tech-lead 已起 ADR）

## 7. Cost Estimate

- 预估 LLM token 消耗 / 月：
- 预估 Agent Team 开发消耗 token：
- 触发 cost-budget.md 哪一档？

## 8. Out of Scope / Future Work

不在本次范围、留给后续迭代的工作项。

## 9. Open Questions

未确定的问题，**每条必须标 Owner + Due**，否则不允许进入 Step 2 任务分配（见 `docs/product-workflow.md §4` 与 `agf-writing-prd` skill）。

| ID | 问题 | Owner | Due | 备注 |
|---|---|---|---|---|
| Q-1 | <一句话问题> | <role / 具名> | YYYY-MM-DD | <附加上下文> |
| Q-2 | … | … | … | … |

## 10. Sign-offs

- [ ] product-lead: 初稿
- [ ] tech-lead: 技术可行性 review（仅在涉及架构变更时）
- [ ] frontend-dev / backend-dev / ai-agent-dev / ml-engineer / miniapp-dev: 实现可行性确认（按 PRD 涉及的执行层角色勾选，不涉及的可跳过）
- [ ] uiux-designer: 设计契合 PRD（仅在有 UI 时；含 miniapp UI 时在 MiniApp Mode 下确认）
- [ ] qa-engineer / miniapp-qa-engineer: AC 可测性确认（按 feature 涉及的 QA 角色勾选）
