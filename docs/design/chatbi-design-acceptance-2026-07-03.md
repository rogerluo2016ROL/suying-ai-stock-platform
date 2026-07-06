# 独立 ChatBI 设计验收记录

**日期**: 2026-07-03  
**验收范围**: 独立移动端 ChatBI H5，复用原 ChatBI 前后端，不接 Dify，接入 K线大模型投研工具。  
**验收结论**: 设计阶段通过。  
**允许进入工程实施：是**  

> 说明：允许进入工程实施不代表本轮已经开始写后端或前端业务代码。工程实施前仍需按计划先清洗原始源码包，且不得改动现有 PC 端业务页面。

## 1. 设计文档覆盖情况

| 文档 | 状态 | 覆盖内容 |
| --- | --- | --- |
| `docs/prd/chatbi-standalone-reuse-2026-07-03.md` | 通过 | 业务范围、用户故事、AC、边界和复用约束 |
| `docs/prd/chatbi-standalone-reuse-detailed-design-2026-07-03.md` | 通过 | 业务架构、数据架构、应用架构、技术架构和复用策略 |
| `docs/prd/chatbi-standalone-reuse-implementation-plan-2026-07-03.md` | 通过 | 阶段、任务、准入和验收顺序 |
| `docs/design/chatbi-prototype-spec-2026-07-03.md` | 通过 | 独立移动端原型结构 |
| `docs/design/chatbi-preview-spec-2026-07-03.md` | 通过 | 可打开静态预览说明 |
| `docs/design/chatbi-prototype-review-2026-07-03.md` | 通过 | 原型验收和用户确认记录 |
| `docs/design/chatbi-backend-design-2026-07-03.md` | 通过 | 后端服务、Orchestrator、模型网关和配置管理设计 |
| `docs/design/chatbi-api-contract-2026-07-03.md` | 通过 | 前后端 API 和 SSE 事件协议 |
| `docs/design/chatbi-tool-contract-2026-07-03.md` | 通过 | 投研工具白名单、入参出参和权限边界 |
| `docs/design/chatbi-data-model-design-2026-07-03.md` | 通过 | 会话、消息、节点过程、artifact、提示词、模板和模型配置数据模型 |
| `docs/design/chatbi-architecture-design-2026-07-03.md` | 通过 | 应用架构、部署边界、企业平台挂载方式 |
| `docs/design/chatbi-security-observability-design-2026-07-03.md` | 通过 | 安全、审计、观测、降级和验收指标 |
| `docs/reviews/chatbi-source-audit-2026-07-03.md` | 通过 | 原始源码包清洗要求和敏感配置审计 |
| `docs/reviews/chatbi-code-reuse-inventory-2026-07-03.md` | 通过 | 前端、后端逐项复用方式和替换边界 |

## 2. PRD AC 自检

