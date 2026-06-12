# Team Roles and Capability Baseline

> **关于 `Permission` 列**：`permissionMode` 是 Claude Code 官方 sub-agent frontmatter 字段，但**仅在 sub-agent / `--agent` 路径生效，Agent Team teammate 路径被忽略**（详见下方 frontmatter 能力表）。当前启动方式：lead = `product-lead` 以 `--agent product-lead` 启动（见 `agf-team-start.sh`），故 **PL 自身的 `acceptEdits` 生效并成为团队权限基线**，其余 teammate 继承该基线；review-only 等更严模式由 lead 在 spawn 后对单个 teammate 单独切换。**默认不再使用 `--dangerously-skip-permissions`**（仅在显式传该 flag 时启用，自担风险）。
>
> **关于 `Pool 上限` 列**：见 [ADR-001](../../docs/adr/001-multi-instance-worker-pool.md) 与 [`workflow.md` §Multi-instance Worker Pool](workflow.md)。值 = 同 type 并发实例数上限（含 1 表示**不允许 pool**；3-7 表示按 cost-budget 分档自动调）。pool 模式触发条件 + 例外清单见 workflow.md。

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
| Deploy Engineer | `deploy-engineer` | sonnet | slate | acceptEdits | **1**（禁 pool，唯一 UAT 环境）| UAT 环境部署、容器编排、冒烟自检 |
| ML Engineer | `ml-engineer` | sonnet | lime | acceptEdits | **3**（ML 任务通常顺序，pool 收益小）| 多模态模型集成、推理服务接入、图像处理 Pipeline |
| MiniApp Dev | `miniapp-dev` | sonnet | teal | acceptEdits | **3**（小程序 task 通常单一）| 微信小程序开发，默认原生，Taro 兜底 |
| MiniApp Code Reviewer | `miniapp-code-reviewer` | haiku | amber | auto | **3**（haiku 便宜可放大，但小程序场景并发量小）| 小程序代码审查、审核合规、包体积评估 → `docs/reviews/` |
| MiniApp QA Engineer | `miniapp-qa-engineer` | sonnet | rose | acceptEdits | **3**（端口偏移 + 真机调度，pool 隔离比 web 复杂）| 小程序 E2E / UAT 测试执行 |
| Apple Dev | `apple-dev` | sonnet | sky | acceptEdits | **3**（Xcode 工程文件易冲突，pool 收紧）| Swift / SwiftUI macOS+iOS 实现（target 由 task 声明），Unit + SIT 自跑 |
| Apple Code Reviewer | `apple-code-reviewer` | sonnet | stone | auto | **3**（Swift 并发 / 内存审查需 sonnet 档，不降 haiku）| Swift 专项审查（并发 / retain cycle / HIG / 签名配置）+ SIT Audit → `docs/reviews/` |
| Apple QA Engineer | `apple-qa-engineer` | sonnet | fuchsia | acceptEdits | **3**（模拟器 + 真机调度）| XCUITest E2E / UAT（对签名分发包） |
| Apple Release Engineer | `apple-release-engineer` | sonnet | zinc | acceptEdits | **1**（禁 pool，唯一签名身份 + App Store Connect）| 签名 / 公证 / 打包 / TestFlight / App Store 上传，冒烟自检 → `docs/deploy/` |
| Content Writer | `content-writer` | sonnet | violet | acceptEdits | **1**（叙事一致性需单一作者）| Release notes / blog / 用户案例 / 知识沉淀 |
| Growth Analyst | `growth-analyst` | sonnet | indigo | acceptEdits | **1**（实验设计需统一 OMTM 锚点）| 北极星 / OMTM / A/B 实验设计与报告 |

### 角色硬边界（review-only / test-only / deploy-only）

> 本节是"不动源码"类角色边界的**唯一团队级声明**；各 agent 文件只留 1-2 行 + 指针 + 角色特有细节（如 reviewer 的架构风险升级路径），不再整段复述。

