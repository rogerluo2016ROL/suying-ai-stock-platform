# 全站页面联通盘点

日期：2026-06-29

## 结论摘要

本报告由 `tools/page_connectivity_inventory.py` 静态生成，用于定位页面到前端 API 的连接情况。它不替代真实 API smoke 或浏览器 UAT。

### 最终闭环补充

2026-06-29 晚间已完成 UAT 复测：

- `tools/page_api_smoke.py --include-actions` 返回 `status=ok`。
- 供应链 `themes/bom/workbench/chain.candidates/mapping-review/quality` 全部 OK。
- 预测 `status/predict/overview/compare/accuracy-backtest` 全部 OK。
- 交易账户、持仓、订单、风控、券商状态、审计、风险判定、决策上下文、`order/pre-check` 全部 OK。
- 训练与模型注册返回真实数据库模型：`mdl-uat-lightgbm-ranker-v1/v2`。
- 策略方案与自动交易策略均已 PostgreSQL 持久化，重启后 API 仍能返回。
- 本报告下方矩阵中的 `needs-smoke` 是静态盘点标签，不表示最终仍未通过；最终验证以本补充和 `full-stack-page-api-smoke-2026-06-29.md` 为准。

### 风险分布

- high: 32
- medium: 35

### 状态分布

- needs-smoke: 67

## 逐菜单修复记录

| 菜单 | 处理结果 | 验证 |
|---|---|---|
| 智能看板 | 已清理默认样本股和固定信号统计，改为真实 dashboard / signal / auction 数据和空态。 | `Dashboard.test.tsx`、`fe-typecheck`、`page_api_smoke.py` |
| 开盘决策 | 已复核竞价、信号、候选、交易、风控接口链路，focused 测试通过。 | `OpenDecision.test.tsx`、`page_api_smoke.py` |
| 智能选股 | 已删除默认候选样本股；运行前和空结果显示真实空态；右侧明细改为后端因子/指标驱动；无后端写接口的候选池/自选按钮禁用并标注原因；导出 CSV、诊断/回测跳转可用。 | `Screener.test.tsx`、`fe-typecheck`、真实 `screener.run` smoke |
| 产业链拆解 | 已确认 workbench、`chain/candidates`、`mapping-review/quality` 均可用；UAT 镜像缺失 BOM 模块的问题已通过同步 `kronos_factors.engine.supply_chain_bom` 与配置修复。 | `SupplyChainBom.test.tsx`、`fe-typecheck`、真实 supply-chain API smoke |
| K线预测 | 已删除默认宁德时代假预测和固定组合/回测指标；页面加载真实 `prediction/status`；单股预测、`prediction/compare`、`prediction/overview`、`accuracy-backtest` 均已接通。 | `Predictions.test.tsx`、`fe-typecheck`、真实 prediction API smoke |
| 交易信号 | 已删除默认宁德时代/中芯国际/贵州茅台样本信号和固定历史记录；实时、历史、风险扫描均改为真实接口驱动；接口为空时展示真实空态；没有实时信号时不调用风险扫描模型。 | `Signals.test.tsx`、`fe-typecheck`、真实 signal API smoke |
| 个股诊断 | 已删除默认写死诊断标的；输入、历史、五维评分、风险扫描均按真实诊断报告驱动；多股对比接入 `diagnosis/compare`；导出报告接入 `diagnosis/report/{code}/pdf`，并按真实 content-type 决定下载扩展名。 | `Diagnosis.test.tsx`、`Phase5SystemPages.test.tsx`、`fe-typecheck`、真实 diagnosis API smoke |
| 策略实验 | 已保留真实 `strategy/plans` 链路并清理固定最大回撤/换手率；详情页支持 `plan_id` 指定方案；报告页使用后端时间字段，不再显示“服务实时”假状态。 | `StrategyConnectivity.test.tsx`、`fe-typecheck`、真实 strategy API smoke |
| 回测分析 | 已删除固定最近回测、平均收益、收益曲线和静态策略对比；运行回测按钮接入 `backtest/run`；策略对比接入 `backtest/compare`；兼容 UAT 当前 `summary/details` 与 `strategies` 返回结构；交易复盘继续聚合 Order/RiskVerdict/DecisionContext。 | `BacktestConnectivity.test.tsx`、`BacktestLineageReview.test.tsx`、`fe-typecheck`、真实 backtest API smoke |
| 模拟交易 | 已删除固定宁德时代/中芯国际持仓和 ORD-001/ORD-002 订单；账户、持仓、订单改为 `tradeApi` 真实数据；券商页展示 hook/风控配置真实状态；模拟盘预检 `trade/order/pre-check` 已接通。 | `TradeConnectivity.test.tsx`、`TradeFormValidation.test.tsx`、`useLiveTrade.test.tsx`、`fe-typecheck`、真实 trade API smoke |
| 交易工作台 | 已删除策略列表失败时的“模拟趋势策略”回退；策略列表、详情、日志和模拟盘启动/停止动作接真实 strategy 接口；日志 404 显示“执行器未启动”，配置页展示策略服务返回的真实参数。 | `AutoTradeLineageLog.test.tsx`、`fe-typecheck`、真实 auto-trade API smoke |
| 风险控制 | 已保留真实 RiskVerdict/DecisionContext/AuditLog/RiskConfig 链路；接口改为局部失败不清空全部数据；市场风险页用真实空态替代伪造上下文。 | `Phase4WorkflowPages.test.tsx`、`fe-typecheck`、真实 risk API smoke |
| 训练中心 | 已改为局部接口失败不清空全部训练数据；`training/models` 可返回 UAT PostgreSQL 中的生产/候选模型记录。 | `Phase5SystemPages.test.tsx`、`fe-typecheck`、真实 training API smoke |
| 模型注册 | 已接入模型详情、部署、回滚、归档 API helper；页面按真实模型阶段启用动作，UAT 已有生产/候选模型种子数据。 | `Phase5SystemPages.test.tsx`、`fe-typecheck`、真实 model-registry API smoke |
| 运行状态 | 已把模型服务、交易链路和运行闸门文案改为真实 health 结果驱动；单服务失败时显示对应异常，不再固定展示“模型服务在线”。 | `Phase5SystemPages.test.tsx`、`fe-typecheck`、真实 runtime health smoke |
| 平台升级 | 已保留真实 health / training / trade 聚合；券商状态接口失败时显示“未知”，不再默认成 Paper；公共模型为空时展示“无模型”。 | `Phase5SystemPages.test.tsx`、`fe-typecheck`、真实 platform API smoke |

