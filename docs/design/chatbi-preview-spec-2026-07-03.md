# ChatBI 静态预览说明

- **日期**: 2026-07-03
- **状态**: Draft
- **阶段**: Design Gate B
- **预览文件**: `docs/design/chatbi-preview/index.html`
- **Mock 数据**: `docs/design/chatbi-preview/mock-data.json`
- **对应原型说明**: `docs/design/chatbi-prototype-spec-2026-07-03.md`

## 1. 预览目标

本预览先让产品确认 ChatBI 的页面结构、信息密度和交互方向。它不是正式前端实现，也没有接真实后端。

预览重点：

1. 复用速赢 AI 现有新 UI 工作台风格。
2. 复用原 ChatBI 的聊天、历史、Markdown、反馈和流式节点交互。
3. 复用原 Java/RuoYi 后端中的会话、历史、智能体、SSE 事件和反馈概念。
4. 展示产业链、证据链、模型解释、报告生成、节点级模型配置如何进入 ChatBI。

## 2. 复用来源

### 2.1 现有前端设计

| 来源 | 本预览复用内容 |
|---|---|
| `docs/design/new front/` | 左侧导航、顶部行情状态栏、模块页签、深色工作台、卡片和表格密度 |
| `docs/design/new front/design-spec.md` | 高密度、交易终端式布局、8px 圆角、状态留在界面中 |
| `docs/design/new front/supply-chain.html` | 产业链、证据链、节点详情和右侧信息面板的表达方式 |

### 2.2 原 ChatBI 前端

| 原文件 | 本预览复用内容 |
|---|---|
| `ai/index.vue` | 热门问题、首页入口、快捷提问 |
| `ai/module/module1.vue` | 聊天主界面、输入框、停止生成、流式节点 |
| `ai/module/Markdown.vue` | 回答正文区域和后续 Markdown/artifact 渲染入口 |
| `ai/module/componentsHistory.vue` | 历史会话入口和会话列表 |
| `ai/module/feedback.vue` | 赞/踩和意见反馈入口 |
| `ai/module/feedView.vue` | 反馈展示基础 |

### 2.3 原 Java 后端

| 原模块 | 本预览复用概念 |
|---|---|
| `GacDifyAIController` | 兼容原流式入口，后续内部改为 ChatBI Orchestrator |
| `AiHistoryController` | 历史会话查询 |
| `AiAgentTypeDifyController` | 智能体配置，后续改为 ChatBI Agent 和节点级模型配置 |
| `AiHistoryEntity` | 会话、问题、答案、节点记录 |
| `AiHistoryMapper.xml` | 会话历史持久化思路 |
| `GacDifyData` | 前端兼容 SSE 事件结构 |
| `AiFeedbackRequestVO` | 用户反馈请求 |
| RuoYi 基础能力 | 权限、审计、AjaxResult、BaseController 风格 |

## 3. 预览页面

### 3.1 问答工作台

展示内容：

- 热门问题
- 历史会话
- 用户问题
- 流式节点
- 回答正文
- 候选公司表格
- 停止生成、导出报告、反馈按钮

对应正式能力：

| 预览区域 | 后续接口或能力 |
|---|---|
| 热门问题 | `/api/v1/chatbi/agents`、热门问题配置 |
| 历史会话 | `/api/v1/chatbi/sessions` |
| 流式回答 | `/api/v1/chatbi/messages/stream` |
| 候选表格 | `supply_chain_candidate_ranking` 工具 |
| 反馈 | `/api/v1/chatbi/feedback` |

### 3.2 证据链分析

展示内容：

- 中际旭创标签级证据
- L1-L8 层级
- 研发/商用阶段
- 三高标签
- 证据来源、日期、置信度

对应正式能力：

| 预览区域 | 后续接口或能力 |
|---|---|
| 公司证据链 | `company_evidence_chain` 工具 |
| L1-L8 层级 | 产业链 BOM 和业务标签库 |
| 三高证据 | 标签级三高结构化数据 |

