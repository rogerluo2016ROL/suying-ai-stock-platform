# PRD — 独立 ChatBI 应用复用改造

- **Date**: 2026-07-03
- **Owner**: product-lead
- **Status**: Draft
- **Estimated effort tier**: Large

## 1. Background

用户提供了 `/Users/rogerluo/程序目录/K线大模型/chatBI` 下的两个包：`ai 前端.zip` 和 `AI 后端.zip`。前端包是 Vue 聊天页面片段，包含首页、聊天、Markdown、历史会话、反馈和流式输出。后端包是 Java Spring Boot / RuoYi 项目，包含 Dify 流式调用、会话历史、智能体配置、热门问题、用户反馈和监控。

现有 K线大模型项目已经具备产业链拆解、公司标签映射、L8 证据链、三高评分、选股模型、选债模型、行情和数据更新能力。用户希望复用原 ChatBI 前后端，但不接 Dify，改造成独立 ChatBI 应用，并在未来挂载到飞书、钉钉、企业微信。

本 PRD 约束第一版范围：复用原前端交互和 Java 后端会话能力，移除 Dify 依赖，后端通过受控工具调用 K线大模型已有服务。第一版产品形态是独立 ChatBI 移动端应用，优先部署为 H5，挂载飞书、钉钉、企业微信，也可独立访问；不改造、不迁移、不侵入现有 PC 端页面、路由、导航和业务组件。PC 端如需入口，只能作为独立应用外链或单独管理入口处理，并且必须经过单独确认。第一版同时纳入提示词管理、报告模板管理和大模型供应商配置，使管理员可以配置 DeepSeek、GLM5.2 等模型，并把模型、提示词、工具、报告模板绑定到不同 ChatBI 智能体及具体执行节点。实现时必须最大化复用原 Vue 前端代码和原 Java/RuoYi 后端代码，只有 Dify 调用链、敏感配置、真实投研工具接入和必要的数据结构扩展允许替换。第一版不做交易下单，不做任意 SQL 查询，不让模型直接访问生产数据库。

## 2. Goal & Non-Goals

**目标**:

- 把原 ChatBI 前后端改造成独立投研 ChatBI 应用，不依赖 Dify。
- 第一版按移动端优先设计和验收，核心部署目标是企业应用 H5。
- 代码层面尽可能复用原 Vue 前端的流式聊天、思考节点、历史会话、反馈、热门问题、Markdown 渲染和停止生成能力。
- 代码层面尽可能复用原 Java/RuoYi 后端的 Controller、Entity、VO、Mapper、会话历史、智能体配置、反馈、权限和审计基础。
- 后端接入 K线大模型已有的产业链、选股、选债、行情、证据链和报告能力。
- 管理员可以维护大模型供应商、模型版本、提示词版本和报告模板版本。
- ChatBI 智能体可以按语义识别、数据查询辅助、证据抽取、答案生成、报告生成等节点分别绑定模型、提示词、工具范围和报告模板。
- 支持后续以 H5 应用方式挂载到飞书、钉钉、企业微信。
- KPI：首版上线后，核心问题集 30 条中至少 24 条能返回结构化答案，且每条答案带数据日期或证据来源；流式首包 P95 ≤ 3 秒；历史会话保存成功率 ≥ 99%；已发布提示词、报告模板和模型配置均可追溯到版本。

**Non-Goals**:

- 不接 Dify，不保留 Dify agent key、workflow path 或 Dify 运行依赖。
- 不把原 Java/RuoYi 项目整体并入 K线大模型主服务。
- 不推倒重写原 ChatBI 前端和后端；确实不能复用的代码必须在复用清单中说明原因。
- 不修改现有 PC 端页面、路由、左侧导航、业务组件和既有接口契约；移动端 ChatBI 必须独立目录、独立构建、独立路由。
- 不允许 ChatBI 直接执行用户生成 SQL。
- 不提供自动买卖、实盘下单、绕过风控的交易指令。
- 不在第一版同时完成飞书、钉钉、企业微信三端生产发布。
- 不做开放式模型广场；第一版只允许管理员维护白名单模型供应商。

## 3. User Stories

