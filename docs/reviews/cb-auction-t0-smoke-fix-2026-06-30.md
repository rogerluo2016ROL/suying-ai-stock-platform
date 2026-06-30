---
reviewer: code-reviewer
feature: cb-auction-t0-smoke-schema-fix
date: 2026-06-30
base_commit: deeed547
head_commit: 95448814
code_verdict: approve
sit_audit_verdict: "✅ Pass"
critical_count: 0
warning_count: 0
suggestion_count: 0
---

# 竞价选债 T+0 Smoke/Schema 修复复审

## Scope

- Review diff: `.superpowers/sdd/review-smoke-schema-fix-deeed547..95448814.diff`
- Base commit: `deeed547`
- Head commit: `95448814`
- Changed files:
  - `progress/backend-dev.md`
  - `services/sql/init_postgres.sql`
  - `services/data-service/app/sync/pg_writer.py`
  - `services/data-service/tests/test_limit_list_d_schema.py`
  - `docs/reviews/cb-auction-t0-doc-closeout-2026-06-30.md`

本次只做 review-only 复审；未修改源码，未重跑 SIT。

## Code Review

复审通过。

上一版审查中的 Important schema warning 已关闭：`limit_list_d` 初始化 schema 已改为真实口径，PG 写入 helper 也改为同一套 `ts_code/trade_date/limit_type` 唯一键，不再依赖旧的 `code` 主键。

### Critical

无。

### Important

无。

### Minor

无。

## Closed Findings

- `services/sql/init_postgres.sql:686` 原 warning 已关闭。当前表定义为 `id SERIAL PRIMARY KEY`、`trade_date TEXT NOT NULL`、`ts_code TEXT NOT NULL`、`limit_type TEXT NOT NULL`，并通过 `UNIQUE(ts_code, trade_date, limit_type)` 固化真实冲突键。
- `services/data-service/app/sync/pg_writer.py:176` 到 `services/data-service/app/sync/pg_writer.py:192` 已改为写入 `trade_date, ts_code, limit_type='U'...`，冲突键为 `["ts_code", "trade_date", "limit_type"]`。
- `progress/backend-dev.md:1912` 到 `progress/backend-dev.md:1943` 已补充本次 smoke/schema 修复的完整 SIT 证据段，原 SIT Audit `❌ Redo SIT` 已关闭。

## Review Notes

- `services/sql/init_postgres.sql:686` 到 `services/sql/init_postgres.sql:712` 与当前模型 SQL 需要的字段一致，包含 `ts_code`、`trade_date`、`limit_type`、`fd_amount`、`first_time` 等字段。
- `services/data-service/app/sync/pg_writer.py:181` 到 `services/data-service/app/sync/pg_writer.py:192` 的输入行顺序与 `services/data-service/app/sync/tushare.py:277` 到 `services/data-service/app/sync/tushare.py:281` 生成的 `limit_rows` 对齐。
- `services/data-service/app/scheduler.py:856` 到 `services/data-service/app/scheduler.py:862` 的盘中写入路径已经使用同一冲突键 `ts_code/trade_date/limit_type`，未被本次修复破坏。
- `services/data-service/tests/test_limit_list_d_schema.py:13` 到 `services/data-service/tests/test_limit_list_d_schema.py:81` 覆盖了两条关键回归线：PG writer 写入列/冲突键，以及 init SQL 不再定义旧 `code` 主键。
- 对目标范围执行文本核对，未发现 `cb_auction_t0` 目标 SQL 中残留 `l.code` / `p.code`。

## Security Review

OWASP Top 10 与项目安全基线逐项核对：

| Item | Result | Notes |
|---|---|---|
| A01 Broken Access Control | 无新增风险 | 本次未新增端点、鉴权或受保护资源访问。 |
| A02 Cryptographic Failures | 无新增风险 | 未处理密钥、加密或敏感数据存储。 |
| A03 Injection | 无新增风险 | SQL 写入仍走列白名单和参数化批量插入；本次没有拼接用户输入到 SQL。 |
| A04 Insecure Design | 无新增风险 | 修复目标是 schema SSOT 对齐，未改变模型交易规则或风险过滤策略。 |
| A05 Security Misconfiguration | 无新增风险 | 原 init SQL 与真实 PG schema 不一致的问题已修复并加测试固化。 |
| A06 Vulnerable Components | 未评估 | 无依赖变更。 |
| A07 Identification and Authentication Failures | 无新增风险 | 未改认证。 |
| A08 Software and Data Integrity Failures | 无新增风险 | 未新增反序列化、动态执行或供应链入口。 |
| A09 Security Logging and Monitoring Failures | 无新增风险 | 未新增敏感日志或错误暴露路径。 |
| A10 SSRF | 无新增风险 | 未新增外部 URL 请求。 |

项目铁律核对：

- 未修改交易执行、真实下单、BrokerInterface 或自动交易执行器。
- 未硬编码密钥、凭证或 API key。
- 未新增 shell 命令执行、`eval`、反序列化危险模式。
- 未新增前端改动；前后端契约强制项不适用。

## SIT Audit

Verdict: ✅ Pass

4 项检查：

1. progress 完整性: Pass。`progress/backend-dev.md:1912` 已新增 `竞价选债 T+0 — Smoke Fix: limit_list_d schema 兼容 - 2026-06-30`，包含标准 `**SIT 证据**` 段。
2. AC 覆盖: Pass。证据覆盖红灯回归、模型 SQL schema 修复、init SQL + PG writer schema 对齐、py_compile、真实 PG CLI 冒烟。
3. 证据可信度: Pass。证据包含真实命令与输出片段：单用例红灯失败摘要、`packages/kronos-factors/tests/test_cb_auction_t0.py -q` 输出 12 个点、`services/data-service/tests/test_limit_list_d_schema.py -q` 输出 2 个点、`py_compile` 退出码 0、真实 CLI 输出 `触发股票: 0 | 概念: 0 | 转债: 0` 并列出 JSON/CSV 产物。
4. 失败/阻塞标记真实性: Pass。红灯回归被明确标为修复前失败；当前没有 fail/blocked 被伪装成 pass。空结果有解释，属于当前数据下无触发股票，不是程序失败。

## Verification

Reviewer only; 未重跑 SIT。

只读核对：

- CodeGraph 读取 `_fetch_trigger_stocks`、`write_limit_list_d`、`sync_limit_list_d` 相关上下文。
- 审阅 `.superpowers/sdd/review-smoke-schema-fix-deeed547..95448814.diff`。
- 审阅 `services/sql/init_postgres.sql` 当前 `limit_list_d` 表定义。
- 审阅 `services/data-service/app/sync/pg_writer.py::write_limit_list_d()` 与 `services/data-service/app/sync/tushare.py` 输入行顺序。
- 审阅 `services/data-service/tests/test_limit_list_d_schema.py` 新增 schema 回归测试。
- 审阅 `progress/backend-dev.md` 新增 SIT 证据段。
- `git diff --check deeed547..95448814` 无输出。

## Verdict Rationale

- 代码 verdict: `approve`。原 Important 已关闭，复审范围内未发现新的 Critical / Important / Minor finding。
- SIT Audit verdict: `✅ Pass`。本次 smoke/schema 修复证据已补入 `progress/backend-dev.md`，覆盖完整且可信。

```agf-verdict
code_verdict: approve
sit_audit_verdict: ✅ Pass
critical_count: 0
warning_count: 0
suggestion_count: 0
critical_findings: []
warning_findings: []
suggestion_findings: []
rule: critical_count > 0 => block; warning_count > 0 => approve with changes; otherwise approve
derived_code_verdict: approve
```
