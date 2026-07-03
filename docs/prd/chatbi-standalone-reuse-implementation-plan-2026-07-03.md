# 独立 ChatBI 应用复用改造实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 复用原 ChatBI Vue 前端和 Java/Spring Boot 后端，移除 Dify 依赖，接入 K线大模型投研工具，并预留飞书、钉钉、企业微信挂载能力。

**Architecture:** 第一版保留原 ChatBI 的前端交互、会话历史和反馈能力；后端把 Dify 流式转发替换为 ChatBI Orchestrator；投研数据通过 K线大模型 FastAPI 工具接口访问，不直接查核心 PostgreSQL 表。

**Tech Stack:** Vue + Java Spring Boot/RuoYi + MyBatis/MySQL 或 PostgreSQL 会话库 + FastAPI 工具服务 + SSE + H5 企业应用 WebView。

## Global Constraints

- 不接 Dify，不保留 Dify agent key、workflow path 或 Dify 运行依赖。
- 不允许 ChatBI 直接执行用户生成 SQL。
- 不提供自动买卖、实盘下单、绕过风控的交易指令。
- Java 后端不直接读写 K线大模型核心 PostgreSQL 表，优先通过内部 FastAPI 工具接口访问。
- 原包中的数据库账号、密码、Dify key、企业内部 URL 不进入新仓库配置。
- DeepSeek、GLM5.2 等模型必须通过统一 LLM Gateway 调用，不能散落在业务代码里。
- 模型供应商 key 只允许加密存储或引用密钥管理系统，前端和普通 API 只能看到脱敏标识。
- 生产问答只能使用 published 提示词版本和 published 报告模板版本。
- SSE 首包 P95 ≤ 3 秒；普通工具查询 P95 ≤ 2 秒；长任务必须返回节点进度。
- 投资相关回答必须显示数据日期、模型版本或证据来源。

---

## Phase 0: 安全清理和工程边界

### Task 1: 解压原包并生成干净工程副本

**Files:**

- Read: `chatBI/ai 前端.zip`
- Read: `chatBI/AI 后端.zip`
- Create: `chatbi-workspace/frontend-vue/`
- Create: `chatbi-workspace/backend-java/`
- Create: `docs/reviews/chatbi-source-audit-2026-07-03.md`

**目标:** 把可复用源码从压缩包中提取出来，剔除 `.git`、`target`、IDE 文件和敏感配置。

- [ ] **Step 1: 解压到隔离目录**

```bash
mkdir -p chatbi-workspace/raw
unzip -q "chatBI/ai 前端.zip" -d chatbi-workspace/raw/frontend
unzip -q "chatBI/AI 后端.zip" -d chatbi-workspace/raw/backend
```

预期：`chatbi-workspace/raw/frontend/ai` 和 `chatbi-workspace/raw/backend/cockpit-screen` 存在。

- [ ] **Step 2: 复制可用源码**

```bash
mkdir -p chatbi-workspace/frontend-vue chatbi-workspace/backend-java
rsync -a --exclude='.git' --exclude='.idea' --exclude='target' chatbi-workspace/raw/frontend/ai/ chatbi-workspace/frontend-vue/
rsync -a --exclude='.git' --exclude='.idea' --exclude='target' chatbi-workspace/raw/backend/cockpit-screen/ chatbi-workspace/backend-java/
```

预期：干净目录中没有 `.git`、`.idea`、`target`。

- [ ] **Step 3: 扫描敏感信息**

```bash
rg -n "password|passwd|secret|agentKey|agent_key|Bearer|jdbc:mysql|10\\.|app-" chatbi-workspace/backend-java chatbi-workspace/frontend-vue
```

预期：输出所有疑似密钥和内部地址，写入审计报告。

- [ ] **Step 4: 形成审计报告**

报告必须包含：

```text
源码来源
保留文件清单
剔除文件清单
发现的敏感配置类型
需要轮换的密钥类别
是否允许进入后续开发
```

- [ ] **Step 5: 验证**

```bash
test ! -d chatbi-workspace/backend-java/.git
test ! -d chatbi-workspace/backend-java/target
test ! -d chatbi-workspace/backend-java/.idea
```

预期：命令返回 0。

### Task 2: 密钥和配置治理

**Files:**

- Modify: `chatbi-workspace/backend-java/cockpit-screen-admin/src/main/resources/application.yml`
- Modify: `chatbi-workspace/backend-java/cockpit-screen-admin/src/main/resources/application-*.yml`
- Create: `chatbi-workspace/backend-java/.env.example`
- Create: `docs/security/chatbi-secret-rotation-2026-07-03.md`

**目标:** 删除包内明文账号、密码、内部 URL 和 Dify key，把运行配置改为环境变量。

