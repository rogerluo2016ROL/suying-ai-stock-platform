# Testing Standards

## Testing Standards

四级测试分工，门槛递进（前一级通过才进下一级）：

| 级别 | 测试对象 | 依赖处理 | 编写者 | 工具 | 触发时机 |
|---|---|---|---|---|---|
| **Unit** | 单个函数/模块/组件 | 全部 Mock | 开发者自己（frontend-dev / backend-dev / ai-agent-dev / ml-engineer / miniapp-dev） | Jest / Vitest / pytest | **test-first**（red → green → refactor，见 ac-lifecycle.md DoD） |
| **SIT** | API + 数据库 + 外部服务协同 | DB 真实，外部 API 可 Mock | 开发者（frontend-dev / backend-dev / ai-agent-dev / ml-engineer / miniapp-dev） | Supertest / pytest + 真实 DB | 功能完成后随代码提交 |
| **E2E** | 完整用户操作流程 | 全部真实 | qa-engineer | Playwright / chrome-devtools-mcp | code-review 通过后（含 SIT Audit） |
| **UAT** | PRD 验收标准（业务视角） | 全部真实 | qa-engineer 执行 + product-lead 判定 | E2E 脚本 + 人工确认 | E2E 通过后 |

- **开发者职责**：Unit + SIT 都随代码提交（Unit 走 Mock，集成层走 API+DB+external 单边集成），不转包给测试角色
- **前端 SIT mock 来源**：含前端的 feature，前端 SIT 的 MSW mock 必须来自 orval 生成产物（`*.msw.ts`，禁手写）——契约同步机制见下文「前后端对接强制覆盖项」节 + [ADR-006](../../docs/adr/006-frontend-backend-contract-sync.md)
- **Apple 轨**：`apple-dev` 同样承担 Unit（Swift Testing，`swift test`）+ SIT（`xcodebuild test` + 模拟器）自跑，流程按 skill `agf-running-apple-sit`；E2E（XCUITest 对签名分发包）/ UAT 由 `apple-qa-engineer` 执行——完整测试矩阵见 [`apple-native.md` §9](apple-native.md)，SIT mock 必须实现生成的 `APIProtocol`（禁手写 JSON fixture，见 [ADR-008](../../docs/adr/008-apple-backend-contract-sync.md)）
- **UAT 判定权**：唯一由 product-lead 对照 PRD AC 签字，qa-engineer 只执行并出报告
- **测试报告**：SIT 证据写入 `progress/<role>.md` 的 `**SIT 证据**` 段（不再单独产 `docs/qa/[feature]-sit-*.md`）；E2E / UAT 完成后分别输出至 `docs/qa/[feature]-[e2e|uat]-[YYYY-MM-DD].md`
- **阶段门槛 / 失败回退**：code-review (含 SIT Audit) 通过 → E2E → UAT；任一阶段失败由 product-lead 重新分派执行层修复，qa-engineer 和 code-reviewer 不直接改实现
- **TDD 是核心纪律**（非建议）：新功能 / bugfix 任务必须按 red → green → refactor 顺序，PR commit history 能看出 test commit 早于 impl commit；详见 [`ac-lifecycle.md` DoD](./ac-lifecycle.md) + skill `superpowers:test-driven-development`；纯重构 / 文档 / 配置任务可跳过

## UAT 用例文档（用户审核 gate）

> UAT 用例不再隐含在"qa 读 AC 直接测"里——**先成文、用户审核确认、再执行**。本节是该 gate 的 SSOT；骨架在模板 [`docs/qa/uat-cases-_TEMPLATE.md`](../../docs/qa/uat-cases-_TEMPLATE.md)，执行编排见 `qa-engineer.md` UAT 节 + `product-lead.md` Step 3.4。

