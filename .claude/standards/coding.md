# Coding and AI Development Standards

## Coding Standards

- 实现前必须读 ADR-000（技术栈 SSOT，`CLAUDE.md ## Tech Stack` 为其摘要）确认技术选型；未经 tech-lead 确认，不引入 ADR-000 未列出的包或框架
- 前端 TypeScript，后端 Python（技术栈详见 ADR-000）
- 使用 ESLint + Prettier 统一代码风格
- Git commit message 使用 Conventional Commits 格式
- 变量/函数命名使用 camelCase，类型/接口使用 PascalCase
- 不添加不必要的注释，只注释 WHY 而非 WHAT
- 优先编辑现有文件而非创建新文件

### Verify before assert（基线引用纪律）

引用项目已有基线（架构 / 鉴权 / DB schema / API 契约 / hook / CLI 参数 / etc）做新决策或写新文档时，**必须先 grep 实际代码 verify**，即使来源是：

- 上一份 ADR / spec / review 报告
- 团队 lead（含 tech-lead / product-lead）的口头描述或 SendMessage
- CLAUDE.md Tech Stack 摘要（描述可能滞后于实现，技术选型以 ADR-000 为准）
- 任务派工模板里的固定句式

**违规典型**：基于二手描述写新文档，不实证验证。一个真实发生过的链路：review 报告对鉴权契约的描述凭印象写错（未 grep 实际 client/router 代码）→ 后续 ADR 引用 review 继承误述 → spec 起草人引用 ADR 接着错 → 错误一路传到实现阶段才被发现，多份文档都得回头 patch。**链条上每个引用方都没 verify，任何一处 grep 就能斩断**。

**最小成本 verify 模板**（10 秒事）：
```bash
grep -nE "<keyword>" <file_or_dir>          # 关键字定位
git log --oneline --grep="<feature>" | head # commit 历史
```

**适用范围**：所有 agent，**tech-lead 自身也不豁免**——上面那次违规链条的起点恰恰是 tech-lead。

### 前后端契约纪律（含 frontend 的 feature 必读）

前后端契约的单一来源是后端 **OpenAPI**（FastAPI 自动生成）；前端调用层全部由 **orval** 从 OpenAPI 生成，杜绝"口头契约 + 手写漂移"。决策与流程见 [ADR-006](../../docs/adr/006-frontend-backend-contract-sync.md)，执行硬约束：

- **前端禁手写**：API 的请求/响应 TypeScript 类型、HTTP client、TanStack Query hooks、MSW mock handler **一律用 orval 生成产物**（约定目录 `frontend/src/api/generated/`），业务代码只 import 生成物；禁手写 `fetch` + 禁手写类型 + 禁手写 mock。契约不一致由 `tsc` 在编译期暴露。
- **后端保证 schema 规范**：FastAPI 路由必须声明 `response_model`、给 operation 合理的 `operationId` / tags（orval 据此生成 hook 名与类型；schema 不规范 → 生成物难用）。这是 orval 生成质量的隐性前置，backend-dev 不可只盯自己的 API 而漏掉。
- **orval 版本下限**：pin `orval ≥ 8.0.3`（CVE-2026-24132 mock 值未转义已在此版修复；取当时最新 8.x，建议 `^8.16.0`）。
- **契约变更闭环**：后端改契约 → 重新导出 OpenAPI + 重跑 orval → 生成产物随 PR 提交；CI `git diff --exit-code` 挡未重生成的漂移。
- 完整测试侧覆盖（SIT mock 来源 / E2E 真后端边界 / 交互完整性）见 [`testing.md` 前后端对接强制覆盖项](testing.md)。

### Apple 客户端契约纪律（含 apple/ 调后端 API 的 feature 必读）

同一份 OpenAPI 契约在 Apple 侧的对应纪律（决策见 [ADR-008](../../docs/adr/008-apple-backend-contract-sync.md)，是 ADR-006 的 Apple 对应版）：