- [ ] **Step 1: 把数据库配置改为环境变量**

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

- [ ] **Step 2: 删除 Dify 配置**

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

- [ ] **Step 3: 创建 `.env.example`**

必须包含：

```text
CHATBI_DB_URL=
CHATBI_DB_USERNAME=
CHATBI_DB_PASSWORD=
CHATBI_TOOL_GATEWAY_BASE_URL=
CHATBI_PLATFORM_SECRET=
```

- [ ] **Step 4: 记录密钥轮换**

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

```bash
rg -n "jdbc:mysql://|password: '.+'|agentKey|Bearer app-|10\\.30\\." chatbi-workspace/backend-java
```

预期：无生产密钥命中；如果命中，只允许出现在 `.env.example` 的空值说明中。

---

## Phase 1: 后端 ChatBI Orchestrator

### Task 3: 建立标准 ChatBI API 和兼容路由

**Files:**

- Create: `chatbi-workspace/backend-java/cockpit-screen-admin/src/main/java/com/ds/cockpit/screen/web/controller/chatbi/ChatBIController.java`
- Modify: `GacDifyAIController.java`
- Test: `chatbi-workspace/backend-java/cockpit-screen-admin/src/test/java/.../ChatBIControllerTest.java`

**目标:** 新增标准 `/api/v1/chatbi` 路由，同时保留 `/gac/dify/ai` 兼容路径。

- [ ] **Step 1: 新增接口**

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

- [ ] **Step 2: 兼容旧路由**

旧路由映射：

```text
/gac/dify/ai/created/session -> /api/v1/chatbi/sessions
/gac/dify/ai/created/data/uuid -> /api/v1/chatbi/messages/prepare
/gac/dify/ai/chat-messages -> /api/v1/chatbi/messages/stream
/gac/dify/ai/feedback -> /api/v1/chatbi/feedback
```

- [ ] **Step 3: 验证**

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

- [ ] **Step 1: 定义事件类型**

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

- [ ] **Step 2: 定义兼容输出**

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

- [ ] **Step 3: 测试事件顺序**

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

- [ ] **Step 1: 支持意图**

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

- [ ] **Step 2: 编写规则**

规则示例：

```text
包含“产业链”“候选”“Top” -> supply_chain_ranking
包含“证据链”“L8”“研发”“商用” -> company_evidence
包含“选债”“可转债”“匪爷” -> bond_model_run
包含“为什么没有”“没票”“未入选” -> no_pick_diagnosis
包含“共振”“多个模型”“同时命中” -> model_resonance
```

- [ ] **Step 3: 验证**

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

第一批接口：

```text
GET /api/v1/screener/supply-chain/candidate-ranking
GET /api/v1/screener/supply-chain/company/{code}
GET /api/v1/screener/supply-chain/business-tag/{mapping_id}/evidence-chain
POST /api/v1/screener/run
GET /api/v1/screener/modes
GET /api/v1/screener/market/index-quotes
```

- [ ] **Step 2: 增加超时和错误结构**

默认：

```text
connectTimeout = 3s
readTimeout = 10s
maxRows = 200
```

- [ ] **Step 3: 验证真实接口**

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

- [ ] **Step 1: 删除 Dify 运行依赖**

禁用以下行为：

```text
读取 ai_agent_type_dify.agent_key 作为 Dify key
调用 Dify chat-messages
调用 Dify workflow
```

- [ ] **Step 2: 输出节点事件**

每次问答至少输出：

```text
问题识别
工具选择
数据查询
答案生成
生成完成
```

- [ ] **Step 3: 答案生成**

第一版可用模板回答，不强制调用 LLM：

```text
结论
数据表
证据/来源
限制说明
下一步建议
```

- [ ] **Step 4: 验证**

```bash
curl -N -X POST http://localhost:8080/api/v1/chatbi/messages/stream \
  -H "Content-Type: application/json" \
  -d '{"question":"AI算力候选公司Top5","userId":"test","userName":"测试","sessionUuid":"s1","id":1}'
```

预期：流中不出现 Dify 请求错误，能返回候选表格文本或 artifact。

---

## Phase 2: 数据、会话、反馈和智能体配置

### Task 8: 设计并迁移 ChatBI 会话表

**Files:**

- Create: `db/migration/chatbi/V001__chatbi_core_tables.sql`
- Modify: `AiHistoryMapper.xml`
- Test: DB migration smoke

**目标:** 建立 ChatBI 自有会话、消息、事件、反馈、工具调用表。

- [ ] **Step 1: 创建表**

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

旧接口：

```text
/ai/histroy/record/list
/ai/histroy/gethistory
```

仍返回前端可用结构。

- [ ] **Step 3: 验证**

提交一轮问答后检查：