- **产物**：`docs/qa/[feature]-uat-cases-[YYYY-MM-DD].md`（全 feature 单份，pool 多实例共享），E2E 通过后、UAT 执行前由 qa-engineer 生成。
- **每条用例 6 字段，独立执行、独立判定**：① 用例 ID / 标题（关联 PRD AC 编号，如 ← AC-3，保证可追溯）② 前置条件（数据准备 / 环境状态）③ 触发条件（"当…时"，对齐 AC 可测试性硬标准）④ 操作步骤（可复现：命令 / API 调用 / UI 操作）⑤ 预期结果（必须可观察："显示…"/"返回…"/"跳转至…"，禁"功能正常"）⑥ 实际结果 + 证据（执行后回填：真实命令 + 输出 / 截图；**涉及用户可见界面的用例，真渲染截图 + 读图四查结论为必选、纯 API / DB 输出不构成 Pass**——见下文「UAT 界面渲染核查」节；fail 必须展开 命令 + 真实输出 + 偏差；只写"已通过"无效）。
- **AC 覆盖矩阵**：每条 AC ≥ 1 个用例，矩阵缺行即漏。
- **界面渲染核查矩阵**：每个用户可见界面 ≥ 1 行（执行时回填真渲染截图 + 读图四查），缺行即漏；纯后端 / CLI feature 标"不适用"——细则见下文「UAT 界面渲染核查」节。
- **用户审核 gate（MAJOR / MINOR 强制）**：用例文档 frontmatter `status: Approved`（用户审核确认 + 署名）之前**不得开始 UAT 执行**；PATCH 级 hotfix 可由 product-lead 显式豁免（豁免理由写进 UAT 报告）。
- **与 UAT 报告分工**：证据 SSOT 在用例文档（执行时回填）；UAT 报告（skill `agf-writing-qa-report`）引用用例 ID + 汇总 verdict，不重复粘贴证据。
- P0 用例 pass^2（连续 2 次都过）不变。

## UAT 界面渲染核查（真渲染 + 截图 + 读图四查）

> 触发来源：UAT 仅凭 API 断言 / curl 输出即判 Pass——接口 200 但界面层缺陷（导航缺失、布局裁切、控件点不动、观感劣化）直达用户现场。**UIUX 是用户对产品最直接的感受，界面质量本身就是交付标准**。本节是 UAT 界面证据的 SSOT；矩阵骨架在 [`docs/qa/uat-cases-_TEMPLATE.md`](../../docs/qa/uat-cases-_TEMPLATE.md)，执行落点 `qa-engineer.md` UAT 节 + skill `agf-writing-qa-report`。

### 适用范围

feature 含任何用户可见界面（页面 / 弹窗 / 抽屉 / 浮层）即触发，**与是否调后端 API 无关**；纯后端 / 纯 CLI / 纯文档 feature 不适用（矩阵标"不适用"）。渲染载体按轨：Web = chrome-devtools MCP（对共享 UAT 栈 URL）；小程序 = 微信开发者工具模拟器 + 真机；Apple = Xcode 模拟器 / 真机。

### 强制项（每个用户可见界面，缺一不可）

界面清单对照 `docs/design/[feature]/spec.md` + PRD 枚举，落进用例文档「界面渲染核查矩阵」（缺行即漏），每行必须：

1. **真渲染**：真实浏览器 / 模拟器加载该界面，**禁**以 curl 输出、API 响应、单测快照、静态原型截图代替；
2. **截图留证**：`evidence/UAT-[case]-[界面slug].png` 回填矩阵，截图必须来自上一步真渲染；
3. **读图**：截图落盘后必须用 `Read` 读回截图、以原生视觉能力逐图分析——**只截图不读图 = 未核查**；四查中除"控件可点"外，结论必须出自读图；
4. **四查**（逐项回填 `✅` / `❌ + 一句偏差`，对照 design spec）：
   - **导航**：该界面应有的全局导航 / 入口 / 返回路径可见且指向正确；
   - **裁切**：无文本截断、元素溢出、相互遮挡；
   - **控件可点**：该界面关键可交互控件真实点击 / 输入并产生可观测后果（断言标准复用下文强制覆盖项 ③）；
   - **视觉达标**：对照 `docs/design/[feature]/spec.md` + `index.html` 原型核还原度——对齐 / 间距 / 配色 / 字体层级 / 文案完整 / 空态与加载态观感；判准 = **这张截图敢不敢直接交付给用户**。

### 证据效力（不可绕过）

- 涉及用户可见界面的用例，**纯 API / DB 断言不构成 Pass**——真渲染截图 + 读图四查结论是必要证据，curl / `SELECT` 只能作补充。
- 矩阵任一行缺截图（= 该界面未真渲染）**或缺读图四查结论（= 截了没看，"已截图" ≠ "已核查"）** → 该界面视同**未测**：相关用例不得记 Pass，UAT 报告**不得发布**（skill `agf-writing-qa-report`「完成前的验证」守门，product-lead 签字前抽查矩阵）。
- 四查 `❌` 不豁免（**"功能对了、样式小事"不是可交付状态**）：按所属用例 priority 走既有 Verdict 决策树（P0 → Block）。