| 边界 | 角色 | 产物写入 | 源码层问题的出路 |
|---|---|---|---|
| **review-only** | `code-reviewer` / `miniapp-code-reviewer` / `apple-code-reviewer` | 仅 `docs/reviews/`（工具层已 − Edit、Write 限此目录，见下表） | 发现的问题由 product-lead 重派执行层修复；重大架构问题**同时**升级 tech-lead + product-lead，不替任何人决策"要不要修" |
| **test-only** | `qa-engineer` / `miniapp-qa-engineer` / `apple-qa-engineer` | `docs/qa/` 测试报告 | 失败用例只报告 + 提交证据，由 product-lead 重派执行层修复 |
| **deploy-only** | `deploy-engineer` / `apple-release-engineer` | `docs/deploy/` 部署 / 发布报告 | 冒烟暴露**代码问题** → 退回 product-lead → dev 修复；**环境 / 配置 / 签名材料问题**（端口、`.env.uat`、容器编排、证书 / profile / 公证凭据）→ 自己重跑；apple-release-engineer 可改 `apple/fastlane/` 配置（流水线配置非业务源码） |

共同点：三类角色都**不修改任何业务源码**（`backend/` / `frontend/` / `miniapp/` / `apple/` 的 App 与 AppCore 等）；需要源码变更时一律 SendMessage product-lead 重派，不绕权限边界。

### Agent Tools

本节是角色 **工具集** 与 **预加载 skills** 的唯一团队级能力基线。
若 agent frontmatter、能力图谱或角色说明与本节冲突，以本文件为准，并同步修正冲突处。