| ID | As a | I want to | So that |
|---|---|---|---|
| US-1 | 投研用户 | 在聊天框里问“今天所有模型结果汇总” | 快速看到选股、选债、产业链候选的结构化结果 |
| US-2 | 投研用户 | 问“某只股票为什么入选或没入选” | 看到因子、门槛、证据和数据日期 |
| US-3 | 投研用户 | 问“今天匪爷竞价选债为什么没有票” | 看到每一道过滤门槛的通过数量 |
| US-4 | 投研用户 | 问“中际旭创的产业链证据链” | 看到标签级三高、研发/商用阶段和 L8 证据 |
| US-5 | 管理员 | 管理 ChatBI 智能体和工具范围 | 控制不同场景能调用哪些模型和数据 |
| US-6 | 管理员 | 查看历史问题、答案和反馈 | 追踪回答质量和用户问题热点 |
| US-7 | 企业用户 | 从飞书/钉钉/企微打开 ChatBI | 使用企业身份免登进入同一个 ChatBI 应用 |
| US-8 | 管理员 | 配置 DeepSeek、GLM5.2 等大模型供应商和模型版本 | 在不同智能体中按成本、质量和可用性选择模型 |
| US-9 | 管理员 | 发布、回滚提示词版本 | 控制回答口径并追踪每次变更 |
| US-10 | 管理员 | 管理报告模板版本 | 让公司分析、产业链拆解、模型复盘报告按固定格式输出 |
| US-11 | 分析师 | 选择报告模板导出问答结果 | 快速生成可复用的投研报告 |
| US-12 | 管理员 | 为语义识别、数据查询、答案生成、报告生成分别配置模型 | 用低成本模型处理简单节点，用强模型处理复杂报告，兼顾成本、速度和质量 |
| US-13 | 产品负责人 | 在开发前先查看 ChatBI 原型和预览稿 | 先确认核心体验、数据展示和配置入口，再进入工程实施 |

## 4. Acceptance Criteria

| ID | Priority | AC | Verification method |
|---|---|---|---|
| AC-1 | P0 | 用户在 390px 移动端 WebView 打开 ChatBI 首页后，页面显示热门问题、历史会话入口和底部输入框 | 移动端浏览器手动验收 |
| AC-2 | P0 | 用户提交问题后，前端调用 `POST /api/v1/chatbi/messages/stream`，后端以 SSE 返回 `node_started`、`node_finished`、`message_delta`、`done` 事件 | curl + 浏览器 Network |
| AC-3 | P0 | 后端不调用 Dify 域名或 Dify API，日志中无 Dify 请求记录 | 后端日志 + 配置检查 |
| AC-4 | P0 | 用户问“AI算力候选公司 Top5”后，系统调用 K线大模型候选总榜工具，并返回公司表格、分数、信号、数据日期 | API mock + 真实库烟测 |
| AC-5 | P0 | 用户问“某公司证据链”后，系统返回 `mapping_id` 关联的证据链，不用公司整体数据冒充标签级证据 | API 响应体检查 |
| AC-6 | P0 | 用户问“某模型为什么没票”后，系统返回分层过滤结果或明确提示该模型未提供门槛诊断 | API 响应体检查 |
| AC-7 | P0 | 每轮问答保存到会话历史，刷新页面后能按用户和 session 回看 | DB row count + 前端手动验收 |
| AC-8 | P0 | 用户提交赞/踩和意见后，系统保存反馈，并能在后台按月份查询 | API + DB 检查 |
| AC-9 | P0 | 原包中的数据库账号、密码、Dify key、企业内部 URL 不进入新仓库配置；如已泄露，完成密钥轮换记录 | 仓库扫描 + 运维确认 |
| AC-10 | P1 | 管理员能配置智能体名称、工具范围、提示词版本和状态 | 前端手动验收 + API |
| AC-11 | P1 | ChatBI 以统一平台用户对象接收飞书/钉钉/企微身份，不在业务逻辑中直接依赖某个平台字段 | 单元测试 |
| AC-12 | P1 | H5 页面在企业微信/飞书/钉钉 WebView 中输入、滚动、停止生成、查看表格和证据卡片不遮挡 | 移动端手动验收 |
| AC-13 | P1 | 系统对每次工具调用记录 tool_id、参数摘要、耗时、状态和错误信息 | DB 检查 |
| AC-14 | P2 | 用户能把回答导出为 Markdown 或 Word 报告 | 手动验收 |
| AC-15 | P0 | 管理员新增 DeepSeek 或 GLM5.2 模型配置后，系统能保存供应商、模型名、base_url、状态、限流和脱敏后的 key 标识 | API + DB 检查 |
| AC-16 | P0 | 用户发起问答时，后端按智能体和节点配置选择已发布模型；如果该节点默认模型不可用，按节点 fallback 顺序切换并记录原因 | 单元测试 + 日志检查 |
| AC-17 | P0 | 管理员发布提示词版本后，新会话使用 published 版本，历史会话仍保留原 prompt_version_id | API + DB 检查 |
| AC-18 | P1 | 管理员发布报告模板后，用户导出报告时能选择模板版本，并在导出记录中保存 template_version_id | 手动验收 + DB 检查 |
| AC-19 | P1 | 管理员在预览页输入样例问题后，系统使用指定模型、提示词和工具范围生成预览结果，不写入正式会话历史 | 前端手动验收 + DB 检查 |
| AC-20 | P0 | 管理员把语义识别配置为 DeepSeek、报告生成配置为 GLM5.2 后，同一次问答在日志中分别记录两个节点的 provider_id、model_id、prompt_version_id、token 和耗时 | API + DB + 日志检查 |
| AC-21 | P0 | 后端和前端实施前，必须先完成 ChatBI 前端原型、静态预览、后端设计、接口契约、工具契约、数据模型、架构设计、安全观测设计和总体验收记录 | 文档检查 + 预览稿手动验收 + 设计验收 |
| AC-22 | P0 | 工程实施前必须完成代码复用清单，逐项标明原 Vue 文件和原 Java 后端模块是原样复用、适配复用、替换还是废弃，并说明替换原因 | 文档检查 + code review |
| AC-23 | P0 | 移动端 ChatBI 实施不得修改现有 PC 端页面、路由、左侧导航、业务组件和既有接口契约；如需 PC 入口，只允许新增隔离外链或独立管理入口，并需单独确认 | git diff 检查 + PC 回归冒烟 + code review |