## 前后端对接强制覆盖项（缺陷 A 契约 + 缺陷 B 交互完整性）

> 触发来源：下游反复反馈「前端与后端 API 接不上 / 页面按钮点击无反应」。两类缺陷——**A 契约漂移**（字段/路径/类型/method 前后端对不上）、**B UI 有控件但无有效行为**（按钮没绑 handler / 没真调 API）。契约机制选型与根因见 [ADR-006](../../docs/adr/006-frontend-backend-contract-sync.md)。本节是这两类缺陷的**测试侧 SSOT**，各 agent DoD 指向本节，不重复细则。

### 适用范围

任何含 `frontend/`（或 `miniapp/` / `apple/`）调用 `backend/` API 的 feature。纯后端 / 纯文档 feature 不触发。Apple 侧的 ①②③ 对应物（生成 client 禁手写 / 控件绑定 handler / XCUITest 控件遍历）细则见 [`apple-native.md`](apple-native.md) + [ADR-008](../../docs/adr/008-apple-backend-contract-sync.md)，原则与本节同源不另立。

### 强制覆盖项（缺一不可）

**① 契约层 — 治 A（左移到编译期 + SIT）**

- 前端 API 调用一律走 **orval 从 OpenAPI 生成**的 client / TanStack Query hooks / 类型 / MSW mock；**禁止**手写 `fetch` + 手写请求/响应类型 + 手写 MSW handler（机制见 ADR-006）。
- 契约不一致在 `tsc` 编译期即暴露（最早一道关，早于任何测试运行）。
- 前端 SIT 的 MSW mock **必须来自 orval 生成产物**（`*.msw.ts`）——mock 与契约同源，不再失真。
- CI drift 红灯：生成产物进库 + 重新生成 `git diff --exit-code`，后端改契约而前端没重生成则 fail。

**② 交互完整性 — 治 B（dev 自验 + Unit）**

- 每个可交互控件（button / form / link / select…）**必须绑定有效 handler**，禁空 handler / `TODO` / 仅 `console.log`。
- 提交 / 数据类 handler **必须真正调用** orval 生成的 client / mutation hook，不留占位。
- 每个数据获取 / 提交路径**必须处理 loading / error / empty** 三态。
- 每个交互控件**至少一个组件测试**断言「触发（点击/提交）→ 以正确参数调了正确 API」——把"按钮没绑事件"从 E2E 左移到 Unit。

**③ E2E 控件遍历 — 治 B（交付末端兜底）**

- qa-engineer E2E **必须遍历页面主要可交互控件**，逐个点击/输入并断言**可观测后果**（DOM 变化 / 网络请求确实发出 / 路由跳转 / 状态翻转）。
- **不接受**"截图里看着有按钮"即 pass（复用下文 Cron-Driven §3 原则「UI 上能看见后果，非仅 BE 200 OK 即 pass」）。执行清单落点：skill `agf-writing-qa-report`。

### 边界（不可误读）

orval 把「契约**结构**不一致」左移到编译期 + SIT，但 **E2E 仍是唯一的真后端行为校验**（业务逻辑 / DB 状态 / 鉴权运行时）——生成的 mock 只保证结构契合契约，**不**保证后端运行时行为正确。**不得**以"已用 orval / 已过 SIT"为由削减 E2E 真后端覆盖。

### 落点（谁在哪层强制）

| 覆盖项 | 强制层 | 落点 |
|---|---|---|
| ① 契约走生成产物 + 禁手写 | 编译期 + code review | `coding.md` 契约纪律 / `frontend-dev.md` DoD / `code-reviewer.md` |
| ① SIT mock 从契约派生 | SIT 自跑 + SIT Audit | skill `agf-running-sit-tests` / `code-reviewer.md` |
| ② 交互完整性 + 交互测试 | dev 自验 + Unit | `frontend-dev.md` DoD |
| ③ E2E 控件遍历断言后果 | E2E | `qa-engineer.md` / skill `agf-writing-qa-report` |

## Cron-Driven Feature E2E（强制覆盖项）