| AC | 前端页面或交互 | 后端 API 或工具契约 | 数据表或日志字段 | 验收方法 |
| --- | --- | --- | --- | --- |
| AC-1 独立移动端应用 | 首页、聊天页、历史抽屉、底部输入栏 | `/api/v1/chatbi/*` | `chatbi_sessions`、访问日志 | 移动端预览和接口冒烟 |
| AC-2 不侵入 PC 端 | 不接入 PC 左侧导航和工作台壳 | 不复用 PC 路由 | PC 端无新增菜单 | `git diff` 路径检查 + PC 回归冒烟 |
| AC-3 快速回答 | 底部“快速回答”按钮 | `answerMode=quick`，模板化查询工具 | `chatbi_messages.answer_mode` | 快速回答不展示思考链，只返回结果 |
| AC-4 深度思考 | 底部“深度思考”按钮、节点过程 | `answerMode=deep`，Orchestrator 编排 | `chatbi_node_runs` | SSE 展示节点状态和耗时 |
| AC-5 热门关键词和近期话题 | 首页关键词和热门话题卡片 | `/hot-keywords`、`/hot-topics` | `chatbi_hot_topics` 或配置表 | 静态预览 + API 冒烟 |
| AC-6 历史会话 | 侧边抽屉搜索和会话列表 | `/sessions` | `chatbi_sessions` | 新建、查询、删除会话测试 |
| AC-7 反馈 | 赞/踩、原因、备注 | `/messages/{id}/feedback` | `chatbi_feedback` | 反馈写入和权限测试 |
| AC-8 结构化投研结果 | 表格、证据卡、公司卡、报告 artifact | artifact 事件和查询 API | `chatbi_artifacts` | 移动端渲染和导出检查 |
| AC-9 工具白名单 | 前端不暴露任意 SQL | Tool Gateway 契约 | `chatbi_tool_invocations` | 工具调用权限和审计测试 |
| AC-10 证据链 | 回答中的证据引用、来源和日期 | evidence search tool | `evidence_refs`、工具日志 | 检查回答是否可追溯 |
| AC-11 模型供应商配置 | 管理配置入口后续实现 | Model Gateway | `llm_providers`、`llm_models` | DeepSeek/GLM 等连通性测试 |
| AC-12 节点级模型配置 | 节点过程展示模型名 | Orchestrator 节点模型绑定 | `chatbi_node_model_bindings` | 不同节点可使用不同模型 |
| AC-13 提示词管理 | 后续管理页或配置入口 | Prompt Manager | `prompt_templates`、版本表 | 版本启停和回滚测试 |
| AC-14 报告模板管理 | 报告 artifact 和导出入口 | Report Template Manager | `report_templates` | 模板生成报告测试 |
| AC-15 企业平台挂载 | H5 安全区和轻量头部 | SSO/OAuth 适配层 | `external_identities` | 飞书、钉钉、企微登录预留测试 |
| AC-16 安全隔离 | 不显示密钥，不暴露 SQL | Auth、RBAC、Tool Gateway | 审计日志、脱敏日志 | 权限和越权测试 |
| AC-17 可观测性 | 节点耗时和失败提示 | traceId、SSE 状态 | `chatbi_node_runs`、日志 | 链路追踪和失败回放 |
| AC-18 降级策略 | 失败提示、重试、停止生成 | 超时、取消、降级配置 | 错误日志 | 模型/工具失败演练 |
| AC-19 移动端 UED | 390px 预览、无底部多页签 | 无 | 无 | Playwright 截图验收 |
| AC-20 数据口径 | 回答展示数据日期、来源、口径 | 工具返回 `asOfDate/source` | artifact metadata | 检查是否出现“无日期结论” |
| AC-21 先设计后实施 | 原型和预览已完成 | 后端、接口、工具、数据、安全设计已完成 | 文档记录 | 本验收记录 |
| AC-22 代码复用清单 | Vue 文件逐项复用 | Java 模块逐项复用 | 复用清单 | `chatbi-code-reuse-inventory` |
| AC-23 PC 不受影响 | 不改 PC 页面 | 不接 PC API 路由 | 无 | PC 路径 diff 检查 |

## 3. 关键验收结论

1. 产品形态已确认：独立移动端 ChatBI H5，不是现有 PC 工作台页面。
2. 原型壳已确认：保留欢迎语、热门关键词、近期热门话题和底部输入栏；移除底部多页签；快速回答与深度思考作为回答模式。
3. 快速回答定义清晰：直接命中模板化查询，只返回结果，不展开分析。
4. 深度思考定义清晰：通过 Orchestrator 调用模型和工具，展示节点过程、证据链和结构化结果。
5. 原始源码包已审计：前端可复用，后端必须清洗后复用，旧密钥和旧环境配置不得进入新工程。
6. 复用清单已完成：前端 Vue 文件和后端 Java/RuoYi 模块都已标注复用、扩展、替换或废弃策略。
7. Dify 替换边界已明确：不再接 Dify，统一由 ChatBI Orchestrator、Model Gateway 和 Tool Gateway 承接。

## 4. 工程实施准入条件

进入 Phase 3 前必须执行：

- 清洗复制原始后端包，确保新目录不含 `.git`、`target`、`.idea`、`*.class`。
- 旧 `application*.yml` 只可作为字段参考，不能复制密钥值。
- 新增配置必须使用环境变量或密钥管理。
- 标准 API 和 SSE 协议先落地，再接前端。
- 每个工具调用必须有白名单、参数校验、traceId 和审计日志。
- PC 端路径检查必须保持无变更。

## 5. 当前不做的事情

- 不把独立 ChatBI 嵌入现有 PC 工作台。
- 不让模型直接执行任意 SQL。
- 不接交易下单。
- 不把 Dify 作为运行依赖。
- 不把原始源码包里的敏感配置落库或提交。

## 6. 最终结论

设计验收通过。文档、原型、后端设计、接口契约、工具契约、数据模型、安全观测设计、源码审计和复用清单已覆盖 PRD 的实施准入要求。

允许进入工程实施：是。