- **Apple 客户端禁手写**：URLSession 请求、请求/响应 Codable DTO、JSON mock **一律走 swift-openapi-generator 生成**（SPM build plugin 构建期生成，产物不进库）；业务代码只用生成的 `Client` / `APIProtocol`。契约不一致由 `swift build` 在编译期暴露。
- **SIT mock**：实现生成的 `APIProtocol` 协议做类型安全 fake server，禁手写 JSON fixture。
- **契约变更闭环**：后端重新导出 `openapi.json` 进库 → apple 侧下次构建自动重生成；CI 对 `openapi.json` 跑「重导出 + `git diff --exit-code`」。
- 执行细则见 [`apple-native.md`](apple-native.md)；后端 schema 规范责任与 Web 轨同一条（上节），不重复。

## AI Development Guidelines

- 接入 LLM SDK 时优先启用 prompt caching（若厂商 SDK 支持）
- Prompt 使用 XML 标签结构化（`<context>`, `<rules>`, `<output_format>`）
- Agent 工具定义要有清晰无歧义的 description 和参数 schema
- 实现 guardrail 防止 Agent 行为失控
- 记录 LLM 输入/输出用于调试和评估

## LLM 行为铁律（全团队适用）

> 本节是给执行层（含 lead）共用的日常工作纪律——不是项目级规则，而是"如何写代码 / 如何动 diff"的行为约束。结构借鉴 Karpathy 的 LLM coding guidelines（2026），按本团队已有规范裁剪后只保留增量条款；与 brainstorming / verify-before-assert / superpowers 套件已覆盖的不重复。

### 1. 多解读不默选

需求出现 ≥2 种合理解读时，**列出选项让 lead 拍板**，别自己挑一个继续。`product-lead` 的 `superpowers:brainstorming` 是需求阶段的版本；执行层拆 task 后看到歧义同样适用——SendMessage 回 product-lead 澄清，不在 PR 里赌。

### 2. 看到更简单方案就说

实现中发现"任务能用更简单的办法做完"——必须先告诉 lead，别默默换路。判断"是否更简单"的口径：更少代码 / 更少依赖 / 更少跨文件改动 / 与既有模式更一致。push-back 不止用在 `receiving-code-review`，日常实现也适用。

### 3. Every changed line traces to the request

完成报告 / PR 发出前对自己的 `git diff` 自检一次：**每一行变更都能直接对应到任务消息里的某条 AC 或显式要求**。对应不上就是越界，删掉或单开任务。

### 4. 不"改良"邻近代码

碰到的代码"看着不顺眼"——格式不一致、命名能更好、注释能补全、import 能整理——**只要不在本任务范围内，一律不改**。理由：

- diff 噪声拖慢 review、放大冲突
- 跨实例并行时的临界区风险（见 [`workflow.md` Parallel Dispatch](workflow.md)）
- 小改良容易夹带未自验的副作用

例外：你**自己改动**导致的 orphan（unused import / 未引用的本次新增变量）必须清。

### 5. 看到无关 dead code 只提不删

发现明显死代码 / 死注释 / 历史残留——在完成报告里**点名提一句**（路径 + 推断原因），由 product-lead 判断是单开 cleanup task 还是保留。**别顺手删**——可能是 feature flag 关掉的功能、运维脚本依赖的入口、或下次 release 还要恢复的代码。

### 6. 不给不可能场景加 error handling

系统边界外的输入（用户表单、外部 API 响应、文件读取）必须验证；**内部代码互相调用、由你自己控制的契约**——别写"以防万一"的 try/except 或 `if x is None`。这类防御代码：

- 隐藏真正的 bug（exception 被吞掉，问题被推迟到更难定位的地方）
- 增加测试负担（要为不会发生的分支写测试）
- 误导 reviewer（看到防御代码会以为这条路径真的会触发）

判定口径：**这个 None / 异常分支真的能走到吗？画出触发它的调用链——画不出来就删掉**。

---

**自检清单**：送审前对照上方铁律 1-6 逐条核对一遍（歧义→澄清 / 更简单→先说 / diff→AC / 不改良邻近 / dead code 只提不删 / 不可能分支不防御）。