> **Frontmatter 字段在不同路径的能力**（影响 spawn 后的实际行为）：
>
> | 字段 | sub-agent 路径 | `claude --agent` headless / `--bg` | Agent Team teammate 路径 |
> |---|---|---|---|
> | `tools` / `disallowedTools` | ✅ 生效 | ✅ 生效 | ✅ 生效；team 协调工具（`SendMessage` / Task*）即使被排除也始终可用 |
> | `permissionMode` | ✅ 生效 | ✅ 生效 | ❌ 忽略，teammate 继承 lead 模式 |
> | `model` | ✅ 生效 | ✅ 生效 | ✅ 生效，teammate 按各自 definition 的 model 档运行（路由基线见 [`cost-budget.md`](cost-budget.md)） |
> | `effort` | ✅ 生效 | ✅ 生效（lead 可再用 session 内 `/effort` 临时调） | ❌ **不生效**，随 session 默认，当前无 per-role 设置手段（操作结论见 [`cost-budget.md`](cost-budget.md) §Effort 维度） |
> | `skills` | ✅ 启动时预加载 | ✅ 启动时预加载 | ❌ **不生效**，teammate 仅按 description 关键词匹配或 `/skill-name` 显式调起，与普通 session 一致 |
> | `mcpServers` | ✅ 生效 | ✅ 生效 | ❌ **不生效**，teammate 从项目 / 用户 settings 加载 MCP，与普通 session 一致 |
> | per-agent `hooks:` | ⚠️ 在 team 路径不可靠 | ⚠️ 在 team 路径不可靠 | ❌ 不可靠，所有 hook 统一注册到 `.claude/settings.json` |
> | `memory` | ✅ spawn 时预加载 `.claude/agent-memory/<name>/MEMORY.md` 前 200 行 / 25KB | ✅ 同 sub-agent | ⚠️ [官方文档未明示，按 exclusion 列表推断 likely 生效] 未实测；如发现 teammate 路径下不生效，回退到主 Claude `autoMemoryEnabled` 兜底 |
>
> **所有路径都生效的硬约束**：`settings.json` 的 `permissions.allow/deny`、agent `tools` 列表、`.claude/hooks/` 中央注册的 hook。
>
> 文档锚点：[`skills` / `mcpServers` 在 teammate 路径被忽略](https://code.claude.com/docs/en/agent-teams#use-subagent-definitions-for-teammates)；[`permissionMode` 与 headless 行为](https://code.claude.com/docs/en/sub-agents#supported-frontmatter-fields)。
>
> **实操影响**：本表后文「Plugin Skills（启动时预加载）」列只在 sub-agent 与 headless `--agent` 路径自动生效；走 `/agf-team-start` 的 Agent Team 路径下，teammate 必须在 spawn prompt 里显式提到 skill 名（如"使用 `agf-wiring-multi-llm-sdk` 接入 DeepSeek"）或依赖 description 关键词触发，否则不会被预加载。`qa-engineer` 的 `chrome-devtools-mcp:chrome-devtools` plugin **skill** 同理（plugin 路径）；但 `chrome-devtools` **MCP server** 本身通过项目级 `.mcp.json` 加载，所有路径（含 teammate）都生效，与 plugin 是否安装无关。⚠️ **关键纠正**："server 被加载" ≠ "agent 能调它的工具"——teammate / sub-agent 都按 `tools` 白名单门控（见上表 `tools` 行：所有路径硬生效），故 `qa-engineer` 的 `tools` **必须显式含 `mcp__chrome-devtools__*`** 才放行；又因 MCP 工具默认 deferred（ToolSearch 延迟加载），sub-agent 路径下可能取不到（[issue #25200](https://github.com/anthropics/claude-code/issues/25200) closed/not-planned），故在 `.mcp.json` 对该 server 设 `alwaysLoad: true` 令其启动即载。
>
> 本表的 `Plugin Skills` 列在所有路径都可被对应 agent 直接 `Skill({skill: "..."})` 调起，无需绕路 Read SKILL.md 文件。

**通用工具底座**（全员默认拥有）：`Glob, Grep, Read, Write, Edit, Bash, SendMessage, TaskGet, TaskUpdate, TaskList, Skill`

下表只列出每个 agent 在通用底座之上的**调整**（增减或限制），以及预加载的 plugin skills。

| Agent | 工具调整 | Plugin Skills（启动时预加载） |
|---|---|---|
| `product-lead` | + WebFetch, WebSearch, TaskCreate | `superpowers:brainstorming`, `superpowers:writing-plans`, `superpowers:using-git-worktrees`, `superpowers:requesting-code-review`, `superpowers:receiving-code-review`, `superpowers:finishing-a-development-branch` |
| `tech-lead` | + WebFetch, WebSearch, `mcp__context7__*` | `superpowers:brainstorming`, `superpowers:writing-plans`, `superpowers:test-driven-development`, `superpowers:systematic-debugging`, `superpowers:verification-before-completion`, `superpowers:requesting-code-review`, `superpowers:receiving-code-review` |
| `uiux-designer` | + WebFetch | `frontend-design:frontend-design` |
| `frontend-dev` | + WebFetch, `mcp__context7__*` | `frontend-design:frontend-design`, `feature-dev:feature-dev`, `agf-running-sit-tests`, `superpowers:test-driven-development`, `superpowers:systematic-debugging`, `superpowers:verification-before-completion`, `superpowers:receiving-code-review` |
| `backend-dev` | + `mcp__context7__*` | `code-simplifier:code-simplifier`, `feature-dev:feature-dev`, `agf-wiring-multi-llm-sdk`, `agf-running-sit-tests`, `superpowers:test-driven-development`, `superpowers:systematic-debugging`, `superpowers:verification-before-completion`, `superpowers:receiving-code-review` |
| `ai-agent-dev` | + WebFetch, WebSearch, TaskCreate, `mcp__context7__*` | `feature-dev:feature-dev`, `agf-wiring-multi-llm-sdk`, `agf-running-sit-tests`, `superpowers:test-driven-development`, `superpowers:systematic-debugging`, `superpowers:verification-before-completion`, `superpowers:receiving-code-review` |
| `code-reviewer` | − Edit；Write 限 `docs/reviews/`（review-only） | `code-review:code-review`, `code-simplifier:code-simplifier`, `simplify`（仅 Phase 1+2 review，不跑 Phase 3 fix）, `agf-running-sit-tests`（**仅作 audit 参考，不强制调用**——reviewer 不跑 SIT，预加载用于读懂 dev SIT 范围 / 评估 dev SIT 结论是否合理） |
| `qa-engineer` | + `mcp__chrome-devtools__*` **写入 `tools` 白名单**（放行 MCP 工具的关键——白名单不含则一律调不到）；server 由项目级 `.mcp.json` 声明 `npx -y chrome-devtools-mcp@latest` 且设 `alwaysLoad: true`（跳过 deferred 延迟加载）；frontmatter `mcpServers: chrome-devtools` 仅 sub-agent 路径生效、teammate 路径被忽略，故 `.mcp.json` 才是 SSOT | `chrome-devtools-mcp:chrome-devtools`, `agf-writing-qa-report`, `superpowers:systematic-debugging`, `superpowers:verification-before-completion` |
| `deploy-engineer` | （仅通用底座） | `agf-deploying-uat`, `superpowers:systematic-debugging`, `superpowers:verification-before-completion` |
| `ml-engineer` | + WebFetch, WebSearch, `mcp__context7__*` | `agf-wiring-multi-llm-sdk`, `agf-running-sit-tests`, `superpowers:test-driven-development`, `superpowers:systematic-debugging`, `superpowers:verification-before-completion`, `superpowers:receiving-code-review` |
| `miniapp-dev` | + WebFetch | `feature-dev:feature-dev`, `agf-running-sit-tests`, `superpowers:test-driven-development`, `superpowers:systematic-debugging`, `superpowers:verification-before-completion`, `superpowers:receiving-code-review` |
| `miniapp-code-reviewer` | − Edit；Write 限 `docs/reviews/`（review-only） | `code-review:code-review`, `code-simplifier:code-simplifier`, `simplify`（仅 Phase 1+2 review，不跑 Phase 3 fix）, `agf-running-sit-tests`（**仅作 audit 参考，不强制调用**——reviewer 不跑 SIT，预加载用于读懂 miniapp-dev SIT 范围 / 评估 dev SIT 结论是否合理） |
| `miniapp-qa-engineer` | （仅通用底座） | `agf-writing-qa-report`, `superpowers:systematic-debugging`, `superpowers:verification-before-completion` |
| `apple-dev` | + WebFetch, `mcp__context7__*`, `mcp__xcodebuild__*`（XcodeBuildMCP：build / 模拟器 / 真机 devicectl / 跑测试；server 走 `.mcp.json` 两道门，同 qa-engineer 的 chrome-devtools 模式） | `feature-dev:feature-dev`, `agf-running-apple-sit`, `superpowers:test-driven-development`, `superpowers:systematic-debugging`, `superpowers:verification-before-completion`, `superpowers:receiving-code-review` |
| `apple-code-reviewer` | − Edit；Write 限 `docs/reviews/`（review-only） | `code-review:code-review`, `code-simplifier:code-simplifier`, `simplify`（仅 Phase 1+2 review，不跑 Phase 3 fix）, `agf-running-apple-sit`（**仅作 audit 参考，不强制调用**——reviewer 不跑 SIT，预加载用于读懂 apple-dev SIT 范围 / 评估其 SIT 结论是否合理） |
| `apple-qa-engineer` | + `mcp__xcodebuild__*`（XcodeBuildMCP：真机/模拟器列表、devicectl 装包、launch、截图、XCUITest；两道门同上） | `agf-writing-qa-report`, `superpowers:systematic-debugging`, `superpowers:verification-before-completion` |
| `apple-release-engineer` | （仅通用底座） | `agf-releasing-apple`, `superpowers:systematic-debugging`, `superpowers:verification-before-completion` |
| `content-writer` | + WebFetch, WebSearch | `superpowers:brainstorming` |
| `growth-analyst` | + WebFetch, WebSearch | `superpowers:brainstorming`, `superpowers:writing-plans` |

通用工具底座 + 其他 plugin skills 均来自 Claude Code 内置或官方 plugin marketplace。`qa-engineer` 的 `chrome-devtools` server 加载机制（`.mcp.json` 声明 + `tools` 白名单放行两道独立门 + 可选 `/plugin install chrome-devtools-mcp` slash command）见上方「实操影响」与「关键纠正」说明，此处不重复。`context7` server 走同款两道门：`.mcp.json` 声明 `@upstash/context7-mcp` 且 `alwaysLoad: true`（teammate 白名单无 ToolSearch，deferred 工具拿不到 schema），`tools` 白名单放行 `mcp__context7__*`——当前授予 `tech-lead`（ADR 版本查证）+ `frontend-dev` / `backend-dev` / `ai-agent-dev` / `ml-engineer` / `apple-dev`（第三方库当前版本文档，防 API 幻觉）。`xcodebuild` server（XcodeBuildMCP，Apple 轨的 chrome-devtools 对等物）同款两道门：`.mcp.json` 声明 `npx -y xcodebuildmcp@latest` 且 `alwaysLoad: true`，`tools` 白名单放行 `mcp__xcodebuild__*`——当前授予 `apple-dev`（build / 模拟器 / 跑测试调试）+ `apple-qa-engineer`（真机 devicectl / XCUITest / 截图取证）；签名不归它管（fastlane match，ADR-009）。其余角色无第三方依赖，可直接分发复用。
