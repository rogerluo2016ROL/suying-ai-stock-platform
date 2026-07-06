# ChatBI 数据模型设计

- **日期**: 2026-07-03
- **阶段**: Design Gate E
- **范围**: ChatBI 自有交互库和配置库
- **原则**: 不复制 K线大模型事实数据；只保存会话、事件、配置、审计、引用和导出记录

## 1. 数据分层

| 层 | 保存内容 | 不保存内容 |
|---|---|---|
| ChatBI 交互层 | 会话、消息、SSE 事件、反馈、工具调用日志 | 行情明细、财报原表、证据正文全集 |
| ChatBI 配置层 | 智能体、工具白名单、模型配置、提示词、报告模板 | 模型供应商明文 key |
| ChatBI 审计层 | 用户行为、工具调用、模型调用、导出记录 | 用户自由 SQL |
| K线事实层 | 产业链、证据链、行情、模型结果 | 由现有 K线大模型维护 |

## 2. 表设计

### 2.1 `chatbi_sessions`

| 字段 | 类型 | 说明 |
|---|---|---|
| `session_id` | varchar(64) PK | 会话 ID |
| `user_id` | varchar(64) | 内部用户 ID |
| `platform` | varchar(32) | h5/feishu/dingtalk/wecom |
| `agent_id` | varchar(64) | 智能体 |
| `title` | varchar(255) | 会话标题 |
| `status` | varchar(32) | active/deleted |
| `created_at` | timestamp | 创建时间 |
| `updated_at` | timestamp | 更新时间 |

索引：

```text
idx_chatbi_sessions_user_updated(user_id, updated_at desc)
idx_chatbi_sessions_agent(agent_id)
```

保留策略：默认 2 年，可按用户删除。

### 2.2 `chatbi_messages`

| 字段 | 类型 | 说明 |
|---|---|---|
| `message_id` | varchar(64) PK | 消息 ID |
| `session_id` | varchar(64) | 会话 ID |
| `user_id` | varchar(64) | 用户 ID |
| `question` | text | 用户问题 |
| `answer` | text | 最终答案 |
| `answer_mode` | varchar(16) | quick/deep |
| `status` | varchar(32) | prepared/running/done/failed/stopped |
| `intent` | varchar(64) | 识别意图 |
| `data_date` | date | 主要数据日期 |
| `elapsed_ms` | int | 总耗时 |
| `error_code` | varchar(64) | 错误码 |
| `created_at` | timestamp | 创建时间 |

索引：

```text
idx_chatbi_messages_session_created(session_id, created_at)
idx_chatbi_messages_user_created(user_id, created_at desc)
```

### 2.3 `chatbi_message_events`

| 字段 | 类型 | 说明 |
|---|---|---|
| `event_id` | varchar(64) PK | 事件 ID |
| `message_id` | varchar(64) | 消息 ID |
| `event_type` | varchar(64) | node_started/tool_finished/message_delta 等 |
| `node_type` | varchar(64) | 节点类型 |
| `payload_json` | json/jsonb | 事件载荷 |
| `elapsed_ms` | int | 节点耗时 |
| `created_at` | timestamp | 创建时间 |

索引：

```text
idx_chatbi_events_message_created(message_id, created_at)
idx_chatbi_events_type(event_type)
```

### 2.4 `chatbi_agents`

| 字段 | 类型 | 说明 |
|---|---|---|
| `agent_id` | varchar(64) PK | 智能体 ID |
| `name` | varchar(128) | 名称 |
| `agent_type` | varchar(64) | supply_chain/model/report/general |
| `default_answer_mode` | varchar(16) | quick/deep |
| `status` | varchar(32) | draft/published/archived |
| `created_by` | varchar(64) | 创建人 |
| `updated_at` | timestamp | 更新时间 |

唯一约束：

```text
uk_chatbi_agents_name(name)
```

### 2.5 `chatbi_agent_model_bindings`

| 字段 | 类型 | 说明 |
|---|---|---|
| `binding_id` | varchar(64) PK | 绑定 ID |
| `agent_id` | varchar(64) | 智能体 |
| `node_type` | varchar(64) | intent_recognition/query_planning/evidence_extraction/answer_generation/report_generation |
| `primary_model_id` | varchar(64) | 主模型 |
| `fallback_model_ids_json` | json/jsonb | fallback 列表 |
| `prompt_version_id` | varchar(128) | 提示词版本 |
| `status` | varchar(32) | enabled/disabled |

唯一约束：

```text
uk_agent_node(agent_id, node_type)
```

### 2.6 `chatbi_agent_tools`

| 字段 | 类型 | 说明 |
|---|---|---|
| `agent_id` | varchar(64) | 智能体 |
| `tool_id` | varchar(64) | 工具 |
| `enabled` | boolean | 是否启用 |
| `max_rows` | int | 最大返回行数 |
| `timeout_ms` | int | 超时 |

唯一约束：

```text
uk_agent_tool(agent_id, tool_id)
```

### 2.7 `chatbi_tool_calls`

| 字段 | 类型 | 说明 |
|---|---|---|
| `call_id` | varchar(64) PK | 工具调用 ID |
| `message_id` | varchar(64) | 消息 ID |
| `tool_id` | varchar(64) | 工具 |
| `params_hash` | varchar(64) | 参数摘要 |
| `params_redacted_json` | json/jsonb | 脱敏参数 |
| `status` | varchar(32) | ok/empty/failed/timeout |
| `data_date` | date | 数据日期 |
| `elapsed_ms` | int | 耗时 |
| `error_code` | varchar(64) | 错误码 |

