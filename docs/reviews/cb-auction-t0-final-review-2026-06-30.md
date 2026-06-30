---
reviewer: code-reviewer
feature: cb-auction-t0-final
date: 2026-06-30
base_commit: cc1fac300da3fcf39dae29d014453cce3a6ff281
head_commit: f952a167
code_verdict: approve
sit_audit_verdict: "✅ Pass"
critical_count: 0
warning_count: 0
suggestion_count: 0
---

# 竞价选债 T+0 模型最终分支级审查

## Scope

- 原最终审查报告: `docs/reviews/cb-auction-t0-final-review-2026-06-30.md`
- 原最终审查 head: `30e9d76f17db8e2c179ba975543599b7944171cf`
- Final fixes base: `30e9d76f`
- Final fixes head: `f952a167`
- Review diff: `.superpowers/sdd/review-final-fixes-30e9d76f..HEAD.diff`
- Review mode: 只读复审；未重跑 SIT，未切换 HEAD，未修改源码。
- 唯一写入: 更新本审查报告。

复审文件：

- `tools/cb_auction_t0_picks.py`
- `packages/kronos-factors/tests/test_cb_auction_t0.py`
- `progress/backend-dev.md`

## Strengths

1. 模型触发方向正确：实现从股票涨停竞价触发，再映射到同花顺概念和转债，未从转债行情反推。
2. 核心触发 SQL 已对齐 `limit_list_d.ts_code/trade_date/limit_type`，并有 schema 回归测试保护。
3. 风险字段没有参与排序或过滤：强赎、溢价、成交额、剩余规模、退市日期只进入字段或 `risk_notes`。
4. 排序主键符合题材相关性：直接触发、命中概念数、触发股票数、封单金额、细分概念规模优先，没有把溢价率、成交额、强赎状态放入主排序。
5. 服务接入是独立 `mode == "cb_auction_t0"` 分支，旧 `cb_floor` / `cb_intraday` / 默认 `cb_auction` 路径没有被改写。
6. Final SIT 证据已按 AC-1 到 AC-10 覆盖完整用户规则，并包含真实 PG 空结果解释和非空 fixture 证据。

## Critical Findings

无。

## Important Findings

无。

## Minor Findings

无。

## Closed Findings

### W-1: Final SIT 证据不足 — 已关闭

- 原位置: `progress/backend-dev.md:1892`
- 关闭位置: `progress/backend-dev.md:1947`
- 复审结论: 已关闭。新增“竞价选债 T+0 — Final SIT: 完整业务 AC 验证 - 2026-06-30”段，按 AC-1 到 AC-10 覆盖股票触发、前日涨停排除、THS 概念、风险只提示、题材排序、JSON/CSV、`top_n`、schema、服务接入和真实 PG smoke。
- 证据可信度: 证据包含真实命令和输出片段：`14 passed`、`2 passed`、`py_compile` 退出码 0、真实 PG CLI 输出 `触发股票: 0 | 概念: 0 | 转债: 0` 并导出 JSON/CSV。当前真实数据为空结果有明确解释，同时用 fixture 单测覆盖非空路径。

### S-1: CLI `--top-n` 允许负数 — 已关闭

- 原位置: `tools/cb_auction_t0_picks.py:22`
- 关闭位置: `tools/cb_auction_t0_picks.py:94`
- 复审结论: 已关闭。`main()` 解析参数后增加 `if args.top_n < 0: parser.error("--top-n must be >= 0")`，避免负数进入引擎并触发 Python 切片。
- 测试: `packages/kronos-factors/tests/test_cb_auction_t0.py:441` 新增 `test_cli_rejects_negative_top_n_before_running_engine`，验证 `--top-n -1` 在进入引擎前报错，退出码为 2。

## Security Review

OWASP Top 10 与项目安全基线核对：

| Item | Result | Notes |
|---|---|---|
| A01 Broken Access Control | 无新增风险 | Final fixes 未新增鉴权入口；只补 CLI 参数校验、测试和 SIT 证据。 |
| A02 Cryptographic Failures | 无新增风险 | 未处理密钥、加密或敏感数据。 |
| A03 Injection | 无新增风险 | 本次修复不改 SQL；负数参数校验减少异常输入面。 |
| A04 Insecure Design | 无新增风险 | Final SIT 已证明模型只输出观察清单，不执行交易；风险不过滤但有提示。 |
| A05 Security Misconfiguration | 无新增风险 | `limit_list_d` schema 对齐证据保留，final fixes 未改部署配置。 |
| A06 Vulnerable Components | 未评估 | 无依赖变更。 |
| A07 Identification and Authentication Failures | 无新增风险 | 未改登录、token、session。 |
| A08 Software and Data Integrity Failures | 无新增风险 | 未新增反序列化、动态执行、供应链下载。 |
| A09 Security Logging and Monitoring Failures | 无新增风险 | 未新增安全审计日志要求。 |
| A10 SSRF | 无新增风险 | 未新增外部 URL 请求。 |

项目铁律核对：

- 未新增真实下单、交易执行或 broker 调用。
- 未硬编码 API key、token 或密码。
- 未新增前端改动；前后端契约强制项不适用。
- 未发现新增 `eval`、`os.system`、危险反序列化等执行路径。

## SIT Audit

Verdict: ✅ Pass

4 项 audit 检查：

1. progress 完整性: Pass。`progress/backend-dev.md:1947` 起新增 Final SIT 证据段，标题明确，按 AC-1 到 AC-10 列出完整条目。
2. AC 覆盖: Pass。证据覆盖最终用户规则：股票触发、`limit_type='U'`、`first_time <= 09:30:00`、`fd_amount > 10 亿`、缺失拒绝、前日涨停排除、THS 概念、风险只提示、题材相关性排序、JSON/CSV、服务接入和空结果解释。
3. 证据可信度: Pass。证据包含真实工具命令和输出片段：`bash tools/codex-lowio.sh py packages/kronos-factors/tests/test_cb_auction_t0.py -q` 输出 `.............. [100%]`，schema 测试 `.. [100%]`，`py_compile` 退出码 0，真实 PG CLI smoke 输出和导出路径。
4. 失败/阻塞标记真实性: Pass。当前真实 PG 结果为 0 触发股票，证据明确解释为真实数据下无满足条件触发；没有把失败伪装成 pass。非空路径由 fixture 单测覆盖。

## Verification

Reviewer 只读核对：

- `git diff --stat 30e9d76f..f952a167`
- `git diff --name-only 30e9d76f..f952a167`
- `.superpowers/sdd/review-final-fixes-30e9d76f..HEAD.diff`
- `nl -ba` 核对新增校验、测试和 Final SIT 证据行号。
- `git diff --check 30e9d76f..f952a167 -- tools/cb_auction_t0_picks.py packages/kronos-factors/tests/test_cb_auction_t0.py progress/backend-dev.md` 无输出。
- 未重跑 SIT。

## Assessment

Ready to merge? Yes.

W-1 已关闭，SIT Audit 变为 ✅ Pass。S-1 已关闭。复审范围内没有新的 Critical / Important / Minor finding。

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
