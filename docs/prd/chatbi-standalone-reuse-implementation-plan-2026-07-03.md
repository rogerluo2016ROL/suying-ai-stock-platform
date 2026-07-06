# 独立 ChatBI 应用复用改造实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 复用原 ChatBI Vue 前端和 Java/Spring Boot 后端，移除 Dify 依赖，接入 K线大模型投研工具，做成独立移动端 ChatBI H5 应用，并预留飞书、钉钉、企业微信挂载能力。

**Architecture:** 第一版先完成移动端前端原型设计和预览设计，再完成后端设计、数据设计、接口契约和整体架构设计；所有设计文档通过验收后，才进入工程实施。工程侧保留原 ChatBI 的前端交互、会话历史和反馈能力；后端把 Dify 流式转发替换为 ChatBI Orchestrator；投研数据通过 K线大模型 FastAPI 工具接口访问，不直接查核心 PostgreSQL 表。

**Tech Stack:** Vue + Java Spring Boot/RuoYi + MyBatis/MySQL 或 PostgreSQL 会话库 + FastAPI 工具服务 + SSE + H5 企业应用 WebView。

## Global Constraints

- 不接 Dify，不保留 Dify agent key、workflow path 或 Dify 运行依赖。
- 不允许 ChatBI 直接执行用户生成 SQL。
- 不提供自动买卖、实盘下单、绕过风控的交易指令。
- Java 后端不直接读写 K线大模型核心 PostgreSQL 表，优先通过内部 FastAPI 工具接口访问。
- 原包中的数据库账号、密码、Dify key、企业内部 URL 不进入新仓库配置。
- DeepSeek、GLM5.2 等模型必须通过统一 LLM Gateway 调用，不能散落在业务代码里。
- 模型供应商 key 只允许加密存储或引用密钥管理系统，前端和普通 API 只能看到脱敏标识。
- 语义识别、查询规划、数据查询辅助、证据抽取、答案生成、报告生成必须支持节点级模型配置；没有配置时才允许回退到智能体默认模型。
- 生产问答只能使用 published 提示词版本和 published 报告模板版本。
- SSE 首包 P95 ≤ 3 秒；普通工具查询 P95 ≤ 2 秒；长任务必须返回节点进度。
- 投资相关回答必须显示数据日期、模型版本或证据来源。
- 后端、前端和数据库实施前，必须先完成移动端前端原型、静态预览、后端设计、架构设计、接口契约、数据模型和总体验收记录，并同步更新 PRD、详细设计和实施计划。
- Phase 0 只允许做源码审计、安全清理和工程边界确认，不写业务实现；Phase 1 和 Phase 2 完成前，不进入任何后端、前端、数据库或平台接入实施。
- 工程实现必须最大化复用 `chatBI/ai 前端.zip` 和 `chatBI/AI 后端.zip` 的源码；无法复用的文件或模块必须写入代码复用清单并说明原因。
- 移动端 ChatBI 必须独立目录、独立构建、独立路由；不得修改现有 PC 端页面、路由、左侧导航、业务组件和既有接口契约。
- 如后续需要 PC 端入口，只允许新增隔离外链或独立管理入口，并且必须先单独确认；不能改变原 PC 页面布局、菜单结构和数据逻辑。

---

## Phase 0: 安全清理和工程边界

### Task 1: 解压原包并生成干净工程副本

**Files:**

- Read: `chatBI/ai 前端.zip`
- Read: `chatBI/AI 后端.zip`
- Create: `chatbi-workspace/frontend-vue/`
- Create: `chatbi-workspace/backend-java/`
- Create: `docs/reviews/chatbi-source-audit-2026-07-03.md`
- Create: `docs/reviews/chatbi-code-reuse-inventory-2026-07-03.md`

**目标:** 把可复用源码从压缩包中提取出来，剔除 `.git`、`target`、IDE 文件和敏感配置。

- [x] **Step 1: 解压到隔离目录**

```bash
mkdir -p chatbi-workspace/raw
unzip -q "chatBI/ai 前端.zip" -d chatbi-workspace/raw/frontend
unzip -q "chatBI/AI 后端.zip" -d chatbi-workspace/raw/backend
```

预期：`chatbi-workspace/raw/frontend/ai` 和 `chatbi-workspace/raw/backend/cockpit-screen` 存在。

- [x] **Step 2: 复制可用源码**

```bash
mkdir -p chatbi-workspace/frontend-vue chatbi-workspace/backend-java
rsync -a --exclude='.git' --exclude='.idea' --exclude='target' chatbi-workspace/raw/frontend/ai/ chatbi-workspace/frontend-vue/
rsync -a --exclude='.git' --exclude='.idea' --exclude='target' chatbi-workspace/raw/backend/cockpit-screen/ chatbi-workspace/backend-java/
```

预期：干净目录中没有 `.git`、`.idea`、`target`。

- [x] **Step 3: 扫描敏感信息**

```bash
rg -n "password|passwd|secret|agentKey|agent_key|Bearer|jdbc:mysql|10\\.|app-" chatbi-workspace/backend-java chatbi-workspace/frontend-vue
```

预期：输出所有疑似密钥和内部地址，写入审计报告。

- [x] **Step 4: 形成审计报告**

报告必须包含：

```text
源码来源
保留文件清单
剔除文件清单
发现的敏感配置类型
需要轮换的密钥类别
是否允许进入后续开发
```

- [x] **Step 5: 形成代码复用清单**

复用清单必须覆盖前端：

```text
ai/index.vue
ai/module/module1.vue
ai/module/Markdown.vue
ai/module/componentsHistory.vue
ai/module/feedback.vue
ai/module/feedView.vue
```

复用清单必须覆盖后端：

```text
GacDifyAIController
AiHistoryController
AiAgentTypeDifyController
AiHistoryEntity
AiHistoryMapper.xml
GacDifyData
GacRAGFlowAIRequestVO
AiFeedbackRequestVO
BaseController
AjaxResult
RuoYi 权限和审计相关基础类
```

每一项必须标注：

```text
原样复用 / 适配复用 / 扩展复用 / 替换 / 废弃
复用原因
需要修改的接口或字段
替换原因，如有
风险
```

- [x] **Step 6: 验证**

```bash
test ! -d chatbi-workspace/backend-java/.git
test ! -d chatbi-workspace/backend-java/target
test ! -d chatbi-workspace/backend-java/.idea
rg -n "原样复用|适配复用|扩展复用|替换|废弃" docs/reviews/chatbi-code-reuse-inventory-2026-07-03.md
```

预期：目录清理命令返回 0；代码复用清单至少覆盖上述前端文件和后端模块。

- [x] **Step 7: 确认没有触碰现有 PC 端**

```bash
git diff --name-only -- frontend src docs/design docs/prd | rg "frontend/src|src/pages|router|menu|layout" || true
```

