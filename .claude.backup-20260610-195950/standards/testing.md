# Testing Standards

## Testing Standards

四级测试分工，门槛递进（前一级通过才进入下一级）：

| 级别 | 测试对象 | 依赖处理 | 编写者 | 工具 | 触发时机 |
|---|---|---|---|---|---|
| **Unit** | 单个函数/模块/组件 | 全部 Mock | 开发者自己（frontend-dev / backend-dev / ai-agent-dev / ml-engineer / miniapp-dev） | Jest / Vitest / pytest | **test-first**（red → green → refactor，见 ac-lifecycle.md DoD） |
| **SIT** | API + 数据库 + 外部服务协同 | DB 真实，外部 API 可 Mock | 开发者（frontend-dev / backend-dev / ai-agent-dev / ml-engineer / miniapp-dev） | Supertest / pytest + 真实 DB | 功能完成后随代码提交 |
| **E2E** | 完整用户操作流程 | 全部真实 | qa-engineer | Playwright / chrome-devtools-mcp | code-review 通过后（含 SIT Audit） |
| **UAT** | PRD 验收标准（业务视角） | 全部真实 | qa-engineer 执行 + product-lead 判定 | E2E 脚本 + 人工确认 | E2E 通过后 |

- **开发者职责**：Unit + SIT 都随代码提交（Unit 走 Mock，集成层走 API+DB+external 单边集成），不转包给测试角色
- **UAT 判定权**：唯一由 product-lead 对照 PRD AC 签字，qa-engineer 只负责执行和出报告
- **测试报告**：SIT 证据写入 `progress/<role>.md` 的 `**SIT 证据**` 段（不再单独产 `docs/qa/[feature]-sit-*.md`）；E2E / UAT 完成后分别输出至 `docs/qa/[feature]-[e2e|uat]-[YYYY-MM-DD].md`
- **阶段门槛**：code-review (含 SIT Audit) 通过 → E2E → UAT；任一阶段失败回 product-lead 重新分派
- **失败回退**：任一阶段失败，由 product-lead 重新分派执行层修复，qa-engineer 和 code-reviewer 不直接修改实现
- **TDD 是核心纪律**（不是建议）：新功能 / bugfix 任务必须按 red → green → refactor 顺序，PR commit history 能看出 test commit 早于 impl commit；详见 [`ac-lifecycle.md` DoD](./ac-lifecycle.md) + skill `superpowers:test-driven-development`；纯重构 / 文档 / 配置任务可跳过

## Cron-Driven Feature E2E（强制覆盖项）

> 触发来源：`docs/reviews/issue-audit-2026-05-16.md` Systemic Pattern 3 "SIT/UAT Scope Gap" — **#16 fan-out** SIT/E2E/UAT 三层全过，但实际端到端断 3 处（worker signature TypeError / LLM prompt 不注入 persona / FE 零接入）。根因：SIT/E2E **只覆盖 BE schema + cron 注册**，**没覆盖** cron 实际 tick + 消费链路 + FE 端到端 user flow。

### 适用范围

凡 feature 含以下任一特征即视为 **cron-driven feature**，E2E 必须满足本节扩展覆盖项：

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
   - **禁用**：等真实 cron tick / 仅 verify "task 已注册到 scheduler"——这正是 #16 的失败模式
2. **验证消费链路**：tick 触发后必须 assert 以下至少 2 项：
   - **worker 实际 run**：`docker compose logs worker --since 30s` 含本次 task 的开始 + 结束日志（含 task_id）
   - **副作用写入**：目标表 / Redis key / 文件 / 外部 API call 已发生（用 psql / redis-cli / mock recorder verify）
   - **task_status 终态**：`ai_task_status` 表对应 row 状态为 `succeeded` 或预期错误码（非 `pending` / `running` 长期不动）
   - **LLM call 实证**（如 LLM 链路）：用 mock recorder 或 prompt log verify "传入 LLM 的 prompt 实际含期望的 persona / context 注入"（防 #16 "prompt 未注入 persona system prompt" 漏检）
3. **FE 端到端 user flow**：从用户视角 + 真实浏览器（chrome-devtools MCP / Playwright）完成：
   - 用户在 UI 触发 feature 入口（如 NewEventModal 选 persona）
   - 等待消费链路完成（轮询 SSE / refetch）
   - **UI 上能看见生成产物 / 状态翻转**（不是仅 BE 200 OK 即声明 pass）
   - 截图 / video 存档至 `docs/qa/<feature>-e2e-YYYY-MM-DD.md` 配套 assets

### 反例 / 历史 incident

> 以下 incident 摘自 RolexOps 项目实战经历（AGF 模板继承的实证教训），具体 issue # / 内部命名 / 路径仅为来源标识；下游 fork 用户读时关注**漏检层**与**现场后果**的方法论。

| 日期 | feature | 漏检层 | 现场后果 |
|---|---|---|---|
| 2026-05-14 | cron-driven fan-out feature | ① cron tick 实际触发 + worker run；② LLM prompt 注入 persona 实证；③ FE 端到端 user flow | close 公告声明 "SHIPPED + SIT 9/9 + UAT Approved"，但 worker signature TypeError 一跑就崩 / FE 入口缺关键字段 → 端到端零可用 |

### 与其他规范的关系

- **部署验证层**：`.claude/standards/deployment.md` §3 定义 "cron-driven feature 容器验证"（部署侧手动 tick + 消费链路 assertion），本节是测试侧 E2E 覆盖项；两侧互为前后置
- **写报告 skill**：`agf-writing-qa-report` skill 在写 E2E 报告时引用本节作为 cron-driven feature 的覆盖项 checklist
- **SIT Audit**：code-reviewer 做 SIT Audit 时若发现 dev 提交的 SIT 仅覆盖 "task 注册" 而无 tick + 消费链路 assertion，judgment 应为 `❌ Redo SIT`
