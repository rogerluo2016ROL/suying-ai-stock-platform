# Platform Auto Executor Lineage Phase B5 Review

日期：2026-06-27

## 范围

- strategy-service 自动交易执行器下单时透传 `decision_context_id / candidate_id / plan_id`。
- 自动执行日志写入同一套 lineage，供前端量化交易详情抽屉展示。
- 前端 AutoTrade 日志将 lineage 从 JSON 中提取为标签，并提供风控与上下文下钻按钮。

## 已验证

- `_place_order` 会把 lineage 字段传给 trade-service。
- `_run_one_check` BUY 自动下单会从 strategy/pick 生成 lineage。
- 自动执行日志会记录 `decision_context_id / candidate_id / plan_id / order_id`。
- DB 风控不可用 fail-safe 行为保持不变：暂停执行器且不下单。
- AutoTrade 前端日志可展示 lineage 并跳转到风控页。

## 风险边界

- 未修改真实券商 BrokerInterface。
- 未修改 Xtquant/QMT 适配。
- 未修改 live order circuit breaker。
- 未新增实盘交易行为。

## 下一步

- B6：前后端联调启动，验证策略生成 -> 自动执行 -> 模拟盘下单 -> 风控闸门 -> 决策上下文 -> 回测复盘的全链路。
- 真实券商接入进入独立阶段，先做 MockBroker/QMT sandbox 双轨验证。