预期：本阶段不出现现有 PC 端页面、路由、菜单、布局和业务组件改动；如出现，必须退回并说明原因。

### Task 2: 密钥和配置治理

**Files:**

- Modify: `chatbi-workspace/backend-java/cockpit-screen-admin/src/main/resources/application.yml`
- Modify: `chatbi-workspace/backend-java/cockpit-screen-admin/src/main/resources/application-*.yml`
- Create: `chatbi-workspace/backend-java/.env.example`
- Create: `docs/security/chatbi-secret-rotation-2026-07-03.md`

**目标:** 删除包内明文账号、密码、内部 URL 和 Dify key，把运行配置改为环境变量。

- [x] **Step 1: 把数据库配置改为环境变量**

配置示例：

```yaml
spring:
  datasource:
    druid:
      master:
        url: ${CHATBI_DB_URL}
        username: ${CHATBI_DB_USERNAME}
        password: ${CHATBI_DB_PASSWORD}
```

- [x] **Step 2: 删除 Dify 配置**

删除或废弃：

```text
ai.agents.list
ai.agents.sessions
ai.agents.completions
Dify agent key
Dify path
```

替换为：

```yaml
chatbi:
  toolGatewayBaseUrl: ${CHATBI_TOOL_GATEWAY_BASE_URL:http://127.0.0.1:8000/api/v1}
  streamTimeoutSeconds: ${CHATBI_STREAM_TIMEOUT_SECONDS:60}
```

- [x] **Step 3: 创建 `.env.example`**

必须包含：

```text
CHATBI_DB_URL=
CHATBI_DB_USERNAME=
CHATBI_DB_PASSWORD=
CHATBI_TOOL_GATEWAY_BASE_URL=
CHATBI_PLATFORM_SECRET=
```

- [x] **Step 4: 记录密钥轮换**

文档记录：

```text
发现位置
密钥类型
是否仍有效
轮换责任人
轮换日期
验证方式
```

- [ ] **Step 5: 验证**

当前配置文件层面的旧密钥、旧内网 URL、旧 Dify/RAGFlow key 已清理；验证命令仍命中 `agentKey` 字段名和旧服务代码中的 `getAgentKey()` 调用。它们不是明文生产密钥，但代表旧 Dify/RAGFlow 调用链仍未替换，需在 Phase 3 `ChatBI Orchestrator` 改造时消除。

```bash
rg -n "jdbc:mysql://|password: '.+'|agentKey|Bearer app-|10\\.30\\." chatbi-workspace/backend-java
```

预期：无生产密钥命中；如果命中，只允许出现在 `.env.example` 的空值说明中。

---

## Phase 1: 原型设计和预览设计

### Design Gate A: 原型范围和页面清单

**Files:**

- Create: `docs/design/chatbi-prototype-spec-2026-07-03.md`
- Reference: `docs/prd/chatbi-standalone-reuse-2026-07-03.md`
- Reference: `docs/prd/chatbi-standalone-reuse-detailed-design-2026-07-03.md`

**目标:** 先定义 ChatBI 要展示什么、怎么操作、哪些配置入口必须存在，避免直接进入代码实现。

- [x] **Step 1: 明确页面清单**

原型必须包含：

```text
首页
问答页
历史会话
结构化结果展示
公司证据链卡片
模型过滤门槛卡片
节点级模型配置
模型供应商配置
提示词管理
报告模板管理
报告生成预览
企业 WebView 适配
```

- [x] **Step 2: 明确核心交互**

每个页面必须写清：

```text
入口
主要控件
用户点击后的变化
调用的后端接口或 mock 数据
空状态
加载状态
错误状态
移动端表现
```

- [x] **Step 3: 明确结构化结果组件**

必须定义：

```text
表格结果
公司卡片
证据链卡片
L8 证据明细
三高标签
研发/商用阶段
节点过程
报告章节
```

- [x] **Step 4: 验证**

检查 `docs/design/chatbi-prototype-spec-2026-07-03.md`，确认以上页面、交互和状态没有缺项。

### Design Gate B: 静态预览设计

**Files:**

- Create: `docs/design/chatbi-preview/index.html`
- Create: `docs/design/chatbi-preview/mock-data.json`
- Create: `docs/design/chatbi-preview-spec-2026-07-03.md`

**目标:** 先输出可打开的移动端静态预览文件给产品评审，再补齐预览说明。预览必须优先复用原 ChatBI 前端交互和原 Java 后端会话/智能体/反馈设计；`docs/design/new front/` 只作为视觉参考，不把 ChatBI 做成现有 PC 工作台页面。

- [x] **Step 1: 制作静态预览文件**

`index.html` 必须能直接打开，并展示：

```text
移动首页预览
问答流式过程预览
结构化表格预览
证据链卡片预览
节点级模型配置预览
提示词管理预览
报告模板管理预览
报告导出预览
```

复用要求：

```text
移动端交互复用 ai 前端.zip 中 index.vue、module1.vue、componentsHistory.vue、Markdown.vue、feedback.vue 的信息结构。
后端概念复用 AI 后端.zip 中 GacDifyAIController、AiHistoryController、AiAgentTypeDifyController、AiHistoryEntity、GacDifyData 的会话、历史、智能体、流式事件和反馈设计。
视觉风格参考 docs/design/new front/ 的卡片密度、状态标签和表格表达，但不复用 PC 左侧导航和工作台壳。
```

- [x] **Step 2: 准备 mock 场景**

mock 数据至少包含：

```text
AI算力候选公司 Top5
中际旭创证据链
某模型无票原因
节点级模型配置示例
DeepSeek 和 GLM5.2 模型配置示例
提示词版本示例
报告模板版本示例
报告生成示例
```

- [x] **Step 3: 编写预览说明**

```text
docs/design/chatbi-preview-spec-2026-07-03.md
```

说明文档必须写清：

```text
复用了哪些现有前端设计
复用了哪些原 ChatBI 前端交互
复用了哪些原 Java 后端概念
哪些地方只是预览 mock
哪些地方后续才接真实接口
```

- [x] **Step 4: 移动端预览**

至少检查 390px 宽度：

```text
底部输入框不遮挡
表格可横向滚动
证据卡片可折叠
模型配置表单不溢出
报告预览章节可阅读
```

- [x] **Step 5: 验证**

用浏览器打开：

```text
docs/design/chatbi-preview/index.html
```

预期：不用启动后端，也能完整查看核心页面和 mock 结果。

### Design Gate C: 前端原型评审和文档同步

**Files:**

- Create: `docs/design/chatbi-prototype-review-2026-07-03.md`
- Modify: `docs/prd/chatbi-standalone-reuse-2026-07-03.md`
- Modify: `docs/prd/chatbi-standalone-reuse-detailed-design-2026-07-03.md`
- Modify: `docs/prd/chatbi-standalone-reuse-implementation-plan-2026-07-03.md`

