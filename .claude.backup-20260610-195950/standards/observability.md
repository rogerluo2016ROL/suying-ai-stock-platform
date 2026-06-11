# Observability Baseline

团队通用观测基线，覆盖 **应用运行时** 与 **AI agent 自身运行时** 两个维度。每个项目的具体技术选型由 tech-lead 在项目级 ADR 中固化。

## 应用运行时

### 结构化日志（必须）

- 后端（FastAPI）：使用 `structlog` 或 `loguru`，输出 JSON；关键字段：`ts`、`level`、`request_id`、`user_id`（脱敏）、`event`、`latency_ms`
- 前端：错误边界 + Sentry SDK；不在控制台打 `console.log`（用 `logger` 抽象）
- 严禁日志包含：完整 token / 密码 / 手机号 / 身份证号 / 完整邮箱（参考 `security.md`）

### 链路追踪（推荐）

- 接入 OpenTelemetry SDK；后端 → 前端 traceparent 透传
- 慢请求阈值：HTTP 接口 P95 ≤ 500ms（API），LLM 调用 P95 ≤ 5s（流式响应除外）
- LLM 调用必须记录：`model`、`prompt_tokens`、`completion_tokens`、`total_cost_cny`、`cache_hit_ratio`

### 指标（推荐）

- HTTP：QPS / 错误率 / P50/P95/P99 延迟
- DB：连接池占用、慢查询计数（>200ms）
- LLM：调用次数 / 失败率 / 平均 token 消耗 / 日累计成本

## AI Agent 运行时（Claude Code 自身）

### 内置 `/usage`

需要查会话 token / cost / cache hit 时跑 Claude Code 内置 `/usage`（不维护项目级 cost log；release retro §3 摘录该输出，见 `agf-running-release-retro` skill）。

### OpenTelemetry 导出（可选启用）

`.claude/settings.json` 在 `env` 块预留了占位（前缀 `_OTEL_EXAMPLE_`），生产启用时复制成正式键名：

```jsonc
{
  "env": {
    "CLAUDE_CODE_ENABLE_TELEMETRY": "1",
    "OTEL_METRICS_EXPORTER": "otlp",
    "OTEL_LOGS_EXPORTER": "otlp",
    "OTEL_EXPORTER_OTLP_ENDPOINT": "http://localhost:4318",
    "OTEL_EXPORTER_OTLP_PROTOCOL": "http/protobuf",
    "OTEL_LOG_USER_PROMPTS": "0"
  }
}
```

> 注意：`OTEL_LOG_USER_PROMPTS=1` 会把用户原始 prompt 推到 OTEL，可能含敏感信息。**生产固定为 0**，仅本地排障打开。

**有用的 event / attribute（Claude Code 2.1.117–2.1.126）**：
- `claude_code.skill_activated` 现带 `invocation_trigger`（`user-slash` / `claude-proactive` / `nested-skill`），可统计哪些 skill 真正被人类显式触发，用于识别"agent 自动绕路调用"型成本
- `cost.usage` / `token.usage` / `api_request` / `api_error` 在支持 effort 的模型上带 `effort` 属性，分级看 high/medium/low effort 的成本占比
- `tool_result` 带 `tool_use_id` 与 `tool_input_size_bytes`；`PostToolUse` hook 输入还带 `duration_ms`（已被 `sanitize-tool-output.sh` 用于 >10s 慢调用警告）

### 推荐对接

- 本地：`docker compose` 起 Jaeger / Grafana / Prometheus
- 团队：Datadog AI Agents Console、Honeycomb、Phoenix（开源）
- 参考：[ColeMurray/claude-code-otel](https://github.com/ColeMurray/claude-code-otel)

## 验收标准

- [ ] 后端服务有结构化日志，日志中无敏感字段
- [ ] LLM 调用日志包含 token 消耗与成本估算
- [ ] 关键接口 P95 延迟有监控面板
- [ ] Agent Team 协作过程的 token 消耗有事后可查的来源（`/usage` 截屏 / OTEL 导出）

## 边界

具体技术栈选型（哪个 APM、哪个日志后端）由 tech-lead 在 ADR 中决策；本基线只规定 **必须覆盖什么**、**禁止做什么**，不锁定供应商。
