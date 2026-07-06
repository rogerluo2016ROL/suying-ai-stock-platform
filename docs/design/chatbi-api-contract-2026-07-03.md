# ChatBI API 契约

- **日期**: 2026-07-03
- **阶段**: Design Gate D
- **Base Path**: `/api/v1/chatbi`
- **返回格式**: JSON；流式接口使用 SSE

## 1. 通用规范

### 1.1 通用响应

```json
{
  "code": "OK",
  "message": "success",
  "data": {},
  "request_id": "req_20260703_0001"
}
```

### 1.2 通用错误

```json
{
  "code": "CHATBI_PARAM_MISSING",
  "message": "缺少必要参数: company_name",
  "request_id": "req_20260703_0002",
  "details": {
    "field": "company_name"
  }
}
```

### 1.3 通用审计字段

所有写接口和所有工具/模型调用必须记录：

```text
request_id
user_id
platform
session_id
message_id
agent_id
answer_mode
action
resource
elapsed_ms
status
error_code
created_at
```

## 2. 会话接口

### 2.1 创建会话

| 项目 | 内容 |
|---|---|
| method | `POST` |
| path | `/sessions` |
| permission | `chatbi.basic` |

Request:

```json
{
  "agent_id": "supply_chain_research",
  "platform": "h5",
  "title": "AI算力候选公司 Top20"
}
```

Response:

```json
{
  "session_id": "s_001",
  "title": "AI算力候选公司 Top20",
  "created_at": "2026-07-03T20:58:00+08:00"
}
```

### 2.2 历史会话

| 项目 | 内容 |
|---|---|
| method | `GET` |
| path | `/sessions` |
| permission | `chatbi.basic` |

Query:

```text
keyword=
cursor=
limit=20
```

Response:

```json
{
  "items": [
    {
      "session_id": "s_001",
      "title": "AI算力候选公司 Top20",
      "last_message_at": "2026-07-03T20:58:00+08:00"
    }
  ],
  "next_cursor": null
}
```

## 3. 消息接口

### 3.1 消息准备

| 项目 | 内容 |
|---|---|
| method | `POST` |
| path | `/messages/prepare` |
| permission | `chatbi.basic` |

Request:

```json
{
  "session_id": "s_001",
  "agent_id": "supply_chain_research",
  "question": "AI算力候选公司 Top20",
  "answer_mode": "quick",
  "client_context": {
    "platform": "h5",
    "viewport": "390x844"
  }
}
```

Response:

```json
{
  "message_id": "m_001",
  "session_id": "s_001",
  "answer_mode": "quick",
  "status": "prepared"
}
```

### 3.2 消息流

| 项目 | 内容 |
|---|---|
| method | `POST` |
| path | `/messages/stream` |
| permission | `chatbi.basic` |
| content-type | `text/event-stream` |

Request:

```json
{
  "message_id": "m_001",
  "answer_mode": "deep"
}
```

SSE event:

```text
event: node_started
data: {"message_id":"m_001","node_type":"intent_recognition","label":"问题识别"}
```

```text
event: artifact_delta
data: {"artifact_type":"table","title":"候选公司","columns":[...],"rows":[...],"data_date":"2026-07-03"}
```

```text
event: done
data: {"message_id":"m_001","elapsed_ms":37780,"status":"done"}
```

### 3.3 停止生成

| 项目 | 内容 |
|---|---|
| method | `POST` |
| path | `/messages/{message_id}/stop` |
| permission | `chatbi.basic` |

Response:

```json
{
  "message_id": "m_001",
  "status": "stopping"
}
```

## 4. 反馈接口

| 项目 | 内容 |
|---|---|
| method | `POST` |
| path | `/feedback` |
| permission | `chatbi.basic` |

Request:

```json
{
  "message_id": "m_001",
  "rating": "up",
  "reason": "accurate",
  "comment": "证据链清楚"
}
```

## 5. 智能体配置

### 5.1 智能体列表