**目标:** 前端原型和静态预览评审通过后，把变化同步回 PRD、详细设计和实施计划。该 Gate 只允许进入后端设计和架构设计，不允许直接进入工程实施。

- [x] **Step 1: 记录评审结论**

评审记录必须包含：

```text
评审日期
参与角色
通过项
需修改项
是否影响 PRD
是否影响详细设计
是否影响实施计划
是否允许进入后端设计和架构设计
```

- [x] **Step 2: 更新文档**

如果评审中调整了页面、交互、数据结构、接口或实施顺序，必须同步更新：

```text
PRD
详细设计
实施计划
```

- [x] **Step 3: 设置下一阶段门槛**

只有评审记录写明：

```text
允许进入后端设计和架构设计：是
```

才能开始 Design Gate D。

---

## Phase 2: 后端设计、架构设计和设计验收

### Design Gate D: 后端设计和接口契约

**Files:**

- Create: `docs/design/chatbi-backend-design-2026-07-03.md`
- Create: `docs/design/chatbi-api-contract-2026-07-03.md`
- Create: `docs/design/chatbi-tool-contract-2026-07-03.md`
- Reference: `docs/reviews/chatbi-code-reuse-inventory-2026-07-03.md`
- Reference: `docs/design/chatbi-prototype-spec-2026-07-03.md`
- Reference: `docs/design/chatbi-preview-spec-2026-07-03.md`

**目标:** 在写后端代码前，先定义 ChatBI 后端边界、接口契约、工具调用契约、错误码、权限和日志字段。

- [x] **Step 1: 设计后端模块边界**

后端设计必须覆盖：

```text
复用原 Java/RuoYi 工程结构
ChatBIController
SessionService
ChatBIOrchestrator
IntentRouter
ToolGatewayClient
LLMGatewayService
AgentConfigService
PromptTemplateService
ReportTemplateService
AuditLogService
```

后端设计必须说明哪些能力来自原代码复用，哪些能力由新增服务补充。

- [x] **Step 2: 设计 API 契约**

接口契约必须覆盖：

```text
会话创建
历史会话
消息 prepare
消息 stream
反馈
智能体配置
节点级模型配置
模型供应商配置
提示词版本
报告模板版本
报告导出
预览接口
```

每个接口必须写清：

```text
path
method
request
response
error_code
permission
audit_fields
```

- [x] **Step 3: 设计工具调用契约**

工具契约必须覆盖：

```text
supply_chain_candidate_ranking
company_evidence_chain
stock_model_run
bond_model_run
model_no_pick_diagnosis
model_resonance
market_snapshot
report_export
```

每个工具必须写清输入参数、输出结构、数据日期字段、证据来源字段和空状态。

- [x] **Step 4: 验证**

检查：

```text
docs/design/chatbi-backend-design-2026-07-03.md
docs/design/chatbi-api-contract-2026-07-03.md
docs/design/chatbi-tool-contract-2026-07-03.md
```

预期：前端原型中的每个页面和控件，都能找到对应 API 或 mock/tool 契约。

### Design Gate E: 数据模型和系统架构设计

**Files:**

- Create: `docs/design/chatbi-data-model-design-2026-07-03.md`
- Create: `docs/design/chatbi-architecture-design-2026-07-03.md`
- Create: `docs/design/chatbi-security-observability-design-2026-07-03.md`
- Reference: `docs/design/chatbi-backend-design-2026-07-03.md`
- Reference: `docs/design/chatbi-api-contract-2026-07-03.md`

**目标:** 在建表、接模型和接真实数据前，先明确数据模型、系统边界、安全边界、可观测性和部署架构。

- [x] **Step 1: 设计数据模型**

数据模型必须覆盖：

```text
chatbi_sessions
chatbi_messages
chatbi_message_events
chatbi_agents
chatbi_agent_model_bindings
chatbi_agent_tools
chatbi_tool_calls
chatbi_feedback
chatbi_model_providers
chatbi_model_versions
chatbi_prompt_versions
chatbi_report_templates
chatbi_report_template_versions
chatbi_render_logs
chatbi_platform_bindings
chatbi_audit_logs
```

每张表必须写清主键、关键字段、唯一约束、索引、数据保留策略和是否包含敏感信息。

- [x] **Step 2: 设计系统架构**

架构设计必须覆盖：

```text
Vue ChatBI 前端
Java ChatBI 后端
K线大模型 FastAPI 工具服务
LLM Gateway
PostgreSQL / MySQL 会话库
企业应用 WebView
日志和监控
```

必须明确：

```text
请求链路
SSE 链路
工具调用链路
模型调用链路
报告生成链路
平台免登链路
```

- [x] **Step 3: 设计安全和可观测性**

必须覆盖：

```text
模型 API Key 加密或密钥引用
接口鉴权
工具白名单
节点级模型调用日志
prompt_version_id 追踪
template_version_id 追踪
token 和成本统计
错误码和告警
审计日志
```

- [x] **Step 4: 验证**

预期：数据表、架构图、链路说明、安全策略和日志字段能支撑 PRD 的 AC-1 到 AC-21。

### Design Gate F: 全部设计验收和实施准入

**Files:**

- Create: `docs/design/chatbi-design-acceptance-2026-07-03.md`
- Modify: `docs/prd/chatbi-standalone-reuse-2026-07-03.md`
- Modify: `docs/prd/chatbi-standalone-reuse-detailed-design-2026-07-03.md`
- Modify: `docs/prd/chatbi-standalone-reuse-implementation-plan-2026-07-03.md`

**目标:** 前端原型、后端设计、架构设计、接口契约和数据模型全部验收通过后，才允许进入工程实施。

- [x] **Step 1: 汇总设计文档**

验收必须覆盖：

```text
chatbi-prototype-spec
chatbi-preview-spec
chatbi-backend-design
chatbi-api-contract
chatbi-tool-contract
chatbi-data-model-design
chatbi-architecture-design
chatbi-security-observability-design
```

- [x] **Step 2: 对照 PRD AC 自检**

每条 AC 必须能映射到：

```text
前端页面或交互
后端 API 或工具契约
数据表或日志字段
验收方法
```

- [x] **Step 3: 更新文档**

如果验收发现 PRD、详细设计或实施计划与设计文档不一致，先更新文档，再进入实施。

- [x] **Step 4: 设置实施准入**

只有验收文档写明：

```text
允许进入工程实施：是
```

才能开始 Phase 3。

---

## Phase 3: 后端 ChatBI Orchestrator

