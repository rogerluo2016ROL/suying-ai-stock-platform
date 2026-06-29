# Platform Backtest Lineage Review Phase B4-7 Review

日期：2026-06-27

## 范围

- 回测分析页新增 `交易复盘` 页签。
- 前端聚合读取 `Order / RiskVerdict / DecisionContext` 三类对象。
- 按 `order_id` 与 `decision_context_id` 合并复盘链路。
- 支持从复盘行继续下钻到风控闸门和决策上下文页面。

## 已验证

- 新增组件测试覆盖回测页签切换、三接口读取、链路字段展示。
- 复盘页签读取 `tradeApi.getOrders()`、`tradeApi.getRiskVerdicts({ page: 1, page_size: 50 })`、`tradeApi.getDecisionContexts({ page: 1, page_size: 50 })`。
- 页面展示订单、风控判定、上下文 payload 摘要。

## 风险边界

- 未修改回测算法。
- 未修改实盘交易执行器。
- 未修改 BrokerInterface、Xtquant、QMT 或其他券商适配路径。

## 下一步

- B5：自动交易执行器补齐 DecisionContext / Candidate / Plan / Order / RiskVerdict 的统一写入与查询链路。
- 进入 B5 前需要对实盘相关代码保持计划评审边界，只先接模拟盘和审计写入。
