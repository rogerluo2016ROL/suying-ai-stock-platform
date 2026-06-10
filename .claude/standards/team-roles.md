# Team Roles and Capability Baseline

> **关于 `Permission` 列**：表中 `Permission` 列是**团队约定的"推荐运行模式"**，并非 Claude Code 官方 sub-agent frontmatter 字段；Agent Team 路径下 `permissionMode` 由 lead session 统一控制（团队启动时 lead 已声明 `--dangerously-skip-permissions`），本表列仅作角色画像参考。
>
> **关于 `Pool 上限` 列**：见 [ADR-001](../../docs/adr/001-multi-instance-worker-pool.md) 与 [`workflow.md` §Multi-instance Worker Pool](workflow.md#multi-instance-worker-poolDev--Reviewer--QA-三层-pool)。值 = 同 type 并发实例数上限（含 1 表示**不允许 pool**；3-7 表示按 cost-budget 分档自动调）。pool 模式触发条件 + 例外清单见 workflow.md。

## Team Roles

| Role | Agent Name | Model | Color | Permission | Pool 上限 | Focus |
|---|---|---|---|---|---|---|
| Product Lead | `product-lead` | opus | orange | acceptEdits | **1**（唯一编排者，禁 pool）| 需求挖掘、PRD、任务分配、团队协调、验收 |
| Tech Lead | `tech-lead` | opus | blue | acceptEdits | **1**（条件触发顾问，无 pool 需求）| 架构基线、技术选型、架构风险评审 |
| UI/UX Designer | `uiux-designer` | sonnet | purple | acceptEdits | **1**（视觉一致性需单一审美锚点）| 界面设计、交互流程、体验优化 |
| Frontend Dev | `frontend-dev` | sonnet | cyan | acceptEdits | **5**（Small=3 / Med=5 / Large=7）| UI 组件、页面、API 对接 |
| Backend Dev | `backend-dev` | sonnet | green | acceptEdits | **5**（Small=3 / Med=5 / Large=7）| REST API、数据库、服务端逻辑 |
| AI Agent Dev | `ai-agent-dev` | opus | pink | acceptEdits | **3**（opus 成本高，pool 上限收紧）| LLM 集成、Prompt 工程、RAG |
| Code Reviewer | `code-reviewer` | sonnet | yellow | auto | **5**（review pool 主力，处理 dev fan-out 后的并发 review）| 代码质量、安全审计 → `docs/reviews/` |
| QA Engineer | `qa-engineer` | sonnet | red | acceptEdits | **5**（QA pool 主力，端口偏移隔离）| E2E / UAT 测试执行、质量验证 |
| ML Engineer | `ml-engineer` | sonnet | lime | acceptEdits | **3**（ML 任务通常顺序，pool 收益小）| 多模态模型集成、推理服务接入、图像处理 Pipeline |
| MiniApp Dev | `miniapp-dev` | sonnet | teal | acceptEdits | **3**（小程序 task 通常单一）| 微信小程序开发，默认原生，Taro 兜底 |
| MiniApp Code Reviewer | `miniapp-code-reviewer` | haiku | amber | auto | **3**（haiku 便宜可放大，但小程序场景并发量小）| 小程序代码审查、审核合规、包体积评估 → `docs/reviews/` |
| MiniApp QA Engineer | `miniapp-qa-engineer` | sonnet | rose | acceptEdits | **3**（端口偏移 + 真机调度，pool 隔离比 web 复杂）| 小程序 E2E / UAT 测试执行 |
| Content Writer | `content-writer` | sonnet | violet | acceptEdits | **1**（叙事一致性需单一作者）| Release notes / blog / 用户案例 / 知识沉淀 |
| Growth Analyst | `growth-analyst` | sonnet | indigo | acceptEdits | **1**（实验设计需统一 OMTM 锚点）| 北极星 / OMTM / A/B 实验设计与报告 |

### Agent Tools

本节是角色 **工具集** 与 **预加载 skills** 的唯一团队级能力基线。
若 agent frontmatter、能力图谱或角色说明与本节冲突，以本文件为准，并同步修正冲突处。

> **Frontmatter 字段在不同路径的能力**（影响 spawn 后的实际行为）：
>
> | 字段 | sub-agent 路径 | `claude --agent` headless / `--bg` | Agent Team teammate 路径 |
> |---|---|---|---|
> | `tools` / `disallowedTools` | ✅ 生效 | ✅ 生效（自 2.1.119） | ✅ 生效；team 协调工具（`SendMessage` / Task*）即使被排除也始终可用 |
> | `permissionMode` | ✅ 生效 | ✅ 生效（自 2.1.119） | ❌ 忽略，teammate 继承 lead 模式 |
> | `skills` | ✅ 启动时预加载 | ✅ 启动时预加载 | ❌ **不生效**，teammate 仅按 description 关键词匹配或 `/skill-name` 显式调起，与普通 session 一致 |
> | `mcpServers` | ✅ 生效 | ✅ 生效 | ❌ **不生效**，teammate 从项目 / 用户 settings 加载 MCP，与普通 session 一致 |
> | per-agent `hooks:` | ⚠️ 在 team 路径不可靠 | ⚠️ 在 team 路径不可靠 | ❌ 不可靠，所有 hook 统一注册到 `.claude/settings.json` |
> | `memory` | ✅ spawn 时预加载 `.claude/agent-memory/<name>/MEMORY.md` 前 200 行 / 25KB | ✅ 同 sub-agent | ⚠️ [官方文档未明示，按 exclusion 列表推断 likely 生效] 未实测；如发现 teammate 路径下不生效，回退到主 Claude `autoMemoryEnabled` 兜底 |
>
> **所有路径都生效的硬约束**：`settings.json` 的 `permissions.allow/deny`、agent `tools` 列表、`.claude/hooks/` 中央注册的 hook。
>
> 文档锚点：[`skills` / `mcpServers` 在 teammate 路径被忽略](https://code.claude.com/docs/en/agent-teams#use-subagent-definitions-for-teammates)；[`permissionMode` 与 headless 行为](https://code.claude.com/docs/en/sub-agents#supported-frontmatter-fields)。
>
> **实操影响**：本表后文「Plugin Skills（启动时预加载）」列只在 sub-agent 与 headless `--agent` 路径自动生效；走 `/agf-team-start` 的 Agent Team 路径下，teammate 必须在 spawn prompt 里显式提到 skill 名（如"使用 `agf-wiring-multi-llm-sdk` 接入 DeepSeek"）或依赖 description 关键词触发，否则不会被预加载。`qa-engineer` 的 `chrome-devtools-mcp:chrome-devtools` plugin **skill** 同理（plugin 路径）；但 `chrome-devtools` **MCP server** 本身通过项目级 `.mcp.json` 加载，所有路径（含 teammate）都生效，与 plugin 是否安装无关。
>
> Subagent 通过 `Skill` 工具发现项目 / 用户 / plugin skill 在 2.1.133 之前存在 bug，已修复——本表的 `Plugin Skills` 列在所有路径都可被对应 agent 直接 `Skill({skill: "..."})` 调起，无需绕路 Read SKILL.md 文件。

**通用工具底座**（全员默认拥有）：`Glob, Grep, Read, Write, Edit, Bash, SendMessage, TaskGet, TaskUpdate, TaskList, Skill`

下表只列出每个 agent 在通用底座之上的**调整**（增减或限制），以及预加载的 plugin skills。

| Agent | 工具调整 | Plugin Skills（启动时预加载） |
|---|---|---|
| `product-lead` | + WebFetch, WebSearch, TaskCreate | `superpowers:brainstorming`, `superpowers:writing-plans`, `superpowers:using-git-worktrees`, `superpowers:requesting-code-review`, `superpowers:receiving-code-review`, `superpowers:finishing-a-development-branch` |
| `tech-lead` | + WebFetch, WebSearch | `superpowers:brainstorming`, `superpowers:writing-plans`, `superpowers:test-driven-development`, `superpowers:systematic-debugging`, `superpowers:verification-before-completion`, `superpowers:requesting-code-review`, `superpowers:receiving-code-review` |
| `uiux-designer` | + WebFetch | `frontend-design:frontend-design` |
| `frontend-dev` | + WebFetch | `frontend-design:frontend-design`, `feature-dev:feature-dev`, `agf-running-sit-tests`, `superpowers:test-driven-development`, `superpowers:systematic-debugging`, `superpowers:verification-before-completion`, `superpowers:receiving-code-review` |
| `backend-dev` | （仅通用底座） | `code-simplifier:code-simplifier`, `feature-dev:feature-dev`, `agf-wiring-multi-llm-sdk`, `agf-running-sit-tests`, `superpowers:test-driven-development`, `superpowers:systematic-debugging`, `superpowers:verification-before-completion`, `superpowers:receiving-code-review` |
| `ai-agent-dev` | + WebFetch, WebSearch, TaskCreate | `feature-dev:feature-dev`, `agf-wiring-multi-llm-sdk`, `agf-running-sit-tests`, `superpowers:test-driven-development`, `superpowers:systematic-debugging`, `superpowers:verification-before-completion`, `superpowers:receiving-code-review` |
| `code-reviewer` | − Edit；Write 限 `docs/reviews/`（review-only） | `code-review:code-review`, `code-simplifier:code-simplifier`, `simplify`（仅 Phase 1+2 review，不跑 Phase 3 fix）, `agf-running-sit-tests`（**仅作 audit 参考，不强制调用**——reviewer 不跑 SIT，预加载用于读懂 dev SIT 范围 / 评估 dev SIT 结论是否合理） |
| `qa-engineer` | + `mcpServers: chrome-devtools`（项目级 `.mcp.json` 声明 `npx -y chrome-devtools-mcp@latest`，E2E 浏览器测试用） | `chrome-devtools-mcp:chrome-devtools`, `agf-writing-qa-report`, `superpowers:systematic-debugging`, `superpowers:verification-before-completion` |
| `ml-engineer` | + WebFetch, WebSearch | `agf-wiring-multi-llm-sdk`, `agf-running-sit-tests`, `superpowers:test-driven-development`, `superpowers:systematic-debugging`, `superpowers:verification-before-completion`, `superpowers:receiving-code-review` |
| `miniapp-dev` | + WebFetch | `feature-dev:feature-dev`, `agf-running-sit-tests`, `superpowers:test-driven-development`, `superpowers:systematic-debugging`, `superpowers:verification-before-completion`, `superpowers:receiving-code-review` |
| `miniapp-code-reviewer` | − Edit；Write 限 `docs/reviews/`（review-only） | `code-review:code-review`, `code-simplifier:code-simplifier`, `simplify`（仅 Phase 1+2 review，不跑 Phase 3 fix）, `agf-running-sit-tests`（**仅作 audit 参考，不强制调用**——reviewer 不跑 SIT，预加载用于读懂 miniapp-dev SIT 范围 / 评估 dev SIT 结论是否合理） |
| `miniapp-qa-engineer` | （仅通用底座） | `agf-writing-qa-report`, `superpowers:systematic-debugging`, `superpowers:verification-before-completion` |
| `content-writer` | + WebFetch, WebSearch | `superpowers:brainstorming` |
| `growth-analyst` | + WebFetch, WebSearch | `superpowers:brainstorming`, `superpowers:writing-plans` |

通用工具底座 + 其他 plugin skills 均来自 Claude Code 内置或官方 plugin marketplace。`qa-engineer` 的 `chrome-devtools` MCP server **由项目根 `.mcp.json` 声明**（`npx -y chrome-devtools-mcp@latest`），团队 clone 后自动可用，所有 agent 路径（含 Agent Team teammate）都生效，无需手动 `/plugin install`；如需 plugin 形态的 `/chrome-devtools-mcp:*` slash command（独立于本 MCP server），另行 `/plugin install chrome-devtools-mcp`，不装不影响 `.mcp.json` 提供的 server 工作。其余角色无第三方依赖，可直接分发复用。