> 2026-07-03 MVP 实施状态：已完成最小可用闭环，范围为标准 ChatBI API、兼容旧流式入口、规则意图识别、产业链候选工具调用、SSE 事件和移动端 H5 UAT 页。提示词管理、报告模板管理、节点级模型真实配置、企业 SSO、会话持久化表和完整权限体系仍按 Phase 4-6 后续推进，未在本轮冒充完成。

### Task 3: 建立标准 ChatBI API 和兼容路由

**Files:**

- Create: `chatbi-workspace/backend-java/cockpit-screen-admin/src/main/java/com/ds/cockpit/screen/web/controller/chatbi/ChatBIController.java`
- Modify: `GacDifyAIController.java`
- Test: `chatbi-workspace/backend-java/cockpit-screen-admin/src/test/java/.../ChatBIControllerTest.java`

**目标:** 新增标准 `/api/v1/chatbi` 路由，同时保留 `/gac/dify/ai` 兼容路径。

- [x] **Step 1: 新增接口**

接口清单：

```text
POST /api/v1/chatbi/sessions
POST /api/v1/chatbi/messages/prepare
POST /api/v1/chatbi/messages/stream
POST /api/v1/chatbi/feedback
GET  /api/v1/chatbi/agents
GET  /api/v1/chatbi/sessions
GET  /api/v1/chatbi/sessions/{sessionId}
```

- [x] **Step 2: 兼容旧路由**

旧路由映射：

```text
/gac/dify/ai/created/session -> /api/v1/chatbi/sessions
/gac/dify/ai/created/data/uuid -> /api/v1/chatbi/messages/prepare
/gac/dify/ai/chat-messages -> /api/v1/chatbi/messages/stream
/gac/dify/ai/feedback -> /api/v1/chatbi/feedback
```

- [x] **Step 3: 验证**

```bash
curl -X POST http://localhost:8080/api/v1/chatbi/sessions
curl -X POST http://localhost:8080/gac/dify/ai/created/session
```

预期：两个接口返回同一结构的 session id。

### Task 4: 实现流式事件协议

**Files:**

- Create: `ChatBIStreamEvent.java`
- Create: `ChatBIStreamService.java`
- Create: `StreamEventMapper.java`
- Test: `ChatBIStreamEventTest.java`

**目标:** 后端能输出标准事件，并兼容前端现有 `type/node/times/message/isShow` 字段。

- [x] **Step 1: 定义事件类型**

事件类型：

```text
node_started
node_finished
message_delta
artifact
warning
error
done
```

- [x] **Step 2: 定义兼容输出**

标准事件必须映射为：

```json
{
  "type": "node_started",
  "node": "问题识别",
  "times": "",
  "message": "",
  "isShow": "1"
}
```

- [x] **Step 3: 测试事件顺序**

输入一个问题后，测试流包含：

```text
node_started: 问题识别
node_finished: 问题识别
node_started: 工具选择
node_finished: 工具选择
message_delta
done
```

### Task 5: 实现意图识别和工具路由

**Files:**

- Create: `IntentRouter.java`
- Create: `IntentResult.java`
- Create: `ChatBIToolRegistry.java`
- Test: `IntentRouterTest.java`

**目标:** 第一版用规则识别常见投研问题。

- [x] **Step 1: 支持意图**

```text
supply_chain_ranking
company_evidence
stock_model_run
bond_model_run
no_pick_diagnosis
model_resonance
report_export
data_quality
unknown
```

- [x] **Step 2: 编写规则**

规则示例：

```text
包含“产业链”“候选”“Top” -> supply_chain_ranking
包含“证据链”“L8”“研发”“商用” -> company_evidence
包含“选债”“可转债”“匪爷” -> bond_model_run
包含“为什么没有”“没票”“未入选” -> no_pick_diagnosis
包含“共振”“多个模型”“同时命中” -> model_resonance
```

- [ ] **Step 3: 验证**

MVP 已验证：

```text
AI算力候选公司Top5 -> supply_chain_ranking
具身智能产业链卡脖子公司清单 -> supply_chain_ranking
```

完整问题集仍在 Phase 7 按 30 条问题继续验收。

测试问题：

```text
AI算力候选公司Top5
中际旭创证据链
今天匪爷竞价选债为什么没有票
今天所有模型共振情况
```

预期：全部路由到正确意图。

### Task 6: 实现工具网关客户端

**Files:**

- Create: `ToolGatewayClient.java`
- Create: `ToolCallRequest.java`
- Create: `ToolCallResponse.java`
- Test: `ToolGatewayClientTest.java`

**目标:** Java 后端通过 HTTP 调用 K线大模型 FastAPI 工具，不直接查核心表。

- [ ] **Step 1: 支持工具接口**

MVP 已接通：

```text
GET /api/v1/screener/supply-chain/candidate-ranking
GET /api/v1/screener/modes
GET /api/v1/screener/market/index-quotes
```

`company/{code}`、`business-tag/{mapping_id}/evidence-chain` 和 `POST /screener/run` 待后续接入。

第一批接口：

```text
GET /api/v1/screener/supply-chain/candidate-ranking
GET /api/v1/screener/supply-chain/company/{code}
GET /api/v1/screener/supply-chain/business-tag/{mapping_id}/evidence-chain
POST /api/v1/screener/run
GET /api/v1/screener/modes
GET /api/v1/screener/market/index-quotes
```

- [x] **Step 2: 增加超时和错误结构**

默认：

```text
connectTimeout = 3s
readTimeout = 10s
maxRows = 200
```

- [x] **Step 3: 验证真实接口**

```bash
curl "http://127.0.0.1:8000/api/v1/screener/supply-chain/candidate-ranking?top_n=5"
```

预期：返回 `source_status=ready` 和候选列表。

### Task 7: 实现 ChatBI Orchestrator

**Files:**

- Create: `ChatBIOrchestratorService.java`
- Modify: `GacAIDifySteamServiceImpl.java`
- Test: `ChatBIOrchestratorServiceTest.java`

**目标:** 替换 Dify 调用链，串联意图识别、工具调用、答案组装和流式事件。

- [x] **Step 1: 删除 Dify 运行依赖**

禁用以下行为：

```text
读取 ai_agent_type_dify.agent_key 作为 Dify key
调用 Dify chat-messages
调用 Dify workflow
```

- [x] **Step 2: 输出节点事件**

每次问答至少输出：

```text
问题识别
工具选择
数据查询
答案生成
生成完成
```

- [ ] **Step 3: 答案生成**

MVP 已完成模板化答案生成和产业链候选结果格式化；真实大模型节点级配置、token 记录、prompt 版本记录仍按后续 Model Gateway / Prompt Manager 实施。

第一版按智能体和节点配置决定是否调用大模型。规则能回答的问题可用模板回答；需要语义识别、查询规划、数据查询辅助、证据抽取、自然语言总结、报告正文时，按当前节点读取模型配置：

