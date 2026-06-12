# Superpowers Skills Policy

> 基线：superpowers plugin（版本以本地安装为准）。每个 skill 的完整描述以本地 SKILL.md 为准：
> `~/.claude/plugins/cache/claude-plugins-official/superpowers/<version>/skills/<name>/SKILL.md`

团队在关键流程节点必须调用 `superpowers:` 系列 skill，保证需求澄清、实现质量、完成验证、代码审查的一致性。

## 1. 强制调用 skill 映射（含 agf-* 项目 skills）

> 本表混合 `superpowers:*` 与项目级 `agf-*` skills；二者"强制"语义等价（dev 必走 SIT 与 TDD 同一档位），仅命名空间不同。

满足"何时调"列条件时**必须先调 skill，再做后续动作**。

| Skill | 谁调 | 何时调 | 跳过条件 |
|---|---|---|---|
| `superpowers:using-superpowers` | 主 Claude（每会话） | 会话启动时由 SessionStart 自动注入；任何响应/clarifying question 之前 | 由 subagent 被直接 dispatch 时（已在 SUBAGENT-STOP 豁免） |
| `superpowers:brainstorming` | product-lead | 接到模糊/多选项需求 → 写 PRD 之前 | 用户已给明确 PRD、bug 修复、纯文档/小改 |
| `superpowers:writing-plans` | product-lead | PRD 涉及多步/跨角色/≥3 AC → 分配之前 | 单角色/单 AC 任务 |
| `superpowers:using-git-worktrees` | product-lead | 并行派 ≥2 个 execution-layer teammate 之前 | 单实例派发、纯只读 reviewer 并行 |
| `superpowers:test-driven-development` | frontend-dev / backend-dev / ai-agent-dev / ml-engineer / miniapp-dev | 收到"新功能"或"bugfix"任务 → 写实现前 | 纯重构、只改文档/配置 |
| `agf-running-sit-tests` | frontend-dev / backend-dev / ai-agent-dev / ml-engineer / miniapp-dev | Unit 全绿后、code-review 前 → 自跑 API+DB+external 单边集成 SIT，证据写入 `progress/<role>.md` | 纯文档/配置；无外部 IO 的算法纯函数 |
| `superpowers:systematic-debugging` | 所有开发者 + qa-engineer / miniapp-qa-engineer + deploy-engineer | 遇测试失败 / bug / 预期外行为 → 定位前；deploy-engineer 部署 / 冒烟遇故障 → 定位（环境 vs 代码）前 | 新功能正常流程 |
| `superpowers:verification-before-completion` | 所有开发者 + qa-engineer / miniapp-qa-engineer + deploy-engineer | 发完成报告 / E2E-UAT 测试报告之前；deploy-engineer 交接 qa-engineer 前确认 UAT 栈真实可用（冒烟真实输出）| 中间汇报（progress 阻塞条目除外） |
| `superpowers:requesting-code-review` | product-lead | 触发 code-reviewer / miniapp-code-reviewer 前 | 文档类任务 |
| `superpowers:receiving-code-review` | product-lead / 开发者 | 收到审查结论 / 被打回要改 → 处理前 | — |
| `superpowers:finishing-a-development-branch` | product-lead | UAT 签字后整合到主干前（决定 merge / PR / 保留分支） | 模板自身的 internal commit |

> `tech-lead` 不在表内：tech-lead 预加载 skills 是条件触发介入时的后备能力，不强制主动调用。

## 2. 推荐但非强制

按 SKILL.md 自带触发条件按需用：

- `superpowers:dispatching-parallel-agents` — 主 Claude / product-lead 决定是否并行多 teammate 时；与 [`workflow.md`](workflow.md) "Parallel Dispatch" 边界一致
- `superpowers:executing-plans` — 把 plan 派去**单独 session** 执行时；本仓库默认在 Team Mode 内由各 teammate 自行消化 plan
- `superpowers:subagent-driven-development` — 在**当前 session 内**用一组 subagent 推进 plan 的独立 task；与 Agent Team 多 teammate 模式互斥，二选一
- `superpowers:writing-skills` — 仅在新增/编辑 `.claude/skills/<name>/SKILL.md` 时调

## 3. 调用语法

```
Skill({skill: "superpowers:brainstorming", args: "[需求/情境摘要]"})
Skill({skill: "superpowers:verification-before-completion"})
```

`args` 可选；带上能让 skill 一进来就有上下文（尤其 `brainstorming` / `writing-plans`）。

## 4. Skills used 字段

- 完成报告 / 任务分配 SendMessage **必须包含 `Skills used:` 字段**，未列视为未遵守
- 同时按 [ac-lifecycle.md "Self-Reporting Pattern"](ac-lifecycle.md)，`progress/<role>.md` 5 段格式中的 **`**Skills**`** 字段（与 SendMessage `Skills used:` 等价）——`progress/` 是底稿，SendMessage 是摘要，二者列表必须一致
- product-lead 验收时核验：
  - "新功能" / "bugfix" 缺 `superpowers:test-driven-development` → 打回重做
  - 报"完成"缺 `superpowers:verification-before-completion` → 打回重验
  - 触发 code review 前缺 `superpowers:requesting-code-review` → 打回补流程
  - 收到打回要改缺 `superpowers:receiving-code-review` → 打回，要求按 skill 流程审查反馈再改

## 5. 多 skill 同时适用 — 优先级

1. **Process skills 先调**（决定 HOW）：`brainstorming` / `systematic-debugging`
2. **Implementation skills 后调**（决定 WHAT）：`test-driven-development` / `using-git-worktrees`

典型组合：
- 新功能：`brainstorming` → `writing-plans` →（并行时 `using-git-worktrees`）→ `test-driven-development` → `verification-before-completion` → `requesting-code-review`
- Bug 修复：`systematic-debugging` → `test-driven-development`（写复现测试）→ `verification-before-completion`
- 收到审查反馈：`receiving-code-review` → 视情况进 `systematic-debugging` 或直接改