## 5. Design

### UI

第一版复用原 Vue 前端交互，不直接迁移到当前 React 应用，也不嵌入现有 PC 工作台壳。页面按独立移动端应用设计。页面保留：

- 首页欢迎语
- 热门关键词
- 热门问题
- 历史会话
- 底部固定聊天输入框，作为唯一输入入口
- 快速回答 / 深度思考模式
- 流式回答
- 思考过程节点
- Markdown 渲染
- 点赞、踩、意见反馈
- 停止生成

需要新增或改造：

- 表格结果卡片
- 公司证据链卡片
- 模型过滤门槛卡片
- 报告导出入口
- 企业应用 WebView 移动端适配
- 原型预览页：覆盖首页、左侧历史抽屉、底部输入、快速回答、深度思考、问答页、结构化表格、思考过程

回答模式要求：

```text
快速回答：直接命中模板化查询，返回结构化结果，不展开大模型分析链。
深度思考：调用大模型组织证据链、三高、阶段、口径说明和交易信号，展开思考过程。
```

实施顺序要求：

```text
1. 先完成前端原型设计和静态预览设计。
2. 再完成后端设计、接口契约、工具契约、数据模型、架构设计和安全观测设计。
3. 所有设计验收通过后更新 PRD、详细设计和实施计划。
4. 再开始后端、前端、数据表和平台接入实施。
```

### API 契约

新增或统一接口：

| Method | Path | 说明 |
|---|---|---|
| POST | `/api/v1/chatbi/sessions` | 创建会话 |
| GET | `/api/v1/chatbi/sessions` | 查询当前用户会话 |
| GET | `/api/v1/chatbi/sessions/{session_id}` | 查询会话详情 |
| POST | `/api/v1/chatbi/messages/prepare` | 创建问题 UUID，写入问题初始记录 |
| POST | `/api/v1/chatbi/messages/stream` | 流式问答 |
| POST | `/api/v1/chatbi/feedback` | 提交反馈 |
| GET | `/api/v1/chatbi/agents` | 查询可用智能体 |
| GET | `/api/v1/chatbi/agents/{id}/model-bindings` | 查询智能体各节点模型配置 |
| PUT | `/api/v1/chatbi/agents/{id}/model-bindings` | 保存智能体各节点模型配置 |
| POST | `/api/v1/chatbi/reports/export` | 导出报告 |
| GET | `/api/v1/chatbi/model-providers` | 查询模型供应商 |
| POST | `/api/v1/chatbi/model-providers` | 新增模型供应商 |
| POST | `/api/v1/chatbi/model-providers/{id}/test` | 测试模型连通性 |
| GET | `/api/v1/chatbi/prompts` | 查询提示词 |
| POST | `/api/v1/chatbi/prompts/{id}/versions` | 新增提示词版本 |
| POST | `/api/v1/chatbi/prompts/{id}/versions/{version}/publish` | 发布提示词版本 |
| GET | `/api/v1/chatbi/report-templates` | 查询报告模板 |
| POST | `/api/v1/chatbi/report-templates/{id}/versions` | 新增报告模板版本 |
| POST | `/api/v1/chatbi/preview` | 使用指定模型、提示词和模板预览 |

