# ChatBI 原始源码包审计

**日期**: 2026-07-03  
**范围**: `chatBI/ai 前端.zip`、`chatBI/AI 后端.zip`  
**结论**: 前端源码包可作为移动端交互壳复用；后端源码包只能在清洗后复用，不能把压缩包原样展开进工程仓库。

## 1. 审计方法

初次审计只读取压缩包目录和配置命中情况，没有把源码包复制到正式工程目录，也没有修改现有 PC 端代码。进入实施后，已按本报告要求把源码清洗复制到 `chatbi-workspace`。

执行检查：

```bash
unzip -l "chatBI/ai 前端.zip"
unzip -Z1 "chatBI/AI 后端.zip"
unzip -p "chatBI/AI 后端.zip" "<application*.yml>" | rg -n -i "password|secret|jdbc:|url:|token|key"
rg -n -i "jdbc:mysql|10\\.30\\.|123Ruoyi|ragflow-[A-Za-z0-9]|app-[A-Za-z0-9]|ft4o|eIj#" chatbi-workspace/backend-java chatbi-workspace/frontend-vue
```

## 2. 源码来源

| 来源 | 类型 | 审计结论 |
| --- | --- | --- |
| `chatBI/ai 前端.zip` | Vue 移动端 ChatBI 前端 | 文件少、边界清晰，可进入复用清单 |
| `chatBI/AI 后端.zip` | Java/Spring Boot/RuoYi 后端 | 包含源码、构建产物、Git 历史和敏感配置，必须清洗后复用 |

## 3. 前端包结果

前端包包含 10 个条目，核心文件如下：

| 文件 | 处理建议 |
| --- | --- |
| `ai/index.vue` | 保留，作为首页、热门关键词、热门话题的信息结构参考 |
| `ai/module/module1.vue` | 保留，作为聊天流、停止生成、回答区和输入区的复用基础 |
| `ai/module/Markdown.vue` | 保留，扩展为投研 Markdown、表格、证据卡片和报告渲染 |
| `ai/module/componentsHistory.vue` | 保留，作为会话历史抽屉基础 |
| `ai/module/feedback.vue` | 保留，作为回答反馈基础 |
| `ai/module/feedView.vue` | 保留，作为反馈记录或意见展示基础 |
| `ai/module/module1 copy.vue`、`module1 copy 2.vue` | 不进入正式工程，避免重复实现和分叉逻辑 |

未发现前端包带 `node_modules`、构建产物或明显敏感配置。

## 4. 后端包结果

后端包可识别到 437 个 Java/XML/POM 源码相关文件，但同时包含以下不应进入新工程的内容：

| 类型 | 数量 | 处理要求 |
| --- | ---: | --- |
| `.git/` 目录条目 | 3680 | 全部剔除 |
| `target/` 构建产物条目 | 680 | 全部剔除 |
| `.class` 文件 | 419 | 全部剔除 |
| `.idea/` IDE 文件 | 12 | 全部剔除 |
| `application*.yml` 配置文件 | 8 | 不能原样复用，改为环境变量和本项目配置模板 |

可进入复用评估的后端文件包括：

| 文件或模块 | 处理建议 |
| --- | --- |
| `GacDifyAIController.java` | 保留路由和 SSE 出口思路，内部替换为 ChatBI Orchestrator |
| `AiHistoryController.java` | 保留历史会话查询思路 |
| `AiAgentTypeDifyController.java` | 改造成智能体、节点模型、提示词和模板配置入口 |
| `AiHistoryEntity.java` | 扩展为会话、消息、节点过程和证据引用模型 |
| `AiHistoryMapper.java` / `AiHistoryMapper.xml` | 扩展字段后复用 |
| `GacDifyData.java` | 改造成标准 SSE 事件数据对象 |
| `GacRAGFlowAIRequestVO.java` | 改造成 ChatBI 请求对象 |
| `AiFeedbackRequestVO.java` | 保留反馈请求结构 |
| `BaseController.java`、`AjaxResult.java` | 保留 RuoYi 风格返回和基础 Controller 能力 |
| RuoYi 权限、审计、登录基础能力 | 复用设计思路，实际接入需按本项目登录态重做 |

