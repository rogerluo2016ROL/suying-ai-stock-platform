# ChatBI 安全与可观测性设计

- **日期**: 2026-07-03
- **阶段**: Design Gate E
- **目标**: 密钥安全、权限边界、工具白名单、日志审计、token 成本、错误告警

## 1. 安全原则

```text
模型不能直接访问数据库。
用户不能执行 SQL。
Java 后端不能直接读写 K线事实表。
所有事实数据访问必须经过工具白名单。
模型供应商 key 不进入前端、不进入日志、不明文入库。
投资回答必须展示数据日期或证据来源。
```

## 2. 密钥治理

| 对象 | 策略 |
|---|---|
| 模型 API Key | 使用 `api_key_ref` 引用 KMS 或环境变量 |
| 数据库密码 | 环境变量注入 |
| 平台应用密钥 | 环境变量或密钥管理 |
| 原 Dify key | 删除，不迁移 |

禁止：

```text
YAML 明文 key
日志打印 Authorization
接口返回 api_key
把原包内部地址和账号提交到新工程
```

## 3. 鉴权与权限

接口权限：

| 权限 | 能力 |
|---|---|
| `chatbi.basic` | 会话、问答、历史、反馈 |
| `chatbi.supply_chain` | 产业链和公司证据链 |
| `chatbi.stock_model` | 选股模型 |
| `chatbi.bond_model` | 选债模型 |
| `chatbi.report_export` | 报告导出 |
| `chatbi.admin` | 智能体、提示词、模板管理 |
| `chatbi.model_config` | 模型供应商和节点模型配置 |

权限校验顺序：

```text
平台身份 -> internal_user_id -> roles -> permissions -> agent tools -> tool params
```

## 4. 工具白名单

每个工具必须配置：

```text
tool_id
required_permission
enabled
max_rows
timeout_ms
allow_export
allowed_params
```

拦截条件：

```text
工具未启用
用户权限不足
参数不在白名单
返回行数超过上限
问题包含执行 SQL 或绕过权限意图
```

## 5. 日志字段

### 5.1 消息日志

```text
request_id
session_id
message_id
user_id
platform
agent_id
answer_mode
intent
status
elapsed_ms
error_code
data_date
```

### 5.2 工具调用日志

```text
call_id
message_id
tool_id
params_hash
params_redacted_json
status
elapsed_ms
data_date
empty_reason
error_code
```

### 5.3 模型调用日志

```text
llm_call_id
message_id
node_type
provider_id
model_id
prompt_version_id
fallback_used
input_tokens
output_tokens
cost_estimate
elapsed_ms
status
error_code
```

### 5.4 报告渲染日志

```text
render_id
message_id
template_version_id
format
status
file_ref
elapsed_ms
error_code
```

## 6. 告警

| 告警 | 阈值 |
|---|---|
| SSE 首包超时 | P95 > 3 秒 |
| 工具超时 | 5 分钟内超过 5 次 |
| LLM fallback | 10 分钟内超过 10 次 |
| 权限拒绝异常 | 单用户 10 分钟内超过 10 次 |
| token 成本异常 | 单日超过预算 80% |
| 导出失败 | 10 分钟内超过 3 次 |

## 7. 成本统计

统计维度：

```text
provider_id
model_id
node_type
agent_id
answer_mode
date
```

快速回答默认不调用 LLM 生成分析正文，成本应显著低于深度思考。成本看板要区分快速回答和深度思考。

## 8. 审计日志

必须审计：

```text
模型供应商新增/修改/停用
提示词发布/回滚
报告模板发布/回滚
工具白名单修改
权限修改
报告导出
越权或 SQL 请求拦截
```

审计日志保留 3 年。

## 9. 数据安全边界

ChatBI 会话库可以保存用户问题和答案，但不能成为事实数据副本库。

| 数据 | 处理 |
|---|---|
| 行情明细 | 不复制，只引用工具结果 |
| 公告/研报原文 | 不复制全集，只保存 evidence_id、摘要、引用片段 |
| 用户问题 | 保存，支持用户删除 |
| 模型答案 | 保存，支持用户删除 |
| 导出文件 | 短期保存，过期清理 |

