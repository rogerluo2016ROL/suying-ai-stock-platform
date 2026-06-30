---
reviewer: code-reviewer
code_verdict: approve
sit_audit_verdict: not_applicable
critical_count: 0
warning_count: 0
suggestion_count: 0
---

# 竞价选债 T+0 模型第 6 步文档收尾审查

## 范围

- base commit: `c669e891`
- head commit: `ade861ad`
- diff: `.superpowers/sdd/review-task-6-c669e891..ade861ad.diff`
- changed file: `docs/superpowers/specs/2026-06-30-cb-auction-t0-design.md`

本次只审查文档新增的“实现后的运行命令”段，不修改业务代码，不重跑模型。

## 结论

审查通过。

## Critical

无。

## Important

无。

## Minor

无。

## 审查要点

1. 新增“实现后的运行命令”清楚、可执行：`tools/cb_auction_t0_picks.py` 存在，支持位置参数 `trade_date`、`--top-n`、`--json-only`。
2. 风险口径没有误导：文档仍明确写明“转债不做硬过滤”和“风险只提示，不删除转债”，新增命令段没有引入风险过滤表述。
3. `KRONOS_PG_URL` 合理：现有引擎读取该环境变量，默认值也是 `postgresql://kronos:kronos@localhost:6432/kronos`。
4. 当前日命令和历史回放命令合理：当前日示例给出日期和 top-n，历史回放用循环和 `--json-only` 适合批量验证。
5. 20 个交易日验证提示合理：新增检查表覆盖现有实现使用的核心表 `limit_list_d`、`ths_member`、`ths_index`、`cb_basic`、`cb_daily`、`cb_call`。文档前文另列 `stocks` 为辅助表，但新增段强调“目标日期附近数据”的核心检查，不构成错误。
6. 未发现日期、表名、模型名错误：模型名 `cb_auction_t0`、入口 `tools/cb_auction_t0_picks.py`、引擎 `CbAuctionT0Engine` 与现有实现一致。

## SIT Audit

不适用。本次是文档收尾审查，用户要求审查文档 diff，没有提供也没有要求 audit `progress/<role>.md` 的 SIT 证据。

## agf-verdict

```yaml
code_verdict: approve
sit_audit_verdict: not_applicable
critical_count: 0
warning_count: 0
suggestion_count: 0
```
