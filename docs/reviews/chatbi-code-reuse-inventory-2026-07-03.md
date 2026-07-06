# ChatBI 代码复用清单

**日期**: 2026-07-03  
**依据**: `docs/prd/chatbi-standalone-reuse-2026-07-03.md`、`docs/prd/chatbi-standalone-reuse-detailed-design-2026-07-03.md`、`docs/reviews/chatbi-source-audit-2026-07-03.md`  
**结论**: 第一版不推倒重写，优先适配复用原 Vue 移动端交互和原 Java/RuoYi 会话后端；Dify 调用链、敏感配置、旧平台环境配置必须替换。

## 1. 复用分级

| 分级 | 含义 | 使用原则 |
| --- | --- | --- |
| 原样复用 | 不改核心逻辑，只调整路径、命名或构建配置 | 用于低风险基础类和反馈结构 |
| 适配复用 | 保留主体代码，替换接口路径、字段映射、样式或鉴权 | 第一版主要方式 |
| 扩展复用 | 保留原组件或类，再新增投研 artifact、节点模型、证据链等能力 | 用于 ChatBI 核心体验 |
| 替换 | 不复用原实现，用本项目能力重做 | 用于 Dify、RAGFlow、旧数据源 |
| 废弃 | 不进入新工程 | 用于副本、构建产物、敏感配置 |

## 2. 前端复用清单

| 原文件 | 复用级别 | 复用原因 | 需要修改的接口或字段 | 替换原因 | 风险 |
| --- | --- | --- | --- | --- | --- |
| `ai/index.vue` | 扩展复用 | 首页结构与用户确认的移动端 ChatBI 壳一致，可复用热门关键词、近期热门话题和入口布局 | 替换旧接口为 `/api/v1/chatbi/hot-topics`、`/api/v1/chatbi/sessions`；文案改为投研数据和模型结果分析 | 不替换整体页面，只移除旧 Dify 入口和多余底部页签 | 中等，需避免把 PC 工作台逻辑带入 |
| `ai/module/module1.vue` | 扩展复用 | 包含聊天输入、回答展示、流式输出、停止生成等核心交互 | 请求改为 `/api/v1/chatbi/chat/stream`；增加 `answerMode=quick/deep`、`agentId`、`templateId`、`attachments` | Dify stream 参数和旧业务字段必须替换 | 高，SSE 事件协议需与后端严格对齐 |
| `ai/module/Markdown.vue` | 扩展复用 | 可承接模型回答的 Markdown 渲染 | 增加 artifact 渲染：表格、证据链、公司卡、产业链节点、报告段落、导出入口 | 原 Markdown 只能做文本展示，不能承载结构化投研结果 | 中等，表格在移动端需要横向滚动和折叠 |
| `ai/module/componentsHistory.vue` | 适配复用 | 可复用会话历史抽屉和搜索结构 | 接口改为 `/api/v1/chatbi/sessions`；字段改为 `sessionId/title/updatedAt/agentName` | 不替换，删除旧应用无关字段 | 中等，历史数据需和权限隔离 |
| `ai/module/feedback.vue` | 适配复用 | 可复用赞/踩、反馈原因和备注 | 接口改为 `/api/v1/chatbi/messages/{messageId}/feedback`；增加 `rating/reason/comment` | 不替换，反馈口径按投研回答质量重命名 | 低 |
| `ai/module/feedView.vue` | 适配复用 | 可作为反馈记录和用户意见展示基础 | 接口改为 `/api/v1/chatbi/feedback`；增加按会话、消息、智能体过滤 | 不替换，但不作为首屏核心页面 | 低 |
| `ai/module/module1 copy.vue` | 废弃 | 与 `module1.vue` 重复，容易形成分叉 | 无 | 重复副本不进入新工程 | 低 |
| `ai/module/module1 copy 2.vue` | 废弃 | 与 `module1.vue` 重复，容易形成分叉 | 无 | 重复副本不进入新工程 | 低 |

## 3. 后端复用清单

