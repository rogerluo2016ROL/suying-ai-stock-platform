# ChatBI 密钥轮换记录

**日期**: 2026-07-03  
**范围**: `chatBI/AI 后端.zip` 清洗到 `chatbi-workspace/backend-java` 的过程。  
**结论**: 原始包中发现的旧数据库、Token、平台和 AI 网关配置不得复用；清洗后的工作区已改为环境变量配置。

## 1. 发现位置

| 发现位置 | 密钥类型 | 当前处理 |
| --- | --- | --- |
| 原始包 `application-gac-local.yml` | UAT 数据库地址、账号、密码、Druid 登录口令、内部平台 URL | 未复制到清洗后工作区 |
| 原始包 `application-gac-test.yml` | 测试环境数据库地址、账号、密码、Druid 登录口令、内部平台 URL | 未复制到清洗后工作区 |
| 原始包 `application-gac-prod.yml` | 生产环境数据库地址、账号、密码、Druid 登录口令、内部平台 URL | 未复制到清洗后工作区 |
| 原始包 `application.yml` | Token/JWT secret 默认值 | 已替换为 `${CHATBI_TOKEN_SECRET}` |
| 原始包 `target/classes/application*.yml` | 上述配置的构建产物副本 | 未复制到清洗后工作区 |
| 原始包测试类和注释 | RAGFlow/Dify 示例 key、`Bearer` 示例、旧内网地址 | 测试目录删除，注释 key 删除 |
| 原始部署脚本 | 旧服务器路径和密码读取脚本 | 已从清洗后工作区删除 |

## 2. 需要轮换的密钥类别

| 密钥类别 | 是否仍有效 | 轮换责任人 | 轮换日期 | 验证方式 |
| --- | --- | --- | --- | --- |
| 旧 UAT 数据库账号和密码 | 待运维确认 | ops / DBA | 待定 | 数据库侧确认旧账号禁用或密码已更新 |
| 旧生产数据库账号和密码 | 待运维确认 | ops / DBA | 待定 | 数据库侧确认旧账号禁用或密码已更新 |
| 旧 Druid 登录口令 | 待运维确认 | ops | 待定 | 旧环境控制台登录验证和配置检查 |
| 旧 Token/JWT secret | 待运维确认 | backend-dev / ops | 待定 | 旧服务 token 签发配置检查 |
| 旧 RAGFlow/Dify agent key | 待运维确认 | ai-agent-dev / ops | 待定 | 旧 AI 网关后台禁用或轮换确认 |
| 旧企业平台对接 secret | 待运维确认 | platform-owner / ops | 待定 | 企业平台后台应用密钥轮换记录 |

## 3. 已完成的清洗动作

- 删除清洗后工作区中的 `.git`、`.idea`、`target`、`*.class`。
- 删除 `application-gac-local.yml`、`application-gac-test.yml`、`application-gac-prod.yml`。
- 重建干净的 `application.yml`，数据库、Token、模型、工具网关和企业平台配置全部走环境变量。
- 新增 `chatbi-workspace/backend-java/.env.example`，只保留空值和本地安全默认值。
- 删除旧部署脚本、Pinpoint Agent、SQL 初始化脚本和测试目录。
- 删除前端重复副本 `module1 copy.vue`、`module1 copy 2.vue`。
- 删除旧 AI 网关 key 注释。

## 4. 当前验证结果

执行：

```bash
rg -n -i "jdbc:mysql|10\\.30\\.|123Ruoyi|ragflow-[A-Za-z0-9]|app-[A-Za-z0-9]|ft4o|eIj#" chatbi-workspace/backend-java chatbi-workspace/frontend-vue
```

结果：未发现旧数据库连接、旧数据库密码、旧 Druid 口令、RAGFlow/Dify 明文 key。`app-container` 属于 RuoYi 模板里的 CSS 类名误报，不是密钥。

补充：`agentKey` 字段名和 `getAgentKey()` 调用仍存在于旧服务代码中。它们不是明文密钥值，但代表旧 Dify/RAGFlow 调用链尚未完成替换。后续 Phase 3 必须把这类字段从运行链路移除，改为模型网关或工具网关的受控凭据引用。

## 5. 后续要求

1. 生产部署前，`CHATBI_DB_PASSWORD`、`CHATBI_TOKEN_SECRET`、`CHATBI_PLATFORM_SECRET` 必须由部署环境注入。
2. 旧包中出现过的数据库账号、平台密钥和 AI 网关 key 需要由对应系统管理员确认是否已轮换。
3. 后续代码评审中，任何新增 `password: '...'`、`Bearer app-...`、`jdbc:mysql://10.`、明文 `agentKey` 都应阻断合入。
