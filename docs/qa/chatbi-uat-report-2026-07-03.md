# ChatBI MVP UAT 报告

**日期**: 2026-07-03  
**对象**: 独立移动端 ChatBI H5 + Java ChatBI 后端 + K线大模型产业链工具服务  
**结论**: MVP UAT 通过。  

## 1. 验收范围

本次只验收最小可用闭环：

| 范围 | 状态 |
| --- | --- |
| 独立移动端 H5 壳 | 通过 |
| 不改现有 PC 端 | 通过 |
| 标准 `/api/v1/chatbi` API | 通过 |
| 兼容旧 `/gac/dify/ai` 路由 | 已接入，未完整回归 |
| 快速回答 | 通过 |
| 深度思考 | 通过 |
| SSE 节点事件 | 通过 |
| 真实产业链候选数据 | 通过 |
| 跨域预检 | 通过 |
| 完整 30 条问题集 | 未执行 |
| 企业 WebView 实机 | 未执行 |
| 提示词管理、报告模板、模型供应商配置 | 未执行 |

## 2. UAT 运行地址

后端服务：

```text
http://127.0.0.1:8088/ds-cockpit-screen/api/v1/chatbi
```

工具服务：

```text
http://127.0.0.1:18088/api/v1
```

移动端 H5 文件：

```text
file:///Users/rogerluo/程序目录/K线大模型/chatbi-workspace/frontend-vue/chatbi-mobile-uat.html
```

## 3. 验收结果

| 项目 | 结果 |
| --- | --- |
| Java 后端编译 | `mvn -pl cockpit-screen-admin -am -DskipTests package` 通过 |
| 工具服务健康检查 | `{"status":"healthy","service":"screener-service","version":"0.1.0"}` |
| CORS 预检 | `Access-Control-Allow-Origin: null`，本地 H5 可调用 |
| 快速回答 | 返回 AI 算力 Top5，未暴露原始 JSON |
| 深度思考 | 返回具身智能候选清单，包含节点过程 |
| 数据日期 | 返回 `latest_trade_date=2026-07-03` |
| 数据版本 | 返回 `supply-chain-candidate-ranking-v1` |

## 4. 核心问题验收

### 问题 1：AI算力候选公司Top5

模式：快速回答  
结果：通过  

返回摘要：

```text
源杰科技（688498）：重点候选，总分 81.18，三高 80.69，阶段 R2 / C2，L8证据 100%，事实 230 条，最新交易日 2026-07-03。
澜起科技（688008）：观察，总分 74.65。
江波龙（301308）：观察，总分 73.2。
新易盛（300502）：观察，总分 73.11。
东芯股份（688110）：观察，总分 72.61。
```

### 问题 2：具身智能产业链卡脖子公司清单

模式：深度思考  
结果：通过  

返回摘要：

```text
威迈斯（688612）：观察，总分 66.75。
双林股份（300100）：观察，总分 66.73。
绿的谐波（688017）：观察，总分 65.53。
众智科技（301361）：观察，总分 65.49。
奥比中光（688322）：暂缓，总分 63.47。
```

## 5. 本轮修复项

| 问题 | 处理 |
| --- | --- |
| 本地 H5 被浏览器 CORS 拦截风险 | 后端新增 ChatBI 路由 CORS 配置 |
| 页面把 UUID `id` 传给 Long 字段导致 500 | H5 stream 请求不再回传 prepare 的 UUID |
| 工具接口拉取全量 by_chain 导致超时 | 工具网关按问题关键词追加 `chain_id`，收窄结果集 |
| 原始 JSON 直接展示 | Orchestrator 增加产业链结果格式化 |
| 旧 RuoYi 表不存在导致启动失败 | 缓存、字典、Quartz 初始化降级处理 |
| 明文 RSA 私钥 | 改为环境变量加载 |

## 6. 已知边界

- 当前会话存储为内存 Map，重启后会丢失；正式版本需接入 ChatBI 会话表。
- 选股、选债、无票诊断、模型共振只完成路由占位，尚未形成完整投研回答。
- 深度思考目前是编排和模板化分析，尚未接入真实大模型节点级配置。
- 提示词管理、报告模板管理、报告导出、企业平台身份未进入本轮 MVP。
- 内置浏览器自动化插件本机文档缺失，本轮使用接口级自动验收和 H5 文件检查替代截图验收。