> 触发来源：RolexOps 实战 issue audit（不随模板分发）Systemic Pattern 3 "SIT/UAT Scope Gap" — 某 fan-out feature SIT/E2E/UAT 三层全过，但端到端断 3 处（worker signature TypeError / LLM prompt 不注入 persona / FE 零接入）。根因：SIT/E2E **只覆盖 BE schema + cron 注册**，**没覆盖** cron 实际 tick + 消费链路 + FE 端到端 user flow。

### 适用范围

feature 含以下任一特征即视为 **cron-driven feature**，E2E 必须满足本节扩展覆盖项：

- 使用 taskiq / Redis 周期 task 注册（如 `fan_out_topics_task` / `enrich_watch_specs` / `materials_archive_cron`）
- 使用 `_TASK_TYPE_MAP` 登记的异步消费链路 task（见 `backend/app/workers/middleware/task_status.py`）
- 任何"BE 写入 → cron tick / worker enqueue → 下游消费 → 副作用可观测"链路
- AI / LLM 异步生成 task（i2i / generate-instant / fan-out / enrich）

### 强制覆盖项（缺一不可）

E2E 报告必须为 cron-driven feature 同时覆盖以下 3 段；qa-engineer 写 E2E 报告时（用 skill `agf-writing-qa-report`）按此结构组织"Cron-Driven Feature 端到端"节：

1. **模拟 cron tick**：不等真实 cron 周期（通常 ≥ 1h），用以下任一手段在测试运行时**手动触发一次** task：
   - taskiq client `await broker.kick(task_name, ...)` 编程触发
   - `docker compose exec backend python -m app.cli ...` CLI 触发
   - Redis enqueue API 直接 push（最底层兜底）
   - **禁用**：等真实 cron tick / 仅 verify "task 已注册到 scheduler"——正是 #16 的失败模式
2. **验证消费链路**：tick 触发后必须 assert 以下至少 2 项：
   - **worker 实际 run**：`docker compose logs worker --since 30s` 含本次 task 的开始 + 结束日志（含 task_id）
   - **副作用写入**：目标表 / Redis key / 文件 / 外部 API call 已发生（用 psql / redis-cli / mock recorder verify）
   - **task_status 终态**：`ai_task_status` 表对应 row 状态为 `succeeded` 或预期错误码（非 `pending` / `running` 长期不动）
   - **LLM call 实证**（如 LLM 链路）：用 mock recorder 或 prompt log verify "传入 LLM 的 prompt 实际含期望的 persona / context 注入"（防 #16 "prompt 未注入 persona system prompt" 漏检）
3. **FE 端到端 user flow**：从用户视角 + 真实浏览器（chrome-devtools MCP / Playwright）完成：
   - 用户在 UI 触发 feature 入口（如 NewEventModal 选 persona）
   - 等待消费链路完成（轮询 SSE / refetch）
   - **UI 上能看见生成产物 / 状态翻转**（非仅 BE 200 OK 即声明 pass）
   - 截图 / video 存档至 `docs/qa/<feature>-e2e-YYYY-MM-DD.md` 配套 assets

### 反例 / 历史 incident

> 以下 incident 摘自 RolexOps 项目实战经历（AGF 模板继承的实证教训），具体 issue # / 内部命名 / 路径仅为来源标识；下游 fork 用户读时关注**漏检层**与**现场后果**的方法论。

| 日期 | feature | 漏检层 | 现场后果 |
|---|---|---|---|
| 2026-05-14 | cron-driven fan-out feature | ① cron tick 实际触发 + worker run；② LLM prompt 注入 persona 实证；③ FE 端到端 user flow | close 公告声明 "SHIPPED + SIT 9/9 + UAT Approved"，但 worker signature TypeError 一跑就崩 / FE 入口缺关键字段 → 端到端零可用 |

### 与其他规范的关系

- **部署验证层**：`.claude/standards/deployment.md` §3 定义 "cron-driven feature 容器验证"（部署侧手动 tick + 消费链路 assertion），本节是测试侧 E2E 覆盖项；两侧互为前后置
- **写报告 skill**：`agf-writing-qa-report` skill 写 E2E 报告时引用本节作为 cron-driven feature 覆盖项 checklist
- **SIT Audit**：code-reviewer 做 SIT Audit 时若发现 dev 提交的 SIT 仅覆盖 "task 注册" 而无 tick + 消费链路 assertion，judgment 应为 `❌ Redo SIT`