## 5. 敏感配置发现

后端配置文件中命中了以下敏感类别。文档只记录类别，不记录明文值。

| 敏感类别 | 命中位置 | 风险 |
| --- | --- | --- |
| 内网 MySQL JDBC 地址 | `application-gac-local.yml`、`application-gac-test.yml`、`application-gac-prod.yml` 及 `target/classes` 副本 | 泄露内部网络和数据库拓扑 |
| 数据库密码 | 同上 | 如果仍有效，会带来数据库访问风险 |
| 默认登录密码 | `application-gac-*.yml` 及 `target/classes` 副本 | 默认凭据不能进入新系统 |
| Token/JWT secret 类配置 | `application.yml` 及 `target/classes` 副本 | 会话签名密钥不能复用 |
| 内部平台 URL | `application-gac-*.yml` 及 `target/classes` 副本 | 泄露内部系统地址 |

需要轮换或替换的类别：

- 数据库账号和密码。
- 应用默认登录口令。
- Token/JWT secret。
- 与 Dify、RAGFlow 或旧平台相关的访问密钥。
- 内部平台 URL 和环境配置。

## 6. 保留文件清单

允许进入后续开发的文件类别：

- 前端 `ai/*.vue` 和 `ai/module/*.vue` 中非重复组件。
- 后端 `src/main/java` 下的 Controller、Entity、VO、Mapper、Service 接口和可复用工具类。
- 后端 `src/main/resources/mapper` 下的 XML Mapper。
- POM 依赖声明，需重新审查版本和许可证。

## 7. 剔除文件清单

禁止进入后续开发的文件类别：

- `.git/`。
- `.idea/`。
- `target/`。
- `*.class`。
- 原始 `application-gac-*.yml`、`application.yml` 中的环境配置和密钥值。
- `module1 copy.vue`、`module1 copy 2.vue` 等重复副本。
- 所有 Dify/RAGFlow 原始密钥、旧平台内网地址和旧数据库连接。

## 8. 实施准入结论

是否允许进入后续开发：**是，但必须满足以下条件**。

1. 工程实施时只能做“清洗后复制”，不能把压缩包原样解压进仓库。
2. 新工程目录不得包含 `.git`、`target`、`.idea`、`.class`。
3. 旧配置文件中的密钥、密码、内网 URL 不得落库、不得提交、不得进入前端包。
4. 所有环境差异统一用 `.env`、配置模板或部署平台密钥管理。
5. Dify 调用链必须替换为本项目 `ChatBI Orchestrator` 和受控投研工具。
6. PC 端 React/Vite 工作台不作为本阶段实现目标，不改现有 PC 路由、导航和业务组件。

## 9. 实际清洗结果

已创建清洗后的独立工作区：

| 目录 | 状态 |
| --- | --- |
| `chatbi-workspace/raw/frontend` | 原始前端包隔离解压目录 |
| `chatbi-workspace/raw/backend` | 原始后端包隔离解压目录 |
| `chatbi-workspace/frontend-vue` | 清洗后的前端复用目录 |
| `chatbi-workspace/backend-java` | 清洗后的后端复用目录 |

已删除或排除：

- `.git`、`.idea`、`target`、`*.class`。
- `application-gac-local.yml`、`application-gac-test.yml`、`application-gac-prod.yml` 中的旧环境配置。
- 前端重复副本 `module1 copy.vue`、`module1 copy 2.vue`。
- 旧部署脚本。
- Pinpoint Agent。
- SQL 初始化脚本。
- 后端测试目录中包含的旧 AI 网关 key 和旧内网地址。

已替换：

- `chatbi-workspace/backend-java/cockpit-screen-admin/src/main/resources/application.yml` 已改为环境变量配置。
- `chatbi-workspace/backend-java/.env.example` 已创建，所有密钥为空值。

复扫结论：

- 未发现旧数据库连接、旧数据库密码、旧 Druid 口令、RAGFlow/Dify 明文 key。
- `app-container` 是 RuoYi 模板里的普通 CSS 类名误报，不属于密钥。
- PC 端页面、路由、菜单、布局和业务组件没有被修改。