## 7. 2026-07-04 增量验收：会话持久化

本次补齐 Phase 4 Task 8 的 MVP 持久化能力。

新增表：

```text
chatbi_sessions
chatbi_messages
chatbi_message_events
chatbi_tool_calls
chatbi_feedback
chatbi_audit_logs
```

验证结果：

```text
sessions=1
messages=1
events=6
tool_calls=1
feedback=1
```

最近一条会话：

```text
AI算力候选公司Top5
```

最近一条消息：

```text
status=completed
intent=supply_chain_ranking
answer 已写入
```

结论：标准 ChatBI 接口已不再依赖内存 Map 作为唯一存储；会话、消息、事件、工具调用和反馈可以在 PostgreSQL 中追溯。

## 8. 2026-07-04 增量验收：模型、提示词和报告模板配置底座

本次补齐 Phase 4 Task 9 的 MVP 配置底座。

新增表：

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

配置摘要接口：

```text
GET /api/v1/chatbi/config/summary
```

返回结果：

```text
provider_count=3
model_count=3
agent_count=6
binding_count=36
prompt_version_count=1
report_template_count=1
report_template_version_count=1
status=ready
```

默认供应商：

```text
deepseek -> DEEPSEEK_API_KEY
glm -> GLM_API_KEY
openai_compatible -> OPENAI_COMPATIBLE_API_KEY
```

默认模型：

```text
deepseek-chat
glm-5.2
custom-model
```

默认智能体：

```text
总入口助手
产业链助手
选股助手
选债助手
报告助手
数据质量助手
```

发布接口已通过：

```text
POST /api/v1/chatbi/prompts/default_prompt/versions/v1/publish
POST /api/v1/chatbi/report-templates/default_report/versions/v1/publish
```

模型供应商测试接口已通过：

```text
POST /api/v1/chatbi/model-providers/deepseek/test
```

当前本机未配置 `DEEPSEEK_API_KEY`，因此接口明确返回 `status=unavailable`，没有伪造真实连通成功。

主问答回归：

```text
AI算力候选公司Top5 -> 返回源杰科技等候选排序，CHAT_OK=true
```

结论：配置底座已可用；真实 LLM Gateway 调用、token 统计、fallback 执行和节点级模型实际切换仍是后续任务。

## 9. 2026-07-04 增量验收：LLM Gateway 和深度思考降级链路

本次补齐 Phase 4 Task 9 的 LLM Gateway MVP。

新增表：

```text
chatbi_llm_invocations
```

新增接口：

```text
POST /api/v1/chatbi/llm/generate
```

接入节点：

```text
answer_generation
```

验证输入：

```text
agent_id=default
node_type=answer_generation
prompt=请总结AI算力候选公司
```

验证结果：

```text
status=unavailable
deepseek-chat -> missing_api_key:DEEPSEEK_API_KEY
glm-5.2 -> missing_api_key:GLM_API_KEY
custom-model -> missing_api_key:OPENAI_COMPATIBLE_API_KEY
message=所有候选模型均不可用，已降级为模板化回答。
```

调用日志：

```text
llm_invocations=6
```

深度思考主问答回归：

```text
具身智能产业链卡脖子公司清单 -> 返回威迈斯、双林股份、绿的谐波等候选排序
回答中明确包含：大模型状态：unavailable。所有候选模型均不可用，已降级为模板化回答。
```

安全检查：

```text
未发现 DEEPSEEK_API_KEY、GLM_API_KEY、OPENAI_COMPATIBLE_API_KEY、Bearer token、私钥或内部 MySQL 地址泄漏。
```

结论：LLM Gateway、节点级模型读取、fallback 尝试、调用日志和深度思考降级链路已跑通。本机没有真实模型 API Key，因此尚未完成外部模型真实连通 UAT；该部分必须在配置真实密钥后单独验收，不能冒充已完成。

