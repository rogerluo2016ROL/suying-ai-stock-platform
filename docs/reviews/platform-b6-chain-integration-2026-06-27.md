# Platform B6 Chain Integration Review

日期：2026-06-27

## 范围

- 建立 P0 主链路模拟盘联调守门：自动执行 -> 模拟下单 -> 风控 -> 决策上下文 -> 回测复盘。
- 修复 strategy-service 自动执行器向 trade-service 下单时使用 query string POST 的问题，改为 JSON body。
- 新增 `tools/b6_platform_chain_smoke.py`，用于服务启动后的 API 级 smoke。
- 新增前端跨页面链路测试，覆盖 AutoTrade 日志下钻到 RiskVerdicts 与 DecisionContexts，并在 Backtest 交易复盘中展示同一条链路。

## 已验证

- trade-service route 层下单后，DecisionContext、RiskVerdict、Order 三类持久化 helper 接收同一组 lineage。
- strategy-service `_place_order` 使用 JSON body 向 trade-service 下单，并保留 lineage 字段。
- AutoTrade -> RiskVerdicts -> DecisionContexts 前端跳转链路通过。
- Backtest 交易复盘显示同一条 Order/RiskVerdict/DecisionContext 链路。
- B6 smoke 脚本语法通过。

## 风险边界

- 未修改 BrokerInterface。
- 未修改 Xtquant/QMT。
- 未修改 live circuit breaker。
- 未触发真实券商下单。

## 下一步

- B7：启动本地服务，跑 `tools/b6_platform_chain_smoke.py` 做 API 级真实联调。
- B8：设计 MockBroker/QMT sandbox 双轨，准备实盘接入前的风控与权限闸门。