流式事件统一为：

```json
{
  "type": "node_started",
  "node": "问题识别",
  "message": "",
  "times": "",
  "is_show": true
}
```

```json
{
  "type": "message_delta",
  "message": "回答片段"
}
```

```json
{
  "type": "artifact",
  "artifact_type": "table",
  "payload": {}
}
```

```json
{
  "type": "done",
  "times": "4.2s"
}
```

### 数据模型

第一版建议保留 Java 后端自有会话库，同时新增通用 ChatBI 表。字段细节进入详细设计。

| 表 | 说明 |
|---|---|
| `chatbi_sessions` | 会话 |
| `chatbi_messages` | 问题和回答 |
| `chatbi_message_events` | 流式节点、消息、表格、错误 |
| `chatbi_agents` | 智能体配置 |
| `chatbi_agent_model_bindings` | 智能体节点级模型、提示词和 fallback 配置 |
| `chatbi_agent_tools` | 智能体可调用工具 |
| `chatbi_tool_calls` | 工具调用记录 |
| `chatbi_feedback` | 用户反馈 |
| `chatbi_platform_bindings` | 飞书/钉钉/企微用户映射 |
| `chatbi_model_providers` | 大模型供应商配置 |
| `chatbi_model_versions` | 可用模型版本和 fallback 顺序 |
| `chatbi_prompt_versions` | 提示词版本 |
| `chatbi_report_templates` | 报告模板 |
| `chatbi_report_template_versions` | 报告模板版本 |
| `chatbi_render_logs` | 报告导出记录 |
| `chatbi_audit_logs` | 审计日志 |

### 工具层

第一版工具清单：

| tool_id | 能力 |
|---|---|
| `supply_chain_candidate_ranking` | 查询产业链候选总榜 |
| `company_evidence_chain` | 查询公司标签级证据链 |
| `stock_model_run` | 运行选股模型 |
| `bond_model_run` | 运行选债模型 |
| `model_no_pick_diagnosis` | 解释无票原因 |
| `model_resonance` | 多模型共振统计 |
| `market_snapshot` | 查询行情快照 |
| `report_export` | 生成报告 |

## 6. Technical Constraints

- 现有 `AI 后端.zip` 中的 `.git`、`target`、IDE 文件、内部地址、账号、密码、key 必须从新工程剔除。
- 移动端 ChatBI 必须作为独立应用建设，不允许改动现有 PC 端页面、路由、导航、业务组件和既有接口契约。
- 如需在 PC 端露出入口，只允许做独立外链或独立管理入口，不能改变原 PC 页面布局、菜单结构和数据逻辑；该入口必须单独评审确认。
- 前端实现优先复用 `ai/index.vue`、`module1.vue`、`Markdown.vue`、`componentsHistory.vue`、`feedback.vue`、`feedView.vue`；新增 artifact 渲染和配置页时应以扩展组件方式接入。
- 后端实现优先复用 `GacDifyAIController`、`AiHistoryController`、`AiAgentTypeDifyController`、`AiHistoryEntity`、`AiHistoryMapper.xml`、`GacDifyData`、`AiFeedbackRequestVO` 等会话、历史、智能体和反馈代码；Dify 调用逻辑替换为 ChatBI Orchestrator。
- Java 后端不直接读写 K线大模型核心 PostgreSQL 表，优先通过内部 FastAPI 工具接口访问。
- ChatBI 后端只允许调用白名单工具，不允许执行用户自由 SQL。
- Dify 相关字段、接口、表名可以保留兼容期，但业务含义要改成 ChatBI agent。
- 生产环境密钥必须走环境变量或密钥管理，不写入 YAML。
- 模型供应商 key 只允许加密存储或引用密钥管理系统，前端和普通 API 只能看到脱敏标识。
- DeepSeek、GLM5.2 等模型必须通过统一 LLM Gateway 调用，不能散落在业务代码里。
- 语义识别、数据查询辅助、证据抽取、答案生成、报告生成必须支持节点级模型配置；没有配置时才允许回退到智能体默认模型。
- 提示词和报告模板必须有 draft、published、archived 状态；生产问答只能使用 published 版本。
- SSE 首包 P95 ≤ 3 秒；普通工具查询 P95 ≤ 2 秒；长任务必须返回节点进度。
- 投资相关回答必须显示数据日期、模型版本或证据来源。
- 接入飞书/钉钉/企微时，平台身份必须先映射为统一内部用户。