```text
结论
数据表
证据/来源
限制说明
下一步建议
```

每次生成必须记录：

```text
llm_node_type
provider_id
model_id
prompt_version_id
input_tokens
output_tokens
fallback_reason
```

节点类型必须至少支持：

```text
intent_recognition
query_planning
data_query_assist
evidence_extraction
answer_generation
report_generation
```

- [x] **Step 4: 验证**

```bash
curl -N -X POST http://localhost:8080/api/v1/chatbi/messages/stream \
  -H "Content-Type: application/json" \
  -d '{"question":"AI算力候选公司Top5","userId":"test","userName":"测试","sessionUuid":"s1","id":1}'
```

预期：流中不出现 Dify 请求错误，能返回候选表格文本或 artifact。

---

## Phase 4: 数据、会话、反馈和智能体配置

> 2026-07-04 进展：Task 8 的 ChatBI 自有核心表已落地，Java 后端启动时会自动 `CREATE TABLE IF NOT EXISTS`，同时保留 `db/migration/chatbi/V001__chatbi_core_tables.sql` 作为正式迁移脚本。会话、消息、节点事件、工具调用和反馈已通过真实问答写入 PostgreSQL。

> 2026-07-04 进展：Task 9 的配置底座已落地，新增 `V002__chatbi_agent_prompt_template.sql`，并在 Java 后端启动时自动建表和写入默认配置。当前完成模型供应商、模型版本、智能体、节点级模型绑定、提示词版本、报告模板版本的持久化和基础 API。LLM Gateway MVP 已新增 `V003__chatbi_llm_invocations.sql`，完成 DeepSeek、GLM5.2、OpenAI-compatible 的统一调用入口、fallback、调用日志和深度思考模式接入；本机未配置真实 API Key，因此已验证“不可用时明确降级”，未伪造真实模型连通成功。

### Task 8: 设计并迁移 ChatBI 会话表

**Files:**

- Create: `db/migration/chatbi/V001__chatbi_core_tables.sql`
- Modify: `AiHistoryMapper.xml`
- Test: DB migration smoke

**目标:** 建立 ChatBI 自有会话、消息、事件、反馈、工具调用表。

- [x] **Step 1: 创建表**

表清单：

```text
chatbi_sessions
chatbi_messages
chatbi_message_events
chatbi_tool_calls
chatbi_feedback
chatbi_audit_logs
```

- [ ] **Step 2: 兼容旧历史查询**

MVP 已完成标准接口 `/api/v1/chatbi/sessions` 从数据库读取历史会话；旧接口 `/ai/histroy/record/list`、`/ai/histroy/gethistory` 尚未回归，保留为后续兼容任务。

旧接口：

```text
/ai/histroy/record/list
/ai/histroy/gethistory
```

仍返回前端可用结构。

- [x] **Step 3: 验证**

2026-07-04 验证结果：

```text
chatbi_sessions: 1
chatbi_messages: 1
chatbi_message_events: 6
chatbi_tool_calls: 1
chatbi_feedback: 1
最近会话标题：AI算力候选公司Top5
最近消息状态：completed
最近消息意图：supply_chain_ranking
```

提交一轮问答后检查：

```text
chatbi_sessions 有会话
chatbi_messages 有问题和答案
chatbi_message_events 有节点事件
chatbi_tool_calls 有工具调用记录
```

### Task 9: 模型供应商、提示词和报告模板配置

**Files:**

- Create: `db/migration/chatbi/V002__chatbi_agent_prompt_template.sql`
- Create: `ChatBIAgentController.java`
- Create: `LLMProviderController.java`
- Create: `LLMProviderService.java`
- Create: `LLMGatewayService.java`
- Create: `PromptTemplateController.java`
- Create: `PromptTemplateService.java`
- Create: `ReportTemplateController.java`
- Create: `ReportTemplateService.java`
- Test: `LLMProviderServiceTest.java`
- Test: `PromptTemplateServiceTest.java`
- Test: `ReportTemplateServiceTest.java`

**目标:** 把原 Dify agent 配置改为 ChatBI 智能体、模型供应商、节点级模型、提示词和报告模板配置。第一版支持 DeepSeek、GLM5.2 和 OpenAI-compatible 供应商。

- [x] **Step 1: 新增配置表**

```text
chatbi_model_providers
chatbi_model_versions
chatbi_agents
chatbi_agent_model_bindings
chatbi_agent_tools
chatbi_prompt_versions
chatbi_report_templates
chatbi_report_template_versions
chatbi_render_logs
```

- [x] **Step 2: 定义模型供应商字段**

`chatbi_model_providers` 必须支持：

```text
provider_id
provider_name
provider_type
base_url
api_key_ref
status
timeout_seconds
rate_limit_qpm
created_by
created_at
updated_at
```

`chatbi_model_versions` 必须支持：

```text
model_id
provider_id
model_name
context_window
max_output_tokens
cost_input_per_1k
cost_output_per_1k
fallback_order
status
```

- [x] **Step 2.1: 定义节点级模型配置字段**

`chatbi_agent_model_bindings` 必须支持：

```text
binding_id
agent_id
node_type
primary_model_id
fallback_model_ids
prompt_version_id
temperature
max_output_tokens
timeout_seconds
enabled
created_by
created_at
updated_at
```

`node_type` 必须限制在：

```text
intent_recognition
query_planning
data_query_assist
evidence_extraction
answer_generation
report_generation
```

- [x] **Step 3: 内置供应商类型**

```text
deepseek
glm
openai_compatible
```

内置模型示例：

```text
DeepSeek: deepseek-chat
GLM: glm-5.2
OpenAI-compatible: custom-model
```

- [x] **Step 4: 实现模型连通性测试**

MVP 当前实现为“配置可用性测试”：按 `api_key_ref` 检查本机环境变量并返回脱敏状态。未配置时返回 `unavailable`，不会伪造真实模型连通成功。

接口：

```text
POST /api/v1/chatbi/model-providers/{id}/test
```

返回：

```json
{
  "status": "ok",
  "provider_id": "deepseek",
  "model_id": "deepseek-chat",
  "latency_ms": 812,
  "masked_key": "sk-***1234"
}
```

失败时只返回脱敏错误，不返回明文 key。

- [x] **Step 5: 实现 LLM Gateway**

MVP 已实现统一 LLM Gateway，支持按 `agent_id + node_type` 读取节点级模型配置，依次尝试主模型和 fallback 模型，并记录 token、fallback、节点类型和调用状态。

新增表：

```text
chatbi_llm_invocations
```

新增接口：

```text
POST /api/v1/chatbi/llm/generate
```

已接入节点：

```text
answer_generation
```

当前深度思考模式流程：

