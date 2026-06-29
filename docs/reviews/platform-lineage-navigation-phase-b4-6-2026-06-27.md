# Platform Lineage Navigation Phase B4-6 Review

日期：2026-06-27

## 范围

- 风控闸门支持 `decision_context_id / order_id / plan_id / candidate_id / code` 深链查询。
- 新增 `DecisionContext` 页面，作为交易域证据下钻页。
- 交易中心订单行新增 `查看风控`，从订单直接进入对应风控判定查询。
- 风控判定行新增 `决策上下文`，进入对应上下文快照。

## 已验证

- 后端 RiskVerdict store/route 支持 lineage 条件查询。
- 前端 API client 可以序列化新增 lineage 查询参数。
- 风控闸门可从 URL 首次加载精确查询条件。
- DecisionContext 页面可从 URL 首次加载精确查询条件。
- 订单行、风控行、上下文页三者之间的跳转闭环有组件测试覆盖。

## 风险边界

- 本阶段只做查询、展示和导航联动。
- 未修改实盘交易执行器、BrokerInterface、Xtquant/QMT 对接路径。
- 下阶段如进入自动交易执行器写入或券商实盘链路，需要单独 Plan Mode 和技术评审。

## 下一步

- B4-7：回测复盘读取 `Order / RiskVerdict / DecisionContext`，按候选池、方案、订单生成复盘视图。
- B5：自动交易执行器补齐同一套 lineage 写入，并继续保持真实券商路径隔离。
