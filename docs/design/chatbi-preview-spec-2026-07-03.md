# ChatBI 移动端静态预览说明

- **日期**: 2026-07-03
- **状态**: Draft
- **阶段**: Design Gate B
- **预览文件**: `docs/design/chatbi-preview/index.html`
- **UAT 联调文件**: `chatbi-workspace/frontend-vue/chatbi-mobile-uat.html`
- **Mock 数据**: `docs/design/chatbi-preview/mock-data.json`
- **产品定位**: 独立 ChatBI 移动端应用，未来挂载飞书、钉钉、企业微信，也可作为独立 H5 使用

## 1. 关键纠偏

本项目不是把 ChatBI 做成现有 PC 端工作台里的一个页面。目标是做一个独立 ChatBI 应用，第一优先级是移动端体验。移动端 ChatBI 必须独立建设，不修改现有 PC 端页面、路由、左侧导航、业务组件和既有接口契约。

根据本次参考图，预览继续从“功能页签”收敛为“单一 AI 对话入口”。核心不是把所有能力摊在首屏；首页中间不再放大提问框，只保留欢迎语、热门关键词和近期热门话题，底部输入框作为唯一提问入口。用户在底部选择“快速回答”或“深度思考”。

因此本次预览采用：

```text
移动端独立应用壳
顶部菜单 / 新对话
左侧历史抽屉
欢迎语
热门关键词
近期热门话题
底部输入框
快速回答 / 深度思考
AI 会话页
用户问题气泡
回答卡片
可展开思考过程
结构化表格结果
```

PC 端只作为可能的独立管理入口或外链入口，不是第一版主体验；任何 PC 入口都必须单独确认，不能改变原 PC 页面布局、菜单结构和数据逻辑。

## 2. 复用原则

### 2.1 前端代码复用

第一版实现时优先复用 `chatBI/ai 前端.zip`：

| 原文件 | 复用方式 |
|---|---|
| `ai/index.vue` | 复用首页入口、热门问题、快捷提问 |
| `ai/module/module1.vue` | 复用聊天主界面、输入框、停止生成、流式节点 |
| `ai/module/Markdown.vue` | 复用回答渲染基础，扩展 artifact 表格、证据卡片、报告预览 |
| `ai/module/componentsHistory.vue` | 复用历史会话入口 |
| `ai/module/feedback.vue` | 复用赞/踩和意见反馈 |
| `ai/module/feedView.vue` | 复用反馈展示基础 |

不做推倒重写。新增能力以扩展组件和适配接口为主。

### 2.2 后端代码复用

第一版实现时优先复用 `chatBI/AI 后端.zip`：

| 原模块 | 复用方式 |
|---|---|
| `GacDifyAIController` | 保留兼容流式入口，内部改为 ChatBI Orchestrator |
| `AiHistoryController` | 复用历史会话查询 |
| `AiAgentTypeDifyController` | 改造成 ChatBI 智能体和节点级模型配置 |
| `AiHistoryEntity` | 复用会话、问题、答案、节点记录基础字段 |
| `AiHistoryMapper.xml` | 复用会话历史持久化思路 |
| `GacDifyData` | 复用前端兼容 SSE 事件结构 |
| `AiFeedbackRequestVO` | 复用反馈请求结构 |
| RuoYi 基础能力 | 复用权限、审计、`AjaxResult`、`BaseController` |

必须替换的是 Dify 调用链、Dify key、workflow path、明文配置和内部地址。

### 2.3 视觉复用

`docs/design/new front/` 只作为视觉参考，提供色彩、信息密度、状态标签、卡片和表格的风格参考。它不是本项目的主壳。

## 3. 移动端页面结构

### 3.1 顶部应用栏

展示：

- 菜单按钮：打开历史会话抽屉
- 新对话按钮
- 状态栏时间、电量和网络信息

### 3.2 首页提问入口

首页只保留用户最需要的内容，不再展示底部五页签，不展示快速/专家/识图三模式，也不展示中间大提问框：

| 区域 | 作用 |
|---|---|
| 欢迎语 | 明确这是投研数据和模型结果分析助手 |
| 热门关键词 | 帮用户快速理解可问范围 |
| 近期热门话题 | 承接常见问题，点击直接进入会话 |
| 底部输入框 | 唯一输入入口，承载继续提问、快速回答、深度思考、附件和语音 |
| 快速回答 | 直接命中模板化查询，只返回结构化结果，不做大模型分析 |
| 深度思考 | 通过大模型组织证据链、三高、阶段和交易信号，输出详细分析 |
| 左侧抽屉 | 搜索和历史会话 |

### 3.3 AI 会话页

会话页按照参考图逻辑展示：