```text
规则识别 -> 工具查询 -> 模板化结果整理 -> answer_generation 调用 LLM Gateway -> 成功则追加大模型分析，失败则明确展示降级状态
```

本机验证状态：

```text
DEEPSEEK_API_KEY 未配置 -> deepseek-chat 返回 unavailable
GLM_API_KEY 未配置 -> glm-5.2 返回 unavailable
OPENAI_COMPATIBLE_API_KEY 未配置 -> custom-model 返回 unavailable
chatbi_llm_invocations 已记录每一次尝试
```

注意：当前只验证了网关、配置读取、fallback、日志和降级链路。真实外部模型连通需要配置对应环境变量后再做联网 UAT。

统一输入：

```json
{
  "model_id": "deepseek-chat",
  "messages": [
    {"role": "system", "content": "你是投研助手"},
    {"role": "user", "content": "总结AI算力候选"}
  ],
  "max_tokens": 1200,
  "temperature": 0.2
}
```

统一输出：

```json
{
  "status": "ok",
  "provider_id": "deepseek",
  "model_id": "deepseek-chat",
  "content": "回答内容",
  "usage": {
    "input_tokens": 1000,
    "output_tokens": 300
  }
}
```

- [x] **Step 6: 新增提示词版本管理**

`chatbi_prompt_versions` 必须支持：

```text
prompt_id
version
status
system_prompt
task_prompt
output_schema
risk_rules
allowed_tools
change_note
created_by
published_by
published_at
```

状态：

```text
draft
reviewing
published
archived
```

发布接口：

```text
POST /api/v1/chatbi/prompts/{id}/versions/{version}/publish
```

- [x] **Step 7: 新增报告模板版本管理**

`chatbi_report_template_versions` 必须支持：

```text
template_id
version
status
format
sections
required_data
optional_data
style_config
change_note
created_by
published_by
published_at
```

发布接口：

```text
POST /api/v1/chatbi/report-templates/{id}/versions/{version}/publish
```

- [x] **Step 8: 内置第一批智能体**

2026-07-04 验证结果：

```text
chatbi_model_providers: 3
chatbi_model_versions: 3
chatbi_agents: 6
chatbi_agent_model_bindings: 36
chatbi_prompt_versions: 1
chatbi_report_templates: 1
chatbi_report_template_versions: 1
默认供应商：deepseek、glm、openai_compatible
默认模型：deepseek-chat、glm-5.2、custom-model
默认智能体：总入口助手、产业链助手、选股助手、选债助手、报告助手、数据质量助手
```

```text
总入口助手
产业链助手
选股助手
选债助手
报告助手
数据质量助手
```

每个智能体必须绑定：

```text
default_model_id
fallback_model_ids
default_prompt_version_id
default_report_template_version_id
tool_scope
```

同时每个智能体可以覆盖节点级配置：

```text
intent_recognition -> primary_model_id=deepseek-chat
query_planning -> primary_model_id=deepseek-chat
data_query_assist -> primary_model_id=deepseek-chat
evidence_extraction -> primary_model_id=glm-5.2
answer_generation -> primary_model_id=deepseek-chat
report_generation -> primary_model_id=glm-5.2
```

- [x] **Step 9: 实现节点级模型配置接口**

接口：

```text
GET /api/v1/chatbi/agents/{id}/model-bindings
PUT /api/v1/chatbi/agents/{id}/model-bindings
```

请求示例：

```json
{
  "bindings": [
    {
      "node_type": "intent_recognition",
      "primary_model_id": "deepseek-chat",
      "fallback_model_ids": ["glm-5.2"],
      "prompt_version_id": "chatbi_intent_router:v1",
      "temperature": 0.1,
      "max_output_tokens": 600,
      "timeout_seconds": 5,
      "enabled": true
    },
    {
      "node_type": "report_generation",
      "primary_model_id": "glm-5.2",
      "fallback_model_ids": ["deepseek-chat"],
      "prompt_version_id": "report_writer:v1",
      "temperature": 0.2,
      "max_output_tokens": 4000,
      "timeout_seconds": 30,
      "enabled": true
    }
  ]
}
```

要求：

```text
保存时校验模型、提示词均为 enabled/published。
同一个 agent_id + node_type 只能有一条启用配置。
接口响应不返回明文 key。
```

2026-07-04 验证结果：

```text
GET /api/v1/chatbi/agents/supply_chain/model-bindings -> code=200，返回 6 个节点配置
PUT /api/v1/chatbi/agents/supply_chain/model-bindings -> code=200，成功保存 answer_generation 配置
fallback_model_ids 请求数组 -> 入库为 glm-5.2,custom-model
bad-model 负向保存 -> 返回业务错误，数据库未覆盖原配置
响应字段检查 -> 不包含 api_key 字段
```

- [x] **Step 10: 实现预览接口**

接口：

```text
POST /api/v1/chatbi/preview
```

请求：

```json
{
  "agent_id": "supply_chain",
  "node_type": "answer_generation",
  "model_id": "deepseek-chat",
  "prompt_version_id": "supply_chain_answer:v1",
  "question": "AI算力候选Top5"
}
```

要求：

```text
预览结果不写入正式会话历史。
预览必须记录 preview log，包括 node_type、provider_id、model_id、prompt_version_id、token 和耗时。
预览可调用 mock 工具或真实只读工具。
```

2026-07-04 验证结果：

```text
新增表：chatbi_preview_logs
POST /api/v1/chatbi/preview -> code=200
agent_id=supply_chain
node_type=answer_generation
model_id=deepseek-chat
provider_id=deepseek
prompt_version_id=default_prompt_v1
status=unavailable
persisted_to_session=false
正式会话数：5 -> 5
preview log：0 -> 1
```

说明：本机未配置 `DEEPSEEK_API_KEY`，因此预览接口只验证到 LLM Gateway 降级和日志链路；真实模型内容预览需要配置 API Key 后再做外部连通 UAT。

- [x] **Step 11: 验证**

```bash
curl http://localhost:8080/api/v1/chatbi/agents
curl http://localhost:8080/api/v1/chatbi/agents/supply_chain/model-bindings
curl http://localhost:8080/api/v1/chatbi/model-providers
curl http://localhost:8080/api/v1/chatbi/prompts
curl http://localhost:8080/api/v1/chatbi/report-templates
```

预期：返回启用状态的智能体、模型供应商、提示词和报告模板列表；任何响应都不包含明文 key。

再执行一次问答：

```bash
curl -N -X POST http://localhost:8080/api/v1/chatbi/messages/stream \
  -H "Content-Type: application/json" \
  -d '{"question":"生成中际旭创产业链拆解报告","userId":"test","userName":"测试","sessionUuid":"s1","id":2}'
```