| 项目 | 内容 |
|---|---|
| method | `GET` |
| path | `/agents` |
| permission | `chatbi.admin` |

Response:

```json
{
  "items": [
    {
      "agent_id": "supply_chain_research",
      "name": "产业链投研助手",
      "status": "published",
      "default_answer_mode": "quick"
    }
  ]
}
```

### 5.2 节点级模型配置

| 项目 | 内容 |
|---|---|
| method | `PUT` |
| path | `/agents/{agent_id}/model-bindings` |
| permission | `chatbi.model_config` |

Request:

```json
{
  "bindings": [
    {
      "node_type": "intent_recognition",
      "primary_model_id": "deepseek-chat",
      "fallback_model_ids": ["glm-5.2"],
      "prompt_version_id": "chatbi_intent_router:v1"
    },
    {
      "node_type": "answer_generation",
      "primary_model_id": "glm-5.2",
      "fallback_model_ids": ["deepseek-chat"],
      "prompt_version_id": "supply_chain_answer:v1"
    }
  ]
}
```

## 6. 模型供应商配置

| 项目 | 内容 |
|---|---|
| method | `POST` |
| path | `/model-providers` |
| permission | `chatbi.model_config` |

Request:

```json
{
  "provider_type": "openai_compatible",
  "name": "DeepSeek",
  "base_url": "https://api.deepseek.com",
  "api_key_ref": "kms://chatbi/deepseek",
  "status": "enabled"
}
```

Response 不返回明文 key。

## 7. 提示词版本

| 项目 | 内容 |
|---|---|
| method | `POST` |
| path | `/prompts` |
| permission | `chatbi.admin` |

Request:

```json
{
  "prompt_id": "supply_chain_answer",
  "version": "v1",
  "status": "draft",
  "node_type": "answer_generation",
  "system_prompt": "你是投研助手...",
  "task_prompt": "基于证据链回答..."
}
```

生产会话只能使用 `published` 版本。

## 8. 报告模板

### 8.1 模板版本

| 项目 | 内容 |
|---|---|
| method | `POST` |
| path | `/report-templates` |
| permission | `chatbi.admin` |

Request:

```json
{
  "template_id": "company_deep_report",
  "version": "v1",
  "status": "draft",
  "sections": ["投资结论", "产业链位置", "三高证据", "风险提示"],
  "required_data": ["company_evidence_chain", "market_snapshot"]
}
```

### 8.2 报告导出

| 项目 | 内容 |
|---|---|
| method | `POST` |
| path | `/reports/export` |
| permission | `chatbi.report_export` |

Request:

```json
{
  "message_id": "m_001",
  "template_version_id": "company_deep_report:v1",
  "format": "docx"
}
```

Response:

```json
{
  "export_id": "r_001",
  "status": "running"
}
```

## 9. 预览接口

| 项目 | 内容 |
|---|---|
| method | `POST` |
| path | `/admin/preview` |
| permission | `chatbi.admin` |

Request:

```json
{
  "agent_id": "supply_chain_research",
  "question": "中际旭创证据链",
  "model_bindings": [],
  "prompt_version_id": "supply_chain_answer:v1",
  "write_history": false
}
```

预览接口不能写入正式会话历史。

## 10. 错误码

| code | HTTP | 说明 |
|---|---:|---|
| `CHATBI_TEMPLATE_NOT_FOUND` | 422 | 快速回答未命中模板 |
| `CHATBI_PARAM_MISSING` | 422 | 参数缺失 |
| `CHATBI_PERMISSION_DENIED` | 403 | 权限不足 |
| `CHATBI_TOOL_TIMEOUT` | 504 | 工具超时 |
| `CHATBI_TOOL_EMPTY` | 200 | 工具返回空状态 |
| `CHATBI_LLM_UNAVAILABLE` | 503 | 模型不可用 |
| `CHATBI_QUERY_BLOCKED` | 403 | 越权查询或 SQL 请求 |