## 10. 2026-07-04 增量验收：节点级模型配置接口

本次补齐 Phase 4 Task 9 的节点级模型配置接口。

新增接口：

```text
GET /api/v1/chatbi/agents/{id}/model-bindings
PUT /api/v1/chatbi/agents/{id}/model-bindings
```

验证对象：

```text
agent_id=supply_chain
```

读取验证：

```text
GET /api/v1/chatbi/agents/supply_chain/model-bindings
code=200
binding_count=6
contains_api_key_field=False
```

保存验证：

```text
PUT /api/v1/chatbi/agents/supply_chain/model-bindings
node_type=answer_generation
primary_model_id=deepseek-chat
fallback_model_ids=["glm-5.2","custom-model"]
prompt_version_id=default_prompt_v1
code=200
```

数据库回查：

```text
supply_chain_answer_generation|deepseek-chat|glm-5.2,custom-model|default_prompt_v1
```

负向校验：

```text
primary_model_id=bad-model
返回：模型不存在或未启用：bad-model
数据库未覆盖原配置
```

结论：节点级模型配置接口已能按智能体读取和批量保存；保存时会校验智能体、模型和提示词版本，响应不返回 API Key 字段。HTTP 状态仍沿用 RuoYi 统一返回风格，业务错误通过 JSON `code=500` 表达。

## 11. 2026-07-04 增量验收：预览接口

本次补齐 Phase 4 Task 9 的配置预览接口。

新增表：

```text
chatbi_preview_logs
```

新增接口：

```text
POST /api/v1/chatbi/preview
```

验证输入：

```text
agent_id=supply_chain
node_type=answer_generation
model_id=deepseek-chat
prompt_version_id=default_prompt_v1
question=AI算力候选Top5
```

接口返回：

```text
code=200
status=unavailable
provider_id=deepseek
model_id=deepseek-chat
prompt_version_id=default_prompt_v1
persisted_to_session=false
message=所有候选模型均不可用，已降级为模板化回答。
```

数据库验证：

```text
sessions_before=5
sessions_after=5
preview_before=0
preview_after=1
57dbd31a-77c9-4216-b236-08f63f7af8d9|supply_chain|answer_generation|deepseek|deepseek-chat|default_prompt_v1|unavailable
```

结论：预览接口不会写入正式会话历史，只写 `chatbi_preview_logs`；本机未配置真实模型 API Key，因此预览结果按 LLM Gateway 规则明确降级，没有伪造模型输出。

## 12. 2026-07-04 增量验收：Task 9 总验证和报告生成节点回归

配置接口总验证：

```text
/api/v1/chatbi/agents -> code=200
/api/v1/chatbi/agents/supply_chain/model-bindings -> code=200
/api/v1/chatbi/model-providers -> code=200
/api/v1/chatbi/prompts -> code=200
/api/v1/chatbi/report-templates -> code=200
/api/v1/chatbi/config/summary -> code=200
```

安全验证：

```text
model-providers 响应未发现 sk-、Bearer 或明文 API Key
```

快速回答回归：

```text
AI算力候选公司Top5 -> 命中源杰科技
未出现原始 JSON 噪声
```

报告类深度思考回归：

```text
问题：生成中际旭创产业链拆解报告
contains_report_event=True
contains_llm_unavailable=True
contains_supply_chain_result=True
```

节点调用日志：

```text
intent_recognition|deepseek|deepseek-chat|unavailable|missing_api_key:DEEPSEEK_API_KEY
intent_recognition|glm|glm-5.2|unavailable|missing_api_key:GLM_API_KEY
intent_recognition|openai_compatible|custom-model|unavailable|missing_api_key:OPENAI_COMPATIBLE_API_KEY
report_generation|glm|glm-5.2|unavailable|missing_api_key:GLM_API_KEY
report_generation|deepseek|deepseek-chat|unavailable|missing_api_key:DEEPSEEK_API_KEY
report_generation|openai_compatible|custom-model|unavailable|missing_api_key:OPENAI_COMPATIBLE_API_KEY
```