预期：日志至少出现 `intent_recognition` 和 `report_generation` 两类节点调用记录；如果两类节点配置了不同模型，日志中的 `model_id` 必须不同。

2026-07-04 验证结果：

```text
/api/v1/chatbi/agents -> code=200
/api/v1/chatbi/agents/supply_chain/model-bindings -> code=200
/api/v1/chatbi/model-providers -> code=200
/api/v1/chatbi/prompts -> code=200
/api/v1/chatbi/report-templates -> code=200
/api/v1/chatbi/config/summary -> code=200
model-providers 响应未发现 sk-、Bearer 或明文 API Key
AI算力候选公司Top5 快速回答回归 -> 命中源杰科技，未出现原始 JSON 噪声
生成中际旭创产业链拆解报告 深度思考回归 -> 进入报告生成节点
chatbi_llm_invocations 同一 message_id 下出现：
intent_recognition|deepseek-chat|unavailable
report_generation|glm-5.2|unavailable
```

说明：节点级模型选择已生效；本机未配置真实模型 Key，因此记录为 unavailable，没有伪造模型成功输出。

---

## Phase 5: 前端复用和增强

### Task 10: 前端 API 适配

**Files:**

- Modify: `chatbi-workspace/frontend-vue/api/home/home.js`
- Modify: `chatbi-workspace/frontend-vue/module/module1.vue`

**目标:** 前端从旧 Dify 路径平滑切换到标准 ChatBI 路径。

- [x] **Step 1: 增加 API 配置**

支持：

```text
VUE_APP_CHATBI_API_BASE=/api/v1/chatbi
VUE_APP_CHATBI_COMPAT_BASE=/gac/dify/ai
```

- [x] **Step 2: 切换流式接口**

优先调用：

```text
POST /api/v1/chatbi/messages/stream
```

失败时可回退兼容路径。

- [x] **Step 3: 验证**

浏览器 Network 中流式请求指向 `/api/v1/chatbi/messages/stream`。

2026-07-04 验证结果：

```text
chatbi-workspace/frontend-vue/module/module1.vue 已新增：
VUE_APP_CHATBI_API_BASE -> 默认 /api/v1/chatbi
VUE_APP_CHATBI_COMPAT_BASE -> 默认 /gac/dify/ai
流式接口优先指向 /api/v1/chatbi/messages/stream
answerMode 按快速回答/深度思考传给后端
新增 normalizeChatBIStreamEvent，兼容旧 JSON 和新 SSE data: JSON 格式
```

限制说明：

```text
chatbi-workspace/frontend-vue 当前不是完整可构建工程，目录下没有 package.json；
因此本步完成的是代码级适配和接口级回归，没有伪造 Vue 构建或浏览器 Network 截图。
独立移动端 UAT 壳 chatbi-mobile-uat.html 已继续使用标准 ChatBI API。
```

### Task 11: 增强 artifact 渲染

**Files:**

- Create: `chatbi-workspace/frontend-vue/module/ArtifactRenderer.vue`
- Modify: `Markdown.vue`
- Modify: `module1.vue`
- Create: `chatbi-workspace/frontend-vue/artifact-renderer-preview.html`

**目标:** 支持表格、图表、证据链、公司卡片。

- [x] **Step 1: 支持 table artifact**

输入：

```json
{
  "artifact_type": "table",
  "payload": {
    "columns": ["代码", "名称", "分数"],
    "rows": [["688498", "源杰科技", 80.97]]
  }
}
```

预期：前端渲染表格。

- [x] **Step 2: 支持 evidence artifact**

输入：

```json
{
  "artifact_type": "evidence",
  "payload": {
    "mapping_id": "auto_688498_ai_compute_hardware",
    "facts": []
  }
}
```

预期：前端渲染可折叠证据卡片。

- [x] **Step 3: 验证移动端**

在 390px 宽度下验证：

```text
输入框不遮挡。
表格可横向滚动。
证据卡片可折叠。
停止生成可点击。
```

2026-07-04 验证结果：

```text
新增 ArtifactRenderer.vue
Markdown.vue 自动识别 artifact/json 代码块中的 artifact_type + payload
table artifact -> 渲染为横向滚动表格
evidence artifact -> 渲染为 details/summary 可折叠证据卡片
company_card artifact -> 渲染为公司卡片
新增 artifact-renderer-preview.html，用于移动端静态预览
```

移动端静态校验：

```text
mobile_viewport=True
bottom_composer_fixed=True
content_bottom_padding=True
table_horizontal_scroll=True
evidence_collapsible=True
```

限制说明：

```text
chatbi-workspace/frontend-vue 当前没有 package.json，不是完整可构建工程；
因此本步完成的是组件代码、artifact 解析和独立 HTML 移动端预览验证，没有伪造 Vue 构建结果。
```

---

## Phase 6: 企业平台试点

### Task 12: 平台身份适配层

**Files:**

- Create: `PlatformIdentityController.java`
- Create: `PlatformIdentityService.java`
- Create: `PlatformUserBinding.java`
- Create: `db/migration/chatbi/V005__chatbi_platform_bindings.sql`

**目标:** 统一飞书、钉钉、企微身份映射。

- [x] **Step 1: 定义统一身份**

```json
{
  "platform": "feishu",
  "platform_user_id": "ou_xxx",
  "tenant_id": "tenant_001",
  "internal_user_id": "u_001",
  "display_name": "张三",
  "roles": ["analyst"],
  "permissions": ["chatbi.basic"]
}
```

- [x] **Step 2: 先接一个平台**

建议第一版选择：

```text
企业微信或飞书
```

- [x] **Step 3: 验证**

平台 WebView 打开 ChatBI 后，后端能拿到统一 `internal_user_id`。

2026-07-04 验证结果：

```text
新增表：chatbi_platform_user_bindings
新增实体：PlatformUserBinding
新增服务：PlatformIdentityService / JdbcPlatformIdentityService
新增控制器：PlatformIdentityController
第一版平台：feishu
保留平台枚举：feishu、dingtalk、wecom
```

接口：

```text
POST /api/v1/chatbi/platform/bindings
GET /api/v1/chatbi/platform/bindings
POST /api/v1/chatbi/platform/identity/resolve
GET /api/v1/chatbi/platform/identity/current
```

实测：

```text
未绑定飞书用户 -> status=unbound
绑定 feishu / tenant_demo / ou_demo_001 -> internalUserId=u_demo_001
GET /identity/current -> status=bound，internal_user_id=u_demo_001
DB 回查 -> feishu|tenant_demo|ou_demo_001|u_demo_001|analyst|chatbi.basic,chatbi.supply_chain|active
```

限制说明：

```text
当前完成的是平台身份映射底座，不是飞书/钉钉/企微真实 OAuth 登录。
真实平台 WebView 鉴权、code 换 user_id、签名校验和免登 SDK 接入仍待后续平台专项验收。
```