## 页面矩阵

| 路由 | 页面 | 风险 | 状态 | API/动作 | 备注 |
|---|---|---|---|---|---|
| `/` | `Dashboard` | `medium` | `needs-smoke` | `signalApi.getDashboardAuction`<br>`signalApi.getDashboardSummary`<br>`signalApi.getScreeningDashboardSummary` | - |
| `/dashboard/auction` | `Dashboard` | `medium` | `needs-smoke` | `signalApi.getDashboardAuction`<br>`signalApi.getDashboardSummary`<br>`signalApi.getScreeningDashboardSummary` | - |
| `/dashboard/signals` | `Dashboard` | `medium` | `needs-smoke` | `signalApi.getDashboardAuction`<br>`signalApi.getDashboardSummary`<br>`signalApi.getScreeningDashboardSummary` | - |
| `/dashboard/watchlist` | `Dashboard` | `medium` | `needs-smoke` | `signalApi.getDashboardAuction`<br>`signalApi.getDashboardSummary`<br>`signalApi.getScreeningDashboardSummary` | - |
| `/open-decision` | `OpenDecision` | `medium` | `needs-smoke` | `chainApi.getCandidates`<br>`signalApi.getDashboardAuction`<br>`signalApi.getLive`<br>`tradeApi.getAccount`<br>`tradeApi.getDecisionContexts`<br>`tradeApi.getOrders`<br>`tradeApi.getPositions`<br>`tradeApi.getRiskVerdicts` | - |
| `/open-decision/auction` | `OpenDecision` | `medium` | `needs-smoke` | `chainApi.getCandidates`<br>`signalApi.getDashboardAuction`<br>`signalApi.getLive`<br>`tradeApi.getAccount`<br>`tradeApi.getDecisionContexts`<br>`tradeApi.getOrders`<br>`tradeApi.getPositions`<br>`tradeApi.getRiskVerdicts` | - |
| `/open-decision/signals` | `OpenDecision` | `medium` | `needs-smoke` | `chainApi.getCandidates`<br>`signalApi.getDashboardAuction`<br>`signalApi.getLive`<br>`tradeApi.getAccount`<br>`tradeApi.getDecisionContexts`<br>`tradeApi.getOrders`<br>`tradeApi.getPositions`<br>`tradeApi.getRiskVerdicts` | - |
| `/open-decision/candidates` | `OpenDecision` | `medium` | `needs-smoke` | `chainApi.getCandidates`<br>`signalApi.getDashboardAuction`<br>`signalApi.getLive`<br>`tradeApi.getAccount`<br>`tradeApi.getDecisionContexts`<br>`tradeApi.getOrders`<br>`tradeApi.getPositions`<br>`tradeApi.getRiskVerdicts` | - |
| `/open-decision/execution` | `OpenDecision` | `medium` | `needs-smoke` | `chainApi.getCandidates`<br>`signalApi.getDashboardAuction`<br>`signalApi.getLive`<br>`tradeApi.getAccount`<br>`tradeApi.getDecisionContexts`<br>`tradeApi.getOrders`<br>`tradeApi.getPositions`<br>`tradeApi.getRiskVerdicts` | - |
| `/screener` | `Screener` | `medium` | `needs-smoke` | `screenerApi.run`<br>`signalApi.triggerSync` | - |
| `/screener/models` | `Screener` | `medium` | `needs-smoke` | `screenerApi.run`<br>`signalApi.triggerSync` | - |
| `/screener/factors` | `Screener` | `medium` | `needs-smoke` | `screenerApi.run`<br>`signalApi.triggerSync` | - |
| `/supply-chain-bom` | `SupplyChainBom` | `high` | `needs-smoke` | `chainApi.deconstructChain`<br>`chainApi.getCandidates`<br>`chainApi.interpretPolicy`<br>`screenerApi.getSupplyChainCompany`<br>`screenerApi.getSupplyChainMappingQuality`<br>`screenerApi.getSupplyChainMappingReviewQueue`<br>`screenerApi.getSupplyChainNode`<br>`screenerApi.getSupplyChainWorkbench`<br>`screenerApi.reviewSupplyChainMapping` | - |
| `/supply-chain-bom/policy` | `SupplyChainBom` | `high` | `needs-smoke` | `chainApi.deconstructChain`<br>`chainApi.getCandidates`<br>`chainApi.interpretPolicy`<br>`screenerApi.getSupplyChainCompany`<br>`screenerApi.getSupplyChainMappingQuality`<br>`screenerApi.getSupplyChainMappingReviewQueue`<br>`screenerApi.getSupplyChainNode`<br>`screenerApi.getSupplyChainWorkbench`<br>`screenerApi.reviewSupplyChainMapping` | - |
| `/supply-chain-bom/company` | `SupplyChainBom` | `high` | `needs-smoke` | `chainApi.deconstructChain`<br>`chainApi.getCandidates`<br>`chainApi.interpretPolicy`<br>`screenerApi.getSupplyChainCompany`<br>`screenerApi.getSupplyChainMappingQuality`<br>`screenerApi.getSupplyChainMappingReviewQueue`<br>`screenerApi.getSupplyChainNode`<br>`screenerApi.getSupplyChainWorkbench`<br>`screenerApi.reviewSupplyChainMapping` | - |
| `/predictions` | `Predictions` | `medium` | `needs-smoke` | `predictionApi.predict` | - |
| `/predictions/single` | `Predictions` | `medium` | `needs-smoke` | `predictionApi.predict` | - |
| `/predictions/compare` | `Predictions` | `medium` | `needs-smoke` | `predictionApi.predict` | - |
| `/predictions/backtest` | `Predictions` | `medium` | `needs-smoke` | `predictionApi.predict` | - |
| `/strategy` | `Strategy` | `high` | `needs-smoke` | `strategyApi.getPlans` | - |
| `/strategy/detail` | `Strategy` | `high` | `needs-smoke` | `strategyApi.getPlans` | - |
| `/strategy/compare` | `Strategy` | `high` | `needs-smoke` | `strategyApi.getPlans` | - |
| `/strategy/reports` | `Strategy` | `high` | `needs-smoke` | `strategyApi.getPlans` | - |
| `/signals` | `Signals` | `medium` | `needs-smoke` | `signalApi.analyzeCode`<br>`signalApi.getHistory`<br>`signalApi.getLive` | - |
| `/signals/overview` | `Signals` | `medium` | `needs-smoke` | `signalApi.analyzeCode`<br>`signalApi.getHistory`<br>`signalApi.getLive` | - |
| `/signals/history` | `Signals` | `medium` | `needs-smoke` | `signalApi.analyzeCode`<br>`signalApi.getHistory`<br>`signalApi.getLive` | - |
| `/signals/risk` | `Signals` | `medium` | `needs-smoke` | `signalApi.analyzeCode`<br>`signalApi.getHistory`<br>`signalApi.getLive` | - |
| `/trade` | `Trade` | `high` | `needs-smoke` | `liveTradeApi.connectBroker`<br>`liveTradeApi.getBrokerStatus`<br>`liveTradeApi.getCircuitBreakerStatus`<br>`liveTradeApi.getRiskConfig`<br>`liveTradeApi.placeOrder`<br>`liveTradeApi.preCheck` | - |
| `/trade/order` | `Trade` | `high` | `needs-smoke` | `liveTradeApi.connectBroker`<br>`liveTradeApi.getBrokerStatus`<br>`liveTradeApi.getCircuitBreakerStatus`<br>`liveTradeApi.getRiskConfig`<br>`liveTradeApi.placeOrder`<br>`liveTradeApi.preCheck` | - |
| `/trade/positions` | `Trade` | `high` | `needs-smoke` | `liveTradeApi.connectBroker`<br>`liveTradeApi.getBrokerStatus`<br>`liveTradeApi.getCircuitBreakerStatus`<br>`liveTradeApi.getRiskConfig`<br>`liveTradeApi.placeOrder`<br>`liveTradeApi.preCheck` | - |
| `/trade/orders` | `Trade` | `high` | `needs-smoke` | `liveTradeApi.connectBroker`<br>`liveTradeApi.getBrokerStatus`<br>`liveTradeApi.getCircuitBreakerStatus`<br>`liveTradeApi.getRiskConfig`<br>`liveTradeApi.placeOrder`<br>`liveTradeApi.preCheck` | - |
| `/trade/account` | `Trade` | `high` | `needs-smoke` | `liveTradeApi.connectBroker`<br>`liveTradeApi.getBrokerStatus`<br>`liveTradeApi.getCircuitBreakerStatus`<br>`liveTradeApi.getRiskConfig`<br>`liveTradeApi.placeOrder`<br>`liveTradeApi.preCheck` | - |
| `/trade/brokers` | `Trade` | `high` | `needs-smoke` | `liveTradeApi.connectBroker`<br>`liveTradeApi.getBrokerStatus`<br>`liveTradeApi.getCircuitBreakerStatus`<br>`liveTradeApi.getRiskConfig`<br>`liveTradeApi.placeOrder`<br>`liveTradeApi.preCheck` | - |
| `/trade/audit-log` | `AuditLog` | `high` | `needs-smoke` | `liveTradeApi.exportAuditLogs`<br>`liveTradeApi.getAuditLogs` | - |
| `/trade/risk-verdicts` | `RiskVerdicts` | `high` | `needs-smoke` | `tradeApi.getRiskVerdicts` | - |
| `/trade/decision-contexts` | `DecisionContexts` | `high` | `needs-smoke` | `tradeApi.getDecisionContexts` | - |
| `/auto-trade` | `AutoTrade` | `high` | `needs-smoke` | `api.get('/strategy/list')`<br>`api.get(`/strategy/${strategy.id}/log`)`<br>`api.get(`/strategy/${strategy.id}`)` | - |
| `/auto-trade/config` | `AutoTrade` | `high` | `needs-smoke` | `api.get('/strategy/list')`<br>`api.get(`/strategy/${strategy.id}/log`)`<br>`api.get(`/strategy/${strategy.id}`)` | - |
| `/auto-trade/monitor` | `AutoTrade` | `high` | `needs-smoke` | `api.get('/strategy/list')`<br>`api.get(`/strategy/${strategy.id}/log`)`<br>`api.get(`/strategy/${strategy.id}`)` | - |
| `/auto-trade/logs` | `AutoTrade` | `high` | `needs-smoke` | `api.get('/strategy/list')`<br>`api.get(`/strategy/${strategy.id}/log`)`<br>`api.get(`/strategy/${strategy.id}`)` | - |
| `/risk` | `RiskControl` | `high` | `needs-smoke` | `liveTradeApi.getAuditLogs`<br>`liveTradeApi.getRiskConfig`<br>`tradeApi.getDecisionContexts`<br>`tradeApi.getRiskVerdicts` | - |
| `/risk/overview` | `RiskControl` | `high` | `needs-smoke` | `liveTradeApi.getAuditLogs`<br>`liveTradeApi.getRiskConfig`<br>`tradeApi.getDecisionContexts`<br>`tradeApi.getRiskVerdicts` | - |
| `/risk/positions` | `RiskControl` | `high` | `needs-smoke` | `liveTradeApi.getAuditLogs`<br>`liveTradeApi.getRiskConfig`<br>`tradeApi.getDecisionContexts`<br>`tradeApi.getRiskVerdicts` | - |
| `/risk/strategies` | `RiskControl` | `high` | `needs-smoke` | `liveTradeApi.getAuditLogs`<br>`liveTradeApi.getRiskConfig`<br>`tradeApi.getDecisionContexts`<br>`tradeApi.getRiskVerdicts` | - |
| `/risk/market` | `RiskControl` | `high` | `needs-smoke` | `liveTradeApi.getAuditLogs`<br>`liveTradeApi.getRiskConfig`<br>`tradeApi.getDecisionContexts`<br>`tradeApi.getRiskVerdicts` | - |
| `/risk/audit` | `RiskControl` | `high` | `needs-smoke` | `liveTradeApi.getAuditLogs`<br>`liveTradeApi.getRiskConfig`<br>`tradeApi.getDecisionContexts`<br>`tradeApi.getRiskVerdicts` | - |
| `/backtest` | `Backtest` | `medium` | `needs-smoke` | `backtestApi.getFactors`<br>`tradeApi.getDecisionContexts`<br>`tradeApi.getOrders`<br>`tradeApi.getRiskVerdicts` | - |
| `/backtest/run` | `Backtest` | `medium` | `needs-smoke` | `backtestApi.getFactors`<br>`tradeApi.getDecisionContexts`<br>`tradeApi.getOrders`<br>`tradeApi.getRiskVerdicts` | - |
| `/backtest/compare` | `Backtest` | `medium` | `needs-smoke` | `backtestApi.getFactors`<br>`tradeApi.getDecisionContexts`<br>`tradeApi.getOrders`<br>`tradeApi.getRiskVerdicts` | - |
| `/backtest/trades` | `Backtest` | `medium` | `needs-smoke` | `backtestApi.getFactors`<br>`tradeApi.getDecisionContexts`<br>`tradeApi.getOrders`<br>`tradeApi.getRiskVerdicts` | - |
| `/diagnosis` | `Diagnosis` | `medium` | `needs-smoke` | `diagnosisApi.analyze`<br>`diagnosisApi.getHistory` | - |
| `/diagnosis/overview` | `Diagnosis` | `medium` | `needs-smoke` | `diagnosisApi.analyze`<br>`diagnosisApi.getHistory` | - |
| `/diagnosis/model` | `Diagnosis` | `medium` | `needs-smoke` | `diagnosisApi.analyze`<br>`diagnosisApi.getHistory` | - |
| `/diagnosis/compare` | `Diagnosis` | `medium` | `needs-smoke` | `diagnosisApi.analyze`<br>`diagnosisApi.getHistory` | - |
| `/diagnosis/risk` | `Diagnosis` | `medium` | `needs-smoke` | `diagnosisApi.analyze`<br>`diagnosisApi.getHistory` | - |
| `/training` | `Training` | `high` | `smoke-ok` | `trainingApi.getHistory`<br>`trainingApi.getModels`<br>`trainingApi.getSchedule` | UAT 返回 `models` / `jobs` / `schedule`。 |
| `/training/tasks` | `Training` | `high` | `smoke-ok` | `trainingApi.getHistory`<br>`trainingApi.getModels`<br>`trainingApi.getSchedule` | UAT 返回 `models` / `jobs` / `schedule`。 |
| `/training/mlflow` | `Training` | `high` | `smoke-ok` | `trainingApi.getHistory`<br>`trainingApi.getModels`<br>`trainingApi.getSchedule` | UAT 返回 `models` / `jobs` / `schedule`。 |
| `/model-registry` | `ModelRegistry` | `high` | `smoke-ok` | `trainingApi.getModels`<br>`trainingApi.getModel`<br>`trainingApi.deployModel`<br>`trainingApi.rollbackModel`<br>`trainingApi.archiveModel` | UAT `training/models` 可用；当前无注册模型，详情/对比跳过，部署/回滚/归档未做破坏性调用。 |
| `/data-update` | `DataUpdate` | `medium` | `needs-smoke` | `signalApi.getDataStatus`<br>`signalApi.getSyncSchedules` | - |
| `/data-update/overview` | `DataUpdate` | `medium` | `needs-smoke` | `signalApi.getDataStatus`<br>`signalApi.getSyncSchedules` | - |
| `/data-update/tables` | `DataUpdate` | `medium` | `needs-smoke` | `signalApi.getDataStatus`<br>`signalApi.getSyncSchedules` | - |
| `/data-update/schedule` | `DataUpdate` | `medium` | `needs-smoke` | `signalApi.getDataStatus`<br>`signalApi.getSyncSchedules` | - |
| `/runtime` | `RuntimeStatus` | `high` | `smoke-ok` | `healthApi.check`<br>`healthApi.gateway` | UAT 网关和 8 个服务 health 直连/网关转发均 OK。 |
| `/runtime-status` | `RuntimeStatus` | `high` | `smoke-ok` | `healthApi.check`<br>`healthApi.gateway` | UAT 网关和 8 个服务 health 直连/网关转发均 OK。 |
| `/workflow/p0` | `P0Workflow` | `medium` | `needs-smoke` | `backtestApi.getFactors`<br>`chainApi.getCandidates`<br>`signalApi.getLive`<br>`strategyApi.getPlans`<br>`tradeApi.getDecisionContexts`<br>`tradeApi.getOrders`<br>`tradeApi.getRiskVerdicts` | - |
| `/platform/upgrade` | `PlatformUpgrade` | `medium` | `smoke-ok` | `healthApi.check`<br>`healthApi.gateway`<br>`liveTradeApi.getBrokerStatus`<br>`liveTradeApi.getRiskConfig`<br>`trainingApi.getModels` | UAT gateway/auth/trade/training health、training/models、broker-status、risk-config 均 OK。 |