| 原模块 | 复用级别 | 复用原因 | 需要修改的接口或字段 | 替换原因 | 风险 |
| --- | --- | --- | --- | --- | --- |
| `GacDifyAIController` | 适配复用 | 已有聊天入口和流式返回形态 | 保留兼容路由，新增标准 `/api/v1/chatbi/chat/stream`；内部调用 `ChatBIOrchestrator` | Dify 转发逻辑必须替换 | 高，流式事件兼容会影响前端体验 |
| `AiHistoryController` | 适配复用 | 已有历史会话查询和管理入口 | 改为会话、消息、节点过程、artifact 查询 | 不替换，扩展字段即可 | 中等，权限过滤必须补齐 |
| `AiAgentTypeDifyController` | 扩展复用 | 可改造为智能体配置入口 | 去掉 Dify 类型，增加智能体、节点模型、提示词、模板绑定 | 旧命名和 Dify 依赖必须替换 | 中等，后台配置对象较多 |
| `AiHistoryEntity` | 扩展复用 | 可作为会话历史实体基础 | 增加 `sessionId/messageId/nodeRuns/artifacts/evidenceRefs/modelUsage` 等结构或关联表 | 原实体不能表达投研链路 | 中等，需控制字段膨胀 |
| `AiHistoryMapper.java` | 扩展复用 | 可保留 MyBatis 数据访问方式 | 增加会话、消息、节点过程、反馈相关查询 | 原查询粒度不足 | 中等 |
| `AiHistoryMapper.xml` | 扩展复用 | 可保留 XML Mapper 风格 | 扩展 SQL 到 `chatbi_sessions/messages/node_runs/artifacts` | 原表结构不足 | 中等，SQL 需适配目标数据库 |
| `GacDifyData` | 适配复用 | 可作为 SSE 事件 DTO 的基础 | 字段改为 `event/type/sessionId/messageId/node/status/payload` | Dify 字段不再作为标准协议 | 中等，需兼容前端事件处理 |
| `GacRAGFlowAIRequestVO` | 适配复用 | 可作为请求 VO 基础 | 重命名为 ChatBI 请求；增加 `query/mode/agentId/templateId/attachments/context` | RAGFlow 语义不再适用 | 低 |
| `AiFeedbackRequestVO` | 原样复用 | 反馈请求结构简单，可保留 | 如缺字段再增加 `messageId/rating/reason/comment` | 无 | 低 |
| `BaseController` | 原样复用 | RuoYi 基础 Controller 可降低后端迁移成本 | 如接入本项目权限上下文，补充用户信息获取 | 无 | 低 |
| `AjaxResult` | 原样复用 | 统一返回结构可复用 | 与标准 API 包装对齐，必要时外层适配 | 无 | 低 |
| RuoYi 权限和审计基础类 | 适配复用 | 后台管理、权限注解、审计思路可复用 | 接入本项目账号、企业应用身份、操作日志 | 原项目登录态不能直接信任 | 中等 |
| `GacAIDifySteamServiceImpl` | 替换 | 旧服务主要职责是 Dify 流式转发 | 替换为 `ChatBIOrchestrator`、节点路由、工具调用、模型网关 | 不接 Dify 是核心需求 | 高，需完整测试 |
| `application-gac-*.yml`、`application.yml` | 废弃 | 包含旧环境连接和敏感配置 | 改为配置模板、环境变量和密钥管理 | 不能提交旧密钥和内网 URL | 高 |
| `.git/`、`target/`、`.idea/`、`*.class` | 废弃 | 不是源码，且存在泄露和污染风险 | 无 | 不允许进入新工程 | 高 |

## 4. Dify 替换边界

必须替换的能力：

- Dify completion / chat / workflow 转发。
- Dify conversation id 作为唯一会话 id 的设计。
- Dify agent type 命名和字段。
- Dify/RAGFlow 密钥配置。

替换后的能力：

- `ChatBI Orchestrator`: 识别意图、选择快速回答或深度思考、编排工具、组织证据、生成结构化回答。
- `Model Gateway`: 对 DeepSeek、GLM、Qwen 等供应商做统一适配。
- `Tool Gateway`: 只允许调用白名单投研工具，不允许模型直接 SQL。
- `Prompt/Report Template Manager`: 按智能体和节点绑定提示词、模型和报告模板。

## 5. PC 端隔离要求

本次复用清单只面向独立移动端 ChatBI H5。实施时不得修改：

- 当前 PC 端左侧导航。
- 当前 PC 端工作台页面。
- 当前产业链拆解页面路由。
- 当前 React/Vite 前端的业务组件。

如未来需要 PC 管理入口，必须另开需求确认。

## 6. 实施顺序建议

1. 清洗后复制可复用源码到独立 `chatbi-workspace`。
2. 先建立后端标准 API 和 SSE 协议。
3. 再改造 `module1.vue` 接标准流式接口。
4. 再补历史会话、反馈、热门话题。
5. 最后补 artifact、报告模板、企业平台挂载。

## 7. 验收要求

工程实施前必须满足：

- 本清单中所有“废弃”项不得进入新工程。
- 所有“替换”项必须有新模块承接。
- 所有“扩展复用”项必须有字段兼容说明和测试。
- 所有“适配复用”项必须保留核心交互或核心数据访问方式。
- PC 端代码变更检查必须为空。