---

## Phase 7: UAT 和验收

> 2026-07-03 已完成 MVP UAT：验证范围为独立移动端 H5 壳、Java ChatBI API、SSE 流式问答、快速回答/深度思考模式、产业链候选真实数据接入、跨域预检和构建启动。详细结果见 `docs/qa/chatbi-uat-report-2026-07-03.md`。
>
> 2026-07-04 已完成 30 问核心问题集回归：产业链候选、公司证据链、选股模型、选债模型、模型共振、无票诊断、数据质量和报告导出共 30 条，自动化结果为 30 通过 / 0 部分通过 / 0 不通过。当前通过代表 ChatBI 编排、意图路由、已接工具的结构化回答和权限拦截可用；不代表已经补齐逐条 L8 原文证据接口、单模型候选明细接口、模型共振交集接口或真实 Word/Excel 文件导出接口。

### Task 13: 核心问题集验收

**Files:**

- Create: `docs/qa/chatbi-uat-question-set-2026-07-03.md`
- Create: `docs/qa/chatbi-uat-report-2026-07-03.md`

**目标:** 用 30 条问题验证 ChatBI 能稳定回答核心投研问题。

- [x] **Step 1: 准备问题集**

已形成 30 条核心问题集：

```text
docs/qa/chatbi-uat-question-set-2026-07-03.md
tools/chatbi_uat_runner.py
```

问题覆盖：

```text
产业链候选 5 条
公司证据链 5 条
选股模型 5 条
选债模型 5 条
模型共振 3 条
无票诊断 3 条
数据质量 2 条
报告导出 2 条
```

- [x] **Step 2: 记录结果**

每条记录：

```text
问题
意图识别结果
调用工具
是否返回结构化数据
是否带数据日期或证据来源
是否出现编造
耗时
验收结论
```

- [x] **Step 3: 通过标准**

第三轮完整 30 题自动化验收已通过：

```text
通过=30
部分通过=0
不通过=0
答案带数据日期或证据来源=30/30
原始 JSON 噪声=0/30
```

```text
核心问题可回答率 >= 80%
答案带数据日期或证据来源 = 100%
会话保存成功率 >= 99%
越权和交易执行问题拒绝率 = 100%
```

### Task 14: 性能和安全验收

**Files:**

- Create: `docs/qa/chatbi-security-performance-2026-07-03.md`

**目标:** 验证首包、总耗时、密钥清理、工具权限和平台身份。

- [x] **Step 1: 性能验收**

采集：

```text
first_token_latency_ms
total_latency_ms
tool_latency_ms
error_rate
```

目标：

```text
首包 P95 <= 3 秒
普通工具查询 P95 <= 2 秒
```

2026-07-04 结果：

```text
已新增 ChatBI 工具响应 5 分钟内存缓存和 SSE 专用 Async TaskExecutor。
冷缓存：30/30 通过，P95=9641ms，慢请求来自 supply-chain candidate-ranking 首次计算。
热缓存：30/30 通过，P95=310ms，30/30 <=2秒。
服务端不再出现 SimpleAsyncTaskExecutor under load 警告。
后续生产化仍建议增加持久化缓存、预聚合、按公司证据详情接口和报告异步任务。
```

- [x] **Step 2: 安全验收**

执行：

```bash
rg -n "password|secret|api_key|agentKey|agent_key|Authorization|Bearer app-|jdbc:mysql://|10\\.|deepseek.*key|glm.*key" chatbi-workspace
```

预期：无生产密钥和内部地址进入新工程。

- [x] **Step 3: 权限验收**

已完成 ChatBI 问答入口的权限上下文拦截：

```text
chatbi.supply_chain -> 产业链候选、公司证据链
chatbi.report_export -> 报告导出
chatbi.model -> 选股、选债、模型共振、无票诊断
chatbi.admin -> 全部放行
```

说明：当前为请求上下文权限校验。企业平台真实登录后，需要把飞书/钉钉/企微身份解析出的 permissions 注入 ChatBIRequest.context。

验证：

```text
无 chatbi.supply_chain 权限时查询 AI 算力候选 -> blocked
无 chatbi.report_export 权限时生成中际旭创报告 -> blocked
chatbi.admin 查询 AI 算力候选 -> ready
ChatBI 仍不执行用户生成 SQL，只按意图调用白名单工具
```

---

## 自检清单

| PRD AC | 对应任务 |
|---|---|
| AC-1 | Task 10、Task 11 |
| AC-2 | Task 3、Task 4、Task 7 |
| AC-3 | Task 2、Task 7 |
| AC-4 | Task 6、Task 7、Task 13 |
| AC-5 | Task 6、Task 7、Task 13 |
| AC-6 | Task 5、Task 6、Task 13 |
| AC-7 | Task 8、Task 13 |
| AC-8 | Task 8、Task 13 |
| AC-9 | Task 1、Task 2、Task 14 |
| AC-10 | Task 9 |
| AC-11 | Task 12 |
| AC-12 | Task 11、Task 12 |
| AC-13 | Task 6、Task 8 |
| AC-14 | Task 9、Task 11、Task 13 |
| AC-15 | Task 9、Task 14 |
| AC-16 | Task 7、Task 9、Task 13 |
| AC-17 | Task 9、Task 13 |
| AC-18 | Task 9、Task 13 |
| AC-19 | Task 9、Task 13 |
| AC-20 | Task 7、Task 9、Task 13 |
| AC-21 | Design Gate A、Design Gate B、Design Gate C、Design Gate D、Design Gate E、Design Gate F |
| AC-22 | Task 1、Design Gate D、Design Gate F |
| AC-23 | Task 1 Step 7、Design Gate F、Phase 7 PC 回归冒烟 |

## 执行建议

优先顺序：

```text
Task 1 -> Task 2 -> Design Gate A -> Design Gate B -> Design Gate C -> Design Gate D -> Design Gate E -> Design Gate F -> Task 3 -> Task 4 -> Task 5 -> Task 6 -> Task 7
```

完成 Design Gate A/B/C/D/E/F 前，不进入后端 Orchestrator、数据表、前端接口和企业平台实施。Design Gate F 的验收文档必须明确写出“允许进入工程实施：是”。完成 Task 3 到 Task 7 后，ChatBI 已经可以不接 Dify 地跑通核心问答。再推进会话表、前端增强、企业平台接入和 UAT。

第一批上线范围建议只包含：

```text
产业链候选总榜
公司证据链
选股模型运行
选债模型运行
无票原因诊断
模型供应商配置
节点级模型配置
提示词版本管理
报告模板版本管理
历史会话
用户反馈
```

暂缓：

```text
三平台同时上线
报告模板市场和模板共享
React 重写
自动推送日报
多 Agent 协作
```