## 高风险清单

- `/supply-chain-bom` / `SupplyChainBom`：needs-smoke，needs real API smoke
- `/supply-chain-bom/policy` / `SupplyChainBom`：needs-smoke，needs real API smoke
- `/supply-chain-bom/company` / `SupplyChainBom`：needs-smoke，needs real API smoke
- `/strategy` / `Strategy`：needs-smoke，needs real API smoke
- `/strategy/detail` / `Strategy`：needs-smoke，needs real API smoke
- `/strategy/compare` / `Strategy`：needs-smoke，needs real API smoke
- `/strategy/reports` / `Strategy`：needs-smoke，needs real API smoke
- `/trade` / `Trade`：needs-smoke，needs real API smoke
- `/trade/order` / `Trade`：needs-smoke，needs real API smoke
- `/trade/positions` / `Trade`：needs-smoke，needs real API smoke
- `/trade/orders` / `Trade`：needs-smoke，needs real API smoke
- `/trade/account` / `Trade`：needs-smoke，needs real API smoke
- `/trade/brokers` / `Trade`：needs-smoke，needs real API smoke
- `/trade/audit-log` / `AuditLog`：needs-smoke，needs real API smoke
- `/trade/risk-verdicts` / `RiskVerdicts`：needs-smoke，needs real API smoke
- `/trade/decision-contexts` / `DecisionContexts`：needs-smoke，needs real API smoke
- `/auto-trade` / `AutoTrade`：needs-smoke，needs real API smoke
- `/auto-trade/config` / `AutoTrade`：needs-smoke，needs real API smoke
- `/auto-trade/monitor` / `AutoTrade`：needs-smoke，needs real API smoke
- `/auto-trade/logs` / `AutoTrade`：needs-smoke，needs real API smoke
- `/risk` / `RiskControl`：needs-smoke，needs real API smoke
- `/risk/overview` / `RiskControl`：needs-smoke，needs real API smoke
- `/risk/positions` / `RiskControl`：needs-smoke，needs real API smoke
- `/risk/strategies` / `RiskControl`：needs-smoke，needs real API smoke
- `/risk/market` / `RiskControl`：needs-smoke，needs real API smoke
- `/risk/audit` / `RiskControl`：needs-smoke，needs real API smoke

## 下一步

1. 用 `tools/page_api_smoke.py` 对 `needs-smoke` 页面接口做真实服务验证。
2. 如出现 `stale-contract` 页面，先核对后端路由，再修前端 API helper。
3. 对 `prototype-only` 系统/模型页补真实服务状态，不能真实启用的功能必须显示禁用原因。