```text
chatbi_sessions 有会话
chatbi_messages 有问题和答案
chatbi_message_events 有节点事件
chatbi_tool_calls 有工具调用记录
```

### Task 9: 智能体、提示词和报告模板配置

**Files:**

- Create: `db/migration/chatbi/V002__chatbi_agent_prompt_template.sql`
- Create: `ChatBIAgentController.java`
- Create: `PromptTemplateController.java`
- Create: `ReportTemplateController.java`

**目标:** 把原 Dify agent 配置改为 ChatBI 智能体、提示词和模板配置。

- [ ] **Step 1: 新增配置表**

```text
chatbi_agents
chatbi_agent_tools
chatbi_prompt_versions
chatbi_report_templates
```

- [ ] **Step 2: 内置第一批智能体**

```text
总入口助手
产业链助手
选股助手
选债助手
报告助手
数据质量助手
```

- [ ] **Step 3: 验证**

```bash
curl http://localhost:8080/api/v1/chatbi/agents
```

预期：返回启用状态的智能体列表，不包含 Dify key。

---

## Phase 3: 前端复用和增强

### Task 10: 前端 API 适配

**Files:**

- Modify: `chatbi-workspace/frontend-vue/api/home/home.js`
- Modify: `chatbi-workspace/frontend-vue/module/module1.vue`

**目标:** 前端从旧 Dify 路径平滑切换到标准 ChatBI 路径。

- [ ] **Step 1: 增加 API 配置**

支持：

```text
VUE_APP_CHATBI_API_BASE=/api/v1/chatbi
VUE_APP_CHATBI_COMPAT_BASE=/gac/dify/ai
```

- [ ] **Step 2: 切换流式接口**

优先调用：

```text
POST /api/v1/chatbi/messages/stream
```

失败时可回退兼容路径。

- [ ] **Step 3: 验证**

浏览器 Network 中流式请求指向 `/api/v1/chatbi/messages/stream`。

### Task 11: 增强 artifact 渲染

**Files:**

- Create: `chatbi-workspace/frontend-vue/module/ArtifactRenderer.vue`
- Modify: `Markdown.vue`
- Modify: `module1.vue`

**目标:** 支持表格、图表、证据链、公司卡片。

- [ ] **Step 1: 支持 table artifact**

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

- [ ] **Step 2: 支持 evidence artifact**

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

- [ ] **Step 3: 验证移动端**

在 390px 宽度下验证：

```text
输入框不遮挡。
表格可横向滚动。
证据卡片可折叠。
停止生成可点击。
```

---

## Phase 4: 企业平台试点

### Task 12: 平台身份适配层

**Files:**

- Create: `PlatformIdentityController.java`
- Create: `PlatformIdentityService.java`
- Create: `PlatformUserBinding.java`
- Create: `db/migration/chatbi/V003__chatbi_platform_bindings.sql`

**目标:** 统一飞书、钉钉、企微身份映射。

- [ ] **Step 1: 定义统一身份**

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

- [ ] **Step 2: 先接一个平台**

建议第一版选择：

```text
企业微信或飞书
```

- [ ] **Step 3: 验证**

平台 WebView 打开 ChatBI 后，后端能拿到统一 `internal_user_id`。

---

## Phase 5: UAT 和验收

### Task 13: 核心问题集验收

**Files:**

- Create: `docs/qa/chatbi-uat-question-set-2026-07-03.md`
- Create: `docs/qa/chatbi-uat-report-2026-07-03.md`

**目标:** 用 30 条问题验证 ChatBI 能稳定回答核心投研问题。

- [ ] **Step 1: 准备问题集**

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

- [ ] **Step 2: 记录结果**

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

- [ ] **Step 3: 通过标准**

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

- [ ] **Step 1: 性能验收**

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

- [ ] **Step 2: 安全验收**

执行：

```bash
rg -n "password|secret|Bearer app-|jdbc:mysql://|10\\." chatbi-workspace
```

预期：无生产密钥和内部地址进入新工程。

- [ ] **Step 3: 权限验收**

验证：

```text
无 chatbi.supply_chain 权限时不能查产业链证据。
无 chatbi.report_export 权限时不能导出报告。
用户不能通过问题文本执行 SQL。
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

## 执行建议

优先顺序：

```text
Task 1 -> Task 2 -> Task 3 -> Task 4 -> Task 5 -> Task 6 -> Task 7
```

完成以上任务后，ChatBI 已经可以不接 Dify 地跑通核心问答。再推进会话表、前端增强、企业平台接入和 UAT。

第一批上线范围建议只包含：

```text
产业链候选总榜
公司证据链
选股模型运行
选债模型运行
无票原因诊断
历史会话
用户反馈
```

暂缓：

```text
三平台同时上线
完整报告模板市场
React 重写
自动推送日报
多 Agent 协作
```