结论：节点级模型配置已实际影响编排。深度思考会记录 `intent_recognition`；报告类问题会进入 `report_generation`，默认主模型为 GLM，普通意图识别主模型为 DeepSeek。本机无真实 API Key，因此状态为 unavailable，这是符合事实的降级结果。

## 13. 2026-07-04 增量验收：前端 API 适配

适配范围：

```text
chatbi-workspace/frontend-vue/module/module1.vue
chatbi-workspace/frontend-vue/chatbi-mobile-uat.html
```

本次处理：

```text
新增 VUE_APP_CHATBI_API_BASE，默认 /api/v1/chatbi
新增 VUE_APP_CHATBI_COMPAT_BASE，默认 /gac/dify/ai
旧 Vue 壳流式接口从 /gac/dify/ai/chat-messages 切到 /api/v1/chatbi/messages/stream
请求体补充 answerMode，快速回答传 quick，深度思考传 deep
新增 normalizeChatBIStreamEvent，同时兼容旧 JSON 和新 SSE data: JSON
```

接口回归：

```text
POST /api/v1/chatbi/messages/stream -> 返回 SSE data: JSON
```

限制说明：

```text
chatbi-workspace/frontend-vue 当前不是完整可构建工程，没有 package.json；
因此本轮没有伪造 Vue 构建结果，也没有伪造浏览器 Network 截图。
独立移动端 UAT 壳 chatbi-mobile-uat.html 已继续使用标准 ChatBI API。
```

## 14. 2026-07-04 增量验收：Artifact 渲染

新增文件：

```text
chatbi-workspace/frontend-vue/module/ArtifactRenderer.vue
chatbi-workspace/frontend-vue/artifact-renderer-preview.html
```

修改文件：

```text
chatbi-workspace/frontend-vue/module/Markdown.vue
```

支持类型：

```text
table -> 横向滚动表格
evidence -> 可折叠证据链
company_card -> 公司卡片
unknown -> JSON 兜底展示
```

解析规则：

```text
Markdown.vue 自动识别 artifact/json 代码块中的 artifact_type + payload。
解析成功后从普通 Markdown 中移除该代码块，交给 ArtifactRenderer.vue 渲染。
解析失败时保留原代码块，不吞内容。
```

移动端预览文件：

```text
file:///Users/rogerluo/程序目录/K线大模型/chatbi-workspace/frontend-vue/artifact-renderer-preview.html
```

静态验收结果：

```text
mobile_viewport=True
bottom_composer_fixed=True
content_bottom_padding=True
table_horizontal_scroll=True
evidence_collapsible=True
```

限制说明：

```text
chatbi-workspace/frontend-vue 当前没有 package.json，不能执行真实 Vue 构建。
本轮没有伪造构建结果；只完成组件代码、解析逻辑和独立移动端 HTML 预览验证。
```

## 15. 2026-07-04 增量验收：企业平台身份适配层

本次补齐 Phase 6 Task 12 的平台身份映射底座。

新增表：

```text
chatbi_platform_user_bindings
```

新增文件：

```text
db/migration/chatbi/V005__chatbi_platform_bindings.sql
chatbi-workspace/backend-java/cockpit-screen-common/src/main/java/com/ds/cockpit/screen/common/core/domain/entity/vo/chatbi/PlatformUserBinding.java
chatbi-workspace/backend-java/cockpit-screen-system/src/main/java/com/ds/cockpit/screen/system/service/chatbi/PlatformIdentityService.java
chatbi-workspace/backend-java/cockpit-screen-system/src/main/java/com/ds/cockpit/screen/system/service/chatbi/impl/JdbcPlatformIdentityService.java
chatbi-workspace/backend-java/cockpit-screen-admin/src/main/java/com/ds/cockpit/screen/web/controller/chatbi/PlatformIdentityController.java
```

接口：

```text
POST /api/v1/chatbi/platform/bindings
GET /api/v1/chatbi/platform/bindings
POST /api/v1/chatbi/platform/identity/resolve
GET /api/v1/chatbi/platform/identity/current
```

支持平台枚举：

```text
feishu
dingtalk
wecom
```

第一版实测平台：

```text
feishu
```

未绑定验证：