### 3.3 模型解释

展示内容：

- 无票原因漏斗
- 每层过滤数量
- 失败原因
- 产业链、三高、交易信号共振解释

对应正式能力：

| 预览区域 | 后续接口或能力 |
|---|---|
| 无票原因 | `model_no_pick_diagnosis` 工具 |
| 共振解释 | `model_resonance` 工具 |
| 个股解释 | 选股/选债模型诊断服务 |

### 3.4 报告生成

展示内容：

- 报告模板列表
- 报告正文预览
- 标的、模型、导出格式
- Word、Markdown、Excel 按钮

对应正式能力：

| 预览区域 | 后续接口或能力 |
|---|---|
| 模板列表 | `/api/v1/chatbi/report-templates` |
| 报告预览 | `report_generation` 节点模型 |
| 报告导出 | `/api/v1/chatbi/reports/export` |
| 渲染记录 | `chatbi_render_logs` |

### 3.5 配置中心

展示内容：

- 节点级模型配置
- 主模型、fallback 模型、提示词版本
- 提示词版本状态
- 报告模板版本状态

对应正式能力：

| 预览区域 | 后续接口或能力 |
|---|---|
| 节点级模型配置 | `/api/v1/chatbi/agents/{id}/model-bindings` |
| 模型供应商 | `/api/v1/chatbi/model-providers` |
| 提示词版本 | `/api/v1/chatbi/prompts` |
| 报告模板版本 | `/api/v1/chatbi/report-templates` |

## 4. Mock 数据说明

`mock-data.json` 覆盖以下场景：

| 场景 | 用途 |
|---|---|
| `hot_questions` | 首页和快捷提问 |
| `chat_flow` | 流式节点过程 |
| `candidates` | AI 算力候选公司表格 |
| `evidence` | 中际旭创 L8 证据链 |
| `model_bindings` | 节点级模型配置 |
| `report_template` | 报告模板预览 |

当前 mock 数据只用于原型确认，不代表实时行情、真实财务、真实公告或真实研报结果。

## 5. 交互说明

当前 `index.html` 支持：

- 顶部模块页签切换。
- 问答工作台、证据链、模型解释、报告生成、配置中心五个视图切换。
- 表格横向滚动。
- 移动端隐藏左侧导航。
- 移动端单列布局。
- 移动端聊天输入区贴底显示。

当前暂不支持：

- 真实 SSE 流。
- 真实接口请求。
- 真实报告文件下载。
- 真实提示词发布。
- 真实模型连通性测试。

这些能力在设计验收完成后进入工程实施。

## 6. 移动端规则

移动端宽度按 390px 设计检查：

| 项目 | 规则 |
|---|---|
| 左侧导航 | 隐藏 |
| 顶部行情条 | 横向滚动 |
| 模块页签 | 横向滚动 |
| 页面主体 | 单列布局 |
| 表格 | 外层横向滚动 |
| 聊天输入区 | 贴近底部，不遮挡正文 |
| 配置表单 | 单列展示，不横向溢出 |

## 7. 后续接真实接口边界

后续工程实现必须遵守：

1. 前端优先复用原 Vue 文件，不推倒重写。
2. 后端优先复用原 Java/RuoYi Controller、Entity、Mapper、VO。
3. Dify 调用链替换为 ChatBI Orchestrator。
4. 兼容原前端事件字段，同时新增标准 artifact payload。
5. 投研事实数据只通过 K线大模型工具接口获取。
6. 模型调用统一走 LLM Gateway。
7. 所有模型、提示词、报告模板调用都记录版本和节点。

## 8. Gate B 验收清单

- [x] `index.html` 已创建。
- [x] `mock-data.json` 已创建。
- [x] 预览覆盖五个核心页签。
- [x] 预览说明写清复用来源。
- [x] 预览说明写清 mock 和真实接口边界。
- [ ] 完成桌面预览检查。
- [ ] 完成 390px 移动端预览检查。
- [ ] 实施计划同步 Design Gate B 状态。