## 7. Cost Estimate

- 预估 LLM token / 月：第一版按 2000 次问答/月、每次 8k token 估算，约 1600 万 token/月。若产业链和模型查询主要用规则路由 + 模板回答，token 可降到 500 万以内。DeepSeek 和 GLM5.2 按供应商单价分别统计，后台需要按 provider/model/node 记录 token 和费用，方便看清语义识别、数据查询辅助、报告生成各自成本。
- 预估 Agent Team 开发 token：Large。
- 触发成本档位：Large。
- 人工开发量粗估：
  - 后端 ChatBI Orchestrator：5–8 人日
  - 前端复用和移动端适配：4–6 人日
  - K线工具接入：4–8 人日
  - 模型供应商配置、提示词和报告模板管理：6–10 人日
  - 企业平台接入一期：3–5 人日
  - UAT 和安全治理：3–5 人日

## 8. Out of Scope / Future Work

- 第二阶段再做完整提示词 A/B 测试和自动评测。
- 第二阶段再做跨平台消息推送，例如飞书机器人主动推送日报。
- 第二阶段再做报告模板市场和模板共享。
- 第二阶段再做多租户计费和会员权益。
- 第二阶段再把 Vue 前端重构为 React 独立应用。
- 第三阶段再考虑多 Agent 协作、自动复盘和定时任务。

## 9. Open Questions

| ID | 问题 | Owner | Due | 备注 |
|---|---|---|---|---|
| Q-1 | 第一版优先挂载哪个平台：飞书、钉钉还是企业微信？ | product-lead | 2026-07-04 | 建议只选一个做试点 |
| Q-2 | 原 Java 后端是否作为独立服务长期保留，还是只作为过渡网关？ | tech-lead | 2026-07-04 | 影响部署和维护成本 |
| Q-3 | 第一版默认供应商使用 DeepSeek 还是 GLM5.2？ | product-lead | 2026-07-04 | 两者都支持配置，需确定默认和 fallback |
| Q-4 | 用户权限按个人、租户、组合、交易账户哪一层隔离？ | product-lead / backend-dev | 2026-07-05 | 影响数据安全模型 |
| Q-5 | 原包中暴露的数据库凭据是否已失效并完成轮换？ | ops / tech-lead | 2026-07-04 | P0 安全前置条件 |
| Q-6 | ChatBI 会话库使用 MySQL 还是迁移到 PostgreSQL？ | tech-lead | 2026-07-05 | 影响复用范围 |
| Q-7 | 模型供应商 key 使用本地加密表还是外部密钥管理系统？ | tech-lead / ops | 2026-07-05 | 影响安全实现 |

## 10. Sign-offs

- [ ] product-lead: 初稿
- [ ] tech-lead: 技术可行性 review
- [ ] frontend-dev: 原 Vue 前端复用和 H5 适配可行性确认
- [ ] backend-dev: Java 后端改造和 K线工具接入可行性确认
- [ ] ai-agent-dev: ChatBI Orchestrator、模型供应商、提示词和工具编排可行性确认
- [ ] qa-engineer: AC 可测性确认
- [ ] security/ops: 密钥清理、平台接入和部署安全确认

## Changelog

- 2026-07-03: 初稿，基于 `chatBI/ai 前端.zip` 与 `chatBI/AI 后端.zip` 可行性阅读结论创建。
- 2026-07-03: 增补模型供应商配置、提示词管理、报告模板管理为第一版范围。
- 2026-07-03: 增补节点级模型配置，支持语义识别、数据查询辅助、证据抽取、答案生成、报告生成分别选择模型。
- 2026-07-03: 调整实施顺序，要求先完成原型设计和预览设计，评审并更新设计文档后再进入工程实施。
- 2026-07-03: 调整为全设计先行，前端原型、后端设计、接口契约、数据模型、架构和安全观测设计全部验收后再实施。
- 2026-07-03: 增补代码复用约束，要求前端和后端实现前先完成代码复用清单，避免推倒重写。
- 2026-07-03: 增补移动端独立应用硬约束，明确不修改现有 PC 端页面、路由、导航和业务组件。
- 2026-07-03: 前端壳确认，底部输入框作为唯一输入入口，后端设计区分快速回答和深度思考两条链路。
- 2026-07-03: 完成源码包审计、代码复用清单和设计验收记录；允许进入工程实施，但实施前必须清洗原始源码包并移除旧敏感配置。