索引：

```text
idx_tool_calls_message(message_id)
idx_tool_calls_tool_created(tool_id, created_at desc)
```

### 2.8 `chatbi_feedback`

| 字段 | 类型 | 说明 |
|---|---|---|
| `feedback_id` | varchar(64) PK | 反馈 ID |
| `message_id` | varchar(64) | 消息 ID |
| `user_id` | varchar(64) | 用户 |
| `rating` | varchar(16) | up/down |
| `reason` | varchar(64) | 原因 |
| `comment` | text | 文本反馈 |
| `created_at` | timestamp | 时间 |

### 2.9 `chatbi_model_providers`

| 字段 | 类型 | 说明 |
|---|---|---|
| `provider_id` | varchar(64) PK | 供应商 |
| `provider_type` | varchar(64) | openai_compatible/deepseek/glm |
| `name` | varchar(128) | 名称 |
| `base_url` | varchar(255) | 地址 |
| `api_key_ref` | varchar(255) | 密钥引用 |
| `status` | varchar(32) | enabled/disabled |

敏感性：`api_key_ref` 不是明文 key，但仍按敏感字段处理。

### 2.10 `chatbi_model_versions`

| 字段 | 类型 | 说明 |
|---|---|---|
| `model_id` | varchar(64) PK | 模型 ID |
| `provider_id` | varchar(64) | 供应商 |
| `model_name` | varchar(128) | 模型名 |
| `context_window` | int | 上下文长度 |
| `status` | varchar(32) | enabled/disabled |
| `cost_rule_json` | json/jsonb | 成本规则 |

### 2.11 `chatbi_prompt_versions`

| 字段 | 类型 | 说明 |
|---|---|---|
| `prompt_version_id` | varchar(128) PK | prompt_id:version |
| `prompt_id` | varchar(64) | 提示词 ID |
| `version` | varchar(32) | 版本 |
| `node_type` | varchar(64) | 节点 |
| `status` | varchar(32) | draft/published/archived |
| `system_prompt` | text | 系统提示词 |
| `task_prompt` | text | 任务提示词 |
| `created_by` | varchar(64) | 创建人 |

唯一约束：

```text
uk_prompt_version(prompt_id, version)
```

### 2.12 `chatbi_report_templates`

| 字段 | 类型 | 说明 |
|---|---|---|
| `template_id` | varchar(64) PK | 模板 ID |
| `name` | varchar(128) | 模板名称 |
| `template_type` | varchar(32) | company/model/chain |
| `status` | varchar(32) | draft/published/archived |

### 2.13 `chatbi_report_template_versions`

| 字段 | 类型 | 说明 |
|---|---|---|
| `template_version_id` | varchar(128) PK | template_id:version |
| `template_id` | varchar(64) | 模板 ID |
| `version` | varchar(32) | 版本 |
| `sections_json` | json/jsonb | 章节结构 |
| `required_data_json` | json/jsonb | 必需数据 |
| `status` | varchar(32) | draft/published/archived |

### 2.14 `chatbi_render_logs`

| 字段 | 类型 | 说明 |
|---|---|---|
| `render_id` | varchar(64) PK | 渲染 ID |
| `message_id` | varchar(64) | 消息 |
| `template_version_id` | varchar(128) | 模板版本 |
| `format` | varchar(16) | md/docx/xlsx |
| `file_ref` | varchar(255) | 文件引用 |
| `status` | varchar(32) | running/done/failed |

### 2.15 `chatbi_platform_bindings`

| 字段 | 类型 | 说明 |
|---|---|---|
| `binding_id` | varchar(64) PK | 绑定 ID |
| `platform` | varchar(32) | feishu/dingtalk/wecom/h5 |
| `platform_user_id` | varchar(128) | 平台用户 |
| `tenant_id` | varchar(128) | 租户 |
| `internal_user_id` | varchar(64) | 内部用户 |

唯一约束：

```text
uk_platform_user(platform, platform_user_id)
```

### 2.16 `chatbi_audit_logs`

| 字段 | 类型 | 说明 |
|---|---|---|
| `audit_id` | varchar(64) PK | 审计 ID |
| `actor_id` | varchar(64) | 操作人 |
| `action` | varchar(64) | 操作 |
| `resource_type` | varchar(64) | 资源类型 |
| `resource_id` | varchar(128) | 资源 ID |
| `request_id` | varchar(64) | 请求 ID |
| `status` | varchar(32) | ok/failed |
| `ip` | varchar(64) | IP |
| `created_at` | timestamp | 时间 |

## 3. 数据保留策略

| 数据 | 保留期 | 说明 |
|---|---:|---|
| 会话和消息 | 2 年 | 支持用户删除 |
| SSE 事件 | 180 天 | 可压缩归档 |
| 工具调用日志 | 1 年 | 支持审计和问题复盘 |
| 模型调用成本日志 | 1 年 | 支持成本分析 |
| 审计日志 | 3 年 | 安全审计 |
| 导出文件 | 30 天 | 过期清理，只保留 render log |

## 4. 敏感字段

| 字段 | 处理 |
|---|---|
| `api_key_ref` | 只保存密钥引用，不保存明文 |
| `params_redacted_json` | 参数脱敏后保存 |
| `question` | 属于用户内容，按会话数据保护 |
| `answer` | 属于生成内容，按会话数据保护 |
| `file_ref` | 不暴露本地路径，使用下载授权 |