```text
platform=feishu
platform_user_id=ou_demo_001
tenant_id=tenant_demo
status=unbound
internal_user_id=
```

绑定验证：

```text
platform=feishu
platform_user_id=ou_demo_001
tenant_id=tenant_demo
internal_user_id=u_demo_001
display_name=张三
roles=["analyst"]
permissions=["chatbi.basic","chatbi.supply_chain"]
```

解析验证：

```text
GET /api/v1/chatbi/platform/identity/current?platform=feishu&platformUserId=ou_demo_001&tenantId=tenant_demo
status=bound
internal_user_id=u_demo_001
```

数据库回查：

```text
feishu|tenant_demo|ou_demo_001|u_demo_001|analyst|chatbi.basic,chatbi.supply_chain|active
```

结论：平台身份到内部用户的统一映射底座已可用。当前没有接真实飞书 OAuth 或免登 SDK，因此不能声称已经完成企业平台真实登录；后续需要在真实 WebView 环境中验证 code 换 user_id、签名校验和租户隔离。

## 16. 2026-07-04 完整验收：30 问核心问题集

执行脚本：

```text
tools/chatbi_uat_runner.py
```

输出文件：

```text
outputs/chatbi_uat/chatbi_uat_30q_results.json
outputs/chatbi_uat/chatbi_uat_30q_results.md
```

覆盖范围：

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

最终结果：

```text
通过=30
部分通过=0
不通过=0
总数=30
答案带数据日期或证据来源=30/30
原始 JSON 噪声=0/30
```

本轮修复点：

```text
收窄意图识别优先级，避免“产业链/清单/top”抢走公司证据链、模型、报告问题。
新增公司证据链、选股模型、选债模型、无票诊断、模型共振、数据质量、报告草稿的中文结构化摘要。
报告导出当前明确标记为“文本草稿”，不伪造 Word/Excel 文件。
公司证据链当前明确标记为“候选证据摘要”，不伪造逐条 L8 原文证据。
```

仍需后续补强的真实工具：

```text
按公司代码/名称查询逐条 L8 原文证据、公告/研报来源、页码和发布时间。
按模型查询今日候选、失败门槛和无票原因。
选股、选债、产业链候选的共振交集统计。
报告模板渲染、文件存储和 Word/Excel 下载。
真实外部大模型 API Key 配置后的联网 UAT。
```

结论：ChatBI 编排、移动端问答接口、意图路由、已接工具结构化回答通过完整 30 问 UAT；剩余为投研工具深度接口和文件导出能力，不在本次“壳 + 后端编排 + 标准问答闭环”的完成口径内。

## 17. 2026-07-04 完整验收：权限拦截

新增权限规则：

```text
chatbi.supply_chain -> 产业链候选、公司证据链
chatbi.report_export -> 报告导出
chatbi.model -> 选股、选债、模型共振、无票诊断
chatbi.admin -> 全部放行
```

验证结果：

```text
无 chatbi.supply_chain 权限查询 AI算力候选公司Top5 -> blocked
无 chatbi.report_export 权限生成中际旭创产业链拆解报告 -> blocked
chatbi.admin 查询 AI算力候选公司Top5 -> ready
```

说明：当前权限来自 `ChatBIRequest.context.permissions`。企业 WebView 真实接入后，需要由平台身份解析层把飞书、钉钉或企微用户绑定的 permissions 注入请求上下文。

## 18. 2026-07-04 完整验收：性能优化回归

本次新增：

```text
ChatBI SSE 专用 Async TaskExecutor
工具网关成功响应 5 分钟内存缓存
```

冷缓存结果：

```text
通过=30
部分通过=0
不通过=0
P50=292.5ms
P95=9641ms
>3秒=11条
```

热缓存结果：

```text
通过=30
部分通过=0
不通过=0
P50=275.5ms
P95=310ms
<=2秒=30条
>3秒=0条
```

日志检查：

```text
未再出现 SimpleAsyncTaskExecutor under load 警告。
```

结论：热缓存下 30 问功能和性能均通过；冷缓存仍受 supply-chain candidate-ranking 首次计算影响，生产化需要继续做持久化缓存或预聚合。