| 区域 | 作用 |
|---|---|
| 用户气泡 | 展示当前问题 |
| 复制 / 编辑 | 后续用于复用问题和改写问题 |
| 回答头部 | 展示“回答”和“思考过程” |
| 思考过程 | 展示问题识别、知识检索、关键数据检索、数据获取、口径说明、生成完成 |
| 结构化结果 | 优先展示表格和结论，不只输出长文本 |
| 继续追问输入框 | 固定在底部，适合移动端连续追问 |

### 3.4 左侧历史抽屉

左侧抽屉用于承载搜索对话内容、历史会话和个人身份，不在主界面展示多余导航。

## 4. 当前预览覆盖

`index.html` 当前覆盖：

- 移动端独立应用外壳。
- 欢迎语。
- 快速回答 / 深度思考。
- 热门关键词。
- 近期热门话题。
- 底部输入框作为唯一输入入口。
- 左侧历史抽屉。
- AI 会话页。
- 停止生成状态。
- 思考过程展开 / 收起。
- 产业链候选公司表格。
- 结论摘要和后续追问建议。

静态设计预览仍保留在 `docs/design/chatbi-preview/index.html`，用于 UED 回看。真实接口联调页已新增到 `chatbi-workspace/frontend-vue/chatbi-mobile-uat.html`，默认连接：

```text
http://localhost:8088/ds-cockpit-screen/api/v1/chatbi
```

如需切换后端，可在 URL 增加：

```text
?api=http://127.0.0.1:8088/ds-cockpit-screen/api/v1/chatbi
```

## 5. 后续真实接口映射

| 移动端区域 | 后续接口或工具 |
|---|---|
| 热门问题 | `/api/v1/chatbi/agents`、热门问题配置 |
| 历史会话 | `/api/v1/chatbi/sessions` |
| 流式问答 | `/api/v1/chatbi/messages/stream` |
| 候选表格 | `supply_chain_candidate_ranking` |
| 公司证据链 | `company_evidence_chain` |
| 模型解释 | `model_no_pick_diagnosis`、`model_resonance` |
| 报告模板 | `/api/v1/chatbi/report-templates` |
| 报告导出 | `/api/v1/chatbi/reports/export` |
| 节点模型配置 | `/api/v1/chatbi/agents/{id}/model-bindings` |
| 提示词版本 | `/api/v1/chatbi/prompts` |

## 6. 移动端验收重点

| 项目 | 标准 |
|---|---|
| 首屏 | 能看到欢迎语、热门关键词和近期热门话题；中间不出现大提问框 |
| 问答 | 用户问题、回答头、思考过程、结果表格和底部输入框结构清楚 |
| 底部导航 | 不出现底部五页签，页面只保留底部输入区 |
| 回答模式 | 快速回答不展开大模型思考链，深度思考展开思考过程和分析摘要 |
| 历史抽屉 | 菜单按钮可打开历史列表，点击历史可进入会话 |
| 表格 | 横向滚动，不压缩到不可读 |
| 生成中 | 能看到停止按钮 |
| 思考过程 | 能展开和收起，节点顺序与后端编排一致 |
| 企业 WebView | 不依赖 PC 左侧导航，不依赖宽屏布局 |
| PC 端边界 | 现有 PC 页面、路由、导航和业务组件改动为 0 |

## 7. Gate B 状态

- [x] 移动端 `index.html` 已创建。
- [x] `mock-data.json` 已创建。
- [x] 预览说明已明确移动端独立应用定位。
- [x] 预览说明已明确不修改现有 PC 端页面、路由、导航和业务组件。
- [x] 说明已明确前后端代码复用原则。
- [x] 根据参考图重做为“首页提问入口 + AI 会话页 + 思考过程 + 表格结果”的移动端逻辑。
- [x] 根据用户反馈移除中间三模式，保留欢迎语、热门关键词和近期热门话题。
- [x] 根据用户反馈移除中间大提问框，底部输入框作为唯一输入入口。
- [x] 明确快速回答走模板化查询，深度思考走大模型详细分析。
- [x] 完成移动端 390px 预览检查。
- [x] 实施计划同步 Design Gate B 状态。

检查证据：

```text
预览地址：http://127.0.0.1:8765/
首页截图：output/playwright/chatbi-preview/mobile-ai-home-no-mid-input-390.png
历史抽屉截图：output/playwright/chatbi-preview/mobile-ai-drawer-390.png
快速回答截图：output/playwright/chatbi-preview/mobile-ai-no-mid-input-quick-390.png
深度思考截图：output/playwright/chatbi-preview/mobile-ai-no-mid-input-deep-390.png
附件面板截图：output/playwright/chatbi-preview/mobile-ai-attachments-390.png
检查结果：页面 200，底部五页签已移除，中间三模式和中间大提问框已移除，首页保留热门关键词和近期热门话题；快速回答不展开思考链，深度思考展开思考过程。
```
